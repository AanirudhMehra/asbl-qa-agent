import os
import sys
import json
from datetime import datetime, timedelta, timezone

import pymongo
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from notifier import notify
from llm import ask_json, ask
from db import save_voice_result, already_evaluated, get_db

MONGO_URI    = os.getenv("MONGO_URI_PROD")  # read-only from prod
KB_FACTS     = os.path.join(os.path.dirname(__file__), '..', 'knowledge_base', 'anandita', 'project_facts.md')
KB_PROMPT    = os.path.join(os.path.dirname(__file__), '..', 'knowledge_base', 'anandita', 'system_prompt.md')
KB_CHECKLIST = os.path.join(os.path.dirname(__file__), '..', 'knowledge_base', 'anandita', 'qa_checklist.md')
PROMPT_FILE  = os.path.join(os.path.dirname(__file__), 'prompts', 'voice_qa.md')


def load_agent_prompt() -> str:
    with open(PROMPT_FILE, "r") as f:
        return f.read()

def load_knowledge_base() -> str:
    kb = ""
    for path in [KB_FACTS, KB_PROMPT, KB_CHECKLIST]:
        with open(path, "r") as f:
            kb += f.read() + "\n\n---\n\n"
    return kb


def format_transcript(transcript: list) -> str:
    lines = []
    for turn in transcript:
        speaker = "Anandita" if turn.get("speaker") == "Anandita" else "Caller"
        lines.append(f"{speaker}: {turn.get('text', '').strip()}")
    return "\n".join(lines)


def classify_call(transcript_text: str) -> str:
    """
    Pre-filter: classify the call before sending to the full evaluator.
    Returns one of:
      "greeting"  — call is just a hello / immediate hang-up, nothing evaluable
      "spam"      — wrong number, silent call, or completely unrelated content
      "evaluate"  — real call that should be evaluated

    Uses a single tiny LLM call. Defaults to "evaluate" on any failure so we
    never accidentally skip a real call.
    """
    system_msg = """Classify voice call transcripts in one word.

Rules:
- Reply "greeting" if the entire call is just a hello / immediate hang-up with nothing asked.
- Reply "spam" if this is a wrong number, silent call, or completely unrelated to real estate.
- Reply "evaluate" for everything else — any property question, inquiry, or real intent, even if short.

Reply with exactly one word: greeting, spam, or evaluate."""

    user_msg = f"Transcript:\n{transcript_text[:600]}"

    try:
        # Use ask() not ask_json() — model returns a plain word, not JSON
        raw = ask(user_msg, expect_json=False, system=system_msg).lower().strip()
        for word in ("greeting", "spam", "evaluate"):
            if word in raw:
                return word
        return "evaluate"
    except Exception:
        return "evaluate"


def score_call(call: dict, kb: str, agent_prompt: str) -> dict:
    call_sid        = call.get("call_sid", "unknown")
    transcript_text = format_transcript(call.get("transcript", []))
    call_direction  = call.get("call_direction", "unknown")
    language_used   = call.get("language_used", "unknown")
    project         = call.get("project", "unknown")

    if not transcript_text.strip():
        return {"call_sid": call_sid, "status": "SKIPPED", "reason": "Empty transcript"}

    # Pre-filter: skip greetings and wrong-number calls before full evaluation
    label = classify_call(transcript_text)
    if label == "greeting":
        return {
            "call_sid":       call_sid,
            "call_direction": call_direction,
            "status":         "SKIPPED",
            "reason":         "Greeting / immediate hang-up — no evaluable content",
            "evaluated_at":   datetime.now().isoformat(),
        }
    if label == "spam":
        return {
            "call_sid":       call_sid,
            "call_direction": call_direction,
            "status":         "SKIPPED",
            "reason":         "Wrong number / silent / unrelated — not a real estate call",
            "evaluated_at":   datetime.now().isoformat(),
        }

    # System message = static KB + agent prompt (cached by KV cache — sent once per batch)
    # User message   = only the transcript + metadata (~500-1000 tokens, changes every call)
    system_msg = f"""{agent_prompt}

---

KNOWLEDGE BASE (Anandita's ground truth):
{kb}

---

You are a precise JSON-producing assistant. Return only valid JSON, nothing else."""

    user_msg = f"""CALL METADATA:
  direction      = {call_direction}
  language_used  = {language_used}
  project        = {project}

TRANSCRIPT:
{transcript_text}

---

Evaluate the call above against the knowledge base.
Follow all instructions in the system prompt exactly.
Return ONLY the JSON. Nothing else."""

    result = ask_json(user_msg, system=system_msg)
    result["call_sid"] = call_sid
    result["phone_number"] = call.get("phone_number", "")
    result["call_direction"] = call_direction
    result["language_used"] = language_used
    result["project"] = project
    result["evaluated_at"] = datetime.now().isoformat()
    result["confidence"] = result.get("confidence", 0.5)  # default if LLM forgot
    return result


def run_on_new_call(call: dict, kb: str, agent_prompt: str):
    call_sid = call.get("call_sid", "unknown")
    print(f"[Voice QA] Evaluating: {call_sid}")

    try:
        result = score_call(call, kb, agent_prompt)
    except Exception as e:
        notify("Voice QA Agent", "ERROR", {"call_sid": call_sid, "error": str(e)})
        return

    if result.get("status") == "FAIL":
        high_issues = [i for i in result.get("issues", []) if i["severity"] == "HIGH"]
        notify(
            agent_name="Voice QA Agent",
            status="FAIL",
            details={
                "call_sid": call_sid,
                "score": f"{result.get('score')}/10",
                "language_compliance": result.get("language_compliance"),
                "summary": result.get("summary"),
                "high_severity_issues": len(high_issues),
                "issues": "; ".join([f"{i['type']}: {i['detail']}" for i in result.get("issues", [])])
            }
        )
    else:
        print(f"[Voice QA] PASS — {call_sid} (score: {result.get('score')}/10)")

    save_voice_result(result)


def batch(hours: int = 4, until: datetime = None):
    """
    Pull only NEW calls from the `hours`-hour window ending at `until`.
    If `until` is None, uses now (normal live cron behaviour).
    Uses bulk deduplication — 2 DB queries upfront instead of one per call.
    """
    until     = until or datetime.now(timezone.utc)
    since     = until - timedelta(hours=hours)
    since_iso = since.isoformat()
    until_iso = until.isoformat()

    print(f"[Voice QA] Pulling calls {since_iso[:16]} → {until_iso[:16]} UTC...")

    client     = pymongo.MongoClient(MONGO_URI)
    collection = client["ASBLVoiceBot"]["call_transcripts"]

    # Step 1 — get all SIDs in the window (lightweight projection)
    all_in_window = list(collection.find(
        {
            "transcript": {"$exists": True, "$not": {"$size": 0}},
            "$or": [
                {"started_at": {"$gte": since_iso, "$lte": until_iso}},
                {"started_at": {"$gte": since,     "$lte": until}}
            ]
        },
        {"call_sid": 1}
    ))
    all_sids = [c.get("call_sid") for c in all_in_window if c.get("call_sid")]
    print(f"[Voice QA] Found {len(all_sids)} calls in window")

    # Step 2 — bulk check which SIDs are already evaluated (1 query, not N)
    results_db   = get_db()
    already_done = set(
        r["call_sid"]
        for r in results_db["voice_qa"].find(
            {"call_sid": {"$in": all_sids}},
            {"call_sid": 1}
        )
    )
    new_sids = [sid for sid in all_sids if sid not in already_done]
    print(f"[Voice QA] {len(already_done)} already evaluated, {len(new_sids)} new to process")

    if not new_sids:
        print("[Voice QA] Nothing new to evaluate.")
        return

    # Step 3 — fetch full docs only for new calls
    new_calls = list(collection.find(
        {"call_sid": {"$in": new_sids}},
        sort=[("started_at", -1)]
    ))

    kb           = load_knowledge_base()
    agent_prompt = load_agent_prompt()
    for call in new_calls:
        run_on_new_call(call, kb, agent_prompt)

    print(f"[Voice QA] Done. Evaluated {len(new_calls)} new calls.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("hours", nargs="?", type=int, default=4)
    parser.add_argument("--until", type=str, default=None,
                        help="ISO datetime — simulate running at this time (for backfills)")
    args = parser.parse_args()
    until_dt = None
    if args.until:
        until_dt = datetime.fromisoformat(args.until)
        if until_dt.tzinfo is None:
            until_dt = until_dt.replace(tzinfo=timezone.utc)
        else:
            until_dt = until_dt.astimezone(timezone.utc)
    batch(args.hours, until=until_dt)
