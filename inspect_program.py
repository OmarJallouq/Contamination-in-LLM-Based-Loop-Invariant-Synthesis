"""
inspect_program.py — look at ONE real DafnyBench program in both forms so we
can see exactly what the stripping leaves behind and where a candidate must go.
Picks the smallest single-loop program from the manifest for readability.
"""
import os
import json

MANIFEST = os.path.expanduser("~/Developer/thesis/corpus_manifest.json")
REPO_DIR = os.path.expanduser("~/Developer/thesis/DafnyBench")

def gt_to_stripped(gt_path):
    """Map a ground_truth path to its hints_removed twin.
    DafnyBench convention: same name in hints_removed/, with _no_hints before .dfy.
    """
    p = gt_path.replace("/ground_truth/", "/hints_removed/")
    return p[:-len(".dfy")] + "_no_hints.dfy"

def main():
    with open(MANIFEST) as f:
        records = json.load(f)

    # Smallest single-loop program, for readability.
    singles = [r for r in records if r["n_loops"] == 1]
    singles.sort(key=lambda r: r["lines"])
    gt_path = singles[0]["path"]
    stripped_path = gt_to_stripped(gt_path)

    print("=" * 70)
    print("GROUND TRUTH (answer key):", os.path.basename(gt_path))
    print("=" * 70)
    with open(gt_path, encoding="utf-8", errors="replace") as f:
        print(f.read())

    print("=" * 70)
    print("HINTS REMOVED (what we feed the pipeline):",
          os.path.basename(stripped_path))
    print("=" * 70)
    if os.path.exists(stripped_path):
        with open(stripped_path, encoding="utf-8", errors="replace") as f:
            print(f.read())
    else:
        print("!! No matching hints_removed file at:", stripped_path)
        print("   (We'll need to fix the path mapping.)")

if __name__ == "__main__":
    main()