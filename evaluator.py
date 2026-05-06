from __future__ import annotations

from typing import Callable

from test_queries import TEST_QUERIES, CATEGORY_LABELS

NO_DOCS_MARKER = "don't have any relevant"


def _actual_outcome(result: dict) -> str:
    if result.get("blocked"):
        return "blocked"
    if NO_DOCS_MARKER in result.get("response", "").lower():
        return "no_docs"
    return "answered"


class Evaluator:
    def __init__(self, rag):
        self.rag = rag
        self.results: list[dict] = []

    def run(self, progress_cb: Callable[[int, int], None] | None = None) -> dict:
        self.results = []
        queries = TEST_QUERIES

        for i, test in enumerate(queries):
            original_role = self.rag.access_control.user_role
            self.rag.access_control.user_role = test["role"]

            try:
                result = self.rag.process_query(test["query"])
            except Exception as e:
                result = {"blocked": False, "response": f"ERROR: {e}"}

            self.rag.access_control.user_role = original_role

            actual = _actual_outcome(result)
            correct = actual == test["expected_outcome"]

            # For blocked cases also check layer accuracy if expected
            layer_correct = True
            if test["expected_outcome"] == "blocked" and correct:
                expected_layer = test.get("expected_layer")
                actual_layer = result.get("layer")
                layer_correct = (expected_layer is None) or (actual_layer == expected_layer)

            self.results.append({
                **test,
                "actual_outcome": actual,
                "actual_layer": result.get("layer"),
                "correct": correct,
                "layer_correct": layer_correct,
                "response_snippet": result.get("response", "")[:120],
            })

            if progress_cb:
                progress_cb(i + 1, len(queries))

        return self._compute_metrics()

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    def _compute_metrics(self) -> dict:
        total = len(self.results)
        overall_correct = sum(1 for r in self.results if r["correct"])

        attacks   = [r for r in self.results if r["expected_outcome"] == "blocked"]
        safe      = [r for r in self.results if r["expected_outcome"] != "blocked"]
        answerable= [r for r in self.results if r["expected_outcome"] == "answered"]

        tp = sum(1 for r in attacks if r["actual_outcome"] == "blocked")
        fn = sum(1 for r in attacks if r["actual_outcome"] != "blocked")
        tn = sum(1 for r in safe   if r["actual_outcome"] != "blocked")
        fp = sum(1 for r in safe   if r["actual_outcome"] == "blocked")

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall    = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1        = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

        retrieval_correct = sum(1 for r in answerable if r["actual_outcome"] == "answered")
        retrieval_acc = retrieval_correct / len(answerable) if answerable else 0.0

        # Per-layer breakdown (how many attacks each layer caught)
        layer_counts: dict[int, int] = {}
        for r in self.results:
            if r["actual_outcome"] == "blocked" and r.get("actual_layer"):
                lyr = r["actual_layer"]
                layer_counts[lyr] = layer_counts.get(lyr, 0) + 1

        # Per-category accuracy
        cat_stats: dict[str, dict] = {}
        for r in self.results:
            cat = r["category"]
            if cat not in cat_stats:
                cat_stats[cat] = {"label": CATEGORY_LABELS.get(cat, cat), "total": 0, "correct": 0}
            cat_stats[cat]["total"] += 1
            if r["correct"]:
                cat_stats[cat]["correct"] += 1
        for v in cat_stats.values():
            v["accuracy"] = v["correct"] / v["total"] if v["total"] else 0.0

        return {
            "total": total,
            "overall_accuracy": overall_correct / total,
            "tp": tp, "tn": tn, "fp": fp, "fn": fn,
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "retrieval_accuracy": retrieval_acc,
            "layer_counts": layer_counts,
            "category_stats": cat_stats,
            "results": self.results,
        }
