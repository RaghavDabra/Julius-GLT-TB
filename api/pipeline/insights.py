"""Deterministic audit-insight generation.

Turns the computed PipelineResult into sophisticated, workpaper-grade prose —
executive summary, risk rating, severity-rated findings, per-break root-cause
analysis and recommendations — without any AI. The AI layer (ai.py) layers
model-authored narrative on top of this when a provider is available, but the
report is fully professional even in deterministic mode.
"""


def _m(v):
    return "n/a" if v is None else f"{v:,.2f}"


def _pct(v):
    return f"{round(100 * v)}%"


CATEGORY_DR_HINT = {
    "Assets": "asset", "Expenses": "expense",
    "Liabilities": "liability", "Equity": "equity", "Revenue": "revenue",
}


# --- overall opinion / risk -------------------------------------------------

def overall_opinion(result):
    k = result["kpis"]
    dq = result["scorecard"]["overall"]
    mb = k["material_breaks"]
    refs = result["validation"]["referential_integrity"]
    orphans = len(refs["gl_only_accounts"]) + len(refs["tb_only_accounts"])

    if mb == 0 and orphans == 0 and dq >= 0.97:
        rating = "Low"
        opinion = ("Clean — the ledger reconciles to the trial balance within materiality "
                   "and data quality is high. The population is suitable for substantive "
                   "testing without adjustment.")
    elif mb == 0 and dq >= 0.90:
        rating = "Low to Moderate"
        opinion = ("Acceptable with minor observations — no material reconciliation "
                   "differences were identified, though some data-quality exceptions "
                   "warrant clearance before reliance.")
    elif mb <= 1 and dq >= 0.88:
        rating = "Moderate"
        opinion = ("Reliance with adjustments — a material reconciliation difference was "
                   "identified and should be investigated and corrected prior to reliance "
                   "on the affected balance(s).")
    else:
        rating = "Elevated"
        opinion = (f"Exceptions requiring resolution — {mb} material reconciliation "
                   "difference(s) and broader data-quality weaknesses were identified. "
                   "Targeted substantive procedures and management adjustment are "
                   "recommended before the population is relied upon.")
    return rating, opinion


# --- executive summary ------------------------------------------------------

def executive_summary(result):
    k = result["kpis"]
    sc = result["scorecard"]
    rating, opinion = overall_opinion(result)
    refs = result["validation"]["referential_integrity"]
    weakest = min(
        ["completeness", "validity", "consistency", "uniqueness", "accuracy", "timeliness"],
        key=lambda d: sc[d])

    parts = [
        f"LedgerLens ingested {k['gl_rows']:,} general-ledger transactions spanning "
        f"{k['journals']:,} journals and reconciled them against {k['tb_accounts']:,} "
        f"trial-balance accounts for {result['client_name']}. The pipeline standardised "
        "heterogeneous source formats, validated double-entry integrity, screened for "
        "duplicate postings and reconciled GL-derived balances to the trial balance at a "
        f"materiality threshold of {_m(k['materiality'])}.",

        f"Overall data quality is assessed at {_pct(sc['overall'])}, with the weakest "
        f"dimension being {weakest} ({_pct(sc[weakest])}). "
        f"{_pct(k['reconciled_pct'])} of accounts reconciled "
        f"cleanly; {k['material_breaks']} account(s) exceeded materiality and "
        f"{k['immaterial_breaks']} fell below it. "
        f"{len(result['duplicates'])} potential duplicate posting group(s) were flagged "
        "for review and retained in the population rather than removed.",

        f"Audit conclusion — risk rated {rating}: {opinion}",
    ]
    if refs["gl_only_accounts"] or refs["tb_only_accounts"]:
        parts.append(
            f"Referential-integrity exceptions were noted: "
            f"{len(refs['gl_only_accounts'])} account(s) appear in the ledger but not the "
            f"trial balance, and {len(refs['tb_only_accounts'])} appear in the trial "
            "balance with no supporting ledger activity. These require reconciliation to a "
            "complete chart of accounts.")
    return parts


# --- per-break root-cause analysis -----------------------------------------

def break_commentary(row, materiality):
    code, name = row["account_code"], row["account_name"]
    var = row["variance"]
    status = row["status"]
    cat = row.get("category", "")
    gl, tb = row["gl_balance"], row["tb_balance"]

    if status == "gl_only":
        observation = (f"Account {code} ({name}) carries ledger activity of {_m(gl)} but "
                       "does not appear in the trial balance.")
        causes = ["the account was omitted from the trial-balance extract",
                  "a mapping/chart-of-accounts difference between the two sources",
                  "a newly opened account not yet reflected in the closing TB"]
        procedure = ("Obtain a complete trial balance and confirm whether the account "
                     "should be presented; agree the ledger movement to supporting entries.")
    elif status == "tb_only":
        observation = (f"Account {code} ({name}) is reported in the trial balance at "
                       f"{_m(tb)} with no corresponding ledger activity in the period.")
        causes = ["an opening balance brought forward with no current-period movement",
                  "ledger postings recorded under a different account code",
                  "a trial-balance line that is no longer supported by activity"]
        procedure = ("Trace the balance to prior-period workpapers and confirm whether "
                     "current-period movement is expected.")
    else:
        direction = ("the ledger overstates the balance relative to the trial balance"
                     if var > 0 else
                     "the trial balance exceeds the ledger-derived balance")
        observation = (f"Account {code} ({name}) shows a variance of {_m(var)} "
                       f"({_m(gl)} per the ledger vs {_m(tb)} per the trial balance); "
                       f"{direction}.")
        if var > 0:
            causes = ["a duplicate or doubled posting inflating ledger activity",
                      "a reversing entry posted to the ledger but not reflected in the TB",
                      f"a misclassified {CATEGORY_DR_HINT.get(cat, 'account')} entry"]
        else:
            causes = ["an unposted or late journal not yet captured in the ledger",
                      "a timing/cut-off difference around period end",
                      "a manual trial-balance adjustment lacking a ledger entry"]
        sev = "material" if status == "material_break" else "immaterial"
        procedure = (f"Variance is {sev} against the {_m(materiality)} threshold. "
                     "Vouch the largest constituent postings to source documentation and "
                     "obtain management's explanation and adjustment.")
    return {"observation": observation, "likely_causes": causes, "procedure": procedure}


# --- severity-rated findings register --------------------------------------

def findings(result):
    out = []
    k = result["kpis"]
    v = result["validation"]
    sc = result["scorecard"]

    n = 0
    def add(severity, area, title, observation, recommendation):
        nonlocal n
        n += 1
        out.append({"ref": f"F-{n:02d}", "severity": severity, "area": area,
                    "title": title, "observation": observation,
                    "recommendation": recommendation})

    if k["material_breaks"]:
        add("High", "Reconciliation",
            f"{k['material_breaks']} material reconciliation difference(s)",
            "GL-derived balances diverge from the trial balance beyond materiality on "
            f"{k['material_breaks']} account(s), the largest being "
            f"{_m(max((r['abs_variance'] for r in result['reconciliation']), default=0))}.",
            "Investigate and adjust each material difference; re-perform the reconciliation "
            "before relying on the affected balances.")
    if k["immaterial_breaks"]:
        add("Low", "Reconciliation",
            f"{k['immaterial_breaks']} immaterial reconciliation difference(s)",
            "Sub-materiality variances were identified that, while not individually "
            "significant, should be cleared to avoid aggregation risk.",
            "Clear or document each variance; monitor for a pattern indicating a systematic "
            "posting issue.")
    refs = v["referential_integrity"]
    if refs["gl_only_accounts"] or refs["tb_only_accounts"]:
        add("Medium", "Completeness",
            "Referential-integrity exceptions between GL and TB",
            f"{len(refs['gl_only_accounts'])} GL-only and {len(refs['tb_only_accounts'])} "
            "TB-only account(s) indicate the two sources are not drawn from an identical "
            "chart of accounts.",
            "Reconcile both extracts to a single, complete chart of accounts and re-run.")
    if len(result["duplicates"]):
        add("Medium", "Data integrity",
            f"{len(result['duplicates'])} potential duplicate posting group(s)",
            "Exact and near-duplicate transactions were detected, which can overstate "
            "balances and distort analytics if not addressed.",
            "Review each flagged group; reverse confirmed duplicates and assess the control "
            "that permitted the double posting.")
    sup = result.get("support")
    if sup:
        if sup.get("unsupported_risky_journals"):
            add("High", "Documentation",
                f"{len(sup['unsupported_risky_journals'])} journal(s) touching a reconciliation "
                "break lack supporting documentation",
                f"Only {round(100*sup['coverage_pct'])}% of journals are evidenced by the supplied "
                "PDFs; some undocumented journals post to accounts that did not reconcile, which is "
                "the highest-risk combination (e.g. " + ", ".join(sup["unsupported_risky_journals"][:5]) + ").",
                "Obtain supporting vouchers/approvals for these journals before relying on the "
                "affected balances; treat undocumented postings to break accounts as a priority.")
        elif sup.get("unsupported_count"):
            add("Medium", "Documentation",
                f"{sup['unsupported_count']} journal(s) lack supporting documentation",
                f"{round(100*sup['coverage_pct'])}% documentation coverage — "
                f"{sup['unsupported_count']} of {sup['total_journals']} journals are not evidenced "
                "by the supplied supporting PDFs.",
                "Request the missing journal vouchers/approvals to complete the evidence file.")
    if v["double_entry"]["unbalanced_count"]:
        add("Medium", "Double-entry",
            f"{v['double_entry']['unbalanced_count']} unbalanced journal(s)",
            "One or more journals do not net to zero, indicating an incomplete or "
            "incorrectly captured double-entry posting.",
            "Identify the missing or erroneous leg of each journal and correct at source.")
    miss = {c: nn for c, nn in v["missing_fields"].items() if isinstance(nn, int) and nn}
    if miss:
        add("Low", "Completeness", "Missing values in required fields",
            "Required fields contain blank values: "
            + ", ".join(f"{c} ({nn})" for c, nn in miss.items()) + ".",
            "Enforce mandatory-field validation at the point of data capture/extraction.")
    if sc["timeliness"] < 0.99:
        add("Low", "Timeliness", "Date anomalies detected",
            "Some postings carry unparseable or out-of-period dates, affecting period "
            "cut-off assurance.",
            "Standardise date capture and confirm period boundaries with management.")
    if not out:
        add("Low", "Overall", "No exceptions identified",
            "The population reconciled within materiality with high data quality and no "
            "duplicate or integrity exceptions.",
            "No remediation required; population suitable for substantive testing.")
    return out


# --- dimension commentary ---------------------------------------------------

_DIM_TEXT = {
    "completeness": ("required fields are populated", "blank required fields reduce reliance"),
    "validity": ("values conform to expected types and domains", "out-of-domain values were found"),
    "consistency": ("journals satisfy double-entry", "unbalanced journals indicate posting gaps"),
    "uniqueness": ("transactions are distinct", "duplicate postings were flagged"),
    "accuracy": ("GL agrees to the trial balance", "reconciliation differences reduce accuracy"),
    "timeliness": ("dates are valid and in-period", "date anomalies affect cut-off"),
}


def dimension_commentary(result):
    sc = result["scorecard"]
    notes = {}
    for dim, (good, bad) in _DIM_TEXT.items():
        s = sc[dim]
        verdict = "Strong" if s >= 0.95 else "Adequate" if s >= 0.85 else "Weak"
        notes[dim] = f"{verdict} ({_pct(s)}) — {good if s >= 0.95 else bad}."
    return notes


def recommendations(result):
    recs = []
    for f in findings(result):
        if f["severity"] in ("High", "Medium"):
            recs.append(f"[{f['severity']}] {f['recommendation']}")
    if not recs:
        recs.append("[Low] Maintain current controls; population is suitable for reliance.")
    recs.append("[Process] Retain the machine-readable audit trail (JSON) as evidence of the "
                "transformations applied from raw extract to reconciled output.")
    return recs


def glossary_answer(q, ctx):
    """Answer a conceptual / definitional question, grounded in this engagement's
    numbers. Returns a string, or None if the question isn't definitional."""
    k = ctx.get("kpis", {})
    refs = ctx.get("validation", {}).get("referential_integrity", {})
    de = ctx.get("validation", {}).get("double_entry", {})
    is_def = any(p in q for p in ("what is", "what are", "what does", "what's", "whats",
                                  "define", "definition", "explain", "meaning", "mean by",
                                  "how is", "how do you", "how are", "why ", "difference between"))
    if not is_def:
        return None

    def has(*words):
        return any(w in q for w in words)

    if has("material"):
        return (f"A reconciliation difference (a 'break') is **material** when its absolute "
                f"size exceeds the materiality threshold — here **{_m(k.get('materiality',0))}**, "
                "set at 1% of total absolute trial-balance value (floored at 1,000). Material "
                "breaks must be investigated and corrected before the affected balances are "
                "relied upon; differences below the threshold are immaterial. This engagement "
                f"has **{k.get('material_breaks',0)} material** and "
                f"**{k.get('immaterial_breaks',0)} immaterial** break(s).")
    if has("reconcil", "gl vs", "gl versus", "ledger vs", "gl and tb", "ledger and trial"):
        return ("**Reconciliation** compares the balance derived from the general ledger "
                "(the sum of signed postings per account) against the trial balance the client "
                "provided. Where the two agree within tolerance the account is *reconciled*; a "
                f"difference is a *break*. Here **{_pct(k.get('reconciled_pct',0))}** of accounts "
                "reconciled — ask for 'reconciliation breaks' to see the exceptions.")
    if has("trial balance", " tb", "trial-balance"):
        return ("A **trial balance** is the list of closing balances per account at period end. "
                "LedgerLens treats it as the client's stated position and reconciles the detailed "
                "general ledger to it account by account.")
    if has("general ledger", "gl ", "what is gl", "the ledger"):
        return ("The **general ledger** is the full list of individual transaction postings. We "
                "normalise each to a signed amount (debits +, credits −) and sum per account to "
                "derive a balance, which is then compared to the trial balance.")
    if has("double", "unbalanced", "balanced journal", "balance journal"):
        return ("Under **double-entry**, every journal's debits must equal its credits, so each "
                "journal nets to zero. An **unbalanced journal** is missing or has a mis-stated "
                f"leg. This engagement has **{de.get('unbalanced_count',0)}** unbalanced journal(s).")
    if has("duplicate", "dupe", "near", "exact"):
        return ("A **duplicate** is the same economic posting recorded more than once — *exact* "
                "(identical rows) or *near* (same account, amount and date, re-keyed under a "
                "different reference). Duplicates overstate balances, so LedgerLens **flags** them "
                f"for review and never auto-deletes. **{k.get('dupes_flagged',0)}** group(s) flagged.")
    if has("gl only", "gl-only", "tb only", "tb-only", "orphan", "referential", "integrity"):
        return ("A **GL-only** account appears in the ledger but not the trial balance; **TB-only** "
                "is the reverse. Both indicate the two extracts aren't drawn from the same chart of "
                f"accounts. Here GL-only: {refs.get('gl_only_accounts') or 'none'}; "
                f"TB-only: {refs.get('tb_only_accounts') or 'none'}.")
    if has("data quality", "quality score", "scorecard", "dimension", "dq"):
        return ("**Data quality** is scored across six dimensions — completeness, validity, "
                "consistency, uniqueness, accuracy and timeliness — each 0–100, then weighted into "
                f"an overall figure (**{_pct(ctx.get('scorecard',{}).get('overall',0))}** here). Ask "
                "for the 'data-quality radar' for the per-dimension breakdown.")
    if has("signed", "debit", "credit", "dr/cr", "dr cr"):
        return ("Each posting is normalised to a **signed amount**: debits positive, credits "
                "negative. Summing signed amounts per account gives the GL balance, matching the "
                "trial-balance convention (assets positive; revenue, liabilities and equity negative).")
    if has("audit trail", "lineage", "traceab"):
        return (f"Every transformation from raw file to reconciled output is recorded in an "
                f"**append-only audit trail** ({len(ctx.get('trail', []) or [])} or more steps) so "
                "any figure in the report can be traced back to the data and the rule that produced it.")
    if has("variance"):
        return ("A **variance** is the GL-derived balance minus the trial-balance balance for an "
                "account. Zero (within tolerance) means it reconciles; a non-zero variance is a "
                "break, classified material or immaterial against the materiality threshold.")
    if has("audit", "assurance"):
        return ("This tool prepares financial data for **audit & assurance**: it standardises messy "
                "GL/TB extracts, validates them, reconciles the ledger to the trial balance and "
                "documents every step — so an auditor can rely on the population and evidence the work.")
    return None


def account_answer(q, ctx):
    """If the question names an account (by code or name), explain that account."""
    recon = ctx.get("reconciliation", [])
    hit = None
    for r in recon:
        if r["account_code"] and r["account_code"] in q:
            hit = r
            break
    if hit is None:
        for r in recon:
            nm = (r["account_name"] or "").lower()
            if len(nm) > 3 and nm in q:
                hit = r
                break
    if hit is None:
        return None
    if hit["status"] == "reconciled":
        return (f"**{hit['account_code']} {hit['account_name']}** reconciles: the ledger-derived "
                f"balance ({_m(hit['gl_balance'])}) agrees with the trial balance "
                f"({_m(hit['tb_balance'])}) within tolerance.")
    c = break_commentary(hit, ctx.get("kpis", {}).get("materiality", 0))
    return (f"**{hit['account_code']} {hit['account_name']}** — {hit['status'].replace('_',' ')}.\n\n"
            f"{c['observation']}\n\n_Likely causes:_ " + "; ".join(c["likely_causes"])
            + f".\n\n_Recommended procedure:_ {c['procedure']}")


def cleaning_summary(ctx):
    """Narrate what ingestion & cleaning did — headers mapped, values transformed
    (with before→after examples and affected row numbers), and what was flagged."""
    cl = ctx.get("cleaning", {})
    m = ctx.get("mapping", {})
    parts = []

    if m:
        pairs = ", ".join(f"`{k}` → {v}" for k, v in list(m.items())[:8])
        parts.append(f"**Ingestion & schema mapping** — {len(m)} source header(s) mapped to "
                     f"the canonical schema: {pairs}.")
    d = cl.get("dates")
    if d and (d["reformatted"] or d["unparsed"]):
        ex = "; ".join(f"row {e['row']}: '{e['before']}' → {e['after']}" for e in d["examples"][:3])
        parts.append(f"**Dates** — standardised {d['reformatted']} value(s) to ISO format"
                     + (f" (e.g. {ex})" if ex else "")
                     + (f"; {d['unparsed']} could not be parsed and were flagged." if d["unparsed"] else "."))
    a = cl.get("amounts")
    if a:
        ex = "; ".join(f"row {e['row']}: '{e['before']}' → {e['after']}" for e in a["examples"][:3])
        parts.append(f"**Amounts** — parsed {a['parsed']} value(s) to numbers"
                     + (f" (e.g. {ex})" if ex else "")
                     + (f"; {a['unparsed']} unparseable." if a["unparsed"] else "."))
    s = cl.get("signed_amount")
    if s:
        parts.append(f"**Debit/Credit** — derived a signed amount per line ({s['rule']}); "
                     f"{s['credits_negated']} credit line(s) were negated.")
    t = cl.get("text_normalised")
    if t and t["changed"]:
        ex = "; ".join(f"'{e['before']}' → '{e['after']}'" for e in t["examples"][:2])
        parts.append(f"**Text** — trimmed/normalised {t['changed']} account name(s)"
                     + (f" (e.g. {ex})." if ex else "."))
    mv = cl.get("missing_values", {})
    if mv:
        bits = [f"{f} in {info['count']} row(s) {info['rows'][:8]}" for f, info in mv.items()]
        parts.append("**Missing values flagged** (not removed) — " + "; ".join(bits) + ".")

    if not parts:
        return None
    parts.append("_Nothing was dropped — originals are retained and every transformation is "
                 "recorded in the audit trail, so any figure is traceable._")
    return "\n\n".join(parts)


def documentation_summary(ctx):
    """Narrate supporting-document coverage: how many journals are evidenced by the
    PDFs, which are not, and which undocumented ones touch a reconciliation break."""
    sup = ctx.get("support")
    if not sup:
        return ("No supporting journal documentation (PDF) was provided for this engagement. "
                "Upload the journal vouchers with the GL/TB to assess documentation coverage.")
    parts = [
        f"**Supporting documentation** — {sup['documents']} PDF(s), {sup['pages']} page(s), "
        f"read via {sup['method']}.",
        f"**Coverage: {round(100*sup['coverage_pct'])}%** — {sup['supported_count']} of "
        f"{sup['total_journals']} journals are evidenced; {sup['unsupported_count']} are not.",
    ]
    if sup.get("unsupported_risky_journals"):
        parts.append("**Highest risk** — undocumented journals that post to a reconciliation-break "
                     "account: " + ", ".join(sup["unsupported_risky_journals"][:12]) + ".")
    if sup.get("unsupported_journals"):
        parts.append("Other undocumented journals: "
                     + ", ".join(sup["unsupported_journals"][:12])
                     + (" …" if len(sup["unsupported_journals"]) > 12 else "") + ".")
    if sup.get("vouchers"):
        parts.append(f"{len(sup['vouchers'])} structured voucher(s) were extracted from the PDFs "
                     "(journal id, amount, date, approver) and matched to the ledger.")
    return "\n\n".join(parts)


def methodology():
    return (
        "Source files were ingested with automatic encoding and delimiter detection and "
        "their headers mapped to a canonical schema using a controlled synonym dictionary "
        "with deterministic fuzzy matching; only headers that could not be resolved "
        "deterministically were referred to AI, and never to override a deterministic "
        "match. Dates, amounts and debit/credit indicators were standardised; double-entry "
        "integrity, completeness and referential consistency were validated; exact and "
        "near-duplicate postings were detected and flagged (never removed); and GL-derived "
        "balances were reconciled to the trial balance at a materiality of one percent of "
        "total absolute trial-balance value (floored at 1,000). Every transformation is "
        "recorded in an append-only audit trail."
    )
