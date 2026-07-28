from harness import verify_candidate_at_loop

src = open('DafnyBench/DafnyBench/dataset/hints_removed/'
           'dafny-synthesis_task_id_69_no_hints.dfy').read()

survivors = [
    '0 <= result', 'result >= 0',
    'result <= |list|', 'result < |list|', 'result == |list|',
    'result <= |sub|', 'result < |sub|', 'result == |sub|',
    'result <==> (exists k :: 0 <= k < i && sub == list[k])',
]

r = verify_candidate_at_loop(src, 0, survivors, timeout=30)
print('All 9 together:', r['verified'])

print('Individual checks:')
for c in ['result == |list|', 'result < |list|', 'result <= |sub|']:
    rr = verify_candidate_at_loop(src, 0, [c], timeout=30)
    print('  ', repr(c), '->', rr['verified'])