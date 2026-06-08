"""Canonical schema + synonym dictionaries for GL / TB ingestion.

The mapping from a client's heterogeneous column headers to our canonical schema
is the first place data variability bites. We keep the synonym dictionaries here,
version-controlled and human-readable, so every mapping decision is auditable and
reproducible. AI is only ever consulted for headers these deterministic rules
cannot resolve (see ``ingest.map_headers``).
"""

import re

# --- Canonical column names ------------------------------------------------

# General Ledger (transaction level)
CANONICAL_GL = [
    "transaction_id",
    "date",
    "account_code",
    "account_name",
    "dr_cr",
    "amount",
    "signed_amount",  # derived in clean.py: +amount for DR, -amount for CR
    "description",
]

# Trial Balance (account level)
CANONICAL_TB = [
    "account_code",
    "account_name",
    "balance",
]

# Fields that must be present for a usable GL / TB.
REQUIRED_GL = ["account_code", "amount"]
REQUIRED_TB = ["account_code", "balance"]


# --- Synonym dictionaries --------------------------------------------------
# Keys are canonical names; values are the raw header variants we have seen
# across ERP exports (SAP, Oracle, Xero, QuickBooks, MYOB, hand-rolled CSVs).

GL_SYNONYMS = {
    "transaction_id": [
        "trans_id", "txn_id", "transaction_id", "journal_id", "je_id",
        "entry_id", "voucher", "voucher_no", "ref", "reference", "doc_no",
        "document_number", "journalentry",
    ],
    "date": [
        "date", "posting_date", "trans_date", "transaction_date", "entry_date",
        "gl_date", "effective_date", "doc_date", "value_date", "posted",
    ],
    "account_code": [
        "acct_code", "account_id", "account_code", "gl_account", "gl_acct",
        "account", "acctno", "acct_no", "account_no", "accountnumber",
        "account_number", "ledger_account", "gl_code", "nominal_code",
    ],
    "account_name": [
        "account_name", "acct_name", "gl_name", "ledger_name", "accountdesc",
        "account_description", "nominal_name", "account_title",
    ],
    "dr_cr": [
        "dr_cr", "drcr", "type", "debit_credit", "posting_type", "indicator",
        "dc", "dc_indicator", "side", "entry_type",
    ],
    "amount": [
        "amt", "amount", "value", "amount_lcy", "local_amount", "trans_amt",
        "transaction_amount", "posting_amount", "gross_amount", "line_amount",
    ],
    "description": [
        "desc", "description", "narrative", "memo", "details", "particulars",
        "line_description", "comment", "remarks", "text",
    ],
}

TB_SYNONYMS = {
    "account_code": [
        "account_id", "acct_code", "account_code", "gl_account", "account",
        "acctno", "acct_no", "account_no", "accountnumber", "account_number",
        "ledger_account", "gl_code", "nominal_code",
    ],
    "account_name": [
        "account_name", "acct_name", "gl_name", "ledger_name", "accountdesc",
        "account_description", "nominal_name", "account_title", "name",
    ],
    "balance": [
        "final_balance", "closing_balance", "balance", "ending_balance",
        "amount", "ytd_balance", "net_balance", "tb_balance", "period_balance",
        "closing_bal", "end_balance",
    ],
}


def normalize_header(header: str) -> str:
    """Lower-case, strip, and remove non-alphanumeric characters.

    "GL Account #" -> "glaccount", "Posting_Date" -> "postingdate".
    Used to make synonym matching robust to spacing / punctuation / case.
    """
    if header is None:
        return ""
    return re.sub(r"[^a-z0-9]", "", str(header).strip().lower())


def build_lookup(synonyms: dict) -> dict:
    """Flatten a synonym dict into {normalized_variant: canonical_name}."""
    lookup = {}
    for canonical, variants in synonyms.items():
        # the canonical name itself is always a valid variant
        for variant in [canonical] + list(variants):
            lookup[normalize_header(variant)] = canonical
    return lookup


def all_variants(synonyms: dict) -> list:
    """Return the flat list of normalized variants (for fuzzy matching)."""
    return list(build_lookup(synonyms).keys())
