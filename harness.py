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


def houdini_at_loop(stripped_source, loop_index, candidates, timeout=60):
    """Houdini filter operating on a REAL program at a specific loop.
    Same isolation logic as houdini(), but injects via inject_at_loop."""
    uniq = list(dict.fromkeys(c.strip() for c in candidates if c.strip()))

    def survives(clause):
        v = verify_candidate_at_loop(stripped_source, loop_index, clause, timeout)
        raw = v["raw"]
        inv_failed = "loop invariant" in raw and (
            "could not be proved to be maintained" in raw
            or "could not be proved on entry" in raw
        )
        return not inv_failed

    survivors = [c for c in uniq if survives(c)]

    if survivors:
        v = verify_candidate_at_loop(stripped_source, loop_index, survivors, timeout)
        return {"invariant": survivors, "verified": v["verified"],
                "raw": v["raw"], "survivors": survivors}
    return {"invariant": [], "verified": False, "raw": "", "survivors": []}

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