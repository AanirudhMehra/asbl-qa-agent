"""
spam_filter.py — Layer 1 regex pre-filter for user messages.

Checks user turns in a conversation before the LLM is called.
If any turn is flagged → conversation is marked SKIPPED (skip_reason=SPAM_FILTERED)
and the LLM evaluation is skipped entirely (saves tokens).

Layer 2 (LLM) detection is handled inside chatbot_qa.md — the LLM returns
user_flags in its JSON output for conversations that pass Layer 1.
"""

import re

# ── Regex rules per category ─────────────────────────────────────────────────
# Each value is a regex pattern matched case-insensitively against user text.
# Keep patterns specific enough to avoid false positives on real estate queries.

RULES = {
    "LINK_URL": (
        r'https?://'
        r'|www\.'
        r'|bit\.ly|t\.me|tinyurl\.com|short\.ly'
        r'|\.com/[^\s]'          # URL paths (not just .com as a word)
        r'|\.in/[^\s]'           # .in URLs
    ),
    "PROMO_SCAM": (
        r'\b(win|prize|lottery|casino|gambling|jackpot)\b'
        r'|\b(earn\s*₹|free\s*money|make\s*money\s*online|earn\s*from\s*home)\b'
        r'|\b(click\s*here|investment\s*scheme|double\s*your|mlm|ponzi)\b'
        r'|\b(crypto|bitcoin|forex|trading\s*tips)\b'
    ),
    "SOCIAL_VIRAL": (
        r'\b(follow\s*(me|us)|subscribe|like\s*and\s*share)\b'
        r'|youtube\.com|instagram\.com|facebook\.com'
        r'|\b(reels|tiktok|viral|share\s*this|forward\s*this)\b'
        r'|\bwhatsapp\s*forward\b'
    ),
    "RELIGIOUS": (
        r'\b(jai\s*shri\s*ram|jai\s*mata\s*di|allah\s*hu\s*akbar|subhan\s*allah)\b'
        r'|\b(jesus\s*loves|praise\s*the\s*lord|hallelujah)\b'
        r'|\b(bhagwan\s*ka|mandir|masjid|church|gurudwara)\b'
        r'|\b(eid\s*mubarak|ramadan\s*kareem|happy\s*diwali|happy\s*christmas)\b'
        r'|\b(om\s*namah\s*shivay|jai\s*hanuman|har\s*har\s*mahadev)\b'
    ),
    "AUTO_REPLY": (
        r'\b(out\s*of\s*office|on\s*leave|back\s*on)\b'
        r'|\b(automated\s*reply|auto\s*reply|auto.?generated)\b'
        r'|\bdo\s*not\s*reply\s*to\s*this\b'
        r'|\bthis\s*is\s*an?\s*(automated|system)\s*(message|reply|notification)\b'
    ),
    "JOB_QUERY": (
        r'\b(job|vacancy|vacancies|opening|openings)\b'
        r'|\b(hiring|recruitment|job\s*offer|job\s*opportunity)\b'
        r'|\b(salary|ctc|lpa|fresher|experienced\s*candidate)\b'
        r'|\b(send\s*(me|your)\s*resume|share\s*(your\s*)?cv|job\s*apply)\b'
        r'|\b(hr\s*contact|hr\s*email|hr\s*department)\b'
    ),
    "VULGAR_ABUSIVE": (
        r'\b(fuck|shit|bitch|asshole|bastard|dickhead)\b'
        r'|\b(chutiya|madarchod|benchod|bhenchod|randi|harami|gandu|sala)\b'
        r'|\b(bc\b|mc\b|mf\b)'                    # abbreviations
        r'|\b(shut\s*up|go\s*to\s*hell|i\s*will\s*kill)\b'
    ),
    "KEYSMASH": (
        r'(.)\1{5,}'                               # same char repeated 6+ times: aaaaaa
        r'|^[qwertyuiop]{6,}$'                    # top keyboard row only
        r'|^[asdfghjkl]{6,}$'                     # middle keyboard row only
        r'|^[zxcvbnm]{5,}$'                       # bottom keyboard row only
        r'|qwert.*asdf|asdf.*qwert'               # mixing keyboard rows
        r'|^[b-df-hj-np-tv-xz]{8,}$'             # 8+ consonants only, no vowels
    ),
    "PERSONAL_IRRELEVANT": (
        r'\b(will\s*you\s*marry|i\s*love\s*you|be\s*my\s*(girlfriend|boyfriend))\b'
        r'|\b(are\s*you\s*(human|real|ai|a\s*robot)|what\s*is\s*your\s*name)\b'
        r'|\b(tell\s*me\s*a\s*joke|sing\s*a\s*song|play\s*a\s*game)\b'
        r'|\b(good\s*morning|good\s*night|how\s*are\s*you)\s*$'  # only if that's the entire message
    ),
}

CATEGORY_LABELS = {
    "LINK_URL":            "Links / URLs",
    "PROMO_SCAM":          "Promo / Scam / Gambling",
    "SOCIAL_VIRAL":        "Social Media / Viral",
    "RELIGIOUS":           "Religious Messages",
    "AUTO_REPLY":          "Auto Reply / Bot",
    "JOB_QUERY":           "Job Queries",
    "VULGAR_ABUSIVE":      "Vulgar / Abusive",
    "KEYSMASH":            "Random Keysmash",
    "PERSONAL_IRRELEVANT": "Personal / Irrelevant",
}


def flag_message(text: str) -> list:
    """
    Check a single message string against all rules.
    Returns list of matching flag type strings. Empty = clean.
    """
    if not text or not text.strip():
        return []
    flags = []
    for category, pattern in RULES.items():
        try:
            if re.search(pattern, text, re.IGNORECASE | re.MULTILINE):
                flags.append(category)
        except re.error:
            pass
    return flags


def flag_conversation(conversation_depth: list) -> list:
    """
    Check all user turns in a conversation depth array.

    Returns list of flag dicts, one per flagged user message:
      [{"turn": 1, "type": "LINK_URL", "layer": 1, "text": "..."}]

    Empty list = no flags found (conversation is clean).
    """
    all_flags = []
    for i, turn in enumerate(conversation_depth, 1):
        user_text = (turn.get("userText") or "").strip()
        if not user_text:
            continue
        for flag_type in flag_message(user_text):
            all_flags.append({
                "turn":  i,
                "type":  flag_type,
                "layer": 1,
                "text":  user_text[:300],
            })
    return all_flags


if __name__ == "__main__":
    # Quick smoke test
    tests = [
        ("Check out this deal at https://bit.ly/xyz", ["LINK_URL"]),
        ("Win a free iPhone! Click here now", ["PROMO_SCAM"]),
        ("Do you have any job vacancies?", ["JOB_QUERY"]),
        ("asdfghjklqwerty", ["KEYSMASH"]),
        ("Jai Shri Ram, I want to book a flat", ["RELIGIOUS"]),
        ("What is the price of 2BHK?", []),    # real estate query — should be clean
        ("I want to visit the site", []),       # clean
    ]
    all_ok = True
    for text, expected_types in tests:
        result = flag_message(text)
        status = "OK" if all(t in result for t in expected_types) else "FAIL"
        if status == "FAIL":
            all_ok = False
        print(f"  [{status}] '{text[:50]}' → {result} (expected {expected_types})")
    print(f"\n{'All tests passed.' if all_ok else 'SOME TESTS FAILED.'}")
