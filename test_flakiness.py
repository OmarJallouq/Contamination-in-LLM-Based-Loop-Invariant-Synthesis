"""Compare flakiness: does a seedable model beat DeepSeek's nondeterminism?"""
import json
from config import gt_to_stripped
from llm_arm import get_llm_candidates
from harness import houdini_at_loop

llm = json.load(open('llm_results_deepseek_deepseek-v4-flash.json'))
programs = [p.strip() for p in llm['results']['solved']][:8]

def solve_3x(src, model):
    outcomes = []
    for _ in range(3):
        c = get_llm_candidates(src, model=model, temperature=0.0)
        solved = bool(c) and houdini_at_loop(src, 0, c, timeout=30)['verified']
        outcomes.append(solved)
    if all(outcomes): return 'yes'
    if not any(outcomes): return 'no'
    return 'FLAKY'

model = "openai/gpt-4.1-mini"
print(f"Testing flakiness on {model} (8 programs, 3 runs each)\n")
flaky = 0
for gt in programs:
    src = open(gt_to_stripped(gt)).read()
    r = solve_3x(src, model)
    if r == 'FLAKY': flaky += 1
    print(f"  {r:6s}  {gt.split('/')[-1][:40]}")
print(f"\nFLAKY: {flaky}/8  (DeepSeek was 3/8)")