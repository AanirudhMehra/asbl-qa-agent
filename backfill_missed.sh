#!/bin/bash
# Backfill 5 missed cron slots — each gets its own Google Sheet tab
# Run from the project directory

cd /Users/aanirudhmehra/Desktop/asbl-qa-agent

PYTHON=$(which python3)
LOG=logs/agent_runner.log

echo "=============================" | tee -a $LOG
echo "BACKFILL START: $(date)" | tee -a $LOG
echo "=============================" | tee -a $LOG

$PYTHON run_all_agents.py --at "2026-05-26T18:00+05:30" >> $LOG 2>&1
echo "[backfill] 18:00 done — $(date)" | tee -a $LOG

$PYTHON run_all_agents.py --at "2026-05-26T22:00+05:30" >> $LOG 2>&1
echo "[backfill] 22:00 done — $(date)" | tee -a $LOG

$PYTHON run_all_agents.py --at "2026-05-27T02:00+05:30" >> $LOG 2>&1
echo "[backfill] 02:00 done — $(date)" | tee -a $LOG

$PYTHON run_all_agents.py --at "2026-05-27T06:00+05:30" >> $LOG 2>&1
echo "[backfill] 06:00 done — $(date)" | tee -a $LOG

$PYTHON run_all_agents.py --at "2026-05-27T10:00+05:30" >> $LOG 2>&1
echo "[backfill] 10:00 done — $(date)" | tee -a $LOG

echo "=============================" | tee -a $LOG
echo "BACKFILL COMPLETE: $(date)" | tee -a $LOG
echo "=============================" | tee -a $LOG
