"""Stage 2 - Cleaning & standardization.

Turns a canonically-mapped (but still messy) GL/TB frame into clean, typed data:
dates -> ISO, amounts -> float, DR/CR -> signed_amount, text trimmed. Nothing is
ever silently dropped: unparseable values are coerced to NaN/NaT and flagged so
the data-quality stage can score them.
"""

import re

import numpy as np
import pandas as pd

DATE_FORMATS = ["%d/%m/%Y", "%m/%d/%Y", "%Y-%m-%d", "%d-%b-%Y", "%d-%B-%Y",
                "%m/%d/%y", "%d/%m/%y", "%Y/%m/%d"]


def _looks_day_first(series):
    """If any value's first component exceeds 12, it must be day-first."""
    for v in series.dropna().astype(str).head(200):
        m = re.match(r"^\s*(\d{1,2})[/-]", v)
        if m and int(m.group(1)) > 12:
            return True
    return False


def normalize_dates(series, trail=None):
    s = series.astype(str).str.strip()
    day_first = _looks_day_first(s)
    # try explicit formats first for a clean, unambiguous parse
    best = None
    best_ok = -1
    for fmt in DATE_FORMATS:
        parsed = pd.to_datetime(s, format=fmt, errors="coerce")
        ok = parsed.notna().sum()
        if ok > best_ok:
            best_ok, best, best_fmt = ok, parsed, fmt
    # fall back to a lenient parse for anything still missing
    if best is None or best.isna().any():
        lenient = pd.to_datetime(s, errors="coerce", dayfirst=day_first)
        best = best.fillna(lenient) if best is not None else lenient
        best_fmt = "mixed"
    coerced = int(best.isna().sum())
    if trail is not None:
        trail.add("clean", "normalize dates", rows_affected=len(series),
                  details=f"format={best_fmt} dayfirst={day_first} unparsed={coerced}")
    return best


def parse_amount(series, trail=None):
    """Parse currency-ish strings to float. Handles $ , () negatives, EU format."""
    def _one(v):
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return np.nan
        t = str(v).strip()
        if t == "" or t.lower() in ("nan", "none", "null"):
            return np.nan
        neg = False
        if t.startswith("(") and t.endswith(")"):
            neg, t = True, t[1:-1]
        t = re.sub(r"[^0-9.,\-]", "", t)  # drop currency symbols / spaces
        if t.count(",") and t.count("."):
            # both present: the rightmost separator is the decimal point
            if t.rfind(",") > t.rfind("."):      # EU: 1.234,56
                t = t.replace(".", "").replace(",", ".")
            else:                                 # US: 1,234.56
                t = t.replace(",", "")
        elif t.count(",") == 1 and re.search(r",\d{2}$", t):
            t = t.replace(",", ".")               # 1234,56 -> 1234.56
        else:
            t = t.replace(",", "")
        try:
            val = float(t)
        except ValueError:
            return np.nan
        return -val if neg else val

    out = series.map(_one)
    if trail is not None:
        trail.add("clean", "parse amounts", rows_affected=len(series),
                  details=f"unparsed={int(out.isna().sum())}")
    return out


_DR_TOKENS = {"dr", "d", "debit", "+", "debits"}
_CR_TOKENS = {"cr", "c", "credit", "-", "credits"}


def normalize_sign(df, trail=None):
    """Derive signed_amount: +amount for DR, -amount for CR (debit-positive).

    If there is no dr_cr column, ``amount`` is assumed already signed.
    """
    amount = df["amount"] if "amount" in df.columns else pd.Series(np.nan, index=df.index)
    if "dr_cr" in df.columns:
        norm = df["dr_cr"].astype(str).str.strip().str.lower()
        sign = pd.Series(np.nan, index=df.index)
        sign[norm.isin(_DR_TOKENS)] = 1.0
        sign[norm.isin(_CR_TOKENS)] = -1.0
        # default unknown indicators to debit-positive but flag via NaN-free fill
        unknown = sign.isna()
        sign = sign.fillna(1.0)
        df["dr_cr"] = np.where(norm.isin(_CR_TOKENS), "CR", "DR")
        signed = amount.abs() * sign
        if trail is not None:
            trail.add("clean", "normalize sign from DR/CR", rows_affected=len(df),
                      details=f"unknown_indicator={int(unknown.sum())}")
    else:
        signed = amount
        if trail is not None:
            trail.add("clean", "amount treated as already signed",
                      rows_affected=len(df))
    df["signed_amount"] = signed
    return df


def _clean_text(series):
    return (series.astype(str)
            .str.replace(r"\s+", " ", regex=True)
            .str.strip()
            .replace({"nan": np.nan, "None": np.nan, "": np.nan}))


def clean_gl(df, trail):
    df = df.copy()
    if "date" in df.columns:
        df["date"] = normalize_dates(df["date"], trail)
    if "amount" in df.columns:
        df["amount"] = parse_amount(df["amount"], trail)
    df = normalize_sign(df, trail)
    for col in ("description", "account_name"):
        if col in df.columns:
            df[col] = _clean_text(df[col])
    if "account_name" in df.columns:
        df["account_name"] = df["account_name"].str.title()
    if "account_code" in df.columns:
        df["account_code"] = df["account_code"].astype(str).str.strip()
    if "transaction_id" in df.columns:
        df["transaction_id"] = df["transaction_id"].astype(str).str.strip()
    trail.add("clean", "GL cleaned", rows_affected=len(df),
              details="dates/amounts/sign/text normalized")
    return df


def build_cleaning_report(before, after, max_examples=8, max_rows=40):
    """Diff the mapped-raw GL against the cleaned GL to record, per field, what was
    transformed, a few before→after examples, and the affected row numbers. This is
    what lets the assistant answer 'what was replaced and which rows were affected'.
    """
    rep = {}

    def _s(v):
        return "" if v is None or (isinstance(v, float) and v != v) else str(v)

    # dates: raw string -> ISO
    if "date" in before.columns and "date" in after.columns:
        ex, rows, unparsed = [], [], 0
        for i in before.index:
            b = _s(before.at[i, "date"])
            a = after.at[i, "date"]
            iso = a.date().isoformat() if isinstance(a, pd.Timestamp) and pd.notna(a) else None
            if iso is None:
                if b.strip() and b.lower() not in ("nan", "none"):
                    unparsed += 1
                    rows.append(int(i))
            elif b != iso:
                rows.append(int(i))
                if len(ex) < max_examples:
                    ex.append({"row": int(i), "before": b, "after": iso})
        rep["dates"] = {"reformatted": len(rows), "unparsed": unparsed,
                        "examples": ex, "rows": rows[:max_rows]}

    # amounts: raw string -> float
    if "amount" in before.columns and "amount" in after.columns:
        ex, rows, unparsed = [], [], 0
        for i in before.index:
            b = _s(before.at[i, "amount"])
            a = after.at[i, "amount"]
            if a is None or (isinstance(a, float) and a != a):
                if b.strip() and b.lower() not in ("nan", "none"):
                    unparsed += 1
                    rows.append(int(i))
            else:
                af = f"{float(a):.2f}"
                if b.replace(",", "").replace("$", "").strip() not in (af, str(a)):
                    if len(ex) < max_examples:
                        ex.append({"row": int(i), "before": b, "after": af})
        rep["amounts"] = {"parsed": int(after["amount"].notna().sum()),
                          "unparsed": unparsed, "examples": ex, "rows": rows[:max_rows]}

    # signed amount from DR/CR
    if "dr_cr" in after.columns and "signed_amount" in after.columns:
        ex = []
        for i in after.index:
            if len(ex) >= max_examples:
                break
            ex.append({"row": int(i), "dr_cr": _s(after.at[i, "dr_cr"]),
                       "amount": _s(after.at[i, "amount"]),
                       "signed_amount": _s(after.at[i, "signed_amount"])})
        n_cr = int((after["dr_cr"] == "CR").sum())
        rep["signed_amount"] = {"credits_negated": n_cr, "examples": ex,
                                "rule": "DR -> +amount, CR -> -amount (debit-positive)"}

    # text normalisation (account_name trim/title-case)
    if "account_name" in before.columns and "account_name" in after.columns:
        ex, rows = [], []
        for i in before.index:
            b, a = _s(before.at[i, "account_name"]), _s(after.at[i, "account_name"])
            if b != a and a:
                rows.append(int(i))
                if len(ex) < max_examples:
                    ex.append({"row": int(i), "before": b, "after": a})
        rep["text_normalised"] = {"changed": len(rows), "examples": ex, "rows": rows[:max_rows]}

    # missing required values after cleaning
    missing = {}
    for col in ("description", "account_name", "amount", "date"):
        if col in after.columns:
            rows = [int(i) for i in after.index
                    if after.at[i, col] is None
                    or (isinstance(after.at[i, col], float) and after.at[i, col] != after.at[i, col])
                    or after.at[i, col] is pd.NaT]
            if rows:
                missing[col] = {"count": len(rows), "rows": rows[:max_rows]}
    rep["missing_values"] = missing
    return rep


def clean_tb(df, trail):
    df = df.copy()
    if "balance" in df.columns:
        df["balance"] = parse_amount(df["balance"], trail)
    if "account_name" in df.columns:
        df["account_name"] = _clean_text(df["account_name"]).str.title()
    if "account_code" in df.columns:
        df["account_code"] = df["account_code"].astype(str).str.strip()
    trail.add("clean", "TB cleaned", rows_affected=len(df))
    return df
