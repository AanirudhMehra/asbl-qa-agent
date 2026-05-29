"""
Analytics Agent — ReAct Orchestrator (Option B)

The orchestrator manages three specialist agents:

  qa_health_checker   → reads chatbot_qa + voice_qa + health_scores from qa_results DB
                        answers: are the bots performing well right now?

  conversion_checker  → reads scores_overall + meta_conversion_events from prod DB
                        answers: are bands converting? are Meta events firing on real leads?
                        (band + meta combined — they measure the same underlying thing)

  multiplier_checker  → reads multiplier_completion_events + scores_overall from prod DB
                        answers: are the M1-M4 score boosts actually helping?

  synthesizer         → reads ALL three findings together
                        can now say things like:
                          "QA healthy + conversion bad = calibration, not bot problem"
                          "QA failing + conversion bad = bot is sending wrong info"
                          "QA healthy + multipliers broken + meta low = scoring model"

Communication:
  orchestrator briefs each agent (tells them what was already found)
  agent does its work and reports back
  orchestrator reads the report, decides what to call next
  all messages are logged to MongoDB
"""

import os
import sys
import json
from datetime import datetime, timedelta
from typing import TypedDict, Annotated, Any
import operator

import pymongo
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import save_analytics_run, get_db as get_results_db
from llm import ask_json
from notifier import notify

MONGO_URI_PROD  = os.getenv("MONGO_URI_PROD")
OUTCOMES_CONFIG = os.path.join(os.path.dirname(__file__), '..', 'config', 'outcomes.json')

BANDS       = ["Band1_Spark", "Band2_Engaged", "Band3_Intent", "Band4_Qualified", "Band5_Hot"]
MULTIPLIERS = ["M1_affordability_yes", "M2_aff_no_bounce_30s", "M3_address_typed", "M4_OTP_verified"]

OUTCOME_FIELD_MAP = {
    "site_visit_booked":       ("milestones.has_visit_booked",      None),
    "otp_verified":            ("milestones.has_otp_verified",       None),
    "affordability_confirmed": ("milestones.affordability_outcome", "YES"),
}


# ════════════════════════════════════════════════════════════════════════════
# SHARED STATE
# ════════════════════════════════════════════════════════════════════════════

class AnalyticsState(TypedDict):
    goals:        dict
    findings:     dict                          # each agent writes its report here
    next:         str                           # orchestrator sets this to route
    briefing:     str                           # orchestrator's message to the next agent
    messages:     Annotated[list, operator.add] # full conversation log
    final_output: dict
    _prod_db:     Any                           # prod MongoDB (analytics_db)
    _results_db:  Any                           # qa_results MongoDB (chatbot_qa, voice_qa)


# ════════════════════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════════════════════

def load_outcomes() -> list:
    with open(OUTCOMES_CONFIG, "r") as f:
        cfg = json.load(f)
    return [o for o in cfg.get("outcomes", []) if o.get("active", True)]


def load_primary_kpis() -> dict:
    """
    Load primary KPIs from outcomes.json.
    These are your top-level business goals — the orchestrator reasons all findings
    against them. Change them in config/outcomes.json; no code change needed.
    Returns: {kpi_name: goal_text}
    """
    with open(OUTCOMES_CONFIG, "r") as f:
        cfg = json.load(f)
    kpis = {}
    for kpi in cfg.get("primary_kpis", []):
        if kpi.get("active", True):
            kpis[kpi["name"]] = (
                f"{kpi.get('goal', '')} "
                f"[Target: {kpi.get('target', '')}] "
                f"[Measured by: {kpi.get('how_we_measure', '')}]"
            )
    return kpis


def get_outcome_value(doc: dict, outcome_name: str) -> bool:
    mapping = OUTCOME_FIELD_MAP.get(outcome_name)
    if not mapping:
        return False
    field_path, expected = mapping
    value = doc
    for part in field_path.split("."):
        if not isinstance(value, dict):
            return False
        value = value.get(part)
    return value == expected if expected is not None else bool(value)


def msg(sender: str, receiver: str, content: str) -> dict:
    return {"from": sender, "to": receiver,
            "content": content, "timestamp": datetime.now().isoformat()}


# ════════════════════════════════════════════════════════════════════════════
# ORCHESTRATOR
# Only node with an LLM. Reads all findings, decides who to call next.
# ════════════════════════════════════════════════════════════════════════════

ORCHESTRATOR_PROMPT = """
You are the Analytics Orchestrator for ASBL, a real estate company in Hyderabad.

You manage three analyst agents:
  - qa_health_checker  : checks whether the chatbot and voice bots are performing well
  - conversion_checker : checks whether leads in each band are converting to site visits,
                         and whether Meta ad events are firing on leads with real intent
  - multiplier_checker : checks whether the M1-M4 score multipliers actually improve conversions

Business goals:
{goals}

Findings collected so far:
{findings}

Agents already called this session: {called}

Your job:
1. Decide which agent to call next and give them a specific briefing
2. The briefing must include what you already know so the agent has context
3. When all three have reported (or you have enough), say FINISH

Return ONLY this JSON:
{{
  "next": "qa_health_checker" | "conversion_checker" | "multiplier_checker" | "FINISH",
  "briefing": "what you want this agent to check, and what you already know from other agents",
  "reasoning": "one sentence — why this next step"
}}
"""

ALL_AGENTS = {"qa_health_checker", "conversion_checker", "multiplier_checker"}


def orchestrator(state: AnalyticsState) -> dict:
    findings = state.get("findings", {})
    called   = set(findings.keys())

    # All agents done — go to synthesis
    if ALL_AGENTS.issubset(called):
        return {
            "next":     "FINISH",
            "briefing": "",
            "messages": [msg("orchestrator", "system", "All agents reported. Synthesizing.")]
        }

    prompt = ORCHESTRATOR_PROMPT.format(
        goals    = json.dumps(state.get("goals", {}), indent=2),
        findings = json.dumps(
            {k: v.get("report", "") for k, v in findings.items()}, indent=2
        ) if findings else "None yet.",
        called   = list(called) if called else "None yet",
    )

    try:
        decision   = ask_json(prompt)
        next_agent = decision.get("next", "qa_health_checker")
        briefing   = decision.get("briefing", "Run your standard check and report all findings.")
        reasoning  = decision.get("reasoning", "")
    except Exception as e:
        remaining  = list(ALL_AGENTS - called)
        next_agent = remaining[0] if remaining else "FINISH"
        briefing   = "Run your standard check and report all findings."
        reasoning  = f"LLM failed ({e}), fallback to sequential."

    print(f"\n  [Orchestrator → {next_agent}]")
    print(f"  Reasoning : {reasoning}")
    print(f"  Briefing  : {briefing[:120]}...")

    return {
        "next":     next_agent,
        "briefing": briefing,
        "messages": [msg("orchestrator", next_agent, f"BRIEFING: {briefing} | REASON: {reasoning}")],
    }


# ════════════════════════════════════════════════════════════════════════════
# AGENT 1 — qa_health_checker
# Reads chatbot_qa and voice_qa from qa_results DB.
# Tells the orchestrator: are the bots healthy right now?
# ════════════════════════════════════════════════════════════════════════════

def qa_health_checker(state: AnalyticsState) -> dict:
    # TODO (scale): Split into chatbot_qa_checker + voice_qa_checker when individual
    # query latency exceeds 2-3s or when you need different refresh cadences per channel
    # (e.g. voice hourly, chatbot daily). Adding a new node is a one-line graph change.

    db       = state["_results_db"]          # qa_results DB
    briefing = state.get("briefing", "")

    print(f"\n  [qa_health_checker] Briefing: {briefing[:80]}...")

    cutoff = (datetime.now() - timedelta(hours=4)).isoformat()

    # --- Chatbot health ---
    cb_docs  = list(db["chatbot_qa"].find({"evaluated_at": {"$gte": cutoff}}))
    # Separate spam-filtered from real evaluations
    cb_spam_docs  = [d for d in cb_docs if d.get("skip_reason") == "SPAM_FILTERED"]
    cb_eval_docs  = [d for d in cb_docs if d.get("skip_reason") != "SPAM_FILTERED"]
    cb_spam_count = len(cb_spam_docs)
    cb_total      = len(cb_eval_docs)   # only real (non-spam) conversations
    cb_spam_pct   = round(cb_spam_count / len(cb_docs) * 100, 1) if cb_docs else 0
    cb_fails = [d for d in cb_eval_docs if d.get("status") == "FAIL"]
    cb_fail_rate = round(len(cb_fails) / cb_total, 3) if cb_total > 0 else 0

    # issue_rate_per_100 normalises for conversation volume — avoids health scores
    # that are biased by whether it was a busy day or a quiet day on the website.
    cb_total_issues   = sum(len(d.get("issues", [])) for d in cb_eval_docs)
    cb_issue_rate_100 = round(cb_total_issues / cb_total * 100, 1) if cb_total > 0 else 0

    cb_issue_types = {}
    for doc in cb_fails:
        for issue in doc.get("issues", []):
            t = issue.get("type", "UNKNOWN")
            cb_issue_types[t] = cb_issue_types.get(t, 0) + 1

    # Pull last health score for chatbot
    cb_health = db["health_scores"].find_one(
        {"component": "chatbot"}, sort=[("recorded_at", -1)]
    )
    cb_score = cb_health.get("score", 0) if cb_health else 0

    # --- Voice health ---
    vc_docs  = list(db["voice_qa"].find({"evaluated_at": {"$gte": cutoff}}))
    vc_total = len(vc_docs)
    vc_fails = [d for d in vc_docs if d.get("status") == "FAIL"]
    vc_fail_rate = round(len(vc_fails) / vc_total, 3) if vc_total > 0 else 0

    vc_total_issues   = sum(len(d.get("issues", [])) for d in vc_docs)
    vc_issue_rate_100 = round(vc_total_issues / vc_total * 100, 1) if vc_total > 0 else 0

    vc_issue_types = {}
    for doc in vc_fails:
        for issue in doc.get("issues", []):
            t = issue.get("type", "UNKNOWN")
            vc_issue_types[t] = vc_issue_types.get(t, 0) + 1

    vc_health = db["health_scores"].find_one(
        {"component": "voice"}, sort=[("recorded_at", -1)]
    )
    vc_score = vc_health.get("score", 0) if vc_health else 0

    # --- Flags ---
    flags = []

    if cb_total > 0 and cb_fail_rate > 0.5:
        flags.append({
            "type": "CHATBOT_HIGH_FAIL_RATE", "severity": "HIGH",
            "source": "qa_health_checker",
            "detail": (
                f"Chatbot fail rate is {cb_fail_rate*100:.0f}% ({len(cb_fails)}/{cb_total}) "
                f"in last 4 hrs — {cb_issue_rate_100} issues per 100 conversations."
            )
        })

    if vc_total > 0 and vc_fail_rate > 0.5:
        flags.append({
            "type": "VOICE_HIGH_FAIL_RATE", "severity": "HIGH",
            "source": "qa_health_checker",
            "detail": (
                f"Voice fail rate is {vc_fail_rate*100:.0f}% ({len(vc_fails)}/{vc_total}) "
                f"in last 4 hrs — {vc_issue_rate_100} issues per 100 calls."
            )
        })

    # Same HIGH issue type in both chatbot and voice → shared KB problem
    shared_high = set(cb_issue_types.keys()) & set(vc_issue_types.keys())
    shared_high = {t for t in shared_high if t in ("KB_MISMATCH", "INVENTED_FACT", "GUARDRAIL_VIOLATION")}
    if shared_high:
        flags.append({
            "type": "SHARED_KB_ISSUE", "severity": "HIGH",
            "source": "qa_health_checker",
            "detail": (
                f"Same HIGH severity issue type(s) found in both chatbot and voice: {shared_high}. "
                f"Both agents read from the same KB — the KB data is likely wrong, not the agents."
            )
        })

    results = {
        "chatbot": {
            "total_evaluated":    cb_total,
            "spam_filtered":      cb_spam_count,
            "spam_pct":           cb_spam_pct,
            "fail_count":         len(cb_fails),
            "fail_rate":          cb_fail_rate,
            "issue_rate_per_100": cb_issue_rate_100,   # volume-normalised — use this for trend comparisons
            "health_score":       cb_score,
            "top_issue_types":    cb_issue_types,
        },
        "voice": {
            "total_evaluated":    vc_total,
            "fail_count":         len(vc_fails),
            "fail_rate":          vc_fail_rate,
            "issue_rate_per_100": vc_issue_rate_100,   # volume-normalised — use this for trend comparisons
            "health_score":       vc_score,
            "top_issue_types":    vc_issue_types,
        },
    }

    bots_healthy = cb_fail_rate <= 0.3 and vc_fail_rate <= 0.3

    spam_note = (
        f"{cb_spam_count} spam-filtered ({cb_spam_pct}% of window, saved {cb_spam_count} LLM calls). "
        if cb_spam_count > 0 else ""
    )
    report = (
        f"Chatbot: {cb_total} evaluated, {len(cb_fails)} failed ({cb_fail_rate*100:.0f}%), "
        f"{cb_issue_rate_100} issues/100 convos, health score {cb_score:.1f}. "
        f"Top issues: {cb_issue_types}. "
        f"{spam_note}"
        f"Voice: {vc_total} evaluated, {len(vc_fails)} failed ({vc_fail_rate*100:.0f}%), "
        f"{vc_issue_rate_100} issues/100 calls, health score {vc_score:.1f}. "
        f"Top issues: {vc_issue_types}. "
        f"Bots are {'HEALTHY' if bots_healthy else 'FAILING'}."
    )

    print(f"  [qa_health_checker → Orchestrator] {report[:150]}...")

    new_findings = dict(state.get("findings", {}))
    new_findings["qa_health_checker"] = {
        "results": results, "flags": flags, "report": report,
        "bots_healthy": bots_healthy,
    }

    return {
        "findings": new_findings,
        "messages": [msg("qa_health_checker", "orchestrator", report)],
    }


# ════════════════════════════════════════════════════════════════════════════
# AGENT 2 — conversion_checker
# Checks band conversion rates AND meta accuracy together.
# Both measure the same thing: are high-band leads actually converting?
# ════════════════════════════════════════════════════════════════════════════

def conversion_checker(state: AnalyticsState) -> dict:
    db       = state["_prod_db"]
    briefing = state.get("briefing", "")
    outcomes = load_outcomes()

    print(f"\n  [conversion_checker] Briefing: {briefing[:80]}...")

    scores = list(db["scores_overall"].find())

    # --- Band conversion rates ---
    band_data = {
        o["name"]: {b: {"total": 0, "converted": 0} for b in BANDS}
        for o in outcomes
    }
    for doc in scores:
        highest_band = doc.get("lifetime", {}).get("highest_band_ever")
        if highest_band not in BANDS:
            continue
        for outcome in outcomes:
            band_data[outcome["name"]][highest_band]["total"] += 1
            if get_outcome_value(doc, outcome["name"]):
                band_data[outcome["name"]][highest_band]["converted"] += 1

    band_results = {}
    flags        = []

    for outcome in outcomes:
        oname          = outcome["name"]
        olabel         = outcome["label"]
        ogoal          = outcome.get("goal", "")
        overall_target = outcome.get("targets", {}).get("overall_pct", 0) / 100.0
        by_band        = {b: pct / 100.0 for b, pct in
                          outcome.get("targets", {}).get("by_band_pct", {}).items()}

        total_all     = sum(band_data[oname][b]["total"]     for b in BANDS)
        converted_all = sum(band_data[oname][b]["converted"] for b in BANDS)
        overall_rate  = round(converted_all / total_all, 3) if total_all > 0 else 0.0

        band_results[oname] = {
            "_goal": ogoal,
            "_overall_target": round(overall_target * 100),
            "_overall_rate":   round(overall_rate * 100, 1),
        }

        if overall_target > 0 and overall_rate < overall_target and total_all >= 3:
            flags.append({
                "type": "OVERALL_OUTCOME_BELOW_TARGET", "severity": "HIGH",
                "source": "conversion_checker",
                "detail": (
                    f"[{olabel}] Overall rate {overall_rate*100:.1f}% vs target "
                    f"{overall_target*100:.0f}%. Goal: \"{ogoal}\""
                )
            })

        for band in BANDS:
            data      = band_data[oname][band]
            total     = data["total"]
            converted = data["converted"]
            rate      = round(converted / total, 3) if total > 0 else 0.0
            threshold = by_band.get(band, 0.0)
            meta_count = db["meta_conversion_events"].count_documents({"band.name": band})

            band_results[oname][band] = {
                "total_leads": total, "converted": converted,
                "rate": rate, "target_pct": round(threshold * 100),
                "meta_events_fired": meta_count, "flag": False,
            }

            if meta_count > 0 and threshold > 0 and rate < threshold and total >= 3:
                band_results[oname][band]["flag"] = True
                flags.append({
                    "type": "BAND_CONVERSION_BELOW_TARGET", "severity": "HIGH",
                    "source": "conversion_checker",
                    "detail": (
                        f"[{olabel}] {band}: {rate*100:.1f}% conversion "
                        f"(target {threshold*100:.0f}%), {meta_count} Meta events fired. "
                        f"Goal: \"{ogoal}\""
                    )
                })

    # --- Meta accuracy ---
    # Same underlying question: of the leads who triggered Meta events,
    # how many actually visited? Measured on the Meta events collection directly.
    meta_events  = list(db["meta_conversion_events"].find())
    total_events = len(meta_events)
    led_to_visit = 0

    for event in meta_events:
        lead_id    = event.get("lead_id")
        session_id = event.get("session_id")
        query      = {}
        if lead_id:
            query["lead_id"] = lead_id
        elif session_id:
            session = db["scores_session_wise"].find_one({"session_id": session_id})
            if session and session.get("lead_id"):
                query["lead_id"] = session["lead_id"]
        if query:
            lead = db["scores_overall"].find_one(query)
            if lead and lead.get("milestones", {}).get("has_visit_booked"):
                led_to_visit += 1

    meta_accuracy = round(led_to_visit / total_events, 3) if total_events > 0 else 0

    if meta_accuracy < 0.20 and total_events >= 10:
        flags.append({
            "type": "META_SIGNAL_LOW_ACCURACY", "severity": "HIGH",
            "source": "conversion_checker",
            "detail": (
                f"Only {meta_accuracy*100:.1f}% of {total_events} Meta events led to "
                f"site visits ({led_to_visit} visits). "
                f"Leads are crossing band thresholds without real purchase intent."
            )
        })

    meta_results = {
        "total_events": total_events,
        "led_to_visit": led_to_visit,
        "accuracy":     meta_accuracy,
    }

    below_target_bands = [
        b for o in band_results.values() for b, d in o.items()
        if isinstance(d, dict) and d.get("flag")
    ]

    report = (
        f"Band conversion: {len(below_target_bands)} band(s) below target: {below_target_bands}. "
        f"Meta accuracy: {meta_accuracy*100:.1f}% ({led_to_visit}/{total_events} events led to visits). "
        f"Total flags: {len(flags)}."
    )

    print(f"  [conversion_checker → Orchestrator] {report[:150]}...")

    new_findings = dict(state.get("findings", {}))
    new_findings["conversion_checker"] = {
        "band_results": band_results,
        "meta_results": meta_results,
        "flags":        flags,
        "report":       report,
    }

    return {
        "findings": new_findings,
        "messages": [msg("conversion_checker", "orchestrator", report)],
    }


# ════════════════════════════════════════════════════════════════════════════
# AGENT 3 — multiplier_checker
# Checks whether each M1-M4 multiplier actually improves site visit conversion.
# If a multiplier doesn't help, the score boost it gives is noise.
# ════════════════════════════════════════════════════════════════════════════

def multiplier_checker(state: AnalyticsState) -> dict:
    db       = state["_prod_db"]
    briefing = state.get("briefing", "")
    scores   = list(db["scores_overall"].find())

    print(f"\n  [multiplier_checker] Briefing: {briefing[:80]}...")

    mult_data = {
        m: {"with": {"total": 0, "visits": 0}, "without": {"total": 0, "visits": 0}}
        for m in MULTIPLIERS
    }

    for doc in scores:
        lead_id               = str(doc.get("lead_id", ""))
        completed_multipliers = []
        if lead_id:
            events = db["multiplier_completion_events"].find({"lead_id": lead_id})
            completed_multipliers = [e.get("pattern_name") for e in events]
        visit_booked = doc.get("milestones", {}).get("has_visit_booked", False)

        for m in MULTIPLIERS:
            m_short = m.split("_")[0]
            if m_short in completed_multipliers:
                mult_data[m]["with"]["total"] += 1
                if visit_booked:
                    mult_data[m]["with"]["visits"] += 1
            else:
                mult_data[m]["without"]["total"] += 1
                if visit_booked:
                    mult_data[m]["without"]["visits"] += 1

    results = {}
    flags   = []

    for m, data in mult_data.items():
        with_total    = data["with"]["total"]
        without_total = data["without"]["total"]
        with_rate     = round(data["with"]["visits"]    / with_total,    3) if with_total    > 0 else 0
        without_rate  = round(data["without"]["visits"] / without_total, 3) if without_total > 0 else 0
        effective     = with_rate > without_rate

        results[m] = {
            "with_rate":    with_rate,
            "without_rate": without_rate,
            "effective":    effective,
            "sample_size":  with_total,
        }

        if not effective and with_total >= 5:
            flags.append({
                "type": "MULTIPLIER_INEFFECTIVE", "severity": "MEDIUM",
                "source": "multiplier_checker",
                "detail": (
                    f"{m}: leads WITH multiplier convert at {with_rate*100:.0f}%, "
                    f"leads WITHOUT convert at {without_rate*100:.0f}%. "
                    f"Score boost is not improving conversions."
                )
            })

    ineffective = [m for m, d in results.items() if not d["effective"] and d["sample_size"] >= 5]
    report = (
        f"Checked {len(MULTIPLIERS)} multipliers. "
        f"Ineffective: {ineffective if ineffective else 'none'}. "
        f"Detail: " + ", ".join(
            f"{m}={'✓' if d['effective'] else '✗'} "
            f"({d['with_rate']*100:.0f}% vs {d['without_rate']*100:.0f}%)"
            for m, d in results.items()
        )
    )

    print(f"  [multiplier_checker → Orchestrator] {report[:150]}...")

    new_findings = dict(state.get("findings", {}))
    new_findings["multiplier_checker"] = {
        "results": results, "flags": flags, "report": report,
    }

    return {
        "findings": new_findings,
        "messages": [msg("multiplier_checker", "orchestrator", report)],
    }


# ════════════════════════════════════════════════════════════════════════════
# SYNTHESIZER
# Reads all three findings. Makes cross-pattern calls the individual agents can't.
# This is where QA health + conversion data + multiplier data come together.
# ════════════════════════════════════════════════════════════════════════════

def synthesizer(state: AnalyticsState) -> dict:
    findings = state.get("findings", {})

    qa_finding   = findings.get("qa_health_checker",  {})
    conv_finding = findings.get("conversion_checker", {})
    mult_finding = findings.get("multiplier_checker", {})

    qa_flags   = qa_finding.get("flags",   [])
    conv_flags = conv_finding.get("flags", [])
    mult_flags = mult_finding.get("flags", [])
    all_flags  = qa_flags + conv_flags + mult_flags

    bots_healthy     = qa_finding.get("bots_healthy", True)
    conv_flags_exist = any(f["type"] in (
        "BAND_CONVERSION_BELOW_TARGET", "OVERALL_OUTCOME_BELOW_TARGET", "META_SIGNAL_LOW_ACCURACY"
    ) for f in conv_flags)
    mult_flags_exist = bool(mult_flags)

    cross_flags = []

    # ── Cross-pattern 1 ──────────────────────────────────────────────────
    # Bots healthy BUT conversion is bad
    # → Not a bot problem. Scoring model is miscalibrated.
    if bots_healthy and conv_flags_exist:
        cross_flags.append({
            "type": "CALIBRATION_NOT_BOT_PROBLEM", "severity": "HIGH",
            "source": "synthesizer",
            "detail": (
                "Chatbot and voice agents are performing well (QA health is good). "
                "But lead conversion rates are below target. "
                "The bots are doing their job correctly — the problem is in the scoring model. "
                "Leads are being promoted to high bands without genuine purchase intent."
            )
        })

    # ── Cross-pattern 2 ──────────────────────────────────────────────────
    # Bots failing AND conversion is bad
    # → Two separate problems. Don't conflate them.
    if not bots_healthy and conv_flags_exist:
        cross_flags.append({
            "type": "BOT_FAILURE_AND_CALIBRATION", "severity": "HIGH",
            "source": "synthesizer",
            "detail": (
                "Both QA agents are failing AND conversion rates are below target. "
                "These are two separate root causes — do not conflate them. "
                "Fix 1: the bots are giving wrong information (fix KB or agent prompts). "
                "Fix 2: the scoring model is miscalibrated (fix band thresholds)."
            )
        })

    # ── Cross-pattern 3 ──────────────────────────────────────────────────
    # Conversion bad + multipliers ineffective
    # → Scoring model is broken in two places at once (thresholds + weights)
    if conv_flags_exist and mult_flags_exist:
        broken = [f["detail"][:60] for f in mult_flags]
        cross_flags.append({
            "type": "SCORING_MODEL_MISCALIBRATED", "severity": "HIGH",
            "source": "synthesizer",
            "detail": (
                f"Band conversion rates are below target AND "
                f"{len(mult_flags)} multiplier(s) are not improving conversions. "
                f"The scoring model is over-rewarding browsing activity. "
                f"Both the band thresholds and the multiplier weights need recalibration. "
                f"Broken multipliers: {broken}"
            )
        })

    # ── Cross-pattern 4 ──────────────────────────────────────────────────
    # Same HIGH issue in both bots → shared KB
    shared_kb = any(f["type"] == "SHARED_KB_ISSUE" for f in qa_flags)
    if shared_kb:
        cross_flags.append({
            "type": "KB_DATA_WRONG", "severity": "HIGH",
            "source": "synthesizer",
            "detail": (
                "The same factual error type is appearing in both chatbot and voice QA. "
                "Both agents read from the same knowledge base files. "
                "This is not an agent bug — the KB data itself is outdated or wrong. "
                "Update the KB files, not the agent prompts."
            )
        })

    final_flags = all_flags + cross_flags

    # Goals come from shared state — loaded from config/outcomes.json at startup.
    # No hardcoding here: KPIs change in the config file, not in code.
    goals    = state.get("goals", {})
    outcomes = load_outcomes()   # needed for outcomes_checked list

    final_output = {
        "run_at":                   datetime.now().isoformat(),
        "outcomes_checked":         [o["name"] for o in outcomes],
        "outcome_goals":            goals,                          # includes visitor_to_lead_ratio
        "qa_health":                qa_finding.get("results", {}),
        "bot_issue_rates_per_100": {
            "chatbot": qa_finding.get("results", {}).get("chatbot", {}).get("issue_rate_per_100", 0),
            "voice":   qa_finding.get("results", {}).get("voice",   {}).get("issue_rate_per_100", 0),
        },
        "band_conversion_rates":    conv_finding.get("band_results", {}),
        "meta_signal_accuracy":     conv_finding.get("meta_results", {}),
        "multiplier_effectiveness": mult_finding.get("results", {}),
        "flags":                    final_flags,
        "agent_messages":           state.get("messages", []),
    }

    print(f"\n  [Synthesizer] {len(all_flags)} agent flags + {len(cross_flags)} cross-pattern flags "
          f"= {len(final_flags)} total")

    return {
        "final_output": final_output,
        "messages":     [msg("synthesizer", "system",
                             f"Done. {len(final_flags)} flags. "
                             f"Cross-patterns: {[f['type'] for f in cross_flags]}")]
    }


# ════════════════════════════════════════════════════════════════════════════
# ROUTING
# ════════════════════════════════════════════════════════════════════════════

def route_after_orchestrator(state: AnalyticsState) -> str:
    nxt = state.get("next", "FINISH")
    return "synthesizer" if nxt == "FINISH" else nxt


# ════════════════════════════════════════════════════════════════════════════
# GRAPH
# ════════════════════════════════════════════════════════════════════════════

def build_graph():
    graph = StateGraph(AnalyticsState)

    graph.add_node("orchestrator",       orchestrator)
    graph.add_node("qa_health_checker",  qa_health_checker)
    graph.add_node("conversion_checker", conversion_checker)
    graph.add_node("multiplier_checker", multiplier_checker)
    graph.add_node("synthesizer",        synthesizer)

    graph.set_entry_point("orchestrator")

    graph.add_conditional_edges(
        "orchestrator",
        route_after_orchestrator,
        {
            "qa_health_checker":  "qa_health_checker",
            "conversion_checker": "conversion_checker",
            "multiplier_checker": "multiplier_checker",
            "synthesizer":        "synthesizer",
        }
    )

    # Every agent reports back to orchestrator
    graph.add_edge("qa_health_checker",  "orchestrator")
    graph.add_edge("conversion_checker", "orchestrator")
    graph.add_edge("multiplier_checker", "orchestrator")
    graph.add_edge("synthesizer",        END)

    return graph.compile()


# ════════════════════════════════════════════════════════════════════════════
# MAIN RUN
# ════════════════════════════════════════════════════════════════════════════

def run():
    print("[Analytics] Connecting to MongoDB...")
    prod_client    = pymongo.MongoClient(MONGO_URI_PROD)
    prod_db        = prod_client["analytics_db"]
    results_db     = get_results_db()       # qa_results DB

    print("[Analytics] Building orchestrator graph...")
    pipeline = build_graph()

    outcomes = load_outcomes()

    # Goals = outcome-level targets (band conversion %) + primary KPIs (plain English)
    # Both come from config/outcomes.json — change the file, no code changes needed.
    goals = {o["name"]: o.get("goal", "") for o in outcomes}
    goals.update(load_primary_kpis())   # adds visitor_to_lead_ratio, meta_spend_efficiency, etc.

    initial_state: AnalyticsState = {
        "goals":        goals,
        "findings":     {},
        "next":         "",
        "briefing":     "",
        "messages":     [],
        "final_output": {},
        "_prod_db":     prod_db,
        "_results_db":  results_db,
    }

    print("[Analytics] Starting ReAct loop...\n")
    result_state = pipeline.invoke(initial_state)
    final        = result_state["final_output"]

    # ── Print conversation log ────────────────────────────────────────────
    print(f"\n{'─'*60}")
    print("  AGENT CONVERSATION")
    print(f"{'─'*60}")
    for m in final.get("agent_messages", []):
        print(f"\n  {m['from']:25} → {m['to']}")
        print(f"  {m['content'][:180]}")

    # ── Print flags ───────────────────────────────────────────────────────
    print(f"\n{'─'*60}")
    print(f"  FLAGS ({len(final.get('flags', []))} total)")
    print(f"{'─'*60}")
    for f in final.get("flags", []):
        print(f"  [{f['severity']}] [{f['source']}] {f['type']}")
        print(f"  {f['detail'][:140]}")

    save_analytics_run(final)

    high_flags = [f for f in final.get("flags", []) if f.get("severity") == "HIGH"]
    if high_flags:
        notify("Analytics Agent", f"{len(high_flags)} HIGH FLAGS", {
            "top_issue": high_flags[0]["detail"],
            "total":     len(final.get("flags", []))
        })

    print(f"\n[Analytics] Done. {len(final.get('flags', []))} total flags.")
    return final


if __name__ == "__main__":
    run()
