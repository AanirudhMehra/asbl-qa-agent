# ASBL QA Agent — Full Implementation Document
*What we built, how it works, every formula, every schema. Plain English.*
*Last updated: May 16, 2026*

---

## SECTION 1: WHAT THIS SYSTEM IS

ASBL has two AI products talking to customers:
1. A **text chatbot** on the website (handles queries about properties)
2. A **voice agent called Anandita** (handles inbound and outbound phone calls)

This system runs automatically every 4 hours. It:
- Reads every chatbot conversation and phone call that happened in the last 4 hours
- Checks each one for errors against the knowledge base
- Validates whether your business goals (site visits, OTP completions, etc.) are being met
- Identifies every problem — whether in the bots or in the analytics scoring
- Tells you exactly which file to change and what to write in it

No human effort needed for routine operation.

---

## SECTION 2: SYSTEM ARCHITECTURE

```
PROD MongoDB (READ ONLY — never written to)
├── asbl_loft.conversations
├── ASBLVoiceBot.call_transcripts
├── analytics_db.scores_overall
├── analytics_db.scores_session_wise
├── analytics_db.meta_conversion_events
├── analytics_db.multiplier_completion_events
└── analytics_db.context_multipliers

        ↓ read only ↓

runner.py (fires every 4 hours)
├── Step 1 → Chatbot QA Agent
├── Step 2 → Voice QA Agent
├── Step 3 → Analytics Agent
├── Step 4 → Feedback Agent  ──→ returns problems[]
└── Step 5 → Recommendation Agent ← receives problems[] directly

        ↓ writes results ↓

Results MongoDB (WRITE ONLY — separate cluster, never prod)
database: qa_results
├── chatbot_qa
├── voice_qa
├── analytics_runs
├── health_scores
├── feedback
└── recommendations
```

**LLM:** Ollama running locally on Mac. Model: llama3.1:8b. Endpoint: http://localhost:11434. Free, offline, no API key needed.

**Two separate MongoDB connections:**
- `MONGO_URI_PROD` — read only, never written to, this is production data
- `MONGO_URI_RESULTS` — separate cluster, all QA results written here

---

## SECTION 3: THE 5 AGENTS — WHAT EACH ONE DOES

---

### AGENT 1: CHATBOT QA

**File:** `agents/chatbot_qa.py`

**Purpose:** Read every new chatbot conversation, check it for errors, score it.

**Where it reads from:** `asbl_loft.conversations` (prod, read only)

**Full step-by-step logic:**

```
1. Calculate time window: now - 4 hours
2. Query prod MongoDB: conversations where createdAt >= window AND turnCount >= 2
3. For each conversation:
   a. Check qa_results.chatbot_qa — does this conversation_id already exist?
      YES → skip (already evaluated in a previous run)
      NO  → proceed
   b. Load agents/prompts/chatbot_qa.md (fresh from disk — 10KB of instructions)
   c. Load all 8 KB files from knowledge_base/webbot/ (fresh from disk)
   d. Strip HTML from botText fields
   e. Format conversation as: "User: ...\nBot: ..."
   f. Send to Ollama:
      [chatbot_qa.md prompt] + [KB] + [conversation]
   g. Ollama returns JSON (score, confidence, issues, status, summary)
   h. Save to qa_results.chatbot_qa
   i. If FAIL → print alert to console
4. Print summary: evaluated X, skipped Y already done
```

**What the Ollama prompt (chatbot_qa.md) tells the LLM to check:**

| Issue Type | Severity | Definition |
|---|---|---|
| PRICE_ACCURACY | HIGH | Wrong price quoted for any unit |
| RERA_NUMBER | HIGH | Wrong or missing RERA registration number |
| INVENTED_FACT | HIGH | Bot stated something not in KB (rental offer, model flat, wrong handover date) |
| GUARDRAIL_VIOLATION | HIGH | Legal guarantee, investment promise |
| MISSED_LEAD_CAPTURE | MEDIUM | 3+ turns, clear interest, no name/phone asked |
| TONE_ISSUE | MEDIUM | Unprofessional language for a premium brand |
| INCOMPLETE_RESPONSE | MEDIUM | Direct question not answered |
| WRONG_PROJECT_RECOMMENDATION | MEDIUM | Recommended project doesn't match stated budget |
| LANGUAGE_MISMATCH | LOW | User wrote Hindi/Telugu, bot replied only English |
| MINOR_PHRASING | LOW | Minor awkwardness, information is correct |

**FAIL condition:** Any HIGH issue exists, OR 3+ MEDIUM issues exist.

**Score rubric (Ollama assigns this):**
```
10 = perfect
 9 = excellent, one minor LOW issue
 8 = good, LOW issues only
 7 = acceptable, one MEDIUM issue
 6 = below average, two MEDIUM issues
 5 = poor, two MEDIUM or one HIGH with some recovery
 4 = bad, one HIGH issue clearly identified
 3 = very bad, multiple HIGH issues
 2 = terrible, invented facts
 1 = complete failure
```

**Confidence score (Ollama assigns this, 0.0–1.0):**
```
1.0 = exact factual mismatch found (bot said 1.90cr, KB says 1.94cr). Certain.
0.8 = strong evidence, minor ambiguity
0.6 = likely issue, conversation short or context unclear
0.4 = possible issue, not confident
0.2 = very uncertain, flagging speculatively

Rule: if conversation is 1-2 turns, default confidence to ≤ 0.5
```

---

### AGENT 2: VOICE QA

**File:** `agents/voice_qa.py`

**Purpose:** Read every new phone call transcript, check Anandita's behaviour, score it.

**Where it reads from:** `ASBLVoiceBot.call_transcripts` (prod, read only)

**Full step-by-step logic:**

```
1. Calculate time window: now - 4 hours
2. Query prod: calls where started_at >= window AND transcript exists and not empty
3. For each call:
   a. Check qa_results.voice_qa — does call_sid already exist?
      YES → skip
      NO  → proceed
   b. Load agents/prompts/voice_qa.md (11KB of voice-specific instructions)
   c. Load 3 Anandita KB files: project_facts.md, system_prompt.md, qa_checklist.md
   d. Format transcript:
      speaker="Anandita" → "Anandita: ..."
      speaker=phone_number → "Caller: ..."
   e. Send to Ollama:
      [voice_qa.md prompt] + [call metadata] + [KB] + [transcript]
   f. Ollama returns JSON (same fields as chatbot + language_compliance)
   g. Save to qa_results.voice_qa
```

**Voice-specific issue types (in addition to shared ones):**

| Issue Type | Severity | Definition |
|---|---|---|
| DECIMAL_NUMBER | HIGH | Said "one ninety-four crore" instead of "one point nine four crore" |
| LANGUAGE_HANDLING | MEDIUM | Caller spoke Hindi/Telugu, Anandita didn't switch |
| MISSED_QUALIFICATION | MEDIUM | Long call without asking budget/timeline/configuration |
| AI_PHRASE | MEDIUM | Said "As an AI language model..." |
| INCOMPLETE_RESPONSE | LOW | Question not directly answered |

**Language compliance:** Separate field evaluated independently.
```
PASS: Call in English throughout,
      OR caller used Hindi/Telugu and Anandita switched correctly

FAIL: Caller clearly spoke Hindi/Telugu (multiple sentences)
      and Anandita stayed in English throughout
```

---

### AGENT 3: ANALYTICS

**File:** `agents/analytics.py`

**Purpose:** Check whether your business goals (defined in outcomes.json) are being met. Check whether the scoring system (bands, multipliers, Meta events) is working correctly.

**Where it reads from:** `analytics_db.*` (prod, read only)

**Runs 4 independent checks:**

---

#### Check 1: Band Conversion Rates (per outcome)

Reads your goals from `config/outcomes.json`. For each active outcome, for each band:

```python
OUTCOME_FIELD_MAP = {
    "site_visit_booked":       ("milestones.has_visit_booked",      None),
    "otp_verified":            ("milestones.has_otp_verified",       None),
    "affordability_confirmed": ("milestones.affordability_outcome", "YES"),
}
```

```
For each outcome:
  Pull all leads from scores_overall

  For each lead:
    band = lead.lifetime.highest_band_ever
    converted = check outcome field (True/False)

  For each band:
    rate = converted_count / total_count
    threshold = your target from outcomes.json (e.g. 60%)
    meta_events = count of meta_conversion_events where band.name = this band

    FLAG if:
      meta_events > 0
      AND rate < threshold
      AND total_count >= 3

    Flag type: BAND_OUTCOME_MISMATCH, severity: HIGH
    Detail: "[Site Visit Booked] Band5_Hot firing 3200 Meta events
             but conversion rate is 25.0% (your target: 60%)"
```

---

#### Check 2: Multiplier Effectiveness

Multipliers are score boosters triggered by specific user actions:
- **M1** = Affordability calculator (EMI-based, uses salary input) determined YES
- **M2** = Lead stayed 30+ seconds after seeing they cannot afford it
- **M3** = Lead typed their actual address
- **M4** = OTP verified (1.3× score multiplier)

```
For each multiplier (M1, M2, M3, M4):

  group_A = leads who completed this multiplier
    → from multiplier_completion_events where pattern_name starts with M1/M2/M3/M4

  group_B = leads who did NOT complete this multiplier

  rate_A = count(group_A where has_visit_booked=True) / count(group_A)
  rate_B = count(group_B where has_visit_booked=True) / count(group_B)

  effective = (rate_A > rate_B)

  FLAG if:
    NOT effective
    AND sample_size (group_A count) >= 5

  Flag type: MULTIPLIER_INEFFECTIVE, severity: MEDIUM
  Detail: "M1 not improving visit rates — with: 12%, without: 15%"
```

---

#### Check 3: Meta Signal Accuracy

Meta/Google conversion events fire when a lead crosses a band threshold. This checks whether those signals are accurate (i.e. the leads that trigger expensive Meta events actually convert).

```
Pull all meta_conversion_events

For each event:
  lead_id = event.lead_id

  If no lead_id:
    Try: event.session_id → scores_session_wise → lead_id

  If lead found:
    Check: scores_overall.milestones.has_visit_booked == True?
    YES → led_to_visit += 1
    NO  → wasted += 1

  If no lead found at all:
    wasted += 1

accuracy = led_to_visit / total_events

FLAG if:
  accuracy < 0.20 (20%)
  AND total_events >= 10

Flag type: META_SIGNAL_LOW_ACCURACY, severity: HIGH
```

Current state: 0.38% accuracy (52/13,653 events led to a visit).

---

#### Check 4: Funnel Gaps

```
Gap 1: leads_with_no_session
  Query: scores_overall where lifetime.total_sessions == 0
  Flag if count > 0, severity: LOW

Gap 2: affordability_yes_no_visit
  Query: scores_overall where:
    milestones.affordability_outcome == "YES"
    AND milestones.has_visit_booked == False
  Flag if count > 3, severity: MEDIUM

NOTE: has_visit_confirmed was REMOVED — this field is never populated in the system.
```

---

#### Analytics Output Saved to MongoDB:

```json
{
  "run_at": "ISO timestamp",
  "outcomes_checked": ["site_visit_booked", "otp_verified", "affordability_confirmed"],
  "band_conversion_rates": {
    "site_visit_booked": {
      "Band5_Hot": {
        "total_leads": 8,
        "converted": 2,
        "rate": 0.25,
        "target_pct": 60,
        "meta_events_fired": 3200,
        "flag": true
      }
    }
  },
  "multiplier_effectiveness": {
    "M1_affordability_yes": {
      "with_multiplier_visit_rate": 0.12,
      "without_multiplier_visit_rate": 0.15,
      "effective": false,
      "sample_size": 8
    }
  },
  "meta_signal_accuracy": {
    "total_events_fired": 13653,
    "events_led_to_visit": 52,
    "wasted_signal_count": 13601,
    "accuracy_rate": 0.004
  },
  "funnel_gaps": [...],
  "flags": [...]
}
```

---

### AGENT 4: FEEDBACK (THE MANAGER)

**File:** `agents/feedback.py`

**Purpose:** Read all QA outputs from this cycle. Compute health scores. Ask the LLM to identify every genuine problem — single-component AND cross-agent patterns.

**Where it reads from:** `qa_results` only (never prod MongoDB).

**Does NOT generate fixes.** Only identifies problems and hands them off.

---

#### Phase 1: Compute Health Scores

**Formula for chatbot and voice health score:**

```
For each result in qa_results.chatbot_qa (last 4 hours):

  base_score  = Ollama's raw score (1–10)
  confidence  = Ollama's confidence (0.0–1.0, default 0.5 if missing)

  penalty = 0
  for each issue in result.issues:
    severity_weight = { HIGH: 2.0, MEDIUM: 0.8, LOW: 0.2 }[issue.severity]
    penalty += severity_weight × confidence

  adjusted_score = max(0, min(10, base_score - penalty))

health_score = average(all adjusted_scores)
fail_rate    = count(status == "FAIL") / total
```

**Why confidence matters in the formula:**

A HIGH issue flagged at 0.95 confidence hurts much more than one at 0.40 confidence.

```
Example A: score=7, confidence=0.95, issues=[{HIGH, PRICE_ACCURACY}]
  penalty = 2.0 × 0.95 = 1.90
  adjusted = 7 - 1.90 = 5.10  ← hurts a lot, very certain

Example B: score=7, confidence=0.40, issues=[{HIGH, PRICE_ACCURACY}]
  penalty = 2.0 × 0.40 = 0.80
  adjusted = 7 - 0.80 = 6.20  ← hurts less, uncertain flag
```

**Formula for analytics health score:**

```
flags     = analytics_doc.flags
high_f    = count(flags where severity == "HIGH")
med_f     = count(flags where severity == "MEDIUM")

analytics_score = max(0, 10 - (high_f × 2.5) - (med_f × 1.0))
```

**Health score interpretation:**

| Score | Meaning |
|---|---|
| 8.0–10.0 | Healthy |
| 6.5–7.9 | Acceptable |
| 5.0–6.4 | Concerning |
| 3.0–4.9 | Bad |
| 0.0–2.9 | Critical |

**Trend detection (looks at last 3 health scores in history):**

```
All decreasing (each < previous) → DECLINING
All increasing (each > previous) → IMPROVING
Otherwise                        → STABLE
```

All three health scores saved to `qa_results.health_scores` after every cycle.

---

#### Phase 2: Pure LLM Problem Detection

Loads `agents/prompts/feedback_reasoning.md` (12KB). No rule-based checks. The LLM sees everything and decides what is wrong.

**What the LLM is given:**
```
[feedback_reasoning.md — 12KB of reasoning instructions]

DATA FOR THIS CYCLE:
  All chatbot results: status, score, confidence, issues, summaries
  All voice results: status, score, confidence, language_compliance, issues
  Full analytics output: band rates vs targets, multiplier effectiveness,
                         meta accuracy, funnel gaps
  Health score history: last 7 readings per component with dates
```

**Cross-agent patterns the LLM is taught to detect:**

| Pattern | Condition | Meaning |
|---|---|---|
| Analytics miscalibrated | Chatbot ≥6.5 AND voice ≥6.5 BUT outcomes below target | Bots are fine. Scoring promotes wrong leads. |
| Shared KB wrong | Same HIGH issue type in BOTH chatbot and voice | KB data is outdated. Not an agent bug. |
| Band thresholds too permissive | Meta accuracy <5% AND QA healthy | Leads cross bands without real intent. |
| Doubly broken | Meta accuracy <5% AND QA also failing | Two separate root causes. |
| Voice-specific bug | Chatbot score >> voice score by 3+ pts | Voice-specific behaviour, not KB. |
| Chatbot-specific bug | Voice score >> chatbot score by 3+ pts | Chatbot-specific, not KB. |
| Affordability gap | affordability_yes_no_visit count >10 | Ops follow-up broken, not AI. |
| Multiplier not working | Multiplier ineffective AND QA healthy | Scoring weight miscalibrated. |

**Output — Problem object schema:**

```json
{
  "id": "P001",
  "title": "short description",
  "urgency": "HIGH",
  "type": "SYSTEMATIC_BUG",
  "components": ["voice"],
  "description": "plain English explanation with numbers",
  "evidence": ["data point 1", "data point 2"],
  "what_is_wrong": "one line — the specific broken thing",
  "what_is_not_wrong": "one line — what should NOT be blamed"
}
```

**Problem types:**

| Type | Meaning |
|---|---|
| SYSTEMATIC_BUG | Same issue appearing in >50% of evaluations |
| CALIBRATION | Analytics scoring model miscalibrated |
| KB_OUTDATED | Knowledge base data wrong or stale |
| PROCESS_GAP | Ops/human process broken, not AI |
| TREND | Health score declining over multiple cycles |

**Urgency rules:**

| Urgency | When |
|---|---|
| HIGH | Compliance error, Meta spend wasted, score dropped >30% from baseline, score declining below 5.0 |
| MEDIUM | Single isolated issues, multiplier calibration, ops gaps, declining trend but score still above 5.0 |
| LOW | Minor, informational, not urgent |

---

### AGENT 5: RECOMMENDATION (THE ENGINEER)

**File:** `agents/recommendation.py`

**Purpose:** For each problem the Feedback Agent found, produce one specific actionable fix. Does NOT hunt for problems — that is the Feedback Agent's job.

**Receives:** Problem list directly from Feedback Agent (passed by runner.py — no re-fetch from DB).

**For each problem, in order:**

```
1. Check KNOWN_FIXES dictionary first (no LLM needed, faster):

   DECIMAL_NUMBER     → add pronunciation rule to anandita/system_prompt.md
   PRICE_ACCURACY     → update prices in both KB files
   RERA_NUMBER        → update RERA numbers in both KB files
   LANGUAGE_HANDLING  → strengthen language switch rule in system_prompt.md

2. If no template match → call Ollama with:
   [recommendation.md — 13KB with ASBL facts, file locations, fix patterns]
   + [the specific problem: id, title, type, components, description, evidence]
   + [historical baseline: first score, best score, current score, dates for each component]

3. Return fix object
```

**Fix object schema:**

```json
{
  "problem_id": "P001",
  "problem_title": "Anandita decimal format broken",
  "urgency": "HIGH",
  "root_cause": "one sentence — includes when it started if history shows it",
  "fix": "exactly what to do — specific enough to act on today",
  "where": "exact file path, or 'scoring model', or 'CRM/ops workflow'",
  "change_type": "kb_file_edit OR scoring_model OR ops_process OR config_edit",
  "expected_outcome": "what improves, by how much, how quickly"
}
```

**Change types:**

| Type | Meaning | Deployment |
|---|---|---|
| `kb_file_edit` | Edit a .md file in knowledge_base/ | Takes effect next run automatically |
| `config_edit` | Edit a .json file in config/ | Takes effect next run |
| `scoring_model` | Change in the analytics scoring system | Needs deployment, 24–48 hrs |
| `ops_process` | Human/CRM action required. No code. | Requires human |

**How historical baseline is used:**

```
For each component (chatbot, voice, analytics):
  Fetch last 30 days of health_scores

  first_score = score on very first run
  best_score  = highest score ever and the date
  current     = latest score and the date

LLM uses this to pinpoint when the problem started:
  "Voice score was 7.5 on 2026-05-09 and dropped to 2.5 by 2026-05-12.
   Something changed around 2026-05-10."
```

---

## SECTION 4: THE RUNNER

**File:** `runner.py`

```python
def run_once():
    chatbot_qa.batch(hours=4)     # Step 1
    voice_qa.batch(hours=4)       # Step 2
    analytics.run()               # Step 3
    problems = feedback.aggregate()       # Step 4 — returns problems[]
    recommendation.run(problems)          # Step 5 — receives problems[] directly
```

The problems list is passed directly from feedback to recommendation — recommendation does NOT re-fetch from the database.

```bash
python3 runner.py once   # run one cycle right now
python3 runner.py        # run forever, every 4 hours
```

---

## SECTION 5: THE OUTCOMES CONFIG SYSTEM

**File:** `config/outcomes.json`

You write your business goals in plain English. The system handles all technical field mappings internally in code.

**Current active outcomes (3):**

```json
{
  "outcomes": [
    {
      "name": "site_visit_booked",
      "label": "Site Visit Booked",
      "goal": "I want at least 30% of all leads to book a site visit. Band5_Hot should be 60%.",
      "active": true,
      "targets": {
        "overall_pct": 30,
        "by_band_pct": {
          "Band3_Intent": 10,
          "Band4_Qualified": 30,
          "Band5_Hot": 60
        }
      }
    },
    {
      "name": "otp_verified",
      "label": "OTP Verified",
      "goal": "I want 60% of Band5_Hot leads to complete OTP verification.",
      "active": true,
      "targets": {
        "overall_pct": 15,
        "by_band_pct": {
          "Band2_Engaged": 15,
          "Band3_Intent": 25,
          "Band4_Qualified": 40,
          "Band5_Hot": 60
        }
      }
    },
    {
      "name": "affordability_confirmed",
      "label": "Affordability Confirmed",
      "goal": "I want 35% of Band4_Qualified leads to confirm affordability.",
      "active": true,
      "targets": {
        "overall_pct": 10,
        "by_band_pct": {
          "Band2_Engaged": 10,
          "Band3_Intent": 20,
          "Band4_Qualified": 35,
          "Band5_Hot": 50
        }
      }
    }
  ]
}
```

**Internal field mapping in analytics.py (users never touch this):**

```python
OUTCOME_FIELD_MAP = {
    "site_visit_booked":       ("milestones.has_visit_booked",      None),
    "otp_verified":            ("milestones.has_otp_verified",       None),
    "affordability_confirmed": ("milestones.affordability_outcome", "YES"),
}
```

**To add a new outcome:** Add a block to outcomes.json with a supported `name`, set `active: true`, write targets as percentages. Zero code changes.

**To pause an outcome:** Set `"active": false`.

---

## SECTION 6: THE PROMPT FILE SYSTEM

Every LLM-using agent has a dedicated prompt file in `agents/prompts/`. These files are loaded **fresh from disk on every run** — edit the file and the agent's behaviour changes on the next 4-hour cycle. No code deployment needed.

| File | Size | What it controls |
|---|---|---|
| `chatbot_qa.md` | ~10KB | Issue types, severity rules, scoring rubric, confidence rules, edge cases, output schema |
| `voice_qa.md` | ~11KB | Same as chatbot plus: decimal format rules, language compliance, voice-specific guardrails |
| `feedback_reasoning.md` | ~12KB | Health score interpretation, all cross-agent reasoning patterns, urgency classification, false positive avoidance |
| `recommendation.md` | ~13KB | All ASBL file locations, project facts ground truth, band/multiplier scoring context, known fix templates, how to use historical baseline |

**How prompts are structured in every LLM call:**

```
[Full .md prompt file — static instructions loaded from disk]
                    +
[Dynamic data injected by code at runtime — conversation / analytics results / problem details]
                    =
Full prompt sent to Ollama (http://localhost:11434)
```

**Ollama settings:**
- Temperature: 0.1 (near-deterministic output)
- num_predict: 1500 tokens max
- JSON extraction: brace-matching algorithm, up to 2 retries on parse failure

---

## SECTION 7: THE RESULTS DATABASE — FULL SCHEMA

**Database:** `qa_results` on a separate MongoDB cluster (never prod)
**URI env var:** `MONGO_URI_RESULTS`

---

### Collection: `chatbot_qa`

One document per conversation evaluated.

| Field | Type | Definition |
|---|---|---|
| `_id` | ObjectId | MongoDB auto-generated ID |
| `conversation_id` | String | e.g. "c-1778876809751-13ps22ku". Unique per conversation. |
| `status` | String | "PASS", "FAIL", or "SKIPPED" |
| `score` | Integer | 1–10. Ollama's raw quality score before penalty. |
| `confidence` | Float | 0.0–1.0. How certain Ollama is about its evaluation. Default 0.5 if LLM omits it. |
| `turn_count` | Integer | Number of user-bot exchanges in the conversation |
| `issues` | Array | List of issue objects (see below) |
| `summary` | String | One sentence from Ollama describing what happened |
| `evaluated_at` | String | ISO timestamp of when evaluation ran |

**Issue object:**
```json
{
  "type": "PRICE_ACCURACY",
  "severity": "HIGH",
  "detail": "Bot said 1695sqft = 1.90 crore. KB says 1.94 crore + 5% GST."
}
```

---

### Collection: `voice_qa`

One document per call evaluated.

| Field | Type | Definition |
|---|---|---|
| `_id` | ObjectId | MongoDB auto-generated |
| `call_sid` | String | Unique call identifier e.g. "2308d6a6-..." |
| `phone_number` | String | Caller's phone number |
| `call_direction` | String | "inbound" or "outbound" |
| `language_used` | String | Language detected on the call |
| `project` | String | Which ASBL project was discussed |
| `status` | String | "PASS", "FAIL", or "SKIPPED" |
| `score` | Integer | 1–10 |
| `confidence` | Float | 0.0–1.0 |
| `language_compliance` | String | "PASS" or "FAIL" — evaluated independently from score |
| `issues` | Array | Same structure as chatbot_qa |
| `summary` | String | One sentence summary |
| `evaluated_at` | String | ISO timestamp |

---

### Collection: `analytics_runs`

One document per analytics check cycle.

| Field | Type | Definition |
|---|---|---|
| `_id` | ObjectId | Auto-generated |
| `run_at` | String | ISO timestamp |
| `outcomes_checked` | Array[String] | Names of active outcomes checked |
| `band_conversion_rates` | Object | Nested: outcome_name → band_name → conversion data |
| `multiplier_effectiveness` | Object | Multiplier name → effectiveness data |
| `meta_signal_accuracy` | Object | Accuracy stats for Meta conversion events |
| `funnel_gaps` | Array | List of gap objects |
| `flags` | Array | All issues found in this run |

**band_conversion_rates nested structure:**
```json
{
  "site_visit_booked": {
    "Band5_Hot": {
      "total_leads": 8,
      "converted": 2,
      "rate": 0.25,
      "target_pct": 60,
      "meta_events_fired": 3200,
      "flag": true
    }
  }
}
```

**multiplier_effectiveness nested structure:**
```json
{
  "M1_affordability_yes": {
    "with_multiplier_visit_rate": 0.12,
    "without_multiplier_visit_rate": 0.15,
    "effective": false,
    "sample_size": 8
  }
}
```

**meta_signal_accuracy structure:**
```json
{
  "total_events_fired": 13653,
  "events_led_to_visit": 52,
  "wasted_signal_count": 13601,
  "accuracy_rate": 0.004
}
```

**flag object:**
```json
{
  "type": "BAND_OUTCOME_MISMATCH",
  "outcome": "Site Visit Booked",
  "severity": "HIGH",
  "detail": "[Site Visit Booked] Band5_Hot firing 3200 Meta events but rate is 25.0% (target: 60%)"
}
```

---

### Collection: `health_scores`

One document per component per run cycle. This is the historical record used by the Feedback and Recommendation agents for trend detection.

| Field | Type | Definition |
|---|---|---|
| `_id` | ObjectId | Auto-generated |
| `recorded_at` | String | ISO timestamp |
| `component` | String | "chatbot", "voice", or "analytics" |
| `score` | Float | Severity-weighted health score 0.0–10.0 |
| `fail_rate` | Float | Fraction of evaluations that failed (0.0–1.0) |
| `details` | Object | Component-specific details (see below) |

**Chatbot/Voice details object:**
```json
{
  "total_evaluated": 15,
  "fails": 3
}
```

**Analytics details object:**
```json
{
  "high_flags": 2,
  "medium_flags": 1,
  "total_flags": 3
}
```

---

### Collection: `feedback`

Human-submitted feedback (separate from automated checks).

| Field | Type | Definition |
|---|---|---|
| `_id` | ObjectId | Auto-generated |
| `text` | String | Raw feedback text submitted |
| `submitted_by` | String | Name of person who submitted |
| `submitted_at` | String | ISO timestamp |
| `product` | String | "chatbot", "voice_agent", "analytics", "general" |
| `type` | String | "bug", "suggestion", "complaint", "praise" |
| `priority` | String | "high", "medium", "low" |
| `tag` | String | "PRICE_ISSUE", "RERA_NUMBER", "TONE", "LANGUAGE", "LEAD_CAPTURE", "ANALYTICS", "META_SIGNAL", "PERFORMANCE", "OTHER" |
| `actionable` | Boolean | Whether this feedback can be acted on |
| `summary` | String | One-sentence LLM-generated summary |

---

### Collection: `recommendations`

One document per recommendation cycle.

| Field | Type | Definition |
|---|---|---|
| `_id` | ObjectId | Auto-generated |
| `generated_at` | String | ISO timestamp |
| `negative_signals` | Array[String] | Titles of all problems that were found this cycle |
| `root_cause` | String | Top root cause sentence (from highest urgency fix) |
| `fixes` | Array | List of fix objects (ranked by urgency) |
| `priority` | String | "HIGH", "MEDIUM", or "LOW" — urgency of the top problem |

**Fix object inside recommendations:**
```json
{
  "rank": 1,
  "problem_id": "P001",
  "component": "voice",
  "problem": "Anandita decimal format broken",
  "fix": "Add pronunciation rule to system_prompt.md: 'Always say one point nine four crore, never one ninety-four crore'",
  "expected_outcome": "DECIMAL_NUMBER errors drop to 0 within next cycle (4 hours)"
}
```

---

## SECTION 8: PROD DATABASE — READ-ONLY DATA STRUCTURES

Never written to. Understood here for reference.

### `asbl_loft.conversations`
```
conversationId    → unique ID e.g. "c-1778876809751-13ps22ku"
createdAt         → timestamp (may be string or datetime)
leadId            → may be null (visitor_id is sufficient, not every visitor is a lead)
turnCount         → number of user-bot exchanges (we only process >= 2)
conversationDepth → array of turns:
  {
    turnNumber  → integer
    userText    → string
    botText     → HTML string (HTML stripped by chatbot_qa.py)
    botSource   → where bot got the answer from
    botLatency  → response time in ms
  }
```

### `ASBLVoiceBot.call_transcripts`
```
call_sid          → unique call ID
phone_number      → caller's number
call_direction    → "inbound" / "outbound"
started_at        → timestamp
ended_at          → timestamp
transcript        → array: { speaker, text, ts }
  speaker = "Anandita" or caller's phone number
full_text         → entire transcript as one string
call_outcome      → result of the call
intent            → detected purchase intent
budget            → detected budget
project           → which project was discussed
site_visit_agreed → boolean
language_used     → detected language
ready_to_book     → boolean
nri_buyer         → boolean
name              → detected caller name
```

### `analytics_db.scores_overall` (~30 docs)
```
lead_id           → unique lead identifier
current_band      → "Band1_Spark" through "Band5_Hot"
latest_score      → current score
lifetime:
  best_score_ever       → highest score ever reached
  highest_band_ever     → highest band ever reached (used for band conversion checks)
  total_reached_value_inr → cumulative Meta event value fired
  total_sessions        → number of website sessions
milestones:
  has_otp_verified      → boolean ← used by otp_verified outcome
  has_visit_booked      → boolean ← used by site_visit_booked outcome
  has_visit_confirmed   → boolean ← NOT POPULATED, removed from all checks
  affordability_outcome → "YES", "NO", or null ← used by affordability_confirmed outcome
visitor_id        → anonymous visitor identifier (always present, lead_id may be null)
```

### `analytics_db.meta_conversion_events` (~13,164 docs)
```
session_id        → session identifier
lead_id           → may be null for anonymous visitors
visitor_id        → always present
event_name        → e.g. "Band3_Intent_Reached"
fired_at          → timestamp
band:
  name            → band name e.g. "Band3_Intent"
  threshold       → score threshold this band requires
  score_at_trigger → actual score when event fired
conversion:
  value_inr       → Meta ad event value (₹500 to ₹7,85,500)
  phase           → lifecycle phase
  platforms       → ["meta", "google"]
```

### `analytics_db.multiplier_completion_events`
```
pattern_name  → starts with "M1", "M2", "M3", or "M4"
lead_id       → the lead who completed this multiplier
completed_at  → timestamp
```

---

## SECTION 9: BAND SCORING SYSTEM (ASBL'S ANALYTICS — READ ONLY)

The scoring system is external. The QA agent reads its outputs and validates them. It does not compute scores itself.

| Band | Approximate Score Range | Meta Event Value (₹) |
|---|---|---|
| Band1_Spark | 8–20 | 500 |
| Band2_Engaged | 40–53 | 5,500 |
| Band3_Intent | 60–98 | 35,500 |
| Band4_Qualified | 130–191 | 1,85,500 |
| Band5_Hot | 230–316+ | 7,85,500 |

**Multipliers:**

| ID | Trigger | Effect |
|---|---|---|
| M1 | Affordability calculator (EMI-based, salary input) says YES | Score boost |
| M2 | Lead stayed 30+ seconds after seeing they cannot afford it | Score boost |
| M3 | Lead typed their actual address | Score boost |
| M4 | OTP verified | 1.3× score multiplier |

---

## SECTION 10: THE LLM WRAPPER

**File:** `llm.py`

```python
def ask(prompt: str) -> str:
    # Sends prompt to Ollama, returns raw text response

def _extract_json(text: str) -> dict:
    # 1. Strip markdown code fences (```json ... ```)
    # 2. Find first { using brace-matching algorithm to locate complete JSON block
    # 3. Parse and return
    # Raises ValueError if no valid JSON found

def ask_json(prompt: str, retries: int = 2) -> dict:
    # Calls ask(), then _extract_json()
    # Retries up to 2 times on parse failure
    # Returns parsed dict or raises on final failure
```

**Ollama call parameters:**
```json
{
  "model": "llama3.1:8b",
  "prompt": "...",
  "stream": false,
  "options": {
    "temperature": 0.1,
    "num_predict": 1500
  }
}
```

---

## SECTION 11: FILE STRUCTURE

```
asbl-qa-agent/
├── .env                              ← MONGO_URI_PROD, MONGO_URI_RESULTS, TEAMS_WEBHOOK_URL
├── requirements.txt                  ← pymongo, python-dotenv, requests
├── llm.py                            ← Ollama wrapper (ask, ask_json, _extract_json)
├── db.py                             ← Results DB interface (reads/writes qa_results only)
├── notifier.py                       ← Console logging + Teams webhook slot
├── runner.py                         ← 4-hour batch runner (runs all 5 agents in sequence)
├── config/
│   └── outcomes.json                 ← Business goals in plain English
├── agents/
│   ├── chatbot_qa.py                 ← Evaluates chatbot conversations
│   ├── voice_qa.py                   ← Evaluates Anandita phone calls
│   ← analytics.py                   ← Validates analytics scoring and band conversion
│   ├── feedback.py                   ← Computes health scores, finds problems via LLM
│   └── recommendation.py             ← Generates specific fixes for each problem
├── agents/prompts/
│   ├── chatbot_qa.md                 ← ~10KB evaluator instructions
│   ├── voice_qa.md                   ← ~11KB voice-specific instructions
│   ├── feedback_reasoning.md         ← ~12KB manager reasoning rules
│   └── recommendation.md             ← ~13KB fix generation instructions and ASBL facts
├── knowledge_base/
│   ├── webbot/
│   │   ├── 00_qa_checklist.md
│   │   ├── 01_system_prompt.md
│   │   ├── 02_kb_project_loft.md
│   │   ├── 03_kb_market_intelligence.md
│   │   ├── 04_kb_competitive_landscape.md
│   │   ├── 05_kb_persona_playbook.md
│   │   ├── 06_kb_objection_library.md
│   │   ├── 07_kb_resale_framework.md
│   │   └── 08_deployment_guide.md
│   └── anandita/
│       ├── project_facts.md          ← Prices, RERA, handover dates for all 4 projects
│       ├── system_prompt.md          ← Anandita's persona, language rules, guardrails
│       └── qa_checklist.md           ← What Anandita is checked against on calls
├── IMPLEMENTATION.md                 ← This document
└── CONTEXT.md                        ← Project context for resuming after context loss
```

---

## SECTION 12: WHAT YOU CAN CHANGE WITHOUT TOUCHING CODE

| What to change | File to edit | Takes effect |
|---|---|---|
| Add a new business goal | `config/outcomes.json` | Next 4-hour run |
| Change target percentages | `config/outcomes.json` | Next 4-hour run |
| Pause a goal | `config/outcomes.json` — set `"active": false` | Next run |
| Change what chatbot is checked for | `agents/prompts/chatbot_qa.md` | Next run |
| Change how voice calls are evaluated | `agents/prompts/voice_qa.md` | Next run |
| Add a cross-agent reasoning pattern | `agents/prompts/feedback_reasoning.md` | Next run |
| Change urgency thresholds | `agents/prompts/feedback_reasoning.md` | Next run |
| Add a known fix template | `agents/prompts/recommendation.md` | Next run |
| Update ASBL prices | `knowledge_base/anandita/project_facts.md` AND `knowledge_base/webbot/02_kb_project_loft.md` | Next run |
| Update RERA numbers | Same two files above | Next run |

---

## SECTION 13: HOW TO RUN

```bash
# Prerequisites
# 1. Ollama app must be open (check Mac menu bar — llama3.1:8b model must be pulled)
# 2. .env must have MONGO_URI_PROD and MONGO_URI_RESULTS set

# Install dependencies (one time)
pip3 install pymongo python-dotenv requests --break-system-packages

# Run one full cycle right now (for testing)
cd /Users/aanirudhmehra/Desktop/asbl-qa-agent
python3 runner.py once

# Run continuously every 4 hours (production)
python3 runner.py

# Run individual agents
python3 agents/chatbot_qa.py          # evaluates last 4 hours of conversations
python3 agents/voice_qa.py            # evaluates last 4 hours of calls
python3 agents/analytics.py           # runs all analytics checks
python3 agents/feedback.py aggregate  # computes health scores + finds problems
python3 agents/recommendation.py      # generates fixes (runs feedback first if needed)

# Submit human feedback
python3 agents/feedback.py submit "Bot gave wrong price for Spectra 1980sqft" "Anirudh"
python3 agents/feedback.py list 20    # view last 20 feedback entries
```

---

## SECTION 14: PENDING (NOT YET BUILT)

| # | What | Status | Needs |
|---|---|---|---|
| 1 | Security Agent | Not started | CodeAnt account + Bitbucket API token from Anirudh |
| 2 | Teams webhook | Wired but not delivering | Power Automate flow returns 202 but message doesn't appear |
| 3 | Meta Agent | Deliberately deferred | Planned for next feature cycle |

---

## SECTION 15: ASBL PROJECT FACTS (GROUND TRUTH)

These are the authoritative values used by the recommendation agent when fixing KB errors.

**ASBL Loft**
- Location: Financial District, Hyderabad
- Configuration: 3BHK only
- Handover: December 2026
- 1695 sqft = 1.94 crore + 5% GST
- 1870 sqft = 2.15 crore + 5% GST
- Payment plan: 50:50
- Booking amount: 10 lakhs
- RERA: P02400006761
- Rental offer: NONE
- Model flat: NONE

**ASBL Spectra**
- Location: Financial District
- Configuration: 3BHK only
- Status: Ready to move NOW
- 1980 sqft = 1.95 crore + 5% GST
- 2220 sqft = 2.15 crore + 5% GST
- RERA: P02400003071
- Model flat: Available

**ASBL Broadway**
- Location: Financial District
- Configuration: 3BHK only
- Handover: December 2029
- Pricing: 9,899 per sqft ONLY (never quote total price)
- RERA: P02400009684

**ASBL Landmark**
- Location: Kukatpally
- Configuration: 3BHK and 3.5BHK (4BHK SOLD OUT — never mention as available)
- Handover: December 2028
- Pricing: 8,799 per sqft ONLY (never quote total price)
- RERA: P02200008770

**GST: 5% on all projects. Always disclosed upfront.**
