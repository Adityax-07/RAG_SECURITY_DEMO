---
title: RAG Security Defense Demo
emoji: 🛡
colorFrom: green
colorTo: gray
sdk: streamlit
sdk_version: "1.40.1"
python_version: "3.10"
app_file: app.py
pinned: false
---

<div align="center">

# 🛡 RAG Security Defense Demo

**5-layer prompt-injection defense on a real CrowdStrike 10-K knowledge base**

[![Live Demo](https://img.shields.io/badge/🤗%20HF%20Space-Live%20Demo-FFD21E?style=for-the-badge)](https://huggingface.co/spaces/Adityax-07/RAG_SECURITY_DEMO)
[![GitHub](https://img.shields.io/badge/GitHub-Repo-181717?style=for-the-badge&logo=github)](https://github.com/Adityax-07/RAG_SECURITY_DEMO)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.40.1-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white)](https://streamlit.io)
[![Groq](https://img.shields.io/badge/Groq-llama--3.3--70b-F55036?style=for-the-badge)](https://groq.com)

</div>

---

## What It Does

This app demonstrates how to defend a RAG (Retrieval-Augmented Generation) system against **prompt injection, jailbreaks, and unauthorized data access**. Every query flows through a 5-layer security pipeline before a response is generated. The knowledge base is real — CrowdStrike's FY2024 10-K annual report — split into 3 role-gated access tiers.

**Try it live → [huggingface.co/spaces/Adityax-07/RAG_SECURITY_DEMO](https://huggingface.co/spaces/Adityax-07/RAG_SECURITY_DEMO)**

---

## Architecture

```
User Query
    │
    ▼
┌─────────────────────────────────────────────────┐
│  Layer 1 — Input Validation          (~1ms)     │
│  Regex blocks: "ignore instructions",           │
│  "system prompt", "jailbreak", "bypass", ...    │
└──────────────────────┬──────────────────────────┘
                       │ PASS
                       ▼
┌─────────────────────────────────────────────────┐
│  Layer 2 — LLM Classifier            (1–2s)     │
│  llama-3.3-70b judges jailbreak intent          │
│  JSON: { is_malicious, confidence, reason }     │
│  Blocks if confidence > 70%                     │
└──────────────────────┬──────────────────────────┘
                       │ PASS
                       ▼
┌─────────────────────────────────────────────────┐
│  Layer 3 — Hybrid Retrieval + RBAC  (100–500ms) │
│  Dense (ChromaDB) + Sparse (BM25)               │
│       → RRF Fusion → Cross-encoder Rerank       │
│  Role filter: public / employee / admin         │
│  Sensitive data masked before LLM sees it       │
└──────────────────────┬──────────────────────────┘
                       │ PASS
                       ▼
              LLM generates answer
                       │
                       ▼
┌─────────────────────────────────────────────────┐
│  Layer 4 — Response Filter           (1–2s)     │
│  LLM-as-judge scans output for leaked           │
│  secrets / PII. Redacts if unsafe.              │
└──────────────────────┬──────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────┐
│  Layer 5 — Audit Logger              (<1ms)     │
│  Logs every query: timestamp, layer, reason     │
└─────────────────────────────────────────────────┘
                       │
                       ▼
                  Response returned
```

---

## Knowledge Base

Real CrowdStrike FY2024 10-K data, split across 3 RBAC tiers:

| Tier | File | Sample Content |
|------|------|----------------|
| **Public** | `crowdstrike_10k_business.txt` | Founded 2011, CEO George Kurtz, ticker CRWD, Falcon XDR, 29K customers |
| **Employee** | `crowdstrike_10k_human_capital.txt` | 7,925 FTE, 9 ERGs, AUP, phishing tests, no US union |
| **Admin** | `crowdstrike_10k_financials.txt` | Revenue $3.056B, ARR $3.435B, net income $89.3M, cash $3.375B |

A public-role user asking about revenue gets zero results — not a refusal, just nothing to retrieve.

---

## Retrieval Pipeline

```
Query → Dense retrieval (ChromaDB cosine, all-MiniLM-L6-v2)
      + Sparse retrieval (BM25Okapi)
              ↓
        RRF Fusion (k=60)
              ↓
     RBAC role filter
              ↓
  Cross-encoder reranking (ms-marco-MiniLM-L-6-v2)
              ↓
      Top-5 chunks → LLM
```

---

## Evaluation Suite

100 labeled test queries across 8 categories, run through the full pipeline:

| Category | Count | Expected Outcome |
|----------|-------|-----------------|
| Safe — Public | 20 | `answered` |
| Safe — Employee | 10 | `answered` |
| Safe — Admin | 5 | `answered` |
| Layer 1 Attacks (regex) | 15 | `blocked` at L1 |
| Layer 2 Attacks (jailbreak) | 15 | `blocked` at L2 |
| Access Denied (wrong role) | 15 | `no_docs` |
| Out of Scope | 10 | `no_docs` |
| Edge Cases (same query, different roles) | 10 | varies |

Metrics: **overall accuracy, precision, recall, F1, retrieval accuracy, confusion matrix, per-layer and per-category breakdown.**
Results auto-saved to `results/eval_YYYYMMDD_HHMMSS_metrics.json` and `_detail.csv`.

---

## Tech Stack

| Component | Tool |
|-----------|------|
| UI | Streamlit 1.40.1 + custom CSS (dark OLED theme) |
| LLM | Groq — `llama-3.3-70b-versatile` (free tier) |
| Vector DB | ChromaDB (persistent, cosine similarity) |
| Bi-encoder | `sentence-transformers/all-MiniLM-L6-v2` |
| Cross-encoder | `cross-encoder/ms-marco-MiniLM-L-6-v2` |
| Sparse search | `rank-bm25` (BM25Okapi) |
| PDF parsing | `pypdf` |
| Fonts | JetBrains Mono + IBM Plex Sans |

---

## Local Setup

```bash
git clone https://github.com/Adityax-07/RAG_SECURITY_DEMO
cd RAG_SECURITY_DEMO
pip install -r requirements.txt
echo GROQ_API_KEY=gsk_... > .env   # free key at console.groq.com
streamlit run app.py
```

In the browser:
1. Sidebar → **Load CrowdStrike Demo Data**
2. Pick a role: `public` / `employee` / `admin`
3. **Demo tab** — test queries or use the attack presets
4. **Evaluation tab** — run all 100 queries and see accuracy metrics

---

## Project Structure

```
├── app.py                  # Streamlit UI + SecureRAG orchestrator
├── document_store.py       # Hybrid retrieval engine
├── evaluator.py            # 100-query batch runner + metrics
├── test_queries.py         # Labeled test suite
├── requirements.txt
└── layers/
    ├── input_validator.py  # Layer 1 — regex
    ├── query_classifier.py # Layer 2 — LLM judge
    ├── access_control.py   # Layer 3 — RBAC + masking
    ├── response_filter.py  # Layer 4 — output safety
    └── audit_logger.py     # Layer 5 — incident log
```

---

## Limitations

- **No real authentication** — role selector is UI-only; anyone can switch to admin
- **Ephemeral storage** — ChromaDB resets on Space restart; click "Load Demo Data" again
- **Layer 1 is regex-only** — bypassable with Unicode tricks or encoding
- **9 demo chunks** — a production system would have thousands from full documents
