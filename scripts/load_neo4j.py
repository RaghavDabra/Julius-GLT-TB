"""Load a LedgerLens engagement into Neo4j as a property graph.

Models the audit as: (Client)-[:HAS_ACCOUNT]->(Account), (Client)-[:HAS_JOURNAL]->
(Journal)-[:POSTS]->(Account), (Journal)-[:EVIDENCED_BY]->(Document), and
(Journal)-[:NEAR_DUPLICATE]->(Journal). Reconciliation status, variances, balance
and documentation flags are node properties, so breaks, undocumented journals and
duplicate postings are all explorable visually in Neo4j Browser.

All nodes carry an :Audit label + engagement property, so the loader only ever
deletes/replaces its own subgraph and never touches other data in the database.

Run:  python scripts/load_neo4j.py            # defaults to Deloitte
env:  NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "api"))

import warnings
warnings.filterwarnings("ignore")

from neo4j import GraphDatabase

from pipeline import run_pipeline
from pipeline.ingest import read_table, map_headers, apply_mapping
from pipeline.clean import clean_gl
from pipeline.schema import GL_SYNONYMS
from pipeline.audit_trail import AuditTrail

# Defaults target the dedicated LedgerLens Neo4j (http 7475 / bolt 7688).
URI = os.environ.get("NEO4J_URI", "bolt://localhost:7688")
USER = os.environ.get("NEO4J_USER", "neo4j")
PWD = os.environ.get("NEO4J_PASSWORD", "ledgerlens")


def discover_engagements():
    """Deloitte + the synthetic clients (from the generated manifest)."""
    items = []
    delo = os.path.join(ROOT, "data", "deloitte")
    if os.path.exists(os.path.join(delo, "gl.csv")):
        items.append(("Deloitte", os.path.join(delo, "gl.csv"),
                      os.path.join(delo, "tb.csv"), os.path.join(delo, "journals.pdf")))
    manifest = os.path.join(ROOT, "data", "synthetic", "manifest.json")
    if os.path.exists(manifest):
        with open(manifest) as f:
            for c in json.load(f).get("clients", [])[:6]:
                base = os.path.join(ROOT, "data", "synthetic")
                items.append((c["client_name"], os.path.join(base, c["gl_path"]),
                              os.path.join(base, c["tb_path"]), None))
    return items


def load_cleaned_gl(gl_path):
    trail = AuditTrail()
    raw = read_table(gl_path, os.path.basename(gl_path), trail, kind="GL")
    gmap, _, _ = map_headers(list(raw.columns), GL_SYNONYMS, trail, kind="GL")
    return clean_gl(apply_mapping(raw, gmap), trail)


def build_payload(eng, gl_path, tb_path, pdf_path):
    gl = load_cleaned_gl(gl_path)
    docs = [pdf_path] if (pdf_path and os.path.exists(pdf_path)) else None
    result = run_pipeline(gl_path, os.path.basename(gl_path),
                          tb_path, os.path.basename(tb_path),
                          client_id=eng.lower(), client_name=eng, use_ai=False,
                          period_start="2026-01-01", period_end="2026-12-31",
                          doc_files=docs, doc_names=["journals.pdf"] if docs else None)

    accounts = [{
        "code": r["account_code"], "name": r["account_name"], "category": r["category"],
        "gl_balance": r["gl_balance"], "tb_balance": r["tb_balance"],
        "variance": r["variance"], "status": r["status"],
    } for r in result["reconciliation"]]

    sup = result.get("support") or {}
    unsupported = set(sup.get("unsupported_journals", []))
    unbalanced = {u["transaction_id"] for u in result["validation"]["double_entry"]["unbalanced"]}

    postings, jmeta = [], {}
    for _, row in gl.iterrows():
        jid = str(row.get("transaction_id"))
        acct = str(row.get("account_code"))
        amt = float(row["amount"]) if row.get("amount") == row.get("amount") else None
        signed = float(row["signed_amount"]) if row.get("signed_amount") == row.get("signed_amount") else None
        date = row["date"].date().isoformat() if hasattr(row.get("date"), "date") else None
        postings.append({"jid": jid, "acct": acct, "dr_cr": row.get("dr_cr"),
                         "amount": amt, "signed": signed})
        m = jmeta.setdefault(jid, {"date": date, "amount": 0.0})
        if date and not m["date"]:
            m["date"] = date
        if amt:
            m["amount"] = max(m["amount"], amt)

    # duplicate groups + per-journal data-quality flags
    dgroups, dup_kind = [], {}
    for d in result["duplicates"]:
        jids = sorted({str(r.get("transaction_id")) for r in d["rows"] if r.get("transaction_id")})
        dgroups.append({"gid": d["group_id"], "kind": d["kind"],
                        "score": d["score"], "journals": jids})
        for jid in jids:
            dup_kind[jid] = d["kind"]

    journals = [{
        "id": jid, "date": m["date"], "amount": m["amount"],
        "balanced": jid not in unbalanced,
        "supported": (jid not in unsupported) if sup else None,
        "duplicate": jid in dup_kind,
        "dup_kind": dup_kind.get(jid),
    } for jid, m in jmeta.items()]

    near_pairs = []
    for d in result["duplicates"]:
        if d["kind"] == "near":
            ids = sorted({str(r.get("transaction_id")) for r in d["rows"]})
            if len(ids) >= 2:
                near_pairs.append({"a": ids[0], "b": ids[1], "score": d["score"]})

    client = {
        "name": eng, "dq": result["scorecard"]["overall"],
        "materiality": result["kpis"]["materiality"],
        "reconciled_pct": result["kpis"]["reconciled_pct"],
        "doc_coverage": result["kpis"].get("doc_coverage"),
        "dupes_flagged": result["kpis"]["dupes_flagged"],
        "gl_rows": result["kpis"]["gl_rows"], "journals": result["kpis"]["journals"],
    }
    return client, accounts, journals, postings, near_pairs, dgroups, bool(docs)


CYPHER = [
    # wipe only our own subgraph
    ("MATCH (n:Audit {engagement:$eng}) DETACH DELETE n", {}),
    ("MERGE (c:Client:Audit {engagement:$eng}) SET c += $client", "client"),
    ("""UNWIND $accounts AS a
        MERGE (n:Account:Audit {code:a.code, engagement:$eng})
        SET n += a
        WITH n MATCH (c:Client {engagement:$eng}) MERGE (c)-[:HAS_ACCOUNT]->(n)""", "accounts"),
    ("""UNWIND $journals AS j
        MERGE (n:Journal:Audit {id:j.id, engagement:$eng})
        SET n += j
        WITH n MATCH (c:Client {engagement:$eng}) MERGE (c)-[:HAS_JOURNAL]->(n)""", "journals"),
    ("""UNWIND $postings AS p
        MATCH (j:Journal {id:p.jid, engagement:$eng})
        MATCH (a:Account {code:p.acct, engagement:$eng})
        CREATE (j)-[:POSTS {dr_cr:p.dr_cr, amount:p.amount, signed:p.signed}]->(a)""", "postings"),
    ("""UNWIND $near AS d
        MATCH (a:Journal {id:d.a, engagement:$eng})
        MATCH (b:Journal {id:d.b, engagement:$eng})
        MERGE (a)-[:NEAR_DUPLICATE {score:d.score}]->(b)""", "near"),
    ("""UNWIND $dgroups AS g
        MERGE (n:DuplicateGroup:Audit {gid:g.gid, engagement:$eng})
        SET n.kind = g.kind, n.score = g.score
        WITH n, g UNWIND g.journals AS jid
        MATCH (j:Journal {id:jid, engagement:$eng})
        MERGE (n)-[:CONTAINS]->(j)""", "dgroups"),
]


def load_one(s, eng, gl_path, tb_path, pdf_path):
    client, accounts, journals, postings, near, dgroups, has_doc = build_payload(
        eng, gl_path, tb_path, pdf_path)
    params = {"eng": eng, "client": client, "accounts": accounts,
              "journals": journals, "postings": postings, "near": near,
              "dgroups": dgroups}
    for query, _ in CYPHER:
        s.run(query, **params)
    if has_doc:
        s.run("MERGE (d:Document:Audit {name:$eng+' journals.pdf', engagement:$eng})", eng=eng)
        s.run("""MATCH (j:Journal {engagement:$eng}) WHERE j.supported = true
                 MATCH (d:Document {engagement:$eng})
                 MERGE (j)-[:EVIDENCED_BY]->(d)""", eng=eng)
    n = s.run("MATCH (x:Audit {engagement:$eng}) RETURN count(x) AS c", eng=eng).single()["c"]
    return n


def main():
    engagements = discover_engagements()
    driver = GraphDatabase.driver(URI, auth=(USER, PWD))
    with driver.session() as s:
        s.run("MATCH (n:Audit) DETACH DELETE n")  # fresh load on the dedicated instance
        loaded = []
        for eng, gl, tb, pdf in engagements:
            try:
                n = load_one(s, eng, gl, tb, pdf)
                loaded.append((eng, n))
                print(f"  loaded {eng}: {n} nodes")
            except Exception as e:
                print(f"  FAILED {eng}: {e}")
        totals = s.run("""MATCH (n:Audit) RETURN labels(n)[0] AS label, count(*) AS n
            ORDER BY label""").data()
        rels = s.run("MATCH (:Audit)-[r]->(:Audit) RETURN type(r) AS rel, count(*) AS n "
                     "ORDER BY rel").data()
    driver.close()

    print(f"\nLoaded {len(loaded)} engagement(s) into {URI}")
    print("Node labels:", {c["label"]: c["n"] for c in totals})
    print("Relationships:", {r["rel"]: r["n"] for r in rels})
    print("\nOpen Neo4j Browser at http://localhost:7475  (user neo4j / pass ledgerlens) and try:")
    print("  // DATA QUALITY - duplicates (group nodes -> the duplicated journals)")
    print("  MATCH (g:DuplicateGroup)-[:CONTAINS]->(j:Journal) RETURN g, j;")
    print("  // the duplicated journals and the accounts they hit")
    print("  MATCH (g:DuplicateGroup)-[:CONTAINS]->(j:Journal)-[:POSTS]->(a:Account) RETURN g,j,a;")
    print("  // other data-quality issues")
    print("  MATCH (j:Journal {balanced:false}) RETURN j;          // unbalanced journals")
    print("  MATCH (j:Journal {supported:false})-[:POSTS]->(a) RETURN j,a;  // undocumented")
    print("  MATCH (n) RETURN n;                                   // EVERYTHING")


if __name__ == "__main__":
    main()
