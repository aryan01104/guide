"""
Entry-point: spin up activity logger in one thread
and the 2-hour commentary scheduler in another.
"""
import threading, time
from .logger     import start_logging
from .scheduler  import start as start_scheduler

if __name__ == "__main__":
    th = threading.Thread(target=start_logging, daemon=True)
    th.start()
    start_scheduler()          # non-blocking
    print("✅ Behaviour tracker running. Ctrl-C to stop.")
    while True:
        time.sleep(60)
