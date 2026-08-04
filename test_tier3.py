from mutate import for_to_while
from harness import houdini_at_loop

src = open('DafnyBench/DafnyBench/dataset/hints_removed/'
           'dafny-synthesis_task_id_477_no_hints.dfy').read()

gt = [
    '0 <= i <= |s|',
    "|s'| == i",
    "forall k :: 0 <= k < i && IsUpperCase(s[k]) ==> IsUpperLowerPair(s[k], s'[k])",
    "forall k :: 0 <= k < i && !IsUpperCase(s[k]) ==> s[k] == s'[k]",
]

ns, ni, meta = for_to_while(src, gt)
print('meta:', meta)
print('=== converted program ===')
print(ns)
print('=== augmented invariants ===')
for inv in ni:
    print('  ', inv)
print()
sound = houdini_at_loop(ns, 0, ni, timeout=30)
print('SOUNDNESS GATE (converted while verifies with GT):', sound['verified'])