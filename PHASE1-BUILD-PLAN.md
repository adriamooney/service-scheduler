# Phase 1 Build Plan — SMS In / SMS Out (Slim)

**Goal:** Receive a text message at a Twilio number and respond to it. No quoting, scheduling, or provider notifications yet. Later phases add the full lifecycle.

---

## Phase 1 Scope (In Scope)

| # | Deliverable | Description |
|---|-------------|-------------|
| 1 | **Webhook endpoint** | HTTP endpoint that accepts Twilio’s `POST` for inbound SMS (e.g. `POST /api/sms/inbound`). |
| 2 | **Parse Twilio payload** | Read `From`, `Body`, `MessageSid` from the request. Validate Twilio signature (recommended). |
| 3 | **Conversation context (minimal)** | Per `From` (phone number), keep the last N messages in DynamoDB so the LLM can respond in context. No state machine or phases. |
| 4 | **LLM response** | Send current message (and recent history) to Claude; get one reply. Use Claude Sonnet 4 (e.g. 4.5/4.6); document a lighter/faster model option for later. |
| 5 | **Send reply via Twilio** | Use Twilio Messages API to send the LLM reply back to `From`. |
| 6 | **Secrets & config** | Config via `.env` (or equivalent) for Twilio credentials and Anthropic API key. No multi-tenant provider config in Phase 1. |
| 7 | **Local dev** | Run webhook locally (e.g. Flask/FastAPI). Use ngrok (or similar) so Twilio can reach the endpoint; document in README. |
| 8 | **Deployable to AWS** | Structure so the same handler can run in **Lambda** behind API Gateway (serverless). Optional: Dockerfile for the handler for Lambda container image or future microservices. |

---

## Phase 1 Out of Scope (Later Phases)

- Quote engine, pricing tiers, modifiers  
- Scheduling, Google Calendar, Calendly  
- Provider notifications (email, calendar, SMS)  
- Multi-provider / multi-tenant (separate Twilio accounts or config)  
- MMS / photo handling  
- Conversation state machine (INTAKE → QUOTED → BOOKED, etc.)  
- Quiet hours, rate limiting, compliance (beyond basic Twilio validation)  
- Dashboard or admin UI  

---

## Tech Stack (Phase 1)

| Layer | Choice | Notes |
|-------|--------|--------|
| **Runtime** | Python 3.11+ | Aligns with your preference. |
| **Web framework** | FastAPI | Simple, async-friendly, easy to wrap for Lambda. |
| **Webhook handler** | Single app: `POST /api/sms/inbound` | Same code path for local and Lambda. |
| **LLM** | Anthropic Claude (Sonnet 4.x) | Primary model; document a smaller/faster model for optional use. |
| **Conversation store** | DynamoDB | One table: partition key = phone number (e.g. `customer_phone`); store last N messages (e.g. 20) as a list in one item. |
| **Secrets** | `.env` locally; AWS Secrets Manager or SSM + env for Lambda | No secrets in code. |
| **Deploy** | Lambda + API Gateway (HTTP API or REST) | Serverless; no long-lived server. |

---

## Data Model (Phase 1 Only)

**DynamoDB table: `conversations` (or `sms_conversations`)**

| Attribute | Type | Description |
|-----------|------|-------------|
| `customer_phone` (PK) | String | E.164 format (e.g. `+15035551234`). |
| `messages` | List of maps | `[{ "role": "user" \| "assistant", "content": "...", "ts": "ISO8601" }]`. Keep last 20 (or 10) turns. |
| `updated_at` | String (ISO8601) | Last activity. |

No `status`, `quote`, `scheduled_at`, or provider fields in Phase 1.

---

## Request Flow (Phase 1)

```
Twilio → POST /api/sms/inbound
    → Validate Twilio signature (optional but recommended)
    → Parse From, Body
    → Get conversation from DynamoDB (key = From); append user message
    → Trim messages to last N
    → Call Anthropic API (Claude) with system prompt + messages
    → Append assistant message to conversation; put back to DynamoDB
    → Twilio Messages API: send reply to From
    → Return 200 + empty TwiML (or 204)
```

---

## Project Layout (Phase 1)

```
service-scheduler/
├── application/                  # Phase 1 app (all below)
│   ├── .env.example              # TWILIO_*, ANTHROPIC_API_KEY, etc.
│   ├── README.md                 # Setup, local run, ngrok, env vars
│   ├── requirements.txt          # fastapi, uvicorn, twilio, anthropic, boto3
│   ├── Dockerfile                # Optional: for Lambda container or later
│   ├── src/
│   │   └── sms_webhook/
│   │       ├── __init__.py
│   │       ├── main.py           # FastAPI app; route POST /api/sms/inbound
│   │       ├── twilio_handler.py # Parse payload, validate signature, send reply
│   │       ├── conversation.py  # DynamoDB read/write, message trim
│   │       └── llm.py            # Anthropic client, system prompt, single reply
│   ├── tests/
│   │   └── test_inbound.py      # Unit tests for parse + mock LLM + mock Twilio
│   └── scripts/
│       └── create_table.py      # Create DynamoDB table (local or AWS)
├── PHASE1-BUILD-PLAN.md
└── template.yaml                 # Optional: SAM or CDK (repo root or in application/)
```

---

## System Prompt (Phase 1)

Keep it minimal: identify as a junk-removal SMS assistant, greet and ask what they need removed. No quoting or scheduling logic; the agent can say things like “We’ll get you a quote in a follow-up” so the flow still makes sense when we add Phase 2.

Example (short):

- You are an SMS assistant for a junk removal service. Be brief and friendly. Ask what they need removed and gather a short description. Do not give prices or book times yet; tell them we’ll follow up with a quote and scheduling options.

---

## LLM Model Choice

- **Primary:** Claude Sonnet 4 (e.g. `claude-sonnet-4-20250514` or latest 4.x).  
- **Lighter/faster option:** Claude Haiku (e.g. `claude-3-5-haiku-latest`) for lower latency and cost; document in README and make model name configurable via env (e.g. `ANTHROPIC_MODEL`).

---

## Local Development

1. Copy `.env.example` → `.env`; add Twilio credentials and `ANTHROPIC_API_KEY`.  
2. Run: `uvicorn src.sms_webhook.main:app --reload`.  
3. Expose with ngrok: `ngrok http 8000`; set Twilio webhook URL to `https://<ngrok-host>/api/sms/inbound`.  
4. For DynamoDB locally: use **DynamoDB Local** in Docker, or a small script to create the table in AWS and point `AWS_REGION` and table name via env.

---

## Deployment (Phase 1 — AWS)

- **Lambda:** One function that runs the FastAPI app via Mangum (or similar) so `POST /api/sms/inbound` is the handler.  
- **API Gateway:** HTTP API or REST API; route `POST /api/sms/inbound` to the Lambda.  
- **DynamoDB:** One table; create via IaC (SAM/CDK/Terraform) with `customer_phone` as partition key.  
- **Secrets:** Twilio and Anthropic keys in Secrets Manager or SSM; inject into Lambda env.  

No SQS/SNS in Phase 1; single synchronous request/response.

---

## Success Criteria (Phase 1)

- [ ] Sending an SMS to the Twilio number results in a reply within a few seconds.  
- [ ] Reply is from Claude and contextually relevant (e.g. asks what they need removed).  
- [ ] A second message from the same number gets a reply that uses prior context.  
- [ ] Webhook validates Twilio signature and returns 200/204.  
- [ ] Same code path runs locally and in Lambda.  

---

## What Comes Next (Later Phases)

- **Phase 2:** Quote engine (cost structure: $150 delivery + $50/hr/person), state machine, scheduling (Google Calendar + Calendly hooks), provider notifications (email via SES, calendar event, optional SMS).  
- **Phase 3:** Multi-provider/tenant (per-provider Twilio and cost config), dashboard, compliance (A2P 10DLC, data retention), analytics.  

Phase 1 is intentionally minimal: **receive SMS → LLM with minimal conversation store → send SMS**, so we can expand the lifecycle in later stages.
