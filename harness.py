import subprocess
import subprocess
import tempfile
import os
from injector import inject_at_loop

def run_dafny(filepath, timeout=60):
    """Run `dafny verify` on a file, return the raw result."""
    result = subprocess.run(
        ["dafny", "verify", filepath],
        capture_output=True,   # grab stdout and stderr instead of printing
        text=True,             # decode bytes to string for us
        timeout=timeout,       # kill it if Dafny hangs (some proofs loop forever)
    )
    return result

def verify(filepath, timeout=60):
    """Verify a file, return a clean verdict dict."""
    try:
        r = run_dafny(filepath, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"verified": False, "outcome": "timeout", "raw": ""}

    verified = (r.returncode == 0)
    return {
        "verified": verified,
        "outcome": "verified" if verified else "error",
        "raw": r.stdout + r.stderr,
    }

def verify_candidate(stripped_path, candidate, timeout=60):
    """Inject a candidate invariant into a stripped program and verify it."""
    with open(stripped_path) as f:
        template = f.read()

    if "// {{INVARIANT}}" not in template:
        raise ValueError(f"No marker found in {stripped_path}")

    # Dafny invariants are one clause per 'invariant' keyword.
    # A candidate may have several clauses separated by newlines.
    injected = "\n".join(f"    invariant {line.strip()}"
                         for line in candidate.strip().splitlines())

    filled = template.replace("// {{INVARIANT}}", injected)

    # Write to a temp file in the same folder (Dafny resolves paths locally).
    folder = os.path.dirname(os.path.abspath(stripped_path))
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".dfy", dir=folder, delete=False
    ) as tmp:
        tmp.write(filled)
        tmp_path = tmp.name

    try:
        return verify(tmp_path, timeout=timeout)
    finally:
        os.remove(tmp_path)   # clean up even if verify throws

def clause_survives(stripped_path, clause, timeout=60):
    """Does this single clause hold as a loop invariant on its own?"""
    verdict = verify_candidate(stripped_path, clause, timeout=timeout)
    # A clause 'survives' if injecting it alone produces no invariant-
    # preservation or entry failure. We detect that via a clean marker:
    # count how many errors mention 'invariant' + 'loop invariant violation'.
    raw = verdict["raw"]
    invariant_failed = "loop invariant" in raw and (
        "could not be proved to be maintained" in raw
        or "could not be proved on entry" in raw
    )
    return not invariant_failed

def verify_candidate_at_loop(stripped_source, loop_index, candidate, timeout=60):
    """Inject a candidate (one or more clauses) at a given loop in a REAL program
    (no marker), then verify. `candidate` may be a string or list of clauses."""
    if isinstance(candidate, str):
        clauses = [c for c in candidate.splitlines() if c.strip()]
    else:
        clauses = list(candidate)

    filled, status = inject_at_loop(stripped_source, loop_index, clauses)
    if status != "ok":
        return {"verified": False, "outcome": f"inject_{status}", "raw": ""}

    folder = os.path.abspath(".")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".dfy",
                                     dir=folder, delete=False) as tmp:
        tmp.write(filled)
        tmp_path = tmp.name
    try:
        return verify(tmp_path, timeout=timeout)
    finally:
        os.remove(tmp_path)


def houdini_at_loop(stripped_source, loop_index, candidates, timeout=30):
    """Two-phase Houdini with malformed-clause filtering.
    Phase 0: drop clauses that cause resolution/type errors in isolation
             (e.g. `a != null` on non-nullable arrays) so they can't poison the set.
    Phase 1: inject the whole clean pool; if it verifies, done.
    Phase 2: isolation-filter to sound clauses, verify that subset.
    """
    uniq = list(dict.fromkeys(c.strip() for c in candidates if c.strip()))
    if not uniq:
        return {"invariant": [], "verified": False, "raw": "", "survivors": []}

    def is_malformed(raw):
        # Resolution/type errors mean the clause is ill-formed, not just unsound.
        markers = [
            "must have a common supertype",
            "must be of a numeric type",
            "must have comparable types",
            "reference type",             # `!= null` on non-nullable
            "unresolved identifier",
            "unresolved",
            "resolution/type error",
            "arguments must",
            "type of the",
            "expected",                    # some parse errors
        ]
        return any(m in raw for m in markers)

    # Phase 0: drop malformed clauses (resolution/type errors in isolation).
    clean = []
    for c in uniq:
        v = verify_candidate_at_loop(stripped_source, loop_index, c, timeout)
        if v["verified"]:
            clean.append(c)                       # well-formed and sound alone
        elif not is_malformed(v["raw"]):
            clean.append(c)                       # well-formed but unsound alone: keep for Houdini
        # else: malformed -> drop it entirely
    if not clean:
        return {"invariant": [], "verified": False, "raw": "", "survivors": []}

    # Phase 1: whole clean pool at once.
    whole = verify_candidate_at_loop(stripped_source, loop_index, clean, timeout)
    if whole["verified"]:
        return {"invariant": clean, "verified": True,
                "raw": whole["raw"], "survivors": clean}

    # Phase 2: isolation sweep for sound clauses (from the clean set).
    def survives(clause):
        v = verify_candidate_at_loop(stripped_source, loop_index, clause, timeout)
        raw = v["raw"]
        if is_malformed(raw):
            return False
        inv_failed = "loop invariant" in raw and (
            "could not be proved to be maintained" in raw
            or "could not be proved on entry" in raw
        )
        return not inv_failed

    survivors = [c for c in clean if survives(c)]
    if not survivors:
        return {"invariant": [], "verified": False, "raw": "", "survivors": []}

    v = verify_candidate_at_loop(stripped_source, loop_index, survivors, timeout)
    if v["verified"]:
        return {"invariant": survivors, "verified": True,
                "raw": v["raw"], "survivors": survivors}

    # Phase 3 (Bug 2 fix): survivor set still failed. Greedily drop clauses that
    # break the combined proof, retry until it verifies or empties.
    working = list(survivors)
    for _ in range(len(survivors)):
        v = verify_candidate_at_loop(stripped_source, loop_index, working, timeout)
        if v["verified"]:
            return {"invariant": working, "verified": True,
                    "raw": v["raw"], "survivors": working}
        if is_malformed(v["raw"]) and len(working) > 1:
            # Remove the last-added clause and retry (crude but effective).
            working = working[:-1]
        else:
            break

    return {"invariant": survivors, "verified": False, "raw": v["raw"], "survivors": survivors}

def houdini(stripped_path, candidates, timeout=60):
    """
    Houdini via per-clause isolation: keep every candidate that holds as an
    invariant on its own, then verify the surviving set together.
    """
    uniq = list(dict.fromkeys(c.strip() for c in candidates if c.strip()))

    survivors = [c for c in uniq if clause_survives(stripped_path, c, timeout)]

    if survivors:
        verdict = verify_candidate(stripped_path, "\n".join(survivors), timeout=timeout)
        return {"invariant": survivors, "verified": verdict["verified"],
                "raw": verdict["raw"], "survivors": survivors}
    return {"invariant": [], "verified": False, "raw": "", "survivors": []}