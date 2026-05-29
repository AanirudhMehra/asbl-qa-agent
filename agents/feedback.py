"""
Feedback Agent — The Manager

Reads all QA outputs from the last cycle and uses the LLM to identify
every genuine problem. No rule-based checks — the LLM sees everything
and decides on its own what is wrong.

Output: a list of Problem objects passed directly to the Recommendation Agent.
"""

import os
import sys
import json
from datetime import datetime

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import (save_feedback, save_health_score,
                get_recent_results_hours, get_health_history, get_connection)
from llm import ask_json

PROMPT_FILE = os.path.join(os.path.dirname(__file__), 'prompts', 'feedback_reasoning.md')

def load_agent_prompt() -> str:
    with open(PROMPT_FILE, "r") as f:
        return f.read()

SEVERITY_PENALTY = {
    "HIGH":   2.0,
    "MEDIUM": 0.8,
    "LOW":    0.2,
}

_problem_counter = [0]


def _make_problem(title, urgency, ptype, components, description,
                  evidence, what_is_wrong, what_is_not_wrong=""):
    _problem_counter[0] += 1
    return {
        "id":               f"P{_problem_counter[0]:03d}",
        "title":            title,
        "urgency":          urgency,
        "type":             ptype,
        "components":       components if isinstance(components, list) else [components],
        "description":      description,
        "evidence":         evidence,
        "what_is_wrong":    what_is_wrong,
        "what_is_not_wrong": what_is_not_wrong,
    }


# ════════════════════════════════════════════════════════════════════════════
# HEALTH SCORE COMPUTATION
# ════════════════════════════════════════════════════════════════════════════

def compute_health_score(results: list) -> tuple:
    """
    Returns (health_score 0–10, fail_rate 0–1).
    Penalty per issue = severity_weight × confidence.
    High-confidence HIGH issue hurts more than a low-confidence one.
    """
    if not results:
        return 0.0, 0.0

    total     = len(results)
    fails     = sum(1 for r in results if r.get("status") == "FAIL")
    fail_rate = round(fails / total, 3)

    adjusted = []
    for r in results:
        base       = r.get("score") or 0
        confidence = r.get("confidence") or 0.5
        issues     = r.get("issues") or []
        penalty    = sum(
            SEVERITY_PENALTY.get(i.get("severity", "LOW"), 0.2) * confidence
            for i in issues
        )
        adjusted.append(max(0.0, min(10.0, base - penalty)))

    return round(sum(adjusted) / total, 2), fail_rate


def detect_trend(history: list) -> str:
    if len(history) < 2:
        return "INSUFFICIENT_DATA"
    scores = [h["score"] for h in history]
    recent = scores[-3:] if len(scores) >= 3 else scores
    if all(recent[i] < recent[i - 1] for i in range(1, len(recent))):
        return "DECLINING"
    if all(recent[i] > recent[i - 1] for i in range(1, len(recent))):
        return "IMPROVING"
    return "STABLE"


# ════════════════════════════════════════════════════════════════════════════
# LLM — FINDS ALL PROBLEMS
# ════════════════════════════════════════════════════════════════════════════

def find_problems_with_llm(
    chatbot_results: list,
    voice_results: list,
    analytics_doc: dict,
    chatbot_score: float,
    voice_score: float,
    chatbot_history: list,
    voice_history: list,
    analytics_history: list,
) -> list:
    """
    Give the LLM the full picture from all agents and ask it to identify
    every genuine problem — single-component issues, cross-agent patterns,
    calibration issues, ops gaps, everything.
    """

    def format_results(results, label):
        if not results:
            return f"{label}: no data this cycle"
        lines = [f"{label} ({len(results)} evaluated):"]
        for r in results:
            issues = "; ".join(
                f"{i.get('severity')}:{i.get('type')} (conf={i.get('confidence', '?')})"
                for i in (r.get("issues") or [])
            ) or "no issues"
            lines.append(
                f"  status={r.get('status')} score={r.get('score')} "
                f"confidence={r.get('confidence')} | {issues}"
            )
        return "\n".join(lines)

    def format_history(history, label):
        if not history:
            return f"{label} history: none"
        scores = [f"{h['recorded_at'][:10]}:{round(h['score'],1)}" for h in history[-7:]]
        return f"{label} history (last 7): {', '.join(scores)}"

    def format_analytics(doc):
        if not doc:
            return "Analytics: no data"
        lines = ["Analytics (latest run):"]

        # Show stated goals first so LLM reasons against intent
        goals = doc.get("outcome_goals") or {}
        if goals:
            lines.append("\nSTATED GOALS (what the business wants to achieve):")
            for name, goal_text in goals.items():
                if goal_text:
                    lines.append(f"  [{name}] {goal_text}")

        # Outcome conversion rates
        for outcome_name, bands in (doc.get("band_conversion_rates") or {}).items():
            if not isinstance(bands, dict):
                continue
            overall_rate   = bands.get("_overall_rate", "?")
            overall_target = bands.get("_overall_target", 0)
            goal_text      = goals.get(outcome_name, "")
            lines.append(
                f"\n  {outcome_name} — overall: {overall_rate}% vs target {overall_target}%"
                + (f'  [Goal: "{goal_text}"]' if goal_text else "")
            )
            for band, data in bands.items():
                if band.startswith("_"):
                    continue
                if not isinstance(data, dict):
                    continue
                if data.get("total_leads", 0) > 0:
                    flag = " ← BELOW TARGET" if data.get("flag") else ""
                    converted  = data.get("converted", data.get("visit_booked", 0))
                    total      = data.get("total_leads", 0)
                    rate       = data.get("rate", data.get("visit_rate", 0)) or 0
                    target_pct = data.get("target_pct", 0)
                    lines.append(
                        f"    {band}: {converted}/{total} "
                        f"({rate*100:.1f}% vs target {target_pct}%){flag}"
                    )

        # Multiplier effectiveness
        for m, data in (doc.get("multiplier_effectiveness") or {}).items():
            if not isinstance(data, dict):
                continue
            effective = "✓" if data.get("effective") else "✗ NOT EFFECTIVE"
            lines.append(
                f"  {m}: with={data.get('with_rate', 0)*100:.0f}% "
                f"without={data.get('without_rate', 0)*100:.0f}% {effective}"
            )

        # Meta accuracy
        meta = doc.get("meta_signal_accuracy", {})
        lines.append(
            f"  Meta accuracy: {meta.get('accuracy_rate',0)*100:.1f}% "
            f"({meta.get('events_led_to_visit',0)}/{meta.get('total_events_fired',0)} events led to visit)"
        )

        # Funnel gaps
        for g in (doc.get("funnel_gaps") or []):
            lines.append(f"  Funnel gap: {g.get('detail')}")

        # Pre-computed flags (explicit — don't make the LLM re-derive these)
        flags = doc.get("flags") or []
        if flags:
            lines.append("\nANALYTICS FLAGS (pre-computed — treat these as confirmed):")
            for f in flags:
                lines.append(f"  [{f.get('severity','?')}] {f.get('type','?')}: {f.get('detail','')}")
        else:
            lines.append("\nANALYTICS FLAGS: none this cycle")

        return "\n".join(lines)

    agent_prompt = load_agent_prompt()

    prompt = f"""{agent_prompt}

---

## DATA FOR THIS CYCLE

{format_results(chatbot_results, "CHATBOT QA")}
Chatbot health score this cycle: {chatbot_score}/10
{format_history(chatbot_history, "Chatbot")}

{format_results(voice_results, "VOICE QA")}
Voice health score this cycle: {voice_score}/10
{format_history(voice_history, "Voice")}

{format_analytics(analytics_doc)}
{format_history(analytics_history, "Analytics")}

---

Now identify every genuine problem following all instructions above.
Return ONLY the JSON."""

    # Valid high-level problem types — these are MANAGER-LEVEL types, NOT QA issue types.
    # QA issue types (DECIMAL_NUMBER, KB_MISMATCH, etc.) must never appear here.
    VALID_TYPES = {"SYSTEMATIC_BUG", "CALIBRATION", "KB_OUTDATED", "PROCESS_GAP", "TREND"}

    try:
        result   = ask_json(prompt)
        raw_list = result.get("problems", [])
        problems     = []
        seen_keys    = set()   # deduplicate by (type, urgency)

        for p in raw_list:
            title         = p.get("title", "").strip()
            what_is_wrong = p.get("what_is_wrong", "").strip()
            description   = p.get("description", "").strip()
            ptype         = p.get("type", "SYSTEMATIC_BUG").strip().upper()

            # Small models (llama3.1:8b) often fill description but leave title/what_is_wrong blank
            if not title and description:
                title = description[:80]
            if not what_is_wrong and description:
                what_is_wrong = description

            # ── Guard: reject QA-level issue types that leaked into manager output ──
            # (e.g. LLM confuses DECIMAL_NUMBER issue type with health score values like 2.79)
            if ptype not in VALID_TYPES:
                print(f"[Feedback Agent] Skipping invalid problem type '{ptype}' (not a manager-level type)")
                continue

            # ── Deduplicate: same type + urgency = same problem reported twice ──
            dedup_key = (ptype, p.get("urgency", "MEDIUM"))
            if dedup_key in seen_keys:
                print(f"[Feedback Agent] Deduplicating problem type '{ptype}' ({p.get('urgency')})")
                continue
            seen_keys.add(dedup_key)

            problems.append(_make_problem(
                title             = title or "Unknown problem",
                urgency           = p.get("urgency", "MEDIUM"),
                ptype             = ptype,
                components        = p.get("components", []),
                description       = description,
                evidence          = p.get("evidence", []),
                what_is_wrong     = what_is_wrong,
                what_is_not_wrong = p.get("what_is_not_wrong", ""),
            ))

        # If LLM returned no usable problems, fall back to analytics flags deterministically
        if not any(p["title"] != "Unknown problem" for p in problems):
            print("[Feedback Agent] LLM returned empty structure — falling back to analytics flags")
            return _problems_from_analytics_flags(analytics_doc)

        return problems
    except Exception as e:
        print(f"[Feedback Agent] LLM failed: {e}")
        return []


# ════════════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════════════

def aggregate(hours: int = 4):
    """
    hours: how far back to look for QA results.
           Default 4 (matches the 4-hour runner cadence).
           Pass hours=168 (7 days) or hours=720 (30 days) for manual / one-shot runs.
    """
    global _problem_counter
    _problem_counter[0] = 0

    print(f"[Feedback Agent] Starting... (window={hours}h)")
    db = get_connection()

    # ── Pull this cycle's results ────────────────────────────────────────────
    chatbot_results = get_recent_results_hours("chatbot_qa", hours=hours)
    voice_results   = get_recent_results_hours("voice_qa",   hours=hours)

    # If nothing in window, fall back to most recent 100 results regardless of age
    if not chatbot_results:
        chatbot_results = list(db["chatbot_qa"].find(
            {"status": {"$ne": "SKIPPED"}},
            sort=[("evaluated_at", -1)], limit=100
        ))
        print(f"[Feedback Agent] No results in {hours}h window — using most recent {len(chatbot_results)} chatbot results")
    if not voice_results:
        voice_results = list(db["voice_qa"].find(
            {"status": {"$ne": "SKIPPED"}},
            sort=[("evaluated_at", -1)], limit=50
        ))
        print(f"[Feedback Agent] No results in {hours}h window — using most recent {len(voice_results)} voice results")

    analytics_doc = db["analytics_runs"].find_one(sort=[("run_at", -1)])

    # ── Compute and save health scores ───────────────────────────────────────
    chatbot_score, chatbot_fail_rate = compute_health_score(chatbot_results)
    voice_score,   voice_fail_rate   = compute_health_score(voice_results)

    if chatbot_results:
        save_health_score("chatbot", chatbot_score, chatbot_fail_rate, {
            "total_evaluated": len(chatbot_results),
            "fails": int(chatbot_fail_rate * len(chatbot_results))
        })
    if voice_results:
        save_health_score("voice", voice_score, voice_fail_rate, {
            "total_evaluated": len(voice_results),
            "fails": int(voice_fail_rate * len(voice_results))
        })
    if analytics_doc:
        flags   = analytics_doc.get("flags", [])
        high_f  = sum(1 for f in flags if f.get("severity") == "HIGH")
        med_f   = sum(1 for f in flags if f.get("severity") == "MEDIUM")
        a_score = max(0.0, 10.0 - high_f * 2.5 - med_f * 1.0)
        save_health_score("analytics", round(a_score, 2),
                          round(high_f / max(len(flags), 1), 3),
                          {"high_flags": high_f, "medium_flags": med_f, "total_flags": len(flags)})

    # ── Print health summary ─────────────────────────────────────────────────
    chatbot_history   = get_health_history("chatbot",   days=7)
    voice_history     = get_health_history("voice",     days=7)
    analytics_history = get_health_history("analytics", days=7)

    print(f"\n{'='*60}")
    print(f"  HEALTH SCORES (this cycle)")
    print(f"{'='*60}")
    for component, history in [("chatbot", chatbot_history),
                                ("voice",   voice_history),
                                ("analytics", analytics_history)]:
        trend = detect_trend(history) if history else "INSUFFICIENT_DATA"
        score = {"chatbot": chatbot_score, "voice": voice_score}.get(component, "–")
        print(f"  {component:<12}  score={score}   trend={trend}")
    print(f"{'='*60}\n")

    # ── LLM identifies all problems ──────────────────────────────────────────
    print("[Feedback Agent] Asking LLM to identify problems...")
    problems = find_problems_with_llm(
        chatbot_results, voice_results, analytics_doc,
        chatbot_score, voice_score,
        chatbot_history, voice_history, analytics_history,
    )

    # ── Print problem report ─────────────────────────────────────────────────
    if problems:
        print(f"\n{'='*60}")
        print(f"  PROBLEMS FOUND ({len(problems)})")
        print(f"{'='*60}")
        for p in sorted(problems, key=lambda x: {"HIGH": 0, "MEDIUM": 1, "LOW": 2}[x["urgency"]]):
            print(f"\n  [{p['id']}] [{p['urgency']}] {p['title']}")
            print(f"  Components      : {', '.join(p['components'])}")
            print(f"  What's wrong    : {p['what_is_wrong']}")
            print(f"  What's NOT wrong: {p['what_is_not_wrong']}")
            print(f"  Detail          : {p['description']}")
        print(f"\n{'='*60}")
    else:
        print("\n  ✓ No problems found. All systems healthy.\n")

    # ── Alert if HIGH problems ────────────────────────────────────────────────
    high_problems = [p for p in problems if p["urgency"] == "HIGH"]
    if high_problems:
        from notifier import notify
        notify("Feedback Agent", f"{len(high_problems)} HIGH PRIORITY PROBLEMS", {
            "problems": " | ".join(p["title"] for p in high_problems),
            "total": len(problems)
        })

    # ── Persist automated feedback entry ─────────────────────────────────────
    feedback_entry = {
        "submitted_at":       datetime.now().isoformat(),
        "source":             "automated",
        "window_hours":       4,
        "chatbot_health":     round(chatbot_score, 2),
        "voice_health":       round(voice_score, 2),
        "chatbot_fail_rate":  round(chatbot_fail_rate, 3),
        "voice_fail_rate":    round(voice_fail_rate, 3),
        "chatbot_evaluated":  len(chatbot_results),
        "voice_evaluated":    len(voice_results),
        "problems_found":     len(problems),
        "high_problems":      len([p for p in problems if p["urgency"] == "HIGH"]),
        "medium_problems":    len([p for p in problems if p["urgency"] == "MEDIUM"]),
        "top_issue_types":    _top_issue_types(chatbot_results + voice_results),
        "problems":           problems,
        "recommendations_generated": False   # recommendation agent updates this
    }
    save_feedback(feedback_entry)
    print(f"[Feedback Agent] Feedback entry saved to db.")

    print(f"[Feedback Agent] Done. {len(problems)} problems identified.")
    return problems


def _problems_from_analytics_flags(analytics_doc: dict) -> list:
    """
    Deterministic fallback — converts analytics flags directly to Problem objects.
    Used when the LLM fails to structure its response properly (small models).
    No LLM call needed — all information comes from the pre-computed flags.
    """
    if not analytics_doc:
        return []

    # Severity + component maps per flag type
    FLAG_META = {
        "CHATBOT_HIGH_FAIL_RATE":      ("HIGH",   ["chatbot"],           "SYSTEMATIC_BUG"),
        "VOICE_HIGH_FAIL_RATE":        ("HIGH",   ["voice"],             "SYSTEMATIC_BUG"),
        "SHARED_KB_ISSUE":             ("HIGH",   ["chatbot", "voice"],  "KB_OUTDATED"),
        "BAND_CONVERSION_BELOW_TARGET":("HIGH",   ["analytics"],         "CALIBRATION"),
        "OVERALL_OUTCOME_BELOW_TARGET":("HIGH",   ["analytics"],         "CALIBRATION"),
        "META_SIGNAL_LOW_ACCURACY":    ("HIGH",   ["analytics"],         "CALIBRATION"),
        "MULTIPLIER_INEFFECTIVE":      ("MEDIUM", ["analytics"],         "CALIBRATION"),
        "CALIBRATION_NOT_BOT_PROBLEM": ("HIGH",   ["analytics"],         "CALIBRATION"),
        "BOT_FAILURE_AND_CALIBRATION": ("HIGH",   ["chatbot", "voice"],  "SYSTEMATIC_BUG"),
        "SCORING_MODEL_MISCALIBRATED": ("HIGH",   ["analytics"],         "CALIBRATION"),
        "KB_DATA_WRONG":               ("HIGH",   ["chatbot", "voice"],  "KB_OUTDATED"),
    }

    NOT_WRONG = {
        "CALIBRATION_NOT_BOT_PROBLEM": "The chatbot and voice agents are not the problem — QA health is acceptable.",
        "KB_DATA_WRONG":               "The agents are behaving correctly — the KB data is the source of error.",
        "MULTIPLIER_INEFFECTIVE":      "The band thresholds and base scoring are not the issue here.",
    }

    problems = []
    seen_types = set()

    for flag in analytics_doc.get("flags", []):
        ftype   = flag.get("type", "UNKNOWN")
        detail  = flag.get("detail", "")
        if not detail or ftype in seen_types:
            continue
        seen_types.add(ftype)

        meta      = FLAG_META.get(ftype, ("MEDIUM", ["analytics"], "SYSTEMATIC_BUG"))
        urgency   = flag.get("severity", meta[0])
        comps     = meta[1]
        ptype     = meta[2]
        not_wrong = NOT_WRONG.get(ftype, "")

        # Build a readable title from the flag type
        title = ftype.replace("_", " ").title()

        problems.append(_make_problem(
            title             = title,
            urgency           = urgency,
            ptype             = ptype,
            components        = comps,
            description       = detail,
            evidence          = [detail[:120]],
            what_is_wrong     = detail,
            what_is_not_wrong = not_wrong,
        ))

    return problems


def _top_issue_types(results: list, n: int = 5) -> list:
    """Return the N most frequent issue types across a list of QA results."""
    from collections import Counter
    counter = Counter()
    for r in results:
        for issue in r.get("issues", []):
            counter[issue.get("type", "UNKNOWN")] += 1
    return [t for t, _ in counter.most_common(n)]


# ════════════════════════════════════════════════════════════════════════════
# HUMAN FEEDBACK (separate from automated checks)
# ════════════════════════════════════════════════════════════════════════════

def tag_human_feedback(text: str) -> dict:
    prompt = f"""Categorize this feedback about an AI real estate chatbot or voice agent.

Feedback: "{text}"

Respond ONLY with this JSON:
{{
  "product": "chatbot",
  "type": "bug",
  "priority": "high",
  "tag": "PRICE_ISSUE",
  "actionable": true,
  "summary": "one sentence summary"
}}

product: chatbot / voice_agent / analytics / general
type: bug / suggestion / complaint / praise
priority: high / medium / low
tag: PRICE_ISSUE / RERA_NUMBER / TONE / LANGUAGE / LEAD_CAPTURE / ANALYTICS / META_SIGNAL / PERFORMANCE / OTHER
Return ONLY the JSON."""
    try:
        return ask_json(prompt)
    except Exception:
        return {"product": "general", "type": "suggestion", "priority": "medium",
                "tag": "OTHER", "actionable": True, "summary": text[:100]}


def submit(text: str, submitted_by: str = "anonymous"):
    print(f"[Feedback Agent] Processing feedback from {submitted_by}...")
    tagged = tag_human_feedback(text)
    entry  = {"text": text, "submitted_by": submitted_by,
               "submitted_at": datetime.now().isoformat(), **tagged}
    save_feedback(entry)
    print(f"[Feedback Agent] Saved [{entry['tag']}] [{entry['priority']}] — {entry['summary']}")
    return entry


def list_feedback(limit: int = 20):
    db   = get_connection()
    rows = list(db["feedback"].find(sort=[("submitted_at", -1)], limit=limit))
    print(f"\n[Feedback] Last {len(rows)} entries:\n")
    for r in rows:
        print(f"  [{r.get('submitted_at','')[:10]}] [{r.get('tag')}] [{r.get('priority')}] {r.get('summary')}")
        print(f"    By: {r.get('submitted_by')} | Product: {r.get('product')} | Type: {r.get('type')}\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python feedback.py aggregate")
        print("  python feedback.py submit \"feedback text\" [name]")
        print("  python feedback.py list [limit]")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "aggregate":
        aggregate()
    elif cmd == "submit":
        text = sys.argv[2]
        by   = sys.argv[3] if len(sys.argv) > 3 else "anonymous"
        submit(text, by)
    elif cmd == "list":
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else 20
        list_feedback(limit)
