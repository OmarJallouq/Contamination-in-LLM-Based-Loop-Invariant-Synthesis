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


# Numeric types eligible for arithmetic comparison templates.
NUMERIC_TYPES = re.compile(r"\b(int|nat|real|bv\d+)\b")

def extract_variables(source):
    """Return (scalar_vars, seq_vars): NUMERIC vars usable in comparisons, and
    length-bearing (seq/array/string) vars. Type-aware: non-numeric scalars like
    bool/char are excluded so we never generate ill-typed templates.
    """
    scalars, seqs = set(), set()

    m = METHOD_SIG_RE.search(source)
    if m:
        for chunk in (m.group(1) or "", m.group(2) or ""):
            for pm in PARAM_RE.finditer(chunk):
                name, typ = pm.group(1), pm.group(2)
                if SEQ_LIKE.search(typ):
                    seqs.add(name)
                elif NUMERIC_TYPES.search(typ):
                    scalars.add(name)
                # else: bool, char, custom types -> neither. No numeric templates.

    # Locals: `var x: int := ...` gives a type; `var x := ...` doesn't.
    # Only include locals we can confirm are numeric via an explicit annotation.
    for lm in re.finditer(r"\bvar\s+(\w+)\s*:\s*([\w<>\[\]]+)", source):
        name, typ = lm.group(1), lm.group(2)
        if SEQ_LIKE.search(typ):
            seqs.add(name)
        elif NUMERIC_TYPES.search(typ):
            scalars.add(name)

    # Untyped locals `var x := 0` — infer numeric only if initialized to an
    # integer literal (common for counters/accumulators). Conservative.
    for lm in re.finditer(r"\bvar\s+(\w+)\s*:=\s*(-?\d+)\b", source):
        scalars.add(lm.group(1))

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

# --- Function-aware templates (postcondition-guided) -----------------------

# User-defined functions:  function Fat(n: nat): nat  /  function method min(...)
FUNC_DEF_RE = re.compile(r"\bfunction(?:\s+method)?\s+(\w+)\s*\(")
# Postcondition clauses.
ENSURES_RE = re.compile(r"^\s*ensures\s+(.+?)\s*$", re.MULTILINE)
# A function application: Name( ... ) with balanced-ish single-level args.
# We capture the function name and the raw argument string.
APP_RE = re.compile(r"\b(\w+)\s*\(([^()]*)\)")


def find_user_functions(source):
    """Names of functions the program defines (so we only template real ones)."""
    return set(FUNC_DEF_RE.findall(source))


def find_loop_counter(source, loop_index=0):
    """Best-effort: the induction variable of the target loop.

    for i := ... -> 'i'.  while loops: look for a 'var X := 0' before the loop,
    else return None and callers fall back to all scalars.
    """
    lines = source.splitlines()
    # Find the loop_index-th while/for line.
    from injector import find_loops
    loops = find_loops(source)
    if loop_index >= len(loops):
        return None
    loop_line = loops[loop_index]["line"]
    kind = loops[loop_index]["kind"]

    if kind == "for":
        m = re.match(r"^\s*for\s+(\w+)", lines[loop_line])
        if m:
            return m.group(1)
    # while: the counter is usually the variable in the guard, e.g. `while i < n`.
    # Take the first identifier in the guard that is also a known scalar.
    m = re.match(r"^\s*while\s+(.+)", lines[loop_line])
    if m:
        guard = m.group(1)
        scalars, _ = extract_variables(source)
        for tok in re.findall(r"\b\w+\b", guard):
            if tok in scalars:
                return tok
    return None


def generate_function_templates(source, loop_index=0):
    """Postcondition-guided candidates: substitute the loop counter (and, as
    fallback, each scalar) for the argument variable in each postcondition
    function-application term.
    """
    user_funcs = find_user_functions(source)
    if not user_funcs:
        return []

    scalars, _ = extract_variables(source)
    counter = find_loop_counter(source, loop_index)
    # Substitution targets: prefer the counter, but also try all scalars.
    subs = ([counter] if counter else []) + [s for s in scalars if s != counter]

    candidates = []
    # Collect (lhs, func_term) pairs from the postconditions.
    for ens in ENSURES_RE.findall(source):
        # Look at equalities:  LHS == RHS  where RHS contains a user function.
        for eq in re.split(r"&&|,", ens):
            if "==" not in eq:
                continue
            lhs, _, rhs = eq.partition("==")
            lhs, rhs = lhs.strip(), rhs.strip()
            # Does RHS use a user function?
            for fname, args in APP_RE.findall(rhs):
                if fname not in user_funcs:
                    continue
                # For each substitution target, rewrite the argument.
                for sub in subs:
                    # Replace whole-word variable occurrences in the arg string.
                    for var in scalars:
                        new_args = re.sub(rf"\b{re.escape(var)}\b", sub, args)
                        cand_rhs = rhs.replace(f"{fname}({args})",
                                               f"{fname}({new_args})")
                        candidates.append(f"{lhs} == {cand_rhs}")

    # Dedup, preserving order.
    seen, uniq = set(), []
    for c in candidates:
        if c not in seen:
            seen.add(c); uniq.append(c)
    return uniq


def generate_all_templates(source, loop_index=0):
    """Full baseline pool: linear grammar (Tiers 1-3) + function templates."""
    return generate_templates(source) + generate_function_templates(source, loop_index)


# --- Family C: postcondition weakening (Furia & Meyer 2009) -----------------

# Terminal bound expressions we replace with the loop counter: |seq|, arr.Length, n.
# We detect the "upper bound" in a quantifier range `0 <= k < BOUND`.

QUANTIFIER_RE = re.compile(r"\b(forall|exists)\s+(\w+)\s*::")

def generate_postcondition_templates(source, loop_index=0):
    """Furia-Meyer: weaken each postcondition by replacing its terminal bound
    with the loop counter, producing a candidate invariant. Handles quantifier
    variable/counter name collisions by renaming the quantifier variable.
    """
    scalars, seqs = extract_variables(source)
    counter = find_loop_counter(source, loop_index)
    if not counter:
        return []

    candidates = []
    for ens in ENSURES_RE.findall(source):
        ens = ens.strip()

        # Case 1: quantified postcondition (forall/exists).
        qm = QUANTIFIER_RE.search(ens)
        if qm:
            qvar = qm.group(2)   # the quantifier's bound variable
            body = ens
            # If the quantifier variable clashes with the loop counter, rename it.
            if qvar == counter:
                fresh = "k" if counter != "k" else "kk"
                body = re.sub(rf"\b{re.escape(qvar)}\b", fresh, body)
                qvar = fresh
            # Now replace the terminal upper bound with the loop counter.
            # Common bound forms: |seq|, seq.Length, or a scalar like n.
            for a in seqs:
                for bound in (f"|{a}|", f"{a}.Length"):
                    if bound in body:
                        candidates.append(body.replace(bound, counter))
            for s in scalars:
                if s == counter:
                    continue
                # Replace bound-position occurrences: `< s` or `<= s`.
                new = re.sub(rf"(<=?\s*){re.escape(s)}\b", rf"\g<1>{counter}", body)
                if new != body:
                    candidates.append(new)

        # Case 2: non-quantified postcondition with a length/scalar bound.
        else:
            for a in seqs:
                for bound in (f"|{a}|", f"{a}.Length"):
                    if bound in ens:
                        candidates.append(ens.replace(bound, counter))

    # Dedup.
    seen, uniq = set(), []
    for c in candidates:
        if c not in seen:
            seen.add(c); uniq.append(c)
    return uniq


def generate_all_templates(source, loop_index=0):
    """Complete baseline pool:
       Family A (Daikon linear)  +  Family B (function subst)  +  Family C (postcond weakening).
    """
    return (generate_templates(source)
            + generate_function_templates(source, loop_index)
            + generate_postcondition_templates(source, loop_index))

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