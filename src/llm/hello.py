"""Stage 0 smoke test: prove the configured model answers.

Run from the repo root:  .venv/bin/python src/llm/hello.py
Reads LLM_BASE_URL, LLM_API_KEY and LLM_MODEL from .env. Never prints the key.
"""
import os

from dotenv import load_dotenv
from openai import OpenAI


load_dotenv()

client = OpenAI(
    base_url=os.environ["LLM_BASE_URL"],
    api_key=os.environ["LLM_API_KEY"],
    timeout=30.0,   # the SDK default is 10 minutes
    max_retries=0,  # no silent SDK retries; our own policy comes in Stage 4
)

res = client.chat.completions.create(
    model=os.environ["LLM_MODEL"],
    messages=[{"role": "user", "content": "Reply with exactly the word: ready"}],
    temperature=0,
)

print(res.choices[0].message.content)
print(f"model={res.model} usage={res.usage}")
