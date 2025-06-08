"""Thin wrapper around the Chat Completions API."""
import openai, json
from .config import OPENAI_KEY, MODEL, ROOT

openai.api_key = OPENAI_KEY

# preload the book digest so we don’t read disk on every call
PERSONA_DIGEST = (ROOT / "resources/persona_digest.txt").read_text()

def chat(messages, *, fmt=None, temperature=0):
    """fmt='json' forces valid-JSON replies (OpenAI native parameter)."""
    return openai.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=temperature,
        response_format=({"type": "json_object"} if fmt == "json" else None),
    )
