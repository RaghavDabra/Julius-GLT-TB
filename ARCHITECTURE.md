# LedgerLens — Architecture

**An AI-enabled data pipeline for financial data preparation in audit & assurance engagements.**

LedgerLens ingests messy General Ledger (GL) and Trial Balance (TB) exports — plus
supporting journal PDFs — from many heterogeneous clients, then **cleans →
standardises → validates → deduplicates → reconciles → documents** the data with a
full, append-only audit trail. Every figure is computed deterministically; Google
Gemini / OpenAI GPT‑4o are layered on top purely for *language* (explanations,
narratives, grounded Q&A) and never produce numbers.

---

## 1. Design principles

| Principle | How it shows up |
|---|---|
| **Deterministic core, AI at the edges** | All balances, variances, scores, duplicate/break detection are pure Python over pandas. AI only writes prose and extracts structure from PDFs. The pipeline runs end-to-end with **no API key**. |
| **Auditability first** | Every transformation appends to an immutable `AuditTrail`. Each output traces back to the raw row + the rule that produced it. Exposed as JSON + PDF. |
| **Nothing silently dropped** | Duplicates, bad dates, missing values, unbalanced journals are **flagged, never deleted** — the auditor decides. |
| **Per-client, stateless pipeline** | `run_pipeline()` is a pure function of its inputs → embarrassingly parallel → scales horizontally to the case study's 1,500 clients. |
| **Graceful degradation** | AI provider chain (Gemini → GPT‑4o → deterministic templates). A dead key never breaks the demo; it just changes the prose source tag. |
| **Honest provenance** | Every AI output is tagged `source: gemini | openai | fallback`. A startup probe reports whether AI is actually reachable, so the UI never lies. |

---

## 2. High-level architecture

```
┌──────────────────────────── React UI (Vite, :5173) ─────────────────────────────┐
│  Sidebar (engagements, DQ%, delete)   Chat-first thread (grounded Q&A)           │
│  Dashboards: KPIs · Quality radar · Sankey · Reconciliation heatmap+table ·      │
│              Schema mapping · Duplicates · Documentation · Audit trail            │
└───────────────────────────────────────┬──────────────────────────────────────────┘
                                         │  REST / JSON (axios, CORS)
┌────────────────────────────── Flask API (:8080) ─────────────────────────────────┐
│ /api/clients  /api/result/<id>  /api/run  /api/ingest  /api/chat  /api/ai/explain │
│ /api/report/<id>.{pdf,json}  DELETE /api/clients/<id>  /api/health                │
│ ClientStore (in-memory per engagement)   env bootstrap (.env → operator fallback) │
└───────────────────────────────────────┬──────────────────────────────────────────┘
                                         │
┌──────────────── Deterministic pipeline  (api/pipeline/, pure functions) ──────────┐
│ 1 ingest    encoding/delimiter sniff · CSV/XLSX read · fuzzy header→canonical      │
│ 2 clean     dates (DD/MM vs MM/DD) · amounts ($ , () EU) · DR/CR→signed · text     │
│ 3 validate  double-entry · completeness · referential integrity · 6-dim scorecard │
│ 4 dedupe    exact + near-duplicate detection (flag, never drop)                    │
│ 5 reconcile GL-derived balance vs TB per account · materiality classification     │
│ 6 documents PDF text extract · journal evidence match · documentation coverage    │
│ 7 ai*       Gemini/GPT-4o: explain breaks · workpaper narrative · grounded chat    │
│ 8 report    fpdf2 workpaper PDF + machine-readable JSON audit trail                │
│             every stage → append-only AuditTrail            (*optional, fallback)  │
└───────────────────────────────────────────────────────────────────────────────────┘
        │                                   │                              │
   PipelineResult (one JSON,           insights.py                   Neo4j graph
   the single source of truth)     (deterministic prose)        (scripts/load_neo4j.py)
```

---

## 3. Technology stack

**Backend** (Python 3.10, `myenv/`)
- Flask + flask-cors — thin orchestration/serialization layer
- pandas — all data wrangling
- stdlib `difflib` — fuzzy header matching + near-duplicate scoring (no `rapidfuzz` dep)
- openpyxl — XLSX ingestion · pypdf — PDF text extraction · fpdf2 — PDF generation
- google-generativeai (`gemini-2.0-flash`) → openai 0.28 (`gpt-4o`) — AI providers
- python-dotenv — key loading · neo4j (driver) + networkx/matplotlib — graph export/viz

**Frontend** (Vite + React 18 + TypeScript)
- Tailwind 3 + MUI (light widgets) — styling · recharts — Sankey + radar charts
- lucide-react — icons · react-dropzone — uploads · react-markdown + remark-gfm — chat
- react-query (TanStack) — server state · axios — HTTP

**Brand:** Coral Black `#0F0B0B` (dark sidebar) + Radioactive Green `#86BC24` (accent), hybrid theme (dark sidebar + light canvas). Tokens in `src/index.css` (CSS vars) + `tailwind.config.js`.

---

## 4. The deterministic pipeline (stage by stage)

Each stage is a **pure function** `(input, config) -> (output, [AuditTrailEntry])`.
`runner.run_pipeline()` wires them into a single `PipelineResult`. Files live in
`api/pipeline/`.

### Stage 1 — Ingestion & schema mapping (`ingest.py`, `schema.py`)
The first place data variability bites: every client names columns differently.
- **Read:** encoding tried `utf-8 → utf-8-sig → latin-1`; delimiter via `csv.Sniffer`; XLSX via `pd.read_excel(engine="openpyxl")`. Read as strings so nothing is coerced prematurely.
- **Map headers → canonical schema** using a version-controlled **synonym dictionary** (`GL_SYNONYMS`, `TB_SYNONYMS` in `schema.py`):
  1. **exact synonym** hit → confidence 1.0, method `exact_synonym`
  2. else **fuzzy** `difflib.get_close_matches` (cutoff **0.82**) → method `fuzzy_difflib`, confidence = ratio
  3. only **unmatched** headers go to **Gemini/GPT-4o** → method `ai_suggested`, flagged `needs_review`
- **AI never overrides a deterministic match.** Canonical GL: `transaction_id, date, account_code, account_name, dr_cr, amount, signed_amount, description`. Canonical TB: `account_code, account_name, balance`.
- Every decision (raw header, canonical target, method, confidence, ai_used) is written to the audit trail → fully reproducible.

### Stage 2 — Cleaning & standardisation (`clean.py`)
- **Dates** (`normalize_dates`): tries explicit formats; disambiguates DD/MM vs MM/DD (any day-part > 12 ⇒ day-first); lenient fallback. Unparseable → `NaT`, flagged.
- **Amounts** (`parse_amount`): strips `$ € £ ,`; `(123.45)` → negative; EU `1.234,56` heuristic; unparseable → `NaN`, flagged.
- **Sign** (`normalize_sign`): derives `signed_amount` = **+amount for DR, −amount for CR** (debit-positive). Tolerant of `D/C`, `Debit/Credit`, `+/-`.
- **Text**: trim/collapse whitespace, title-case account names, keep `description` verbatim as evidence.
- **`build_cleaning_report(before, after)`** diffs mapped-raw vs cleaned and records, **per field**: count changed, before→after examples, and **affected row numbers** — this is what lets the assistant answer *"what was replaced and which rows were affected"*.

### Stage 3 — Validation & data-quality scorecard (`validate.py`)
Deterministic assurance checks → a 6-dimension scorecard (see [INFO.md](INFO.md)):
- **Double-entry**: per `transaction_id`, `sum(signed_amount) ≈ 0` (tol 0.005). Unbalanced journals listed with residual.
- **Missing fields**: required canonical fields non-null.
- **Referential integrity**: `GL.account_code ⊆ TB.account_code`; reports GL-only / TB-only accounts.
- **Validity**: `dr_cr ∈ {DR,CR}`, positive amounts, dates in period.
- **Scorecard** (0–1 per dimension): completeness, validity, consistency, timeliness computed here; **uniqueness** filled from Stage 4, **accuracy** from Stage 5; `finalize_scorecard` weights them (consistency ×1.5, accuracy ×2, rest ×1) into `overall`.

### Stage 4 — Deduplication (`dedupe.py`)
- **Exact**: `df.duplicated(subset=[transaction_id,date,account_code,dr_cr,amount,description], keep=False)`.
- **Near**: block on `(account_code, round(amount,2), date)`; flag blocks with **≥2 distinct `transaction_id`** (a same-amount/date/account posting under a different reference — the real double-posting signal). Description similarity (`difflib.SequenceMatcher`) is reported as the score, not the gate.
- **Flagged, never dropped.** Count feeds the `uniqueness` dimension.

### Stage 5 — Reconciliation (`reconcile.py`)
- `gl_balance = gl.groupby(account_code)[signed_amount].sum()`; outer-join TB.
- `variance = gl_balance − tb_balance`; **materiality** = `max(1% of total |TB|, 1000)`.
- Status: `reconciled` (|var| ≤ 0.005) · `immaterial_break` (≤ materiality) · `material_break` (> materiality) · `gl_only` · `tb_only`.
- Builds the **Sankey** payload (GL Postings → account category → status) and the **heatmap** payload (per-account intensity = |variance|/materiality). Accuracy = 1 − breaks/accounts.

### Stage 6 — Supporting documents (`documents.py`)
The case study's third input: supporting journal PDFs.
- **Extract** text with pypdf. **Match**: a journal is *evidenced* if its id appears in the document text (format-agnostic substring) — deterministic core.
- **AI enrichment** (optional): `ai.extract_vouchers()` pulls structured vouchers (journal_id, date, amount, approver) from the text.
- **Coverage** = evidenced journals / total; flags **unsupported journals**, and especially **unsupported journals that post to a reconciliation-break account** (highest audit risk).

### Stage 7 — AI reasoning (`ai.py`) — *optional enrichment*
- **Provider chain**: `_generate()` tries **Gemini** (`gemini-2.0-flash`), then **OpenAI GPT‑4o**, returns `(text, provider)`; returns `(None, None)` if both fail → caller uses the deterministic template.
- **Functions**: `suggest_mapping` (Stage 1 residue), `explain_break`, `draft_workpaper`, `extract_vouchers`, `answer_chat`. Each has a deterministic fallback from `insights.py`.
- **Grounded chat = RAG over the computed outputs only.** The system prompt allows answering *general* accounting concepts from expertise, but engagement-specific *figures* must come from the supplied audit-results JSON (scorecard, reconciliation, validation, duplicates, **cleaning report**, **support**, audit trail) — "never invent numbers."
- **`probe()`**: one cached live call at startup so `/api/clients`/`/api/health` report whether AI actually works (`ai_provider`), not merely whether a key is present.

### Stage 8 — Documentation (`report.py`, `insights.py`)
- **`insights.py`** is a deterministic *insight engine*: executive summary, risk rating/opinion, severity-rated findings register, per-break root-cause analysis, dimension commentary, cleaning summary, documentation summary, recommendations. It powers the PDF, the JSON, **and** the chat fallback — so the product reads like a real workpaper even with zero AI.
- **`report.py`** (fpdf2): an 8-section workpaper PDF (cover + risk badge → exec summary → scope/methodology → DQ assessment → reconciliation analysis w/ per-break narrative → supporting documentation → findings register → recommendations → AI commentary → audit-trail appendix) + `build_audit_json()` (machine-readable lineage).

### The audit trail (`audit_trail.py`)
`AuditTrail` is append-only (`add()` only). Each entry: `{seq, timestamp, stage, action, rows_affected, ai_used, inputs, outputs, details}`. It is the evidence that links every reported figure back to a transformation.

---

## 5. `PipelineResult` — the single source of truth

`run_pipeline()` returns one JSON dict that the entire frontend, the report, and the
Neo4j loader all read from:

```jsonc
{
  "client_id", "client_name",
  "mapping":   { gl, tb, gl_decisions[], tb_decisions[], gl_unmatched[], tb_unmatched[] },
  "summary":   { ... }, "scorecard": { completeness…timeliness, overall },
  "cleaning":  { dates, amounts, signed_amount, text_normalised, missing_values },  // row-level
  "validation":{ double_entry, missing_fields, referential_integrity, validity },
  "duplicates":[ { group_id, kind, score, rows[] } ],
  "reconciliation":[ { account_code, account_name, category, gl_balance, tb_balance,
                       variance, abs_variance, status } ],
  "support":   { documents, pages, method, vouchers[], coverage_pct,
                 supported_count, unsupported_count, unsupported_risky_journals[] },
  "sankey":    { nodes[], links[] }, "heatmap": { materiality, cells[] },
  "kpis":      { gl_rows, journals, reconciled_pct, material_breaks, dupes_flagged,
                 dq_overall, materiality, doc_coverage, … },
  "ai":        { available, explanations[], narrative },
  "trail":     [ AuditTrailEntry … ]
}
```

`_json_safe()` converts numpy/pandas/NaN/Timestamp into JSON-native values.

---

## 6. Backend API (`api/app.py`, `api/store.py`)

| Method | Route | Purpose |
|---|---|---|
| GET | `/api/health` | liveness + `ai_available` (live probe) + `ai_provider` + engagement count |
| GET | `/api/clients` | sidebar list (per-client DQ%, breaks, dupes) + AI status |
| GET | `/api/result/<id>` | the full `PipelineResult` for an engagement |
| POST | `/api/ingest` | upload GL → Stage-1 mapping preview (decisions + sample rows) |
| POST | `/api/run` | upload GL (+TB +docs) → full pipeline → store + return `PipelineResult` |
| POST | `/api/ai/explain` | on-demand Stage-7 narratives for an engagement |
| POST | `/api/chat` | grounded chat; builds context from the stored result |
| GET | `/api/report/<id>.pdf` | on-demand workpaper PDF |
| GET | `/api/report/<id>.json` | machine-readable audit JSON |
| DELETE | `/api/clients/<id>` | remove an engagement from the workspace (session-only) |

- **`ClientStore`** (`store.py`): thread-safe in-memory dict keyed by `client_id`. Holds the latest `PipelineResult` per engagement. *Production note:* swap for a DB / object store; the interface is tiny (`put/get/remove/list`).
- **Startup**: `load_synthetic()` auto-loads `LEDGERLENS_MAX_ENGAGEMENTS` (default 3) synthetic clients; `load_pinned()` always loads **Deloitte** from `data/deloitte/` (GL+TB+PDF). The Gemini/OpenAI keys are bootstrapped from the project `.env` (overrides `projects/operator/backend/.env` fallback).

---

## 7. Frontend (`src/audit/`)

Chat-first, claude.ai-style. State-driven view switcher (no router). `react-query`
caches `clients` + `result`; a fresh ingest is **seeded into the cache** so it renders
immediately.

```
AppShell.tsx      2-pane shell; clients/result queries; ingest+delete; ?client= deep-link
Sidebar.tsx       coral-black engagement list, search, "New ingest", per-row delete,
                  AI-provider status ("GPT-4o reasoning active")
WorkCanvas.tsx    header (client, DQ pill, Chat/Dashboard toggle, report buttons) + body
ChatThread.tsx    primary surface; bubbles; inline charts/tables; quick-action chips;
                  grounded chat with source badge (Gemini/GPT-4o/Deterministic)
UploadPanel.tsx   modal: GL + TB + supporting PDFs + "Generate AI narratives"
views/            KpiCards · QualityRadar (recharts) · FlowSankey (recharts) ·
                  ReconHeatmap (CSS grid) · ReconTable · DuplicatesPanel · MappingReview ·
                  DocumentationCard · AuditTrailView · ReportDownload · DashboardTabs
api.ts types.ts format.ts ui.tsx   client, types mirroring PipelineResult, helpers
```

Every view reads from the one `PipelineResult` prop — **one run, many views, zero
per-chart fetching.**

---

## 8. Handling data variability (the case study's #1 challenge)

| Variability | Mechanism |
|---|---|
| Different column names | synonym dictionary + difflib fuzzy + AI residue (Stage 1) |
| Different date formats | DD/MM vs MM/DD disambiguation + multi-format + lenient parse |
| Different amount styles | `$`/`,`/`()`/EU parsing; signed vs DR/CR normalisation |
| CSV **and** XLSX | encoding/delimiter sniff; openpyxl engine |
| Missing / blank values | flagged with row numbers (completeness), never dropped |
| GL≠TB chart of accounts | referential integrity → GL-only / TB-only |
| Duplicated postings | exact + near detection, flagged |
| Supporting docs (PDF) | text extract + evidence matching (Stage 6) |

The synthetic generator deliberately injects **all** of these across 25 clients (each
with its own quirk profile) to prove the handling — see §11.

---

## 9. AI vs deterministic logic (the key interview topic)

**Deterministic owns every number.** Balances, variances, materiality, scores,
duplicate/break detection, coverage — all pure pandas. Reproducible, explainable,
testable, free.

**AI is confined to language + unstructured extraction**, where it genuinely adds value:
1. **Header mapping residue** — only headers difflib can't place (flagged for review).
2. **Break explanations & workpaper narrative** — prose over the computed figures.
3. **Voucher extraction** — structure out of unstructured PDFs.
4. **Grounded chat** — answers concepts from expertise; answers figures strictly from the supplied JSON (RAG), instructed to never invent numbers.

**Why this split:** auditability and reliability. An auditor must be able to trust and
trace the figures; an LLM's figures are neither reproducible nor explainable. So the
LLM never touches them. The provider chain (Gemini → GPT‑4o → deterministic templates)
means the deterministic insight engine is always a complete fallback — the demo can't
be broken by a dead key or quota.

---

## 10. Neo4j graph projection (`scripts/load_neo4j.py`)

The engagement is also projected as a property graph for exploration:

```
(Client)-[:HAS_ACCOUNT]->(Account {code,name,category,gl_balance,tb_balance,variance,status})
(Client)-[:HAS_JOURNAL]->(Journal {id,date,amount,balanced,supported,duplicate,dup_kind})
(Journal)-[:POSTS {dr_cr,amount,signed}]->(Account)
(Journal)-[:EVIDENCED_BY]->(Document)
(Journal)-[:NEAR_DUPLICATE {score}]->(Journal)
(DuplicateGroup {gid,kind,score})-[:CONTAINS]->(Journal)
```

- All nodes carry an **`:Audit` label + `engagement` property** → the loader only ever touches its own subgraph.
- Runs in a **dedicated container** (`ledgerlens-neo4j`, http `:7475`, bolt `:7688`, user `neo4j`/`ledgerlens`) advertising its own bolt address so the Browser connects to *itself*, isolated from other databases.
- 7 engagements loaded (≈400 nodes). Data-quality views: `MATCH (g:DuplicateGroup)-[:CONTAINS]->(j:Journal)-[:POSTS]->(a:Account) RETURN g,j,a`; breaks: `…WHERE a.status CONTAINS 'break'`; unbalanced/undocumented via journal flags.

---

## 11. Synthetic data + verification (`scripts/`)

- **`generate_dataset.py`** (seeded): 25 client engagements, **~2,176 GL rows**, realistic chart of accounts, **balanced double-entry journals**, TB derived from the GL — then injects a *controlled, recorded* quirk profile per client (header synonyms, date format, amount style, exact+near duplicates, missing values, reconciliation breaks, GL-only/TB-only). Emits `manifest.json` + **`answer_key.json`** (ground truth) and a few XLSX files.
- **`verify_pipeline.py`**: runs the real pipeline over every client and asserts the output against `answer_key.json` — mapping is deterministic, injected dupes flagged, breaks detected with the right magnitude/materiality class, referential issues surfaced, clean clients score ~1.0, no rows dropped. **219 checks, all passing** — the proof the preprocessing/reconciliation actually works.
- **`make_deloitte_sample.py`**: a realistic professional-services engagement (Deloitte) — GL + TB with ERP-style headers + a **supporting `journals.pdf`** documenting ~70% of journals (the rest deliberately unevidenced, incl. break-touching ones).
- **`check_gemini.py`**: validates any AI key in 2 seconds with a clear verdict.

---

## 12. Production reliability & scaling to 1,500 clients

- **Stateless per-client pipeline** → run one job per client; scale workers horizontally (queue → workers → results store). Wall-clock is per-client, not portfolio-wide.
- **No external dependency on the happy path** — the deterministic pipeline needs no network/AI; AI calls are isolated, retried, and fall back. A provider outage degrades prose, never figures.
- **Reproducible & testable** — seeded synthetic data + an answer-key verifier give regression coverage; same input → identical output.
- **Auditable by construction** — the append-only trail + machine-readable JSON are the evidence a production assurance process requires.
- **Observability** — startup logs the AI status; `/api/health` exposes liveness + provider; every AI output carries a source tag.
- **What to harden for production:** replace `ClientStore` with a database/object store; move ingestion to a job queue (Celery/SQS); add authn/z + per-tenant isolation; pin dependency versions; add a portfolio rollup dashboard across all clients; structured logging + metrics.

---

## 13. Repository map

```
api/
  app.py            Flask orchestrator + endpoints + startup loaders + env bootstrap
  store.py          ClientStore (in-memory per engagement)
  pipeline/
    schema.py       canonical schema + GL/TB synonym dictionaries
    audit_trail.py  append-only lineage
    ingest.py clean.py validate.py dedupe.py reconcile.py documents.py   the stages
    ai.py           provider chain (Gemini→GPT-4o) + probe + grounded chat + fallbacks
    insights.py     deterministic insight engine (summary, findings, glossary, etc.)
    report.py       fpdf2 workpaper PDF + JSON audit report
    runner.py       wires stages → PipelineResult
scripts/
  generate_dataset.py   verify_pipeline.py   make_deloitte_sample.py
  check_gemini.py       load_neo4j.py
data/
  synthetic/        25 clients + manifest.json + answer_key.json
  deloitte/         gl.csv tb.csv journals.pdf
src/audit/          React UI (AppShell, Sidebar, WorkCanvas, ChatThread, views/, …)
requirements.txt  .env(.example)  README.md  ARCHITECTURE.md  INFO.md
```

---

## 14. Running it

```bash
# backend
cd "Julius.AI clone" && myenv/bin/pip install -r requirements.txt
myenv/bin/python scripts/generate_dataset.py          # synthetic data (seeded)
myenv/bin/python scripts/verify_pipeline.py           # 219 checks — prove correctness
cd api && ../myenv/bin/python app.py                  # http://localhost:8080
# frontend
npm install && npm run dev                            # http://localhost:5173
# graph (optional)
myenv/bin/python scripts/load_neo4j.py                # → http://localhost:7475
```
AI keys live in the project `.env` (`GEMINI_API_KEY`, `OPENAI_API_KEY`). With none set,
the app runs fully in deterministic mode.

## 15. Security notes
- No secrets in source — keys are read at runtime from `.env` (the previous hardcoded OpenAI key was removed; OpenAI auto-revokes exposed keys).
- CORS open for local dev only — lock down for production.
- In-memory store resets on restart — acceptable for a showcase, documented as a production change.
