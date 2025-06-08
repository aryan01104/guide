#!/usr/bin/env python3
"""Activity evaluator (Nietzsche – Genealogy of Morality edition)

Adds **streak‑aware notifications**:
• sustained good streak → short praise pop‑up
• sustained bad streak  → longer warning (includes *why* it violates Nietzsche)
• trend flip (good→bad or bad→good) → change‑of‑trend pop‑up

Change the window/threshold via the constants near the top.

Run:
    python activity_evaluator_nietzsche.py --in raw.csv --out scored.csv
"""
from __future__ import annotations

import argparse, hashlib, json, pathlib
from typing import Any, Dict, List

import pandas as pd
from openai import OpenAI
from dotenv import load_dotenv

# ── Optional notifications ────────────────────────────────────
try:
    from pync import Notifier  # macOS
    def notify(msg: str, *, title: str = "Activity coach") -> None:
        Notifier.notify(msg, title=title)
except ImportError:  # non‑macOS → silent
    def notify(msg: str, *, title: str = "Activity coach") -> None:  # type: ignore
        return None

# ── Environment & OpenAI client ────────────────────────────────
load_dotenv()
openai = OpenAI()

# ── Tunables ───────────────────────────────────────────────────
DEFAULT_MODEL   = "gpt-4o-mini"
CACHE_DIR       = pathlib.Path(".cache"); CACHE_DIR.mkdir(exist_ok=True)
POS_THRESH      = 4          # ≥  +4 counts as good
NEG_THRESH      = -4         # ≤  –4 counts as bad
STREAK_LEN      = 3          # how many consecutive events constitute "sustained"

# ── Nietzsche rubric & prompt ──────────────────────────────────
PHILOSOPHY = (
    "Nietzsche, *On the Genealogy of Morality* — 4 diagnostic rules:\n"
    "1. Life‑affirming, creative, power‑expanding actions (master morality) are GOOD.\n"
    "2. Reactive, ressentiment‑driven, herd‑pleasing actions (slave morality) are BAD.\n"
    "3. Guilt‑ridden self‑punishment & excessive asceticism are life‑denying (score −).\n"
    "4. Self‑overcoming discipline that strengthens one’s will is positive (score +)."
)
CATEGORIES = ["deep_work", "learning", "research", "admin", "break_fun", "social", "vice"]
PROMPT_TMPL = (
    "You are a Nietzschean critic.\nCategories = {cats}.\nPhilosophy = {phil}\n\n"
    "Return ONLY a JSON object with keys:\n"
    "  category – one of the categories\n  score    – integer −5…5 (positive = life‑affirming)\n  reason   – ≤ 12 words\n\n"
    "ACTIVITY: \"{activity}\"\n"
)

# ── Helpers ────────────────────────────────────────────────────

def first_clause(text: str) -> str:
    return text.split("|")[0] if isinstance(text, str) else text


def sentence_from_row(row: pd.Series) -> str:
    event, details = row["event"], row.get("details", "")
    if event.startswith("browser_tab"):
        return f'Visited "{first_clause(details)}" in browser'
    if event.startswith("app_switch"):
        return f'Switched to {first_clause(details).strip()}'
    if event.startswith("app_usage"):
        return f'Used {first_clause(details).strip()}'
    return event


def cache_file(text: str) -> pathlib.Path:
    return CACHE_DIR / f"{hashlib.sha1(text.encode()).hexdigest()}.json"


# ── LLM wrapper with caching ───────────────────────────────────

def call_llm(activity: str, model: str = DEFAULT_MODEL) -> Dict[str, Any]:
    prompt = PROMPT_TMPL.format(cats=CATEGORIES, phil=PHILOSOPHY, activity=activity)
    resp = openai.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0,
    )
    return json.loads(resp.choices[0].message.content)


def classify(activity: str, model: str = DEFAULT_MODEL) -> Dict[str, Any]:
    path = cache_file(activity)
    if path.exists():
        return json.loads(path.read_text())
    try:
        result = call_llm(activity, model)
    except Exception as e:
        print("LLM error:", e)
        result = {"category": "unknown", "score": 0, "reason": "llm_error"}
    path.write_text(json.dumps(result))
    return result

# ── Streak tracker ─────────────────────────────────────────────
class Streak:
    """Track consecutive good / bad scores and trend flips."""
    def __init__(self) -> None:
        self.pos = 0
        self.neg = 0
        self.state = "neutral"  # neutral | good | bad

    def update(self, score: int, sentence: str, reason: str) -> None:
        # increment appropriate counter
        if score >= POS_THRESH:
            self.pos += 1; self.neg = 0
        elif score <= NEG_THRESH:
            self.neg += 1; self.pos = 0
        else:
            self.pos = self.neg = 0

        # sustained good
        if self.pos == STREAK_LEN and self.state != "good":
            notify(f"🔥 {STREAK_LEN} strong, life‑affirming actions in a row! Keep going.",
                   title="Nietzsche approves ✨")
            self.state = "good"
        # sustained bad
        if self.neg == STREAK_LEN and self.state != "bad":
            notify(
                f"⚠️ Streak of {STREAK_LEN} life‑denying actions:\n{sentence}\nBecause: {reason}",
                title="Slave‑morality alert 🕱",
            )
            self.state = "bad"
        # trend reversal
        if self.state == "good" and self.neg == 1:
            notify("Trend change: good streak broken – stay vigilant.")
            self.state = "neutral"
        if self.state == "bad" and self.pos == 1:
            notify("🎉 Turning the tide – first positive after a bad patch")
            self.state = "neutral"

# ── Main processing ────────────────────────────────────────────

def process(inp: str, out: str, *, model: str, limit: int | None) -> None:
    df = pd.read_csv(inp)
    if limit:
        df = df.head(limit)

    streak = Streak()
    enriched: List[pd.Series] = []

    for _, row in df.iterrows():
        sent = sentence_from_row(row)
        res  = classify(sent, model)
        row["ai_category"], row["ai_score"], row["ai_reason"] = res.values()
        enriched.append(row)
        streak.update(res["score"], sent, res["reason"])

    pd.DataFrame(enriched).to_csv(out, index=False)
    print(f"✓ Scored file saved to {out}")

# ── CLI ────────────────────────────────────────────────────────

def cli() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Nietzsche activity scorer with streak notifications")
    p.add_argument("--in", dest="inp", default="data/behavior_log.csv")
    p.add_argument("--out", dest="out", default="activity_log_scored.csv")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--limit", type=int)
    return p.parse_args()


def main() -> None:
    a = cli(); process(a.inp, a.out, model=a.model, limit=a.limit)

if __name__ == "__main__":
    main()
