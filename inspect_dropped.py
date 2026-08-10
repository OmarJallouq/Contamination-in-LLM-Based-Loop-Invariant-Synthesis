import json

d = json.load(open('results/mutation_structure__deepseek-deepseek-v4-flash__full.json'))

# Look at the worst-dropped program.
target = [p for p in d['results'] if 'task_id_307' in p][0]
rec = d['results'][target]
print("PROGRAM:", target.split('/')[-1])
print("orig_solves:", rec['orig_solves'], " mutated_solves:", rec['mutated_solves'])
print("meta (conversion):", rec.get('meta'))
print()

# The result file stores solve counts but not the candidates per attempt.
# So let's re-derive: show the original program and its for->while conversion.
from config import gt_to_stripped
from mutate import for_to_while
from injector import extract_invariants

src = open(gt_to_stripped(target), encoding='utf-8', errors='replace').read()
gt = extract_invariants(open(target, encoding='utf-8', errors='replace').read())

print("=== ORIGINAL (for-loop) ===")
print(src)
print("=== GROUND TRUTH INVARIANTS ===")
for i in gt: print("  ", i)

ns, ni, meta = for_to_while(src, gt)
print("\n=== CONVERTED (while-loop) ===")
print(ns)