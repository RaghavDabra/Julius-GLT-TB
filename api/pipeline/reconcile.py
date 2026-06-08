"""Stage 5 - Reconciliation (GL vs TB).

Computes the GL-derived balance per account (sum of signed amounts) and compares
it to the Trial Balance. Each account is classified relative to a materiality
threshold. This stage produces the reconciliation table plus the derived
``sankey`` (money-flow lineage) and ``heatmap`` payloads the dashboard renders.
"""

import numpy as np
import pandas as pd

RECON_TOL = 0.005


def _account_category(code):
    code = str(code)
    first = code[0] if code and code[0].isdigit() else "0"
    return {
        "1": "Assets", "2": "Liabilities", "3": "Equity",
        "4": "Revenue", "5": "Expenses", "6": "Expenses",
    }.get(first, "Other")


def compute_materiality(tb, floor=1000.0, pct=0.01):
    if "balance" not in tb.columns or tb.empty:
        return floor
    total = float(tb["balance"].abs().sum())
    return round(max(total * pct, floor), 2)


def reconcile(gl, tb, trail, materiality=None):
    if materiality is None:
        materiality = compute_materiality(tb)

    gl_bal = (gl.groupby("account_code")["signed_amount"].sum()
              if {"account_code", "signed_amount"}.issubset(gl.columns)
              else pd.Series(dtype=float))
    tb_idx = tb.set_index("account_code") if "account_code" in tb.columns else pd.DataFrame()

    names = {}
    if "account_name" in gl.columns:
        names.update(gl.dropna(subset=["account_code"])
                     .groupby("account_code")["account_name"].first().to_dict())
    if "account_name" in tb.columns:
        for code, nm in tb.set_index("account_code")["account_name"].items():
            names.setdefault(str(code), nm)

    all_codes = sorted(set(gl_bal.index.astype(str)) |
                       set(tb_idx.index.astype(str) if not tb_idx.empty else []))

    rows = []
    for code in all_codes:
        gl_val = float(gl_bal.get(code, np.nan)) if code in gl_bal.index else np.nan
        tb_val = (float(tb_idx.at[code, "balance"])
                  if (not tb_idx.empty and code in tb_idx.index and "balance" in tb_idx.columns)
                  else np.nan)
        in_gl, in_tb = not np.isnan(gl_val), not np.isnan(tb_val)

        if in_gl and not in_tb:
            status, variance = "gl_only", gl_val
        elif in_tb and not in_gl:
            status, variance = "tb_only", -tb_val
        else:
            variance = gl_val - tb_val
            av = abs(variance)
            if av <= RECON_TOL:
                status = "reconciled"
            elif av <= materiality:
                status = "immaterial_break"
            else:
                status = "material_break"

        rows.append({
            "account_code": str(code),
            "account_name": names.get(code) or names.get(str(code)) or "(unknown)",
            "category": _account_category(code),
            "gl_balance": None if np.isnan(gl_val) else round(gl_val, 2),
            "tb_balance": None if np.isnan(tb_val) else round(tb_val, 2),
            "variance": round(float(variance), 2),
            "abs_variance": round(abs(float(variance)), 2),
            "status": status,
        })

    n_break = sum(1 for r in rows if r["status"] in ("material_break", "immaterial_break",
                                                     "gl_only", "tb_only"))
    accuracy = 1.0 - (n_break / max(len(rows), 1))

    trail.add("reconcile", "GL vs TB reconciliation", rows_affected=len(rows),
              details=(f"materiality={materiality} reconciled="
                       f"{sum(1 for r in rows if r['status']=='reconciled')} "
                       f"material_breaks={sum(1 for r in rows if r['status']=='material_break')}"),
              outputs={"materiality": materiality})

    sankey = _build_sankey(rows)
    heatmap = _build_heatmap(rows, materiality)
    return rows, round(max(accuracy, 0.0), 4), materiality, sankey, heatmap


_STATUS_LABEL = {
    "reconciled": "Reconciled",
    "immaterial_break": "Immaterial break",
    "material_break": "Material break",
    "gl_only": "GL only",
    "tb_only": "TB only",
}


def _build_sankey(rows):
    """3-layer flow: GL Postings -> account category -> reconciliation status.

    Returns recharts-compatible {nodes:[{name}], links:[{source,target,value}]}.
    """
    categories = []
    statuses = []
    cat_totals = {}
    cat_status_totals = {}
    for r in rows:
        cat = r["category"]
        st = _STATUS_LABEL[r["status"]]
        weight = abs(r["gl_balance"] if r["gl_balance"] is not None else r["tb_balance"] or 0) + 1
        categories.append(cat)
        statuses.append(st)
        cat_totals[cat] = cat_totals.get(cat, 0) + weight
        cat_status_totals[(cat, st)] = cat_status_totals.get((cat, st), 0) + weight

    cats = sorted(set(categories))
    sts = sorted(set(statuses))
    nodes = ["GL Postings"] + cats + sts
    index = {name: i for i, name in enumerate(nodes)}
    links = []
    for cat in cats:
        links.append({"source": index["GL Postings"], "target": index[cat],
                      "value": round(cat_totals[cat], 2)})
    for (cat, st), val in cat_status_totals.items():
        links.append({"source": index[cat], "target": index[st],
                      "value": round(val, 2)})
    return {"nodes": [{"name": n} for n in nodes], "links": links}


def _build_heatmap(rows, materiality):
    """Per-account intensity 0..1 (variance / materiality, capped) for the grid."""
    cells = []
    for r in rows:
        intensity = min(r["abs_variance"] / materiality, 1.0) if materiality else 0.0
        cells.append({
            "account_code": r["account_code"],
            "account_name": r["account_name"],
            "category": r["category"],
            "status": r["status"],
            "intensity": round(intensity, 3),
            "variance": r["variance"],
        })
    return {"materiality": materiality, "cells": cells}
