import json
from config import gt_to_stripped
from llm_arm import get_llm_candidates
from harness import houdini_at_loop

# Take programs from the ceiling set, find ones where mini solves but full doesn't.
ceiling = json.load(open('ceiling_results.json'))
progs = [p.strip() for p in ceiling['verified']][:25]

mini_only = []
for gt in progs:
    src = open(gt_to_stripped(gt), encoding='utf-8', errors='replace').read()
    mc = get_llm_candidates(src, model='openai/gpt-4.1-mini', temperature=0.0)
    fc = get_llm_candidates(src, model='openai/gpt-4.1', temperature=0.0)
    m_ok = bool(mc) and houdini_at_loop(src, 0, mc, timeout=30)['verified']
    f_ok = bool(fc) and houdini_at_loop(src, 0, fc, timeout=30)['verified']
    flag = ''
    if m_ok and not f_ok:
        flag = '  <-- MINI solves, FULL fails'
        mini_only.append((gt, fc))
    print(f"{gt.split('/')[-1][:45]:45s} mini={m_ok} full={f_ok}{flag}")

# Show what full proposed on the ones it failed.
print("\n=== What GPT-4.1 proposed on programs it failed but mini solved ===")
for gt, fc in mini_only[:3]:
    print(f"\n{gt.split('/')[-1]}:")
    for c in fc:
        print("   ", repr(c))