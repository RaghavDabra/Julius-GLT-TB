"""Stage 3 - Validation & data-quality scorecard.

Runs the deterministic assurance checks an auditor would expect (double-entry,
completeness, referential integrity, validity) and rolls them up into a
six-dimension data-quality scorecard (0-100 per dimension) that drives the radar
chart. The ``uniqueness`` and ``accuracy`` dimensions are filled in later from
the dedupe and reconcile stages.
"""

import numpy as np
import pandas as pd

from .schema import REQUIRED_GL, REQUIRED_TB

BALANCE_TOL = 0.005


def _journal_balance(gl):
    """Per-transaction double-entry check: sum(signed_amount) ~ 0."""
    if "transaction_id" not in gl.columns or "signed_amount" not in gl.columns:
        return [], 0
    grouped = gl.groupby("transaction_id")["signed_amount"].sum()
    unbalanced = grouped[grouped.abs() > BALANCE_TOL]
    rows = [{"transaction_id": str(tid), "residual": round(float(res), 2)}
            for tid, res in unbalanced.items()]
    return rows, int(grouped.shape[0])


def _missing_fields(gl):
    issues = {}
    for col in REQUIRED_GL:
        if col not in gl.columns:
            issues[col] = "column_absent"
        else:
            n = int(gl[col].isna().sum())
            if n:
                issues[col] = n
    return issues


def _referential_integrity(gl, tb):
    gl_accts = set(gl["account_code"].dropna().astype(str)) if "account_code" in gl else set()
    tb_accts = set(tb["account_code"].dropna().astype(str)) if "account_code" in tb else set()
    gl_only = sorted(gl_accts - tb_accts)
    tb_only = sorted(tb_accts - gl_accts)
    return gl_only, tb_only


def _validity(gl, period_start, period_end):
    problems = {"bad_dr_cr": 0, "non_positive_amount": 0, "out_of_period": 0}
    if "dr_cr" in gl.columns:
        problems["bad_dr_cr"] = int((~gl["dr_cr"].isin(["DR", "CR"])).sum())
    if "amount" in gl.columns and "dr_cr" in gl.columns:
        problems["non_positive_amount"] = int((gl["amount"] <= 0).sum())
    if "date" in gl.columns and period_start is not None:
        d = pd.to_datetime(gl["date"], errors="coerce")
        out = ((d < period_start) | (d > period_end)) & d.notna()
        problems["out_of_period"] = int(out.sum())
    return problems


def validate(gl, tb, trail, period_start=None, period_end=None):
    n = max(len(gl), 1)

    unbalanced, n_journals = _journal_balance(gl)
    missing = _missing_fields(gl)
    gl_only, tb_only = _referential_integrity(gl, tb)
    validity = _validity(gl, period_start, period_end)

    # --- scorecard dimensions (0..1) ---
    required_cells = max(len(gl) * len(REQUIRED_GL), 1)
    missing_cells = sum(v for v in missing.values() if isinstance(v, int))
    completeness = 1.0 - missing_cells / required_cells

    validity_fails = sum(validity.values())
    validity_score = 1.0 - min(validity_fails / n, 1.0)

    consistency = 1.0 - (len(unbalanced) / max(n_journals, 1))

    nat = int(gl["date"].isna().sum()) if "date" in gl.columns else 0
    timeliness = 1.0 - min((nat + validity["out_of_period"]) / n, 1.0)

    validation = {
        "double_entry": {
            "journals": n_journals,
            "unbalanced": unbalanced,
            "unbalanced_count": len(unbalanced),
        },
        "missing_fields": missing,
        "referential_integrity": {
            "gl_only_accounts": gl_only,
            "tb_only_accounts": tb_only,
        },
        "validity": validity,
    }

    # uniqueness + accuracy are completed by dedupe / reconcile stages
    scorecard = {
        "completeness": round(max(completeness, 0.0), 4),
        "validity": round(max(validity_score, 0.0), 4),
        "consistency": round(max(consistency, 0.0), 4),
        "uniqueness": 1.0,   # placeholder, set in runner after dedupe
        "accuracy": 1.0,     # placeholder, set in runner after reconcile
        "timeliness": round(max(timeliness, 0.0), 4),
    }

    trail.add("validate", "data-quality checks", rows_affected=len(gl),
              details=(f"unbalanced={len(unbalanced)} missing_cells={missing_cells} "
                       f"gl_only={len(gl_only)} tb_only={len(tb_only)}"),
              outputs={"scorecard_partial": scorecard})
    return validation, scorecard


def finalize_scorecard(scorecard, weights=None):
    weights = weights or {
        "completeness": 1, "validity": 1, "consistency": 1.5,
        "uniqueness": 1, "accuracy": 2, "timeliness": 1,
    }
    num = sum(scorecard[k] * w for k, w in weights.items())
    den = sum(weights.values())
    scorecard["overall"] = round(num / den, 4)
    return scorecard
