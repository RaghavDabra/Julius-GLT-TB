# LedgerLens — AI-Enabled Audit Data Pipeline

An assurance-grade pipeline that ingests messy **General Ledger (GL)** and **Trial
Balance (TB)** exports from many different clients, then **cleans → standardises →
validates → deduplicates → reconciles → documents** the data, with a full
append-only audit trail. A premium, claude.ai-style chat-first UI sits on top, with
dashboards (Sankey, radar, heatmap, KPI cards). AI reasoning is powered by Google
Gemini but is strictly an *enrichment layer* — the pipeline is 100 % deterministic
and works with no API key.

Built for the audit & assurance case study (handling data variability, AI vs
deterministic logic, reconciliation, production reliability, auditability, scaling).

---

## Quick start

```bash
cd "Julius.AI clone"

# 1. backend deps (one-time)
myenv/bin/pip install -r requirements.txt

# 2. generate the synthetic multi-client dataset (~2000 GL rows, 25 clients)
myenv/bin/python scripts/generate_dataset.py

# 3. prove the pipeline is correct against the ground-truth answer key
myenv/bin/python scripts/verify_pipeline.py          # 219 checks, exits 0

# 4. run the API (auto-loads the 25 engagements on startup)
cd api && ../myenv/bin/python app.py                  # http://localhost:8080

# 5. run the UI (separate terminal)
npm install && npm run dev                            # http://localhost:5173
```

Gemini key: read automatically from `projects/operator/backend/.env`
(`GEMINI_API_KEY`), or set your own `export GEMINI_API_KEY=...`. With no key (or no
credit) the app runs in **deterministic mode** — every figure is identical, only the
prose narratives switch to templated text (`source: "fallback"`).

---

## Architecture

```
            ┌──────────────────────────── React UI (Vite, :5173) ───────────────────────────┐
            │  Sidebar (engagements)   Chat-first thread   Dashboards: KPIs · Radar ·        │
            │  coral-black + green      grounded Q&A        Sankey · Heatmap · Recon table    │
            └───────────────────────────────────┬───────────────────────────────────────────┘
                                                 │  REST (axios)
            ┌────────────────────────────── Flask API (:8080) ──────────────────────────────┐
            │  /api/clients /api/result /api/run /api/ingest /api/chat /api/report.{pdf,json}│
            └───────────────────────────────────┬───────────────────────────────────────────┘
                                                 │
   ┌──────────────────────────── Deterministic pipeline (api/pipeline) ────────────────────────────┐
   │ 1 ingest    encoding/delimiter sniff, CSV/XLSX read, fuzzy header → canonical (difflib)        │
   │ 2 clean     dates (DD/MM vs MM/DD), amounts ($ , () EU), DR/CR → signed_amount, text           │
   │ 3 validate  double-entry, completeness, referential integrity, 6-dim quality scorecard         │
   │ 4 dedupe    exact + near-duplicate detection (flag, never drop)                                │
   │ 5 reconcile GL-derived vs TB per account, materiality classification → Sankey + heatmap        │
   │ 6 ai*       Gemini: explain breaks, workpaper narrative, grounded chat  (*optional, fallback)  │
   │ 7 report    fpdf2 reconciliation PDF + machine-readable JSON audit trail                       │
   │             every stage appends to an append-only AuditTrail (full lineage)                    │
   └───────────────────────────────────────────────────────────────────────────────────────────────┘
```

Convention (from the real sample): `signed_amount = +amount` for DR, `−amount` for
CR; `TB balance = Σ signed_amount` per account (debit-positive).

---

## How it answers the case study

**1. Handling messy datasets across clients.** Each client arrives with different
column names, date formats and amount styles. A version-controlled **synonym
dictionary** (`api/pipeline/schema.py`) plus stdlib `difflib` fuzzy matching maps
any header onto a canonical schema; cleaning handles DD/MM-vs-MM/DD, `$`/`,`/`()`/EU
amounts, and DR/CR vs signed amounts. The 25-client generator deliberately varies
all of these (2–3 clients even arrive as `.xlsx`).

**2. Validating & reconciling.** Double-entry balance per journal, completeness,
referential integrity (GL↔TB), validity, then per-account GL-vs-TB reconciliation
classified against a **materiality** threshold (`max(1 % of |TB|, 1,000)`). Results
roll up into a six-dimension data-quality scorecard.

**3. Where AI is appropriate (and where it is not).** Deterministic logic owns every
number — balances, variances, duplicate detection, scores. **Gemini is confined to
language**: explaining a break's likely cause, drafting workpaper narrative, mapping
the rare header `difflib` can't, and answering chat questions **grounded only in the
computed outputs** (it is instructed to answer from the supplied JSON or say it
doesn't know — no invented figures). Every AI output is tagged `source: gemini |
fallback`.

**4. Reliable & auditable outputs.** The pipeline runs with no API key, so a live
demo never depends on a third party. An **append-only audit trail** records every
transformation (stage, action, rows affected, whether AI was used) and is exported
as JSON + a PDF workpaper. `scripts/verify_pipeline.py` asserts the pipeline against
a ground-truth answer key (**219 checks**), proving injected breaks, duplicates and
referential issues are all detected with the right magnitude.

**5. Scaling across engagements.** State is keyed per client (`api/store.py`); the
sidebar is a portfolio of engagements; the same `PipelineResult` shape powers every
client and every view. In production the in-memory store becomes a database/object
store and stages become queue workers — the pure-function stage design is already
horizontally parallel.

---

## Project layout

```
api/
  app.py                 Flask orchestrator + endpoints (auto-loads synthetic clients)
  store.py               per-engagement in-memory store
  pipeline/
    schema.py            canonical schema + synonym dictionaries
    audit_trail.py       append-only lineage
    ingest.py clean.py validate.py dedupe.py reconcile.py   the deterministic stages
    ai.py                Gemini wrapper + deterministic fallbacks
    report.py            fpdf2 PDF + JSON audit report
    runner.py            wires the stages → PipelineResult
scripts/
  generate_dataset.py    seeded 25-client generator + answer_key.json
  verify_pipeline.py     asserts pipeline output vs answer key (219 checks)
data/synthetic/          generated engagements + manifest + answer key
src/audit/               React UI (AppShell, Sidebar, ChatThread, WorkCanvas, views/)
```

## Testing the reconciliation yourself

`data/synthetic/answer_key.json` is the ground truth (which breaks, duplicates and
missing values were injected per client). Download any engagement's
**Report PDF** / **Audit JSON** from the UI header, or hit
`/api/report/<client_id>.json`, and cross-check the findings against the answer key —
`scripts/verify_pipeline.py` automates exactly this.
