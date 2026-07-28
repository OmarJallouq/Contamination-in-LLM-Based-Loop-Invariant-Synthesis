"""
measure_ceiling.py — establish the corpus CEILING.

For each single-loop program: extract its ground-truth invariant(s), inject them
into the stripped twin, verify. The pass rate is the maximum any method could
achieve, since we're injecting the known-correct answer. Failures reveal missing
assertions, lost lemmas, injector limits, or timeouts — categorized, not hidden.
"""
import os
import re
import json
import time
import tempfile
from harness import verify
from injector import find_loops, inject_at_loop, extract_invariants

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(PROJECT_ROOT, "corpus_manifest.json")

def gt_to_stripped(gt_path):
    p = gt_path.replace("/ground_truth/", "/hints_removed/")
    return p[:-len(".dfy")] + "_no_hints.dfy"

def run():
    with open(MANIFEST) as f:
        records = json.load(f)

    singles = [r for r in records if r["n_loops"] == 1]
    print(f"Single-loop programs to test: {len(singles)}\n")

    results = {"verified": [], "error": [], "timeout": [],
               "no_stripped": [], "inject_failed": [], "no_invariant": []}

    start = time.time()
    for idx, r in enumerate(singles):
        gt_path = r["path"]
        stripped_path = gt_to_stripped(gt_path)

        if not os.path.exists(stripped_path):
            results["no_stripped"].append(gt_path)
            continue

        with open(gt_path, encoding="utf-8", errors="replace") as f:
            gt_source = f.read()
        with open(stripped_path, encoding="utf-8", errors="replace") as f:
            stripped = f.read()

        invs = extract_invariants(gt_source)
        if not invs_present(invs):
            results["no_invariant"].append(gt_path)
            continue

        filled, status = inject_at_loop(stripped, 0, invs)
        if status != "ok":
            results["inject_failed"].append((gt_path, status))
            continue

        with tempfile.NamedTemporaryFile(mode="w", suffix=".dfy",
                                         dir=".", delete=False) as tmp:
            tmp.write(filled)
            tmp_path = tmp.name
        try:
            verdict = verify(tmp_path, timeout=30)
        finally:
            os.remove(tmp_path)

        results[verdict["outcome"]].append(gt_path)

        # Progress ping every 25 programs so we know it's alive.
        if (idx + 1) % 25 == 0:
            elapsed = time.time() - start
            print(f"  {idx+1}/{len(singles)} done "
                  f"({elapsed:.0f}s, {elapsed/(idx+1):.1f}s each)")

    # Summary.
    total = len(singles)
    v = len(results["verified"])
    print(f"\n{'='*50}")
    print(f"CEILING: {v}/{total} = {100*v/total:.1f}% verified")
    print(f"{'='*50}")
    for k in ["error", "timeout", "no_stripped", "inject_failed", "no_invariant"]:
        print(f"  {k:16s}: {len(results[k])}")

    # Save full results for later inspection.
    out = os.path.join(PROJECT_ROOT, "ceiling_results.json")
    with open(out, "w") as f:
        json.dump({k: [str(x) for x in v] for k, v in results.items()},
                  f, indent=2)
    print(f"\nFull results saved to {out}")

def invs_present(invs):
    return len(invs) > 0

if __name__ == "__main__":
    run()