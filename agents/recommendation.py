"""
Recommendation Agent — The Engineer

Role: For every problem the Feedback Agent identified, produce a specific, actionable fix.
      Do NOT hunt for problems — that is the Feedback Agent's job.
      Do NOT produce vague suggestions — name the file, field, or config to change.

Input:  list of Problem objects from feedback.aggregate()
Output: list of Fix objects, one per problem, ranked by urgency
"""

import os
import sys
import json
from datetime import datetime

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import save_recommendation, get_health_history, get_connection
from llm import ask_json
from notifier import notify

PROMPT_FILE    = os.path.join(os.path.dirname(__file__), 'prompts', 'recommendation.md')
OUTCOMES_FILE  = os.path.join(os.path.dirname(__file__), '..', 'config', 'outcomes.json')


def load_outcome_goals() -> str:
    """Load plain-English goals from outcomes.json so the LLM knows what the business wants."""
    try:
        with open(OUTCOMES_FILE, "r") as f:
            cfg = json.load(f)
        active = [o for o in cfg.get("outcomes", []) if o.get("active", True)]
        if not active:
            return ""
        lines = ["BUSINESS GOALS (from outcomes.json — fixes must help achieve these):"]
        for o in active:
            goal = o.get("goal", "")
            if goal:
                lines.append(f"  [{o['label']}] {goal}")
        return "\n".join(lines)
    except Exception:
        return ""

def load_agent_prompt() -> str:
    with open(PROMPT_FILE, "r") as f:
        return f.read()


# ════════════════════════════════════════════════════════════════════════════
# KNOWN FIX TEMPLATES (deterministic — fast, no LLM needed)
# These cover the most common patterns we know how to fix.
# For everything else, the LLM generates the fix.
# ════════════════════════════════════════════════════════════════════════════

KNOWN_FIXES = {
    # ── Bot / KB issues ──────────────────────────────────────────────────────
    "DECIMAL_NUMBER": {
        "root_cause": "Anandita is verbalising decimal prices in compressed form ('one ninety-four') instead of 'one point nine four crore'.",
        "fix": (
            "Add an explicit number-pronunciation rule to Anandita's system prompt: "
            "'Always read decimal prices as X point Y Z — e.g. 1.94 crore = one point nine four crore. "
            "Never say one ninety-four.'"
        ),
        "where": "knowledge_base/anandita/system_prompt.md — Price Communication rules section",
        "expected_outcome": "Voice DECIMAL_NUMBER errors should drop to 0 within one cycle",
    },
    "PRICE_ACCURACY": {
        "root_cause": "KB contains outdated or incorrect prices. Both chatbot and voice agents read from the same KB and are quoting wrong figures.",
        "fix": (
            "Verify and update all prices in both KB files. "
            "Correct values: Loft 1695sqft=1.94cr+GST, 1870sqft=2.15cr+GST; "
            "Spectra 1980sqft=1.95cr+GST, 2220sqft=2.15cr+GST; Broadway=9899/sqft; Landmark=8799/sqft."
        ),
        "where": "knowledge_base/webbot/02_kb_project_loft.md AND knowledge_base/anandita/project_facts.md",
        "expected_outcome": "PRICE_ACCURACY failures clear immediately once KB is corrected",
    },
    "RERA_NUMBER": {
        "root_cause": "RERA registration numbers in the KB are incorrect or missing.",
        "fix": (
            "Verify and update RERA numbers: Loft=P02400006761, Spectra=P02400003071, "
            "Broadway=P02400009684, Landmark=P02200008770."
        ),
        "where": "knowledge_base/webbot/02_kb_project_loft.md AND knowledge_base/anandita/project_facts.md",
        "expected_outcome": "RERA errors clear immediately once KB is corrected",
    },
    "LANGUAGE_HANDLING": {
        "root_cause": "Anandita is not switching to Hindi/Telugu when the caller uses those languages.",
        "fix": (
            "Strengthen the language-switch rule in Anandita's system prompt: "
            "'If the caller speaks even one word in Hindi or Telugu, switch to that language "
            "immediately and maintain it for the entire call. Do not revert to English.'"
        ),
        "where": "knowledge_base/anandita/system_prompt.md — Language rules section",
        "expected_outcome": "Language compliance failures reduce significantly within one cycle",
    },
    "KB_OUTDATED": {
        "root_cause": "The same factual error appears in both chatbot and voice QA — both read from the same KB files, so the KB data is the source of error.",
        "fix": "Audit both KB files for outdated facts. Cross-check prices, RERA numbers, availability, and payment terms against the latest sales team data.",
        "where": "knowledge_base/webbot/02_kb_project_loft.md AND knowledge_base/anandita/project_facts.md",
        "expected_outcome": "Shared factual errors clear in both agents once KB is corrected",
    },

    # ── Analytics / scoring model issues ─────────────────────────────────────
    "META_SIGNAL_LOW_ACCURACY": {
        "root_cause": "Leads are crossing Band3/4/5 thresholds and triggering Meta conversion events without having genuine purchase intent. The band thresholds are too easy to reach through passive browsing.",
        "fix": (
            "Raise the band thresholds in the scoring model. "
            "Band3_Intent and above should require active engagement signals (OTP verified, affordability confirmed, visit form started) — not just page views or chatbot opens. "
            "Audit the score weights in analytics_db.scoring_config and increase the minimum score required for Band3 entry by 20-30%."
        ),
        "where": "analytics_db → scoring_config collection — band threshold values for Band3, Band4, Band5",
        "expected_outcome": "Meta event accuracy should improve from 0.4% toward the 20% target within 2 weeks of threshold adjustment",
    },
    "BAND_CONVERSION_BELOW_TARGET": {
        "root_cause": "Leads are being classified into high bands but not converting to site visits. The band thresholds are miscalibrated — leads reach Band4/5 without real purchase intent.",
        "fix": (
            "1. Raise Band3/4 entry thresholds so only leads with confirmed intent (OTP, affordability) qualify. "
            "2. Add a mandatory 'intent signal' requirement before a lead can enter Band4_Qualified — e.g. affordability_confirmed=YES or visit_form_started=true. "
            "3. Review the scoring_config weights — passive actions (page scroll, chatbot open) are likely over-weighted."
        ),
        "where": "analytics_db → scoring_config — band_thresholds and action_weights sections",
        "expected_outcome": "Band conversion rates should improve once only genuinely qualified leads reach Band4/5",
    },
    "OVERALL_OUTCOME_BELOW_TARGET": {
        "root_cause": "The overall conversion rate for this outcome is below the configured target. Either the target is too aggressive for current pipeline quality, or the scoring model is promoting leads prematurely.",
        "fix": (
            "Two options: "
            "1. Recalibrate targets in config/outcomes.json if the current targets were set without baseline data. "
            "2. If targets are correct, raise band thresholds in the scoring model so only genuinely qualified leads are counted. "
            "Check: is the funnel volume (total leads in Band4+) large enough? Low volume = high variance in rates."
        ),
        "where": "config/outcomes.json — targets.overall_pct AND analytics_db → scoring_config",
        "expected_outcome": "Conversion rate improves once scoring model only promotes genuine intent leads",
    },
    "MULTIPLIER_INEFFECTIVE": {
        "root_cause": "The M4_OTP_verified multiplier gives a score boost when a lead completes OTP verification, but leads who complete OTP are NOT converting to site visits at a higher rate. The score boost is not predicting real intent.",
        "fix": (
            "Reduce the M4_OTP_verified score multiplier weight by 50% in the scoring config. "
            "OTP completion may indicate bot engagement rather than purchase intent. "
            "Monitor M1_affordability_yes instead — it currently shows a positive correlation with visits (50% vs 39%) and should be weighted higher."
        ),
        "where": "analytics_db → scoring_config — multiplier_weights.M4_OTP_verified (reduce) and multiplier_weights.M1_affordability_yes (increase)",
        "expected_outcome": "Score distribution becomes more predictive of real intent. M4 changes take effect on next score recalculation cycle.",
    },
    "CALIBRATION_NOT_BOT_PROBLEM": {
        "root_cause": "QA health scores are acceptable but conversion rates are below target. The bots are working correctly — the problem is the scoring model promoting low-intent leads to high bands.",
        "fix": (
            "Do NOT change chatbot or voice agent prompts — they are performing correctly. "
            "Focus entirely on the scoring model: "
            "1. Raise Band4/5 entry thresholds in analytics_db.scoring_config. "
            "2. Add hard requirements: Band4_Qualified must have affordability_confirmed=YES. "
            "3. Reduce weight of passive signals (scroll depth, page time) in the scoring formula."
        ),
        "where": "analytics_db → scoring_config — band_thresholds and action_weights",
        "expected_outcome": "Conversion rates improve as fewer low-intent leads reach high bands and trigger Meta events",
    },
    "SCORING_MODEL_MISCALIBRATED": {
        "root_cause": "Band conversion rates are below target AND at least one multiplier is not improving conversion rates. The scoring model is over-rewarding passive browsing activity in both the band thresholds and the multiplier weights.",
        "fix": (
            "Full scoring model recalibration needed — two parts: "
            "1. THRESHOLDS: Raise Band3 and Band4 entry scores in analytics_db.scoring_config. "
            "Require at least one active intent signal (affordability_confirmed, visit_form_started, OTP) for Band4 entry. "
            "2. MULTIPLIER WEIGHTS: Disable or halve M4_OTP_verified boost. "
            "Increase M1_affordability_yes weight since it correlates with actual visits. "
            "Run a backtest on historical data before deploying."
        ),
        "where": "analytics_db → scoring_config — band_thresholds AND multiplier_weights",
        "expected_outcome": "After recalibration, Meta event accuracy should improve from 0.4% toward 20% target within 2-4 weeks",
    },

    # ── High-level type fallbacks (used when LLM generates freeform titles) ──
    "CALIBRATION": {
        "root_cause": "Lead scoring model is miscalibrated — leads are reaching high bands or triggering Meta events without genuine purchase intent.",
        "fix": (
            "Raise band entry thresholds in analytics_db.scoring_config. "
            "Band4_Qualified must require at least one active intent signal (affordability_confirmed=YES, OTP verified, or visit form started). "
            "Reduce weights for passive signals (page scroll, chatbot open). "
            "Review and adjust multiplier weights where the multiplier is not improving conversion rates."
        ),
        "where": "analytics_db → scoring_config — band_thresholds and action_weights",
        "expected_outcome": "Meta event accuracy and band conversion rates improve within 2 weeks of threshold adjustment",
    },
    "PROCESS_GAP": {
        "root_cause": "AI-qualified leads (affordability confirmed, high band score) are not being followed up by the sales team fast enough after the conversation ends.",
        "fix": (
            "Set up an automated alert to the sales team within 30 minutes of a lead confirming affordability. "
            "Check CRM — leads with affordability_confirmed=YES should appear in a priority queue. "
            "Review the handoff flow between the AI and the human sales team: is the lead data being passed correctly?"
        ),
        "where": "CRM / sales ops process — lead notification and assignment workflow",
        "expected_outcome": "Drop-off between affordability confirmation and site visit booking should reduce within 1 week of faster follow-up",
    },
    "SYSTEMATIC_BUG": {
        "root_cause": "The same issue type is appearing in more than 50% of evaluated conversations or calls, indicating a systematic error in the bot's behaviour rather than isolated mistakes.",
        "fix": (
            "Identify the dominant issue type from the QA results. "
            "If LANGUAGE_HANDLING: strengthen the language-switch rule in the voice agent prompt. "
            "If DECIMAL_NUMBER: add explicit pronunciation rules to the voice system prompt. "
            "If KB_MISMATCH: audit and update the relevant KB file. "
            "Deploy the fix and re-evaluate a fresh batch to confirm the issue rate drops."
        ),
        "where": "knowledge_base/ — the relevant KB or prompt file for the dominant issue type",
        "expected_outcome": "Issue rate drops below 10% within one evaluation cycle after the fix is deployed",
    },
    "TREND": {
        "root_cause": "Health scores are declining over consecutive evaluation cycles, indicating a gradual degradation in bot performance or KB accuracy.",
        "fix": (
            "Compare the current KB and prompt files against the version from when scores were healthy. "
            "Check if any KB content was recently updated or if new conversation types are appearing. "
            "Run a targeted evaluation on the failing conversations to identify the common issue type."
        ),
        "where": "knowledge_base/ and agents/prompts/ — compare current vs previous versions",
        "expected_outcome": "Score stabilises and begins recovering within 2 cycles after root cause is identified and fixed",
    },
}


def get_known_fix(problem: dict) -> dict | None:
    """
    Return a templated fix if the problem maps to a known pattern.

    Matching order:
    1. Exact match on problem type (e.g. "OVERALL_OUTCOME_BELOW_TARGET")
    2. Exact match on title normalised to UPPER_SNAKE_CASE
       — handles titles produced by the deterministic fallback:
         "Overall Outcome Below Target" → "OVERALL_OUTCOME_BELOW_TARGET"
    3. Substring match on the raw UPPER title (catches titles that have
       the flag name embedded, e.g. "BAND_CONVERSION_BELOW_TARGET: Band3...")
    """
    ptype = problem.get("type", "").upper()
    title = problem.get("title", "").upper()
    title_snake = title.replace(" ", "_")   # "OVERALL OUTCOME..." → "OVERALL_OUTCOME..."

    # 1. Exact match on type
    if ptype in KNOWN_FIXES:
        return KNOWN_FIXES[ptype]

    # 2. Normalised title exact match (deterministic fallback titles)
    if title_snake in KNOWN_FIXES:
        return KNOWN_FIXES[title_snake]

    # 3. Substring match (LLM titles that embed the flag name)
    for key, fix_data in KNOWN_FIXES.items():
        if key in title or key in title_snake:
            return fix_data

    return None


# ════════════════════════════════════════════════════════════════════════════
# HISTORICAL BASELINE (used for CALIBRATION and TREND problems)
# ════════════════════════════════════════════════════════════════════════════

def get_baseline_context() -> str:
    """
    Pull health score history for all components and format it for the LLM.
    This lets the LLM say 'this was working on date X, broke around date Y'.
    """
    lines = []
    for component in ["chatbot", "voice", "analytics"]:
        history = get_health_history(component, days=30)
        if not history:
            lines.append(f"{component}: no history")
            continue
        scores = [(h["recorded_at"][:10], round(h["score"], 1)) for h in history]
        best   = max(scores, key=lambda x: x[1])
        worst  = min(scores, key=lambda x: x[1])
        latest = scores[-1]
        first  = scores[0]
        lines.append(
            f"{component}: first={first[1]} on {first[0]}, "
            f"best={best[1]} on {best[0]}, "
            f"worst={worst[1]} on {worst[0]}, "
            f"current={latest[1]} on {latest[0]}"
        )
    return "\n".join(lines)


# ════════════════════════════════════════════════════════════════════════════
# FIX GENERATION
# ════════════════════════════════════════════════════════════════════════════

def generate_fix_for_problem(problem: dict, baseline_context: str) -> dict:
    """
    Generate one specific fix for one problem.
    Uses a known template if available, otherwise asks the LLM.
    """
    # Try known fix first (faster, no LLM needed)
    known = get_known_fix(problem)
    if known:
        return {
            "problem_id":       problem["id"],
            "problem_title":    problem["title"],
            "urgency":          problem["urgency"],
            "root_cause":       problem["what_is_wrong"],
            "fix":              known["fix"],
            "where":            known["where"],
            "expected_outcome": known["expected_outcome"],
            "source":           "template",
        }

    # Otherwise ask the LLM
    agent_prompt  = load_agent_prompt()
    outcome_goals = load_outcome_goals()

    prompt = f"""{agent_prompt}

---

{outcome_goals}

---

## PROBLEM TO FIX

  ID               : {problem['id']}
  Title            : {problem['title']}
  Type             : {problem['type']}
  Components       : {', '.join(problem.get('components', []))}
  Description      : {problem['description']}
  Evidence         : {'; '.join(problem.get('evidence', []))}
  What is wrong    : {problem['what_is_wrong']}
  What is NOT wrong: {problem.get('what_is_not_wrong', '')}

## HISTORICAL BASELINE

{baseline_context}

---

The fix you produce must directly help achieve the business goals stated above.
If the fix will not meaningfully move any of those goals, say so explicitly in expected_outcome.
Produce the fix following all instructions above.
Return ONLY the JSON."""

    try:
        result = ask_json(prompt)
        return {
            "problem_id":       problem["id"],
            "problem_title":    problem["title"],
            "urgency":          problem["urgency"],
            "root_cause":       result.get("root_cause", ""),
            "fix":              result.get("fix", ""),
            "where":            result.get("where", ""),
            "expected_outcome": result.get("expected_outcome", ""),
            "source":           "llm",
        }
    except Exception as e:
        return {
            "problem_id":       problem["id"],
            "problem_title":    problem["title"],
            "urgency":          problem["urgency"],
            "root_cause":       problem["what_is_wrong"],
            "fix":              f"Could not generate fix: {e}",
            "where":            "unknown",
            "expected_outcome": "unknown",
            "source":           "error",
        }


# ════════════════════════════════════════════════════════════════════════════
# MAIN RUN
# ════════════════════════════════════════════════════════════════════════════

def run(problems: list = None):
    """
    problems: list of Problem objects from feedback.aggregate().
              If None, agent tries to re-run feedback to get them.
    """
    if problems is None:
        print("[Recommendation Agent] No problems passed — running feedback agent first...")
        from agents.feedback import aggregate
        problems = aggregate()

    if not problems:
        print("[Recommendation Agent] No problems to fix — system is healthy.")
        return []

    print(f"[Recommendation Agent] Generating fixes for {len(problems)} problem(s)...")

    baseline_context = get_baseline_context()

    # Sort: HIGH first, then MEDIUM, then LOW
    sorted_problems = sorted(
        problems,
        key=lambda p: {"HIGH": 0, "MEDIUM": 1, "LOW": 2}.get(p["urgency"], 3)
    )

    fixes = []
    for problem in sorted_problems:
        print(f"  → Fix for [{problem['id']}] {problem['title']}...")
        fix = generate_fix_for_problem(problem, baseline_context)
        fixes.append(fix)

    # ── Save to MongoDB ───────────────────────────────────────────────────────
    save_recommendation({
        "negative_signals": [p["title"] for p in problems],
        "root_cause":       fixes[0]["root_cause"] if fixes else "",
        "fixes": [
            {
                "rank":             i + 1,
                "problem_id":       f["problem_id"],
                "component":        ", ".join(
                    next((p["components"] for p in problems if p["id"] == f["problem_id"]), [])
                ),
                "problem":          f["problem_title"],
                "fix":              f["fix"],
                "expected_outcome": f["expected_outcome"],
            }
            for i, f in enumerate(fixes)
        ],
        "priority": sorted_problems[0]["urgency"] if sorted_problems else "LOW",
    })

    # ── Print fix report ──────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  FIXES ({len(fixes)} total)")
    print(f"{'='*60}")
    for fix in fixes:
        print(f"\n  [{fix['problem_id']}] [{fix['urgency']}] {fix['problem_title']}")
        print(f"  Root cause : {fix['root_cause']}")
        print(f"  Fix        : {fix['fix']}")
        print(f"  Where      : {fix['where']}")
        print(f"  Outcome    : {fix['expected_outcome']}")
    print(f"\n{'='*60}")

    # ── Alert if HIGH fixes exist ─────────────────────────────────────────────
    high_fixes = [f for f in fixes if f["urgency"] == "HIGH"]
    if high_fixes:
        notify(
            agent_name="Recommendation Agent",
            status=f"{len(high_fixes)} HIGH PRIORITY FIX(ES) NEEDED",
            details={
                "top_problem": high_fixes[0]["problem_title"],
                "top_fix":     high_fixes[0]["fix"],
                "total_fixes": len(fixes),
            }
        )

    print(f"\n[Recommendation Agent] Done.")
    return fixes


if __name__ == "__main__":
    run()
