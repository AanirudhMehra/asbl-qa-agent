import os
import json
from datetime import datetime, timedelta

import pymongo
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

MONGO_URI_RESULTS = os.getenv("MONGO_URI_RESULTS")
DB_NAME = "qa_results"


def get_db():
    client = pymongo.MongoClient(MONGO_URI_RESULTS)
    return client[DB_NAME]


def init_db():
    db = get_db()
    # Create collections with validation (MongoDB creates them on first insert,
    # but we explicitly create indexes here for query performance)
    collections = [
        "chatbot_qa",
        "voice_qa",
        "analytics_runs",
        "feedback",
        "health_scores",
        "recommendations"
    ]
    existing = db.list_collection_names()
    for col in collections:
        if col not in existing:
            db.create_collection(col)

    # Indexes for fast queries
    db["chatbot_qa"].create_index([("evaluated_at", -1)])
    db["chatbot_qa"].create_index([("status", 1)])
    db["voice_qa"].create_index([("evaluated_at", -1)])
    db["voice_qa"].create_index([("status", 1)])
    db["analytics_runs"].create_index([("run_at", -1)])
    db["health_scores"].create_index([("component", 1), ("recorded_at", -1)])
    db["feedback"].create_index([("submitted_at", -1)])
    db["recommendations"].create_index([("generated_at", -1)])

    print(f"[DB] MongoDB qa_results database ready.")


def save_chatbot_result(result: dict):
    db = get_db()
    doc = {
        "conversation_id": result.get("conversation_id"),
        "status":          result.get("status"),
        "score":           result.get("score"),
        "confidence":      result.get("confidence", 0.5),
        "turn_count":      result.get("turn_count"),
        "issues":          result.get("issues", []),
        "summary":         result.get("summary"),
        "evaluated_at":    result.get("evaluated_at", datetime.now().isoformat())
    }
    db["chatbot_qa"].insert_one(doc)


def save_voice_result(result: dict):
    db = get_db()
    doc = {
        "call_sid":           result.get("call_sid"),
        "phone_number":       result.get("phone_number"),
        "call_direction":     result.get("call_direction"),
        "language_used":      result.get("language_used"),
        "project":            result.get("project"),
        "status":             result.get("status"),
        "score":              result.get("score"),
        "confidence":         result.get("confidence", 0.5),
        "language_compliance":result.get("language_compliance"),
        "issues":             result.get("issues", []),
        "summary":            result.get("summary"),
        "evaluated_at":       result.get("evaluated_at", datetime.now().isoformat())
    }
    db["voice_qa"].insert_one(doc)


def save_analytics_run(result: dict):
    db = get_db()
    doc = {
        "run_at":                   result.get("run_at", datetime.now().isoformat()),
        "outcomes_checked":         result.get("outcomes_checked", []),
        "outcome_goals":            result.get("outcome_goals", {}),
        "band_conversion_rates":    result.get("band_conversion_rates", {}),
        "multiplier_effectiveness": result.get("multiplier_effectiveness", {}),
        "meta_signal_accuracy":     result.get("meta_signal_accuracy", {}),
        "funnel_gaps":              result.get("funnel_gaps", []),
        "flags":                    result.get("flags", []),
        "agent_messages":           result.get("agent_messages", []),  # full ReAct conversation log
    }
    db["analytics_runs"].insert_one(doc)


def save_feedback(entry: dict):
    db = get_db()
    db["feedback"].insert_one(entry)


def save_health_score(component: str, score: float, fail_rate: float, details: dict):
    db = get_db()
    db["health_scores"].insert_one({
        "recorded_at": datetime.now().isoformat(),
        "component": component,
        "score": score,
        "fail_rate": fail_rate,
        "details": details
    })


def save_recommendation(result: dict):
    db = get_db()
    db["recommendations"].insert_one({
        "generated_at": datetime.now().isoformat(),
        "negative_signals": result.get("negative_signals", []),
        "root_cause": result.get("root_cause", ""),
        "fixes": result.get("fixes", []),
        "priority": result.get("priority", "")
    })


def get_recent_results(collection: str, days: int = 7) -> list:
    db = get_db()
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    return list(db[collection].find(
        {"evaluated_at": {"$gte": cutoff}},
        sort=[("evaluated_at", -1)]
    ))


def get_recent_results_hours(collection: str, hours: int = 4) -> list:
    """Pull results evaluated within the last N hours — matches the runner frequency."""
    db = get_db()
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
    return list(db[collection].find(
        {"evaluated_at": {"$gte": cutoff}},
        sort=[("evaluated_at", -1)]
    ))


def already_evaluated(collection: str, id_field: str, id_value: str) -> bool:
    """
    Check if a conversation or call has already been evaluated.
    Prevents re-processing the same item on every 4-hour run.

    Usage:
        already_evaluated("chatbot_qa", "conversation_id", "c-123456")
        already_evaluated("voice_qa",   "call_sid",        "abc-xyz")
    """
    db = get_db()
    return db[collection].find_one({id_field: id_value}) is not None


def get_health_history(component: str, days: int = 30) -> list:
    db = get_db()
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    return list(db["health_scores"].find(
        {"component": component, "recorded_at": {"$gte": cutoff}},
        sort=[("recorded_at", 1)]
    ))


def get_connection():
    # Compatibility shim — returns the db object directly
    return get_db()


if __name__ == "__main__":
    init_db()
