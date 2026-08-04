"""
run_mutation_study.py — general contamination pipeline for ANY mutation tier.

Takes a mutation function `(source, gt_invariants) -> (new_source, new_invs, meta)`.
For each originally-solved program:
  1. Apply the mutation.
  2. SOUNDNESS GATE: verify mutated program still passes with mutated ground-truth.
     Unsound / inapplicable mutations are excluded automatically (per-program).
  3. For valid mutations only: test the LLM on original vs mutated, 2x-confirmed.

This is uniform across all tiers — the gate guarantees we NEVER test the LLM on
a broken program, regardless of which mutation is used.
"""
import os, json, time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from harness import houdini_at_loop
from llm_arm import get_llm_candidates
from injector import extract_invariants
from config import DAFNY_TIMEOUT, result_path, gt_to_stripped, MODELS, RUNS

# --- The mutation registry: name -> function -----------------------------------
from mutate import for_to_while, rename_variables, perturb_constants
MUTATIONS = {
    "rename":  rename_variables,
    "constants": perturb_constants,
    "structure": for_to_while,
    # "structure": restructure,   # Tier 3, added later
}

def get_gt_invariants(gt_path):
    return extract_invariants(open(gt_path, encoding="utf-8", errors="replace").read())

def solve_confirmed(src, model, runs=RUNS):
    outcomes = []
    for _ in range(runs):
        cands = get_llm_candidates(src, model=model, temperature=0.0)
        solved = bool(cands) and houdini_at_loop(src, 0, cands, timeout=DAFNY_TIMEOUT)["verified"]
        outcomes.append(solved)
    if all(outcomes): return "yes"
    if not any(outcomes): return "no"
    return "flaky"

def process_one(args):
    gt_path, model, mutation_name, runs = args
    mutate_fn = MUTATIONS[mutation_name]
    stripped_path = gt_to_stripped(gt_path)
    if not os.path.exists(stripped_path):
        return (gt_path, {"status": "no_stripped"})
    try:
        src = open(stripped_path, encoding="utf-8", errors="replace").read()
        gt_invs = get_gt_invariants(gt_path)

        # Apply mutation.
        new_src, new_invs, meta = mutate_fn(src, gt_invs)
        if new_src is None:
            return (gt_path, {"status": "not_applicable"})   # e.g. no constants

        # SOUNDNESS GATE — the guarantee that we only test valid mutations.
        sound = houdini_at_loop(new_src, 0, new_invs, timeout=DAFNY_TIMEOUT)
        if not sound["verified"]:
            return (gt_path, {"status": "mutation_unsound"})

        # Valid test case: original vs mutated, confirmed.
        orig = solve_confirmed(src, model, runs)
        mutated = solve_confirmed(new_src, model, runs)

        if orig == "flaky" or mutated == "flaky":
            effect = "flaky"
        elif orig == "yes" and mutated == "yes":
            effect = "robust"
        elif orig == "yes" and mutated == "no":
            effect = "hurt"
        elif orig == "no" and mutated == "yes":
            effect = "helped"
        else:
            effect = "both_failed"

        return (gt_path, {"status": "ok", "effect": effect,
                          "orig": orig, "mutated": mutated, "meta": meta})
    except Exception as e:
        return (gt_path, {"status": "error", "error": str(e)})

def run(model, mutation_name, limit=None, runs=RUNS, max_workers=4):
    tag = model.replace("/", "_").replace(":", "_")
    llm_results = json.load(open(f"llm_results_{tag}.json"))
    solved = [p.strip() for p in llm_results["results"]["solved"]]
    if limit:
        solved = solved[:limit]

    print(f"Mutation study [{mutation_name}], model={model}, {len(solved)} programs\n")

    results = {}
    start = time.time(); done = 0
    with ProcessPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(process_one, (p, model, mutation_name, runs)): p
                   for p in solved}
        for fut in as_completed(futures):
            gt_path, detail = fut.result()
            results[gt_path] = detail
            done += 1
            if done % 10 == 0:
                print(f"  {done}/{len(solved)}  ({time.time()-start:.0f}s)")

    # --- Analysis ---
    statuses = Counter(d["status"] for d in results.values())
    valid = {p: d for p, d in results.items() if d.get("status") == "ok"}
    effects = Counter(d["effect"] for d in valid.values())
    n = len(valid)

    print(f"\n{'='*55}")
    print(f"MUTATION STUDY [{mutation_name}] — {model}")
    print(f"{'='*55}")
    print(f"Applicability:")
    print(f"  not applicable:    {statuses['not_applicable']}")
    print(f"  mutation unsound:  {statuses['mutation_unsound']}")
    print(f"  valid test cases:  {n}")
    print(f"\nEffects (on {n} valid programs):")
    print(f"  robust:      {effects['robust']}")
    print(f"  hurt:        {effects['hurt']}   <- memorization signal")
    print(f"  helped:      {effects['helped']}")
    print(f"  both_failed: {effects['both_failed']}")
    print(f"  FLAKY:       {effects['flaky']}   <- {model} noise")

    hurt, helped = effects['hurt'], effects['helped']
    if hurt + helped > 0:
        chi2 = (abs(hurt - helped) - 1)**2 / (hurt + helped)
        sig = "SIGNIFICANT" if chi2 > 3.84 else "not significant"
        print(f"\n  McNemar (hurt vs helped): chi2={chi2:.2f} ({sig})")

    print(f"\n  Time: {time.time()-start:.0f}s")

    path = result_path(f"mutation_{mutation_name}", model, limit=limit)
    json.dump({"model": model, "mutation": mutation_name, "runs": runs,
               "results": results, "statuses": dict(statuses),
               "effects": dict(effects), "n_valid": n},
              open(path, "w"), indent=2)
    print(f"  Saved {os.path.basename(path)}")

if __name__ == "__main__":
    import sys
    mutation_name = sys.argv[1] if len(sys.argv) > 1 else "rename"
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else None
    for model in MODELS:
        run(model, mutation_name, limit=limit)