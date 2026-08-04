"""
reproduce_dafnybench.py — faithful replica of DafnyBench's eval/fill_hints.py
protocol, using OpenRouter instead of sglang (which won't install on Apple Silicon).

Same prompt, same cheating-check, same verification criterion, same 3-turn
repair loop, same benchmark, same Dafny verifier. Only the LLM transport differs.
"""
import os, re, json, time, subprocess, tempfile
from openai import OpenAI

client = OpenAI(base_url="https://openrouter.ai/api/v1",
                api_key=os.environ["OPENROUTER_API_KEY"])

DAFNY = "/opt/homebrew/bin/dafny"   # adjust if yours differs
HINTS_DIR = "DafnyBench/DafnyBench/dataset/hints_removed"

# --- Their exact prompts (copied from sys_prompts.py) ---
SYS_DAFNY = ("You are an expert in Dafny. You will be given tasks dealing with "
             "Dafny programs including precise annotations.\n")
GEN_HINTS_FROM_BODY = (
    "Given a Dafny program with function signature, preconditions, postconditions, "
    "and code, but with annotations missing. Please return a complete Dafny program "
    "with the strongest possible annotations (loop invariants, assert statements, etc.) "
    "filled back in. Do not explain. Please use exactly the same function signature, "
    "preconditions, and postconditions. Do not ever modify the given lines. "
    "Below is the program:\n")

# Their exact appended helper (from utils.py)
HELPER = "\nfunction abs(a: real) : real {if a>0.0 then a else -a}\n"


def extract_code(reply):
    """Their extract_code_from_llm_output logic."""
    for tag in ("```dafny", "```Dafny", "```"):
        i = reply.find(tag)
        if i != -1:
            reply = reply[i + len(tag):]
            j = reply.find("```")
            return reply[:j] if j != -1 else reply
    return reply


def run_dafny(program):
    """Their run_dafny: append helper, verify with /compile:0."""
    with tempfile.NamedTemporaryFile("w", suffix=".dfy", dir=".", delete=False) as f:
        f.write(program + HELPER)
        tmp = f.name
    try:
        r = subprocess.run(f"{DAFNY} verify {tmp}", shell=True,
                           capture_output=True, timeout=30)
        return r.stdout.decode() + r.stderr.decode()
    except Exception as e:
        return str(e)
    finally:
        os.remove(tmp)


def is_verified(msg):
    return "verified, 0 errors" in msg and "File contains no code" not in msg


def check_no_cheating(body, recon):
    """Their exact check: specs preserved + no verify-avoidance."""
    def specs(text):
        out, in_doc = [], False
        for line in text.split("\n"):
            if line.strip().startswith("/*"): in_doc = not in_doc
            is_c = line.strip().startswith("//")
            if ("requires" in line or "ensures" in line) and not in_doc and not is_c:
                out.append(line.strip().replace(" ", ""))
            if line.strip().endswith("*/"): in_doc = not in_doc
        return out
    spec_preserved = specs(body) == specs(recon)
    no_avoid = "{:verify false}" not in recon and "assume false" not in recon
    return spec_preserved, no_avoid


def fill_hints(test_file, model, feedback_turns=3):
    """Their fill_hints protocol: generate, verify, repair up to N turns."""
    with open(os.path.join(HINTS_DIR, test_file)) as f:
        body = f.read()

    messages = [{"role": "system", "content": SYS_DAFNY},
                {"role": "user", "content": GEN_HINTS_FROM_BODY + body}]

    for attempt in range(1, feedback_turns + 1):
        resp = client.chat.completions.create(model=model, messages=messages,
                                              max_tokens=4096, temperature=0.3)
        reply = resp.choices[0].message.content or ""
        recon = extract_code(reply)
        messages.append({"role": "assistant", "content": recon})

        out = run_dafny(recon)
        spec_ok, no_cheat = check_no_cheating(body, recon)

        if is_verified(out) and spec_ok and no_cheat:
            return {"verified": True, "attempt": attempt}

        # Their exact feedback messages.
        fb = ""
        if not is_verified(out):
            fb += "This answer got Dafny verification error:\n" + out + "\nPlease try again by taking the Dafny feedback.\n"
        if not spec_ok:
            fb += "Please keep the preconditions and postconditions the same as the original program, or you fail the test.\n"
        if not no_cheat:
            fb += "Please don't use {:verify false} or assume false."
        messages.append({"role": "user", "content": fb})

    return {"verified": False, "attempt": "failed"}


def run(model="deepseek/deepseek-v4-flash", limit=20):
    files = sorted(f for f in os.listdir(HINTS_DIR) if f.endswith(".dfy"))[:limit]
    print(f"Reproducing DafnyBench protocol: {len(files)} programs, model={model}\n")

    solved = 0
    for i, tf in enumerate(files, 1):
        try:
            r = fill_hints(tf, model)
            if r["verified"]:
                solved += 1
            print(f"  [{i}/{len(files)}] {'OK ' if r['verified'] else 'no '} "
                  f"(attempt {r['attempt']})  solved {solved}  {tf[:40]}")
        except Exception as e:
            print(f"  [{i}/{len(files)}] ERR {e}  {tf[:40]}")

    print(f"\n{'='*50}")
    print(f"Success rate: {solved}/{len(files)} = {100*solved/len(files):.1f}%")
    print(f"{'='*50}")

if __name__ == "__main__":
    import sys
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    run(limit=limit)