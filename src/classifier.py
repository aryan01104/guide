import openai, os, json, pathlib
DIGEST = pathlib.Path(__file__).parent.parent / "resources/persona_digest.txt"
PERSONA = DIGEST.read_text()

from .llm_client import chat, PERSONA
def classify_activity(activity: str) -> dict:
    sys = PERSONA + (
        "\n\nYou are an activity classifier. "
        "Return JSON {category, confidence, rationale}."
    )
    messages = [
        {"role": "system", "content": sys},
        {"role": "user""""
Classifies a single activity string into one of ~10 ‘lenses’
defined implicitly by the PERSONA_DIGEST.
Returns a dict: {category, confidence, rationale}
"""
import json, textwrap
from .llm_client import chat, PERSONA_DIGEST

SYS = PERSONA_DIGEST + textwrap.dedent("""
You are an activity classifier.
Output STRICT JSON with keys:
  category   # one of the lenses you described
  confidence # float 0–1
  rationale  # ≤30 words
""")

def classify(activity: str) -> dict:
    resp = chat(
        [
            {"role": "system", "content": SYS},
            {"role": "user",   "content": f"Activity: {activity}"}
        ],
        fmt="json",
        temperature=0
    )
    return json.loads(resp.choices[0].message.content)
, "content": f"Activity: {activity}"}
    ]
    resp = chat(messages, fmt="json", temp=0)
    return json.loads(resp.choices[0].message.content)