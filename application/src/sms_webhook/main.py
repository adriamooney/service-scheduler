"""FastAPI app: POST /api/sms/inbound — receive Twilio SMS, respond via LLM."""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Load .env when running locally (application/.env or repo root .env / .env.local)
_app_dir = Path(__file__).resolve().parent.parent.parent  # application/
_repo_root = _app_dir.parent
load_dotenv(_app_dir / ".env")
load_dotenv(_app_dir / ".env.local")
load_dotenv(_repo_root / ".env")
load_dotenv(_repo_root / ".env.local")

from fastapi import FastAPI, Request, Form, Response

from . import conversation, llm, twilio_handler, quote_engine, notifications, scheduler, throttling

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

    # Quiet hours: send short acknowledgment only, no LLM
    decision, throttle_msg = throttling.check_reply_allowed()
    if decision == throttling.THROTTLED_REPLY and throttle_msg:
        conversation.add_assistant_message(from_phone, throttle_msg)
        twilio_handler.send_sms(from_phone, throttle_msg)
        return Response(status_code=200, content="", media_type="text/plain")

    # LLM reply (may include an ACTION line requesting a quote or booking)
    messages = conversation.get_messages_for_llm(from_phone)
    try:
        reply_text, action = llm.reply_with_action(messages)
    except Exception:
        traceback.print_exc(file=sys.stderr)
        reply_text, action = "Sorry, something went wrong. Please try again in a moment.", None

    # Persist assistant message
    conversation.add_assistant_message(from_phone, reply_text)

    # Send reply via Twilio
    sid = twilio_handler.send_sms(from_phone, reply_text)
    if not sid:
        # Still return 200 so Twilio doesn't retry; log in production
        pass

    # Optional: if the LLM requested a quote, compute it and send a follow-up message
    if isinstance(action, dict) and action.get("type") == "GENERATE_QUOTE":
        items_payload = action.get("items") or []
        modifiers_payload = action.get("modifiers") or {}
        mods = quote_engine.QuoteModifiers(
            stairs_flights=int(modifiers_payload.get("stairs_flights", 0) or 0),
            inside_carry=bool(modifiers_payload.get("inside_carry", False)),
            hazardous_count=int(modifiers_payload.get("hazardous_count", 0) or 0),
            same_day=bool(modifiers_payload.get("same_day", False)),
            curbside=bool(modifiers_payload.get("curbside", False)),
        )
        quote = quote_engine.compute_quote(items_payload, mods)
        # Persist structured job fields and status
        conversation.update_job_fields(
            from_phone,
            items=items_payload,
            quote=quote.to_dict(),
        )
        conversation.set_status(from_phone, "QUOTED")

        # Simple SMS summarizing the quote (no need for a second LLM call)
        quote_sms = (
            f"Rough estimate: ${quote.amount_min_dollars():.0f}-${quote.amount_max_dollars():.0f} "
            f"({quote.tier} load, ~{quote.est_truck_fraction * 100:.0f}% of a truck). "
            "If that works, reply with your preferred day/time for pickup."
        )
        conversation.add_assistant_message(from_phone, quote_sms)
        twilio_handler.send_sms(from_phone, quote_sms)
        notifications.notify_quote(from_phone)

    # If LLM requested a booking, apply it and notify provider
    if isinstance(action, dict) and action.get("type") == "BOOK_SLOT":
        slot_id = (action.get("slot_id") or "").strip()
        slot = scheduler.slot_from_id(slot_id) if slot_id else None
        if slot:
            scheduled_label = f"{slot.date_str} {slot.window}"
            conversation.update_job_fields(
                from_phone,
                scheduled_at=scheduled_label,
                address=(action.get("address") or "").strip() or None,
                access_notes=(action.get("access_notes") or "").strip() or None,
            )
            conversation.set_status(from_phone, "BOOKED")
            notifications.notify_booking(from_phone)
            confirm_sms = (
                f"You're booked for {scheduler.format_slot_for_sms(slot)}. "
                "We'll send a reminder before your pickup. Reply HELP for questions or STOP to opt out."
            )
            conversation.add_assistant_message(from_phone, confirm_sms)
            twilio_handler.send_sms(from_phone, confirm_sms)

    # Twilio expects 200 and can optionally get TwiML; empty 200 is fine
    return Response(status_code=200, content="", media_type="text/plain")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
