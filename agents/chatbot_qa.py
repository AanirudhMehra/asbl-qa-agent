import os
import sys
import json
import glob
import re
from datetime import datetime, timedelta, timezone

import pymongo
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from notifier import notify
from llm import ask_json, ask
from db import save_chatbot_result, already_evaluated, get_db
from spam_filter import flag_conversation

MONGO_URI  = os.getenv("MONGO_URI_PROD")  # read-only from prod
KB_DIR     = os.path.join(os.path.dirname(__file__), '..', 'knowledge_base', 'webbot')
PROMPT_FILE = os.path.join(os.path.dirname(__file__), 'prompts', 'chatbot_qa.md')


def load_agent_prompt() -> str:
    with open(PROMPT_FILE, "r") as f:
        return f.read()

def load_knowledge_base() -> str:
    # Only load files relevant for QA evaluation.
    # Excluded: persona_playbook, objection_library, deployment_guide,
    #           competitive_landscape, resale_framework — these are sales
    #           strategy docs, not ground-truth facts the QA agent checks against.
    QA_KB_FILES = [
        "00_qa_checklist.md",        # QA rules
        "01_system_prompt_qa.md",    # compliance rules only (§1 Absolute Rules, §6 Resale, §11 Guardrails)
        "02_kb_project_loft.md",     # prices, RERA, sizes, configs — primary fact source
        # 03_kb_market_intelligence.md — excluded: location/market facts rarely trigger QA violations
        #   add back if location-accuracy flags become a pattern
    ]
    combined = []
    for filename in QA_KB_FILES:
        filepath = os.path.join(KB_DIR, filename)
        if os.path.exists(filepath):
            with open(filepath, "r") as fh:
                combined.append(f"### {filename}\n\n" + fh.read())
    return "\n\n---\n\n".join(combined)


def format_conversation(conversation_depth: list) -> str:
    lines = []
    for turn in conversation_depth:
        user_text = turn.get("userText", "").strip()
        bot_text  = re.sub(r'<[^>]+>', '', turn.get("botText", "")).strip()
        artifact  = turn.get("artifactLabel", "").strip()
        lines.append(f"User: {user_text}")
        if artifact:
            lines.append(f"Bot [showed: {artifact}]: {bot_text}")
        else:
            lines.append(f"Bot: {bot_text}")
    return "\n".join(lines)


def get_identity_fields(client: pymongo.MongoClient, conversation: dict) -> dict:
    """
    Look up visitor_id, lead_id, and phone_number for a conversation.
    All three come from prod — visitors and leads collections.
    Returns a dict with keys: visitor_id, lead_id, phone_number.
    Falls back to None/empty string on any failure.
    """
    result = {"visitor_id": None, "lead_id": None, "phone_number": None}
    if not client:
        return result
    try:
        db = client["asbl_loft"]

        # visitor_id — conversation.visitorId is usually a plain string like "v-xxx"
        # but older docs may store it as an ObjectId.
        # Ephemeral IDs ("v-ephemeral-*") have no visitors record — skip them.
        raw_visitor = conversation.get("visitorId")
        if raw_visitor:
            is_ephemeral = isinstance(raw_visitor, str) and raw_visitor.startswith("v-ephemeral")
            if not is_ephemeral:
                if isinstance(raw_visitor, str):
                    visitor_doc = db["visitors"].find_one({"visitorId": raw_visitor}, {"visitorId": 1, "phoneE164": 1})
                else:
                    # ObjectId stored directly — look up by _id
                    visitor_doc = db["visitors"].find_one({"_id": raw_visitor}, {"visitorId": 1, "phoneE164": 1})
                if visitor_doc:
                    result["visitor_id"] = visitor_doc.get("visitorId")
                    if visitor_doc.get("phoneE164"):
                        result["phone_number"] = visitor_doc["phoneE164"]

        # lead_id + phone — conversation.leadId (ObjectId) → leads._id
        raw_lead = conversation.get("leadId")
        if raw_lead:
            lead_doc = db["leads"].find_one({"_id": raw_lead}, {"leadId": 1, "phone": 1})
            if lead_doc:
                result["lead_id"] = lead_doc.get("leadId")
                if lead_doc.get("phone") and not result["phone_number"]:
                    result["phone_number"] = lead_doc["phone"]
    except Exception as e:
        print(f"[Identity] lookup failed: {e}")
    return result


def get_session_signals(client: pymongo.MongoClient, session_id: str) -> dict:
    """
    Look up the events collection for this session and extract
    lead capture and visit booking signals. Returns a dict of booleans.
    """
    if not session_id:
        return {}
    try:
        session = client["asbl_loft"]["events"].find_one({"sessionId": session_id})
        if not session:
            return {}
        event_names = set(session.get("uniqueEventNames", []))
        return {
            "lead_captured":       "lead_success"          in event_names,
            "lead_submitted":      "lead_submit"           in event_names,
            "visit_booked":        "visit_booking"         in event_names,
            "visit_otp_verified":  "visit_otp_verify_click" in event_names,
            "visit_form_started":  any(e in event_names for e in [
                                       "visit_phone_focus", "visit_name_focus",
                                       "visit_otp_send_click"]),
        }
    except Exception:
        return {}


def classify_conversation(conversation_text: str) -> str:
    """
    Pre-filter: classify the conversation before sending to the full evaluator.
    Returns one of:
      "greeting" — just a hi/hello opener, nothing to evaluate
      "spam"     — garbage, bot test, or completely off-topic (no real estate intent at all)
      "evaluate" — real conversation that should be evaluated

    Uses a single tiny LLM call. If the call fails, defaults to "evaluate"
    so we never accidentally skip a real conversation.
    """
    system_msg = """Classify chatbot conversations in one word.

Rules:
- Reply "greeting" if the entire conversation is just a hello/hi/greeting with no real question asked yet.
- Reply "spam" if this is clearly a bot test, random keyboard spam, or has zero real estate intent (e.g. "asdfgh", "test 123", completely unrelated topic).
- Reply "evaluate" for everything else — any real question, inquiry, or property discussion, even if short.

Reply with exactly one word: greeting, spam, or evaluate."""

    user_msg = f"Conversation:\n{conversation_text[:600]}"

    try:
        # Use ask() not ask_json() — model returns a plain word, not JSON
        raw = ask(user_msg, expect_json=False, system=system_msg).lower().strip()
        for word in ("greeting", "spam", "evaluate"):
            if word in raw:
                return word
        return "evaluate"
    except Exception:
        return "evaluate"


def score_conversation(conversation: dict, kb: str, agent_prompt: str,
                       client: pymongo.MongoClient = None) -> dict:
    conversation_text = format_conversation(conversation.get("conversationDepth", []))
    conversation_id   = conversation.get("conversationId", "unknown")
    session_id        = conversation.get("sessionId", "")

    if not conversation_text.strip():
        return {
            "conversation_id": conversation_id,
            "status": "SKIPPED",
            "reason": "Empty conversation"
        }

    # conversation_date = when the chat actually happened (from prod createdAt)
    # evaluated_at      = when the cron/backfill ran — these differ for backfills
    raw_created = conversation.get("createdAt")
    if raw_created is None:
        conversation_date = None
    elif isinstance(raw_created, datetime):
        conversation_date = raw_created.isoformat()
    else:
        conversation_date = str(raw_created)

    # ── Identity enrichment (visitor_id, lead_id, phone_number) ────────────
    identity = get_identity_fields(client, conversation)

    # ── Layer 1: Regex spam filter (zero LLM cost) ───────────────────────────
    user_flags = flag_conversation(conversation.get("conversationDepth", []))
    if user_flags:
        flag_types = list({f["type"] for f in user_flags})
        print(f"[Chatbot QA] SPAM_FILTERED — {conversation_id} ({', '.join(flag_types)})")
        return {
            "conversation_id":  conversation_id,
            "status":           "SKIPPED",
            "skip_reason":      "SPAM_FILTERED",
            "user_flags":       user_flags,
            "turn_count":       conversation.get("turnCount", 0),
            "conversation_date": conversation_date,
            "evaluated_at":     datetime.now().isoformat(),
            **identity,
        }

    # ── Pre-filter: skip greetings and spam (LLM classifier) ────────────────
    label = classify_conversation(conversation_text)
    if label == "greeting":
        return {
            "conversation_id":  conversation_id,
            "status":           "SKIPPED",
            "reason":           "Greeting only — no evaluable content",
            "turn_count":       conversation.get("turnCount", 0),
            "conversation_date": conversation_date,
            "evaluated_at":     datetime.now().isoformat(),
            **identity,
        }
    if label == "spam":
        return {
            "conversation_id":  conversation_id,
            "status":           "SKIPPED",
            "reason":           "Spam / off-topic — not a real estate conversation",
            "turn_count":       conversation.get("turnCount", 0),
            "conversation_date": conversation_date,
            "evaluated_at":     datetime.now().isoformat(),
            **identity,
        }

    # Fetch event-based signals for this session
    signals = get_session_signals(client, session_id) if client else {}
    signal_lines = []
    if signals:
        signal_lines.append("SESSION SIGNALS (from event tracking — ground truth):")
        signal_lines.append(f"  lead_captured      : {signals.get('lead_captured', False)}")
        signal_lines.append(f"  lead_submitted     : {signals.get('lead_submitted', False)}")
        signal_lines.append(f"  visit_booked       : {signals.get('visit_booked', False)}")
        signal_lines.append(f"  visit_otp_verified : {signals.get('visit_otp_verified', False)}")
        signal_lines.append(f"  visit_form_started : {signals.get('visit_form_started', False)}")
        signal_lines.append("Use these as the authoritative truth for lead capture and visit booking.")
        signal_lines.append("Do NOT flag MISSED_LEAD_CAPTURE if lead_captured = True.")
    signal_block = "\n".join(signal_lines)

    # System message = static KB + agent prompt (cached by KV cache — sent once per batch)
    # User message   = only the conversation (~500 tokens, changes every call)
    system_msg = f"""{agent_prompt}

---

KNOWLEDGE BASE (ground truth — what the bot should say):
{kb}

---

You are a precise JSON-producing assistant. Return only valid JSON, nothing else."""

    user_msg = f"""{signal_block}

CONVERSATION TO EVALUATE:
{conversation_text}

---

Evaluate the conversation above against the knowledge base.
Follow all instructions in the system prompt exactly.
Return ONLY the JSON. Nothing else."""

    result = ask_json(user_msg, system=system_msg)
    result["conversation_id"]   = conversation_id
    result["turn_count"]        = conversation.get("turnCount", 0)
    result["conversation_date"] = conversation_date
    result["evaluated_at"]      = datetime.now().isoformat()
    result["confidence"]        = result.get("confidence", 0.5)
    result["session_signals"]   = signals
    result["visitor_id"]        = identity.get("visitor_id")
    result["lead_id"]           = identity.get("lead_id")
    result["phone_number"]      = identity.get("phone_number")
    # Layer 2: LLM may return user_flags for flagged user messages it noticed
    if "user_flags" not in result:
        result["user_flags"] = []
    return result


def run_on_new_conversation(conversation: dict, kb: str, agent_prompt: str,
                            client: pymongo.MongoClient = None):
    conversation_id = conversation.get("conversationId", "unknown")
    print(f"[Chatbot QA] Evaluating: {conversation_id}")

    try:
        result = score_conversation(conversation, kb, agent_prompt, client)
    except Exception as e:
        notify("Chatbot QA Agent", "ERROR", {
            "conversation_id": conversation_id,
            "error": str(e)
        })
        return

    if result.get("status") == "FAIL":
        high_issues = [i for i in result.get("issues", []) if i["severity"] == "HIGH"]
        notify(
            agent_name="Chatbot QA Agent",
            status="FAIL",
            details={
                "conversation_id": conversation_id,
                "score": f"{result.get('score')}/10",
                "summary": result.get("summary"),
                "high_severity_issues": len(high_issues),
                "issues": "; ".join([f"{i['type']}: {i['detail']}" for i in result.get("issues", [])])
            }
        )
    else:
        print(f"[Chatbot QA] PASS — {conversation_id} (score: {result.get('score')}/10)")

    save_chatbot_result(result)


def batch(hours: int = 4, until: datetime = None):
    """
    Pull only NEW conversations from the `hours`-hour window ending at `until`.
    If `until` is None, uses now (normal live cron behaviour).
    Uses bulk deduplication — 2 DB queries upfront instead of one per conversation.
    """
    until     = until or datetime.now(timezone.utc)
    since     = until - timedelta(hours=hours)
    since_iso = since.isoformat()
    until_iso = until.isoformat()

    print(f"[Chatbot QA] Pulling conversations {since_iso[:16]} → {until_iso[:16]} UTC...")

    client     = pymongo.MongoClient(MONGO_URI)
    collection = client["asbl_loft"]["conversations"]

    # Step 1 — get all IDs in the window (lightweight projection, no full docs)
    all_in_window = list(collection.find(
        {
            "$or": [
                {"createdAt": {"$gte": since_iso, "$lte": until_iso}},
                {"createdAt": {"$gte": since,     "$lte": until}}
            ]
        },
        {"conversationId": 1}
    ))
    all_ids = [c.get("conversationId") for c in all_in_window if c.get("conversationId")]
    print(f"[Chatbot QA] Found {len(all_ids)} conversations in window")

    # Step 2 — bulk check which IDs are already evaluated (1 query, not N)
    results_db    = get_db()
    already_done  = set(
        r["conversation_id"]
        for r in results_db["chatbot_qa"].find(
            {"conversation_id": {"$in": all_ids}},
            {"conversation_id": 1}
        )
    )
    new_ids = [cid for cid in all_ids if cid not in already_done]
    print(f"[Chatbot QA] {len(already_done)} already evaluated, {len(new_ids)} new to process")

    if not new_ids:
        print("[Chatbot QA] Nothing new to evaluate.")
        return

    # Step 3 — fetch full docs only for new conversations
    new_convs = list(collection.find(
        {"conversationId": {"$in": new_ids}},
        sort=[("createdAt", -1)]
    ))

    kb           = load_knowledge_base()
    agent_prompt = load_agent_prompt()
    for conv in new_convs:
        run_on_new_conversation(conv, kb, agent_prompt, client)

    print(f"[Chatbot QA] Done. Evaluated {len(new_convs)} new conversations.")


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
