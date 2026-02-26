# SMS Junk Removal Agent — System Plan

## Overview

An AI-powered SMS conversational agent that handles inbound customer inquiries for a junk removal service. Customers text a Twilio number, and an LLM agent guides them through describing their junk, generates a quote, and schedules pickup — all via text message.

---

## 1. Architecture

```
Customer SMS → Twilio Number → Webhook (POST) → Application Server → LLM Agent
                                                                        ↓
                                                              Conversation Manager
                                                              (state + history)
                                                                        ↓
                                                              Quote Engine / Scheduler
                                                                        ↓
                                                              Twilio API → Reply SMS
```

### Core Components

| Component | Responsibility |
|---|---|
| **Twilio Phone Number** | Receive and send SMS messages |
| **Application Server** | Handle webhooks, route messages, manage sessions |
| **LLM Agent** | Conversational logic, item classification, quote generation |
| **Conversation Store** | Persist chat history and job state per phone number |
| **Quote Engine** | Pricing rules, volume/weight estimation |
| **Scheduling Module** | Availability windows, booking confirmation |
| **Notification Layer** | Alerts to service provider when a job is quoted/booked |

---

## 2. Twilio Setup

### Account & Number

1. Create a Twilio account at [twilio.com](https://www.twilio.com)
2. Purchase a phone number with SMS capability
3. Configure the **Messaging webhook** to point to your server endpoint:
   - URL: `https://your-domain.com/api/sms/inbound`
   - Method: `POST`
4. (Optional) Set up a status callback URL for delivery receipts

### Key Twilio Config

- **Messaging Service SID** — group numbers under a messaging service for scaling later
- **Opt-out handling** — Twilio provides built-in STOP/START keyword management (stay compliant with TCPA)
- **Rate limiting** — be aware of SMS throughput limits per number (~1 msg/sec for long codes, higher for short codes/toll-free)

### Twilio Environment Variables

```
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=xxxxxxxxxxxxxxxx
TWILIO_PHONE_NUMBER=+1XXXXXXXXXX
WEBHOOK_URL=https://your-domain.com/api/sms/inbound
```

---

## 3. Application Server

### Tech Stack (Recommended)

- **Runtime:** Node.js (Express) or Python (FastAPI/Flask)
- **Database:** PostgreSQL or SQLite (for conversation state + job records)
- **Queue:** Redis or BullMQ (for async LLM calls if latency is a concern)
- **Hosting:** Railway, Render, AWS Lambda + API Gateway, or a VPS

### Inbound Webhook Endpoint

```
POST /api/sms/inbound
```

**Twilio sends:**
- `From` — customer phone number
- `Body` — message text
- `MessageSid` — unique message ID
- `NumMedia` / `MediaUrl0` — if customer sends photos

**Server flow:**

1. Extract `From` and `Body` from the Twilio POST
2. Look up or create a **conversation session** keyed by phone number
3. Append the new message to conversation history
4. Send conversation context to the **LLM Agent**
5. Receive agent response (may include tool calls: quote, schedule, escalate)
6. Send reply via Twilio Messages API
7. Persist updated state

---

## 4. LLM Agent Design

### Model Selection

- **Primary:** Claude (via Anthropic API) or GPT-4o
- Use tool/function calling for structured actions (generate quote, book appointment, escalate)

### System Prompt — Core Responsibilities

The agent operates in a multi-phase conversational flow:

#### Phase 1: Intake & Item Discovery

- Greet the customer, explain the service
- Ask what they need removed (furniture, appliances, yard debris, construction waste, general household, etc.)
- Clarify quantities, sizes, and approximate weight
- Ask if items are inside (which floor?) or outside / curbside
- Ask for photos if descriptions are ambiguous (MMS support)
- Confirm the full list before moving to quoting

#### Phase 2: Quote Generation

- Classify items into pricing tiers (see Quote Engine below)
- Calculate estimated volume (fraction of a truckload)
- Apply modifiers (stairs, distance from truck, hazardous materials, etc.)
- Present the quote with a breakdown
- Handle negotiation or questions about pricing

#### Phase 3: Scheduling

- Present available time windows
- Confirm customer's preferred date/time
- Collect address and any access instructions
- Send confirmation summary

#### Phase 4: Post-Booking

- Send reminder 24 hours before
- Handle reschedule/cancellation requests
- Trigger follow-up for review after service completion

### Agent Tools (Function Calls)

| Tool | Input | Output |
|---|---|---|
| `classify_items` | Item descriptions | Categorized list with volume estimates |
| `generate_quote` | Categorized items, location modifiers | Price range or fixed quote |
| `check_availability` | Preferred date range, service area | Available time slots |
| `book_appointment` | Date/time, address, customer phone, job details | Confirmation ID |
| `escalate_to_human` | Reason, conversation summary | Notification to provider |
| `send_photo_request` | — | Prompt customer for MMS image |

### Conversation State Machine

```
NEW → INTAKE → ITEMS_CONFIRMED → QUOTED → SCHEDULING → BOOKED → COMPLETED
                                    ↓
                               NEGOTIATING
                                    ↓
                            ESCALATED_TO_HUMAN
```

### Guardrails

- Max 3 unanswered follow-ups before escalating to human
- Detect off-topic messages and gently redirect
- Never commit to a price the business can't honor — use ranges when uncertain
- If the job sounds large (e.g., full estate cleanout), escalate for an in-person estimate
- Respect quiet hours — don't send automated replies between 9 PM and 8 AM local time

---

## 5. Quote Engine

### Pricing Model (Example — Customize to Your Business)

| Tier | Description | Example Items | Est. Price Range |
|---|---|---|---|
| **Small** | Single item, light | Chair, microwave, bags of trash | $50–$100 |
| **Medium** | A few items or one large item | Couch, mattress, dresser | $100–$250 |
| **Large** | Partial truckload | Room cleanout, multiple furniture | $250–$450 |
| **XL** | Full or near-full truckload | Garage cleanout, estate | $450–$800+ |

### Modifiers

| Modifier | Adjustment |
|---|---|
| Stairs (per flight) | +$25–$50 |
| Inside carry (long distance) | +$25 |
| Hazardous / special disposal (paint, tires, e-waste) | +$30–$75 per item |
| Same-day service | +20% |
| Curbside (no carry needed) | −10% |

### Volume Estimation Heuristic

The LLM should map item descriptions to approximate cubic yards and sum them against truck capacity (typically 10–15 cubic yards for a standard junk truck). Provide the customer a fraction-of-truck estimate for transparency.

---

## 6. Scheduling Module

### Options

- **Simple:** Google Calendar API integration — check availability, create events
- **Moderate:** Calendly or Cal.com API — let the system query open slots
- **Custom:** Internal availability table in the database with provider-managed windows

### Required Data per Booking

- Customer phone number
- Service address
- Scheduled date and time window
- Job summary (items, estimated volume, quote amount)
- Access instructions
- Confirmation ID (generated)

---

## 7. Service Provider Notifications

When a job is quoted or booked, notify the provider via:

- SMS to provider's phone (via Twilio)
- Email summary (via SendGrid, SES, or similar)
- Dashboard entry (if a web UI is built later)
- Slack/Discord webhook (lightweight option)

**Notification should include:** customer phone, address, job summary, quote, scheduled time, and a link to the full conversation transcript.

---

## 8. Data Model (Simplified)

```
conversations
├── id (UUID)
├── customer_phone (string, indexed)
├── status (enum: new, intake, quoted, booked, completed, cancelled)
├── messages (JSONB array of {role, content, timestamp})
├── items (JSONB array of classified items)
├── quote_amount (decimal, nullable)
├── scheduled_at (timestamp, nullable)
├── address (string, nullable)
├── access_notes (text, nullable)
├── created_at (timestamp)
└── updated_at (timestamp)
```

---

## 9. MMS / Photo Support

Twilio supports inbound MMS. When a customer sends a photo:

1. Twilio includes `NumMedia` and `MediaUrl0..N` in the webhook payload
2. Download the image from the media URL
3. Pass it to the LLM as a vision input (Claude and GPT-4o both support image analysis)
4. Use the image to better classify items, estimate volume, and identify anything requiring special disposal

This is a major UX advantage — "Just text us a photo of what you need gone."

---

## 10. Compliance & Legal

- **TCPA Compliance:** Only message customers who initiate contact; honor STOP requests (Twilio handles this automatically)
- **Data Retention:** Define a policy for how long you retain conversation data and phone numbers
- **Opt-in Language:** First reply should include opt-in/opt-out language, e.g., "Reply STOP at any time to unsubscribe"
- **Pricing Transparency:** Quotes should clearly state they are estimates unless confirmed by the provider
- **A2P 10DLC Registration:** Register your Twilio number for A2P messaging to avoid carrier filtering (required for US long codes)

---

## 11. Development Phases

### Phase 1 — MVP (Weeks 1–3)

- [ ] Twilio account + phone number setup
- [ ] Webhook server with basic inbound/outbound SMS
- [ ] LLM integration with system prompt and conversation memory
- [ ] Simple keyword-based quoting (no tool calls yet)
- [ ] Manual scheduling (agent tells customer "we'll call to confirm")
- [ ] Provider notification via SMS

### Phase 2 — Smart Agent (Weeks 4–6)

- [ ] Tool/function calling for structured quoting
- [ ] Conversation state machine with phase tracking
- [ ] Photo/MMS intake and vision analysis
- [ ] Automated scheduling with calendar integration
- [ ] Quote modifiers and volume estimation logic
- [ ] Quiet hours and rate limiting

### Phase 3 — Polish & Scale (Weeks 7–10)

- [ ] Provider-facing dashboard (view jobs, adjust availability, override quotes)
- [ ] Customer follow-up flows (reminders, review requests)
- [ ] Analytics (conversion rate, avg quote, response time)
- [ ] Multi-provider routing (if scaling to multiple crews)
- [ ] A2P 10DLC registration and compliance audit
- [ ] Load testing and error handling hardening

---

## 12. Cost Estimates

| Item | Cost |
|---|---|
| Twilio phone number | ~$1.15/month |
| Twilio SMS (send + receive) | ~$0.0079/msg each way |
| Twilio MMS (receive) | ~$0.01/msg |
| LLM API (Claude/GPT-4o) | ~$0.01–$0.05 per conversation turn |
| Hosting (small server) | $5–$25/month |
| **Estimated cost per completed booking** | **~$0.50–$2.00** |

---

## 13. Sample Conversation

```
CUSTOMER: Hi, I need to get rid of some stuff from my garage
AGENT: Hey! 👋 I can help with that. What kind of items are you looking
       to have removed? (furniture, appliances, yard waste, general junk, etc.)
CUSTOMER: An old couch, a broken treadmill, and about 10 bags of random junk
AGENT: Got it — here's what I have so far:
       • 1 couch
       • 1 treadmill
       • ~10 bags of misc junk
       Is that everything, or is there more? Also, is this all in the
       garage with ground-level access?
CUSTOMER: That's it. Yeah ground level, garage door opens to the driveway
AGENT: Perfect, easy access — no stair fees. Here's your estimate:

       🧾 Quote: $175 – $225
       - Couch + treadmill: ~$120
       - 10 bags misc: ~$75
       - Ground-level access: no surcharge

       This covers loading, hauling, and disposal. Want to lock in a
       pickup time? We have openings this Thu and Fri afternoon.
CUSTOMER: Thursday works
AGENT: Great! I have Thursday 1–3 PM available. Can you confirm your
       address and any gate codes or access notes?
CUSTOMER: 1234 Oak St, Portland OR 97201. No gate, just pull into the driveway.
AGENT: You're all set! ✅

       📋 Booking #JR-0042
       📍 1234 Oak St, Portland OR 97201
       📅 Thursday, 1:00–3:00 PM
       💰 Est. $175–$225 (final price confirmed on-site)

       We'll send a reminder tomorrow. Reply HELP for questions or
       STOP to opt out of messages.
```

---

## Next Steps

1. **Decide on tech stack** (Node vs Python, hosted vs serverless)
2. **Create Twilio account** and purchase a number
3. **Draft the full system prompt** for the LLM agent with your specific pricing, service area, and business rules
4. **Build the webhook MVP** and test end-to-end with your own phone
5. **Iterate on the prompt** based on real conversation testing
