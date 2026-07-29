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

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ["OPENROUTER_API_KEY"],
)

# Development model (free, churn-tolerant). For final runs, pin a paid version.
DEFAULT_MODEL = "openai/gpt-oss-20b:free"

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


def get_llm_candidates(stripped_source, model=DEFAULT_MODEL, n_candidates_hint=8):
    """Ask the model for candidate invariants; return a clean list of clauses."""
    prompt = PROMPT_TEMPLATE.format(program=stripped_source)
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = resp.choices[0].message.content
    return parse_candidates(raw)


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