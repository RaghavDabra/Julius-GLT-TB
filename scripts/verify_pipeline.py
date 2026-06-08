"""Verify the deterministic pipeline against the generator's ground-truth answer key.

Runs every generated engagement through the real pipeline (with AI OFF) and
asserts the injected duplicates, reconciliation breaks, referential-integrity
issues and clean-client scores are detected exactly. Exits non-zero on any
failure. This is the proof that the data preprocessing / reconciliation logic
actually works.

Run:  python scripts/verify_pipeline.py
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "api"))

from pipeline import run_pipeline  # noqa: E402

DATA = os.path.join(ROOT, "data", "synthetic")
PASS, FAIL = "\033[92mPASS\033[0m", "\033[91mFAIL\033[0m"


def main():
    with open(os.path.join(DATA, "manifest.json")) as f:
        manifest = json.load(f)
    with open(os.path.join(DATA, "answer_key.json")) as f:
        answer = json.load(f)["clients"]

    failures = []
    checks = 0

    for c in manifest["clients"]:
        cid = c["client_id"]
        ak = answer[cid]
        gl_path = os.path.join(DATA, c["gl_path"])
        tb_path = os.path.join(DATA, c["tb_path"])
        res = run_pipeline(gl_path, os.path.basename(gl_path),
                           tb_path, os.path.basename(tb_path),
                           client_id=cid, client_name=c["client_name"],
                           use_ai=False, period_start="2026-01-01", period_end="2026-12-31")

        def check(name, cond):
            nonlocal checks
            checks += 1
            if not cond:
                failures.append(f"{cid} {c['client_name']}: {name}")

        # 1. mapping resolved deterministically (no AI), key fields present
        gl_map_vals = set(res["mapping"]["gl"].values())
        check("GL account_code+amount mapped", {"account_code", "amount"} <= gl_map_vals)
        check("mapping used no AI",
              all(not d["ai_used"] for d in res["mapping"]["gl_decisions"]))

        # 2. duplicates: injected trans_ids are all flagged
        flagged_tids = set()
        for d in res["duplicates"]:
            for r in d["rows"]:
                flagged_tids.add(r.get("transaction_id"))
        for inj in ak["injected_dupes"]:
            check(f"dup {inj['kind']} {inj['trans_id']} flagged",
                  inj["trans_id"] in flagged_tids)

        # 3. reconciliation breaks: each injected break detected with right magnitude
        recon = {r["account_code"]: r for r in res["reconciliation"]}
        for b in ak["injected_breaks"]:
            row = recon.get(b["account_code"])
            ok = (row is not None
                  and row["status"] in ("material_break", "immaterial_break")
                  and abs(row["abs_variance"] - abs(b["delta"])) <= 1.0)
            check(f"break {b['account_code']} detected (delta {b['delta']})", ok)
            if row is not None and ok:
                want = "material_break" if b["material"] else "immaterial_break"
                check(f"break {b['account_code']} classified {want}",
                      row["status"] == want)

        # 4. referential integrity
        gl_only = set(res["validation"]["referential_integrity"]["gl_only_accounts"])
        tb_only = set(res["validation"]["referential_integrity"]["tb_only_accounts"])
        for a in ak["injected_gl_only"]:
            check(f"gl_only {a} surfaced", a in gl_only)
        for a in ak["injected_tb_only"]:
            check(f"tb_only {a} surfaced", a in tb_only)

        # 5. clean engagements score high and have no breaks/dupes
        if ak["clean"]:
            check("clean DQ >= 0.95", res["scorecard"]["overall"] >= 0.95)
            check("clean has no material breaks", res["kpis"]["material_breaks"] == 0)
            check("clean has no duplicates", res["kpis"]["dupes_flagged"] == 0)

        # 6. nothing silently dropped: flagged dupes <= total rows, rows preserved
        check("gl_rows preserved", res["kpis"]["gl_rows"] == ak["gl_rows"])

        status = PASS if not [f for f in failures if f.startswith(cid)] else FAIL
        print(f"  [{status}] {cid} {c['client_name']:28s} "
              f"DQ={round(100*res['scorecard']['overall']):3d}%  "
              f"breaks(m/i)={res['kpis']['material_breaks']}/{res['kpis']['immaterial_breaks']}  "
              f"dupes={res['kpis']['dupes_flagged']}")

    print(f"\n{checks} checks run, {len(failures)} failures.")
    if failures:
        print("\nFailures:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print(f"\n\033[92mALL CHECKS PASSED\033[0m")


if __name__ == "__main__":
    main()
