"""Generate a realistic, messy, multi-client GL/TB dataset for LedgerLens.

Seeded from the 5 real sample rows in Downloads/, this builds ~25 client
engagements with proper double-entry accounting (~2000 GL rows total) and injects
*controlled, recorded* data-quality issues so the pipeline's output can be checked
against a ground-truth answer key.

Convention (matches the real sample): signed_amount = +amount for DR, -amount for
CR; TB balance = sum(signed_amount) per account.

Run:  python scripts/generate_dataset.py
Out:  data/synthetic/{manifest.json, answer_key.json, C01_*/gl.csv, tb.csv, ...}
"""

import json
import os
import random

import pandas as pd

# make backend synonyms the source of truth for header quirks
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
import sys
sys.path.insert(0, os.path.join(ROOT, "api"))
from pipeline.schema import GL_SYNONYMS, TB_SYNONYMS  # noqa: E402

SEED = 42
random.seed(SEED)

OUT_DIR = os.path.join(ROOT, "data", "synthetic")

# --- chart of accounts -----------------------------------------------------
COA = {
    "1000": "Cash", "1010": "Bank Current Account", "1100": "Accounts Receivable",
    "1200": "Inventory", "1500": "Fixed Assets", "1510": "Equipment",
    "2000": "Accounts Payable", "2100": "Accrued Liabilities",
    "2200": "Loans Payable", "2300": "Tax Payable",
    "3000": "Share Capital", "3100": "Retained Earnings",
    "4000": "Sales Revenue", "4100": "Service Revenue", "4200": "Other Income",
    "5000": "Cost of Goods Sold", "5100": "Salaries Expense", "5200": "Rent Expense",
    "5300": "Utilities Expense", "5400": "Office Expenses", "5500": "Marketing Expense",
    "5600": "Depreciation Expense",
}
CASH = ["1000", "1010"]
AR = "1100"
AP = "2000"
REVENUE = ["4000", "4100", "4200"]
EXPENSES = ["5000", "5100", "5200", "5300", "5400", "5500"]
ASSETS_BUY = ["1200", "1500", "1510"]

# (debit account-pool, credit account-pool, description)
TEMPLATES = [
    (CASH + [AR], REVENUE, "Sales invoice"),
    (EXPENSES, CASH + [AP], "Operating expense"),
    ([AP], CASH, "Supplier payment"),
    (CASH, [AR], "Customer receipt"),
    (ASSETS_BUY, CASH + [AP], "Asset purchase"),
    (CASH, ["2200"], "Loan drawdown"),
    (CASH, ["3000"], "Capital contribution"),
    (["5100"], CASH, "Payroll run"),
    (["5600"], ["1500"], "Depreciation charge"),
]

CLIENT_NAMES = [
    "Northwind Traders", "Contoso Manufacturing", "Fabrikam Logistics", "Adventure Works",
    "Tailspin Toys", "Wingtip Imports", "Proseware Health", "Litware Energy",
    "Fourth Coffee", "Graphic Design Institute", "Coho Vineyard", "Alpine Ski House",
    "Margie's Travel", "Blue Yonder Airlines", "Trey Research", "Lucerne Publishing",
    "Wide World Importers", "City Power & Light", "Humongous Insurance", "Woodgrove Bank",
    "Consolidated Messenger", "School of Fine Art", "Southridge Video", "Nod Publishers",
    "Bellows College",
]

DATE_FORMATS = ["%d/%m/%Y", "%m/%d/%Y", "%Y-%m-%d", "%d-%b-%Y"]
AMOUNT_STYLES = ["drcr_positive", "currency_drcr", "signed", "paren_neg"]


def _rand_date():
    return pd.Timestamp(year=2026, month=random.randint(1, 12), day=random.randint(1, 28))


def _make_journal(client_accts, tid):
    pool = random.choice(TEMPLATES)
    dr_opts = [a for a in pool[0] if a in client_accts] or [random.choice(client_accts)]
    cr_opts = [a for a in pool[1] if a in client_accts] or [random.choice(client_accts)]
    dr = random.choice(dr_opts)
    cr = random.choice(cr_opts)
    if dr == cr:
        cr = random.choice([a for a in client_accts if a != dr] or [dr])
    amt = round(random.uniform(150, 95000), 2)
    date = _rand_date()
    desc = pool[2]
    return [
        {"trans_id": tid, "date": date, "account_code": dr, "account_name": COA[dr],
         "dr_cr": "DR", "amount_abs": amt, "signed": amt, "description": desc},
        {"trans_id": tid, "date": date, "account_code": cr, "account_name": COA[cr],
         "dr_cr": "CR", "amount_abs": amt, "signed": -amt, "description": desc},
    ]


def _client_accounts():
    core = CASH + [AR, AP, "3000", "4000", "5100", "5200", "5400"]
    extra = random.sample([c for c in COA if c not in core],
                          k=random.randint(2, 6))
    return sorted(set(core + extra))


def _derive_tb(rows):
    bal = {}
    for r in rows:
        bal[r["account_code"]] = round(bal.get(r["account_code"], 0.0) + r["signed"], 2)
    return bal


def generate():
    os.makedirs(OUT_DIR, exist_ok=True)
    manifest = {"seed": SEED, "clients": []}
    answer_key = {"seed": SEED, "materiality_note": "backend uses max(1% of |TB|, 1000)",
                  "clients": {}}
    total_rows = 0

    for i, name in enumerate(CLIENT_NAMES):
        cid = f"C{i+1:02d}"
        slug = "".join(ch.lower() if ch.isalnum() else "" for ch in name.split()[0])
        folder = os.path.join(OUT_DIR, f"{cid}_{slug}")
        os.makedirs(folder, exist_ok=True)
        clean = (i % 4 == 0)  # ~6 pristine engagements for contrast

        accts = _client_accounts()
        rows = []
        for j in range(random.randint(30, 55)):
            rows.extend(_make_journal(accts, f"JE{i+1:02d}-{j+1:04d}"))

        ak = {"client_id": cid, "client_name": name, "clean": clean,
              "injected_dupes": [], "injected_missing": {}, "injected_breaks": [],
              "injected_gl_only": [], "injected_tb_only": []}

        # --- inject duplicates (whole balanced journals -> no spurious break) ---
        if not clean:
            for _ in range(random.randint(1, 2)):
                kind = random.choice(["exact", "near"])
                src_tid = random.choice([r["trans_id"] for r in rows])
                legs = [dict(r) for r in rows if r["trans_id"] == src_tid]
                if kind == "exact":
                    rows.extend([dict(r) for r in legs])
                    ak["injected_dupes"].append({"kind": "exact", "trans_id": src_tid})
                else:
                    new_tid = src_tid + "-COPY"
                    for r in legs:
                        c = dict(r); c["trans_id"] = new_tid
                        c["description"] = r["description"] + " (copy)"
                        rows.append(c)
                    ak["injected_dupes"].append({"kind": "near", "trans_id": new_tid})

        # --- inject missing values (don't touch amount -> recon stays clean) ---
        if not clean:
            miss = {"description": 0, "account_name": 0, "date": 0}
            for field in ("description", "account_name", "date"):
                k = random.randint(1, max(2, len(rows) // 25))
                for r in random.sample(rows, min(k, len(rows))):
                    r[field] = None
                    miss[field] += 1
            ak["injected_missing"] = miss

        # --- derive TB from the (dup-inclusive) GL ---
        tb_bal = _derive_tb(rows)

        # --- inject reconciliation breaks by perturbing TB balances ---
        if not clean:
            total_abs = sum(abs(v) for v in tb_bal.values()) or 1.0
            materiality = max(0.01 * total_abs, 1000.0)
            candidates = [a for a in tb_bal if a in accts]
            for acct in random.sample(candidates, min(random.randint(1, 3), len(candidates))):
                material = random.random() < 0.6
                delta = round(materiality * (2.0 if material else 0.2)
                              * random.choice([1, -1]), 2)
                if not material:
                    delta = round(delta if abs(delta) > 1 else 50.0 * (1 if delta >= 0 else -1), 2)
                tb_bal[acct] = round(tb_bal[acct] + delta, 2)
                ak["injected_breaks"].append(
                    {"account_code": acct, "delta": delta, "material": material})

            # referential integrity: drop one TB account (-> gl_only) ~40% of the time.
            # Exclude already-broken accounts so findings never overlap.
            broken = {b["account_code"] for b in ak["injected_breaks"]}
            drop_pool = [a for a in tb_bal if a in accts and a not in broken]
            if random.random() < 0.4 and len(tb_bal) > 4 and drop_pool:
                drop = random.choice(drop_pool)
                del tb_bal[drop]
                ak["injected_gl_only"].append(drop)
            # phantom TB-only account ~30% of the time
            if random.random() < 0.3:
                phantom = "2300"
                if phantom not in tb_bal:
                    tb_bal[phantom] = round(random.uniform(500, 9000), 2)
                    ak["injected_tb_only"].append(phantom)

        # --- choose this client's presentation quirks ---
        date_fmt = random.choice(DATE_FORMATS)
        amt_style = random.choice(AMOUNT_STYLES)
        gl_headers = _choose_headers(GL_SYNONYMS, amt_style)
        tb_headers = _choose_headers(TB_SYNONYMS, "drcr_positive")
        ak["date_format"], ak["amount_style"] = date_fmt, amt_style
        ak["header_map_gl"], ak["header_map_tb"] = gl_headers, tb_headers

        # --- write GL ---
        gl_df = _format_gl(rows, gl_headers, date_fmt, amt_style)
        as_xlsx = (i % 9 == 3)  # a few xlsx files to exercise the openpyxl path
        if as_xlsx:
            gl_rel = f"{cid}_{slug}/gl.xlsx"
            gl_df.to_excel(os.path.join(OUT_DIR, gl_rel), index=False)
        else:
            gl_rel = f"{cid}_{slug}/gl.csv"
            gl_df.to_csv(os.path.join(OUT_DIR, gl_rel), index=False)

        # --- write TB ---
        tb_df = _format_tb(tb_bal, tb_headers)
        tb_rel = f"{cid}_{slug}/tb.csv"
        tb_df.to_csv(os.path.join(OUT_DIR, tb_rel), index=False)

        ak["gl_rows"], ak["tb_accounts"] = len(rows), len(tb_bal)
        answer_key["clients"][cid] = ak
        manifest["clients"].append({
            "client_id": cid, "client_name": name,
            "gl_path": gl_rel, "tb_path": tb_rel,
            "clean": clean, "date_format": date_fmt, "amount_style": amt_style,
            "gl_rows": len(rows), "tb_accounts": len(tb_bal),
        })
        total_rows += len(rows)

    with open(os.path.join(OUT_DIR, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)
    with open(os.path.join(OUT_DIR, "answer_key.json"), "w") as f:
        json.dump(answer_key, f, indent=2)

    print(f"Generated {len(CLIENT_NAMES)} clients, {total_rows} GL rows -> {OUT_DIR}")
    print(f"  clean engagements: {sum(1 for c in manifest['clients'] if c['clean'])}")
    print(f"  manifest.json + answer_key.json written")


def _choose_headers(synonyms, amount_style):
    """Pick a random raw header name per canonical field (from the backend's dict)."""
    headers = {}
    for canon, variants in synonyms.items():
        headers[canon] = random.choice(variants)
    if amount_style in ("signed", "paren_neg"):
        headers.pop("dr_cr", None)  # signed styles have no debit/credit column
    return headers


def _fmt_amount(signed, abs_amt, style):
    if style == "drcr_positive":
        return f"{abs_amt:.2f}"
    if style == "currency_drcr":
        return f"${abs_amt:,.2f}"
    if style == "signed":
        return f"{signed:.2f}"
    if style == "paren_neg":
        return f"({abs(signed):.2f})" if signed < 0 else f"{signed:.2f}"
    return f"{abs_amt:.2f}"


def _format_gl(rows, headers, date_fmt, amt_style):
    out = []
    for r in rows:
        rec = {}
        rec[headers["transaction_id"]] = r["trans_id"]
        rec[headers["date"]] = (r["date"].strftime(date_fmt)
                                if r["date"] is not None else "")
        rec[headers["account_code"]] = r["account_code"]
        if "account_name" in headers:
            rec[headers["account_name"]] = (r["account_name"]
                                            if r["account_name"] is not None else "")
        if "dr_cr" in headers:
            rec[headers["dr_cr"]] = r["dr_cr"]
        rec[headers["amount"]] = _fmt_amount(r["signed"], r["amount_abs"], amt_style)
        rec[headers["description"]] = (r["description"]
                                       if r["description"] is not None else "")
        out.append(rec)
    return pd.DataFrame(out)


def _format_tb(tb_bal, headers):
    out = []
    for code, bal in sorted(tb_bal.items()):
        out.append({
            headers["account_code"]: code,
            headers["account_name"]: COA.get(code, "Unknown Account"),
            headers["balance"]: f"{bal:.2f}",
        })
    return pd.DataFrame(out)


if __name__ == "__main__":
    generate()
