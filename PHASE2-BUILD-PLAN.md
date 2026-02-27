## Phase 2 Build Plan — Quotes, Scheduling, Notifications

**Goal:** Evolve the Phase 1 SMS assistant from “LLM-only small talk” into a **stateful junk-removal agent** that:

- Generates structured quotes using your pricing model.
- Tracks conversation / job state (INTAKE → QUOTED → BOOKED).
- Schedules pickups against a simple availability model.
- Notifies the provider when a quote is accepted or a job is booked.

This plan assumes we **keep the existing stack**:

- Python 3.11+, FastAPI, uvicorn.
- Twilio SMS.
- Anthropic Claude (Haiku for speed, Sonnet as an option).
- DynamoDB as the single backing store.

---

## 1. Phase 2 Scope (In Scope)

| # | Deliverable | Description |
|---|-------------|-------------|
| 1 | **Conversation state machine** | Track per-phone job status: `NEW → INTAKE → ITEMS_CONFIRMED → QUOTED → SCHEDULING → BOOKED`. |
| 2 | **Structured quote engine** | Implement a concrete pricing function (tiers + modifiers) that returns a structured quote object the LLM can present. |
| 3 | **Quote tool for LLM** | Add a “tool calling” style API in the backend: LLM requests quote computation; backend returns structured results. |
| 4 | **Scheduling module (simple)** | Implement a minimal availability model (e.g. fixed daily time windows or a small table of slots) and booking creation. |
| 5 | **Provider notifications** | On QUOTED and BOOKED, send a concise SMS (and optionally email) summary to the provider. |
| 6 | **Quiet hours + rate limiting (basic)** | Block/snooze non-critical outbound SMS during quiet hours and avoid rapid-fire message loops. |
| 7 | **Data model upgrade** | Extend the Phase 1 DynamoDB item schema to include status, quote, and booking fields. |
| 8 | **Observability hooks** | Add minimal logging/metrics for quotes, bookings, and provider notifications to support debugging. |

**Out-of-scope for Phase 2 (intentionally):**

- Full-blown calendar integration (Google Calendar / Calendly) — placeholder implementation only.
- MMS / photo analysis and vision models (kept for Phase 3).
- Multi-tenant or multi-provider routing.
- Web dashboard / UI.

---

## 2. Assumptions & Open Questions

**Assumptions (can revise later):**

- **Service area:** Single metro area with roughly similar travel times; no per-zip pricing differences yet.
- **Truck size:** Treat 1 “truck” as ~12 cubic yards for fraction-of-load estimates.
- **Pricing baseline:** Use the example tiers from `sms-junk-removal-agent-plan.md` (Small/Medium/Large/XL) and modifiers table as the starting point.
- **Scheduling model:** Simple availability windows (e.g. “Today/Thu/Fri: 9–12, 1–4”) stored in a config or small DynamoDB table.
- **Provider notifications:** Start with **SMS-only** to a single provider phone number; email is optional / later.

**Questions for you (no need to block implementation, we can default now and tune later):**

- **Q1 — Pricing:** Do you want **fixed prices** per tier (e.g. Medium = $200) or **ranges** (e.g. $175–$225) in Phase 2?
- **Q2 — Scheduling:** For now, is a simple “we offer 2 windows per weekday” model OK, or do you want to feed in actual calendar events from Google/Calendly before Phase 3?
- **Q3 — Provider contact:** What phone number should we treat as the **provider notification target**? (We’ll wire this as an env var like `PROVIDER_PHONE_NUMBER`.)
- **Q4 — Quiet hours:** What local time window should count as “quiet hours” (e.g. **21:00–08:00**)?

Where you don’t answer yet, we will:

- Use **price ranges**.
- Implement **fixed per-day time windows** in configuration.
- Use a single provider phone in env.
- Default quiet hours to **21:00–08:00 local**.

---

## 3. Architecture Changes (Delta from Phase 1)

**Phase 1 recap:**

- `POST /api/sms/inbound`:
  - Parses Twilio payload, validates signature when configured.
  - Stores user message in DynamoDB (`sms_conversations`).
  - Sends entire conversation to Claude, gets a free-form reply.
  - Stores assistant message, sends SMS reply via Twilio.

**Phase 2 deltas:**

- Introduce a **lightweight state + job model** layered on top of the existing DynamoDB item.
- Add a **backend quote function** that:
  - Takes a structured description of items + modifiers.
  - Returns a `Quote` object (with tier, estimated truck fraction, price or range, and rationale).
- Add a **backend scheduling module** that:
  - Knows current “open slots”.
  - Given a requested date/time window, checks availability and returns a slot or an error.
- Extend the LLM integration so it can:
  - Call backend “tools” (quote, schedule, escalate).
  - Render natural-language replies based on those tool results.

We will **not** expose tool calling directly to Twilio; it stays internal between our backend and the LLM client.

---

## 4. Data Model Changes (DynamoDB)

Phase 1 DynamoDB item (per phone number) looks like:

```text
PK: customer_phone (S)
messages: L[ M{ role:S, content:S, ts:S } ]
updated_at: S (ISO8601)
```

**Phase 2 extensions (same item, same table):**

- `status` (S): One of `NEW`, `INTAKE`, `ITEMS_CONFIRMED`, `QUOTED`, `SCHEDULING`, `BOOKED`, `COMPLETED`, `CANCELLED`.
- `items` (L of M): Structured list of items with classification and estimated volume, e.g.:
  - `[{ name, category, quantity, est_cubic_yards }]`
- `quote` (M): Last computed quote:
  - `amount_min` (N), `amount_max` (N), `tier` (S), `est_truck_fraction` (N), `currency` (S, default `USD`).
- `scheduled_at` (S): ISO8601 timestamp or time-window token (e.g. `2026-03-01T13:00:00-08:00` or `2026-03-01T13:00-16:00`).
- `address` (S): Service address text.
- `access_notes` (S): Free-text notes for the crew.
- `provider_notified_at` (S, optional): Last time we notified the provider about this job.

**Implementation tasks:**

- Update `conversation.py` helpers or add new ones to:
  - Read/write `status`, `items`, `quote`, `scheduled_at`, `address`, `access_notes`.
  - Maintain backward compatibility: Phase 1 conversations without these fields still work.

---

## 5. Quote Engine (Backend Function)

Implement a dedicated module, e.g. `src/sms_webhook/quote_engine.py`, that exposes:

- `classify_items(raw_text: str | list[dict]]) -> list[Item]`
  - Phase 2: acceptable to have the LLM propose a structured list, we then normalize.
- `compute_quote(items: list[Item], modifiers: QuoteModifiers) -> Quote`

**Key responsibilities:**

- Map items into **tiers** (Small/Medium/Large/XL) based on example table.
- Approximate **total volume** in cubic yards and fraction of truckload.
- Apply **modifiers** (stairs, distance from truck, curbside discount, hazardous items, same-day).
- Return a **stable, deterministic quote** given structured inputs.

**Implementation notes:**

- Keep all pricing logic **server-side**, not just in the prompt.
- Represent prices in cents (integers) internally, format to dollars when rendering.
- Add unit tests that:
  - Given a set of items and modifiers, assert on the computed quote range and tier.

---

## 6. LLM “Tool Calling” Integration

Phase 2 should give the LLM **structured knobs** instead of pure free text:

- Define internal “tools” that the LLM can conceptually invoke:
  - `generate_quote(conversation_state) -> quote`
  - `check_availability(desired_date_range) -> slots`
  - `book_appointment(slot, address, notes) -> confirmation_id`

Implementation approach (pragmatic for Phase 2):

- Keep using the Anthropic Python client with a **system prompt** describing:
  - Conversation phases.
  - The existence and purpose of our tools.
  - A JSON-like schema for tool inputs/outputs.
- Have the LLM respond in **JSON envelopes** when it wants a tool call, e.g.:

```json
{ "action": "GENERATE_QUOTE", "payload": { "items": [...], "modifiers": {...} } }
```

- The backend:
  - Detects when the reply is a tool request.
  - Runs the corresponding Python function(s).
  - Feeds results back to the LLM for final natural-language response.

**Tasks:**

- Update `llm.py` to:
  - Support a “tool call” style response format (with simple JSON envelopes).
  - Provide helper(s) to extract either a plain-text reply or a tool invocation.
- Update system prompt to encode:
  - **Phase transitions** (when to go from INTAKE → QUOTED → SCHEDULING).
  - The structure of `items`, `quote`, and `booking` objects.

---

## 7. Scheduling Module (Simple)

Phase 2 will use a **simple availability model**, not a full calendar integration.

**Option A (config-based, default):**

- Hard-code weekly availability in a small config or env var (e.g. “Mon–Fri, 9–12 and 13–16”).
- Scheduling module:
  - Given a requested day, pick the next open slot.
  - Ensure we don’t overbook (e.g. max N jobs per slot per day).
  - Return a slot descriptor and store it in DynamoDB (`scheduled_at`).

**Option B (DynamoDB-backed slots):**

- Create a small `availability` table keyed by date, with a list of open slots.
- For Phase 2 we can keep this optional and default to Option A.

**Tasks:**

- Implement `scheduler.py` with:
  - `list_slots(preferences) -> list[Slot]`
  - `book_slot(conversation, slot) -> Booking`
- Extend system prompt so the agent:
  - Asks for date/time preferences after quote acceptance.
  - Confirms the chosen window in natural language.

Later phases can swap the backend to Google Calendar / Calendly without changing the LLM-facing behavior.

---

## 8. Provider Notifications

On important state transitions (QUOTED, BOOKED), notify the provider.

**Phase 2 scope:**

- SMS notification via Twilio to a `PROVIDER_PHONE_NUMBER` env var.
- Optional: log/email for later investigation, but not required.

**Notification contents:**

- Customer phone.
- Status (`QUOTED` or `BOOKED`).
- Address (if known).
- Quote range and estimated truck fraction.
- Scheduled time window (if BOOKED).

**Implementation tasks:**

- Add env var: `PROVIDER_PHONE_NUMBER=+1...`.
- Implement `notifications.py`:
  - `notify_quote(conversation)`
  - `notify_booking(conversation)`
- Wire notifications from the state machine so they fire once per relevant state change.

---

## 9. Quiet Hours & Rate Limiting (Basic)

To avoid spamming customers and to align with compliance guidelines:

- **Quiet hours:** Default to **21:00–08:00 local**.
  - During quiet hours:
    - Still accept inbound messages and update state.
    - Send a single polite “we’ll respond in the morning” reply on first message.
    - Defer non-essential outbound notifications until quiet hours end.
- **Rate limiting:**
  - Avoid sending more than **1 agent message** for every **1 customer message** within a short window.
  - Avoid sending more than **X messages per conversation per day** (configurable).

Implementation details:

- Implement helper in a new module (e.g. `throttling.py`) that:
  - Given the conversation history and current timestamp, decides whether a full reply is allowed.
  - Returns either:
    - `ALLOW_FULL_REPLY`
    - `ALLOW_THROTTLED_REPLY` (e.g. short “we got your message”)
    - `BLOCK_REPLY`

---

## 10. Implementation Tasks (Checklist)

**Data & state:**

- [ ] Extend DynamoDB item schema and `conversation.py` helpers with `status`, `items`, `quote`, `scheduled_at`, `address`, `access_notes`.
- [ ] Add simple state machine helpers (e.g. `get_status`, `set_status`, convenience methods like `mark_quoted`, `mark_booked`).

**Quote engine:**

- [ ] Create `quote_engine.py` with `compute_quote` + tests based on the tier/modifier tables.
- [ ] Update `llm.py` prompt and parsing to support tool-like requests for quotes.

**Scheduling:**

- [ ] Implement `scheduler.py` with config-driven availability and booking.
- [ ] Integrate scheduling into the LLM flow after a quote is accepted.

**Notifications:**

- [ ] Add `PROVIDER_PHONE_NUMBER` env var and `.env.example` documentation.
- [ ] Implement `notifications.py` and wire it to status transitions.

**Quiet hours / rate limiting:**

- [ ] Implement `throttling.py` and integrate into `sms_inbound` path.
- [ ] Add env/config for quiet hours window and daily message limits.

**Testing & validation:**

- [ ] Unit tests for quote engine and scheduler.
- [ ] End-to-end tests that simulate:
  - INTAKE → QUOTED → BOOKED via mocked LLM + Twilio.
- [ ] Manual test script to:
  - Send a synthetic conversation through the webhook.
  - Inspect resulting DynamoDB items and provider notifications.

---

## 11. Success Criteria (Phase 2)

- [ ] A customer can text in, describe items, and receive a **clear price range** with a brief breakdown.
- [ ] The system tracks and persists conversation **status** and **quote** in DynamoDB.
- [ ] After accepting a quote, the customer can choose a **time window**, and the system confirms a booking.
- [ ] The provider receives an SMS with job details whenever a quote is accepted or a job is booked.
- [ ] Quiet hours and basic rate limiting prevent spammy behavior while still acknowledging inbound messages.

Once these are in place, Phase 3 can focus on **MMS/vision, calendar integration, dashboards, and multi-provider support** without reworking the core conversational + data model.

