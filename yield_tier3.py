import json, os
from config import gt_to_stripped
from mutate import for_to_while
from harness import houdini_at_loop
from injector import extract_invariants

llm = json.load(open('llm_results_deepseek_deepseek-v4-flash.json'))
solved = [p.strip() for p in llm['results']['solved']]

no_for, unsound, sound = 0, 0, 0
for gt_path in solved:
    sp = gt_to_stripped(gt_path)
    if not os.path.exists(sp): continue
    src = open(sp, encoding='utf-8', errors='replace').read()
    gt_invs = extract_invariants(open(gt_path, encoding='utf-8', errors='replace').read())
    ns, ni, meta = for_to_while(src, gt_invs)
    if ns is None:
        no_for += 1
        continue
    try:
        if houdini_at_loop(ns, 0, ni, timeout=20)['verified']:
            sound += 1
        else:
            unsound += 1
    except Exception:
        unsound += 1

total = len(solved)
print(f'Total: {total}')
print(f'  No for-loop:        {no_for}')
print(f'  Converted, unsound: {unsound}')
print(f'  Converted, SOUND:   {sound}')
print(f'Tier 3 yield: {sound}/{total} = {100*sound/total:.0f}%')