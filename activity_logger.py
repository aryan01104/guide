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
LOG_PATH = os.path.join(SCRIPT_DIR, "/Users/aryanagarwal/projects/guide/data/behavior_log.csv")
WIN_POLL_INTERVAL = 5       # seconds between checking active window
INACTIVITY_THRESHOLD = 300    # seconds of no input → log inactivity

# ─── UTILS ──────────────────────────────────────────────────────
def write_log(writer, f, event, details):
    ts = datetime.datetime.now().isoformat()
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


# ─── ACTIVE WINDOW ──────────────────────────────────────────────
def get_active_window():
    try:
        w = gw.getActiveWindow()
        if not w:
            return "Unknown"
        return w.title() if callable(w.title) else w.title
    except:
        return "Unknown"

# ─── INACTIVITY DETECTION ───────────────────────────────────────
def get_idle_time():
    # Returns seconds since last user input (mouse/keyboard)
    return CGEventSourceSecondsSinceLastEventType(
        kCGEventSourceStateCombinedSessionState,
        kCGAnyInputEventType
    )

# ─── MAIN LOGGER ────────────────────────────────────────────────
def run_logger():
    # Prepare CSV
    f = open(LOG_PATH, "a", newline="")
    writer = csv.writer(f)
    # Write header if file is new
    if os.stat(LOG_PATH).st_size == 0:
        writer.writerow(["timestamp", "event", "details"])
        f.flush()

    prev_app = None
    app_start = time.time()
    was_idle = False

    try:
        while True:
            now = time.time()
            idle = get_idle_time()

            # Log inactivity events
            if idle >= INACTIVITY_THRESHOLD and not was_idle:
                write_log(writer, f, "inactivity", int(idle))
                was_idle = True
            elif idle < INACTIVITY_THRESHOLD and was_idle:
                was_idle = False

            # Log app usage and switches
            app = get_active_window()
            if "Chrome" in app:
                tab_title, tab_url = get_chrome_active_tab()
                write_log(writer, f, "browser_tab", f"{tab_title}|{tab_url}")

            if app != prev_app:
                # Log duration for previous window if not idle
                if prev_app is not None and not was_idle:
                    dur = round(now - app_start, 2)
                    write_log(writer, f, "app_usage", f"{prev_app}|{dur}")
                # Log the switch
                write_log(writer, f, "app_switch", app)
                prev_app = app
                app_start = now

            time.sleep(WIN_POLL_INTERVAL)

    except KeyboardInterrupt:
        print("Logger stopped by Ctrl-C")
    finally:
        f.close()

if __name__ == "__main__":
    print("PWD:", os.getcwd())
    print("Logging to:", LOG_PATH)
    run_logger()
