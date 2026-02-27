# Service Scheduler — SMS Junk Removal Agent

Phase 1: receive an SMS at a Twilio number and respond via an LLM (Claude). No quoting or scheduling yet.

**All commands below are run from the `application` directory** (one level below the repo root).

## Setup

1. **Python 3.11+** and a virtualenv:

   ```bash
   cd application
   python3 -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Environment:**

   ```bash
   cp .env.example .env
   # Edit .env: set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER, ANTHROPIC_API_KEY
   # Optional: ANTHROPIC_MODEL (default claude-sonnet-4-20250514; use claude-3-5-haiku-latest for faster/cheaper)
   # Optional: DYNAMODB_TABLE_NAME, AWS_REGION (or use DynamoDB Local; see below)
   ```

3. **DynamoDB:**

   - **Option A — AWS:** Create a table in the AWS console (or via IaC):
     - Table name: `sms_conversations` (or set `DYNAMODB_TABLE_NAME`)
     - Partition key: `customer_phone` (String)
     - No sort key. Set `AWS_REGION` in `.env`.
   - **Option B — Local:** Run DynamoDB Local (e.g. `docker run -p 8000:8000 amazon/dynamodb-local`) and set in `.env`:
     - `DYNAMODB_ENDPOINT_URL=http://localhost:8000`
     - Create the table with the same schema (e.g. using `aws dynamodb create-table` against the local endpoint).

## Run locally

```bash
cd application
source .venv/bin/activate
uvicorn src.sms_webhook.main:app --reload --port 8000
```

- Health: [http://localhost:8000/health](http://localhost:8000/health)
- Webhook: `POST http://localhost:8000/api/sms/inbound` (Twilio will call this).

## Expose to Twilio (ngrok)

1. Install [ngrok](https://ngrok.com/download).
2. Run: `ngrok http 8000`
3. Copy the HTTPS URL (e.g. `https://abc123.ngrok.io`).
4. In Twilio Console → Phone Numbers → your number → Messaging:
   - **Webhook URL:** `https://abc123.ngrok.io/api/sms/inbound`
   - Method: POST
5. Optional (signature validation): set in `.env`:
   - `TWILIO_WEBHOOK_URL=https://abc123.ngrok.io/api/sms/inbound`
   So that the webhook validates Twilio’s request signature. Update this if the ngrok URL changes.

Text your Twilio number; you should get a reply from the assistant.

## Tests

```bash
cd application
pip install -r requirements.txt
pytest tests/ -v
```

Tests mock Twilio and Anthropic; no real credentials or DynamoDB needed for `tests/test_inbound.py`. For tests that hit DynamoDB, use a local table or a test table in AWS.

## Project layout (Phase 1)

- `src/sms_webhook/main.py` — FastAPI app, `POST /api/sms/inbound`
- `src/sms_webhook/twilio_handler.py` — Parse payload, validate signature, send SMS
- `src/sms_webhook/conversation.py` — DynamoDB read/write (last N messages per phone)
- `src/sms_webhook/llm.py` — Anthropic Claude, system prompt, single reply

## Lighter / faster model

Set in `.env`:

```bash
ANTHROPIC_MODEL=claude-3-5-haiku-latest
```

for lower latency and cost; Sonnet 4 remains the default for best quality.

## Deploy to AWS (Lambda)

- Use **Mangum** to run the FastAPI app as the Lambda handler.
- API Gateway (HTTP or REST) routes `POST /api/sms/inbound` to that Lambda.
- Create the DynamoDB table (e.g. SAM/CDK/Terraform); give the Lambda role read/write access.
- Put Twilio and Anthropic secrets in Secrets Manager or SSM and inject into the Lambda env.

See `../PHASE1-BUILD-PLAN.md` (in the repo root) for full Phase 1 scope and later phases.
# service-provider-poc
