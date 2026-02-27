"""FastAPI app: POST /api/sms/inbound — receive Twilio SMS, respond via LLM."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Load .env when running locally (application/.env or repo root .env / .env.local)
_app_dir = Path(__file__).resolve().parent.parent.parent  # application/
_repo_root = _app_dir.parent
load_dotenv(_app_dir / ".env")
load_dotenv(_repo_root / ".env")
load_dotenv(_repo_root / ".env.local")

from fastapi import FastAPI, Request, Form, Response

from . import conversation, llm, twilio_handler

app = FastAPI(title="SMS Junk Removal Webhook", version="0.1.0")


def _validate_and_parse(request: Request, form: dict[str, Any]) -> tuple[str, str] | None:
    """If Twilio signature is configured, validate and return (from_phone, body). Else return parsed only. None if invalid."""
    signature = request.headers.get("X-Twilio-Signature")
    webhook_url = os.environ.get("TWILIO_WEBHOOK_URL")
    if webhook_url and signature:
        if not twilio_handler.validate_twilio_signature(webhook_url, form, signature):
            return None
    from_phone, body = twilio_handler.parse_inbound(form)
    if not from_phone:
        return None
    return from_phone, body or ""


@app.post("/api/sms/inbound")
async def sms_inbound(request: Request) -> Response:
    """Twilio SMS inbound webhook (application/x-www-form-urlencoded)."""
    # Read form data once; FastAPI parses application/x-www-form-urlencoded for us.
    form_multi = await request.form()
    form: dict[str, Any] = dict(form_multi)
    from_phone = (form.get("From") or "").strip()
    msg_body = (form.get("Body") or "").strip()

    if not from_phone:
        return Response(status_code=400, content="Missing From")

    # Optional signature check
    signature = request.headers.get("X-Twilio-Signature")
    webhook_url = os.environ.get("TWILIO_WEBHOOK_URL")
    if webhook_url and signature and not twilio_handler.validate_twilio_signature(webhook_url, form, signature):
        return Response(status_code=403, content="Invalid signature")

    # Persist user message
    conversation.add_user_message(from_phone, msg_body or "(no text)")

    # LLM reply
    messages = conversation.get_messages_for_llm(from_phone)
    try:
        reply_text = llm.reply(messages)
    except Exception:
        reply_text = "Sorry, something went wrong. Please try again in a moment."

    # Persist assistant message
    conversation.add_assistant_message(from_phone, reply_text)

    # Send reply via Twilio
    sid = twilio_handler.send_sms(from_phone, reply_text)
    if not sid:
        # Still return 200 so Twilio doesn't retry; log in production
        pass

    # Twilio expects 200 and can optionally get TwiML; empty 200 is fine
    return Response(status_code=200, content="", media_type="text/plain")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
