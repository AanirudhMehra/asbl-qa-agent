# ASBL QA Agent — Full System Context

> This file is the single source of truth for how the entire system works.
> Read this before touching any file in this repo.

---

## What This System Does

Every 4 hours, this system automatically evaluates:
- Every chatbot conversation that happened on the ASBL website
- Every call Anandita (voice AI) handled
- All lead conversion data against business targets

It finds problems, calculates health scores, identifies root causes, and generates specific actionable fixes. Humans apply the fixes. The next cycle confirms whether they worked.

---

## Tech Stack

| Component | Technology |
|---|---|
| Language | Python 3.14 |
| LLM | llama3.1:8b via Ollama (local, temperature 0.1, max 1500 tokens) |
| Prod DB (read) | MongoDB Atlas — `MONGO_URI_PROD` |
| Results DB (write) | MongoDB Atlas — `MONGO_URI_RESULTS` → `qa_results` database |
| Notifications | Microsoft Teams via Power Automate webhook |
| Runner | `runner.py` — 4-hour loop or `python3 runner.py once` |

---

## File Structure

```
asbl-qa-agent/
├── runner.py                        Entry point — runs all 5 agents sequentially
├── db.py                            All MongoDB read/write functions
├── llm.py                           Ollama wrapper — ask_json()
├── notifier.py                      Teams webhook + console + file logger
├── seed_demo.py                     Python seed script (SSL issue with Python 3.14 — use seed_demo.js)
├── seed_demo.js                     mongosh seed script — inserts sample data into all 6 collections
├── generate_doc.py                  Generates asbl_qa_elaborated.docx
├── .env                             MONGO_URI_PROD, MONGO_URI_RESULTS, TEAMS_WEBHOOK_URL
│
├── agents/
│   ├── chatbot_qa.py                Chatbot QA agent
│   ├── voice_qa.py                  Voice QA agent
│   ├── analytics.py                 Analytics agent (no LLM)
│   ├── feedback.py                  Feedback agent — health scores + LLM problem finder
│   ├── recommendation.py            Recommendation agent — generates fixes
│   └── prompts/
│       ├── chatbot_qa.md            Chatbot evaluation rules (no hardcoded facts)
│       ├── voice_qa.md              Voice evaluation rules (mirrors chatbot + voice-specific)
│       ├── feedback_reasoning.md    7 cross-agent patterns the Feedback LLM looks for
│       └── recommendation.md        Fix generation instructions
│
├── knowledge_base/
│   ├── webbot/                      Facts for chatbot KB (prices, RERA, handover, GST)
│   │   ├── 01_kb_general.md
│   │   ├── 02_kb_project_loft.md
│   │   ├── 03_kb_project_spectra.md
│   │   └── ...
│   └── anandita/                    Facts for voice agent KB
│       ├── project_facts.md
│       ├── system_prompt.md
│       └── qa_checklist.md
│
├── config/
│   └── outcomes.json                Plain-English business goals + targets
│
└── results/
    ├── qa_log.jsonl                 Append-only log of all notifications
    └── qa_results.db                (legacy SQLite — not used, MongoDB is primary)
```

---

## The 5-Step Pipeline

### Step 1 — Chatbot QA (`agents/chatbot_qa.py`)

**What it reads:** `asbl_loft.conversations` (prod MongoDB)

**Filter:** `turnCount >= 2`, `createdAt >= now - 4 hours`

**Dedup:** Checks `qa_results.chatbot_qa` — skips already evaluated `conversation_id`

**What it sends to LLM:**
- `chatbot_qa.md` — evaluation rules
- Full knowledge base (all `knowledge_base/webbot/*.md` concatenated)
- Session signals from `asbl_loft.events` (lead_captured, visit_booked, otp_verified etc.)
- Formatted conversation: `User: ... / Bot [showed: artifact]: ...`

**artifactLabel** — exposes what the bot displayed visually (unit_plans, price, visit, rental_offer, commute, amenity). Included in the formatted conversation.

**Session signals** pulled from `asbl_loft.events.uniqueEventNames`:
- `lead_success` → lead_captured
- `lead_submit` → lead_submitted
- `visit_booking` → visit_booked
- `visit_otp_verify_click` → visit_otp_verified

**LLM process:** Pass 1 (read full conversation for context) → Pass 2 (evaluate turn by turn)

**Output saved to `chatbot_qa`:**
```json
{
  "conversation_id": "conv-001",
  "status": "PASS or FAIL",
  "score": 9,
  "confidence": 0.91,
  "turn_count": 6,
  "issues": [{ "type": "KB_MISMATCH", "severity": "HIGH", "detail": "..." }],
  "summary": "One sentence.",
  "evaluated_at": "2026-05-18T04:03:21Z",
  "session_signals": { "lead_captured": true, "visit_booked": false }
}
```

---

### Step 2 — Voice QA (`agents/voice_qa.py`)

**What it reads:** `ASBLVoiceBot.call_transcripts` (prod MongoDB)

**Filter:** transcript exists and non-empty, `started_at >= now - 4 hours`

**What it sends to LLM:**
- `voice_qa.md` — evaluation rules
- Knowledge base from `knowledge_base/anandita/` (3 files)
- Call metadata: direction, language_used, project
- Formatted transcript: `Anandita: ... / Caller: ...`

**Voice-specific issue types (in addition to all chatbot types):**
- `DECIMAL_NUMBER` (HIGH): "one ninety-four crore" sounds like ₹194 cr. Correct: "one point nine four crore". Right number wrong format = DECIMAL_NUMBER. Wrong number = KB_MISMATCH. Both can fire simultaneously.
- `LANGUAGE_HANDLING` (MEDIUM): Caller spoke sustained Hindi/Telugu, Anandita stayed in English.

**Voice-specific GUARDRAIL additions:**
- Saying "As an AI language model..." — breaks persona
- Saying "I'll call you back" — she IS the call, cannot schedule herself

**Extra output field:** `language_compliance: PASS/FAIL` — independent of quality score. A call can score 8/10 but have language_compliance = FAIL.

**Output saved to `voice_qa`:**
```json
{
  "call_sid": "CA-001",
  "phone_number": "+91-9876543210",
  "call_direction": "inbound",
  "language_used": "English",
  "project": "ASBL Loft",
  "status": "PASS or FAIL",
  "score": 9,
  "confidence": 0.90,
  "language_compliance": "PASS",
  "issues": [],
  "summary": "One sentence.",
  "evaluated_at": "2026-05-18T04:11:03Z"
}
```

---

### Step 3 — Analytics Agent (`agents/analytics.py`)

**No LLM — pure Python data checks.**

**What it reads:** `analytics_db` (prod MongoDB)

**Loads:** `config/outcomes.json` — plain-English goals + target percentages

**4 checks:**

**1. Band conversion rates**
For each active outcome × each band:
```
rate = converted_leads / total_leads_in_band
```
Compared against target from outcomes.json. Flags `BAND_OUTCOME_MISMATCH` if below target AND meta_events > 0.
Also computes overall rate vs overall target → flags `OVERALL_OUTCOME_BELOW_TARGET`.
Goal text from outcomes.json is embedded in every flag.

**2. Multiplier effectiveness**
For each multiplier (M1–M4), splits leads into "completed it" vs "didn't" and compares visit rates.
If with-rate <= without-rate AND sample >= 5 → `MULTIPLIER_INEFFECTIVE`.

**3. Meta signal accuracy**
```
accuracy = events_led_to_visit / total_meta_events_fired
```
If < 20% with >= 10 events → `META_SIGNAL_LOW_ACCURACY`.

**4. Funnel gaps**
- Leads with 0 sessions
- `affordability_outcome = YES` AND `has_visit_booked = False` — AI qualified them, sales didn't follow up

**Output saved to `analytics_runs`** — full nested structure including `outcome_goals` (the plain-English goal text), band rates, multiplier data, meta accuracy, funnel gaps, and flat `flags` list.

---

### Step 4 — Feedback Agent (`agents/feedback.py`)

**Pulls:** Last 4 hours of `chatbot_qa`, `voice_qa`, most recent `analytics_runs`

**Also pulls:** Health score history (last 7 days) per component for trend detection

#### Health Score Calculation (Python — confidence-weighted)

```
Severity weights: HIGH = 1.0, MEDIUM = 0.5, LOW = 0.2

For each QA result:
  adjusted = raw_score - sum(severity_weight × confidence per issue)
  adjusted = clamp(adjusted, 0, 10)

health_score = average of all adjusted scores
fail_rate = fails / total
```

Analytics health (flag-based):
```
score = 10.0 - (2.5 × high_flags) - (1.0 × medium_flags)
score = max(0, score)
```

#### Trend Detection
Looks at last 3 health score entries per component:
- Each lower than previous → `DECLINING`
- Each higher than previous → `IMPROVING`
- Otherwise → `STABLE`
- Fewer than 2 points → `INSUFFICIENT_DATA`

#### What the Feedback LLM sees
Everything: chatbot results + health + trend, voice results + health + trend, analytics with:
- **Stated goals** from outcomes.json shown first
- Band rates with `← BELOW TARGET` markers and overall rate vs target
- Pre-computed analytics flags stated as confirmed facts
- Funnel gaps

Uses `feedback_reasoning.md` which defines **7 cross-agent patterns**:
1. QA healthy but outcomes below target → scoring model miscalibrated
2. Same HIGH issue in chatbot + voice → KB is wrong (not agent bug)
3. Meta accuracy very low + QA healthy → band thresholds too easy
4. Meta accuracy very low + QA failing → two separate problems
5. Large gap between chatbot and voice health → agent-specific bug
6. Multiplier not effective + QA healthy → multiplier weight miscalibrated
7. Affordability confirmed but no visit → human follow-up gap

LLM returns problems (not fixes) with: title, urgency, type, components, description, evidence, what_is_wrong, what_is_not_wrong.

**Output saved to `feedback`:**
```json
{
  "submitted_at": "2026-05-18T04:22:01Z",
  "source": "automated",
  "window_hours": 4,
  "chatbot_health": 6.78,
  "voice_health": 5.53,
  "chatbot_fail_rate": 0.5,
  "voice_fail_rate": 0.667,
  "chatbot_evaluated": 8,
  "voice_evaluated": 6,
  "problems_found": 3,
  "high_problems": 3,
  "medium_problems": 0,
  "top_issue_types": ["KB_MISMATCH", "LANGUAGE_HANDLING", "DECIMAL_NUMBER"],
  "problems": [...],
  "recommendations_generated": false
}
```

Problems list returned directly to runner → passed to Step 5.

---

### Step 5 — Recommendation Agent (`agents/recommendation.py`)

**Receives:** Problems list directly from Feedback Agent (no re-fetch)

**Also loads:**
- `config/outcomes.json` — goal text injected into every fix prompt
- Health score history (30 days) for baseline context

**Known fix templates** (no LLM needed — instant):
- `DECIMAL_NUMBER` → add pronunciation rule to Anandita system prompt
- `PRICE_ACCURACY` → update KB with correct values
- `RERA_NUMBER` → verify and update RERA numbers in KB
- `LANGUAGE_HANDLING` → strengthen language-switch instruction

**For all other problems:** LLM generates the fix. Every fix prompt includes:
- The problem details
- Historical baseline (when did scores start declining?)
- **Business goals from outcomes.json** — every fix must state whether it will move the goal

**Fix types:** `KB_UPDATE` / `PROMPT_UPDATE` / `CONFIG_CHANGE` / `PROCESS` (human workflow)

**Output saved to `recommendations`:**
```json
{
  "generated_at": "2026-05-18T04:23:44Z",
  "negative_signals": ["problem titles"],
  "root_cause": "One sentence.",
  "priority": "HIGH",
  "fixes": [
    {
      "rank": 1,
      "problem_id": "P-001",
      "component": "chatbot, voice",
      "problem": "Problem title",
      "fix": "Exact thing to do",
      "where": "Exact file path",
      "expected_outcome": "What improves + contribution to business goal"
    }
  ]
}
```

---

## All Scores Calculated

| Score | Scale | Who Calculates | Where Saved |
|---|---|---|---|
| Per-conversation quality | 1–10 | LLM | `chatbot_qa.score` |
| Per-call quality | 1–10 | LLM | `voice_qa.score` |
| Language compliance | PASS/FAIL | LLM | `voice_qa.language_compliance` |
| Confidence | 0.0–1.0 | LLM | `.confidence` on both |
| Chatbot health | 0–10 | Python (weighted avg) | `health_scores` component=chatbot |
| Voice health | 0–10 | Python (weighted avg) | `health_scores` component=voice |
| Analytics health | 0–10 | Python (flag-based) | `health_scores` component=analytics |
| Trend | DECLINING/IMPROVING/STABLE | Python | prompt context only |
| Band conversion rate | % | Python | `analytics_runs` |
| Meta signal accuracy | % | Python | `analytics_runs` |

---

## All Issue Types

### Chatbot and Voice (shared)

| Type | Severity | What It Catches |
|---|---|---|
| `KB_MISMATCH` | HIGH | Any factual claim contradicting the KB — price, RERA, handover, GST, sqft, payment terms |
| `INVENTED_FACT` | HIGH | Company-specific claim not in KB and couldn't come from external source |
| `GUARDRAIL_VIOLATION` | HIGH | Possession guarantee, return promise, false urgency, competitor comparison. Checked from buyer's perspective — soft language flagged same as explicit guarantees |
| `INCOMPLETE_RESPONSE` | MEDIUM | KB covers the topic but bot/Anandita didn't fully answer. Every question in a multi-question message must be addressed |
| `WRONG_PROJECT_RECOMMENDATION` | MEDIUM | 30%+ above budget with no acknowledgment, sold-out config offered, wrong location, ignored fitting option |
| `TONE_ISSUE` | MEDIUM | Unprofessional, dismissive, pushy, deflecting genuine concern |
| `LANGUAGE_MISMATCH` | LOW | Chatbot only — user wrote sustained Hindi/Telugu, bot replied only in English |
| `MINOR_PHRASING` | LOW | Factually correct but slightly awkward wording |

### Voice-only additions

| Type | Severity | What It Catches |
|---|---|---|
| `DECIMAL_NUMBER` | HIGH | Wrong verbal format — "one ninety-four" vs "one point nine four". Right number wrong format = this. Wrong number = KB_MISMATCH. Both can fire together |
| `LANGUAGE_HANDLING` | MEDIUM | Caller spoke sustained Hindi/Telugu, Anandita stayed in English. More serious than chatbot equivalent — caller feels unheard on a live call |

### FAIL conditions (both agents)
```
FAIL if: 1 or more HIGH severity issues
      OR 1 or more MEDIUM severity issues

PASS if: no HIGH issues AND no MEDIUM issues
```

---

## Results Database — 6 Collections

| Collection | What It Stores | Written By | Documents Per Cycle |
|---|---|---|---|
| `chatbot_qa` | One doc per evaluated conversation | Chatbot QA | ~8–20 |
| `voice_qa` | One doc per evaluated call | Voice QA | ~5–10 |
| `analytics_runs` | One doc per analytics run | Analytics | 1 |
| `health_scores` | One doc per component (chatbot, voice, analytics) | Feedback | 3 |
| `feedback` | One doc per cycle (health + problems) | Feedback | 1 |
| `recommendations` | One doc per cycle (ranked fixes) | Recommendation | 1 |

---

## outcomes.json — How to Use

Plain-English goals drive the analytics checks and recommendation framing.

```json
{
  "name": "site_visit_booked",
  "label": "Site Visit Booked",
  "goal": "I want to increase the lead to site visit ratio from 15% to 25%",
  "active": true,
  "targets": {
    "overall_pct": 25,
    "by_band_pct": {
      "Band4_Qualified": 35,
      "Band5_Hot": 60
    }
  }
}
```

- `name` must be in `OUTCOME_FIELD_MAP` in `analytics.py` (currently: `site_visit_booked`, `otp_verified`, `affordability_confirmed`)
- `goal` text flows through: analytics flags → feedback LLM prompt → recommendation fix prompts
- `active: false` to pause without deleting
- If below target AND meta events are firing → `BAND_OUTCOME_MISMATCH` flag raised
- Recommendation Agent frames every fix against your goals — states whether a fix will or won't move the ratio

---

## Prompt Design Philosophy

Prompts contain **rules only** — no hardcoded facts. Facts live in the knowledge base.

```
chatbot_qa.md / voice_qa.md  →  how to evaluate (rules, issue types, scoring)
knowledge_base/*.md          →  what to evaluate against (facts, prices, RERA)
feedback_reasoning.md        →  how to find cross-agent patterns (7 patterns)
recommendation.md            →  how to generate fixes
outcomes.json                →  what the business wants to achieve (goals)
```

Change a KB file → next cycle evaluates against the new facts.
Change a prompt → next cycle evaluates differently.
No code change needed for either.

---

## Notifications

`notifier.py` does three things on every FAIL or problem:
1. Logs to console
2. Appends to `results/qa_log.jsonl`
3. POSTs to Teams webhook (if configured)

**Current status:** Teams webhook returns 202 but message not appearing in channel.
**Fix:** Open Power Automate flow → verify "Post message in a channel" action exists and targets the correct channel. Check message body mapping.

---

## Known Issues / Pending Work

| Item | Status | Notes |
|---|---|---|
| Teams webhook | Broken | Power Automate flow needs debugging |
| Voice QA context | Missing | `callbackRequested`, `siteVisitBooked` from call_transcripts not passed to evaluator |
| NO_ANSWER filter | Missing | `voice_qa.batch()` should skip calls where `call_outcome == "NO_ANSWER"` |
| Security Agent | Not built | `agents/security.py` — Bitbucket API + Bandit/pip-audit |
| Bitbucket Pipelines | Not built | `bitbucket-pipelines.yml` with security scanning on push |
| End-to-end test run | Not done | `python3 runner.py once` against real data |

---

## How to Run

```bash
# Full loop every 4 hours
python3 runner.py

# Single cycle (testing)
python3 runner.py once

# Individual agents
python3 agents/chatbot_qa.py 4        # last 4 hours
python3 agents/voice_qa.py 4
python3 agents/analytics.py
python3 agents/feedback.py
python3 agents/recommendation.py

# Seed sample data into all 6 collections (requires mongosh)
mongosh "mongodb+srv://user:pass@cluster0.xxx.mongodb.net/qa_results" seed_demo.js

# Generate Word document
python3 generate_doc.py
```

---

## Key Design Decisions

**1. Each agent does exactly one job.**
QA agents evaluate. Analytics checks numbers. Feedback connects dots. Recommendations prescribes fixes. Nothing overlaps. A failure in one agent does not stop others.

**2. The system advises — humans apply fixes.**
Recommendations are never auto-applied. You make the change. The next cycle confirms it worked. If it didn't, the problem gets re-flagged.

**3. Confidence-weighted penalties.**
A HIGH issue with 0.95 confidence hurts the health score more than a MEDIUM issue with 0.4 confidence. Speculative flags don't tank the score the same way confirmed mismatches do.

**4. Cross-agent patterns are the highest value.**
No single agent can tell you "the KB is wrong" — only the Feedback Agent can, by seeing the same error in both chatbot and voice simultaneously. This is why the pipeline exists as a pipeline and not as isolated checkers.

**5. Goals drive recommendations.**
Every fix produced by the Recommendation Agent must state whether it will move your business goal. A fix that doesn't contribute to the goal is still produced but labelled as such — so you know what to prioritise.

**6. Prompts are generic — KB is the source of truth.**
No ASBL-specific facts are hardcoded in any prompt file. All prices, RERA numbers, handover dates, and project details live in the knowledge base. The prompt defines how to evaluate; the KB defines what to evaluate against.
