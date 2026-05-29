"""
ABM Benchmark Runner

Runs all synthetic test cases through the real QA agents (chatbot_qa and voice_qa)
and measures their accuracy against the known ground truth.

Metrics per issue type:
  - True Positive (TP):  agent flagged an issue that WAS injected
  - False Negative (FN): agent MISSED an issue that was injected
  - False Positive (FP): agent flagged an issue that was NOT injected (hallucinated)

Overall accuracy:
  precision = TP / (TP + FP)   — of what the agent flags, how much is real?
  recall    = TP / (TP + FN)   — of what was injected, how much did it catch?
  f1        = 2 * (P * R) / (P + R)

Target: f1 > 0.90 before going to production.

Usage:
  # Generate test cases first (only needed once):
  python3 simulation/generate_test_cases.py

  # Run benchmark:
  python3 simulation/run_benchmark.py

  # Run only chatbot:
  python3 simulation/run_benchmark.py --chatbot

  # Run only voice:
  python3 simulation/run_benchmark.py --voice
"""

import os
import sys
import json
import argparse
from datetime import datetime

# Resolve project root so we can import agents
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

from agents.chatbot_qa import score_conversation, load_knowledge_base, load_agent_prompt
from agents.voice_qa   import score_call,         load_knowledge_base as load_voice_kb, load_agent_prompt as load_voice_prompt

SIMULATION_DIR = os.path.dirname(os.path.abspath(__file__))
CB_CASES_FILE  = os.path.join(SIMULATION_DIR, "test_cases_chatbot.json")
VC_CASES_FILE  = os.path.join(SIMULATION_DIR, "test_cases_voice.json")
RESULTS_FILE   = os.path.join(SIMULATION_DIR, "benchmark_results.json")


# ════════════════════════════════════════════════════════════════════════════
# SCORING HELPERS
# ════════════════════════════════════════════════════════════════════════════

def match_issue(found_issues: list, expected_type: str) -> bool:
    """Return True if any found issue matches the expected type."""
    return any(i.get("type") == expected_type for i in found_issues)


def score_result(test_case: dict, agent_result: dict) -> dict:
    """
    Compare agent output against ground truth.
    Returns a dict with TP, FP, FN counts and a list of mismatches.
    """
    ground_truth     = test_case["ground_truth"]
    expected_issues  = ground_truth.get("issues", [])
    found_issues     = agent_result.get("issues", [])
    expected_status  = ground_truth.get("status", "PASS")
    actual_status    = agent_result.get("status", "PASS")

    tp = 0
    fn = 0
    fp = 0
    mismatches = []

    # Status match
    status_correct = (expected_status == actual_status)
    if not status_correct:
        mismatches.append(
            f"Status mismatch: expected {expected_status}, got {actual_status}"
        )

    # Check each expected issue — did the agent find it?
    for exp in expected_issues:
        if match_issue(found_issues, exp["type"]):
            tp += 1
        else:
            fn += 1
            mismatches.append(f"MISSED: expected {exp['type']} ({exp.get('severity','?')})")

    # Check each found issue — was it expected?
    expected_types = {e["type"] for e in expected_issues}
    for found in found_issues:
        if found.get("type") not in expected_types:
            fp += 1
            mismatches.append(
                f"FALSE POSITIVE: flagged {found.get('type')} ({found.get('severity','?')}) — not in ground truth"
            )

    return {
        "case_id":        test_case["id"],
        "label":          test_case["label"],
        "description":    test_case["description"],
        "status_correct": status_correct,
        "tp":             tp,
        "fn":             fn,
        "fp":             fp,
        "mismatches":     mismatches,
        "agent_score":    agent_result.get("score"),
        "agent_status":   actual_status,
        "expected_status": expected_status,
        "found_issues":   [{"type": i.get("type"), "severity": i.get("severity")} for i in found_issues],
    }


def compute_metrics(case_scores: list) -> dict:
    total_tp = sum(s["tp"] for s in case_scores)
    total_fn = sum(s["fn"] for s in case_scores)
    total_fp = sum(s["fp"] for s in case_scores)

    precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 1.0
    recall    = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 1.0
    f1        = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    status_correct = sum(1 for s in case_scores if s["status_correct"])

    return {
        "total_cases":     len(case_scores),
        "status_accuracy": round(status_correct / len(case_scores), 3) if case_scores else 0,
        "tp": total_tp,
        "fn": total_fn,
        "fp": total_fp,
        "precision": round(precision, 3),
        "recall":    round(recall, 3),
        "f1":        round(f1, 3),
    }


# ════════════════════════════════════════════════════════════════════════════
# CHATBOT BENCHMARK
# ════════════════════════════════════════════════════════════════════════════

def run_chatbot_benchmark() -> dict:
    print("\n[Benchmark] Loading chatbot test cases...")
    with open(CB_CASES_FILE, "r") as f:
        test_cases = json.load(f)

    kb           = load_knowledge_base()
    agent_prompt = load_agent_prompt()

    case_scores = []
    print(f"[Benchmark] Running {len(test_cases)} chatbot cases...\n")

    for tc in test_cases:
        print(f"  [{tc['id']}] {tc['description'][:60]}...")

        # Build the conversation dict the agent expects
        conversation = {
            "conversationId":   tc["id"],
            "conversationDepth": tc["conversation"],
            "turnCount":        len(tc["conversation"]),
        }

        try:
            result = score_conversation(conversation, kb, agent_prompt, client=None)
        except Exception as e:
            print(f"    ERROR: {e}")
            result = {"status": "ERROR", "issues": [], "score": 0}

        scored = score_result(tc, result)
        case_scores.append(scored)

        icon = "✓" if scored["status_correct"] and not scored["mismatches"] else "✗"
        print(f"    {icon} Expected {tc['label']} → Got {result.get('status','?')} | "
              f"TP={scored['tp']} FN={scored['fn']} FP={scored['fp']}")
        for m in scored["mismatches"]:
            print(f"      ⚠  {m}")

    metrics = compute_metrics(case_scores)
    return {"agent": "chatbot", "metrics": metrics, "cases": case_scores}


# ════════════════════════════════════════════════════════════════════════════
# VOICE BENCHMARK
# ════════════════════════════════════════════════════════════════════════════

def run_voice_benchmark() -> dict:
    print("\n[Benchmark] Loading voice test cases...")
    with open(VC_CASES_FILE, "r") as f:
        test_cases = json.load(f)

    kb           = load_voice_kb()
    agent_prompt = load_voice_prompt()

    case_scores = []
    print(f"[Benchmark] Running {len(test_cases)} voice cases...\n")

    for tc in test_cases:
        print(f"  [{tc['id']}] {tc['description'][:60]}...")

        call = {
            "call_sid":        tc["id"],
            "transcript":      tc["transcript"],
            "call_direction":  tc["call_metadata"].get("call_direction", "inbound"),
            "language_used":   tc["call_metadata"].get("language_used", "English"),
            "project":         tc["call_metadata"].get("project", "Loft"),
        }

        try:
            result = score_call(call, kb, agent_prompt)
        except Exception as e:
            print(f"    ERROR: {e}")
            result = {"status": "ERROR", "issues": [], "score": 0}

        scored = score_result(tc, result)

        # Also check language_compliance if present in ground truth
        if "language_compliance" in tc["ground_truth"]:
            expected_lc = tc["ground_truth"]["language_compliance"]
            actual_lc   = result.get("language_compliance", "PASS")
            if expected_lc != actual_lc:
                scored["mismatches"].append(
                    f"Language compliance mismatch: expected {expected_lc}, got {actual_lc}"
                )
                scored["status_correct"] = False

        case_scores.append(scored)

        icon = "✓" if scored["status_correct"] and not scored["mismatches"] else "✗"
        print(f"    {icon} Expected {tc['label']} → Got {result.get('status','?')} | "
              f"TP={scored['tp']} FN={scored['fn']} FP={scored['fp']}")
        for m in scored["mismatches"]:
            print(f"      ⚠  {m}")

    metrics = compute_metrics(case_scores)
    return {"agent": "voice", "metrics": metrics, "cases": case_scores}


# ════════════════════════════════════════════════════════════════════════════
# REPORT
# ════════════════════════════════════════════════════════════════════════════

def print_report(results: list):
    print(f"\n{'═'*60}")
    print("  BENCHMARK REPORT")
    print(f"{'═'*60}")
    print(f"  Run at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    all_pass = True
    for r in results:
        m     = r["metrics"]
        agent = r["agent"].upper()
        f1    = m["f1"]
        target_met = f1 >= 0.90

        status = "✓ PASS" if target_met else "✗ NEEDS WORK"
        if not target_met:
            all_pass = False

        print(f"  [{agent}] {status}")
        print(f"    Cases   : {m['total_cases']} total")
        print(f"    Status  : {m['status_accuracy']*100:.0f}% correct (PASS/FAIL classification)")
        print(f"    TP/FN/FP: {m['tp']} / {m['fn']} / {m['fp']}")
        print(f"    Precision: {m['precision']*100:.0f}%  Recall: {m['recall']*100:.0f}%  F1: {f1*100:.0f}%")
        print(f"    Target  : F1 ≥ 90% — {'MET ✓' if target_met else 'NOT MET ✗'}\n")

        # Show failures
        failures = [c for c in r["cases"] if c["mismatches"]]
        if failures:
            print(f"    Failed cases ({len(failures)}):")
            for c in failures:
                print(f"      [{c['case_id']}] {c['description'][:50]}")
                for m_text in c["mismatches"][:2]:
                    print(f"        → {m_text}")
            print()

    print(f"{'─'*60}")
    print(f"  Overall: {'ALL AGENTS READY FOR PRODUCTION ✓' if all_pass else 'FIX ISSUES BEFORE PRODUCTION ✗'}")
    print(f"{'═'*60}\n")


# ════════════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Run QA agent benchmark")
    parser.add_argument("--chatbot", action="store_true", help="Run chatbot benchmark only")
    parser.add_argument("--voice",   action="store_true", help="Run voice benchmark only")
    args = parser.parse_args()

    # Ensure test cases exist
    if not os.path.exists(CB_CASES_FILE) or not os.path.exists(VC_CASES_FILE):
        print("[Benchmark] Test cases not found. Generating them first...")
        sys.path.insert(0, SIMULATION_DIR)
        from generate_test_cases import main as gen_main
        gen_main()

    results = []
    run_both = not args.chatbot and not args.voice

    if args.chatbot or run_both:
        results.append(run_chatbot_benchmark())

    if args.voice or run_both:
        results.append(run_voice_benchmark())

    print_report(results)

    # Save results to JSON
    output = {
        "run_at":  datetime.now().isoformat(),
        "results": results,
    }
    with open(RESULTS_FILE, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"[Benchmark] Results saved to {RESULTS_FILE}")


if __name__ == "__main__":
    main()
