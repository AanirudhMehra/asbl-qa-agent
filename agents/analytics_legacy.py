import os
import sys
import json
from datetime import datetime

import pymongo
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import save_analytics_run
from notifier import notify

MONGO_URI = os.getenv("MONGO_URI_PROD")  # read-only from prod

BANDS = ["Band1_Spark", "Band2_Engaged", "Band3_Intent", "Band4_Qualified", "Band5_Hot"]
MULTIPLIERS = ["M1_affordability_yes", "M2_aff_no_bounce_30s", "M3_address_typed", "M4_OTP_verified"]

OUTCOMES_CONFIG = os.path.join(os.path.dirname(__file__), '..', 'config', 'outcomes.json')

# Internal field map — user never touches this.
# The outcomes.json only has plain-English goals and target percentages.
# This dict maps the outcome name → (field_path, expected_value_or_None)
OUTCOME_FIELD_MAP = {
    "site_visit_booked":      ("milestones.has_visit_booked",       None),
    "otp_verified":           ("milestones.has_otp_verified",        None),
    "affordability_confirmed": ("milestones.affordability_outcome", "YES"),
}


def load_outcomes() -> list:
    with open(OUTCOMES_CONFIG, "r") as f:
        cfg = json.load(f)
    return [o for o in cfg.get("outcomes", []) if o.get("active", True)]


def get_outcome_value(doc: dict, outcome_name: str) -> bool:
    """
    Check whether a lead document satisfies a given outcome.
    Uses the internal OUTCOME_FIELD_MAP — not the config file.
    """
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


def get_db():
    client = pymongo.MongoClient(MONGO_URI)
    return client["analytics_db"]


def check_band_conversion_rates(db) -> tuple:
    """
    For every active outcome in config/outcomes.json, compute per-band conversion rates
    and flag bands whose rates fall below the targets defined in plain-English config.
    """
    outcomes = load_outcomes()
    scores   = list(db["scores_overall"].find())

    outcome_data = {
        o["name"]: {b: {"total": 0, "converted": 0} for b in BANDS}
        for o in outcomes
    }

    for doc in scores:
        highest_band = doc.get("lifetime", {}).get("highest_band_ever")
        if highest_band not in BANDS:
            continue
        for outcome in outcomes:
            outcome_data[outcome["name"]][highest_band]["total"] += 1
            if get_outcome_value(doc, outcome["name"]):
                outcome_data[outcome["name"]][highest_band]["converted"] += 1

    result = {}
    flags  = []

    for outcome in outcomes:
        oname      = outcome["name"]
        olabel     = outcome["label"]
        ogoal      = outcome.get("goal", "")   # plain-English goal from outcomes.json
        overall_target = outcome.get("targets", {}).get("overall_pct", 0) / 100.0
        by_band    = {b: pct / 100.0
                      for b, pct in outcome.get("targets", {}).get("by_band_pct", {}).items()}

        result[oname] = {
            "_goal":           ogoal,
            "_overall_target": round(overall_target * 100),
        }

        # Compute overall rate across all bands
        total_all     = sum(outcome_data[oname][b]["total"]     for b in BANDS)
        converted_all = sum(outcome_data[oname][b]["converted"] for b in BANDS)
        overall_rate  = round(converted_all / total_all, 3) if total_all > 0 else 0.0
        result[oname]["_overall_rate"] = round(overall_rate * 100, 1)

        # Flag if overall rate is below overall target
        if overall_target > 0 and overall_rate < overall_target and total_all >= 3:
            flags.append({
                "type":     "OVERALL_OUTCOME_BELOW_TARGET",
                "outcome":  olabel,
                "goal":     ogoal,
                "severity": "HIGH",
                "detail": (
                    f"[{olabel}] Overall rate {overall_rate*100:.1f}% is below your target "
                    f"of {overall_target*100:.0f}%. "
                    f"Your goal: \"{ogoal}\""
                )
            })

        for band in BANDS:
            data      = outcome_data[oname][band]
            total     = data["total"]
            converted = data["converted"]
            rate      = round(converted / total, 3) if total > 0 else 0.0
            threshold = by_band.get(band, 0.0)

            meta_events = db["meta_conversion_events"].count_documents({"band.name": band})

            result[oname][band] = {
                "total_leads":       total,
                "converted":         converted,
                "rate":              rate,
                "target_pct":        round(threshold * 100),
                "meta_events_fired": meta_events,
                "flag":              False
            }

            if meta_events > 0 and threshold > 0 and rate < threshold and total >= 3:
                result[oname][band]["flag"] = True
                flags.append({
                    "type":     "BAND_OUTCOME_MISMATCH",
                    "outcome":  olabel,
                    "goal":     ogoal,
                    "severity": "HIGH",
                    "detail": (
                        f"[{olabel}] {band} firing {meta_events} Meta events "
                        f"but conversion rate is {rate*100:.1f}% "
                        f"(your target: {threshold*100:.0f}%). "
                        f"Your goal: \"{ogoal}\""
                    )
                })

    return result, flags


def check_multiplier_effectiveness(db) -> tuple:
    scores           = list(db["scores_overall"].find())
    multiplier_data  = {
        m: {"with": {"total": 0, "visits": 0}, "without": {"total": 0, "visits": 0}}
        for m in MULTIPLIERS
    }

    for doc in scores:
        lead_id              = str(doc.get("lead_id", ""))
        completed_multipliers = []
        if lead_id:
            events = db["multiplier_completion_events"].find({"lead_id": lead_id})
            completed_multipliers = [e.get("pattern_name") for e in events]

        visit_booked = doc.get("milestones", {}).get("has_visit_booked", False)

        for m in MULTIPLIERS:
            m_short = m.split("_")[0]   # M1, M2, M3, M4
            if m_short in completed_multipliers:
                multiplier_data[m]["with"]["total"] += 1
                if visit_booked:
                    multiplier_data[m]["with"]["visits"] += 1
            else:
                multiplier_data[m]["without"]["total"] += 1
                if visit_booked:
                    multiplier_data[m]["without"]["visits"] += 1

    result = {}
    flags  = []

    for m, data in multiplier_data.items():
        with_total    = data["with"]["total"]
        without_total = data["without"]["total"]
        with_rate     = round(data["with"]["visits"]    / with_total,    3) if with_total    > 0 else 0
        without_rate  = round(data["without"]["visits"] / without_total, 3) if without_total > 0 else 0
        effective     = with_rate > without_rate

        result[m] = {
            "with_multiplier_visit_rate":    with_rate,
            "without_multiplier_visit_rate": without_rate,
            "effective":   effective,
            "sample_size": with_total
        }

        if not effective and with_total >= 5:
            flags.append({
                "type":     "MULTIPLIER_INEFFECTIVE",
                "severity": "MEDIUM",
                "detail": (
                    f"{m} is not improving visit rates — "
                    f"with: {with_rate*100:.0f}%, without: {without_rate*100:.0f}%"
                )
            })

    return result, flags


def check_meta_signal_accuracy(db) -> tuple:
    meta_events   = list(db["meta_conversion_events"].find())
    total_events  = len(meta_events)
    led_to_visit  = 0
    wasted        = 0

    for event in meta_events:
        lead_id    = event.get("lead_id")
        session_id = event.get("session_id")

        query = {}
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
            else:
                wasted += 1
        else:
            wasted += 1

    accuracy = round(led_to_visit / total_events, 3) if total_events > 0 else 0

    flags = []
    if accuracy < 0.20 and total_events >= 10:
        flags.append({
            "type":     "META_SIGNAL_LOW_ACCURACY",
            "severity": "HIGH",
            "detail": (
                f"Only {accuracy*100:.1f}% of Meta conversion events led to site visits "
                f"({led_to_visit}/{total_events})"
            )
        })

    return {
        "total_events_fired":  total_events,
        "events_led_to_visit": led_to_visit,
        "wasted_signal_count": wasted,
        "accuracy_rate":       accuracy
    }, flags


def check_funnel_gaps(db) -> list:
    gaps = []

    leads_no_session = db["scores_overall"].count_documents({"lifetime.total_sessions": 0})
    if leads_no_session > 0:
        gaps.append({
            "gap":      "leads_with_no_session",
            "count":    leads_no_session,
            "severity": "LOW",
            "detail":   f"{leads_no_session} leads have 0 sessions recorded"
        })

    aff_yes_no_visit = db["scores_overall"].count_documents({
        "milestones.affordability_outcome": "YES",
        "milestones.has_visit_booked":      False
    })
    if aff_yes_no_visit > 3:
        gaps.append({
            "gap":      "affordability_yes_no_visit",
            "count":    aff_yes_no_visit,
            "severity": "MEDIUM",
            "detail":   f"{aff_yes_no_visit} leads confirmed affordability but never booked — follow-up gap"
        })

    return gaps


def run():
    print("[Analytics Agent] Connecting to MongoDB...")
    mongo_client = pymongo.MongoClient(MONGO_URI)
    db           = mongo_client["analytics_db"]
    print("[Analytics Agent] Running checks...")

    all_flags = []

    band_rates,    band_flags = check_band_conversion_rates(db)
    all_flags.extend(band_flags)

    multiplier_eff, mult_flags = check_multiplier_effectiveness(db)
    all_flags.extend(mult_flags)

    meta_accuracy, meta_flags = check_meta_signal_accuracy(db)
    all_flags.extend(meta_flags)

    funnel_gaps = check_funnel_gaps(db)
    all_flags.extend(g for g in funnel_gaps if g.get("severity") == "HIGH")

    outcomes = load_outcomes()
    result = {
        "run_at":                 datetime.now().isoformat(),
        "outcomes_checked":       [o["name"] for o in outcomes],
        "outcome_goals":          {o["name"]: o.get("goal", "") for o in outcomes},
        "band_conversion_rates":  band_rates,
        "multiplier_effectiveness": multiplier_eff,
        "meta_signal_accuracy":   meta_accuracy,
        "funnel_gaps":            funnel_gaps,
        "flags":                  all_flags
    }

    save_analytics_run(result)

    high_flags = [f for f in all_flags if f.get("severity") == "HIGH"]
    if high_flags:
        notify("Analytics Agent", "FLAGS FOUND", {
            "high_severity": len(high_flags),
            "total_flags":   len(all_flags),
            "top_issue":     high_flags[0]["detail"]
        })
    else:
        print(f"[Analytics Agent] Clean run. {len(all_flags)} low/medium flags.")

    print(f"[Analytics Agent] Done. {len(all_flags)} total flags.")
    return result


if __name__ == "__main__":
    run()
