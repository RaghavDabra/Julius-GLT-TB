"""Pipeline orchestrator: wires stages 1-5 into a single PipelineResult.

The returned dict is the single source of truth the whole frontend renders from.
Stage 6 (AI narratives) and stage 7 (PDF/JSON report) are layered on top of this
result on demand, so a run is fully deterministic and works with no API key.
"""

import numpy as np
import pandas as pd

from . import ai
from .audit_trail import AuditTrail
from .clean import clean_gl, clean_tb, build_cleaning_report
from .dedupe import find_duplicates
from .ingest import read_table, map_headers, apply_mapping
from .reconcile import reconcile
from .schema import GL_SYNONYMS, TB_SYNONYMS, CANONICAL_GL, CANONICAL_TB
from .validate import validate, finalize_scorecard


def _json_safe(obj):
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, (np.floating, float)):
        return None if (isinstance(obj, float) and obj != obj) else float(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, pd.Timestamp):
        return obj.date().isoformat()
    if obj is pd.NaT:
        return None
    return obj


def run_pipeline(gl_file, gl_name, tb_file, tb_name, client_id, client_name,
                 use_ai=False, period_start=None, period_end=None,
                 doc_files=None, doc_names=None):
    trail = AuditTrail()
    ai_enabled = use_ai and ai.ai_available()
    ai_suggest = ai.suggest_mapping if ai_enabled else None

    # --- Stage 1: ingest + map ---
    raw_gl = read_table(gl_file, gl_name, trail, kind="GL")
    gl_map, gl_unmatched, gl_decisions = map_headers(
        list(raw_gl.columns), GL_SYNONYMS, trail, kind="GL", ai_suggest=ai_suggest)
    gl_mapped = apply_mapping(raw_gl, gl_map)

    if tb_file is not None:
        raw_tb = read_table(tb_file, tb_name, trail, kind="TB")
        tb_map, tb_unmatched, tb_decisions = map_headers(
            list(raw_tb.columns), TB_SYNONYMS, trail, kind="TB", ai_suggest=ai_suggest)
        tb = apply_mapping(raw_tb, tb_map)
    else:
        tb = pd.DataFrame(columns=CANONICAL_TB)
        tb_map, tb_unmatched, tb_decisions = {}, [], []

    # --- Stage 2: clean ---
    gl = clean_gl(gl_mapped, trail)
    tb = clean_tb(tb, trail)
    cleaning_report = build_cleaning_report(gl_mapped, gl)

    if period_start is not None:
        period_start = pd.Timestamp(period_start)
    if period_end is not None:
        period_end = pd.Timestamp(period_end)

    # --- Stage 3: validate + scorecard ---
    validation, scorecard = validate(gl, tb, trail, period_start, period_end)

    # --- Stage 4: dedupe ---
    duplicates, uniqueness, dup_index = find_duplicates(gl, trail)
    scorecard["uniqueness"] = uniqueness

    # --- Stage 5: reconcile ---
    recon_rows, accuracy, materiality, sankey, heatmap = reconcile(gl, tb, trail)
    scorecard["accuracy"] = accuracy
    scorecard = finalize_scorecard(scorecard)

    # --- Stage: supporting-document evidence matching (optional) ---
    support = None
    if doc_files:
        from .documents import process_documents
        support = process_documents(doc_files, doc_names, gl, recon_rows, trail,
                                    use_ai=ai_enabled)

    # --- KPIs ---
    n_acc = max(len(recon_rows), 1)
    reconciled = sum(1 for r in recon_rows if r["status"] == "reconciled")
    material_breaks = sum(1 for r in recon_rows if r["status"] == "material_break")
    immaterial_breaks = sum(1 for r in recon_rows if r["status"] == "immaterial_break")
    kpis = {
        "gl_rows": int(len(gl)),
        "tb_accounts": int(len(tb)),
        "journals": int(gl["transaction_id"].nunique()) if "transaction_id" in gl.columns else 0,
        "reconciled_pct": round(reconciled / n_acc, 4),
        "material_breaks": material_breaks,
        "immaterial_breaks": immaterial_breaks,
        "dupes_flagged": len(duplicates),
        "dq_overall": scorecard["overall"],
        "materiality": materiality,
        "doc_coverage": support["coverage_pct"] if support else None,
        "unsupported_journals": support["unsupported_count"] if support else None,
    }

    summary = {
        "client_name": client_name,
        "gl_rows": kpis["gl_rows"], "tb_accounts": kpis["tb_accounts"],
        "journals": kpis["journals"], "material_breaks": material_breaks,
        "dupes": len(duplicates), "dq_overall": scorecard["overall"],
    }

    result = {
        "client_id": client_id,
        "client_name": client_name,
        "mapping": {"gl": gl_map, "tb": tb_map,
                    "gl_decisions": gl_decisions, "tb_decisions": tb_decisions,
                    "gl_unmatched": gl_unmatched, "tb_unmatched": tb_unmatched},
        "summary": summary,
        "scorecard": scorecard,
        "cleaning": cleaning_report,
        "validation": validation,
        "duplicates": duplicates,
        "reconciliation": recon_rows,
        "support": support,
        "sankey": sankey,
        "heatmap": heatmap,
        "kpis": kpis,
        "ai": {"available": ai.ai_available(), "explanations": []},
        "trail": trail.to_list(),
    }
    return _json_safe(result)


def attach_explanations(result, top_n=8):
    """Stage 6 enrichment: explain the largest breaks + workpaper narrative."""
    breaks = [r for r in result["reconciliation"]
              if r["status"] in ("material_break", "immaterial_break", "gl_only", "tb_only")]
    breaks = sorted(breaks, key=lambda r: -r["abs_variance"])[:top_n]
    materiality = result["kpis"]["materiality"]
    explanations = []
    for r in breaks:
        exp = ai.explain_break(r, materiality)
        explanations.append({"account_code": r["account_code"], **exp})
    narrative = ai.draft_workpaper(result)
    result["ai"]["explanations"] = explanations
    result["ai"]["narrative"] = narrative
    result["ai"]["available"] = ai.ai_available()
    return result
