import os
import sys
import time
from datetime import datetime

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

from db import init_db
from notifier import notify

INTERVAL_HOURS = 4
INTERVAL_SECONDS = INTERVAL_HOURS * 60 * 60


def run_cycle():
    print(f"\n{'='*60}")
    print(f"[Runner] Starting QA cycle at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")

    errors = []

    # Step 1 — Chatbot QA (all conversations from last 4 hours)
    try:
        print("\n[Runner] Step 1/5 — Chatbot QA")
        from agents.chatbot_qa import batch as chatbot_batch
        chatbot_batch(hours=4)
    except Exception as e:
        errors.append(f"Chatbot QA failed: {e}")
        print(f"[Runner] ERROR in Chatbot QA: {e}")

    # Step 2 — Voice QA (all calls from last 4 hours)
    try:
        print("\n[Runner] Step 2/5 — Voice QA")
        from agents.voice_qa import batch as voice_batch
        voice_batch(hours=4)
    except Exception as e:
        errors.append(f"Voice QA failed: {e}")
        print(f"[Runner] ERROR in Voice QA: {e}")

    # Step 3 — Analytics Agent
    try:
        print("\n[Runner] Step 3/5 — Analytics Agent")
        from agents.analytics import run as analytics_run
        analytics_run()
    except Exception as e:
        errors.append(f"Analytics failed: {e}")
        print(f"[Runner] ERROR in Analytics: {e}")

    # Step 4 — Feedback Agent (identifies problems)
    problems = []
    try:
        print("\n[Runner] Step 4/5 — Feedback Agent")
        from agents.feedback import aggregate as feedback_aggregate
        problems = feedback_aggregate()
    except Exception as e:
        errors.append(f"Feedback failed: {e}")
        print(f"[Runner] ERROR in Feedback: {e}")

    # Step 5 — Recommendation Agent (fixes the problems feedback found)
    try:
        print("\n[Runner] Step 5/5 — Recommendation Agent")
        from agents.recommendation import run as recommendation_run
        recommendation_run(problems=problems)   # pass directly — no re-fetch needed
    except Exception as e:
        errors.append(f"Recommendation failed: {e}")
        print(f"[Runner] ERROR in Recommendation: {e}")

    print(f"\n[Runner] Cycle complete at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    if errors:
        notify("Runner", "CYCLE ERRORS", {"errors": " | ".join(errors)})
    else:
        print(f"[Runner] All steps completed successfully.")

    print(f"[Runner] Next run in {INTERVAL_HOURS} hours.")
    print(f"{'='*60}\n")


def main():
    print("[Runner] Initializing database...")
    init_db()

    if len(sys.argv) > 1 and sys.argv[1] == "once":
        # Run once and exit — useful for testing
        run_cycle()
        return

    # Run on loop every 4 hours
    print(f"[Runner] Starting. Will run every {INTERVAL_HOURS} hours.")
    print("[Runner] Press Ctrl+C to stop.\n")

    while True:
        run_cycle()
        print(f"[Runner] Sleeping for {INTERVAL_HOURS} hours...")
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
