"""
LLM backend abstraction.

Supports two backends:
  - Ollama  (default): http://localhost:11434/api/generate
  - LM Studio:         http://localhost:1234/v1/chat/completions  (OpenAI-compatible)

Set in .env:
  LLM_BACKEND=lmstudio        # or "ollama"
  LLM_MODEL=meta-llama-3.1-8b-instruct   # model name loaded in LM Studio
  LLM_URL=http://localhost:1234           # optional override for the base URL

LM Studio is preferred on Apple Silicon — it uses the MLX backend for GPU acceleration,
running models 3–5× faster than Ollama on M-series chips.

To use LM Studio:
  1. Open LM Studio → load a model (e.g. Meta-Llama-3.1-8B-Instruct-Q4)
  2. Start the local server (Server tab → Start)
  3. Set LLM_BACKEND=lmstudio in .env
"""

import os
import json
import re
import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# ── Config ────────────────────────────────────────────────────────────────────
_BACKEND    = os.getenv("LLM_BACKEND", "ollama").lower().strip()
_MODEL      = os.getenv("LLM_MODEL",   "llama3.1:8b")  # default for Ollama; override for LM Studio
_LM_BASE    = os.getenv("LLM_URL",     "http://localhost:1234")
_OLLAMA_URL = "http://localhost:11434/api/generate"
_LM_URL     = f"{_LM_BASE}/v1/chat/completions"

_TEMPERATURE  = 0.1   # low temp = consistent, factual
_MAX_TOKENS   = 800   # was 1500 — QA JSON output rarely needs more than 600 tokens
_CTX_LENGTH   = 12288  # override LM Studio's default 4096 — sized for chatbot KB (~9k tokens) + conversation

# TODO (optimisation — Option 2): Add prefix/prompt caching.
# The system prompt + KB loaded per batch is already shared across all conversations
# in the same batch run (KB loaded once, passed in). The next level is KV-cache reuse:
#
# - Ollama: KV cache is active automatically when the same prefix is reused within a session.
#   No code change needed — just keep calling the same model back-to-back.
# - LM Studio: use stateful sessions once officially supported (track via session_id header).
# - At scale (> 500 convos/day): consider RAG — embed KB into a vector store and retrieve
#   only the 5-10 relevant facts per conversation. Expected token saving: ~70%.
#
# Trigger to implement RAG: when Ollama total token throughput exceeds 100k tokens/cycle.


# ════════════════════════════════════════════════════════════════════════════
# BACKEND IMPLEMENTATIONS
# ════════════════════════════════════════════════════════════════════════════

def _ask_ollama(prompt: str) -> str:
    payload = {
        "model":  _MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": _TEMPERATURE,
            "num_predict": _MAX_TOKENS,
        }
    }
    response = requests.post(_OLLAMA_URL, json=payload, timeout=120)
    response.raise_for_status()
    return response.json()["response"].strip()


def _ask_lmstudio(prompt: str, system: str = None) -> str:
    """
    LM Studio uses the OpenAI chat/completions API.

    If `system` is provided, it is placed in the system message (cached by KV cache).
    Only the `prompt` (conversation/query) goes in the user message.

    This means for a batch of N conversations with the same KB:
      - System message (KB + agent prompt): processed ONCE, cached
      - User message (conversation only ~500 tokens): processed N times
      - Token saving: ~93% vs sending everything in user message each time
    """
    system_content = system if system else "You are a precise JSON-producing assistant. Return only valid JSON, nothing else."
    payload = {
        "model": _MODEL,
        "messages": [
            {
                "role":    "system",
                "content": system_content
            },
            {
                "role":    "user",
                "content": prompt
            }
        ],
        "temperature": _TEMPERATURE,
        "max_tokens":  _MAX_TOKENS,
        "stream":      False,
        "num_ctx":     _CTX_LENGTH,
    }
    response = requests.post(_LM_URL, json=payload, timeout=45)
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"].strip()


# ════════════════════════════════════════════════════════════════════════════
# PUBLIC INTERFACE
# ════════════════════════════════════════════════════════════════════════════

def ask(prompt: str, expect_json: bool = True, system: str = None) -> str:
    """
    Call the configured LLM backend and return the raw text response.

    `system` — if provided, sent as the system message (KB/agent prompt).
               Only the conversation goes in `prompt` (user message).
               Dramatically reduces tokens processed per call via KV cache.
    """
    if _BACKEND == "lmstudio":
        raw = _ask_lmstudio(prompt, system=system)
    else:
        raw = _ask_ollama(prompt)

    if expect_json:
        raw = _extract_json(raw)
    return raw


def ask_json(prompt: str, retries: int = 2, system: str = None) -> dict:
    """
    Call the LLM and parse the result as JSON.
    Retries up to `retries` times if the response isn't valid JSON.

    `system` — if provided, sent as the system message (see ask()).
    """
    last_error = None
    for attempt in range(retries + 1):
        try:
            raw = ask(prompt, expect_json=True, system=system)
            return json.loads(raw)
        except json.JSONDecodeError as e:
            last_error = e
            if attempt < retries:
                print(f"[LLM] JSON parse failed on attempt {attempt + 1}/{retries + 1} — retrying...")
    raise ValueError(f"LLM returned non-JSON after {retries + 1} attempts: {last_error}")


# ════════════════════════════════════════════════════════════════════════════
# JSON EXTRACTION
# ════════════════════════════════════════════════════════════════════════════

def _extract_json(raw: str) -> str:
    """
    Pull the first valid JSON object or array out of whatever the LLM returned.
    Handles: markdown fences, leading/trailing prose, nested objects.
    """
    # 1. Strip markdown code fences
    fence = re.search(r'```(?:json)?\s*([\s\S]*?)```', raw)
    if fence:
        raw = fence.group(1).strip()

    # 2. Try as-is (cheapest path)
    try:
        json.loads(raw)
        return raw
    except json.JSONDecodeError:
        pass

    # 3. Find the outermost { ... } with brace matching
    start = raw.find('{')
    if start != -1:
        depth = 0
        for i, ch in enumerate(raw[start:], start):
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    candidate = raw[start:i + 1]
                    try:
                        json.loads(candidate)
                        return candidate
                    except json.JSONDecodeError:
                        break

    # 4. Try outermost [ ... ]
    start = raw.find('[')
    if start != -1:
        depth = 0
        for i, ch in enumerate(raw[start:], start):
            if ch == '[':
                depth += 1
            elif ch == ']':
                depth -= 1
                if depth == 0:
                    candidate = raw[start:i + 1]
                    try:
                        json.loads(candidate)
                        return candidate
                    except json.JSONDecodeError:
                        break

    # 5. Nothing worked — return raw and let ask_json raise a clear error
    return raw


# ════════════════════════════════════════════════════════════════════════════
# STARTUP LOG
# ════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print(f"[LLM] Backend: {_BACKEND}")
    print(f"[LLM] Model  : {_MODEL}")
    print(f"[LLM] URL    : {_LM_URL if _BACKEND == 'lmstudio' else _OLLAMA_URL}")
