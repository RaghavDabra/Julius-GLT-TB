"""Stage 6 - AI reasoning layer (Google Gemini), with deterministic fallbacks.

The numeric pipeline never depends on this module: every function returns a
useful result even with no API key (``source: "fallback"``). When GEMINI_API_KEY
is present we enrich the output with Gemini-authored narratives
(``source: "gemini"``). Chat is grounded RAG over the *computed* pipeline outputs
only - the model is instructed to answer strictly from the supplied audit results
so it cannot invent figures.
"""

import json
import os

from . import insights

MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o")

_genai = None
_configured = False


def gemini_available():
    return bool(os.environ.get("GEMINI_API_KEY"))


def openai_available():
    return bool(os.environ.get("OPENAI_API_KEY"))


def ai_available():
    """True if any provider key is configured (cheap; no network call)."""
    return gemini_available() or openai_available()


_probe_cache = None
_probe_provider = None


def probe(force=False):
    """One-time live check that some provider actually answers (key present AND
    has quota / is unblocked). Cached for the process so the UI can report
    honestly without spending a call on every request. Returns True/False.
    """
    global _probe_cache, _probe_provider
    if _probe_cache is not None and not force:
        return _probe_cache
    if not ai_available():
        _probe_cache, _probe_provider = False, None
        return False
    txt, prov = _generate("Reply with: OK", temperature=0, max_tokens=5)
    _probe_cache = txt is not None
    _probe_provider = prov
    return _probe_cache


def active_provider():
    """Which provider answered the probe ('gemini' | 'openai' | None)."""
    return _probe_provider


def _get_genai():
    """Lazy import + configure so a missing package degrades gracefully."""
    global _genai, _configured
    if _genai is None:
        try:
            import google.generativeai as genai
            _genai = genai
        except Exception:
            return None
    if not _configured:
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            return None
        try:
            _genai.configure(api_key=key)
            _configured = True
        except Exception:
            return None
    return _genai


def _gen_gemini(prompt, system="", temperature=0.3, max_tokens=900, json_mode=False):
    """Single non-streaming Gemini call. Returns text or None on any failure."""
    genai = _get_genai()
    if genai is None:
        return None
    full = f"{system}\n\n{prompt}" if system else prompt
    if json_mode:
        full += "\n\nRespond with valid JSON only, no markdown fences."
    try:
        model = genai.GenerativeModel(MODEL)
        resp = model.generate_content(
            full,
            generation_config=genai.types.GenerationConfig(
                temperature=temperature, max_output_tokens=max_tokens),
        )
        return (resp.text or "").strip()
    except Exception:
        return None


def _gen_openai(prompt, system="", temperature=0.3, max_tokens=900, json_mode=False):
    """Fallback to OpenAI GPT-4o (SDK 0.28 ChatCompletion). Returns text or None."""
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return None
    try:
        import openai
        openai.api_key = key
        sys_msg = system or "You are a precise assistant."
        if json_mode:
            sys_msg += " Respond with valid JSON only, no markdown fences."
        resp = openai.ChatCompletion.create(
            model=OPENAI_MODEL,
            messages=[{"role": "system", "content": sys_msg},
                      {"role": "user", "content": prompt}],
            temperature=temperature, max_tokens=max_tokens,
        )
        return (resp.choices[0].message["content"] or "").strip()
    except Exception:
        return None


def _generate(prompt, system="", temperature=0.3, max_tokens=900, json_mode=False):
    """Provider chain: Gemini -> OpenAI GPT-4o. Returns (text, provider|None)."""
    text = _gen_gemini(prompt, system, temperature, max_tokens, json_mode)
    if text:
        return text, "gemini"
    text = _gen_openai(prompt, system, temperature, max_tokens, json_mode)
    if text:
        return text, "openai"
    return None, None


# --- Mapping suggestion (used by ingest for unmatched headers) -------------

def suggest_mapping(unmatched_headers, canonical_targets):
    """Return {raw_header: canonical} for headers difflib could not place."""
    if not unmatched_headers:
        return {}
    prompt = (
        "Map each raw financial column header to the single best canonical field, "
        "or null if none fits.\n"
        f"Raw headers: {json.dumps(unmatched_headers)}\n"
        f"Canonical fields: {json.dumps(canonical_targets)}\n"
        'Return JSON: {"<raw>": "<canonical-or-null>"}'
    )
    text, _prov = _generate(prompt, system="You are a meticulous financial-data engineer.",
                            json_mode=True, temperature=0.0)
    if not text:
        return {}
    try:
        return {k: v for k, v in json.loads(text).items() if v}
    except Exception:
        return {}


# --- Supporting-document voucher extraction --------------------------------

def extract_vouchers(doc_text):
    """Extract structured journal vouchers from supporting-document text. Returns
    a list of {journal_id, date, amount, description, approver}, or [] on failure
    (the deterministic substring match in documents.py still computes coverage)."""
    if not ai_available() or not doc_text.strip():
        return []
    prompt = (
        "Extract every journal voucher / supporting entry from this audit "
        "documentation text. For each, return journal_id, date, amount, description "
        "and approver (use null if a field is absent). Copy values verbatim; do not "
        "invent any.\n\n"
        f"DOCUMENT TEXT:\n{doc_text[:12000]}\n\n"
        'Return JSON: {"vouchers": [{"journal_id": "...", "date": "...", '
        '"amount": "...", "description": "...", "approver": "..."}]}'
    )
    text, _prov = _generate(prompt, system="You extract structured data from audit "
                            "documents with perfect fidelity.", json_mode=True,
                            temperature=0.0, max_tokens=1500)
    if not text:
        return []
    try:
        return json.loads(text).get("vouchers", []) or []
    except Exception:
        return []


# --- Break explanation -----------------------------------------------------

def explain_break(recon_row, materiality=0, supporting_rows=None):
    c = insights.break_commentary(recon_row, materiality)
    fallback = (c["observation"] + " Likely causes: "
                + "; ".join(c["likely_causes"]) + ". " + c["procedure"])
    if not ai_available():
        return {"text": fallback, "source": "fallback"}
    prompt = (
        "Explain this audit reconciliation break in 2-3 plain-English sentences for an "
        "audit workpaper. State the most likely root cause and the recommended test.\n"
        f"Account: {json.dumps(recon_row)}\n"
        f"Supporting GL rows: {json.dumps(supporting_rows or [])[:2000]}"
    )
    text, prov = _generate(prompt, system="You are an experienced external auditor.")
    return {"text": text or fallback, "source": prov or "fallback"}


# --- Workpaper narrative ---------------------------------------------------

def draft_workpaper(result):
    """``result`` is the full PipelineResult. Fallback is the deterministic
    executive summary; AI rewrites it into flowing workpaper prose when available."""
    fallback = " ".join(insights.executive_summary(result))
    if not ai_available():
        return {"text": fallback, "source": "fallback"}
    rating, opinion = insights.overall_opinion(result)
    prompt = ("Rewrite the following audit summary as a polished 5-7 sentence workpaper "
              "narrative for the engagement file. Keep every figure exact; do not invent "
              "numbers. Cover data preparation, reconciliation outcome, key risks and the "
              f"overall opinion.\nRisk rating: {rating}\nSummary: {fallback}")
    text, prov = _generate(prompt, system="You are an experienced external auditor.",
                           max_tokens=600)
    return {"text": text or fallback, "source": prov or "fallback"}


# --- Grounded chat ---------------------------------------------------------

def answer_chat(question, context_pack, history=None):
    if not ai_available():
        return {"text": _chat_fallback(question, context_pack), "source": "fallback"}
    system = (
        "You are an expert audit & assurance data assistant for the engagement below. "
        "Answer GENERAL accounting/auditing concept questions (e.g. what a trial balance "
        "or general ledger is, the difference between GL and TB, materiality, "
        "double-entry, reconciliation) from your professional knowledge, clearly and "
        "concisely. For figures, balances, variances, counts or findings SPECIFIC to "
        "THIS engagement, use ONLY the provided audit-results JSON and never invent "
        "numbers; if a specific figure is genuinely absent, say so. Where helpful, "
        "ground a concept with this engagement's actual numbers (e.g. its breaks or "
        "materiality). Be precise, cite account codes, and use short paragraphs or "
        "markdown tables."
    )
    convo = ""
    for turn in (history or [])[-6:]:
        convo += f"{turn.get('role','user')}: {turn.get('content','')}\n"
    prompt = (f"AUDIT RESULTS (the only source of truth for engagement-specific figures; "
              f"includes the schema mapping, the cleaning report with before→after examples "
              f"and affected row numbers, validation, duplicates, reconciliation and the audit "
              f"trail):\n{json.dumps(context_pack)[:20000]}\n\n"
              f"{convo}\nQuestion: {question}")
    text, prov = _generate(prompt, system=system, temperature=0.2, max_tokens=1100)
    return {"text": text or _chat_fallback(question, context_pack),
            "source": prov or "fallback"}


def _chat_fallback(question, ctx):
    """Smart deterministic answer when no AI provider is reachable. Routes the
    question to a definition, a specific account, a metric, or a briefing. Figures
    are exact and grounded in the computed pipeline outputs."""
    q = (question or "").lower().strip()
    k = ctx.get("kpis", {})

    # 1. a specific account named by code or name (wins over a generic definition,
    #    e.g. "what is the variance on Consulting Revenue?" wants that account's number)
    a = insights.account_answer(q, ctx)
    if a:
        return a

    # 2. conceptual / definitional questions ("what is a material break?")
    g = insights.glossary_answer(q, ctx)
    if g:
        return g

    def header():
        rating, _ = insights.overall_opinion(ctx)
        return (f"**{ctx.get('client_name','This engagement')}** · risk **{rating}** · "
                f"DQ {round(100*k.get('dq_overall',0))}% · {k.get('material_breaks',0)} material "
                f"break(s)\n\n")

    def recon_breaks():
        breaks = sorted([r for r in ctx.get("reconciliation", [])
                         if r["status"] != "reconciled"], key=lambda x: -x["abs_variance"])
        if not breaks:
            return "All accounts reconciled within materiality — no breaks to report."
        rows = ["| Account | Name | Variance | Status |", "|---|---|---:|---|"]
        for r in breaks[:10]:
            rows.append(f"| {r['account_code']} | {r['account_name']} | "
                        f"{r['variance']:,.2f} | {r['status'].replace('_',' ')} |")
        top = breaks[0]
        c = insights.break_commentary(top, k.get("materiality", 0))
        return ("\n".join(rows) + f"\n\n**Largest — {top['account_code']} {top['account_name']}:** "
                + c["observation"] + " " + c["procedure"])

    # 3. metric / data intents
    if any(w in q for w in ("ingest", "clean", "cleaned", "replaced", "transform", "standardi",
                            "mapping", "mapped", "preprocess", "normalis", "what changed",
                            "which rows", "rows affected", "rows were affected", "reformat",
                            "parsed", "wrangl")):
        body = (insights.cleaning_summary(ctx)
                or "No transformations were required — the data was already clean.")
    elif any(w in q for w in ("document", "supporting", "voucher", "evidence", "coverage",
                              "undocumented", "approval", "pdf", "support")):
        body = insights.documentation_summary(ctx)
    elif any(w in q for w in ("recommend", "should i", "next step", "what do i do", "remediat", "fix")):
        body = "**Recommendations**\n" + "\n".join(f"- {r}" for r in insights.recommendations(ctx))
    elif any(w in q for w in ("dupe", "duplicate")):
        d = ctx.get("duplicates", [])
        lines = [f"**{len(d)} duplicate group(s) flagged** (retained for review, never auto-removed):"]
        for g2 in d[:8]:
            lines.append(f"- {g2.get('group_id')} · {g2.get('kind')} · "
                         f"{g2.get('n', len(g2.get('rows', [])))} rows")
        body = "\n".join(lines)
    elif any(w in q for w in ("quality", "completeness", "validity", "consistency",
                              "uniqueness", "accuracy", "timeliness", "dimension", "score")):
        body = "**Data-quality by dimension**\n" + "\n".join(
            f"- **{dim.title()}**: {note}" for dim, note in insights.dimension_commentary(ctx).items())
    elif any(w in q for w in ("break", "reconcil", "variance", "vs tb", "vs trial", "gl vs",
                              "ledger vs", "unreconcil", "exception")):
        body = recon_breaks()
    elif any(w in q for w in ("risk", "summary", "overview", "opinion", "conclusion",
                              "tell me", "what does this", "key findings", "say")):
        body = "\n\n".join(insights.executive_summary(ctx))
        body += "\n\n**Key findings:**\n" + "\n".join(
            f"- [{f['severity']}] {f['title']}" for f in insights.findings(ctx)[:5])
    else:
        # genuinely unmatched — answer briefly and steer, don't dump the whole summary
        body = (insights.executive_summary(ctx)[2]  # the audit-conclusion sentence
                + "\n\nI can answer questions about specific accounts (by code or name), "
                "reconciliation breaks, duplicates, data quality, materiality, or the overall "
                "risk. For free-form questions, add a funded GEMINI_API_KEY/OPENAI_API_KEY to "
                "enable the AI model.")
    return header() + body


def _fmt(v):
    return "n/a" if v is None else f"{v:,.2f}"
