"""
run_baseline.py — the classical baseline across the scoped corpus.

For each scoped program (verifiable by ground-truth invariants): generate the
linear template pool, filter with Houdini, record whether it verifies. This is
the number every other method is measured against.
"""
import os, json, time
from templates import generate_templates
from harness import houdini_at_loop

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
CEILING = os.path.join(PROJECT_ROOT, "ceiling_results.json")

def gt_to_stripped(p):
    return p.replace("/ground_truth/", "/hints_removed/")[:-4] + "_no_hints.dfy"

def run():
    # Scoped corpus = the programs that verified with ground-truth invariants.
    ceiling = json.load(open(CEILING))
    scoped = [p.strip() for p in ceiling["verified"]]
    print(f"Scoped corpus: {len(scoped)} programs\n")

    solved, failed, errored = [], [], []
    start = time.time()
    for idx, gt_path in enumerate(scoped):
        stripped_path = gt_to_stripped(gt_path)
        if not os.path.exists(stripped_path):
            errored.append(gt_path); continue
        stripped = open(stripped_path, encoding="utf-8", errors="replace").read()

        try:
            pool = generate_templates(stripped)
            result = houdini_at_loop(stripped, 0, pool, timeout=30)
            (solved if result["verified"] else failed).append(gt_path)
        except Exception as e:
            errored.append((gt_path, str(e)))

        if (idx + 1) % 20 == 0:
            el = time.time() - start
            print(f"  {idx+1}/{len(scoped)}  ({el:.0f}s)  solved so far: {len(solved)}")

    total = len(scoped)
    print(f"\n{'='*50}")
    print(f"BASELINE: {len(solved)}/{total} = {100*len(solved)/total:.1f}% solved")
    print(f"{'='*50}")
    print(f"  failed:  {len(failed)}")
    print(f"  errored: {len(errored)}")

    json.dump({"solved": solved, "failed": failed,
               "errored": [str(e) for e in errored]},
              open(os.path.join(PROJECT_ROOT, "baseline_results.json"), "w"), indent=2)
    print("\nSaved baseline_results.json")

if __name__ == "__main__":
    run()