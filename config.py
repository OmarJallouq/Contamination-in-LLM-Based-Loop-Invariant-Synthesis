"""
config.py — central configuration for all thesis experiments.

Pins the models, corpus, parameters, and output locations so that every run is
reproducible and results are organized. For the final thesis, run each experiment
across ALL models on the FULL corpus by iterating MODELS and setting limit=None.
"""
import os

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# ---- Models to compare (the capability spread) -------------------------------
# Add/remove here; every experiment iterates this list for the final runs.
# Use pinned/paid model IDs for reproducibility in the final thesis.
MODELS = [
    "deepseek/deepseek-v4-flash",     # primary, cheap, fast
    # "openai/gpt-oss-120b",          # add for capability comparison
    # "anthropic/claude-sonnet-4.5",  # add a frontier point (costs more)
]

# ---- Corpus ------------------------------------------------------------------
CEILING_FILE = os.path.join(PROJECT_ROOT, "ceiling_results.json")
GROUND_TRUTH_DIR = os.path.join(
    PROJECT_ROOT, "DafnyBench/DafnyBench/dataset/ground_truth")
HINTS_REMOVED_DIR = os.path.join(
    PROJECT_ROOT, "DafnyBench/DafnyBench/dataset/hints_removed")

# ---- Run parameters ----------------------------------------------------------
DAFNY_TIMEOUT = 30          # seconds per verification
MAX_WORKERS = 8             # parallel workers
LLM_TEMPERATURE = 0.3       # match DafnyBench's setting for comparability
N_SEEDS = 3                 # repeat runs to measure nondeterminism (final: >=3)

# ---- Output organization -----------------------------------------------------
RESULTS_DIR = os.path.join(PROJECT_ROOT, "results")

def result_path(experiment, model, seed=None, limit=None):
    """Canonical path for a result file, encoding what produced it.

    e.g. results/contamination_rename__deepseek-v4-flash__full__seed0.json
    """
    os.makedirs(RESULTS_DIR, exist_ok=True)
    tag = model.replace("/", "-").replace(":", "-")
    scope = "full" if limit is None else f"n{limit}"
    seed_str = f"__seed{seed}" if seed is not None else ""
    return os.path.join(RESULTS_DIR,
                        f"{experiment}__{tag}__{scope}{seed_str}.json")

def gt_to_stripped(gt_path):
    return gt_path.replace("/ground_truth/", "/hints_removed/")[:-4] + "_no_hints.dfy"


RUNS = 2   # runs per condition; bump to 3 for final reportable runs