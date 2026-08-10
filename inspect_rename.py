from config import gt_to_stripped
from mutate import rename_variables
from injector import extract_invariants
from llm_arm import get_llm_candidates
from harness import houdini_at_loop

target = ('DafnyBench/DafnyBench/dataset/ground_truth/'
          'MFES_2021_tmp_tmpuljn8zd9_FCUL_Exercises_8_sum.dfy')
src = open(gt_to_stripped(target), encoding='utf-8', errors='replace').read()
gt = extract_invariants(open(target, encoding='utf-8', errors='replace').read())

print("=== ORIGINAL PROGRAM ===")
print(src)
print("=== GROUND TRUTH INVARIANTS ===")
for i in gt:
    print("  ", i)

new_src, new_invs, mapping = rename_variables(src, gt)
print("\n=== RENAMED PROGRAM ===")
print(new_src)
print("mapping:", mapping)

print("\n=== WHAT THE LLM PROPOSES ===")
print("--- on ORIGINAL ---")
oc = get_llm_candidates(src, temperature=0.0)
for c in oc:
    print("  ", c)
print("  verifies:", houdini_at_loop(src, 0, oc)['verified'])

print("--- on RENAMED ---")
rc = get_llm_candidates(new_src, temperature=0.0)
for c in rc:
    print("  ", c)
print("  verifies:", houdini_at_loop(new_src, 0, rc)['verified'])