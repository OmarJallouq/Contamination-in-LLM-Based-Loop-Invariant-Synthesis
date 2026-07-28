"""
fetch_corpus.py — pull DafnyBench and report what's usable for our study.
Run once. It clones the repo (if absent), scans hints_removed for programs
that actually contain a loop, and prints a summary so we know our corpus size
before building anything on top of it.
"""
import os
import re
import subprocess
import json

REPO_URL = "https://github.com/sun-wendy/DafnyBench.git"
REPO_DIR = os.path.expanduser("~/Developer/thesis/DafnyBench")

def ensure_repo():
    """Clone DafnyBench if we don't have it yet."""
    if os.path.isdir(REPO_DIR):
        print(f"Repo already present at {REPO_DIR}")
        return
    print("Cloning DafnyBench (this may take a minute)...")
    subprocess.run(["git", "clone", "--depth", "1", REPO_URL, REPO_DIR], check=True)

def find_dfy_files(root):
    """All .dfy files under a directory."""
    hits = []
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            if fn.endswith(".dfy"):
                hits.append(os.path.join(dirpath, fn))
    return hits

# A program is 'loop-bearing' if it has a while/for loop.
LOOP_RE = re.compile(r"\b(while|for)\b")
# We also note whether the ground-truth version had an invariant at all.
INVARIANT_RE = re.compile(r"\binvariant\b")

def classify(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    return {
        "path": path,
        "has_loop": bool(LOOP_RE.search(text)),
        "has_invariant": bool(INVARIANT_RE.search(text)),
        "lines": text.count("\n") + 1,
        "n_loops": len(LOOP_RE.findall(text)),
        "n_invariants": len(INVARIANT_RE.findall(text)),
    }

def main():
    ensure_repo()

    # DafnyBench ships ground_truth (answers) and hints_removed (stripped).
    # Find both folders wherever they live in the repo tree.
    ground_truth_dirs, hints_removed_dirs = [], []
    for dirpath, dirnames, _ in os.walk(REPO_DIR):
        for d in dirnames:
            if d == "ground_truth":
                ground_truth_dirs.append(os.path.join(dirpath, d))
            if d == "hints_removed":
                hints_removed_dirs.append(os.path.join(dirpath, d))

    print("\n=== FOLDERS FOUND ===")
    print("ground_truth:", ground_truth_dirs)
    print("hints_removed:", hints_removed_dirs)

    if not ground_truth_dirs:
        print("\n!! Couldn't find ground_truth folder. Let's inspect the repo layout:")
        subprocess.run(["ls", "-la", REPO_DIR])
        return

    gt_files = []
    for d in ground_truth_dirs:
        gt_files += find_dfy_files(d)

    print(f"\n=== SCANNING {len(gt_files)} ground_truth programs ===")
    records = [classify(p) for p in gt_files]

    total = len(records)
    with_loop = [r for r in records if r["has_loop"]]
    with_loop_and_inv = [r for r in records if r["has_loop"] and r["has_invariant"]]
    single_loop = [r for r in with_loop_and_inv if r["n_loops"] == 1]
    multi_loop = [r for r in with_loop_and_inv if r["n_loops"] > 1]

    print(f"Total programs:              {total}")
    print(f"  ...with a loop:            {len(with_loop)}")
    print(f"  ...with loop + invariant:  {len(with_loop_and_inv)}   <- candidate corpus")
    print(f"       of which single-loop: {len(single_loop)}")
    print(f"       of which multi-loop:  {len(multi_loop)}")

    # Save the candidate corpus manifest for later steps.
    manifest = os.path.expanduser("~/Developer/thesis/corpus_manifest.json")
    with open(manifest, "w") as f:
        json.dump(with_loop_and_inv, f, indent=2)
    print(f"\nWrote manifest of {len(with_loop_and_inv)} programs to {manifest}")

    # Show a few examples across the size range so we can eyeball difficulty.
    with_loop_and_inv.sort(key=lambda r: r["lines"])
    print("\n=== SAMPLE (smallest, median, largest) ===")
    if with_loop_and_inv:
        picks = [with_loop_and_inv[0],
                 with_loop_and_inv[len(with_loop_and_inv)//2],
                 with_loop_and_inv[-1]]
        for r in picks:
            print(f"  {r['lines']:4d} lines, {r['n_loops']} loop(s), "
                  f"{r['n_invariants']} invariant(s): {os.path.basename(r['path'])}")

if __name__ == "__main__":
    main()