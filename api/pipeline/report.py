"""Stage 7 - Documentation: a sophisticated reconciliation / validation workpaper.

Generates a multi-section, narrative-rich PDF (executive summary, risk opinion,
methodology, data-quality commentary, per-break root-cause analysis, a
severity-rated findings register and recommendations) plus a machine-readable JSON
audit trail. The prose is produced deterministically by ``insights.py`` so the
document is professional with or without AI; AI-authored narrative is appended when
a provider is available.
"""

from datetime import datetime

from . import insights

CORAL_BLACK = (15, 11, 11)
GREEN = (134, 188, 36)
GREEN_DK = (95, 130, 40)
AMBER = (201, 154, 30)
RED = (200, 71, 58)
GREY = (110, 102, 100)
LIGHT = (245, 245, 242)
INK = (28, 22, 22)

_STATUS_COLOR = {
    "reconciled": GREEN_DK, "immaterial_break": AMBER,
    "material_break": RED, "gl_only": (181, 116, 60), "tb_only": (181, 116, 60),
}
_SEVERITY_COLOR = {"High": RED, "Medium": AMBER, "Low": GREEN_DK}


def build_audit_json(result):
    rating, opinion = insights.overall_opinion(result)
    return {
        "engagement": result["client_name"],
        "client_id": result["client_id"],
        "generated": datetime.utcnow().isoformat() + "Z",
        "risk_rating": rating,
        "audit_opinion": opinion,
        "executive_summary": insights.executive_summary(result),
        "kpis": result["kpis"],
        "scorecard": result["scorecard"],
        "dimension_commentary": insights.dimension_commentary(result),
        "findings": insights.findings(result),
        "recommendations": insights.recommendations(result),
        "mapping": result["mapping"],
        "validation": result["validation"],
        "duplicates": result["duplicates"],
        "reconciliation": result["reconciliation"],
        "supporting_documentation": result.get("support"),
        "ai": result.get("ai", {}),
        "audit_trail": result["trail"],
    }


def build_pdf(result):
    from fpdf import FPDF

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.add_page()

    def _txt(s):
        return str(s).encode("latin-1", "replace").decode("latin-1")

    def section(text, n=None):
        pdf.ln(1.5)
        pdf.set_draw_color(*GREEN)
        pdf.set_line_width(0.6)
        y = pdf.get_y()
        pdf.line(pdf.l_margin, y, pdf.l_margin + 4, y)  # small green tick
        pdf.set_font("Helvetica", "B", 12.5)
        pdf.set_text_color(*CORAL_BLACK)
        label = f"{n}.  {text}" if n else text
        pdf.set_x(pdf.l_margin + 6)
        pdf.cell(0, 8, _txt(label), ln=True)
        pdf.set_text_color(0, 0, 0)

    def sub(text):
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(*INK)
        pdf.set_x(pdf.l_margin)
        pdf.cell(0, 6, _txt(text), ln=True)
        pdf.set_text_color(0, 0, 0)

    def para(text, h=5, size=9.5, style=""):
        pdf.set_font("Helvetica", style, size)
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(pdf.epw, h, _txt(text))

    def kv(label, value, vcolor=None):
        pdf.set_font("Helvetica", "B", 9.5)
        pdf.set_x(pdf.l_margin)
        pdf.cell(58, 5.6, _txt(label), 0)
        pdf.set_font("Helvetica", "", 9.5)
        if vcolor:
            pdf.set_text_color(*vcolor)
        pdf.cell(0, 5.6, _txt(value), ln=True)
        pdf.set_text_color(0, 0, 0)

    def bullet(text, color=None):
        pdf.set_x(pdf.l_margin + 2)
        pdf.set_font("Helvetica", "B", 9.5)
        if color:
            pdf.set_text_color(*color)
        pdf.cell(4, 5, _txt("-"))
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Helvetica", "", 9.5)
        x = pdf.get_x()
        pdf.multi_cell(pdf.epw - (x - pdf.l_margin), 5, _txt(text))

    k = result["kpis"]
    sc = result["scorecard"]
    rating, opinion = insights.overall_opinion(result)

    # ---------- cover band ----------
    pdf.set_fill_color(*CORAL_BLACK)
    pdf.rect(0, 0, 210, 34, "F")
    pdf.set_xy(12, 8)
    pdf.set_font("Helvetica", "B", 20)
    pdf.set_text_color(*GREEN)
    pdf.cell(0, 9, _txt("LedgerLens"), ln=True)
    pdf.set_x(12)
    pdf.set_font("Helvetica", "", 10.5)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 6, _txt("Reconciliation & Data-Quality Workpaper"), ln=True)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(10)

    # ---------- engagement block + risk badge ----------
    pdf.set_font("Helvetica", "B", 15)
    pdf.set_x(pdf.l_margin)
    pdf.cell(0, 8, _txt(result["client_name"]), ln=True)
    kv("Client ID:", result["client_id"])
    kv("Report date (UTC):", datetime.utcnow().strftime("%Y-%m-%d %H:%M"))
    kv("Materiality threshold:", f"{k.get('materiality', 0):,.2f}")
    kv("Overall data quality:", f"{round(100 * sc['overall'])}%")
    # risk badge
    rc = RED if "Elevated" in rating else AMBER if "Moderate" in rating else GREEN_DK
    pdf.ln(1)
    pdf.set_x(pdf.l_margin)
    pdf.set_fill_color(*rc)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 9.5)
    pdf.cell(0, 7, _txt(f"  AUDIT RISK RATING:  {rating.upper()}"), ln=True, fill=True)
    pdf.set_text_color(0, 0, 0)

    # ---------- 1. executive summary ----------
    section("Executive summary", 1)
    for p in insights.executive_summary(result):
        para(p)
        pdf.ln(0.6)

    # ---------- 2. scope & methodology ----------
    section("Scope & methodology", 2)
    para(insights.methodology())

    # ---------- 3. data-quality scorecard ----------
    section("Data-quality assessment", 3)
    notes = insights.dimension_commentary(result)
    for dim in ["completeness", "validity", "consistency", "uniqueness", "accuracy", "timeliness"]:
        score = sc.get(dim, 0)
        col = GREEN_DK if score >= 0.9 else AMBER if score >= 0.7 else RED
        pdf.set_x(pdf.l_margin)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(34, 5.4, _txt(dim.title()), 0)
        x, y = pdf.get_x(), pdf.get_y()
        pdf.set_fill_color(*LIGHT); pdf.rect(x, y + 1, 46, 3.4, "F")
        pdf.set_fill_color(*col); pdf.rect(x, y + 1, 46 * score, 3.4, "F")
        pdf.set_xy(x + 49, y)
        pdf.set_font("Helvetica", "", 8.5)
        pdf.multi_cell(pdf.epw - 49 - 34, 5.4, _txt(f"{round(100*score)}%  -  {notes[dim]}"))
    pdf.ln(1)

    # ---------- 4. reconciliation analysis ----------
    section("Reconciliation analysis", 4)
    breaks = [r for r in result["reconciliation"] if r["status"] != "reconciled"]
    para(f"{k['reconciled_pct'] and round(100*k['reconciled_pct'])}% of {len(result['reconciliation'])} "
         f"accounts reconciled within the {k.get('materiality',0):,.2f} materiality threshold. "
         f"{len(breaks)} account(s) require attention, detailed below.")
    pdf.ln(0.5)
    _recon_table(pdf, breaks if breaks else result["reconciliation"][:12], _txt)
    pdf.ln(1.5)
    # per-break narrative
    mat = k.get("materiality", 0)
    for r in sorted(breaks, key=lambda x: -x["abs_variance"])[:6]:
        c = insights.break_commentary(r, mat)
        sub(f"{r['account_code']}  {r['account_name']}  -  {r['status'].replace('_',' ')}")
        para(c["observation"])
        pdf.set_font("Helvetica", "B", 9); pdf.set_x(pdf.l_margin)
        pdf.cell(0, 5, _txt("Likely causes:"), ln=True)
        for cause in c["likely_causes"]:
            bullet(cause)
        para("Recommended procedure: " + c["procedure"], style="I")
        pdf.ln(1)

    # ---------- 5. duplicate & integrity analysis ----------
    section("Duplicate & integrity analysis", 5)
    dups = result["duplicates"]
    if dups:
        n_exact = sum(1 for d in dups if d["kind"] == "exact")
        n_near = len(dups) - n_exact
        para(f"{len(dups)} potential duplicate posting group(s) were identified "
             f"({n_exact} exact, {n_near} near-duplicate) and retained in the population for "
             "auditor judgement. Duplicate postings can overstate balances and distort "
             "analytical procedures if not investigated.")
        for d in dups[:8]:
            r0 = d["rows"][0]
            bullet(f"Group {d['group_id']} ({d['kind']}, {round(d['score']*100)}% similar): "
                   f"account {r0.get('account_code')}, amount {r0.get('amount')}, "
                   f"\"{(r0.get('description') or r0.get('transaction_id') or '')}\" - {len(d['rows'])} rows.")
    else:
        para("No exact or near-duplicate postings were detected; uniqueness assurance is high.")
    v = result["validation"]
    pdf.ln(0.5); sub("Referential integrity & double-entry")
    kv("Unbalanced journals:", str(v["double_entry"]["unbalanced_count"]),
       RED if v["double_entry"]["unbalanced_count"] else GREEN_DK)
    kv("GL-only accounts:", ", ".join(v["referential_integrity"]["gl_only_accounts"]) or "none")
    kv("TB-only accounts:", ", ".join(v["referential_integrity"]["tb_only_accounts"]) or "none")

    # ---------- 5b. supporting documentation ----------
    sup = result.get("support")
    if sup:
        section("Supporting documentation")
        para(f"{sup['documents']} supporting PDF(s) ({sup['pages']} page(s)) were read via "
             f"{sup['method']}. Documentation coverage is "
             f"{round(100*sup['coverage_pct'])}% — {sup['supported_count']} of "
             f"{sup['total_journals']} journals are evidenced; {sup['unsupported_count']} are not.")
        if sup.get("unsupported_risky_journals"):
            sub("Undocumented journals touching a reconciliation break (priority)")
            para(", ".join(sup["unsupported_risky_journals"][:20]))
        if sup.get("unsupported_journals"):
            sub("Other undocumented journals")
            para(", ".join(sup["unsupported_journals"][:30]))

    # ---------- 6. findings register ----------
    section("Key findings register", 6)
    for f in insights.findings(result):
        col = _SEVERITY_COLOR.get(f["severity"], GREY)
        pdf.set_x(pdf.l_margin)
        pdf.set_fill_color(*col); pdf.set_text_color(255, 255, 255)
        pdf.set_font("Helvetica", "B", 8)
        pdf.cell(20, 5, _txt(f["severity"].upper()), 0, 0, "C", True)
        pdf.set_text_color(*INK); pdf.set_font("Helvetica", "B", 9.5)
        pdf.cell(3); pdf.cell(0, 5, _txt(f"{f['ref']}  {f['title']}  ({f['area']})"), ln=True)
        pdf.set_text_color(0, 0, 0)
        para(f["observation"])
        para("Recommendation: " + f["recommendation"], style="I")
        pdf.ln(0.8)

    # ---------- 7. recommendations ----------
    section("Recommendations", 7)
    for rec in insights.recommendations(result):
        bullet(rec)

    # ---------- 8. AI narrative (if available) ----------
    ai_block = result.get("ai", {})
    if ai_block.get("narrative") or ai_block.get("explanations"):
        section("Independent AI commentary", 8)
        nar = ai_block.get("narrative", {})
        if nar.get("text"):
            para(nar["text"])
            para(f"[source: {nar.get('source','fallback')}]", size=8, style="I")
        for e in ai_block.get("explanations", [])[:5]:
            sub(f"Account {e['account_code']}  [{e.get('source','fallback')}]")
            para(e["text"])

    # ---------- appendix: audit trail ----------
    pdf.add_page()
    section("Appendix A - Audit trail (lineage)")
    para("Every transformation from raw extract to reconciled output, in order. "
         "Entries marked [AI] used a language model; all figures are deterministic.", size=8.5)
    pdf.ln(1)
    pdf.set_font("Helvetica", "", 8)
    for t in result["trail"]:
        flag = "AI" if t["ai_used"] else "  "
        para(f"#{t['seq']:>2} [{flag}] {t['stage']:>9} | {t['action']} "
             f"(rows={t['rows_affected']})  {t['details']}", h=4.4, size=8)

    out = pdf.output(dest="S")
    if isinstance(out, str):
        out = out.encode("latin-1")
    return bytes(out)


def _recon_table(pdf, rows, _txt):
    headers = [("Acct", 16), ("Account name", 48), ("GL balance", 28),
               ("TB balance", 28), ("Variance", 28), ("Status", 30)]
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_fill_color(*CORAL_BLACK)
    pdf.set_text_color(255, 255, 255)
    pdf.set_x(pdf.l_margin)
    for label, w in headers:
        pdf.cell(w, 6, _txt(label), 1, 0, "L", True)
    pdf.ln()
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "", 8)
    for r in rows[:24]:
        col = _STATUS_COLOR.get(r["status"], GREY)
        pdf.set_x(pdf.l_margin)
        pdf.cell(16, 5.4, _txt(r["account_code"]), 1)
        pdf.cell(48, 5.4, _txt((r["account_name"] or "")[:30]), 1)
        pdf.cell(28, 5.4, _txt(_n(r["gl_balance"])), 1, 0, "R")
        pdf.cell(28, 5.4, _txt(_n(r["tb_balance"])), 1, 0, "R")
        pdf.cell(28, 5.4, _txt(_n(r["variance"])), 1, 0, "R")
        pdf.set_text_color(*col)
        pdf.cell(30, 5.4, _txt(r["status"].replace("_", " ")), 1, 0, "L")
        pdf.set_text_color(0, 0, 0)
        pdf.ln()


def _n(v):
    return "-" if v is None else f"{v:,.2f}"
