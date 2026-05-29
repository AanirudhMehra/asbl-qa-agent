# 08 · DEPLOYMENT & INTEGRATION GUIDE

> **Audience:** Dev team, Sales Ops, Growth Analytics · **Priority:** Read before shipping to production
>
> This guide explains how to wire the system into your existing Next.js + Node stack without breaking at scale. Every piece here is needed for the bot to actually work as designed.

---

## 1. ARCHITECTURE OVERVIEW

```
 ┌─────────────────────────────────────────────────────────────────┐
 │                      FRONTEND (Next.js)                         │
 │  • Chat UI                                                      │
 │  • Artifact renderer (project_comparison, trends, rental_offer, │
 │    amenity, master_plan, resale_framework, etc.)                │
 │  • Signal stripper (removes <signal>...</signal> before render) │
 └──────────────────┬──────────────────────────────────────────────┘
                    │
                    │ POST /api/chat
                    ▼
 ┌─────────────────────────────────────────────────────────────────┐
 │                 BACKEND (Node middleware)                       │
 │  1. Load system prompt + relevant KBs                           │
 │  2. Inject daily <dynamic_market_pulse> (if available)          │
 │  3. Forward to LLM with full conversation history               │
 │  4. On response:                                                │
 │     a. Extract <signal>{...}</signal>                           │
 │     b. Send signal JSON to CRM + analytics                      │
 │     c. Strip signal from text                                   │
 │     d. Return clean text + artifact call to frontend            │
 └──────────┬──────────────────────────────┬───────────────────────┘
            │                              │
            ▼                              ▼
 ┌────────────────────┐        ┌────────────────────────────┐
 │   CRM INGEST       │        │   ANALYTICS / WAREHOUSE    │
 │   (Sales dashboard)│        │   (Postgres/BigQuery)      │
 │                    │        │   Powers daily pulse       │
 └────────────────────┘        └────────────────────────────┘
```

---

## 2. SIGNAL STRIPPING (MUST-HAVE BEFORE LAUNCH)

If this fails, users see raw JSON in chat. This is non-negotiable infrastructure.

### Node middleware snippet

```javascript
function processLLMResponse(rawText) {
  // Extract signal payload
  const signalMatch = rawText.match(/<signal>([\s\S]*?)<\/signal>/);
  let signalData = null;
  let cleanText = rawText;

  if (signalMatch) {
    try {
      signalData = JSON.parse(signalMatch[1].trim());
    } catch (e) {
      console.error('Signal parse error:', e);
      // Log to alerting — malformed signal = bot bug
    }
    // Strip signal from user-facing text
    cleanText = rawText.replace(/<signal>[\s\S]*?<\/signal>/, '').trim();
  }

  return { cleanText, signalData };
}

// Usage in API route:
const { cleanText, signalData } = processLLMResponse(llmResponse);
if (signalData) {
  await ingestToCRM(signalData, conversationId, userId);
  await logToAnalytics(signalData, conversationId);
}
return res.json({ text: cleanText, ...artifactData });
```

### Regex safety
Use `[\s\S]*?` (non-greedy, any-char-including-newline), not `.*?`. The JSON spans multiple lines and `.` won't match newlines by default in JS.

### Fallback behaviour
If the model forgets to emit a signal (rare but possible), log the conversation turn for review and default to an empty signal object. Don't crash the reply.

---

## 3. CRM INGEST ENDPOINT

### Schema (Postgres recommended)

```sql
CREATE TABLE conversation_signals (
  id BIGSERIAL PRIMARY KEY,
  conversation_id UUID NOT NULL,
  user_id UUID,
  turn_number INT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  -- Structural anchors
  geo_context TEXT,
  primary_intent TEXT,
  decision_mode TEXT,
  rtb_score INT,
  wtb_score INT,
  mind_shift_stage INT,
  stage_delta INT,
  -- Free-text accumulative
  traits_observed JSONB,  -- array of strings
  key_facts_extracted JSONB,  -- nested object
  objection_surface JSONB,  -- array
  conversation_intelligence JSONB,  -- nested
  edge_case_flag TEXT,
  -- For sales
  next_best_action_for_sales TEXT,
  briefing TEXT,
  -- Raw for debugging
  raw_signal JSONB
);

CREATE INDEX idx_cs_conv ON conversation_signals(conversation_id);
CREATE INDEX idx_cs_rtb ON conversation_signals(rtb_score) WHERE rtb_score >= 7;
CREATE INDEX idx_cs_edge ON conversation_signals(edge_case_flag) WHERE edge_case_flag != 'none';
CREATE INDEX idx_cs_created ON conversation_signals(created_at);
```

### Sales dashboard view
Pull the **latest signal per conversation** where `rtb_score >= 6` and `edge_case_flag NOT IN ('suspected_broker', 'hostile')`. That's your hot-lead queue. The `briefing` field is the 5-second pre-call read.

### SLA
CRM ingest should be async (don't block the reply). Use a queue (Redis/BullMQ, SQS, or Postgres NOTIFY). Target: signal available in sales dashboard within 2 seconds of reply delivery.

---

## 4. KB LOADING STRATEGY AT SCALE

### Problem at 1L visitors/day
If every conversation loads all 6 KBs into context every turn:
- ~30,000 tokens per turn × ~500K turns/day = 15B tokens/day of KB data alone
- Cost-prohibitive
- Slow response times

### Solution: lazy KB loading by topic

**Router layer:** Before the main LLM call, a small classifier (can be the same LLM with a short routing prompt, or a cheaper model) classifies the user's message into 1-3 relevant KB buckets:

```
User message → Router classifier → {needs: [loft_facts, competitive]}
```

Load only those KBs into context. Default fallback: always load `01_system_prompt` + `02_kb_project_loft` (small enough to always keep).

### KB routing rules (starter config)

| Message contains... | Load these KBs |
|---------------------|----------------|
| Price, cost, payment, EMI, booking, loan, BHFL | 01, 02 |
| Other developer/project mentioned by name | 01, 02, 04 |
| Appreciation, resale, ROI, "worth in X years" | 01, 02, 07, 03 |
| Rent, yield, tenant, rental offer | 01, 02, 07 |
| Location comparison, why FD, commute | 01, 02, 03 |
| Personal context (job, family, location shared) | 01, 02, 05 |
| Objection-like language (concern, worry, catch) | 01, 02, 06 |
| Booking intent ("I want to book") | 01, 02 (minimal) |
| Default / uncertain | 01, 02 |

### Caching
Cache the system prompt and loaded KBs per session — only re-classify on topic shifts.

### When to refactor
If a single conversation covers 5+ topics, context window pressure will force smarter chunk-level retrieval (RAG). Design for this by treating KBs as retrievable documents from day one, not hardcoded strings.

---

## 5. DYNAMIC MARKET PULSE (cross-conversation learning)

The system prompt has a placeholder for `<dynamic_market_pulse>` injection. Here's how to populate it.

### Daily aggregator job (runs 6 AM daily)

```sql
-- What topics trended in the last 24h
SELECT
  jsonb_array_elements_text(conversation_intelligence->'topics_user_engaged_with') AS topic,
  COUNT(*) AS mentions
FROM conversation_signals
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY topic
ORDER BY mentions DESC
LIMIT 5;

-- What objections are rising
SELECT
  jsonb_array_elements_text(objection_surface) AS obj,
  COUNT(*) AS mentions
FROM conversation_signals
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY obj
ORDER BY mentions DESC
LIMIT 3;

-- What personas are trending (parse traits)
-- Compare 24h vs 7d baseline to find surges
```

### Format injected into prompt

```xml
<dynamic_market_pulse>
Today's conversation patterns (last 24h, aggregate):
- Top topics: rental_offer_mechanics, bhfl_vs_other_banks, kokapet_comparison
- Rising objection: "price seems high vs Kokapet" (up 32% vs 7-day baseline)
- Persona surge: NRI returning buyers (up 41% — possibly driven by H1B cycle)
- Competitor mentions surge: Nova by Raghava (up 67%)
</dynamic_market_pulse>
```

### How the bot uses it
The system prompt §9 instructs the bot to reference this naturally when relevant:
> *"A lot of people are asking this exact question this week — here's why..."*

This creates **genuine cross-conversation learning without retraining**. It also gives sales real-time visibility into market sentiment shifts.

### Privacy note
The pulse is aggregate-only. No individual buyer data, no PII. Safe to include in every session's prompt.

---

## 6. FRONTEND ARTIFACT RENDERER REQUIREMENTS

The bot emits artifact calls like `render_artifact: rental_offer` with optional params (e.g., `unitId`, `salaryLakh`, `existingEmi`). The frontend must handle **all** of these:

| Artifact kind | What frontend must render |
|---------------|---------------------------|
| `project_comparison` | Side-by-side table: Loft vs mentioned competitors, key stats |
| `trends` | FD appreciation chart, GCC timeline, TDR cost table |
| `rental_offer` | ₹85K/month math card with entry/net-effective calculations |
| `amenity` | Amenity grid with clubhouse + outdoor zones |
| `master_plan` | Interactive 26-zone site plan |
| `unit_plans` | 1695/1870 floor plans toggleable |
| `unit_detail` | Specific unit (floor, view, availability) |
| `finance` | BHFL vs Other Banks payment structure |
| `affordability` | EMI calculator pre-filled with user's salary/EMI |
| `schools` | School map within 5/10/15 min |
| `commute` | Drive-time grid to Google/Apple/Amazon/Microsoft etc. |
| `why_fd` | FD fortress visual — GCC density, TDR, appreciation |
| `resale_framework` | **NEW** — analytical dashboard (see KB-07 §8) |
| `visit` | Site visit booking flow |
| `share_request` | Download brochure / callback form |
| `none` | No artifact — pure text reply |

### Rule for frontend
Every artifact is a React component. Components live in `/components/artifacts/`. Each receives props from the bot's artifact call. If `render_artifact: none` is emitted, hide the artifact panel entirely.

---

## 7. MEMORY & CONVERSATION CONTINUITY

### In-session memory (live)
The full conversation history is sent to the LLM on every turn. This is mandatory. Never truncate. If context pressure rises past 80% of limit, trigger a summary-compaction step (not a truncation) — preserve the signal payload and the user's declared facts verbatim.

### Cross-session memory (future feature)
Currently not implemented. If you add it later:
- Store the final signal payload per conversation in `conversation_signals` (already done).
- On new session from the same user (email/phone match), inject the last signal's `traits_observed` and `key_facts_extracted` into the system prompt under a `<prior_session_context>` tag.
- The bot's rule (§11 edge cases): *"Returning user claiming prior conversation: be honest about no memory"* — update this when cross-session memory is live.

### Hard rule against drift
System prompt §1 rule 11 requires re-reading the full conversation at the top of every reply. This isn't optional. **If the model drifts** (re-asks something the user already answered), it's a prompt failure. Monitor drift rate as a quality metric: % of conversations where the bot re-asks an answered question. Target: <3%.

---

## 8. MONITORING & QUALITY GATES

### Must-watch metrics (Week 1 of production)

| Metric | Target | Alert at |
|--------|--------|----------|
| Signal parse success rate | >99.5% | <98% |
| Avg response time | <4s | >6s |
| Drift rate (re-asking answered questions) | <3% | >5% |
| Hot-lead rate (RTB≥7 in last signal) | Benchmark, track trend | — |
| Site visit booking rate (RTB≥8 → visit artifact) | Benchmark | — |
| User tone escalation (hostile flag) | <0.5% | >1% |
| Sensitive emotional flag | Track | — |
| Edge case breakdown | Distribution | Skew changes |

### Sales team feedback loop
At the end of Week 1, interview 5 sales execs on:
1. *"Is the briefing useful before you dial?"*
2. *"Is the traits list accurate?"*
3. *"What are you reading in the chat that the briefing missed?"*
4. *"What's wrong about the lead quality scoring?"*

Iterate the signal schema based on Sales answers. The bot exists to serve sales — if sales isn't using the briefing, the system isn't working no matter how clever the bot is.

### Red flags in conversations to review manually
- Conversations where `rtb_score` dropped by 3+ points within a session — something the bot said turned them off
- Conversations where `edge_case_flag: sensitive_emotional` fired and the next reply still had persuasion language — major safety issue
- Conversations where the user shared salary/personal info and it was echoed back in subsequent turns — PII violation
- Conversations where the bot promised a specific appreciation number — RERA compliance violation, escalate immediately

---

## 9. DEPLOYMENT CHECKLIST (pre-launch)

- [ ] Signal stripper middleware deployed and tested (regex covers multiline JSON)
- [ ] CRM ingest endpoint live with Postgres schema + indexes
- [ ] Sales dashboard reads from `conversation_signals` table
- [ ] All 13 artifact components rendered correctly on frontend (including new `resale_framework`)
- [ ] KB lazy-loading router tested end-to-end
- [ ] Dynamic market pulse aggregator SQL written (can ship without it; add in Week 2)
- [ ] Monitoring dashboards for signal parse rate, response time, drift rate
- [ ] Error alerting on signal parse failures
- [ ] PII echo detection (did the bot repeat a phone number in turn N+2?)
- [ ] Compliance scanner: flag any reply containing "guaranteed X%" or "will appreciate" language
- [ ] Sales team trained on reading the `briefing` field and using the RTB score
- [ ] Fallback: if LLM fails or returns malformed output, a graceful "let me connect you with a human" message
- [ ] Rate limiting on the endpoint (abuse / prompt-injection flood protection)
- [ ] Conversation history storage (mandatory for cross-session memory and analytics)
- [ ] TS-RERA link live in artifacts that reference RERA
- [ ] `share_request` artifact tested end-to-end — buyer gets actual brochure in email

---

## 10. SCALING TO 1L VISITORS/DAY

Back-of-envelope:
- 100,000 visitors × ~30% start a conversation = ~30,000 conversations/day
- Avg 10 turns per conversation = ~300,000 LLM calls/day
- Avg ~3,000 input tokens + ~600 output tokens per call = ~1B tokens/day

### Cost levers
1. **Lazy KB loading (§4)** — 40-60% token reduction
2. **Cheaper router model** for KB classification (e.g., 3B-parameter local or Haiku-class API)
3. **Cache the system prompt** — if using Anthropic API, enable prompt caching (the system prompt + KBs are large and repeated)
4. **Conversation summarization** — after 15 turns, compact older turns into a summary + preserve signal payload
5. **Batch signal writes to CRM** — 100 signals per batch, 200ms intervals, vs single-row inserts

### Latency levers
1. Stream responses to frontend as they generate (most LLM APIs support this)
2. Render artifact skeleton immediately; populate from backend async
3. Async CRM write (don't block response delivery)
4. Pre-warm KB vectors if you move to RAG later

### Availability
- Deploy behind a load balancer; autoscale the Node middleware
- LLM failover: if primary model fails, fall back to secondary with the same system prompt
- Circuit breaker: if CRM write queue is lagging >30s, drop signals to dead-letter queue (DO NOT block replies)

---

## 11. OWNERSHIP & UPDATE CADENCE

| File | Owner | Update When |
|------|-------|-------------|
| 01_system_prompt.md | Head of Growth + Head of Sales | Behavioural tweaks; quarterly review |
| 02_kb_project_loft.md | Sales Ops | Pricing or inventory change |
| 03_kb_market_intelligence.md | Market Research | Quarterly (Q1/Q2/Q3/Q4) |
| 04_kb_competitive_landscape.md | Growth | Monthly (new launches, competitor news) |
| 05_kb_persona_playbook.md | Sales + Growth | Quarterly (as new personas emerge) |
| 06_kb_objection_library.md | Sales | Continuously (every new real objection) |
| 07_kb_resale_framework.md | Legal + Growth | Only when market data shifts materially |
| 08_deployment_guide.md | Engineering | Version-controlled with code |

**Rule:** Never let sales/marketing edit the system prompt without behavioural review. Never let engineering edit the KBs without sales sign-off. Separation of concerns is what lets this scale.

---

## 12. KNOWN UNKNOWNS / OPEN QUESTIONS

These are issues to confirm with stakeholders before locking v1:

1. **Maintenance charge discrepancy:** KB-02 cites ₹100/sqft (legacy doc) vs ₹108/sqft (pricing sheet). Sales needs to confirm which is current.
2. **Live inventory counts:** The bot avoids citing exact unit availability (it routes `share_request`). Confirm the CRM endpoint has live inventory access for the sales dashboard.
3. **Rental offer payout mechanics:** Monthly, quarterly, or lump-sum? KB-02 implies monthly. Confirm legal language.
4. **Visit slot booking:** Is the `visit` artifact connected to a real calendar, or does it create a sales task? Week 1 scope question.
5. **Channel partner detection:** The bot flags suspected brokers (edge_case_flag). Confirm how sales routes these — separate CP team or standard flow.
6. **Language support:** Does the bot need to handle Telugu or Hindi responses in v1, or English + Hinglish only?
7. **Cross-session memory:** Building it? If yes, needs phone/email unique identifier tied to conversation_id.

---

## 13. WHAT HAPPENS WHEN THIS SYSTEM FAILS (AND HOW TO RECOVER)

**Failure mode: Bot hallucinates a number.**
Detection: compliance scanner in production flags any numeric claim not present in KBs. Response: auto-retry with stricter prompt ("only cite facts from loaded KBs"). If still failing, fallback reply: *"Let me have an executive confirm that for you"* + route to share_request.

**Failure mode: Bot contradicts earlier conversation.**
Detection: drift rate monitor. Response: prompt engineering update — strengthen §1 rule 11 wording. Retrain sales on flagging drift manually.

**Failure mode: Bot becomes abusive or off-topic during a jailbreak attempt.**
Detection: sentiment + topic drift monitors. Response: §11 edge case protocols are the first line. Second line: conversation termination with graceful handoff to sales@asbl.in.

**Failure mode: Signal JSON malformed.**
Detection: parse failure rate monitor. Response: log the raw output, fallback to empty signal, flag conversation for engineering review. Don't block user reply.

**Failure mode: Sales team stops using the briefing field.**
Detection: weekly feedback loop. Response: rewrite the `briefing` instruction in the system prompt with examples from sales' own best pre-call notes. This is the *most important* product metric — if sales stops using it, the whole system is just expensive chat.

---

## 14. FINAL NOTE

This system is not a bot. It's a product that happens to converse. The conversation is the acquisition surface; the signal payload is the B2B product sales actually consumes. Build and monitor accordingly.

The bot's job is not to close the deal. The bot's job is to advance the buyer's thinking *and* hand sales a perfect briefing. If both jobs happen on every turn, the system works. If either fails, fix it fast.
