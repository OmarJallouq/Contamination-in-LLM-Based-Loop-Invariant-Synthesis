from injector import find_loops, inject_at_loop
from harness import verify  # your existing harness
import tempfile, os

# The real DafnyBench stripped program.
path = ("DafnyBench/DafnyBench/dataset/hints_removed/"
        "Clover_integer_square_root_no_hints.dfy")
with open(path) as f:
    stripped = f.read()

print("Loops found:", find_loops(stripped))

# Inject the ground-truth invariant into loop 0.
filled, status = inject_at_loop(stripped, 0, ["r*r<=N"])
print("Inject status:", status)
print("--- filled program ---")
print(filled)

# Write to a temp file and verify.
with tempfile.NamedTemporaryFile(mode="w", suffix=".dfy",
                                 dir=".", delete=False) as tmp:
    tmp.write(filled)
    tmp_path = tmp.name
try:
    print("VERDICT:", verify(tmp_path))
finally:
    os.remove(tmp_path)