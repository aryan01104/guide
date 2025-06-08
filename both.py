#!/usr/bin/env python3
"""Real-time behaviour monitor – Nietzsche *Genealogy* edition

One file = **logger + evaluator + notifier**
…"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import pathlib
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI

# ─── Constants ─────────────────────────────────────────────────
# Interval between GUI snapshots, thresholds for scoring, cache & log paths
WIN_POLL_INTERVAL: int = 5        # seconds between GUI samples
POS_THRESH: int = 4               # score ≥ this is "good"
NEG_THRESH: int = -4              # score ≤ this is "bad"
STREAK_LEN: int = 3               # consecutive count to trigger a streak
CACHE_DIR: pathlib.Path = pathlib.Path(".cache")  # caching LLM responses
LOG_PATH: pathlib.Path = pathlib.Path("data/behavior_log.csv")
DEFAULT_MODEL: str = "gpt-4.1" 


# Nietzschean rubric text and allowed categories for classification
PHILOSOPHY: str = (
    "Nietzsche, *On the Genealogy of Morality* rules:\n"
    "1. Life-affirming, power-expanding actions (master) are GOOD.\n"
    "2. Ressentiment-driven, herd-pleasing actions (slave) are BAD.\n"
    "3. Self-punishing asceticism is life-denying (score −).\n"
    "4. Self-overcoming discipline that strengthens will is positive (score +)."
)
CATEGORIES: List[str] = [
    "deep_work", "learning", "research", "admin", "break_fun", "social", "vice"
]
PROMPT_TMPL: str = (
    # Template injected with categories, philosopher text, and specific activity
    "You are a Nietzschean critic.\nCategories = {cats}.\nPhilosophy = {phil}\n\n"
    "Return ONLY a JSON object with keys:\n"
    "  category – one category\n  score – integer −5…5\n  reason – ≤ 12 words\n\n"
    "ACTIVITY: \"{activity}\"\n"
)

# ─── Initialization ──────────────────────────────────────────────
# Create cache dir, load .env, initialize OpenAI client
CACHE_DIR.mkdir(exist_ok=True)
load_dotenv()
openai: OpenAI = OpenAI()
print("[DEBUG] Environment loaded, OpenAI client initialized.")

# ─── Type Aliases ────────────────────────────────────────────────
Classification = Dict[str, Any]  # LLM JSON output shape
CsvRow = Dict[str, str]       # CSV row mapping

# ─── Helper Functions ───────────────────────────────────────────

def first_clause(text: Optional[str]) -> str:
    """
    Extracts substring before first '|' or returns text repr if not a string.
    """
    if not isinstance(text, str):
        return str(text or "")
    return text.split("|", 1)[0]


def sentence_from_row(row: CsvRow) -> str:
    """
    Normalizes a CSV row for activity to a human-readable sentence:
    - app_snapshot → 'Used this app'
    - browser_snaphot'  → 'Visited "title" in browser'
    """
    event = row.get("event", "")
    details = row.get("details", "")
    base = first_clause(details).strip()

    if event.startswith("browser_tab"):
        return f'Visited "{base}" in browser'
    if event.startswith("app_switch"):
        return f'Switched to {base}'
    if event.startswith("app_usage"):
        return f'Used {base}'
    return event


def cache_path(activity: str) -> pathlib.Path:
    """
    Returns cache file path for hashing an activity string.
    """
    name = hashlib.sha1(activity.encode()).hexdigest() + ".json"
    return CACHE_DIR / name

# ─── Classification via LLM ─────────────────────────────────────

def call_llm(activity: str, model: str = DEFAULT_MODEL) -> Classification:
    """
    Sends a classificaton request prompt to llm and then parses its JSON output.
    """
    prompt = PROMPT_TMPL.format(cats=CATEGORIES, phil=PHILOSOPHY, activity=activity)
    print(f"[DEBUG] Calling LLM with model={model}, prompt snippet={prompt[:30]}...")
    resp = openai.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0,
    )
    return json.loads(resp.choices[0].message.content)


def classify(activity: str, model: str = DEFAULT_MODEL) -> Classification:
    """
    Caches LLM responses to avoid re-querying the same activity.
    On cache miss, calls `call_llm`, handles exceptions, and writes result to disk.
    """
    path = cache_path(activity)
    if path.exists():
        print(f"[DEBUG] Cache hit for activity: '{activity}'")
        return json.loads(path.read_text())
    print(f"[DEBUG] Cache miss, calling LLM for: '{activity}'")
    try:
        result = call_llm(activity, model)
    except Exception as e:
        print(f"[DEBUG] LLM call failed: {e}")
        result = {"category": "unknown", "score": 0, "reason": "llm_error"}
    path.write_text(json.dumps(result))
    print(f"[DEBUG] LLM result cached for: '{activity}' -> {result}")
    return result

# ─── Streak Tracking & Notifications ───────────────────────────
class Streak:
    """Tracks consecutive good/bad scores and issues notifications on streaks/flips."""
    def __init__(self) -> None:
        self.pos_count = 0      # number of consecutive positive scores
        self.neg_count = 0      # number of consecutive negative scores
        self.state = "neutral"  # 'neutral', 'good', or 'bad'
        print("[DEBUG] Streak tracker initialized.")

    def update(self, score: int, sentence: str, reason: str) -> None:
        """
        Update streak counts based on thresholds and call `notify` when:
        - Sustained good (pos_count == STREAK_LEN)
        - Sustained bad (neg_count == STREAK_LEN)
        - Trend reversal (good→neutral or bad→neutral)
        """
        print(f"[DEBUG] Streak.update called - score={score}, state={self.state}, pos={self.pos_count}, neg={self.neg_count}")
        # Bucket the score
        if score >= POS_THRESH:
            self.pos_count += 1; self.neg_count = 0
        elif score <= NEG_THRESH:
            self.neg_count += 1; self.pos_count = 0
        else:
            self.pos_count = self.neg_count = 0
        print(f"[DEBUG] After bucketing - pos={self.pos_count}, neg={self.neg_count}")

        # Check for sustained streaks
        if self.pos_count == STREAK_LEN and self.state != "good":
            print("[DEBUG] Triggering sustained good notification.")
            notify(f"🔥 {STREAK_LEN} life-affirming acts in a row!", title="Nietzsche approves ✨")
            self.state = "good"
        if self.neg_count == STREAK_LEN and self.state != "bad":
            print("[DEBUG] Triggering sustained bad notification.")
            notify(f"⚠️ {STREAK_LEN} life-demining acts:\n{sentence}\nBecause: {reason}", title="Slave-morality alert 🕱")
            self.state = "bad"

        # Trend reversal notifications
        if self.state == "good" and self.neg_count == 1:
            print("[DEBUG] Triggering trend flip: good -> neutral.")
            notify("Good streak broken – stay vigilant.")
            self.state = "neutral"
        if self.state == "bad" and self.pos_count == 1:
            print("[DEBUG] Triggering trend flip: bad -> neutral.")
            notify("🎉 First positive after bad streak – well done!")
            self.state = "neutral"

# ─── Notification Stub (macOS pync or no-op) ───────────────────
try:
    from pync import Notifier
    def notify(msg: str, *, title: str = "Activity coach") -> None:
        print(f"[DEBUG] notify called – msg={msg!r}, title={title!r}")
        Notifier.notify(msg, title=title)
except ImportError:
    def notify(msg: str, *, title: str = "Activity coach") -> None:
        print(f"[DEBUG] notify stub called – msg={msg!r}, title={title!r}")
        return

# ─── Logger Thread (Desktop activity sampling) ───────────——
def start_logger(stop_event: threading.Event) -> threading.Thread:
    """
    Spawn a daemon thread that samples the active window or Chrome tab every
    WIN_POLL_INTERVAL seconds and appends rows to the CSV log with columns:
    timestamp, event, details
    """
    print("[DEBUG] start_logger invoked.")
    def _thread_body() -> None:
        # Ensure directory and CSV exist
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_PATH, "a", newline="") as f:
            writer = csv.writer(f)
            if os.stat(LOG_PATH).st_size == 0:
                writer.writerow(["timestamp", "event", "details"])
                f.flush()
            # Loop until stop_event is set
            while not stop_event.is_set():
                ts = dt.datetime.now().isoformat()
                event, details = "app_snapshot", "Unknown"
                try:
                    from pygetwindow import getActiveWindow
                    window = getActiveWindow()
                    details = window.title if window else "Unknown"
                except Exception:
                    details = "Unknown"
                # If Chrome, get tab via AppleScript
                if "Chrome" in details:
                    title, url = _get_chrome_tab()
                    event, details = "browser_tab_snapshot", f"{title}|{url}"
                writer.writerow([ts, event, details])
                f.flush()
                time.sleep(WIN_POLL_INTERVAL)
    stop_event.clear()
    thread = threading.Thread(target=_thread_body, daemon=True)
    thread.start()
    return thread


def _get_chrome_tab() -> Tuple[str, str]:
    """
    macOS-only: uses AppleScript to fetch the title and URL of\ the active Chrome tab.
    Returns (title, url) or ("Unknown","Unknown") on failure.
    """
    print("[DEBUG] _get_chrome_tab called.")
    script = (
        'tell application "Google Chrome"\n'
        'if not (exists window 1) then return "Unknown||Unknown"\n'
        'set t to title of active tab of front window\n'
        'set u to URL of active tab of front window\n'
        'return t & "||" & u\n'
        'end tell'
    )
    try:
        import subprocess
        out = subprocess.check_output(["osascript", "-e", script])
        title, url = out.decode().strip().split("||", 1)
    except Exception:
        title, url = ("Unknown", "Unknown")
    return title, url

# ─── Real-Time Log Evaluator ───────────────────────────────────
def evaluate_live(model: str, process_existing: bool) -> None:
    """
    Tail the CSV logfile in real-time and classify each new row:
    - If process_existing, classify existing rows first
    - Then loop reading f.readline(), parse via csv.reader, classify & update streak
    """
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    streak = Streak()

    with open(LOG_PATH, "r", newline="") as f:
        reader = csv.DictReader(f)
        # Optionally process file history
        if process_existing:
            for row in reader:
