#!/bin/bash
# ============================================================
# backfill_queue.sh
# Waits for any currently-running pipeline to finish, then
# runs missed cron slots sequentially.
# ============================================================

PYTHON="/opt/homebrew/bin/python3"
DIR="/Users/aanirudhmehra/Desktop/asbl-qa-agent"
LOG="$DIR/logs/agent_runner.log"

cd "$DIR"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Backfill queue started." | tee -a "$LOG"

# ── Wait for any running pipeline to finish ──────────────────
while pgrep -f "run_all_agents.py\|analytics.py\|feedback.py\|recommendation.py\|chatbot_qa.py\|voice_qa.py" > /dev/null 2>&1; do
    RUNNING=$(pgrep -f "run_all_agents.py\|analytics.py\|feedback.py\|recommendation.py" | tr '\n' ' ')
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Waiting for running pipeline (PIDs: $RUNNING) to finish..." | tee -a "$LOG"
    sleep 30
done

echo "[$(date '+%Y-%m-%d %H:%M:%S')] No running pipeline detected. Starting backfill." | tee -a "$LOG"

SLOTS=(
    "2026-05-29T02:00+05:30"
    "2026-05-29T06:00+05:30"
    "2026-05-29T10:00+05:30"
)

for SLOT in "${SLOTS[@]}"; do
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ▶ Backfilling slot: $SLOT" | tee -a "$LOG"
    $PYTHON "$DIR/run_all_agents.py" --at "$SLOT" >> "$LOG" 2>&1
    EXIT=$?
    if [ $EXIT -eq 0 ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✓ Slot $SLOT complete." | tee -a "$LOG"
    else
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✗ Slot $SLOT failed (exit $EXIT)." | tee -a "$LOG"
    fi
    sleep 5
done

echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✓ All backfill slots complete." | tee -a "$LOG"
