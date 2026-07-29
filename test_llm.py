"""test_llm.py — confirm we can reach a model through OpenRouter."""
import os
from openai import OpenAI

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ["OPENROUTER_API_KEY"],
)

resp = client.chat.completions.create(
    model="openai/gpt-oss-20b:free",
    messages=[{"role": "user", "content": "Reply with exactly the word: works"}],
)
print("MODEL SAID:", resp.choices[0].message.content)