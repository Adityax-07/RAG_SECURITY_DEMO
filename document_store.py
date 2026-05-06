import hashlib
import io

import chromadb
import numpy as np
import pypdf
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder


class DocumentStore:
    """
    Hybrid retrieval pipeline:
      1. Dense search  — ChromaDB cosine similarity (bi-encoder)
      2. Sparse search — BM25 keyword matching
      3. RRF fusion    — Reciprocal Rank Fusion merges both ranked lists
      4. Reranking     — cross-encoder rescores fused candidates for final precision
    """

    DENSE_CANDIDATES = 20   # how many to fetch from each retriever before fusion
    SPARSE_CANDIDATES = 20
    RERANK_TOP_N = 5        # final results returned after reranking
    RRF_K = 60              # RRF constant (60 is standard)

    def __init__(self, persist_dir: str = "./chroma_db"):
        ef = SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
        self._chroma = chromadb.PersistentClient(path=persist_dir)
        self.collection = self._chroma.get_or_create_collection(
            name="rag_docs",
            embedding_function=ef,
            metadata={"hnsw:space": "cosine"},
        )
        self._reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
        self._bm25: BM25Okapi | None = None
        self._bm25_corpus: list[tuple[str, str, dict]] = []  # (id, text, metadata)
        self._rebuild_bm25()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def seed_demo_data(self) -> int:
        demo_docs = [
            # ── PUBLIC TIER (3 chunks) ────────────────────────────────────────
            {
                "source": "crowdstrike_10k_business.txt",
                "allowed_roles": ["public", "employee", "admin"],
                "text": (
                    "CrowdStrike Holdings, Inc. was founded in 2011 by George Kurtz and is headquartered at "
                    "206 E. 9th Street, Suite 1400, Austin, Texas 78701 (phone: 888-512-8906). The company "
                    "trades on Nasdaq under the ticker CRWD and can be reached at crowdstrike.com or "
                    "ir.crowdstrike.com for investor relations. CrowdStrike's mission is to stop breaches "
                    "through an AI-native, cloud-native cybersecurity platform. George Kurtz serves as CEO, "
                    "Burt W. Podbere as CFO, Shawn Henry as CSO, and Michael Sentonas as President. "
                    "The company went public on June 12, 2019."
                ),
            },
            {
                "source": "crowdstrike_10k_business.txt",
                "allowed_roles": ["public", "employee", "admin"],
                "text": (
                    "CrowdStrike's flagship product is the Falcon XDR platform — a cloud-native solution "
                    "delivered via a single lightweight agent. The platform offers 27 cloud modules through "
                    "SaaS subscriptions priced on a per-endpoint, per-module basis. Key modules include "
                    "Falcon Prevent (Next-Gen AV), Falcon Insight XDR (EDR), Falcon Complete (managed "
                    "detection and response), Falcon OverWatch (threat hunting), Charlotte AI (generative "
                    "AI security), Falcon LogScale (Next-Gen SIEM), Falcon Cloud Workload Protection, and "
                    "Falcon Horizon (CSPM). The platform's Security Cloud correlates trillions of "
                    "cybersecurity events per week using three graph technologies: Threat Graph, Intel "
                    "Graph, and Asset Graph. CrowdStrike is FedRAMP authorized."
                ),
            },
            {
                "source": "crowdstrike_10k_business.txt",
                "allowed_roles": ["public", "employee", "admin"],
                "text": (
                    "As of January 31, 2024, CrowdStrike had 29,000 subscription customers — a 26% "
                    "increase year-over-year from 23,019 customers. The platform is used by 25 of the "
                    "50 US states for government cybersecurity. CrowdStrike operates within a category "
                    "it calls the Security Cloud, which aggregates and analyzes massive volumes of "
                    "threat intelligence globally. Financial statements are audited by "
                    "PricewaterhouseCoopers LLP. The company operates internationally, with revenue "
                    "spanning the US, EMEA, APAC, and other regions, and competes across endpoint "
                    "security, cloud security, identity protection, and threat intelligence markets."
                ),
            },

            # ── EMPLOYEE TIER (3 chunks) ──────────────────────────────────────
            {
                "source": "crowdstrike_10k_human_capital.txt",
                "allowed_roles": ["employee", "admin"],
                "text": (
                    "As of January 31, 2024, CrowdStrike employed 7,925 full-time employees, up from "
                    "4,965 in January 2022. The company has operated a distributed, hybrid/remote "
                    "workforce since inception. Total compensation includes base salary, annual "
                    "performance bonuses and commissions (paid to US payroll employees), equity awards, "
                    "an Employee Stock Purchase Plan (ESPP), 401(k) retirement savings, comprehensive "
                    "healthcare, dental, and vision insurance, health savings accounts, paid time off, "
                    "family leave, flexible schedules, adoption and infertility assistance, and employee "
                    "assistance programs. CrowdStrike has no US labor union."
                ),
            },
            {
                "source": "crowdstrike_10k_human_capital.txt",
                "allowed_roles": ["employee", "admin"],
                "text": (
                    "CrowdStrike enforces a comprehensive security training and compliance program. "
                    "Annual security training is mandatory for all employees and contractors. All "
                    "employees must certify compliance with the Acceptable Use Policy each year, and "
                    "annual reviews of security policies and procedures are conducted. Periodic "
                    "simulated phishing emails are sent to test employee compliance. A cross-functional "
                    "incident response team — covering IT, security, product security, engineering, "
                    "privacy, and legal — manages security incidents. Independent third-party auditors "
                    "perform compliance validation on a regular basis."
                ),
            },
            {
                "source": "crowdstrike_10k_human_capital.txt",
                "allowed_roles": ["employee", "admin"],
                "text": (
                    "CrowdStrike supports nine official Employee Resource Groups (ERGs): Women of "
                    "CrowdStrike, Veterans of CrowdStrike, Pride Team (LGBTQ+), Green Team "
                    "(Sustainability), Team BELIEVE (Black employees), AbilityStrikers (employees "
                    "with disabilities), Comunidad (Latine/Hispanic employees), Embracing Equity, "
                    "and Mazel (Jewish community). Headcount grew 34% in R&D, 20% in sales and "
                    "marketing, and 23% in G&A during FY2024. These groups support inclusion, "
                    "belonging, and community-building across CrowdStrike's global distributed "
                    "workforce."
                ),
            },

            # ── ADMIN TIER (3 chunks) ─────────────────────────────────────────
            {
                "source": "crowdstrike_10k_financials.txt",
                "allowed_roles": ["admin"],
                "text": (
                    "CrowdStrike FY2024 (fiscal year ended January 31, 2024) total revenue was "
                    "$3,055,555 thousand ($3.1 billion), up 36% year-over-year from $2.2 billion. "
                    "Subscription revenue accounted for $2,870,557 thousand (94% of total); "
                    "professional services contributed $184,998 thousand (6%). Gross profit was "
                    "$2,299,832 thousand with a gross margin of 75%. Net income was $89,327 thousand "
                    "— CrowdStrike's first profitable year — compared to a net loss of $183.2 million "
                    "in the prior year. Sales and marketing expenses were $1,140,566 thousand; R&D "
                    "expenses were $768,497 thousand; G&A expenses were $392,764 thousand."
                ),
            },
            {
                "source": "crowdstrike_10k_financials.txt",
                "allowed_roles": ["admin"],
                "text": (
                    "Annual Recurring Revenue (ARR) as of January 31, 2024 was $3,435,150 thousand "
                    "($3.4 billion), representing 34% growth year-over-year. The dollar-based net "
                    "retention rate was 119%, reflecting strong expansion within the existing customer "
                    "base. International revenue was approximately 32% of total revenue (~$967.5 "
                    "million in FY2024, up 43% YoY). Geographic breakdown: US 68% (~$2.1B), EMEA "
                    "15% (~$468M), APAC 10% (~$316M), other regions 7%. Total backlog stood at $1.5 "
                    "billion as of January 31, 2024. Stock-based compensation was $631,519 thousand. "
                    "CrowdStrike acquired Bionic (ASPM) for $239 million in September 2023."
                ),
            },
            {
                "source": "crowdstrike_10k_financials.txt",
                "allowed_roles": ["admin"],
                "text": (
                    "As of January 31, 2024, CrowdStrike held cash and cash equivalents of "
                    "$3,375,069 thousand ($3.4 billion). Total assets were $6,646,520 thousand. "
                    "Long-term debt consists of $742,494 thousand in Senior Notes bearing 3% "
                    "interest, due February 2029. The company also maintains a $750 million "
                    "revolving credit facility (Amended A&R Credit Agreement, matures January "
                    "2026) with $0 drawn. Operating cash flow for FY2024 was $1,166,207 thousand "
                    "($1.2 billion). The accumulated deficit as of January 31, 2024 was "
                    "approximately $1.1 billion, reflecting historic losses prior to FY2024."
                ),
            },
        ]

        ids, documents, metadatas = [], [], []
        for doc in demo_docs:
            chunk_id = hashlib.md5(f"{doc['source']}_{doc['text'][:50]}".encode()).hexdigest()
            ids.append(chunk_id)
            documents.append(doc["text"])
            metadatas.append({
                "source": doc["source"],
                "chunk": 0,
                "allowed_roles": ",".join(doc["allowed_roles"]),
            })

        self.collection.upsert(documents=documents, metadatas=metadatas, ids=ids)
        self._rebuild_bm25()
        return len(ids)

    def add_pdf(self, file_bytes: bytes, filename: str, allowed_roles: list[str]) -> int:
        text = self._extract_text(file_bytes)
        chunks = self._chunk_text(text)

        ids, documents, metadatas = [], [], []
        for i, chunk in enumerate(chunks):
            chunk_id = hashlib.md5(f"{filename}_{i}_{chunk[:50]}".encode()).hexdigest()
            ids.append(chunk_id)
            documents.append(chunk)
            metadatas.append({
                "source": filename,
                "chunk": i,
                "allowed_roles": ",".join(allowed_roles),
            })

        self.collection.upsert(documents=documents, metadatas=metadatas, ids=ids)
        self._rebuild_bm25()
        return len(chunks)

    def query(self, query_text: str, user_role: str) -> tuple[list[dict], dict]:
        """
        Returns (results, debug_info).
        Each result: {"content": str, "source": str, "score": float}
        debug_info: counts and scores for the UI layer breakdown.
        """
        if self.collection.count() == 0:
            return [], {"dense": 0, "sparse": 0, "fused": 0, "reranked": 0}

        # Stage 1: retrieve candidates from both retrievers
        dense_ranked = self._dense_retrieve(query_text)
        sparse_ranked = self._sparse_retrieve(query_text)

        # Stage 2: fuse with RRF
        fused = self._rrf_fuse(dense_ranked, sparse_ranked)

        # Stage 3: role-filter fused candidates
        allowed = [c for c in fused if user_role in c["meta"].get("allowed_roles", "public").split(",")]

        if not allowed:
            return [], {"dense": len(dense_ranked), "sparse": len(sparse_ranked), "fused": len(fused), "reranked": 0}

        # Stage 4: cross-encoder reranking
        reranked = self._rerank(query_text, allowed)

        debug = {
            "dense": len(dense_ranked),
            "sparse": len(sparse_ranked),
            "fused": len(fused),
            "reranked": len(reranked),
        }
        results = [{"content": c["content"], "source": c["meta"]["source"], "score": round(float(c["score"]), 4)} for c in reranked]
        return results, debug

    def list_documents(self) -> list[str]:
        if self.collection.count() == 0:
            return []
        return sorted({m["source"] for m in self.collection.get()["metadatas"]})

    def delete_document(self, filename: str):
        results = self.collection.get(where={"source": filename})
        if results["ids"]:
            self.collection.delete(ids=results["ids"])
        self._rebuild_bm25()

    # ------------------------------------------------------------------
    # Retrieval stages
    # ------------------------------------------------------------------

    def _dense_retrieve(self, query_text: str) -> list[dict]:
        n = min(self.DENSE_CANDIDATES, self.collection.count())
        results = self.collection.query(query_texts=[query_text], n_results=n)
        return [
            {"id": doc_id, "content": doc, "meta": meta}
            for doc_id, doc, meta in zip(
                results["ids"][0], results["documents"][0], results["metadatas"][0]
            )
        ]

    def _sparse_retrieve(self, query_text: str) -> list[dict]:
        if self._bm25 is None or not self._bm25_corpus:
            return []
        tokens = query_text.lower().split()
        scores = self._bm25.get_scores(tokens)
        top_indices = np.argsort(scores)[::-1][: self.SPARSE_CANDIDATES]
        return [
            {"id": self._bm25_corpus[i][0], "content": self._bm25_corpus[i][1], "meta": self._bm25_corpus[i][2]}
            for i in top_indices
            if scores[i] > 0
        ]

    def _rrf_fuse(self, dense: list[dict], sparse: list[dict]) -> list[dict]:
        all_docs: dict[str, dict] = {}
        rrf_scores: dict[str, float] = {}

        for rank, doc in enumerate(dense):
            all_docs[doc["id"]] = doc
            rrf_scores[doc["id"]] = rrf_scores.get(doc["id"], 0) + 1 / (self.RRF_K + rank + 1)

        for rank, doc in enumerate(sparse):
            all_docs[doc["id"]] = doc
            rrf_scores[doc["id"]] = rrf_scores.get(doc["id"], 0) + 1 / (self.RRF_K + rank + 1)

        sorted_ids = sorted(rrf_scores, key=rrf_scores.__getitem__, reverse=True)
        return [all_docs[doc_id] for doc_id in sorted_ids]

    def _rerank(self, query_text: str, candidates: list[dict]) -> list[dict]:
        if len(candidates) <= 1:
            return [{**c, "score": 1.0} for c in candidates]
        pairs = [(query_text, c["content"]) for c in candidates]
        scores = self._reranker.predict(pairs)
        ranked = sorted(zip(scores, candidates), key=lambda x: x[0], reverse=True)
        return [{**c, "score": float(s)} for s, c in ranked[: self.RERANK_TOP_N]]

    # ------------------------------------------------------------------
    # BM25 index
    # ------------------------------------------------------------------

    def _rebuild_bm25(self):
        if self.collection.count() == 0:
            self._bm25 = None
            self._bm25_corpus = []
            return
        data = self.collection.get()
        self._bm25_corpus = list(zip(data["ids"], data["documents"], data["metadatas"]))
        tokenized = [doc.lower().split() for doc in data["documents"]]
        self._bm25 = BM25Okapi(tokenized)

    # ------------------------------------------------------------------
    # Text utilities
    # ------------------------------------------------------------------

    def _extract_text(self, file_bytes: bytes) -> str:
        reader = pypdf.PdfReader(io.BytesIO(file_bytes))
        return "\n".join(page.extract_text() or "" for page in reader.pages)

    def _chunk_text(self, text: str, chunk_size: int = 600, overlap: int = 100) -> list[str]:
        text = " ".join(text.split())
        chunks = []
        start = 0
        while start < len(text):
            chunks.append(text[start : start + chunk_size])
            start += chunk_size - overlap
        return [c for c in chunks if len(c.strip()) > 50]
