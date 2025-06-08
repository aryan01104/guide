#!/usr/bin/env python3
import os
import time
import datetime
import csv
import pygetwindow as gw
from Quartz import (
    CGEventSourceSecondsSinceLastEventType,
    kCGAnyInputEventType,
    kCGEventSourceStateCombinedSessionState,
)
import subprocess

# ─── CONFIG ─────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(SCRIPT_DIR, "data/behavior_log.csv")
WIN_POLL_INTERVAL = 40       # seconds between samples

# ─── UTILITIES ─────────────────────────────────────────────────
def write_log(writer, f, ts, event, details):
    writer.writerow([ts, event, details])
    f.flush()
    print(f"WROTE: {ts} | {event} | {details}")

def get_chrome_active_tab():
    script = '''
    tell application "Google Chrome"
      if not (exists window 1) then return "Unknown||Unknown"
      set t to title of active tab of front window
      set u to URL of   active tab of front window
      return t & "||" & u
    end tell
    '''
    out = subprocess.check_output(["osascript", "-e", script])
    title, url = out.decode().strip().split("||", 1)
    return title, url

def get_active_window():
    try:
        w = gw.getActiveWindow()
        if not w:
            return "Unknown"
        return w.title() if callable(w.title) else w.title
    except:
        return "Unknown"

# ─── MAIN SAMPLING LOGGER ───────────────────────────────────────
def run_logger():
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    f = open(LOG_PATH, "a", newline="")
    writer = csv.writer(f)

    # write header if new
    if os.stat(LOG_PATH).st_size == 0:
        writer.writerow(["timestamp", "event", "details"])
        f.flush()

    try:
        while True:
            ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            app = get_active_window()

            if "Chrome" in app:
                # record the current tab
                title, url = get_chrome_active_tab()
                event = "browser_tab_snapshot"
                details = f"{title}|{url}"
            else:
                # record whatever other app is frontmost
                event = "app_snapshot"
                details = app

            write_log(writer, f, ts, event, details)
            time.sleep(WIN_POLL_INTERVAL)

    except KeyboardInterrupt:
        print("Logger stopped by Ctrl-C")
    finally:
        f.close()

if __name__ == "__main__":
    print("PWD:", os.getcwd())
    print("Sampling every", WIN_POLL_INTERVAL, "s →", LOG_PATH)
    run_logger()
