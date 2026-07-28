"""
templates.py — the classical baseline's candidate SOURCE.

Enumerates a fixed grammar of linear invariant candidates from a program's
variables (Houdini/Daikon-style), to be filtered by the sound Houdini filter.

Grammar (deliberately linear-only; see thesis methodology):
  Tier 1  variable bounds:        0 <= v,  v >= 0
  Tier 2  variable comparisons:   u <= v,  u < v,  u == v   (ordered pairs)
  Tier 3  variable-length compare: v <= |a|, v < |a|, v == |a|

By construction this CANNOT express nonlinear (s == i*i) or quantified
(forall k :: ...) invariants — that gap is the hypothesized locus of LLM value.
"""
import re

# --- Variable extraction ---------------------------------------------------

# Method parameters:  method Foo(a: int, b: seq<int>) returns (r: nat)
METHOD_SIG_RE = re.compile(r"method\s+\w+\s*\((.*?)\)\s*(?:returns\s*\((.*?)\))?", re.DOTALL)
# Local declarations:  var i := 0;   var x: int := ...;
LOCAL_VAR_RE = re.compile(r"\bvar\s+(\w+)")
# A parameter/return entry looks like `name: type`; we want the names and
# whether the type is a sequence/array (so we can build length templates).
PARAM_RE = re.compile(r"(\w+)\s*:\s*([\w<>\[\]]+)")

# Types we treat as "has a length |v|": seq, array, string, multiset.
SEQ_LIKE = re.compile(r"\b(seq|array|string|multiset)\b")


def extract_variables(source):
    """Return (scalar_vars, seq_vars): integer-ish vars, and length-bearing vars.

    scalar_vars: names usable in numeric comparisons (int/nat params, locals,
                 returns). seq_vars: names that have a |v| length.
    """
    scalars, seqs = set(), set()

    m = METHOD_SIG_RE.search(source)
    if m:
        params = m.group(1) or ""
        returns = m.group(2) or ""
        for chunk in (params, returns):
            for pm in PARAM_RE.finditer(chunk):
                name, typ = pm.group(1), pm.group(2)
                if SEQ_LIKE.search(typ):
                    seqs.add(name)
                else:
                    scalars.add(name)

    # Locals: we don't know their types reliably, so treat as scalar candidates.
    # (A local seq is possible but rarer; over-including a scalar just makes a
    #  few extra candidates that Houdini will discard — safe, not wrong.)
    for lm in LOCAL_VAR_RE.finditer(source):
        name = lm.group(1)
        if name not in seqs:
            scalars.add(name)

    return sorted(scalars), sorted(seqs)


# --- Template enumeration --------------------------------------------------

def generate_templates(source):
    """Produce the full candidate pool for a program (Tiers 1-3)."""
    scalars, seqs = extract_variables(source)
    candidates = []

    # Tier 1: bounds on each scalar.
    for v in scalars:
        candidates.append(f"0 <= {v}")
        candidates.append(f"{v} >= 0")   # redundant with above; Houdini dedups effect

    # Tier 2: comparisons between each ordered pair of distinct scalars.
    for u in scalars:
        for v in scalars:
            if u == v:
                continue
            candidates.append(f"{u} <= {v}")
            candidates.append(f"{u} < {v}")
            candidates.append(f"{u} == {v}")

    # Tier 3: each scalar compared to each sequence length.
    for v in scalars:
        for a in seqs:
            candidates.append(f"{v} <= |{a}|")
            candidates.append(f"{v} < |{a}|")
            candidates.append(f"{v} == |{a}|")

    # De-duplicate while preserving order.
    seen, unique = set(), []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            unique.append(c)
    return unique


if __name__ == "__main__":
    # Quick self-test on Sum.
    sum_src = """method Sum(n: int) returns (s: int)
  requires n >= 0
  ensures s == n * (n + 1) / 2
{
  s := 0;
  var i := 0;
  while i < n { }
}"""
    scalars, seqs = extract_variables(sum_src)
    print("scalars:", scalars)
    print("seqs:", seqs)
    pool = generate_templates(sum_src)
    print(f"\n{len(pool)} candidates:")
    for c in pool:
        print("  ", c)