"""
run_contamination.py — Tier 1 contamination study, paired + 2x-confirmed.

For each originally-solved program, tests ORIGINAL vs RENAMED, running each
condition twice (temp 0) and only trusting CONSISTENT outcomes. Flaky programs
(inconsistent within a condition) are counted separately as the model's noise
level, not as a renaming effect. Model-agnostic: iterates config.MODELS.
"""
import os, json, time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from mutate import rename_variables
from llm_arm import get_llm_candidates
from harness import houdini_at_loop
from injector import extract_invariants
from config import MAX_WORKERS, DAFNY_TIMEOUT, result_path, gt_to_stripped, MODELS

RUNS = 2  # runs per condition, to confirm consistency vs. flakiness

def get_gt_invariants(gt_path):
    return extract_invariants(open(gt_path, encoding="utf-8", errors="replace").read())

def solve_confirmed(src, model, runs=RUNS):
    """Run the LLM `runs` times. 'yes'=all solved, 'no'=none, 'flaky'=mixed."""
    outcomes = []
    for _ in range(runs):
        cands = get_llm_candidates(src, model=model, temperature=0.0)
        solved = False
        if cands:
            r = houdini_at_loop(src, 0, cands, timeout=DAFNY_TIMEOUT)
            solved = r["verified"]
        outcomes.append(solved)
    if all(outcomes):
        return "yes"
    if not any(outcomes):
        return "no"
    return "flaky"

def process_one(args):
    gt_path, model, runs = args
    stripped_path = gt_to_stripped(gt_path)
    if not os.path.exists(stripped_path):
        return (gt_path, {"status": "no_stripped"})
    try:
        src = open(stripped_path, encoding="utf-8", errors="replace").read()
        gt_invs = get_gt_invariants(gt_path)
        new_src, new_invs, mapping = rename_variables(src, gt_invs)
        if new_src is None:
            return (gt_path, {"status": "no_variables"})
        sound = houdini_at_loop(new_src, 0, new_invs, timeout=DAFNY_TIMEOUT)
        if not sound["verified"]:
            return (gt_path, {"status": "mutation_unsound"})

        orig = solve_confirmed(src, model, runs)
        renamed = solve_confirmed(new_src, model, runs)

        if orig == "flaky" or renamed == "flaky":
            effect = "flaky"
        elif orig == "yes" and renamed == "yes":
            effect = "robust"
        elif orig == "yes" and renamed == "no":
            effect = "hurt"
        elif orig == "no" and renamed == "yes":
            effect = "helped"
        else:
            effect = "both_failed"

        return (gt_path, {"status": "ok", "effect": effect,
                          "orig": orig, "renamed": renamed, "mapping": mapping})
    except Exception as e:
        return (gt_path, {"status": "error", "error": str(e)})

def run(model, limit=None, runs=RUNS, max_workers=4):
    tag = model.replace("/", "_").replace(":", "_")
    llm_results = json.load(open(f"llm_results_{tag}.json"))
    solved = [p.strip() for p in llm_results["results"]["solved"]]
    if limit:
        solved = solved[:limit]

    print(f"Contamination (rename, {runs}x-confirmed), model={model}")
    print(f"{len(solved)} programs, ~{len(solved)*2*runs} LLM calls\n")

    results = {}
    start = time.time(); done = 0
    with ProcessPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(process_one, (p, model, runs)): p for p in solved}
        for fut in as_completed(futures):
            gt_path, detail = fut.result()
            results[gt_path] = detail
            done += 1
            if done % 10 == 0:
                print(f"  {done}/{len(solved)}  ({time.time()-start:.0f}s)")

    valid = {p: d for p, d in results.items() if d.get("status") == "ok"}
    effects = Counter(d["effect"] for d in valid.values())
    n = len(valid)

    print(f"\n{'='*55}")
    print(f"CONTAMINATION (rename, {runs}x-confirmed) — {model}, n={n}")
    print(f"{'='*55}")
    print(f"  robust (solved both ways):     {effects['robust']}")
    print(f"  hurt (orig yes, renamed no):   {effects['hurt']}   <- memorization signal")
    print(f"  helped (orig no, renamed yes): {effects['helped']}")
    print(f"  both_failed:                   {effects['both_failed']}")
    print(f"  FLAKY (nondeterministic):      {effects['flaky']}   <- {model} noise level")

    hurt, helped = effects['hurt'], effects['helped']
    if hurt + helped > 0:
        chi2 = (abs(hurt - helped) - 1)**2 / (hurt + helped)
        sig = "significant asymmetry" if chi2 > 3.84 else "no significant asymmetry"
        print(f"\n  McNemar (hurt vs helped): chi2={chi2:.2f}  ({sig})")

    print(f"\n  Total time: {time.time()-start:.0f}s")

    path = result_path("contamination_rename2x", model, limit=limit)
    json.dump({"model": model, "runs": runs, "results": results,
               "effects": dict(effects), "n": n},
              open(path, "w"), indent=2)
    print(f"  Saved {os.path.basename(path)}")

if __name__ == "__main__":
    import sys
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    for model in MODELS:
        run(model, limit=limit)