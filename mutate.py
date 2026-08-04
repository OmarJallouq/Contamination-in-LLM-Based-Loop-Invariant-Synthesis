"""
mutate.py — Tier 1 contamination mutation: consistent variable renaming.

Renames program variables to semantically-neutral fresh names, breaking verbatim
memorization while preserving semantics. Each mutation is applied consistently to
BOTH the stripped program and the ground-truth invariant, then verified to still
pass (soundness re-check) before being used as a test case.
"""
import re
from templates import extract_variables

# Neutral replacement pool — generic names unlikely to carry semantic hints.
RENAME_POOL = ["v0", "v1", "v2", "v3", "v4", "v5", "v6", "v7", "v8", "v9"]

# Dafny keywords / built-ins we must never rename.
RESERVED = {
    "method", "function", "predicate", "returns", "requires", "ensures",
    "invariant", "decreases", "reads", "modifies", "while", "for", "if",
    "else", "assert", "assume", "var", "return", "true", "false", "int",
    "nat", "bool", "real", "seq", "array", "set", "map", "forall", "exists",
    "in", "old", "fresh", "null", "this", "new", "match", "case", "then",
    "abs", "Length", "Keys", "Values", "Items",
}


def rename_variables(source, ground_truth_invariants):
    """Rename all program variables consistently in source AND invariants.

    Returns (new_source, new_invariants, mapping) or (None,...) if no vars found.
    """
    scalars, seqs = extract_variables(source)
    variables = [v for v in (scalars + seqs) if v not in RESERVED]
    if not variables:
        return None, None, {}

    # Map each variable to a fresh neutral name.
    mapping = {}
    for idx, var in enumerate(variables):
        if idx < len(RENAME_POOL):
            mapping[var] = RENAME_POOL[idx]

    def apply(text):
        # Replace each variable as a whole word, longest names first to avoid
        # partial-overlap issues (e.g. 'i' inside 'index' — word boundary handles
        # it, but longest-first is extra safety).
        for var in sorted(mapping, key=len, reverse=True):
            text = re.sub(rf"\b{re.escape(var)}\b", mapping[var], text)
        return text

    new_source = apply(source)
    new_invs = [apply(inv) for inv in ground_truth_invariants]
    return new_source, new_invs, mapping


if __name__ == "__main__":
    # Test on SquareRoot.
    src = open("DafnyBench/DafnyBench/dataset/hints_removed/"
               "Clover_integer_square_root_no_hints.dfy").read()
    gt_invs = ["r*r<=N"]
    new_src, new_invs, mapping = rename_variables(src, gt_invs)
    print("Mapping:", mapping)
    print("=== renamed program ===")
    print(new_src)
    print("=== renamed invariants ===")
    print(new_invs)