"""
seed_demo.py — Inserts realistic sample data into all 6 qa_results collections.
Run once: python3 seed_demo.py
Safe to re-run (skips collections that already have data).
"""

import os
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv
import pymongo

load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

base_uri = os.getenv("MONGO_URI_RESULTS").rstrip("/")
# Mirror the same TLS override that MONGO_URI_PROD uses
MONGO_URI_RESULTS = base_uri + "?tls=true&tlsAllowInvalidCertificates=true"

client = pymongo.MongoClient(MONGO_URI_RESULTS)
db = client["qa_results"]

def ts(hours_ago=0, minutes_ago=0):
    t = datetime.now() - timedelta(hours=hours_ago, minutes=minutes_ago)
    return t.isoformat()

# ── 1. CHATBOT QA ──────────────────────────────────────────────────────────────
chatbot_docs = [
    {
        "conversation_id": "conv-demo-001",
        "status": "PASS",
        "score": 9,
        "confidence": 0.92,
        "turn_count": 6,
        "issues": [],
        "summary": "Bot correctly quoted ASBL Loft pricing and RERA number. All questions answered completely. Professional tone throughout.",
        "evaluated_at": ts(hours_ago=1),
        "session_signals": {"lead_captured": True, "visit_booked": False}
    },
    {
        "conversation_id": "conv-demo-002",
        "status": "FAIL",
        "score": 4,
        "confidence": 0.95,
        "turn_count": 8,
        "issues": [
            {
                "type": "KB_MISMATCH",
                "severity": "HIGH",
                "detail": "Bot said 'Starting price is ₹1.75 crore' in turn 3 — KB states starting price is ₹1.94 crore for ASBL Loft."
            }
        ],
        "summary": "Critical price mismatch in turn 3 — bot quoted ₹1.75 cr instead of ₹1.94 cr, which could mislead the buyer on budget.",
        "evaluated_at": ts(hours_ago=2),
        "session_signals": {"lead_captured": False, "visit_booked": False}
    },
    {
        "conversation_id": "conv-demo-003",
        "status": "FAIL",
        "score": 6,
        "confidence": 0.78,
        "turn_count": 5,
        "issues": [
            {
                "type": "INCOMPLETE_RESPONSE",
                "severity": "MEDIUM",
                "detail": "User asked 'What is the RERA number and when is possession?' in turn 2. Bot answered possession date but did not provide the RERA number which is available in the KB."
            }
        ],
        "summary": "Bot skipped the RERA number when directly asked — buyer left without key compliance information.",
        "evaluated_at": ts(hours_ago=3),
        "session_signals": {"lead_captured": True, "visit_booked": False}
    },
    {
        "conversation_id": "conv-demo-004",
        "status": "PASS",
        "score": 8,
        "confidence": 0.88,
        "turn_count": 10,
        "issues": [
            {
                "type": "MINOR_PHRASING",
                "severity": "LOW",
                "detail": "Turn 5 response used slightly informal phrasing — 'Yeah, so the project is...' — minor tone inconsistency for a premium brand."
            }
        ],
        "summary": "Accurate and helpful throughout — minor phrasing note in turn 5 but no factual issues.",
        "evaluated_at": ts(hours_ago=4),
        "session_signals": {"lead_captured": True, "visit_booked": True}
    },
    {
        "conversation_id": "conv-demo-005",
        "status": "FAIL",
        "score": 3,
        "confidence": 0.91,
        "turn_count": 7,
        "issues": [
            {
                "type": "GUARDRAIL_VIOLATION",
                "severity": "HIGH",
                "detail": "Bot said 'You are guaranteed to receive possession by December 2025' in turn 4 — no possession guarantee exists in the KB; this creates a binding commitment impression."
            },
            {
                "type": "INVENTED_FACT",
                "severity": "HIGH",
                "detail": "Bot stated 'ASBL Loft has a dedicated concierge service on every floor' in turn 6 — this amenity is not present in the KB for this project."
            }
        ],
        "summary": "Two HIGH issues: illegal possession guarantee and invented amenity — serious risk if shared with buyer.",
        "evaluated_at": ts(hours_ago=5),
        "session_signals": {"lead_captured": False, "visit_booked": False}
    },
    {
        "conversation_id": "conv-demo-006",
        "status": "FAIL",
        "score": 7,
        "confidence": 0.72,
        "turn_count": 4,
        "issues": [
            {
                "type": "TONE_ISSUE",
                "severity": "MEDIUM",
                "detail": "Turn 3: user expressed concern about project delays, bot responded 'Don't worry, all projects have delays!' without acknowledging the concern — dismissive for a premium brand."
            }
        ],
        "summary": "Tone failure when handling buyer concern about delays — deflected instead of empathising and addressing.",
        "evaluated_at": ts(hours_ago=6),
        "session_signals": {"lead_captured": True, "visit_booked": False}
    },
    {
        "conversation_id": "conv-demo-007",
        "status": "PASS",
        "score": 10,
        "confidence": 0.94,
        "turn_count": 12,
        "issues": [],
        "summary": "Perfect evaluation — all facts correct, RERA provided unprompted, professional tone, visit booking offer made at the right moment.",
        "evaluated_at": ts(hours_ago=7),
        "session_signals": {"lead_captured": True, "visit_booked": True}
    },
    {
        "conversation_id": "conv-demo-008",
        "status": "FAIL",
        "score": 5,
        "confidence": 0.81,
        "turn_count": 9,
        "issues": [
            {
                "type": "WRONG_PROJECT_RECOMMENDATION",
                "severity": "MEDIUM",
                "detail": "User stated budget of ₹1.2 crore in turn 1. Bot recommended ASBL Loft (starting ₹1.94 cr) in turn 2 with no acknowledgment of the 62% gap — significantly above budget with no explanation."
            }
        ],
        "summary": "Recommendation mismatch — bot offered a project 62% above stated budget without addressing the gap.",
        "evaluated_at": ts(hours_ago=8),
        "session_signals": {"lead_captured": False, "visit_booked": False}
    },
]

# ── 2. VOICE QA ────────────────────────────────────────────────────────────────
voice_docs = [
    {
        "call_sid": "CA-demo-001",
        "phone_number": "+91-9876543210",
        "call_direction": "inbound",
        "language_used": "English",
        "project": "ASBL Loft",
        "status": "PASS",
        "score": 9,
        "confidence": 0.90,
        "language_compliance": "PASS",
        "issues": [],
        "summary": "Anandita correctly quoted pricing, explained payment plan, and offered a site visit. Tone was warm and professional.",
        "evaluated_at": ts(hours_ago=1, minutes_ago=30)
    },
    {
        "call_sid": "CA-demo-002",
        "phone_number": "+91-9123456780",
        "call_direction": "inbound",
        "language_used": "English",
        "project": "ASBL Loft",
        "status": "FAIL",
        "score": 4,
        "confidence": 0.96,
        "language_compliance": "PASS",
        "issues": [
            {
                "type": "DECIMAL_NUMBER",
                "severity": "HIGH",
                "detail": "Anandita said 'one ninety-four crore' — this sounds like ₹194 crore to the caller. Correct verbal format: 'one point nine four crore'."
            }
        ],
        "summary": "Decimal number error — 'one ninety-four crore' could be misheard as 194 crore, critically misleading the caller on pricing.",
        "evaluated_at": ts(hours_ago=2, minutes_ago=15)
    },
    {
        "call_sid": "CA-demo-003",
        "phone_number": "+91-9988776655",
        "call_direction": "inbound",
        "language_used": "Hindi",
        "project": "ASBL Spectra",
        "status": "FAIL",
        "score": 6,
        "confidence": 0.80,
        "language_compliance": "FAIL",
        "issues": [
            {
                "type": "LANGUAGE_HANDLING",
                "severity": "MEDIUM",
                "detail": "Caller spoke Hindi throughout the entire call. Anandita responded exclusively in English with no attempt to switch — caller likely felt unheard."
            }
        ],
        "summary": "Language compliance failure — Hindi-speaking caller was responded to in English throughout, risking disengagement.",
        "evaluated_at": ts(hours_ago=3, minutes_ago=45)
    },
    {
        "call_sid": "CA-demo-004",
        "phone_number": "+91-8765432109",
        "call_direction": "inbound",
        "language_used": "English",
        "project": "ASBL Loft",
        "status": "FAIL",
        "score": 3,
        "confidence": 0.93,
        "language_compliance": "PASS",
        "issues": [
            {
                "type": "KB_MISMATCH",
                "severity": "HIGH",
                "detail": "Anandita quoted ₹6,800/sqft as the base rate — KB states ₹7,200/sqft for ASBL Loft. Caller was given an incorrect lower price."
            },
            {
                "type": "GUARDRAIL_VIOLATION",
                "severity": "HIGH",
                "detail": "Anandita said 'I fully expect you'll get possession by mid-2026, no issues' — this implies a commitment not present in the KB."
            }
        ],
        "summary": "Two HIGH issues: wrong per-sqft rate quoted and implied possession commitment — significant risk of buyer complaint.",
        "evaluated_at": ts(hours_ago=4, minutes_ago=10)
    },
    {
        "call_sid": "CA-demo-005",
        "phone_number": "+91-7654321098",
        "call_direction": "inbound",
        "language_used": "English",
        "project": "ASBL Spectra",
        "status": "PASS",
        "score": 8,
        "confidence": 0.85,
        "language_compliance": "PASS",
        "issues": [
            {
                "type": "MINOR_PHRASING",
                "severity": "LOW",
                "detail": "Minor transcription artifact in turn 4 — one line appears garbled, isolated noise not a quality failure."
            }
        ],
        "summary": "Strong call — accurate pricing, good objection handling, minor transcription artifact noted.",
        "evaluated_at": ts(hours_ago=5, minutes_ago=20)
    },
    {
        "call_sid": "CA-demo-006",
        "phone_number": "+91-6543210987",
        "call_direction": "inbound",
        "language_used": "Telugu",
        "project": "ASBL Loft",
        "status": "FAIL",
        "score": 5,
        "confidence": 0.76,
        "language_compliance": "FAIL",
        "issues": [
            {
                "type": "LANGUAGE_HANDLING",
                "severity": "MEDIUM",
                "detail": "Caller used Telugu for the majority of the call. Anandita acknowledged once but reverted to English without the caller switching back."
            }
        ],
        "summary": "Language compliance failure — Anandita reverted to English mid-call despite caller continuing in Telugu.",
        "evaluated_at": ts(hours_ago=6, minutes_ago=5)
    },
]

# ── 3. ANALYTICS RUNS ──────────────────────────────────────────────────────────
analytics_docs = [
    {
        "run_at": ts(hours_ago=4),
        "band_conversion_rates": {
            "1cr_1.5cr": {"leads": 42, "site_visits": 18, "bookings": 3, "conversion_rate": 0.071},
            "1.5cr_2cr": {"leads": 67, "site_visits": 31, "bookings": 8, "conversion_rate": 0.119},
            "2cr_3cr":   {"leads": 29, "site_visits": 15, "bookings": 5, "conversion_rate": 0.172},
            "3cr_plus":  {"leads": 11, "site_visits": 6,  "bookings": 2, "conversion_rate": 0.182},
        },
        "multiplier_effectiveness": {
            "rental_offer":   {"shown": 34, "leads_after": 22, "effectiveness": 0.647},
            "payment_plan":   {"shown": 58, "leads_after": 41, "effectiveness": 0.707},
            "site_visit_cta": {"shown": 89, "leads_after": 53, "effectiveness": 0.596},
        },
        "meta_signal_accuracy": {
            "lead_captured_matches_db": 0.94,
            "visit_booked_matches_db":  0.91,
            "discrepancy_count": 4
        },
        "funnel_gaps": [
            "1cr_1.5cr band has 42 leads but only 3 bookings — low conversion suggests price objection not being handled",
            "rental_offer artifact shown in 34 sessions but only 22 led to lead capture — copy may need review"
        ],
        "flags": [
            "meta_signal_discrepancy: 4 sessions where lead_captured=True in events but no record in CRM",
            "band_1cr_1.5cr: conversion below 8% threshold"
        ]
    },
    {
        "run_at": ts(hours_ago=8),
        "band_conversion_rates": {
            "1cr_1.5cr": {"leads": 38, "site_visits": 15, "bookings": 2, "conversion_rate": 0.053},
            "1.5cr_2cr": {"leads": 61, "site_visits": 28, "bookings": 7, "conversion_rate": 0.115},
            "2cr_3cr":   {"leads": 25, "site_visits": 13, "bookings": 4, "conversion_rate": 0.160},
        },
        "multiplier_effectiveness": {
            "rental_offer":   {"shown": 28, "leads_after": 17, "effectiveness": 0.607},
            "payment_plan":   {"shown": 52, "leads_after": 38, "effectiveness": 0.731},
            "site_visit_cta": {"shown": 81, "leads_after": 48, "effectiveness": 0.593},
        },
        "meta_signal_accuracy": {
            "lead_captured_matches_db": 0.96,
            "visit_booked_matches_db":  0.93,
            "discrepancy_count": 2
        },
        "funnel_gaps": [
            "1cr_1.5cr band remains lowest converting segment for second consecutive run"
        ],
        "flags": [
            "band_1cr_1.5cr: conversion below 8% threshold — persistent"
        ]
    },
]

# ── 4. FEEDBACK ────────────────────────────────────────────────────────────────
feedback_docs = [
    {
        "submitted_at": ts(hours_ago=4),
        "window_hours": 4,
        "chatbot_health": 71.4,
        "voice_health": 68.2,
        "overall_health": 69.8,
        "chatbot_fail_rate": 0.375,
        "voice_fail_rate": 0.50,
        "top_issue_types": ["KB_MISMATCH", "DECIMAL_NUMBER", "LANGUAGE_HANDLING"],
        "patterns": [
            {
                "pattern": "pricing_error",
                "description": "Price misquotes appearing in both chatbot and voice — likely KB entry for ASBL Loft starting price needs review",
                "affected_agents": ["chatbot_qa", "voice_qa"],
                "frequency": 3,
                "severity": "HIGH"
            },
            {
                "pattern": "decimal_verbal_format",
                "description": "DECIMAL_NUMBER errors recurring in voice — Anandita repeatedly saying 'one ninety-four' instead of 'one point nine four'",
                "affected_agents": ["voice_qa"],
                "frequency": 2,
                "severity": "HIGH"
            }
        ],
        "recommendations_generated": True
    },
    {
        "submitted_at": ts(hours_ago=8),
        "window_hours": 4,
        "chatbot_health": 78.5,
        "voice_health": 74.1,
        "overall_health": 76.3,
        "chatbot_fail_rate": 0.25,
        "voice_fail_rate": 0.333,
        "top_issue_types": ["INCOMPLETE_RESPONSE", "LANGUAGE_HANDLING", "TONE_ISSUE"],
        "patterns": [
            {
                "pattern": "rera_skip",
                "description": "Bot not providing RERA numbers when directly asked — seen in 2 chatbot conversations",
                "affected_agents": ["chatbot_qa"],
                "frequency": 2,
                "severity": "MEDIUM"
            }
        ],
        "recommendations_generated": True
    },
]

# ── 5. HEALTH SCORES ───────────────────────────────────────────────────────────
health_docs = [
    {"recorded_at": ts(hours_ago=4),  "component": "chatbot_qa", "score": 71.4, "fail_rate": 0.375, "details": {"evaluated": 8, "passed": 5, "failed": 3, "high_issues": 3, "medium_issues": 4}},
    {"recorded_at": ts(hours_ago=4),  "component": "voice_qa",   "score": 68.2, "fail_rate": 0.500, "details": {"evaluated": 6, "passed": 3, "failed": 3, "high_issues": 4, "medium_issues": 2}},
    {"recorded_at": ts(hours_ago=4),  "component": "overall",    "score": 69.8, "fail_rate": 0.429, "details": {"total_evaluated": 14, "total_failed": 6}},
    {"recorded_at": ts(hours_ago=8),  "component": "chatbot_qa", "score": 78.5, "fail_rate": 0.250, "details": {"evaluated": 8, "passed": 6, "failed": 2, "high_issues": 1, "medium_issues": 3}},
    {"recorded_at": ts(hours_ago=8),  "component": "voice_qa",   "score": 74.1, "fail_rate": 0.333, "details": {"evaluated": 6, "passed": 4, "failed": 2, "high_issues": 2, "medium_issues": 1}},
    {"recorded_at": ts(hours_ago=8),  "component": "overall",    "score": 76.3, "fail_rate": 0.286, "details": {"total_evaluated": 14, "total_failed": 4}},
    {"recorded_at": ts(hours_ago=12), "component": "chatbot_qa", "score": 82.0, "fail_rate": 0.125, "details": {"evaluated": 8, "passed": 7, "failed": 1, "high_issues": 1, "medium_issues": 0}},
    {"recorded_at": ts(hours_ago=12), "component": "voice_qa",   "score": 80.3, "fail_rate": 0.167, "details": {"evaluated": 6, "passed": 5, "failed": 1, "high_issues": 1, "medium_issues": 0}},
    {"recorded_at": ts(hours_ago=12), "component": "overall",    "score": 81.1, "fail_rate": 0.143, "details": {"total_evaluated": 14, "total_failed": 2}},
]

# ── 6. RECOMMENDATIONS ─────────────────────────────────────────────────────────
recommendation_docs = [
    {
        "generated_at": ts(hours_ago=4),
        "negative_signals": [
            {"issue_type": "KB_MISMATCH", "agent": "chatbot_qa", "frequency": 2, "detail": "Starting price for ASBL Loft quoted as ₹1.75 cr (correct: ₹1.94 cr)"},
            {"issue_type": "DECIMAL_NUMBER", "agent": "voice_qa", "frequency": 2, "detail": "Anandita saying 'one ninety-four crore' instead of 'one point nine four crore'"},
        ],
        "root_cause": "ASBL Loft pricing is being misread from the KB — the decimal format '1.94 crore' is being verbalized incorrectly by the voice agent and possibly stored ambiguously in the chatbot KB entry.",
        "priority": "HIGH",
        "fixes": [
            {
                "type": "KB_UPDATE",
                "target": "knowledge_base/webbot/asbl_loft.md",
                "description": "Add explicit note: 'Verbal format for voice: one point nine four crore (NOT one ninety-four crore)'",
                "estimated_impact": "Eliminates DECIMAL_NUMBER recurrence for this project"
            },
            {
                "type": "PROMPT_UPDATE",
                "target": "agents/prompts/voice_qa.md",
                "description": "Add example to DECIMAL_NUMBER section: 1.94 → 'one point nine four crore'. 2.15 → 'two point one five crore'.",
                "estimated_impact": "Reinforces correct format with concrete examples"
            }
        ]
    },
    {
        "generated_at": ts(hours_ago=8),
        "negative_signals": [
            {"issue_type": "INCOMPLETE_RESPONSE", "agent": "chatbot_qa", "frequency": 2, "detail": "RERA number not provided when directly asked"},
        ],
        "root_cause": "Bot appears to skip RERA numbers when answering multi-part questions — answers one part (possession date) and does not loop back to the RERA number.",
        "priority": "MEDIUM",
        "fixes": [
            {
                "type": "PROMPT_UPDATE",
                "target": "agents/prompts/chatbot_qa.md",
                "description": "Strengthen multi-question rule — add instruction: 'If user asks both RERA and any other question in the same message, RERA must be answered explicitly, not implied.'",
                "estimated_impact": "Reduces RERA skip rate in multi-part questions"
            }
        ]
    },
]

# ── INSERT ─────────────────────────────────────────────────────────────────────
def seed_collection(name, docs):
    col = db[name]
    if col.count_documents({}) > 0:
        print(f"  [SKIP] {name} already has data ({col.count_documents({})} docs)")
        return
    col.insert_many(docs)
    print(f"  [OK]   {name} — inserted {len(docs)} documents")

print("\nSeeding qa_results database...\n")
seed_collection("chatbot_qa",     chatbot_docs)
seed_collection("voice_qa",       voice_docs)
seed_collection("analytics_runs", analytics_docs)
seed_collection("feedback",       feedback_docs)
seed_collection("health_scores",  health_docs)
seed_collection("recommendations",recommendation_docs)

print("\nDone. All collections seeded.")
client.close()
