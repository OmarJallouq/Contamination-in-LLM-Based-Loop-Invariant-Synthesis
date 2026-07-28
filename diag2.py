from injector import inject_at_loop

src = open('DafnyBench/DafnyBench/dataset/hints_removed/'
           'dafny-synthesis_task_id_69_no_hints.dfy').read()

# Inject a mix of good and bad clauses, see how Dafny reports which failed.
clauses = [
    'result == |list|',                                      # bad
    'result <==> (exists k :: 0 <= k < i && sub == list[k])',# good
    'result <= |sub|',                                       # bad
]
filled, status = inject_at_loop(src, 0, clauses)
print('INJECT STATUS:', status)
print('=== FILLED (with line numbers) ===')
for n, line in enumerate(filled.splitlines(), 1):
    print(f'{n:3d}| {line}')

import tempfile, os
from harness import run_dafny
with tempfile.NamedTemporaryFile(mode='w', suffix='.dfy', dir='.', delete=False) as t:
    t.write(filled); tp = t.name
try:
    r = run_dafny(tp)
    print('=== DAFNY OUTPUT ===')
    print(r.stdout)
finally:
    os.remove(tp)