"""Stage 4 - Deduplication.

Detects exact and near-duplicate transactions deterministically. Duplicates are
*flagged, never dropped* - in an audit context the decision to remove a record is
the auditor's, and silent removal would itself be a finding. Near-duplicate
detection blocks on (account, rounded amount, date) and compares descriptions
with stdlib difflib, so it catches e.g. "Laptop purchase" vs
"Laptop purchase - accessory duplicate entry".
"""

import difflib

NEAR_THRESHOLD = 0.85

EXACT_SUBSET = ["transaction_id", "date", "account_code", "dr_cr", "amount", "description"]


def find_duplicates(gl, trail):
    duplicates = []
    flagged_index = set()

    # --- exact duplicates ---
    subset = [c for c in EXACT_SUBSET if c in gl.columns]
    if subset:
        dup_mask = gl.duplicated(subset=subset, keep=False)
        if dup_mask.any():
            grouped = gl[dup_mask].groupby(subset, dropna=False)
            for gid, (_, group) in enumerate(grouped, start=1):
                idxs = list(group.index)
                flagged_index.update(idxs)
                duplicates.append({
                    "group_id": f"E{gid}",
                    "kind": "exact",
                    "score": 1.0,
                    "rows": [_row_summary(gl, i) for i in idxs],
                })

    # --- near duplicates: same account+amount+date posted under DIFFERENT
    # transaction ids (a likely double-posting). An identical amount-to-the-cent
    # on the same date and account is the structural signal; description
    # similarity is reported as the score but is not the gate, because a re-keyed
    # duplicate is often given a slightly altered narrative.
    if ({"account_code", "amount", "transaction_id"}.issubset(gl.columns)):
        gl_block = gl.assign(_amt=gl["amount"].round(2))
        block_cols = ["account_code", "_amt"] + (["date"] if "date" in gl.columns else [])
        n_near = 0
        for _, block in gl_block.groupby(block_cols, dropna=False):
            idxs = list(block.index)
            if len(idxs) < 2:
                continue
            if gl.loc[idxs, "transaction_id"].nunique() < 2:
                continue  # same journal id -> handled by exact check
            descs = [str(gl.at[i, "description"] or "") for i in idxs]
            ratio = max(
                (difflib.SequenceMatcher(None, descs[a].lower(), descs[b].lower()).ratio()
                 for a in range(len(idxs)) for b in range(a + 1, len(idxs))),
                default=0.0)
            flagged_index.update(idxs)
            n_near += 1
            duplicates.append({
                "group_id": f"N{n_near}",
                "kind": "near",
                "score": round(ratio, 3),
                "rows": [_row_summary(gl, i) for i in idxs],
            })

    trail.add("dedupe", "duplicate detection", rows_affected=len(flagged_index),
              details=f"{len(duplicates)} groups flagged "
                      f"({sum(1 for d in duplicates if d['kind']=='exact')} exact, "
                      f"{sum(1 for d in duplicates if d['kind']=='near')} near); none dropped")
    uniqueness = 1.0 - (len(flagged_index) / max(len(gl), 1))
    return duplicates, round(max(uniqueness, 0.0), 4), flagged_index


def _row_summary(gl, i):
    out = {"row": int(i)}
    for c in ("transaction_id", "date", "account_code", "dr_cr", "amount", "description"):
        if c in gl.columns:
            v = gl.at[i, c]
            try:
                import pandas as pd
                if isinstance(v, pd.Timestamp):
                    v = v.date().isoformat()
            except Exception:
                pass
            out[c] = None if (v != v) else (str(v) if not isinstance(v, (int, float)) else v)
    return out
