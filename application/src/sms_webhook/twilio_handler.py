"""Parse Twilio inbound webhook, validate signature, send reply."""

from __future__ import annotations

import os
from typing import Any

import sys

from twilio.request_validator import RequestValidator
from twilio.rest import Client


def get_twilio_client() -> Client:
    sid = os.environ.get("TWILIO_ACCOUNT_SID")
    token = os.environ.get("TWILIO_AUTH_TOKEN")
    if not sid or not token:
        raise ValueError("TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN must be set")
    return Client(sid, token)


def get_from_number() -> str:
    num = os.environ.get("TWILIO_PHONE_NUMBER")
    if not num:
        raise ValueError("TWILIO_PHONE_NUMBER must be set")
    return num


def parse_inbound(form: dict[str, Any]) -> tuple[str, str]:
    """Extract (from_phone, body) from Twilio POST form. Body may be empty."""
    from_phone = (form.get("From") or "").strip()
    body = (form.get("Body") or "").strip()
    return from_phone, body


def validate_twilio_signature(url: str, form: dict[str, Any], signature: str | None) -> bool:
    """Return True if the request is signed by Twilio (or if validation is skipped)."""
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
    if not auth_token or not signature:
        return False
    validator = RequestValidator(auth_token)
    # Twilio signs the full URL (including scheme and host) and the sorted form body
    return validator.validate(url, form, signature)


def send_sms(to_phone: str, body: str) -> str | None:
    """Send SMS from TWILIO_PHONE_NUMBER to to_phone. Returns message SID or None on failure."""
    try:
        client = get_twilio_client()
        from_number = get_from_number()
        msg = client.messages.create(to=to_phone, from_=from_number, body=body)
        return msg.sid
    except Exception as exc:  # pragma: no cover - log and swallow in Phase 1
        # Temporary debug print so we can see why Twilio send failed
        print(f"[twilio_handler.send_sms] Failed to send SMS: {exc!r}", file=sys.stderr)
        return None
