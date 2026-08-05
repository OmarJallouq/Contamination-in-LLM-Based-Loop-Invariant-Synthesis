"""
run_mutation_study.py — general contamination pipeline for ANY mutation tier.

For each originally-solved program:
  1. Apply the mutation.
  2. SOUNDNESS GATE: verify mutated program still passes with mutated ground-truth.
     Unsound / inapplicable mutations are excluded automatically (per-program).
  3. For valid mutations: measure SOLVE RATE (k of RUNS attempts) on original
     vs mutated. Solve-rate handles borderline programs (inconsistently solvable
     even at temp 0) instead of discarding them — flakiness is program-intrinsic,
     confirmed identical across DeepSeek and GPT, so it's signal, not noise.

The soundness gate guarantees we NEVER test the LLM on a broken program.
"""
import os, json, time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from harness import houdini_at_loop
from llm_arm import get_llm_candidates
from injector import extract_invariants
from config import DAFNY_TIMEOUT, result_path, gt_to_stripped, MODELS, RUNS

from mutate import for_to_while, rename_variables, perturb_constants
MUTATIONS = {
    "rename":  rename_variables,
    "constants": perturb_constants,
    "structure": for_to_while,
}

def get_gt_invariants(gt_path):
    return extract_invariants(open(gt_path, encoding="utf-8", errors="replace").read())

def solve_rate(src, model, runs):
    """Return how many of `runs` attempts solve the program (0..runs)."""
    solved = 0
    for _ in range(runs):
        cands = get_llm_candidates(src, model=model, temperature=0.0)
        if cands and houdini_at_loop(src, 0, cands, timeout=DAFNY_TIMEOUT)["verified"]:
            solved += 1
    return solved

def process_one(args):
    gt_path, model, mutation_name, runs = args
    mutate_fn = MUTATIONS[mutation_name]
    stripped_path = gt_to_stripped(gt_path)
    if not os.path.exists(stripped_path):
        return (gt_path, {"status": "no_stripped"})
    try:
        src = open(stripped_path, encoding="utf-8", errors="replace").read()
        gt_invs = get_gt_invariants(gt_path)
        new_src, new_invs, meta = mutate_fn(src, gt_invs)
        if new_src is None:
            return (gt_path, {"status": "not_applicable"})
        sound = houdini_at_loop(new_src, 0, new_invs, timeout=DAFNY_TIMEOUT)
        if not sound["verified"]:
            return (gt_path, {"status": "mutation_unsound"})

        orig = solve_rate(src, model, runs)
        mutated = solve_rate(new_src, model, runs)
        return (gt_path, {"status": "ok", "orig_solves": orig,
                          "mutated_solves": mutated, "runs": runs, "meta": meta})
    except Exception as e:
        return (gt_path, {"status": "error", "error": str(e)})

def run(model, mutation_name, limit=None, runs=RUNS, max_workers=4, per_program_timeout=300):
    tag = model.replace("/", "_").replace(":", "_")
    llm_results = json.load(open(f"llm_results_{tag}.json"))
    solved = [p.strip() for p in llm_results["results"]["solved"]]
    if limit:
        solved = solved[:limit]

    path = result_path(f"mutation_{mutation_name}", model, limit=limit)

    # --- Resume: load any already-completed results and skip them. ---
    results = {}
    if os.path.exists(path):
        try:
            prior = json.load(open(path))
            results = prior.get("results", {})
            done_paths = set(results.keys())
            solved = [p for p in solved if p not in done_paths]
            print(f"Resuming: {len(results)} already done, {len(solved)} remaining")
        except Exception:
            results = {}

    print(f"Mutation study [{mutation_name}], model={model}, {len(solved)} to run\n")

    def flush():
        statuses = Counter(d["status"] for d in results.values())
        json.dump({"model": model, "mutation": mutation_name, "runs": runs,
                   "results": results, "statuses": dict(statuses)},
                  open(path, "w"), indent=2)

    start = time.time(); done = 0
    with ProcessPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(process_one, (p, model, mutation_name, runs)): p
                   for p in solved}
        for fut in as_completed(futures):
            gt_path = futures[fut]
            try:
                _, detail = fut.result(timeout=per_program_timeout)
            except Exception as e:
                detail = {"status": "error", "error": f"worker: {e}"}
            results[gt_path] = detail
            done += 1
            if done % 5 == 0:
                flush()
                print(f"  {done}/{len(solved)}  ({time.time()-start:.0f}s)")

    flush()

    # --- Analysis: solve-rate comparison ---
    statuses = Counter(d["status"] for d in results.values())
    valid = {p: d for p, d in results.items() if d.get("status") == "ok"}
    n = len(valid)

    if n > 0:
        import statistics as st
        orig_rates = [d["orig_solves"]/d["runs"] for d in valid.values()]
        mut_rates = [d["mutated_solves"]/d["runs"] for d in valid.values()]
        diffs = [o - m for o, m in zip(orig_rates, mut_rates)]
        mean_orig = 100*st.mean(orig_rates)
        mean_mut = 100*st.mean(mut_rates)
        mean_diff = 100*st.mean(diffs)
        sd_diff = 100*st.pstdev(diffs) if n > 1 else 0
        dropped = sum(1 for d in diffs if d > 0.001)
        rose = sum(1 for d in diffs if d < -0.001)
        unchanged = sum(1 for d in diffs if abs(d) <= 0.001)
        borderline = sum(1 for d in valid.values()
                         if 0 < d["orig_solves"] < d["runs"]
                         or 0 < d["mutated_solves"] < d["runs"])
    else:
        mean_orig = mean_mut = mean_diff = sd_diff = 0
        dropped = rose = unchanged = borderline = 0

    print(f"\n{'='*55}")
    print(f"MUTATION STUDY [{mutation_name}] — {model}")
    print(f"{'='*55}")
    print(f"Applicability:")
    print(f"  not applicable:   {statuses['not_applicable']}")
    print(f"  mutation unsound: {statuses['mutation_unsound']}")
    print(f"  valid test cases: {n}")
    print(f"\nSolve rates (mean over {n} programs, {runs} attempts each):")
    print(f"  ORIGINAL: {mean_orig:.1f}%")
    print(f"  MUTATED:  {mean_mut:.1f}%")
    print(f"  DIFFERENCE (orig - mutated): {mean_diff:+.1f}pp  (sd {sd_diff:.1f})")
    print(f"\nPer-program:")
    print(f"  dropped after mutation:    {dropped}   <- contamination signal")
    print(f"  rose after mutation:       {rose}")
    print(f"  unchanged:                 {unchanged}")
    print(f"  borderline (inconsistent): {borderline}")
    print(f"\n  Time: {time.time()-start:.0f}s")
    print(f"  Saved {os.path.basename(path)}")

if __name__ == "__main__":
    import sys
    mutation_name = sys.argv[1] if len(sys.argv) > 1 else "rename"
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else None
    for model in MODELS:
        run(model, mutation_name, limit=limit)