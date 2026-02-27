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

   - **Option A — AWS DynamoDB:** Do **not** set `DYNAMODB_ENDPOINT_URL`. Set `AWS_REGION` in `.env` (e.g. `us-west-2`). Ensure AWS credentials are available (e.g. `aws configure` or `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` in `.env`). Then create the table:
     ```bash
     python scripts/create_table.py
     ```
     This creates table `sms_conversations` (or `DYNAMODB_TABLE_NAME`) with partition key `customer_phone` (String), on-demand billing.
   - **Option B — Local:** Run DynamoDB Local (e.g. `docker run -p 8000:8000 amazon/dynamodb-local`) and set in `.env`:
     - `DYNAMODB_ENDPOINT_URL=http://localhost:8000`
     - Run `python scripts/create_table.py` to create the table against the local endpoint.

## Run locally

```bash
cd application
source .venv/bin/activate
uvicorn src.sms_webhook.main:app --reload --port 8000
```

- Health: [http://localhost:8000/health](http://localhost:8000/health)
- Webhook: `POST http://localhost:8000/api/sms/inbound` (Twilio will call this).

## Testing with Twilio Virtual Phone

While your long-code number is waiting for A2P 10DLC approval, you can fully test the app using Twilio’s **Virtual Phone**, which simulates a mobile device inside the Twilio Console and avoids carrier/A2P restrictions (see [Twilio Virtual Phone guide](https://www.twilio.com/docs/messaging/guides/guide-to-using-the-twilio-virtual-phone)).

- **No code changes required** — the app and webhook stay the same.
- You can:
  - Send messages from your application to the Virtual Phone’s toll-free number (`+1 877 780 4236`).
  - Start chats from the Virtual Phone UI to your Twilio number (which will hit this webhook), then see the assistant’s replies in the Virtual Phone UI.

**Steps:**

1. Start the app and (optionally) ngrok as above, and configure your Twilio number’s Messaging webhook to point to `/api/sms/inbound`.
2. In Twilio Console, go to **Messaging → Virtual Phone**.
3. From the Virtual Phone, start a **New Chat** to your Twilio phone number. Messages you send from the Virtual Phone will POST to this app, and replies will appear back in the Virtual Phone conversation.
4. To test outbound-only behavior, you can also have your app send SMS to the Virtual Phone number `+1 877 780 4236` and watch them appear in the Virtual Phone UI.

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

## Phase 2 (quotes, scheduling, notifications)

- **Quote flow:** After the assistant has enough item/access info, it can emit a `GENERATE_QUOTE` action; the backend computes a price range and sends it in a follow-up SMS. Status is stored as `QUOTED`.
- **Booking:** When the customer confirms a date/time, the assistant can emit `BOOK_SLOT` with `slot_id` (e.g. `YYYY-MM-DD_0` or `_1` for morning/afternoon). The backend stores the booking and sets status `BOOKED`.
- **Provider SMS:** Set `PROVIDER_PHONE_NUMBER` in `.env`; the provider receives an SMS when a job is quoted and when it is booked.
- **Quiet hours:** Default 9 PM–8 AM local (override with `TIMEZONE`, `QUIET_HOURS_START`, `QUIET_HOURS_END`). During quiet hours, inbound messages get a short “we’ll respond in business hours” reply only.

## Project layout (Phase 1 + 2)

- `src/sms_webhook/main.py` — FastAPI app, `POST /api/sms/inbound`
- `src/sms_webhook/twilio_handler.py` — Parse payload, validate signature, send SMS
- `src/sms_webhook/conversation.py` — DynamoDB read/write (messages + status, quote, scheduling)
- `src/sms_webhook/llm.py` — Claude with optional ACTION lines (GENERATE_QUOTE, BOOK_SLOT)
- `src/sms_webhook/quote_engine.py` — Tier/modifier pricing
- `src/sms_webhook/scheduler.py` — Simple date/window slots
- `src/sms_webhook/notifications.py` — Provider SMS on QUOTED/BOOKED
- `src/sms_webhook/throttling.py` — Quiet hours check

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
