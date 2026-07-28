import subprocess
import subprocess
import tempfile
import os

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

if __name__ == "__main__":
    # A messy candidate pool: the two real invariants plus three wrong ones.
    pool = [
        "s == i * i",              # wrong
        "0 <= i <= n",             # correct, needed
        "s == n * (n + 1) / 2",    # the postcondition — false mid-loop
        "s == i * (i + 1) / 2",    # correct, the key one
        "i < n",                   # the loop guard — false at exit
    ]
    result = houdini("Sum_stripped.dfy", pool)
    print("VERIFIED:", result["verified"])
    print("SURVIVORS:", result["invariant"])