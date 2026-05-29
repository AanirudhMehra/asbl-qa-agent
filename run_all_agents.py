"""
ASBL QA — Full agent pipeline runner.

Runs all five agents in sequence:
  1. chatbot_qa   — evaluate new chatbot conversations
  2. voice_qa     — evaluate new voice calls
  3. analytics    — aggregate patterns across all QA results
  4. feedback     — generate problem statements from analytics
  5. recommendation — generate actionable fixes from feedback

Usage:
  python3 run_all_agents.py                          # run once now (default 4-hour window)
  python3 run_all_agents.py 8                        # look back 8 hours instead
  python3 run_all_agents.py --loop                   # run every 4 hours indefinitely
  python3 run_all_agents.py --at "2026-05-26T18:00+05:30"   # backfill a specific cron slot

Backfill missed crons (run sequentially, each gets its own Sheet tab):
  python3 run_all_agents.py --at "2026-05-26T18:00+05:30"
  python3 run_all_agents.py --at "2026-05-26T22:00+05:30"
  python3 run_all_agents.py --at "2026-05-27T02:00+05:30"
  ...

Cron (every 4 hours):
  0 2,6,10,14,18,22 * * * cd /Users/aanirudhmehra/Desktop/asbl-qa-agent && \
    /usr/bin/python3 run_all_agents.py >> logs/agent_runner.log 2>&1
"""

import sys
import os
import time
import subprocess
import argparse
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "/Users/aanirudhmehra/Desktop/asbl-qa-agent")

LOCK_FILE = "/tmp/asbl_qa_pipeline.lock"


def acquire_lock():
    """Returns True if lock acquired, False if another instance is running."""
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE) as f:
                pid = int(f.read().strip())
            # Check if process is actually still alive
            os.kill(pid, 0)
            return False  # Process is running
        except (ProcessLookupError, ValueError):
            pass  # Stale lock — process is gone, safe to take over
    with open(LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))
    return True


def release_lock():
    try:
        os.remove(LOCK_FILE)
    except FileNotFoundError:
        pass

PROJECT_DIR = "/Users/aanirudhmehra/Desktop/asbl-qa-agent"
PYTHON      = sys.executable   # same interpreter that's running this script

# (script_path, extra_args, accepts_hours)
# chatbot_qa and voice_qa take `hours` as a positional arg.
# analytics and recommendation call run() with no args.
# feedback needs "aggregate" as first arg, no hours.
AGENTS = [
    ("Chatbot QA",     ["agents/chatbot_qa.py"],            True),
    ("Voice QA",       ["agents/voice_qa.py"],              True),
    ("Analytics",      ["agents/analytics.py"],             False),
    ("Feedback",       ["agents/feedback.py", "aggregate"], False),
    ("Recommendation", ["agents/recommendation.py"],        False),
]

INTERVAL_HOURS = 4


def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)



def run_pipeline(hours: int = INTERVAL_HOURS, at_time: datetime = None):
    """
    at_time — if set, simulate running the pipeline at this specific datetime.
              Window = [at_time - hours, at_time]. Sheet tab uses at_time.
              If None, uses datetime.now() (normal live cron behaviour).
    """
    # cron_time is what we show on the Sheet tab and in logs
    cron_time      = at_time or datetime.now(timezone.utc)
    cron_time_local = cron_time.astimezone()  # convert to local for display
    log("=" * 60)
    log(f"Pipeline start — cron slot: {cron_time_local.strftime('%Y-%m-%d %H:%M %Z')}  window: {hours}h")
    log("=" * 60)
    t_start        = time.time()
    pipeline_start = cron_time  # used for sheet window calculation

    results = {}
    for name, script_args, accepts_hours in AGENTS:
        cmd = [PYTHON] + script_args
        if accepts_hours:
            cmd += [str(hours)]
            if at_time:
                cmd += ["--until", at_time.isoformat()]
        log(f"▶  Starting {name}{'  (last ' + str(hours) + 'h)' if accepts_hours else ''}...")
        t0 = time.time()
        result = subprocess.run(cmd, cwd=PROJECT_DIR, capture_output=False)
        elapsed = round(time.time() - t0, 1)
        ok = result.returncode == 0
        results[name] = ok
        log(f"{'✓' if ok else '✗'}  {name} {'done' if ok else 'FAILED'} in {elapsed}s")

    total = round(time.time() - t_start, 1)
    passed = sum(1 for v in results.values() if v)
    log("-" * 60)
    log(f"Pipeline complete in {total}s — {passed}/{len(AGENTS)} agents succeeded")
    for name, ok in results.items():
        log(f"  {'✓' if ok else '✗'}  {name}")
    log("=" * 60)

    # ── Write results to Google Sheet ─────────────────────────────────────
    try:
        from db import get_db
        import pymongo
        from dotenv import load_dotenv
        import os
        load_dotenv(os.path.join(PROJECT_DIR, ".env"))

        db = get_db()

        # Use the cron time (IST) as the tab label, not the actual wall-clock run time
        IST_OFFSET = timedelta(hours=5, minutes=30)
        cron_time_ist = (cron_time + IST_OFFSET).replace(tzinfo=None) if cron_time.tzinfo else cron_time
        run_time_str = cron_time_ist.strftime("%Y-%m-%d %H:%M")

        since_obj = pipeline_start - timedelta(hours=hours)
        since_ist = (since_obj + IST_OFFSET).replace(tzinfo=None) if since_obj.tzinfo else since_obj
        window_str = f"{since_ist.strftime('%H:%M')} → {cron_time_ist.strftime('%H:%M')}"

        # Pull results evaluated in this run window (with small buffer for evaluation lag)
        since_iso = (pipeline_start - timedelta(hours=hours, minutes=5)).isoformat()

        cb_results = list(db["chatbot_qa"].find(
            {"status": {"$ne": "SKIPPED"}, "evaluated_at": {"$gte": since_iso}},
            sort=[("evaluated_at", -1)]
        ))
        cb_flagged = list(db["chatbot_qa"].find(
            {"skip_reason": "SPAM_FILTERED", "evaluated_at": {"$gte": since_iso}},
            sort=[("evaluated_at", -1)]
        ))
        vc_results = list(db["voice_qa"].find(
            {"status": {"$ne": "SKIPPED"}, "evaluated_at": {"$gte": since_iso}},
            sort=[("evaluated_at", -1)]
        ))

        an_run   = db["analytics_runs"].find_one(sort=[("run_at", -1)])
        an_flags = an_run.get("flags", []) if an_run else []

        fb_doc   = db["feedback"].find_one({"source": "automated"}, sort=[("submitted_at", -1)])
        problems = fb_doc.get("problems", []) if fb_doc else []

        rec_doc = db["recommendations"].find_one(sort=[("generated_at", -1)])
        fixes   = rec_doc.get("fixes", []) if rec_doc else []

        from sheets_reporter import write_run_to_sheet
        write_run_to_sheet({
            "run_time":   run_time_str,
            "window":     window_str,
            "cb_results": cb_results,
            "cb_flagged": cb_flagged,
            "vc_results": vc_results,
            "an_flags":   an_flags,
            "problems":   problems,
            "fixes":      fixes,
        })
        log("✓  Google Sheet updated")
    except Exception as e:
        log(f"✗  Google Sheet update failed: {e}")


def main():
    parser = argparse.ArgumentParser(description="ASBL QA pipeline runner")
    parser.add_argument("hours", nargs="?", type=int, default=INTERVAL_HOURS,
                        help="Look-back window in hours (default: 4)")
    parser.add_argument("--loop", action="store_true",
                        help="Run every 4 hours indefinitely")
    parser.add_argument("--at", type=str, default=None,
                        help="Backfill: simulate cron running at this ISO datetime "
                             "(e.g. '2026-05-26T18:00+05:30'). Creates a Sheet tab for that slot.")
    args = parser.parse_args()

    at_time = None
    if args.at:
        at_time = datetime.fromisoformat(args.at)
        if at_time.tzinfo is None:
            # Assume IST if no tz given
            at_time = at_time.replace(tzinfo=timezone(timedelta(hours=5, minutes=30)))
        at_time = at_time.astimezone(timezone.utc)

    if not acquire_lock():
        log(f"⚠  Another pipeline instance is already running (see {LOCK_FILE}). Skipping this cron.")
        sys.exit(0)

    try:
        if args.loop:
            log(f"Loop mode: running pipeline every {INTERVAL_HOURS}h. Ctrl+C to stop.")
            while True:
                run_pipeline(args.hours)
                next_run = datetime.now().strftime("%H:%M:%S")
                log(f"Sleeping {INTERVAL_HOURS}h. Next run at approx {next_run} + {INTERVAL_HOURS}h")
                release_lock()
                time.sleep(INTERVAL_HOURS * 3600)
                acquire_lock()
        else:
            run_pipeline(args.hours, at_time=at_time)
    finally:
        release_lock()


if __name__ == "__main__":
    main()
