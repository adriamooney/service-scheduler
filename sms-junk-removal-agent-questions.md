# SMS Junk Removal Agent — Follow-up Questions

Answer these so we can implement the plan and build the phased development plan. Add your answers below each question (or inline).

---

## 1. Tech stack

- **Runtime:** Node.js or Python?
  - Your answer:
python
- **Database:** Preference? (PostgreSQL on RDS/Cloud SQL vs DynamoDB/Firestore for serverless-native.)
  - Your answer:
dynamodb is probably sufficient. if you think postgres is better, then justify it in the build doc but also lean toward aurora for serverless AWS
---

## 2. Twilio & external accounts

- Do you already have a **Twilio account** and phone number?
  - Your answer:
   yes. i can provide the API keys when we get to that stage.
   note that there will be multiple service providers paying me a subscription for htis service so they will need to be able to provide their twillio accounts (or we charge them an account fee to set it up)

- For **scheduling** (Phase 2): Google Calendar, Calendly, Cal.com, or custom availability table in our DB first?
  - Your answer:
build with google calendar and hooks for calendly 
---

## 3. Business rules (quote engine & prompts)

- Use the **example pricing tiers/modifiers** in the plan as-is, or do you have **real numbers** to plug in?
  - Your answer:
  assume that it costs $150 delivery fee (to the junkyard) and $50 per hour per person
  assume that there will be multiple service providers using this application and they each need to provide their cost structure along these lines.

- **Service area:** Single city/region or multiple?
  - Your answer:
  portland, oregon but again each service provider will need to set this up

- **Single crew/provider** only for now, or **multi-provider routing** in v1?
  - Your answer:
  for v1 we do not need to support routes or mapping just need to make sure there is a decent window between pickups to manage travel. keep it simple for now.

---

## 4. Provider notifications

- How should the **provider** be notified when a job is quoted or booked? (SMS only, email only, both? Slack/Discord?)
  - Your answer:
  yes. they should get an email, a calendar entry (in their calendar) as well as options for an SMS message 

- Do you already use **SendGrid**, **AWS SES**, or another **email** provider?
  - Your answer:
  nothing set up. assume AWS SES

---

## 5. LLM

- **Model:** Prefer **Claude** (Anthropic) or **GPT-4o** (OpenAI), or **support both** via config?
  - Your answer:
  claude sonnet 4.6 -- is there a lighter weight option for a faster response?

- Do you have **API keys** (and rough **budget** per conversation) in mind?
  - Your answer:
  we can provide the API keys as necessary. assume there is a .evn file for managing secrets or other good patterns for secrets management.

---

## 6. Local development

- How do you want to **receive Twilio webhooks locally**? (e.g. ngrok, Twilio CLI)
  - Your answer:
  i don't care. 

- Prefer **Docker Compose** for local Postgres (and optional Redis), or **SQLite + no Docker** for simplest MVP?
  - Your answer:
  yes. eventually we will want to use docker to containerize the individual comoponents. 
  think micro-services architecture with clean ways of managing and deploying

---

## 7. Compliance & scope

- **US-only** for now? (Affects A2P 10DLC planning.)
  - Your answer:
  yes, uS only

- Any **data retention** requirement (e.g. delete conversations after 90 days)?
  - Your answer:
  data retention of 365 days unless flagged (do this later)

---

## 8. Scope of “serverless”

- **No long-lived servers at all** (webhook = Lambda/Cloud Functions, managed DB, SQS/Pub/Sub), or is **Cloud Run / one small container** acceptable if it simplifies things?
  - Your answer:
  all should be sqs, pub/sub with lambdas as feasible. 
