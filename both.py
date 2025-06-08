#!/usr/bin/env python3
"""Real‑time behaviour monitor – Nietzsche *Genealogy* edition

One file = **logger + evaluator + notifier**
-------------------------------------------------
• Starts an internal *logger* thread that samples the active window / Chrome tab every
  `WIN_POLL_INTERVAL` seconds and appends to `data/behavior_log.csv`.
• The *evaluator* thread tails that CSV and, row‑by‑row, classifies each activity
  with a GPT rubric derived from Nietzsche and fires **streak‑aware notifications**.

Run it once:
    python monitor_nietzsche.py

If you already have a logger running separately you can disable the built‑in logger
with `--no-log`.
"""
from __future__ import annotations

import argparse, csv, datetime as dt, hashlib, json, os, pathlib, queue, threading, time
from typing import Any, Dict, List

import pandas as pd
from openai import OpenAI
from dotenv import load_dotenv

# ─── Optional notifications (macOS → pync) ────────────────────
try:
    from pync import Notifier  # macOS only
    def notify(msg: str, *, title: str = "Activity coach") -> None:
        Notifier.notify(msg, title=title)
except ImportError:  # Linux/Windows → silent stub
    def notify(msg: str, *, title: str = "Activity coach") -> None:  # type: ignore
        return None

# ─── GPT / environment ────────────────────────────────────────
load_dotenv()
openai = OpenAI()

# ─── Tunables ─────────────────────────────────────────────────
DEFAULT_MODEL   = "gpt-4o-mini"
CACHE_DIR       = pathlib.Path(".cache"); CACHE_DIR.mkdir(exist_ok=True)
LOG_PATH        = pathlib.Path("data/behavior_log.csv")
WIN_POLL_INTERVAL = 5       # seconds between GUI samples
POS_THRESH      = 4           # good ≥ +4
NEG_THRESH      = -4          # bad ≤ –4
STREAK_LEN      = 3           # consecutive events → sustained

# ─── Nietzsche rubric ─────────────────────────────────────────
PHILOSOPHY = (
    "Nietzsche, *On the Genealogy of Morality* rules:\n"
    "1. Life‑affirming, power‑expanding actions (master) are GOOD.\n"
    "2. Ressentiment‑driven, herd‑pleasing actions (slave) are BAD.\n"
    "3. Self‑punishing asceticism is life‑denying (score −).\n"
    "4. Self‑overcoming discipline that strengthens will is positive (score +)."
)
CATEGORIES = ["deep_work","learning","research","admin","break_fun","social","vice"]
PROMPT_TMPL = (
    "You are a Nietzschean critic.\nCategories = {cats}.\nPhilosophy = {phil}\n\n"
    "Return ONLY a JSON object with keys: \n"
    "  category – one category\n  score – integer −5…5\n  reason – ≤ 12 words\n\n"
    "ACTIVITY: \"{activity}\"\n"
)

# ─── Helper functions ─────────────────────────────────────────

def first_clause(text: str) -> str:
    return text.split("|")[0] if isinstance(text, str) else text


def sentence_from_row(row: Dict[str, str]) -> str:
    event, details = row["event"], row.get("details", "")
    if event.startswith("browser_tab"):
        return f'Visited "{first_clause(details)}" in browser'
    if event.startswith("app_switch"):
        return f'Switched to {first_clause(details).strip()}'
    if event.startswith("app_usage"):
        return f'Used {first_clause(details).strip()}'
    return event


def cache_path(text: str) -> pathlib.Path:
    return CACHE_DIR / (hashlib.sha1(text.encode()).hexdigest() + ".json")

# ─── GPT classification with caching ──────────────────────────

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
    p = cache_path(activity)
    if p.exists():
        return json.loads(p.read_text())
    try:
        res = call_llm(activity, model)
    except Exception as exc:
        print("LLM error:", exc)
        res = {"category":"unknown","score":0,"reason":"llm_error"}
    p.write_text(json.dumps(res))
    return res

# ─── Streak tracker ───────────────────────────────────────────
class Streak:
    def __init__(self) -> None:
        self.pos = self.neg = 0
        self.state = "neutral"  # neutral|good|bad
    def update(self, score: int, sentence: str, reason: str) -> None:
        # decide bucket
        if score >= POS_THRESH:
            self.pos, self.neg = self.pos + 1, 0
        elif score <= NEG_THRESH:
            self.neg, self.pos = self.neg + 1, 0
        else:
            self.pos = self.neg = 0
        # sustained notifications
        if self.pos == STREAK_LEN and self.state != "good":
            notify(f"🔥 {STREAK_LEN} strong, life‑affirming acts in a row!",
                   title="Nietzsche approves ✨")
            self.state = "good"
        if self.neg == STREAK_LEN and self.state != "bad":
            notify(f"⚠️ {STREAK_LEN} life‑denying acts:\n{sentence}\nBecause: {reason}",
                   title="Slave‑morality alert 🕱")
            self.state = "bad"
        # trend flips
        if self.state == "good" and self.neg == 1:
            notify("Good streak broken – stay vigilant.")
            self.state = "neutral"
        if self.state == "bad" and self.pos == 1:
            notify("🎉 Turning the tide – first positive after a bad patch")
            self.state = "neutral"

# ─── Logger (Mac‑only: Quartz, pygetwindow) ───────────────────
# Runs in its own thread; writes CSV rows periodically.
try:
    import pygetwindow as gw
    from Quartz import (
        CGEventSourceSecondsSinceLastEventType,
        kCGAnyInputEventType,
        kCGEventSourceStateCombinedSessionState,
    )
    import subprocess

    def _get_active_window_title() -> str:
        try:
            w = gw.getActiveWindow()
            if not w:
                return "Unknown"
            return w.title() if callable(w.title) else w.title
        except Exception:
            return "Unknown"

    def _get_chrome_tab() -> tuple[str,str]:
        script = (
            'tell application "Google Chrome"\n'
            'if not (exists window 1) then return "Unknown||Unknown"\n'
            'set t to title of active tab of front window\n'
            'set u to URL of active tab of front window\n'
            'return t & "||" & u\nend tell'
        )
        try:
            out = subprocess.check_output(["osascript", "-e", script])
        except Exception:
            return ("Unknown", "Unknown")
        return out.decode().strip().split("||", 1)

    def logger_thread(stop: threading.Event) -> None:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_PATH, "a", newline="") as f:
            writer = csv.writer(f)
            if os.stat(LOG_PATH).st_size == 0:
                writer.writerow(["timestamp","event","details"])
                f.flush()
            while not stop.is_set():
                ts = dt.datetime.now().isoformat()
                app = _get_active_window_title()
                if "Chrome" in app:
                    title, url = _get_chrome_tab()
                    event, details = "browser_tab_snapshot", f"{title}|{url}"
                else:
                    event, details = "app_snapshot", app
                writer.writerow([ts,event,details])
                f.flush()
                time.sleep(WIN_POLL_INTERVAL)
except Exception:
    # if dependencies missing, logger cannot run
    def logger_thread(stop: threading.Event) -> None:  # type: ignore
        print("Logger not available on this platform – skipping.")
        return None

# ─── Evaluator tail loop ───────────────────────────────────────

def evaluate_live(model: str, tail_start: bool = True) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    streak = Streak()
    # Open the CSV for reading and seek to desired position
    with open(LOG_PATH, "r", newline="") as f:
        reader = csv.DictReader(f)
        if tail_start:
            # skip to end so we only process *new* rows
            for _ in reader:
                pass
        while True:
            line = f.readline()
            if not line:
                time.sleep(0.5)
                continue
            row = dict(zip(reader.fieldnames, next(csv.reader([line]))))
            # Skip header duplicates
            if row.get("timestamp") == "timestamp":
                continue
            sent = sentence_from_row(row)
            res  = classify(sent, model)
            streak.update(res["score"], sent, res["reason"])

# ─── CLI / entry point ─────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="Real‑time Nietzsche behaviour monitor")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--no-log", action="store_true", help="Do not run internal logger thread")
    ap.add_argument("--history", action="store_true", help="Process existing rows before tailing")
    args = ap.parse_args()

    stop_evt = threading.Event()
    threads: List[threading.Thread] = []

    if not args.no_log:
        t = threading.Thread(target=logger_thread, args=(stop_evt,), daemon=True)
        t.start(); threads.append(t)
        print("▶ Logger thread started …")

    # evaluator runs in main thread (so Ctrl‑C stops everything)
    print("▶ Evaluator running …")
    try:
        evaluate_live(model=args.model, tail_start=not args.history)
    except KeyboardInterrupt:
        print("Stopping …")
        stop_evt.set()
        for t in threads:
            t.join()

if __name__ == "__main__":
    main()
