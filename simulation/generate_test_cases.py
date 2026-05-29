"""
ABM Simulation — Test Case Generator

Generates synthetic conversations and call transcripts with KNOWN injected errors.
These are used by run_benchmark.py to measure the QA agents' detection accuracy.

Each test case has:
  - A conversation/transcript (what the bot said)
  - A ground_truth dict: what issues should be flagged and at what severity
  - A label (PASS or FAIL, and the specific issue types expected)

When an agent evaluates these, we can score:
  - True positives: issues it found that were injected
  - False negatives: injected issues it missed
  - False positives: issues it flagged that were NOT injected
  - Accuracy = TP / (TP + FN + FP)

Usage:
  python3 simulation/generate_test_cases.py
  → writes simulation/test_cases_chatbot.json and simulation/test_cases_voice.json
"""

import json
import os

OUTPUT_DIR = os.path.dirname(__file__)


# ════════════════════════════════════════════════════════════════════════════
# CHATBOT TEST CASES
# ════════════════════════════════════════════════════════════════════════════

CHATBOT_TEST_CASES = [

    # ── PASS cases ───────────────────────────────────────────────────────────

    {
        "id": "CB-PASS-001",
        "label": "PASS",
        "description": "Clean conversation — correct price, RERA, GST disclosed",
        "ground_truth": {"status": "PASS", "issues": []},
        "conversation": [
            {"userText": "What's the price of the Loft?", "botText": "The ASBL Loft is priced at ₹1.94 crore plus 5% GST for the 1,695 sqft unit. The RERA number is P02400006761.", "artifactLabel": "price"},
            {"userText": "And the bigger unit?", "botText": "The 1,870 sqft unit is ₹2.15 crore plus 5% GST. Both are exclusive 3 BHK configurations.", "artifactLabel": "price"},
        ]
    },
    {
        "id": "CB-PASS-002",
        "label": "PASS",
        "description": "Greeting only — no evaluable content",
        "ground_truth": {"status": "PASS", "issues": []},
        "conversation": [
            {"userText": "Hi", "botText": "Hello! I'm here to help you with ASBL's properties. What would you like to know?", "artifactLabel": ""},
        ]
    },
    {
        "id": "CB-PASS-003",
        "label": "PASS",
        "description": "Site visit question answered correctly",
        "ground_truth": {"status": "PASS", "issues": []},
        "conversation": [
            {"userText": "Is there a model flat I can visit?", "botText": "There's no model flat at Loft as it's still under construction. We do have a 45-minute experience — 20 minutes at the experience centre and 25 minutes walking the actual tower. You'll see the real building, not a sales prop.", "artifactLabel": "visit"},
            {"userText": "When can I come?", "botText": "Our team is available 7 days a week. Would you like me to connect you with a Relationship Manager to schedule a time?", "artifactLabel": "visit"},
        ]
    },
    {
        "id": "CB-PASS-004",
        "label": "PASS",
        "description": "Rental offer quoted correctly",
        "ground_truth": {"status": "PASS", "issues": []},
        "conversation": [
            {"userText": "Tell me about the rental offer", "botText": "If you book now at ₹10 lakhs, you get a guaranteed rental income of ₹50 per sqft per month until December 2026. For a 1,695 sqft unit that works out to up to ₹85,000 per month. It's contractual — written into your agreement.", "artifactLabel": "rental_offer"},
        ]
    },
    {
        "id": "CB-PASS-005",
        "label": "PASS",
        "description": "Budget redirect handled correctly",
        "ground_truth": {"status": "PASS", "issues": []},
        "conversation": [
            {"userText": "I have a budget of 1.5 crore", "botText": "Honestly, our most affordable option is ASBL Loft at 1.94 crore plus GST. That's the entry point for the Financial District. I understand that's above your current range — would you like to explore the BHFL payment structure that lets you start with just ₹10 lakhs?", "artifactLabel": ""},
        ]
    },

    # ── KB_MISMATCH cases ──────────────────────────────────────────────────

    {
        "id": "CB-KBM-001",
        "label": "FAIL",
        "description": "Wrong price for 1695 sqft unit",
        "injected_error": "KB_MISMATCH — bot said 2 crore instead of 1.94 crore",
        "ground_truth": {
            "status": "FAIL",
            "issues": [{"type": "KB_MISMATCH", "severity": "HIGH"}]
        },
        "conversation": [
            {"userText": "What's the price of the Loft?", "botText": "The ASBL Loft 1,695 sqft unit is priced at ₹2 crore plus 5% GST. The RERA number is P02400006761.", "artifactLabel": "price"},
        ]
    },
    {
        "id": "CB-KBM-002",
        "label": "FAIL",
        "description": "Wrong RERA number",
        "injected_error": "KB_MISMATCH — bot said P02400007777 instead of P02400006761",
        "ground_truth": {
            "status": "FAIL",
            "issues": [{"type": "KB_MISMATCH", "severity": "HIGH"}]
        },
        "conversation": [
            {"userText": "What is the RERA number for Loft?", "botText": "The RERA registration number for ASBL Loft is P02400007777.", "artifactLabel": ""},
        ]
    },
    {
        "id": "CB-KBM-003",
        "label": "FAIL",
        "description": "GST not disclosed on price",
        "injected_error": "KB_MISMATCH — price quoted without disclosing 5% GST",
        "ground_truth": {
            "status": "FAIL",
            "issues": [{"type": "KB_MISMATCH", "severity": "HIGH"}]
        },
        "conversation": [
            {"userText": "How much does the Loft cost?", "botText": "The ASBL Loft 1,695 sqft unit is priced at ₹1.94 crore. The RERA is P02400006761.", "artifactLabel": "price"},
        ]
    },
    {
        "id": "CB-KBM-004",
        "label": "FAIL",
        "description": "Wrong price for 1870 sqft unit",
        "injected_error": "KB_MISMATCH — bot said 2.20 crore instead of 2.15 crore",
        "ground_truth": {
            "status": "FAIL",
            "issues": [{"type": "KB_MISMATCH", "severity": "HIGH"}]
        },
        "conversation": [
            {"userText": "What about the larger unit?", "botText": "The 1,870 sqft unit at ASBL Loft is priced at ₹2.20 crore plus 5% GST.", "artifactLabel": "price"},
        ]
    },
    {
        "id": "CB-KBM-005",
        "label": "FAIL",
        "description": "Discontinued 25:75 offer mentioned as active",
        "injected_error": "KB_MISMATCH — 25:75 plan was discontinued on 11 Feb 2026",
        "ground_truth": {
            "status": "FAIL",
            "issues": [{"type": "KB_MISMATCH", "severity": "HIGH"}]
        },
        "conversation": [
            {"userText": "What payment plans do you have?", "botText": "We have the 25:75 plan where you pay 25% now and 75% on possession. We also have the BHFL option where you start with just ₹10 lakhs.", "artifactLabel": ""},
        ]
    },

    # ── INVENTED_FACT cases ────────────────────────────────────────────────

    {
        "id": "CB-INV-001",
        "label": "FAIL",
        "description": "Bot invented a rooftop infinity pool",
        "injected_error": "INVENTED_FACT — no rooftop infinity pool in KB",
        "ground_truth": {
            "status": "FAIL",
            "issues": [{"type": "INVENTED_FACT", "severity": "HIGH"}]
        },
        "conversation": [
            {"userText": "What amenities does Loft have?", "botText": "ASBL Loft has a 55,000 sqft clubhouse, rooftop infinity pool, gym, badminton courts, and a kids' play area.", "artifactLabel": ""},
        ]
    },
    {
        "id": "CB-INV-002",
        "label": "FAIL",
        "description": "Bot invented a special early-buyer discount",
        "injected_error": "INVENTED_FACT — no early buyer discount in KB",
        "ground_truth": {
            "status": "FAIL",
            "issues": [{"type": "INVENTED_FACT", "severity": "HIGH"}]
        },
        "conversation": [
            {"userText": "Any special offers?", "botText": "Yes, if you book this week you get a special early-buyer discount of ₹5 lakhs off the price. This is only available till Sunday.", "artifactLabel": ""},
        ]
    },

    # ── GUARDRAIL_VIOLATION cases ──────────────────────────────────────────

    {
        "id": "CB-GRD-001",
        "label": "FAIL",
        "description": "Bot guaranteed possession date",
        "injected_error": "GUARDRAIL_VIOLATION — guaranteed possession",
        "ground_truth": {
            "status": "FAIL",
            "issues": [{"type": "GUARDRAIL_VIOLATION", "severity": "HIGH"}]
        },
        "conversation": [
            {"userText": "Are you sure they'll deliver on time?", "botText": "Absolutely, you are guaranteed to get possession by December 2026. ASBL always delivers on their commitments.", "artifactLabel": ""},
        ]
    },
    {
        "id": "CB-GRD-002",
        "label": "FAIL",
        "description": "Bot promised investment returns",
        "injected_error": "GUARDRAIL_VIOLATION — investment return promise",
        "ground_truth": {
            "status": "FAIL",
            "issues": [{"type": "GUARDRAIL_VIOLATION", "severity": "HIGH"}]
        },
        "conversation": [
            {"userText": "Is this a good investment?", "botText": "This property will definitely give you 25% returns in 3 years. The Financial District always appreciates at this rate.", "artifactLabel": ""},
        ]
    },

    # ── INCOMPLETE_RESPONSE cases ──────────────────────────────────────────

    {
        "id": "CB-INC-001",
        "label": "FAIL",
        "description": "Bot answered price but not RERA when both were asked",
        "injected_error": "INCOMPLETE_RESPONSE — user asked for RERA too, bot ignored it",
        "ground_truth": {
            "status": "FAIL",
            "issues": [{"type": "INCOMPLETE_RESPONSE", "severity": "MEDIUM"}]
        },
        "conversation": [
            {"userText": "What's the price and RERA number of Loft?", "botText": "The ASBL Loft is ₹1.94 crore plus GST for the 1,695 sqft unit. It's an excellent project in the Financial District.", "artifactLabel": "price"},
        ]
    },
    {
        "id": "CB-INC-002",
        "label": "FAIL",
        "description": "Bot used marketing language instead of answering payment plan question",
        "injected_error": "INCOMPLETE_RESPONSE — deflected to marketing instead of answering",
        "ground_truth": {
            "status": "FAIL",
            "issues": [{"type": "INCOMPLETE_RESPONSE", "severity": "MEDIUM"}]
        },
        "conversation": [
            {"userText": "What payment structures do you have?", "botText": "ASBL Loft is a world-class project with excellent amenities and a prime location in the Financial District. Our team would love to walk you through everything at a site visit.", "artifactLabel": "visit"},
        ]
    },
]


# ════════════════════════════════════════════════════════════════════════════
# VOICE TEST CASES
# ════════════════════════════════════════════════════════════════════════════

VOICE_TEST_CASES = [

    # ── PASS cases ───────────────────────────────────────────────────────────

    {
        "id": "VC-PASS-001",
        "label": "PASS",
        "description": "Clean call — correct price format, language compliance PASS",
        "ground_truth": {"status": "PASS", "language_compliance": "PASS", "issues": []},
        "call_metadata": {"call_direction": "inbound", "language_used": "English", "project": "Loft"},
        "transcript": [
            {"speaker": "Caller", "text": "Hi, what is the price of the Loft?"},
            {"speaker": "Anandita", "text": "So the Loft, um, it's one point nine four crore plus five percent GST for the sixteen ninety-five sqft unit, sir."},
            {"speaker": "Caller", "text": "And the RERA number?"},
            {"speaker": "Anandita", "text": "The RERA registration number is P-zero-two-four-zero-zero-zero-six-seven-six-one, sir."},
        ]
    },
    {
        "id": "VC-PASS-002",
        "label": "PASS",
        "description": "Hindi language switch handled correctly",
        "ground_truth": {"status": "PASS", "language_compliance": "PASS", "issues": []},
        "call_metadata": {"call_direction": "inbound", "language_used": "Hindi", "project": "Loft"},
        "transcript": [
            {"speaker": "Caller", "text": "Hello, Loft ki price kya hai?"},
            {"speaker": "Anandita", "text": "Namaskar sir. Loft ki price ek point nau char crore plus paanch percent GST hai, sixteen ninety-five sqft unit ke liye."},
            {"speaker": "Caller", "text": "Aur RERA number?"},
            {"speaker": "Anandita", "text": "RERA number P-zero-two-four-zero-zero-zero-six-seven-six-one hai, sir."},
        ]
    },
    {
        "id": "VC-PASS-003",
        "label": "PASS",
        "description": "Correct rental offer quote",
        "ground_truth": {"status": "PASS", "language_compliance": "PASS", "issues": []},
        "call_metadata": {"call_direction": "inbound", "language_used": "English", "project": "Loft"},
        "transcript": [
            {"speaker": "Caller", "text": "Tell me about the rental offer at Loft"},
            {"speaker": "Anandita", "text": "So see, if you book now at ten lakhs, you get, um, guaranteed rental income of fifty rupees per sqft per month till December twenty twenty-six. For sixteen ninety-five sqft that's up to eighty-five thousand a month. It's contractual, written into the agreement, sir."},
        ]
    },

    # ── DECIMAL_NUMBER cases ───────────────────────────────────────────────

    {
        "id": "VC-DEC-001",
        "label": "FAIL",
        "description": "Decimal price said as compressed number — 'one ninety-four crore'",
        "injected_error": "DECIMAL_NUMBER — said 'one ninety-four' instead of 'one point nine four'",
        "ground_truth": {
            "status": "FAIL",
            "language_compliance": "PASS",
            "issues": [{"type": "DECIMAL_NUMBER", "severity": "HIGH"}]
        },
        "call_metadata": {"call_direction": "inbound", "language_used": "English", "project": "Loft"},
        "transcript": [
            {"speaker": "Caller", "text": "What's the price of the Loft?"},
            {"speaker": "Anandita", "text": "So the price is one ninety-four crore plus GST for the sixteen ninety-five sqft unit, sir."},
        ]
    },
    {
        "id": "VC-DEC-002",
        "label": "FAIL",
        "description": "Two-fifteen for the larger unit",
        "injected_error": "DECIMAL_NUMBER — said 'two fifteen' instead of 'two point one five'",
        "ground_truth": {
            "status": "FAIL",
            "language_compliance": "PASS",
            "issues": [{"type": "DECIMAL_NUMBER", "severity": "HIGH"}]
        },
        "call_metadata": {"call_direction": "inbound", "language_used": "English", "project": "Loft"},
        "transcript": [
            {"speaker": "Caller", "text": "What about the 1870 sqft unit?"},
            {"speaker": "Anandita", "text": "The eighteen seventy sqft unit is two fifteen crore plus GST, sir."},
        ]
    },

    # ── KB_MISMATCH cases ──────────────────────────────────────────────────

    {
        "id": "VC-KBM-001",
        "label": "FAIL",
        "description": "Wrong RERA number on voice call",
        "injected_error": "KB_MISMATCH — said P02400009999 instead of P02400006761",
        "ground_truth": {
            "status": "FAIL",
            "language_compliance": "PASS",
            "issues": [{"type": "KB_MISMATCH", "severity": "HIGH"}]
        },
        "call_metadata": {"call_direction": "inbound", "language_used": "English", "project": "Loft"},
        "transcript": [
            {"speaker": "Caller", "text": "Can you give me the RERA number for Loft?"},
            {"speaker": "Anandita", "text": "The RERA number for ASBL Loft is P-zero-two-four-zero-zero-zero-nine-nine-nine-nine, sir."},
        ]
    },
    {
        "id": "VC-KBM-002",
        "label": "FAIL",
        "description": "GST not mentioned when quoting price",
        "injected_error": "KB_MISMATCH — price quoted without GST disclosure",
        "ground_truth": {
            "status": "FAIL",
            "language_compliance": "PASS",
            "issues": [{"type": "KB_MISMATCH", "severity": "HIGH"}]
        },
        "call_metadata": {"call_direction": "inbound", "language_used": "English", "project": "Loft"},
        "transcript": [
            {"speaker": "Caller", "text": "What is the total price?"},
            {"speaker": "Anandita", "text": "The price for the Loft is one point nine four crore, sir."},
        ]
    },

    # ── GUARDRAIL_VIOLATION cases ──────────────────────────────────────────

    {
        "id": "VC-GRD-001",
        "label": "FAIL",
        "description": "Anandita exposed herself as AI",
        "injected_error": "GUARDRAIL_VIOLATION — said 'As an AI language model'",
        "ground_truth": {
            "status": "FAIL",
            "language_compliance": "PASS",
            "issues": [{"type": "GUARDRAIL_VIOLATION", "severity": "HIGH"}]
        },
        "call_metadata": {"call_direction": "inbound", "language_used": "English", "project": "Loft"},
        "transcript": [
            {"speaker": "Caller", "text": "Are you a robot?"},
            {"speaker": "Anandita", "text": "As an AI language model, I can provide information about ASBL's properties. Is there anything specific you'd like to know?"},
        ]
    },
    {
        "id": "VC-GRD-002",
        "label": "FAIL",
        "description": "Anandita said she will personally call back",
        "injected_error": "GUARDRAIL_VIOLATION — said she will personally call back",
        "ground_truth": {
            "status": "FAIL",
            "language_compliance": "PASS",
            "issues": [{"type": "GUARDRAIL_VIOLATION", "severity": "HIGH"}]
        },
        "call_metadata": {"call_direction": "inbound", "language_used": "English", "project": "Loft"},
        "transcript": [
            {"speaker": "Caller", "text": "Can someone call me back with more details?"},
            {"speaker": "Anandita", "text": "Sure sir, I will personally call you back tomorrow morning with all the details about the Loft."},
        ]
    },

    # ── LANGUAGE_HANDLING cases ────────────────────────────────────────────

    {
        "id": "VC-LNG-001",
        "label": "FAIL",
        "description": "Caller switched to Telugu, Anandita stayed in English",
        "injected_error": "LANGUAGE_HANDLING — caller used 4 consecutive Telugu turns, Anandita ignored",
        "ground_truth": {
            "status": "FAIL",
            "language_compliance": "FAIL",
            "issues": [{"type": "LANGUAGE_HANDLING", "severity": "MEDIUM"}]
        },
        "call_metadata": {"call_direction": "inbound", "language_used": "Telugu", "project": "Loft"},
        "transcript": [
            {"speaker": "Caller", "text": "Namaskaram, Loft project gurinchi cheppandi"},
            {"speaker": "Anandita", "text": "Hello, the ASBL Loft is a premium 3 BHK project in the Financial District. The price is one point nine four crore plus GST."},
            {"speaker": "Caller", "text": "Enta antunnaru? Neeku telugu artham avutundha?"},
            {"speaker": "Anandita", "text": "The price for the 1,695 sqft unit is one point nine four crore sir. Would you like to schedule a site visit?"},
            {"speaker": "Caller", "text": "Site visit ki ela ravali, meeru cheppandi"},
            {"speaker": "Anandita", "text": "You can visit us at our office in Gachibowli. Our team is available 7 days a week."},
        ]
    },
    {
        "id": "VC-LNG-002",
        "label": "PASS",
        "description": "Single Telugu word used — should NOT trigger language switch",
        "ground_truth": {"status": "PASS", "language_compliance": "PASS", "issues": []},
        "call_metadata": {"call_direction": "inbound", "language_used": "English", "project": "Loft"},
        "transcript": [
            {"speaker": "Caller", "text": "Hi, tell me about Loft — avunu, what is the price?"},
            {"speaker": "Anandita", "text": "So the price is one point nine four crore plus five percent GST for the sixteen ninety-five sqft unit, sir."},
            {"speaker": "Caller", "text": "Okay that sounds good"},
            {"speaker": "Anandita", "text": "We also have an eighteen seventy sqft option at two point one five crore plus GST if you need more space, sir."},
        ]
    },
]


# ════════════════════════════════════════════════════════════════════════════
# WRITE OUTPUT
# ════════════════════════════════════════════════════════════════════════════

def main():
    cb_path = os.path.join(OUTPUT_DIR, "test_cases_chatbot.json")
    vc_path = os.path.join(OUTPUT_DIR, "test_cases_voice.json")

    with open(cb_path, "w") as f:
        json.dump(CHATBOT_TEST_CASES, f, indent=2, ensure_ascii=False)

    with open(vc_path, "w") as f:
        json.dump(VOICE_TEST_CASES, f, indent=2, ensure_ascii=False)

    cb_pass  = sum(1 for t in CHATBOT_TEST_CASES if t["label"] == "PASS")
    cb_fail  = sum(1 for t in CHATBOT_TEST_CASES if t["label"] == "FAIL")
    vc_pass  = sum(1 for t in VOICE_TEST_CASES   if t["label"] == "PASS")
    vc_fail  = sum(1 for t in VOICE_TEST_CASES   if t["label"] == "FAIL")

    print(f"[Generator] Chatbot: {len(CHATBOT_TEST_CASES)} cases ({cb_pass} PASS, {cb_fail} FAIL) → {cb_path}")
    print(f"[Generator] Voice  : {len(VOICE_TEST_CASES)} cases ({vc_pass} PASS, {vc_fail} FAIL) → {vc_path}")

    # Error type breakdown
    cb_types = {}
    for t in CHATBOT_TEST_CASES:
        for issue in t["ground_truth"].get("issues", []):
            cb_types[issue["type"]] = cb_types.get(issue["type"], 0) + 1
    vc_types = {}
    for t in VOICE_TEST_CASES:
        for issue in t["ground_truth"].get("issues", []):
            vc_types[issue["type"]] = vc_types.get(issue["type"], 0) + 1

    print(f"\n[Generator] Chatbot issue distribution: {cb_types}")
    print(f"[Generator] Voice issue distribution  : {vc_types}")
    print(f"\n[Generator] Done. Run benchmark with: python3 simulation/run_benchmark.py")


if __name__ == "__main__":
    main()
