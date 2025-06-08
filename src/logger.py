#!/usr/bin/env python3
# ─── Logger Thread (Desktop activity sampling) ─────────────────────────────────

import csv
import datetime as dt
import os
import pathlib
import threading
import time

# ─── Constants ────────────────────────────────────────────────────────────────
WIN_POLL_INTERVAL: int = 5                           # seconds between samples
LOG_PATH: pathlib.Path = pathlib.Path("data/activity_log.csv")

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

def _get_chrome_tab() -> tuple[str, str]:
    """
    macOS-only: uses AppleScript to fetch the title and URL of the active Chrome tab.
    Returns (title, url) or ("Unknown","Unknown") on failure.
    """
    print("[DEBUG] _get_chrome_tab called.")
    script = (
        'tell application "Google Chrome"\n'
        '  if not (exists window 1) then return "Unknown||Unknown"\n'
        '  set t to title of active tab of front window\n'
        '  set u to URL of active tab of front window\n'
        '  return t & "||" & u\n'
        'end tell'
    )
    try:
        import subprocess
        out = subprocess.check_output(["osascript", "-e", script])
        title, url = out.decode().strip().split("||", 1)
    except Exception:
        title, url = ("Unknown", "Unknown")
    return title, url
