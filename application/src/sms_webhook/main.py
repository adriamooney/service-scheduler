"""FastAPI app: POST /api/sms/inbound — receive Twilio SMS, respond via LLM."""

from __future__ import annotations

import os
from typing import Any

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
async def sms_inbound(
    request: Request,
    From: str = Form(None, alias="From"),
    Body: str = Form("", alias="Body"),
) -> Response:
    """
    Twilio calls this with form data. We need the raw form for signature validation,
    so we also accept request and rebuild form from body for validation.
    """
    # Build form dict for signature validation (Twilio sends application/x-www-form-urlencoded)
    body_bytes = await request.body()
    form: dict[str, Any] = {}
    if body_bytes:
        from urllib.parse import parse_qs
        parsed = parse_qs(body_bytes.decode("utf-8"), keep_blank_values=True)
        form = {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}
    from_phone = form.get("From") or From or ""
    msg_body = (form.get("Body") or Body or "").strip()

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
