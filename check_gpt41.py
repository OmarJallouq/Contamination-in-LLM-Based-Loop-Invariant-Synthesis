from llm_arm import get_llm_candidates
from harness import houdini_at_loop

# A program we KNOW is solvable (SquareRoot needs r*r <= N).
src = open('DafnyBench/DafnyBench/dataset/hints_removed/'
           'Clover_integer_square_root_no_hints.dfy').read()

for model in ['openai/gpt-4.1-mini', 'openai/gpt-4.1']:
    print(f"\n===== {model} =====")
    cands = get_llm_candidates(src, model=model, temperature=0.0)
    print(f"candidates ({len(cands)}):")
    for c in cands:
        print("   ", repr(c))
    r = houdini_at_loop(src, 0, cands, timeout=30)
    print("verified:", r['verified'])