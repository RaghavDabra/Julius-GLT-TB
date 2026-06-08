"""Stage 1 - Ingestion & schema mapping.

Reads a client's raw GL/TB file (whatever encoding / delimiter / format it
arrived in) and maps its heterogeneous headers onto our canonical schema. The
mapping is deterministic-first:

    1. exact synonym hit          (confidence 1.0,  method "exact_synonym")
    2. fuzzy match via difflib    (confidence=ratio, method "fuzzy_difflib")
    3. Gemini suggestion          (only for the residue, flagged needs_review)

AI never overrides a deterministic match, and every decision is written to the
audit trail so the mapping can be reproduced and explained.
"""

import csv
import difflib
import io
import os

import pandas as pd

from .schema import (
    build_lookup,
    all_variants,
    normalize_header,
)

FUZZY_CUTOFF = 0.82


# --- File reading ----------------------------------------------------------

def _read_bytes(file_obj_or_path):
    if hasattr(file_obj_or_path, "read"):
        data = file_obj_or_path.read()
        if isinstance(data, str):
            data = data.encode("utf-8")
        return data
    with open(file_obj_or_path, "rb") as f:
        return f.read()


def _detect_encoding(raw_bytes):
    for enc in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            raw_bytes.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    return "latin-1"  # latin-1 can decode any byte sequence


def _detect_delimiter(text):
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        return dialect.delimiter
    except Exception:
        return ","


def read_table(file_obj_or_path, filename, trail, kind="GL"):
    """Read a CSV or XLSX into a raw DataFrame, recording how it was read."""
    raw_bytes = _read_bytes(file_obj_or_path)
    name = (filename or "").lower()

    if name.endswith((".xlsx", ".xls")):
        try:
            df = pd.read_excel(io.BytesIO(raw_bytes), dtype=str)
            trail.add("ingest", f"read {kind} xlsx", rows_affected=len(df),
                      details=f"{filename} via openpyxl engine")
            return df
        except ImportError as e:
            raise RuntimeError(
                "Reading .xlsx requires openpyxl (pip install openpyxl)."
            ) from e

    encoding = _detect_encoding(raw_bytes)
    text = raw_bytes.decode(encoding)
    delimiter = _detect_delimiter(text)
    df = pd.read_csv(io.StringIO(text), delimiter=delimiter, dtype=str)
    trail.add(
        "ingest", f"read {kind} csv", rows_affected=len(df),
        details=f"{filename} encoding={encoding} delimiter={repr(delimiter)}",
        outputs={"columns": list(df.columns)},
    )
    return df


# --- Header mapping --------------------------------------------------------

def map_headers(headers, synonyms, trail, kind="GL", ai_suggest=None):
    """Map raw headers -> canonical names.

    ``ai_suggest`` is an optional callable (raw_headers, targets) -> {raw: canon}
    used only for headers the deterministic layer cannot resolve.
    Returns (mapping, unmatched, decisions).
    """
    lookup = build_lookup(synonyms)
    variants = all_variants(synonyms)
    canonical_targets = list(synonyms.keys())

    mapping = {}
    decisions = []
    unmatched = []
    used_canon = set()

    for raw in headers:
        norm = normalize_header(raw)
        # 1. exact synonym
        if norm in lookup and lookup[norm] not in used_canon:
            canon = lookup[norm]
            mapping[raw] = canon
            used_canon.add(canon)
            decisions.append({"raw": raw, "canonical": canon, "method": "exact_synonym",
                              "confidence": 1.0, "ai_used": False, "needs_review": False})
            continue
        # 2. fuzzy
        match = difflib.get_close_matches(norm, variants, n=1, cutoff=FUZZY_CUTOFF)
        if match:
            canon = lookup[match[0]]
            if canon not in used_canon:
                ratio = difflib.SequenceMatcher(None, norm, match[0]).ratio()
                mapping[raw] = canon
                used_canon.add(canon)
                decisions.append({"raw": raw, "canonical": canon, "method": "fuzzy_difflib",
                                  "confidence": round(ratio, 3), "ai_used": False,
                                  "needs_review": ratio < 0.9})
                continue
        unmatched.append(raw)

    # 3. AI only for the residue
    ai_used_any = False
    if unmatched and ai_suggest is not None:
        missing_targets = [t for t in canonical_targets if t not in used_canon]
        try:
            suggestions = ai_suggest(unmatched, missing_targets) or {}
        except Exception:
            suggestions = {}
        for raw in list(unmatched):
            canon = suggestions.get(raw)
            if canon and canon in missing_targets and canon not in used_canon:
                mapping[raw] = canon
                used_canon.add(canon)
                ai_used_any = True
                decisions.append({"raw": raw, "canonical": canon, "method": "ai_suggested",
                                  "confidence": 0.6, "ai_used": True, "needs_review": True})
                unmatched.remove(raw)

    for raw in unmatched:
        decisions.append({"raw": raw, "canonical": None, "method": "unmapped",
                          "confidence": 0.0, "ai_used": False, "needs_review": True})

    trail.add(
        "ingest", f"map {kind} headers",
        rows_affected=len(headers), ai_used=ai_used_any,
        details=f"{len(mapping)}/{len(headers)} headers mapped; {len(unmatched)} unmapped",
        outputs={"mapping": mapping, "decisions": decisions},
    )
    return mapping, unmatched, decisions


def apply_mapping(df, mapping):
    """Rename mapped columns to canonical names and keep only those."""
    renamed = df.rename(columns=mapping)
    keep = [c for c in renamed.columns if c in set(mapping.values())]
    # if duplicate canonical targets appear, keep the first occurrence
    seen = set()
    cols = []
    for c in keep:
        if c not in seen:
            cols.append(c)
            seen.add(c)
    return renamed[cols].copy()
