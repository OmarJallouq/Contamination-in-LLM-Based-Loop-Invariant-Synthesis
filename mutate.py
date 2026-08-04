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


# --- Tier 2: constant perturbation -------------------------------------------

import random

# Match integer literals, but we'll filter by context to avoid spec constants.
INT_LITERAL_RE = re.compile(r"\b(\d+)\b")


def _lines_in_spec(source):
    """Return set of line indices that are part of requires/ensures clauses,
    so we never perturb constants that the specification depends on."""
    spec_lines = set()
    for i, line in enumerate(source.splitlines()):
        s = line.strip()
        if s.startswith("requires") or s.startswith("ensures"):
            spec_lines.add(i)
    return spec_lines


def perturb_constants(source, ground_truth_invariants, delta_pool=(1, 2, 3, 5, 10)):
    """Perturb integer literals in executable code (not in the spec), applying
    the SAME perturbation to the ground-truth invariants for consistency.

    Returns (new_source, new_invariants, mapping) or (None, None, {}) if there
    are no safely-perturbable constants. mapping is {original_const: new_const}.

    Strategy: find integer literals that appear in NON-spec lines, pick a
    consistent new value for each distinct literal (old -> old+delta), and
    replace that literal everywhere (code AND invariants) so semantics of the
    'shape' are preserved while the specific number changes.
    """
    spec_lines = _lines_in_spec(source)
    lines = source.splitlines()

    # Collect distinct literals that appear in executable (non-spec) lines,
    # excluding 0 and 1 (perturbing these often breaks loop logic/semantics).
    perturbable = set()
    for i, line in enumerate(lines):
        if i in spec_lines:
            continue
        for m in INT_LITERAL_RE.finditer(line):
            val = int(m.group(1))
            if val >= 2:                      # skip 0 and 1 (semantically load-bearing)
                perturbable.add(val)

    if not perturbable:
        return None, None, {}

    # Assign each distinct literal a consistent new value.
    mapping = {}
    for val in sorted(perturbable, reverse=True):   # largest first (avoid overlap)
        delta = random.choice(delta_pool)
        mapping[val] = val + delta

    def apply(text, respect_spec=False):
        out_lines = []
        for i, line in enumerate(text.splitlines()):
            if respect_spec and i in spec_lines:
                out_lines.append(line)          # never touch spec lines
                continue
            new_line = line
            # Replace each mapped literal as a whole number, largest first.
            for old in sorted(mapping, reverse=True):
                new_line = re.sub(rf"\b{old}\b", str(mapping[old]), new_line)
            out_lines.append(new_line)
        return "\n".join(out_lines)

    new_source = apply(source, respect_spec=True)
    # Invariants may reference the same constants; perturb them consistently too.
    new_invs = [apply(inv) for inv in ground_truth_invariants]
    return new_source, new_invs, mapping


if __name__ == "__main__":
    # Test both tiers on a program with a literal constant.
    # (SquareRoot has no literals >=2, so use one that does.)
    import os
    # Find a program with a perturbable constant for demonstration.
    src = """method Foo(a: array<int>) returns (count: int)
  requires a.Length == 10
  ensures count >= 0
{
  count := 0;
  var i := 0;
  while i < 10
  {
    if a[i] > 5 { count := count + 1; }
    i := i + 1;
  }
}"""
    gt = ["0 <= i <= 10", "count >= 0"]
    ns, ni, m = perturb_constants(src, gt)
    print("Tier 2 mapping:", m)
    print("=== perturbed ===")
    print(ns)
    print("=== perturbed invariants ===", ni)


# --- Tier 3: for -> while conversion (semantics-preserving by construction) ---

# Match:  for <var> := <start> to <end>
# Captures indentation, loop var, start expr, end expr.
FOR_LOOP_RE = re.compile(
    r"^(\s*)for\s+(\w+)\s*:=\s*(.+?)\s+to\s+(.+?)\s*$", re.MULTILINE)


def for_to_while(source, ground_truth_invariants):
    """Convert the first `for i := start to end` loop into an equivalent
    `while` loop, augmenting invariants with the counter bounds.

    Semantics-preserving by construction (Dafny defines for as while sugar).
    Returns (new_source, new_invariants, meta) or (None, None, {}) if no
    convertible for-loop is found.
    """
    lines = source.splitlines()

    # Find the first `for ... to ...` line.
    for_line_idx = None
    for i, line in enumerate(lines):
        m = re.match(r"^(\s*)for\s+(\w+)\s*:=\s*(.+?)\s+to\s+(.+?)\s*$", line)
        if m:
            for_line_idx = i
            indent, var, start, end = m.group(1), m.group(2), m.group(3).strip(), m.group(4).strip()
            break
    if for_line_idx is None:
        return None, None, {}   # no convertible for-loop

    # 'downto' loops desugar differently; skip them (detect and bail).
    if "downto" in lines[for_line_idx]:
        return None, None, {}

    # Find the loop body's opening brace (the next line that is just `{`,
    # possibly after invariant/decreases clauses on the for-loop).
    body_open_idx = None
    j = for_line_idx + 1
    while j < len(lines):
        if lines[j].strip() == "{":
            body_open_idx = j
            break
        # Skip invariant/decreases clauses attached to the for-loop.
        if re.match(r"^\s*(invariant|decreases)\b", lines[j]):
            j += 1
            continue
        # Anything else before `{` means an unexpected shape; bail safely.
        break
    if body_open_idx is None:
        return None, None, {}

    # Find the matching closing brace of the loop body (brace counting).
    depth = 0
    body_close_idx = None
    for k in range(body_open_idx, len(lines)):
        depth += lines[k].count("{") - lines[k].count("}")
        if depth == 0:
            body_close_idx = k
            break
    if body_close_idx is None:
        return None, None, {}

    # Build the while version.
    bounds_inv = f"0 <= {var} <= {end}"
    # New loop header lines.
    new_header = [
        f"{indent}var {var} := {start};",
        f"{indent}while {var} < {end}",
    ]
    # Preserve any invariant/decreases clauses that were on the for-loop,
    # and prepend the bounds invariant (dedup if already present).
    clause_lines = lines[for_line_idx + 1: body_open_idx]
    existing = "\n".join(clause_lines)
    if bounds_inv.replace(" ", "") not in existing.replace(" ", ""):
        new_header.append(f"{indent}  invariant {bounds_inv}")
    new_header.extend(clause_lines)

    # Body: original body lines, with `i := i + 1;` appended before close.
    body_lines = lines[body_open_idx: body_close_idx]   # includes the `{`
    increment = f"{indent}  {var} := {var} + 1;"

    new_lines = (lines[:for_line_idx]
                 + new_header
                 + body_lines
                 + [increment]
                 + lines[body_close_idx:])   # the `}` and everything after
    new_source = "\n".join(new_lines) + "\n"

    # Augment the ground-truth invariants with the bounds (dedup).
    new_invs = list(ground_truth_invariants)
    if not any(bounds_inv.replace(" ", "") == inv.replace(" ", "") for inv in new_invs):
        new_invs = [bounds_inv] + new_invs

    return new_source, new_invs, {"var": var, "start": start, "end": end}
