"""
llm_arm.py — LLM as candidate invariant generator.

Prompts a model for candidate loop invariants on a Dafny program, parses them,
and returns a candidate pool to feed into the same houdini_at_loop filter the
baseline uses. The LLM is just another candidate SOURCE; everything downstream
(injection, filtering, verification) is shared with the classical arm.
"""
import os
import re
from openai import OpenAI
import httpx

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ["OPENROUTER_API_KEY"],
    timeout=httpx.Timeout(60.0, connect=10.0, read=60.0, write=10.0, pool=10.0),
    max_retries=0,   # we do our own retry logic
)

# Development model (free, churn-tolerant). For final runs, pin a paid version.
DEFAULT_MODEL = "deepseek/deepseek-v4-flash"

PROMPT_TEMPLATE = """You are helping verify a Dafny program. The loop invariant\
(s) have been removed. Propose candidate loop invariants that would let Dafny\
verify this program.

Rules:
- Output ONLY invariant expressions, one per line.
- Each line is a single Dafny boolean expression (no "invariant" keyword).
- Do not include explanations, comments, markdown, or code fences.
- Propose several candidates; it is fine to include ones you are unsure about.

Program:
```dafny
{program}
```

Candidate invariants (one per line):"""


import time

def get_llm_candidates(stripped_source, model=DEFAULT_MODEL, max_retries=4, temperature=0.0, seed=42):
    """Ask the model for candidate invariants, with retry/backoff for rate
    limits and transient failures. Returns a list of clauses (possibly empty)."""
    prompt = PROMPT_TEMPLATE.format(program=stripped_source)
    for attempt in range(max_retries):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                seed=seed,
            )
            raw = resp.choices[0].message.content or ""
            return parse_candidates(raw)
        except Exception as e:
            msg = str(e).lower()
            # Rate limit or transient server error: back off and retry.
            if "rate" in msg or "429" in msg or "timeout" in msg or "503" in msg:
                wait = 2 ** attempt * 3   # 3s, 6s, 12s, 24s
                print(f"    [retry {attempt+1}/{max_retries} after {wait}s: {e}]")
                time.sleep(wait)
                continue
            # Other error: one retry then give up on this program.
            if attempt == 0:
                time.sleep(3)
                continue
            print(f"    [giving up: {e}]")
            return []
    return []

def parse_candidates(raw_text):
    """Extract invariant expressions from the model's free-text reply.

    Robust to common LLM formatting: code fences, 'invariant' keywords,
    bullets, numbering, blank lines.
    """
    lines = raw_text.splitlines()
    candidates = []
    for line in lines:
        s = line.strip()
        if not s:
            continue
        # Skip markdown fences and obvious prose.
        if s.startswith("```") or s.startswith("#"):
            continue
        # Strip leading bullets / numbering: "- ", "* ", "1. ", "1) "
        s = re.sub(r"^\s*[-*]\s+", "", s)
        s = re.sub(r"^\s*\d+[.)]\s+", "", s)
        # Strip a leading 'invariant' keyword if the model included it.
        s = re.sub(r"^\s*invariant\s+", "", s)
        # Drop trailing semicolons.
        s = s.rstrip(";").strip()
        # Heuristic: a real invariant contains a relational/logical operator.
        if re.search(r"(==|<=|>=|<|>|&&|\|\||==>|<==>|!=|forall|exists)", s):
            candidates.append(s)
    # Dedup, preserve order.
    seen, uniq = set(), []
    for c in candidates:
        if c not in seen:
            seen.add(c); uniq.append(c)
    return uniq


if __name__ == "__main__":
    # First real test: SquareRoot, which needs the NONLINEAR r*r<=N that
    # templates categorically could not express.
    path = ("DafnyBench/DafnyBench/dataset/hints_removed/"
            "Clover_integer_square_root_no_hints.dfy")
    src = open(path).read()

    print("=== PROGRAM ===")
    print(src)
    print("=== LLM CANDIDATES ===")
    cands = get_llm_candidates(src)
    for c in cands:
        print("  ", c)