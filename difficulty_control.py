"""
difficulty_control.py — measure the inherent difficulty gap between for-loop and
while-loop programs, to interpret the structure-mutation result.

Both groups are ORIGINAL, unmutated programs. The only difference is native loop
type. If while-programs solve much lower, while-invariants are inherently harder
(a difficulty confound in the structure mutation). If they solve equally, the
structure-mutation drop is attributable to distance-from-training-form
(memorization), not difficulty.
"""
import json, re, os, time
from concurrent.futures import ProcessPoolExecutor, as_completed
from config import gt_to_stripped, RUNS, DAFNY_TIMEOUT, MODELS
from llm_arm import get_llm_candidates
from harness import houdini_at_loop

def classify_loop(src):
    has_for = bool(re.search(r'\bfor\s+\w+\s*:=', src))
    has_while = bool(re.search(r'\bwhile\b', src))
    if has_for and not has_while:
        return "for"
    if has_while and not has_for:
        return "while"
    return "mixed"  # both or neither — excluded

def solve_rate(src, model, runs):
    solved = 0
    for _ in range(runs):
        cands = get_llm_candidates(src, model=model, temperature=0.0)
        if cands and houdini_at_loop(src, 0, cands, timeout=DAFNY_TIMEOUT)["verified"]:
            solved += 1
    return solved

def process_one(args):
    gt_path, model, runs = args
    sp = gt_to_stripped(gt_path)
    if not os.path.exists(sp):
        return (gt_path, None, None)
    src = open(sp, encoding="utf-8", errors="replace").read()
    loop_type = classify_loop(src)
    if loop_type == "mixed":
        return (gt_path, "mixed", None)
    try:
        rate = solve_rate(src, model, runs)
        return (gt_path, loop_type, rate)
    except Exception as e:
        return (gt_path, "error", str(e))

def run(model, runs=RUNS, max_workers=4):
    llm = json.load(open(f"llm_results_{model.replace('/','_').replace(':','_')}.json"))
    solved = [p.strip() for p in llm["results"]["solved"]]
    print(f"Difficulty control: {len(solved)} programs, model={model}\n")

    for_rates, while_rates = [], []
    start = time.time(); done = 0
    with ProcessPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(process_one, (p, model, runs)): p for p in solved}
        for fut in as_completed(futures):
            gt_path, loop_type, rate = fut.result()
            if loop_type == "for" and rate is not None:
                for_rates.append(rate / runs)
            elif loop_type == "while" and rate is not None:
                while_rates.append(rate / runs)
            done += 1
            if done % 20 == 0:
                print(f"  {done}/{len(solved)}  ({time.time()-start:.0f}s)")

    import statistics as st
    print(f"\n{'='*55}")
    print(f"DIFFICULTY CONTROL — {model}")
    print(f"{'='*55}")
    print(f"Native FOR-loop programs:   n={len(for_rates)}, "
          f"solve rate {100*st.mean(for_rates):.1f}%")
    print(f"Native WHILE-loop programs: n={len(while_rates)}, "
          f"solve rate {100*st.mean(while_rates):.1f}%")
    gap = 100*(st.mean(for_rates) - st.mean(while_rates))
    print(f"\nDIFFICULTY GAP (for - while): {gap:+.1f}pp")
    print(f"\nInterpretation:")
    print(f"  Large gap  -> while-loops inherently harder; part of the 37.8pp")
    print(f"                structure drop is difficulty, not memorization.")
    print(f"  Small gap  -> loop type doesn't affect difficulty; the structure")
    print(f"                drop is attributable to distance-from-training-form.")
    print(f"\nRecall: structure mutation (for->while) drop was +37.8pp.")
    print(f"  Difficulty component (this gap):    ~{gap:.1f}pp")
    print(f"  Residual (memorization candidate):  ~{37.8-gap:.1f}pp")

    json.dump({"model": model, "for_rates": for_rates, "while_rates": while_rates,
               "for_mean": st.mean(for_rates), "while_mean": st.mean(while_rates),
               "gap_pp": gap},
              open(f"difficulty_control_{model.replace('/','_').replace(':','_')}.json", "w"),
              indent=2)
    print(f"\n  Time: {time.time()-start:.0f}s")

if __name__ == "__main__":
    for model in MODELS:
        run(model)