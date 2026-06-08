"""Generate one realistic, deliberately-messy GL + TB for a 'Deloitte' engagement.

Professional-services chart of accounts, ERP-style headers (to exercise schema
mapping), DD/MM/YYYY dates, and a controlled, documented set of data-quality
issues so the reconciliation, insights and report have meaningful findings.

Run:  python scripts/make_deloitte_sample.py
Out:  data/deloitte/gl.csv , data/deloitte/tb.csv  (+ prints what was injected)
"""

import csv
import os
import random

random.seed(7)

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.normpath(os.path.join(HERE, "..", "data", "deloitte"))

COA = {
    "1000": "Cash at Bank", "1100": "Accounts Receivable", "1200": "Unbilled WIP",
    "1500": "Office Equipment", "1510": "Leasehold Improvements",
    "2000": "Accounts Payable", "2100": "Accrued Expenses", "2200": "Deferred Revenue",
    "2300": "GST Payable", "3000": "Partners Capital",
    "4000": "Consulting Revenue", "4100": "Audit & Assurance Revenue", "4200": "Tax Advisory Revenue",
    "5000": "Salaries & Wages", "5200": "Office Rent", "5300": "Software & Technology",
    "5400": "Travel & Entertainment", "5500": "Professional Indemnity Insurance",
    "5600": "Training & Development", "5700": "Business Development",
}
CASH = "1000"

# (debit pool, credit pool, narratives)
TX = [
    (["1100"], ["4000"], ["Consulting fees - {c}", "Advisory engagement - {c}"]),
    (["1100"], ["4100"], ["Statutory audit fee - {c}", "Assurance services - {c}"]),
    (["1100"], ["4200"], ["Tax advisory - {c}", "Corporate tax compliance - {c}"]),
    ([CASH], ["1100"], ["Client receipt - {c}", "Invoice settlement - {c}"]),
    (["5000"], [CASH], ["Monthly payroll", "Salaries - consulting staff"]),
    (["5200"], [CASH], ["Office rent - Sydney", "Office rent - Melbourne"]),
    (["5300"], ["2000"], ["SaaS subscription - audit platform", "Data analytics licences"]),
    (["5400"], [CASH], ["Client travel - {c}", "Engagement travel & meals"]),
    (["5600"], [CASH], ["CPD training", "Staff certification program"]),
    (["5700"], [CASH], ["Proposal & pursuit costs - {c}", "Industry conference"]),
    (["2000"], [CASH], ["Supplier payment", "Vendor settlement"]),
    (["1500"], ["2000"], ["Laptop fleet refresh", "Monitors & peripherals"]),
    (["5500"], [CASH], ["PI insurance premium"]),
]
CLIENTS = ["Northwind", "Contoso", "Fabrikam", "Litware", "Proseware", "Tailspin",
           "Woodgrove", "Humongous Insurance", "Alpine", "Blue Yonder"]

DATES = [f"{d:02d}/{m:02d}/2026" for m in range(1, 13) for d in (5, 12, 19, 26)]


def amount_for(acct):
    if acct.startswith("4"):
        return round(random.uniform(80000, 520000), 2)       # revenue
    if acct == "5000":
        return round(random.uniform(180000, 320000), 2)      # payroll
    if acct == "5200":
        return round(random.uniform(45000, 65000), 2)        # rent
    if acct in ("1500", "1510"):
        return round(random.uniform(8000, 60000), 2)
    return round(random.uniform(3000, 40000), 2)


def main():
    os.makedirs(OUT, exist_ok=True)
    rows = []          # dicts: jid,date,acct,name,drcr,amount,narr
    jid = 0

    def journal(dr, cr, narr, amt, date):
        nonlocal jid
        jid += 1
        j = f"JE-{jid:04d}"
        rows.append({"jid": j, "date": date, "acct": dr, "name": COA[dr],
                     "drcr": "DR", "amount": amt, "narr": narr})
        rows.append({"jid": j, "date": date, "acct": cr, "name": COA[cr],
                     "drcr": "CR", "amount": amt, "narr": narr})
        return j

    for _ in range(46):
        dr_pool, cr_pool, narrs = random.choice(TX)
        dr, cr = random.choice(dr_pool), random.choice(cr_pool)
        narr = random.choice(narrs).format(c=random.choice(CLIENTS))
        journal(dr, cr, narr, amount_for(dr if dr[0] in "45" else cr), random.choice(DATES))

    injected = {"duplicates": [], "unbalanced": [], "breaks": [], "missing": {},
                "gl_only": [], "tb_only": []}

    # --- exact duplicate journal (double-posted software subscription) ---
    src = rows[0]["jid"]
    legs = [dict(r) for r in rows if r["jid"] == src]
    rows.extend(dict(r) for r in legs)
    injected["duplicates"].append((src, "exact"))

    # --- near duplicate (same amount/date/account, re-keyed) ---
    pick = next(r for r in rows if r["acct"] == "5300")
    twin = next(r for r in rows if r["jid"] == pick["jid"])
    new_legs = [dict(r) for r in rows if r["jid"] == twin["jid"]]
    for r in new_legs:
        r["jid"] = twin["jid"] + "-RB"
        r["narr"] = r["narr"] + " (rebooked)"
    rows.extend(new_legs)
    injected["duplicates"].append((twin["jid"] + "-RB", "near"))

    # --- one unbalanced journal: drop a credit leg (missing posting) ---
    ub = journal("5400", CASH, "Engagement travel - partial posting",
                 18450.00, random.choice(DATES))
    rows.pop()  # remove the CR leg -> journal no longer balances
    injected["unbalanced"].append(ub)

    # --- missing values: null some narratives + one account name ---
    miss_n = random.sample([r for r in rows if r["drcr"] == "DR"], 4)
    for r in miss_n:
        r["narr"] = ""
    injected["missing"]["description"] = len(miss_n)
    rows[3]["name"] = ""
    injected["missing"]["account_name"] = 1

    # --- derive the true TB (signed: +DR / -CR) ---
    tb = {}
    for r in rows:
        s = r["amount"] if r["drcr"] == "DR" else -r["amount"]
        tb[r["acct"]] = round(tb.get(r["acct"], 0.0) + s, 2)

    total_abs = sum(abs(v) for v in tb.values()) or 1.0
    materiality = max(0.01 * total_abs, 1000.0)

    # --- inject reconciliation breaks (2 material, 1 immaterial) ---
    def perturb(acct, delta, kind):
        tb[acct] = round(tb[acct] + delta, 2)
        injected["breaks"].append((acct, COA[acct], delta, kind))

    perturb("4000", round(materiality * 2.4, 2), "material")     # revenue overstated in TB
    perturb("1100", -round(materiality * 1.8, 2), "material")    # AR understated in TB
    perturb("5200", round(materiality * 0.25, 2), "immaterial")  # small rent variance

    # --- referential integrity: one account in GL but not TB ---
    drop = "5600"
    if drop in tb:
        del tb[drop]
        injected["gl_only"].append((drop, COA[drop]))
    # one TB-only account with no GL activity
    tb["2300"] = round(random.uniform(40000, 90000), 2)
    injected["tb_only"].append(("2300", COA["2300"]))

    # --- write GL (ERP-style headers, DD/MM/YYYY) ---
    gl_path = os.path.join(OUT, "gl.csv")
    with open(gl_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Journal_ID", "Posting_Date", "GL_Account", "Account_Name",
                    "DR_CR", "Amount", "Narrative"])
        for r in rows:
            w.writerow([r["jid"], r["date"], r["acct"], r["name"], r["drcr"],
                        f"{r['amount']:.2f}", r["narr"]])

    # --- write TB (different headers again) ---
    tb_path = os.path.join(OUT, "tb.csv")
    with open(tb_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Account", "Account Description", "Closing Balance"])
        for acct, bal in sorted(tb.items()):
            w.writerow([acct, COA.get(acct, "Unknown"), f"{bal:.2f}"])

    # --- supporting journal documentation PDF (covers ~70% of journals) ---
    jsum = {}
    for r in rows:
        s = jsum.setdefault(r["jid"], {"date": r["date"], "accts": set(),
                                       "amount": 0.0, "narr": ""})
        s["accts"].add(r["acct"])
        s["amount"] = max(s["amount"], r["amount"])
        if r["narr"]:
            s["narr"] = r["narr"]
    base_jids = sorted(j for j in jsum if not j.endswith("-RB"))
    shuffled = base_jids[:]
    random.shuffle(shuffled)
    skip = set(shuffled[: max(1, int(0.3 * len(base_jids)))])
    for j in base_jids:  # ensure at least one break-touching journal is undocumented
        if jsum[j]["accts"] & {"4000", "1100"}:
            skip.add(j)
            break
    documented = [j for j in base_jids if j not in skip]
    approvers = ["A. Mehta (Engagement Partner)", "S. Cole (Audit Manager)",
                 "R. Davies (Director)", "P. Nguyen (Senior Associate)"]

    from fpdf import FPDF
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_fill_color(15, 11, 11); pdf.rect(0, 0, 210, 26, "F")
    pdf.set_xy(12, 7); pdf.set_font("Helvetica", "B", 16); pdf.set_text_color(134, 188, 36)
    pdf.cell(0, 8, "Deloitte - Supporting Journal Documentation", ln=True)
    pdf.set_x(12); pdf.set_font("Helvetica", "", 9); pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 5, "Financial Year 2026  |  Journal vouchers & approvals", ln=True)
    pdf.set_text_color(0, 0, 0); pdf.ln(12)
    def vline(txt, h=5, bold=False):
        pdf.set_x(pdf.l_margin)
        pdf.set_font("Helvetica", "B" if bold else "", 10 if bold else 9)
        pdf.multi_cell(pdf.epw, h, txt.encode("latin-1", "replace").decode("latin-1"))

    for n, j in enumerate(documented):
        s = jsum[j]
        accts = ", ".join(f"{a} {COA.get(a,'')}" for a in sorted(s["accts"]))
        vline(f"Journal Voucher  {j}", h=6, bold=True)
        vline(f"Posting date: {s['date']}    Amount: {s['amount']:,.2f}")
        vline(f"Accounts: {accts}")
        vline(f"Narrative: {s['narr'] or '(per ledger)'}")
        vline(f"Approved by: {approvers[n % len(approvers)]}")
        pdf.set_draw_color(220, 220, 218); pdf.line(12, pdf.get_y() + 1, 198, pdf.get_y() + 1)
        pdf.ln(3)
    out = pdf.output(dest="S")
    pdf_path = os.path.join(OUT, "journals.pdf")
    with open(pdf_path, "wb") as f:
        f.write(out.encode("latin-1") if isinstance(out, str) else bytes(out))
    undoc_risky = [j for j in skip if jsum[j]["accts"] & {"4000", "1100", "5200"}]
    injected["undocumented_journals"] = sorted(skip)
    injected["undocumented_risky"] = sorted(undoc_risky)

    print(f"Wrote:\n  {gl_path}  ({len(rows)} rows)\n  {tb_path}  ({len(tb)} accounts)"
          f"\n  {pdf_path}  ({len(documented)}/{len(base_jids)} journals documented)")
    print(f"\nMateriality (approx): {materiality:,.2f}")
    print("Injected issues to look for in the app / report:")
    print(f"  • Duplicates: {injected['duplicates']}")
    print(f"  • Unbalanced journal: {injected['unbalanced']}")
    print(f"  • Reconciliation breaks: "
          + "; ".join(f"{c} {n} {d:+,.0f} ({k})" for c, n, d, k in injected["breaks"]))
    print(f"  • GL-only account: {injected['gl_only']}")
    print(f"  • TB-only account: {injected['tb_only']}")
    print(f"  • Missing values: {injected['missing']}")
    print(f"  • Undocumented journals ({len(injected['undocumented_journals'])}): "
          f"{injected['undocumented_journals'][:8]}{' ...' if len(injected['undocumented_journals'])>8 else ''}")
    print(f"  • Undocumented journals touching a break: {injected['undocumented_risky']}")


if __name__ == "__main__":
    main()
