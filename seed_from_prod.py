"""
Seed QA Results from Production Data

Pulls the most recent conversations and calls from the production DB,
runs them through the real QA agents, and saves results to qa_results DB.

This is a one-shot script — run it to populate qa_results before running
the full analytics pipeline.

Usage:
    python3 seed_from_prod.py                  # 100 chatbot + 10 voice (default)
    python3 seed_from_prod.py --chatbot 50     # 50 chatbot conversations only
    python3 seed_from_prod.py --voice 20       # 20 voice calls only
    python3 seed_from_prod.py --chatbot 100 --voice 10   # both

Note:
    Already-evaluated conversations are skipped (deduplication is on by default).
    Pass --rerun to re-evaluate everything regardless.
"""

import os
import sys
import argparse
from datetime import datetime

import pymongo
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

sys.path.insert(0, os.path.dirname(__file__))

from agents.chatbot_qa import (
    score_conversation, load_knowledge_base as load_cb_kb,
    load_agent_prompt as load_cb_prompt
)
from agents.voice_qa import (
    score_call, load_knowledge_base as load_vc_kb,
    load_agent_prompt as load_vc_prompt
)
from db import save_chatbot_result, save_voice_result, already_evaluated

MONGO_URI_PROD = os.getenv("MONGO_URI_PROD")


# ════════════════════════════════════════════════════════════════════════════
# CHATBOT
# ════════════════════════════════════════════════════════════════════════════

def seed_chatbot(limit: int, rerun: bool = False):
    print(f"\n{'─'*60}")
    print(f"  CHATBOT QA — seeding {limit} most recent conversations")
    print(f"{'─'*60}")

    client = pymongo.MongoClient(MONGO_URI_PROD)
    collection = client["asbl_loft"]["conversations"]

    docs = list(collection.find(
        {"conversationDepth": {"$exists": True, "$not": {"$size": 0}}},
        sort=[("createdAt", -1)],
        limit=limit
    ))

    print(f"  Pulled {len(docs)} conversations from prod\n")

    kb           = load_cb_kb()
    agent_prompt = load_cb_prompt()

    results    = {"PASS": 0, "FAIL": 0, "SKIPPED": 0, "ERROR": 0}
    skipped_dup = 0

    for i, conv in enumerate(docs, 1):
        cid = conv.get("conversationId", "unknown")

        # Deduplication — skip if already in qa_results
        if not rerun and already_evaluated("chatbot_qa", "conversation_id", cid):
            skipped_dup += 1
            continue

        try:
            result = score_conversation(conv, kb, agent_prompt, client=client)
            status = result.get("status", "ERROR")

            if status not in ("SKIPPED", "ERROR"):
                save_chatbot_result(result)

            results[status if status in results else "ERROR"] += 1

            # Progress line
            icon   = {"PASS": "✓", "FAIL": "✗", "SKIPPED": "–", "ERROR": "!"}.get(status, "?")
            issues = ""
            if result.get("issues"):
                top = result["issues"][0]
                issues = f"  [{top.get('severity')}] {top.get('type')}"
            print(f"  [{i:>3}/{len(docs)}] {icon} {status:<7}  "
                  f"score={result.get('score', '–'):>2}  {cid}{issues}")

        except Exception as e:
            results["ERROR"] += 1
            print(f"  [{i:>3}/{len(docs)}] ! ERROR    {cid}  → {e}")

    print(f"\n  Summary: PASS={results['PASS']}  FAIL={results['FAIL']}  "
          f"SKIPPED={results['SKIPPED']}  ERROR={results['ERROR']}  "
          f"already_done={skipped_dup}")
    return results


# ════════════════════════════════════════════════════════════════════════════
# VOICE
# ════════════════════════════════════════════════════════════════════════════

def seed_voice(limit: int, rerun: bool = False):
    print(f"\n{'─'*60}")
    print(f"  VOICE QA — seeding {limit} most recent calls")
    print(f"{'─'*60}")

    client = pymongo.MongoClient(MONGO_URI_PROD)
    collection = client["ASBLVoiceBot"]["call_transcripts"]

    docs = list(collection.find(
        {"transcript": {"$exists": True, "$not": {"$size": 0}}},
        sort=[("started_at", -1)],
        limit=limit
    ))

    print(f"  Pulled {len(docs)} calls from prod\n")

    kb           = load_vc_kb()
    agent_prompt = load_vc_prompt()

    results    = {"PASS": 0, "FAIL": 0, "SKIPPED": 0, "ERROR": 0}
    skipped_dup = 0

    for i, doc in enumerate(docs, 1):
        sid = doc.get("call_sid", "unknown")

        if not rerun and already_evaluated("voice_qa", "call_sid", sid):
            skipped_dup += 1
            continue

        call = {
            "call_sid":       sid,
            "transcript":     doc.get("transcript", []),
            "call_direction": doc.get("call_direction", "unknown"),
            "language_used":  doc.get("language_used", "unknown"),
            "project":        doc.get("project", ""),
            "phone_number":   doc.get("phone_number", ""),
        }

        try:
            result = score_call(call, kb, agent_prompt)
            status = result.get("status", "ERROR")

            if status not in ("SKIPPED", "ERROR"):
                save_voice_result(result)

            results[status if status in results else "ERROR"] += 1

            icon   = {"PASS": "✓", "FAIL": "✗", "SKIPPED": "–", "ERROR": "!"}.get(status, "?")
            issues = ""
            if result.get("issues"):
                top = result["issues"][0]
                issues = f"  [{top.get('severity')}] {top.get('type')}"
            print(f"  [{i:>3}/{len(docs)}] {icon} {status:<7}  "
                  f"score={result.get('score', '–'):>2}  {sid[:36]}{issues}")

        except Exception as e:
            results["ERROR"] += 1
            print(f"  [{i:>3}/{len(docs)}] ! ERROR    {sid}  → {e}")

    print(f"\n  Summary: PASS={results['PASS']}  FAIL={results['FAIL']}  "
          f"SKIPPED={results['SKIPPED']}  ERROR={results['ERROR']}  "
          f"already_done={skipped_dup}")
    return results


# ════════════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Seed QA results from prod data")
    parser.add_argument("--chatbot", type=int, default=100,
                        help="Number of chatbot conversations to seed (default: 100)")
    parser.add_argument("--voice",   type=int, default=10,
                        help="Number of voice calls to seed (default: 10)")
    parser.add_argument("--only-chatbot", action="store_true",
                        help="Run chatbot seeding only")
    parser.add_argument("--only-voice",   action="store_true",
                        help="Run voice seeding only")
    parser.add_argument("--rerun", action="store_true",
                        help="Re-evaluate even if already in qa_results DB")
    args = parser.parse_args()

    print(f"\n{'═'*60}")
    print(f"  PROD SEEDER")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'═'*60}")

    run_chatbot = not args.only_voice
    run_voice   = not args.only_chatbot

    if run_chatbot:
        seed_chatbot(args.chatbot, rerun=args.rerun)

    if run_voice:
        seed_voice(args.voice, rerun=args.rerun)

    print(f"\n{'═'*60}")
    print(f"  Done. Results saved to qa_results DB.")
    print(f"  Run analytics next:")
    print(f"    python3 -c \"from agents.analytics import run; run()\"")
    print(f"{'═'*60}\n")


if __name__ == "__main__":
    main()
