# LedgerLens — Metrics & Concepts

A plain-English reference for every figure LedgerLens computes: **what it is, why
it's needed, how it's calculated, and what it tells an auditor.** Pair this with
[ARCHITECTURE.md](ARCHITECTURE.md) for the *how it's built*.

---

## 1. The accounting model (the foundation)

| Term | What it is | Why it matters |
|---|---|---|
| **General Ledger (GL)** | The complete list of individual transaction postings (journal lines). | The detailed evidence — the "what actually happened". |
| **Trial Balance (TB)** | The list of closing balances per account at period end. | The client's *stated* position — what we reconcile the detail to. |
| **Journal / transaction** | A set of postings sharing one `transaction_id` that should net to zero. | The unit of double-entry; the thing we test for balance & evidence. |
| **Debit / Credit (DR/CR)** | The two sides of every posting. | Direction of the entry. |
| **`signed_amount`** | Normalised value: **+amount for DR, −amount for CR** (debit-positive). | Lets us sum a column to get a balance and compare to the TB. |

**Core convention (used everywhere):**
`signed_amount = +amount` if DR, `−amount` if CR.
`GL-derived balance = Σ signed_amount` per account.
With this, **assets/expenses are positive; revenue/liabilities/equity are negative** — which matches how the TB is stated (e.g. Revenue shows as a negative number).

> **Interview answer — "why signed amounts?"** Because reconciliation is just "does the
> sum of the detail equal the stated balance?". Normalising DR/CR to a single signed
> number makes that a one-line `groupby().sum()` and makes the convention explicit and
> testable, instead of scattered DR/CR logic.

---

## 2. Reconciliation (the headline output)

**What:** comparing the balance *derived from the GL* against the *Trial Balance*, per
account.
**Why:** the GL (detail) and TB (summary) are often produced/exported separately; if
they disagree, the financials can't be relied upon until the difference is explained.

```
gl_balance = Σ signed_amount        (grouped by account)
variance   = gl_balance − tb_balance
```

**Status of each account:**

| Status | Condition | Meaning |
|---|---|---|
| `reconciled` | `|variance| ≤ 0.005` | GL agrees with TB (within rounding). ✅ |
| `immaterial_break` | `0.005 < |variance| ≤ materiality` | A difference, but below the audit threshold. |
| `material_break` | `|variance| > materiality` | A difference large enough to matter — must be investigated & adjusted. 🔴 |
| `gl_only` | account in GL, not in TB | The two extracts aren't from the same chart of accounts. |
| `tb_only` | account in TB, no GL activity | Same — an orphan balance with no supporting detail. |

**What it tells you:** `reconciled_pct` is the share of accounts that tie out. Breaks
are your work-list; material ones are the priority. `gl_only`/`tb_only` are
completeness/scoping issues.

---

## 3. Materiality (the threshold that defines "matters")

**What:** the size above which a difference is considered significant.
**Why:** auditors don't chase every cent — they focus effort on amounts that could
change a reader's decision. Materiality draws that line objectively.

```
materiality = max(1% of total |TB|, 1000)      # 1% of total absolute TB value, floored at 1,000
```

**What it tells you:** it converts a raw variance into a **risk classification**
(material vs immaterial). A variance of 23,000 is *immaterial* on a large engagement
(materiality ~95k for Deloitte) but could be material on a tiny one. The figure is
shown on every dashboard and in the report so the basis is transparent.

---

## 4. Data-quality scorecard — the 6 dimensions (the radar)

Each dimension scores **0–100**; they roll up (weighted) into an **overall** score.
These are the standard data-quality dimensions an assurance team cares about.

| Dimension | What it measures | Formula (1 − error rate) | Why it's needed / what it says |
|---|---|---|---|
| **Completeness** | Are required fields populated? | `1 − missing_cells / required_cells` | Blanks in account/amount/date undermine every downstream test. |
| **Validity** | Do values conform to type/domain? | `1 − invalid_rows / rows` | Bad DR/CR codes, non-positive amounts, out-of-period dates = unreliable data. |
| **Consistency** | Do journals obey double-entry? | `1 − unbalanced_journals / journals` | An unbalanced journal means a missing/wrong leg — the books don't internally agree. |
| **Uniqueness** | Are transactions distinct? | `1 − duplicate_rows / rows` | Duplicates overstate balances and distort analytics. |
| **Accuracy** | Does the GL agree to the TB? | `1 − break_accounts / accounts` | The reconciliation result, as a quality score. |
| **Timeliness** | Are dates valid & in-period? | `1 − (NaT + out_of_period) / rows` | Cut-off assurance — postings in the wrong period misstate the year. |

**Overall** = weighted mean, weights: `consistency ×1.5, accuracy ×2, others ×1`
(reconciliation accuracy and double-entry consistency are weighted highest because
they're the strongest signals of reliability).

> **Interview answer — "why a scorecard?"** It turns "is this data any good?" into six
> comparable, defensible numbers. It localises the problem (low *completeness* → fix data
> capture; low *accuracy* → reconciliation breaks), and it lets you compare engagements
> and track improvement over time.

---

## 5. Duplicates (uniqueness, in detail)

**What:** the same economic posting recorded more than once.
**Why:** duplicates inflate balances and distort analytical procedures; a double-posting
is also a control weakness worth a finding.

| Kind | Detection | Example |
|---|---|---|
| **Exact** | identical rows (`transaction_id, date, account, dr_cr, amount, description`) | a journal posted twice verbatim |
| **Near** | same `account + rounded amount + date` under **≥2 different `transaction_id`s** | the same payment re-keyed under a new reference |

**Crucial principle: flagged, never deleted.** Removing a transaction is the auditor's
call, not the pipeline's — silent deletion would itself be an audit finding. Each group
records the rows + a similarity score, so a human can review.

---

## 6. Validation findings (internal integrity)

- **Double-entry / unbalanced journals:** `Σ signed_amount` per journal should be 0. A non-zero residual means a leg is missing or wrong.
- **Referential integrity:** every GL account should exist in the TB and vice-versa. `gl_only`/`tb_only` accounts mean the two extracts don't share a chart of accounts (a scoping/completeness problem).
- **Missing values:** required fields that are blank — reported **with the specific row numbers** so they can be fixed at source.

---

## 7. Supporting-documentation coverage (the PDF input)

**What:** the share of journals evidenced by the supplied supporting PDFs.
**Why:** an auditor needs *evidence* (vouchers, approvals) behind postings — especially
those driving a reconciliation difference.

```
coverage = evidenced_journals / total_journals
```

**What it tells you:** low coverage = incomplete evidence file. The highest-risk signal
is an **undocumented journal that posts to a reconciliation-break account** — an
unexplained difference *and* no supporting evidence. LedgerLens lists these explicitly
(e.g. Deloitte `JE-0020` → posts to both Accounts Receivable and Consulting Revenue,
both material breaks, and has no voucher).

---

## 8. Headline KPIs (the cards)

| KPI | Meaning | Good / bad |
|---|---|---|
| **Data quality** | overall scorecard | higher is better |
| **Reconciled** | % of accounts tying GL↔TB | higher is better |
| **Material breaks** | accounts over materiality | 0 is the goal |
| **Immaterial breaks** | accounts under materiality | clear to avoid aggregation risk |
| **Duplicate groups** | flagged exact/near dupes | each needs review |
| **GL transactions / journals** | population size | context for the above |
| **Materiality** | the threshold used | transparency |
| **Doc coverage** | % journals evidenced | higher is better |

---

## 9. Findings register & severity

Findings are auto-generated from the metrics and **severity-rated** so an auditor sees
priorities, not just data:

| Severity | Triggers (examples) |
|---|---|
| **High** | material reconciliation breaks; undocumented journals touching a break |
| **Medium** | referential-integrity exceptions; duplicate groups; unbalanced journals; partial documentation |
| **Low** | immaterial breaks; missing values; date anomalies |

Each finding carries an **observation** (what), an **implication** (so what), and a
**recommendation** (do what). The **risk rating** (Low → Moderate → Elevated) is derived
from material breaks + orphans + overall DQ and headlines the report.

---

## 10. Per-break root-cause analysis

For each break the system states the observation, **likely causes**, and the
**recommended procedure** — deterministically, keyed on direction and account category:
- **GL > TB** (positive variance): duplicate/doubled posting, an unreversed entry, or a misclassification.
- **GL < TB** (negative variance): an unposted/late journal, a timing/cut-off difference, or a manual TB adjustment with no ledger entry.
- **gl_only / tb_only**: omitted from one extract, posted under a different code, or a brought-forward balance with no current movement.

(When AI is available it rewrites these as workpaper prose; the figures and causes are
the deterministic ones.)

---

## 11. The audit trail (auditability)

**What:** an append-only log of every transformation — stage, action, rows affected,
whether AI was used, and details (e.g. *"normalize dates: format=%d/%m/%Y unparsed=0"*).
**Why:** auditability is the whole point. Any figure in the report can be traced back to
the raw row and the rule that produced it. Exported as both a PDF appendix and machine-
readable JSON (`/api/report/<id>.json`).

---

## 12. The cleaning report (what was changed)

For transparency, cleaning records **per field**: how many values were transformed,
before→after examples, and the **affected row numbers**:
- *Dates:* e.g. row 0 `19/02/2026` → `2026-02-19` (97 reformatted).
- *Amounts:* `$4,500.00` → `4500.00`.
- *Sign:* 48 credit lines negated (DR +, CR −).
- *Missing:* description blank in rows 2, 56, 70, 96; account_name in row 3.

This is what lets the assistant answer *"what was replaced and which rows were affected?"*
precisely — and proves nothing was silently changed.

---

## 13. Quick glossary

- **Variance** — `GL-derived balance − TB balance` for an account. 0 = reconciled.
- **Break** — a non-zero variance; *material* if above materiality, else *immaterial*.
- **Double-entry** — every journal's debits = credits, so it nets to zero.
- **Orphan account** — appears in only one of GL/TB (`gl_only`/`tb_only`).
- **Coverage** — share of journals evidenced by supporting documents.
- **Source tag** — `gemini` / `openai` / `fallback`: which engine wrote a piece of prose (figures are always deterministic).

---

## 14. Sample interview Q&A

- **"How do you handle clients with different formats?"** → synonym-dictionary + fuzzy header mapping, multi-format date/amount parsing, CSV+XLSX, AI only for unresolved headers (§ARCHITECTURE 8).
- **"Where is AI appropriate vs not?"** → AI for language + extracting structure from PDFs; never for figures (reproducibility/auditability). Deterministic owns all numbers, with AI as a graceful enrichment (§ARCHITECTURE 9).
- **"How do you know the reconciliation is right?"** → seeded synthetic data + an answer-key verifier; **219 checks** assert injected breaks/dupes are detected with the right magnitude and class.
- **"How is it auditable?"** → append-only trail + cleaning report with row numbers + machine-readable JSON; nothing dropped.
- **"How does it scale to 1,500 clients?"** → stateless per-client pipeline → parallel workers; the happy path needs no AI/network; AI failures degrade prose only.
- **"What's materiality and why 1%?"** → `max(1% of |TB|, 1000)` — a transparent, engagement-relative threshold separating differences that matter from those that don't.
