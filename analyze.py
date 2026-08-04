"""
analyze.py — solve-set overlap between baseline and LLM (the complementarity analysis).
"""
import os, json

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

def load_baseline():
    d = json.load(open(os.path.join(PROJECT_ROOT, "baseline_results.json")))
    return set(p.strip() for p in d["solved"])

def load_llm(tag="deepseek_deepseek-v4-flash"):
    d = json.load(open(os.path.join(PROJECT_ROOT, f"llm_results_{tag}.json")))
    return set(p.strip() for p in d["results"]["solved"])

def main():
    base = load_baseline()
    llm = load_llm()

    both = base & llm
    only_base = base - llm
    only_llm = llm - base
    either = base | llm

    print(f"Baseline solves:   {len(base)}")
    print(f"LLM solves:        {len(llm)}")
    print(f"{'='*40}")
    print(f"Both:              {len(both)}")
    print(f"Only baseline:     {len(only_base)}   <- templates' niche")
    print(f"Only LLM:          {len(only_llm)}   <- LLM's categorical wins")
    print(f"Either (union):    {len(either)}")
    print(f"Neither:           {188 - len(either)}")

    # McNemar's test on the paired disagreement.
    b = len(only_base)   # baseline yes, LLM no
    c = len(only_llm)    # LLM yes, baseline no
    print(f"\nMcNemar: b={b} (base-only), c={c} (llm-only)")
    if b + c > 0:
        # Exact/continuity-corrected chi-square.
        chi2 = (abs(b - c) - 1) ** 2 / (b + c)
        print(f"  chi-square (corrected) = {chi2:.2f}")
        print(f"  (chi-square > 3.84 => significant at p<0.05, 1 df)")

    if only_base:
        print(f"\n=== Programs ONLY the baseline solves ({len(only_base)}) ===")
        for p in sorted(only_base):
            print("  ", os.path.basename(p))

if __name__ == "__main__":
    main()