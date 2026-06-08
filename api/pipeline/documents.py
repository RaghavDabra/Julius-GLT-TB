"""Stage: supporting-document evidence matching.

The case study provides supporting journal documentation as PDFs. This stage
reads those PDFs, extracts which journals they evidence (AI extraction of
structured vouchers when a provider is available, with a deterministic
substring/regex fallback), and matches them to the general ledger to produce a
**documentation coverage** metric and a list of unsupported journals — with
special attention to journals that touch a reconciliation break (highest audit
risk when undocumented).
"""

import io
import re

from . import ai

JE_HINT = re.compile(r"[A-Z]{2,4}[-\s]?\d{2,6}(?:-[A-Z0-9]+)?")


def extract_text(file_obj_or_path):
    from pypdf import PdfReader
    if hasattr(file_obj_or_path, "read"):
        reader = PdfReader(io.BytesIO(file_obj_or_path.read()))
    else:
        reader = PdfReader(file_obj_or_path)
    pages = [(p.extract_text() or "") for p in reader.pages]
    return "\n".join(pages), len(pages)


def process_documents(doc_files, doc_names, gl, recon_rows, trail, use_ai=False):
    if not doc_files:
        return None

    texts, total_pages = [], 0
    for f in doc_files:
        try:
            txt, npages = extract_text(f)
            texts.append(txt)
            total_pages += npages
        except Exception as e:
            trail.add("documents", "PDF read failed", details=str(e)[:120])
    full = "\n\n".join(texts)

    journal_ids = (sorted(set(gl["transaction_id"].dropna().astype(str)))
                   if "transaction_id" in gl.columns else [])

    # deterministic: a journal is evidenced if its id appears in the document text
    referenced = sorted({j for j in journal_ids if j and str(j) in full})

    # AI enrichment: structured vouchers (approver, amount, date) for display
    vouchers, method = [], "text-match"
    if use_ai and ai.ai_available() and full.strip():
        v = ai.extract_vouchers(full)
        if v:
            vouchers = v
            method = ai.active_provider() or "ai"
            for vv in vouchers:  # fold any AI-found ids into the referenced set
                jid = str(vv.get("journal_id", "")).strip()
                if jid and jid in journal_ids and jid not in referenced:
                    referenced.append(jid)
            referenced = sorted(set(referenced))

    trail.add("documents", "extracted references from supporting PDF(s)",
              rows_affected=len(referenced), ai_used=(method not in ("text-match",)),
              details=f"{len(doc_files)} doc(s), {total_pages} page(s), method={method}, "
                      f"{len(referenced)}/{len(journal_ids)} journals evidenced")

    # match coverage
    ref = set(referenced)
    supported = [j for j in journal_ids if j in ref]
    unsupported = [j for j in journal_ids if j not in ref]
    coverage = len(supported) / max(len(journal_ids), 1)

    # which unsupported journals touch a reconciliation break (highest risk)
    break_accts = {r["account_code"] for r in recon_rows
                   if r["status"] in ("material_break", "immaterial_break", "gl_only")}
    j2acc = {}
    if "transaction_id" in gl.columns and "account_code" in gl.columns:
        for jid, grp in gl.groupby("transaction_id"):
            j2acc[str(jid)] = set(grp["account_code"].dropna().astype(str))
    unsupported_risky = [j for j in unsupported if break_accts & j2acc.get(j, set())]

    trail.add("documents", "matched supporting docs to ledger journals",
              rows_affected=len(supported),
              details=f"coverage={round(100*coverage)}%, {len(unsupported)} unsupported "
                      f"({len(unsupported_risky)} touching a reconciliation break)")

    return {
        "documents": len(doc_files),
        "document_names": list(doc_names or []),
        "pages": total_pages,
        "method": method,
        "vouchers": vouchers[:40],
        "total_journals": len(journal_ids),
        "coverage_pct": round(coverage, 4),
        "supported_count": len(supported),
        "unsupported_count": len(unsupported),
        "unsupported_journals": unsupported[:60],
        "unsupported_risky_journals": unsupported_risky[:60],
    }
