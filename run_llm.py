"""
run_llm.py — the LLM arm across the scoped corpus.

For each program: ask the LLM for candidate invariants, filter with the same
Houdini as the baseline, record whether it verifies. Rate-limited for the free
tier (20 req/min). Saves per-program results including the candidate pool.
"""
import os, json, time
from llm_arm import get_llm_candidates, DEFAULT_MODEL
from harness import houdini_at_loop

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
CEILING = os.path.join(PROJECT_ROOT, "ceiling_results.json")

# Free tier: 20 req/min -> min 3s between calls. Use 3.5s for safety margin.
MIN_INTERVAL = 0.2

def gt_to_stripped(p):
    return p.replace("/ground_truth/", "/hints_removed/")[:-4] + "_no_hints.dfy"

def run(model=DEFAULT_MODEL, limit=None):
    ceiling = json.load(open(CEILING))
    scoped = [p.strip() for p in ceiling["verified"]]
    if limit:
        scoped = scoped[:limit]
    print(f"LLM arm: {len(scoped)} programs, model={model}\n")

    results = {"solved": [], "failed": [], "no_candidates": [], "error": []}
    details = {}   # per-program: candidates + survivors, for later analysis
    start = time.time()
    last_call = 0

    for idx, gt_path in enumerate(scoped):
        stripped_path = gt_to_stripped(gt_path)
        if not os.path.exists(stripped_path):
            results["error"].append(gt_path); continue
        src = open(stripped_path, encoding="utf-8", errors="replace").read()

        # Rate limit: ensure MIN_INTERVAL since last API call.
        gap = time.time() - last_call
        if gap < MIN_INTERVAL:
            time.sleep(MIN_INTERVAL - gap)
        last_call = time.time()

        try:
            cands = get_llm_candidates(src, model=model)
            if not cands:
                results["no_candidates"].append(gt_path)
                details[gt_path] = {"candidates": [], "survivors": [], "verified": False}
                continue
            result = houdini_at_loop(src, 0, cands, timeout=30)
            key = "solved" if result["verified"] else "failed"
            results[key].append(gt_path)
            details[gt_path] = {"candidates": cands,
                                "survivors": result["invariant"],
                                "verified": result["verified"]}
        except Exception as e:
            results["error"].append(f"{gt_path} :: {e}")

        done = idx + 1
        if done % 10 == 0:
            el = time.time() - start
            print(f"  {done}/{len(scoped)}  ({el:.0f}s)  solved: {len(results['solved'])}")

    total = len(scoped)
    s = len(results["solved"])
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