"""
injector.py — insert candidate invariant clauses into real Dafny programs.

DafnyBench 'hints_removed' files delete the `invariant` lines entirely, leaving
a bare `while (guard)` above the loop body. This module finds loop sites and
injects candidate clauses at a chosen loop, supporting multi-loop programs.
"""
import re

# Matches a line whose first non-space token is `while` or `for`.
# Both take invariants in the same position (after the header, before `{`),
# so injection placement is identical; we tag loop type separately for analysis.
LOOP_RE = re.compile(r"^(\s*)(while|for)\b")

def find_loops(source):
    """Return a list of loop sites: (line_index, indentation) for each `while`.

    line_index is 0-based into source.splitlines(). We inject AFTER this line.
    """
    loops = []
    for i, line in enumerate(source.splitlines()):
        m = LOOP_RE.match(line)
        if m:
            loops.append({"line": i, "indent": m.group(1), "kind": m.group(2)})
    return loops


def _same_line_brace(line):
    """True if the loop body's opening brace is on the `while` line itself,
    e.g. `while x < n {`. We can't cleanly inject after the guard in that case
    without splitting the line, so we flag it for exclusion / special handling.
    """
    # Strip the guard's balanced parens, then look for a trailing '{'.
    # Cheap heuristic: a '{' anywhere after the first non-paren content.
    return line.rstrip().endswith("{")


def inject_at_loop(source, loop_index, clauses):
    """Insert `clauses` (list of invariant strings) after the given loop's guard.

    Returns (new_source, status). status is 'ok' or a reason string if we had
    to skip (e.g. same-line brace). loop_index is 0-based into find_loops().
    """
    loops = find_loops(source)
    if loop_index >= len(loops):
        return source, f"no_such_loop({loop_index}/{len(loops)})"

    site = loops[loop_index]
    lines = source.splitlines()
    guard_line = lines[site["line"]]

    if _same_line_brace(guard_line):
        return source, "same_line_brace"

    indent = site["indent"] + "  "  # nest invariants one level under `while`
    injected = [f"{indent}invariant {c.strip()}"
                for c in clauses if c.strip()]

    new_lines = (lines[: site["line"] + 1]   # up to and including the while
                 + injected                   # our invariant clauses
                 + lines[site["line"] + 1:])  # the rest (body onward)
    return "\n".join(new_lines) + "\n", "ok"


def inject_all_loops(source, clauses):
    """Inject the SAME clause set after EVERY loop's guard.

    Useful for the 'let Houdini sort it' strategy: dump all candidates on all
    loops, let the sound filter discard the ones that don't hold at each site.
    Returns (new_source, status). Injects from the last loop backwards so that
    earlier line indices stay valid as we insert.
    """
    loops = find_loops(source)
    if not loops:
        return source, "no_loops"

    lines = source.splitlines()
    skipped = 0
    for site in reversed(loops):          # back-to-front keeps indices valid
        guard_line = lines[site["line"]]
        if _same_line_brace(guard_line):
            skipped += 1
            continue
        indent = site["indent"] + "  "
        injected = [f"{indent}invariant {c.strip()}"
                    for c in clauses if c.strip()]
        lines = (lines[: site["line"] + 1] + injected + lines[site["line"] + 1:])

    status = "ok" if skipped == 0 else f"skipped_{skipped}_same_line"
    return "\n".join(lines) + "\n", status


# A clause ends when the next line starts a new clause keyword OR opens the
# loop body with `{`. The brace is matched separately since `\b` doesn't apply
# after a non-word character like `{`.
_CLAUSE_BOUNDARY = re.compile(r"^\s*(invariant\b|decreases\b|modifies\b|ensures\b|\{)")

def extract_invariants(source):
    """Extract complete invariant clauses, joining multi-line ones.

    A clause starts at an `invariant` keyword and runs until the next clause
    keyword or the loop body `{`. Returns a list of clause strings with the
    leading `invariant` keyword stripped.
    """
    lines = source.splitlines()
    clauses = []
    i = 0
    while i < len(lines):
        m = re.match(r"^\s*invariant\s+(.*)$", lines[i])
        if not m:
            i += 1
            continue
        # Start a clause with the text after `invariant`.
        parts = [m.group(1).rstrip()]
        j = i + 1
        # Absorb continuation lines until we hit the next boundary.
        while j < len(lines) and not _CLAUSE_BOUNDARY.match(lines[j]):
            stripped = lines[j].strip()
            if stripped:                       # skip blank lines
                parts.append(stripped)
            j += 1
        clauses.append(" ".join(parts))
        i = j
    return clauses