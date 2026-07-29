"""
run_llm_parallel.py — LLM arm across the corpus, parallelized.
Paid model (no 20/min free cap), so we run several programs concurrently.
Each worker: API call -> Houdini -> verdict. Independent, so process-parallel.
"""
import os, json, time
from concurrent.futures import ProcessPoolExecutor, as_completed
from llm_arm import get_llm_candidates, DEFAULT_MODEL
from harness import houdini_at_loop

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
CEILING = os.path.join(PROJECT_ROOT, "ceiling_results.json")

def gt_to_stripped(p):
    return p.replace("/ground_truth/", "/hints_removed/")[:-4] + "_no_hints.dfy"

def process_one(args):
    gt_path, model = args
    sp = gt_to_stripped(gt_path)
    if not os.path.exists(sp):
        return (gt_path, "error", {})
    try:
        src = open(sp, encoding="utf-8", errors="replace").read()
        cands = get_llm_candidates(src, model=model)
        if not cands:
            return (gt_path, "no_candidates", {"candidates": [], "survivors": []})
        r = houdini_at_loop(src, 0, cands, timeout=30)
        outcome = "solved" if r["verified"] else "failed"
        return (gt_path, outcome,
                {"candidates": cands, "survivors": r["invariant"], "verified": r["verified"]})
    except Exception as e:
        return (gt_path, "error", {"error": str(e)})

def run(model=DEFAULT_MODEL, max_workers=8, limit=None):
    ceiling = json.load(open(CEILING))
    scoped = [p.strip() for p in ceiling["verified"]]
    if limit:
        scoped = scoped[:limit]
    print(f"LLM arm (parallel): {len(scoped)} programs, model={model}, {max_workers} workers\n")

    results = {"solved": [], "failed": [], "no_candidates": [], "error": []}
    details = {}
    start = time.time(); done = 0

    with ProcessPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(process_one, (p, model)): p for p in scoped}

        for fut in as_completed(futures):
            gt_path, outcome, detail = fut.result()
            results[outcome].append(gt_path if outcome != "error"
                                     else f"{gt_path} :: {detail.get('error','')}")
            details[gt_path] = detail
            done += 1
            el = time.time() - start
            rate = el / done
            eta = rate * (len(scoped) - done)
            solved = len(results["solved"])
            pct = 100 * solved / done
            mark = {"solved": "OK ", "failed": "no ",
                    "no_candidates": "-- ", "error": "ERR"}.get(outcome, "?  ")
            name = os.path.basename(gt_path)[:45]
            print(f"  [{done:3d}/{len(scoped)}] {mark} "
                  f"solved {solved} ({pct:.0f}%)  "
                  f"{el:.0f}s elapsed, ~{eta:.0f}s left   {name}")

    total = len(scoped); s = len(results["solved"])
    print(f"\n{'='*50}")
    print(f"LLM ({model}): {s}/{total} = {100*s/total:.1f}% solved  in {time.time()-start:.0f}s")
    print(f"{'='*50}")
    for k in ["failed", "no_candidates", "error"]:
        print(f"  {k}: {len(results[k])}")

    tag = model.replace("/", "_").replace(":", "_")
    json.dump({"model": model, "results": results, "details": details},
              open(os.path.join(PROJECT_ROOT, f"llm_results_{tag}.json"), "w"), indent=2)
    print(f"\nSaved llm_results_{tag}.json")

if __name__ == "__main__":
    import sys
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    run(limit=limit)