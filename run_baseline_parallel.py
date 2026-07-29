"""
run_baseline_parallel.py — same classical baseline, run across CPU cores.
Each program is independent, so we distribute them over a process pool.
"""
import os, json, time
from concurrent.futures import ProcessPoolExecutor, as_completed
from templates import generate_all_templates
from harness import houdini_at_loop

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
CEILING = os.path.join(PROJECT_ROOT, "ceiling_results.json")

def gt_to_stripped(p):
    return p.replace("/ground_truth/", "/hints_removed/")[:-4] + "_no_hints.dfy"

def process_one(gt_path):
    """Run the baseline on a single program. Must be top-level (picklable)
    so worker processes can call it. Returns (gt_path, outcome)."""
    stripped_path = gt_to_stripped(gt_path)
    if not os.path.exists(stripped_path):
        return (gt_path, "no_stripped")
    try:
        src = open(stripped_path, encoding="utf-8", errors="replace").read()
        pool = generate_all_templates(src, 0)
        result = houdini_at_loop(src, 0, pool, timeout=30)
        return (gt_path, "solved" if result["verified"] else "failed")
    except Exception as e:
        return (gt_path, f"error:{e}")

def run(max_workers=6):
    ceiling = json.load(open(CEILING))
    scoped = [p.strip() for p in ceiling["verified"]]
    print(f"Scoped corpus: {len(scoped)} programs, {max_workers} workers\n")

    results = {"solved": [], "failed": [], "no_stripped": [], "error": []}
    start = time.time()
    done = 0

    with ProcessPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(process_one, p): p for p in scoped}
        for fut in as_completed(futures):
            gt_path, outcome = fut.result()
            key = outcome if outcome in results else "error"
            results[key].append(gt_path if key != "error" else f"{gt_path} :: {outcome}")
            done += 1
            if done % 20 == 0:
                el = time.time() - start
                print(f"  {done}/{len(scoped)}  ({el:.0f}s)  solved: {len(results['solved'])}")

    total = len(scoped)
    s = len(results["solved"])
    print(f"\n{'='*50}")
    print(f"BASELINE: {s}/{total} = {100*s/total:.1f}% solved  in {time.time()-start:.0f}s")
    print(f"{'='*50}")
    for k in ["failed", "no_stripped", "error"]:
        print(f"  {k}: {len(results[k])}")

    json.dump(results, open(os.path.join(PROJECT_ROOT, "baseline_results.json"), "w"),
              indent=2)
    print("\nSaved baseline_results.json")

if __name__ == "__main__":
    run(max_workers=6)