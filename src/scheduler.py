"""
Runs a background job every 2h: loads recent history,
classifies each unique window title, then prints one commentary.
"""
from apscheduler.schedulers.background import BackgroundScheduler
from .logger import fetch_last
from .classifier import classify
from .commentator import comment
from datetime import datetime, timezone

def two_hour_cycle():
    history = fetch_last(hours=2)
    verdicts = {w: classify(w) for w in set(history)}
    # feed **all** recent verdicts to the author in one go (pick any)
    commentary = comment(history, cls=list(verdicts.values())[0])
    ts = datetime.now(timezone.utc).strftime("%F %R")
    print(f"\n[{ts} UTC] {commentary}\n")

def start():
    sch = BackgroundScheduler(timezone="UTC")
    sch.add_job(two_hour_cycle, "interval", hours=2, next_run_time=datetime.utcnow())
    sch.start()
