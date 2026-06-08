"""LedgerLens - AI-enabled audit data pipeline (Flask API).

Replaces the previous ML/regression backend. Exposes the deterministic audit
pipeline (ingest -> clean -> validate -> dedupe -> reconcile -> document) plus a
Gemini-powered, grounded reasoning layer. The pipeline runs with no API key; AI
is an optional enrichment with deterministic fallbacks.
"""

import json
import os
import traceback

from flask import Flask, request, jsonify, Response
from flask_cors import CORS

from pipeline import run_pipeline, attach_explanations
from pipeline import ai as ai_layer
from pipeline.report import build_pdf, build_audit_json
from store import STORE

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.normpath(os.path.join(HERE, "..", "data", "synthetic"))
OPERATOR_ENV = "/Users/manushresthkrishnan/projects/operator/backend/.env"
# How many engagements to surface in the app (the dataset on disk can be larger).
MAX_ENGAGEMENTS = int(os.environ.get("LEDGERLENS_MAX_ENGAGEMENTS", "3"))


# --- env bootstrap: reuse the Gemini key wherever it already lives ----------
def _bootstrap_env():
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(HERE, "..", ".env"))
    except Exception:
        pass
    if not os.environ.get("GEMINI_API_KEY") and os.path.exists(OPERATOR_ENV):
        try:
            with open(OPERATOR_ENV) as f:
                for line in f:
                    if line.strip().startswith("GEMINI_API_KEY="):
                        val = line.split("=", 1)[1].strip().strip('"').strip("'")
                        if val:
                            os.environ["GEMINI_API_KEY"] = val
                        break
        except Exception:
            pass


_bootstrap_env()

app = Flask(__name__)
CORS(app)


# --- startup: load the synthetic engagements so the sidebar is populated ----
def load_synthetic():
    manifest_path = os.path.join(DATA_DIR, "manifest.json")
    if not os.path.exists(manifest_path):
        print(f"[startup] no synthetic manifest at {manifest_path}; "
              "run scripts/generate_dataset.py")
        return
    with open(manifest_path) as f:
        manifest = json.load(f)
    loaded = 0
    for c in manifest.get("clients", [])[:MAX_ENGAGEMENTS]:
        try:
            gl_path = os.path.join(DATA_DIR, c["gl_path"])
            tb_path = os.path.join(DATA_DIR, c["tb_path"]) if c.get("tb_path") else None
            result = run_pipeline(
                gl_path, os.path.basename(gl_path),
                tb_path, os.path.basename(tb_path) if tb_path else None,
                client_id=c["client_id"], client_name=c["client_name"],
                use_ai=False, period_start="2026-01-01", period_end="2026-12-31",
            )
            STORE.put(c["client_id"], result)
            loaded += 1
        except Exception as e:
            print(f"[startup] failed to load {c.get('client_id')}: {e}")
    if not ai_layer.ai_available():
        gem = "off (no key) -> deterministic fallback"
    elif ai_layer.probe():
        gem = f"on (live via {ai_layer.active_provider()})"
    else:
        gem = "key set but not responding (quota/blocked) -> deterministic fallback"
    print(f"[startup] loaded {loaded} engagement(s); AI={gem}")


# --- routes ----------------------------------------------------------------

@app.route("/api/health")
def health():
    return jsonify({"ok": True, "ai_available": ai_layer.probe(),
                    "ai_key_present": ai_layer.ai_available(),
                    "ai_provider": ai_layer.active_provider(),
                    "engagements": len(STORE.list())})


@app.route("/api/clients")
def clients():
    return jsonify({"clients": STORE.list(),
                    "ai_available": ai_layer.probe(),
                    "ai_provider": ai_layer.active_provider()})


@app.route("/api/result/<client_id>")
def result(client_id):
    res = STORE.get(client_id)
    if not res:
        return jsonify({"error": "unknown client"}), 404
    return jsonify(res)


@app.route("/api/clients/<client_id>", methods=["DELETE"])
def delete_client(client_id):
    """Remove an engagement from the in-memory workspace (session-only; pinned and
    synthetic engagements reload on the next restart)."""
    return jsonify({"ok": STORE.remove(client_id)})


@app.route("/api/ingest", methods=["POST"])
def ingest():
    """Upload GL (+ optional TB), return the deterministic header mapping preview."""
    try:
        gl = request.files.get("gl")
        if gl is None:
            return jsonify({"error": "no GL file provided"}), 400
        from pipeline.ingest import read_table, map_headers
        from pipeline.schema import GL_SYNONYMS
        from pipeline.audit_trail import AuditTrail
        trail = AuditTrail()
        raw = read_table(gl, gl.filename, trail, kind="GL")
        mapping, unmatched, decisions = map_headers(
            list(raw.columns), GL_SYNONYMS, trail, kind="GL")
        preview = raw.head(8).fillna("").astype(str).to_dict(orient="records")
        return jsonify({"mapping": mapping, "unmatched": unmatched,
                        "decisions": decisions, "preview": preview,
                        "columns": list(raw.columns), "rows": len(raw),
                        "trail": trail.to_list()})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/run", methods=["POST"])
def run():
    """Upload GL (+ optional TB), run the full pipeline, store + return result."""
    try:
        gl = request.files.get("gl")
        tb = request.files.get("tb")
        if gl is None:
            return jsonify({"error": "no GL file provided"}), 400
        client_name = request.form.get("client_name") or os.path.splitext(gl.filename)[0]
        client_id = request.form.get("client_id") or _slug(client_name)
        use_ai = request.form.get("ai", "false").lower() == "true"
        docs = request.files.getlist("docs")
        result = run_pipeline(
            gl, gl.filename, tb, tb.filename if tb else None,
            client_id=client_id, client_name=client_name, use_ai=use_ai,
            period_start="2026-01-01", period_end="2026-12-31",
            doc_files=docs or None,
            doc_names=[d.filename for d in docs] if docs else None,
        )
        if use_ai:
            attach_explanations(result)
        STORE.put(client_id, result)
        return jsonify(result)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/ai/explain", methods=["POST"])
def ai_explain():
    data = request.get_json(force=True) or {}
    res = STORE.get(data.get("client_id"))
    if not res:
        return jsonify({"error": "unknown client"}), 404
    attach_explanations(res)
    STORE.put(res["client_id"], res)
    return jsonify({"ai": res["ai"]})


@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(force=True) or {}
    res = STORE.get(data.get("client_id"))
    question = data.get("question", "")
    history = data.get("history", [])
    if not res:
        return jsonify({"error": "unknown client"}), 404
    context = {
        "client_name": res["client_name"],
        "kpis": res["kpis"],
        "scorecard": res["scorecard"],
        "reconciliation": res["reconciliation"],
        "validation": res["validation"],
        "duplicates": [{"group_id": d["group_id"], "kind": d["kind"], "score": d["score"],
                        "n": len(d["rows"]), "rows": d["rows"]}
                       for d in res["duplicates"]],
        "mapping": res["mapping"]["gl"],
        "mapping_decisions": res["mapping"]["gl_decisions"],
        "cleaning": res.get("cleaning", {}),
        "support": res.get("support"),
        "audit_trail": [{"stage": t["stage"], "action": t["action"],
                         "rows": t["rows_affected"], "details": t["details"]}
                        for t in res["trail"]],
    }
    answer = ai_layer.answer_chat(question, context, history)
    return jsonify(answer)


@app.route("/api/report/<client_id>.pdf")
def report_pdf(client_id):
    res = STORE.get(client_id)
    if not res:
        return jsonify({"error": "unknown client"}), 404
    if not res["ai"].get("explanations"):
        attach_explanations(res)
        STORE.put(client_id, res)
    pdf = build_pdf(res)
    return Response(pdf, mimetype="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="LedgerLens_{client_id}.pdf"'})


@app.route("/api/report/<client_id>.json")
def report_json(client_id):
    res = STORE.get(client_id)
    if not res:
        return jsonify({"error": "unknown client"}), 404
    return jsonify(build_audit_json(res))


def _slug(name):
    return "".join(c.lower() if c.isalnum() else "-" for c in name).strip("-")[:40]


def load_pinned():
    """Auto-load hand-crafted sample engagements (e.g. data/deloitte) so they are
    always present in the sidebar without re-ingesting."""
    for cid, name, folder in [("deloitte", "Deloitte", "deloitte")]:
        base = os.path.normpath(os.path.join(HERE, "..", "data", folder))
        gl, tb = os.path.join(base, "gl.csv"), os.path.join(base, "tb.csv")
        pdf = os.path.join(base, "journals.pdf")
        docs = [pdf] if os.path.exists(pdf) else None
        if os.path.exists(gl) and os.path.exists(tb):
            try:
                STORE.put(cid, run_pipeline(
                    gl, "gl.csv", tb, "tb.csv", client_id=cid, client_name=name,
                    use_ai=False, period_start="2026-01-01", period_end="2026-12-31",
                    doc_files=docs, doc_names=["journals.pdf"] if docs else None))
                print(f"[startup] pinned engagement: {name}"
                      + (" (+ supporting PDF)" if docs else ""))
            except Exception as e:
                print(f"[startup] failed to load {name}: {e}")


load_synthetic()
load_pinned()

if __name__ == "__main__":
    app.run(debug=True, port=8080)
