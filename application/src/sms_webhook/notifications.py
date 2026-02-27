"""Notify provider via SMS when a job is quoted or booked."""

from __future__ import annotations

import os
import sys

from . import conversation, twilio_handler


def _provider_phone() -> str | None:
    return (os.environ.get("PROVIDER_PHONE_NUMBER") or "").strip() or None


def notify_quote(customer_phone: str) -> bool:
    """Send SMS to provider with quote summary. Returns True if sent."""
    phone = _provider_phone()
    if not phone:
        print("[notifications] PROVIDER_PHONE_NUMBER not set; skipping quote SMS", file=sys.stderr)
        return False
    snap = conversation.get_job_snapshot(customer_phone)
    quote = snap.get("quote") or {}
    amin = quote.get("amount_min")
    amax = quote.get("amount_max")
    tier = quote.get("tier", "—")
    frac = quote.get("est_truck_fraction")
    frac_pct = f"{frac * 100:.0f}%" if isinstance(frac, (int, float)) else "—"
    body = (
        f"[Junk] QUOTED — Customer {customer_phone} | "
        f"${amin}–${amax} ({tier}, ~{frac_pct} truck). Reply to this number to view thread."
    )
    sid = twilio_handler.send_sms(phone, body)
    if sid:
        print(f"[notifications] Quote alert sent to provider (SID {sid})", file=sys.stderr)
    return sid is not None


def notify_booking(customer_phone: str) -> bool:
    """Send SMS to provider with booking summary. Returns True if sent."""
    phone = _provider_phone()
    if not phone:
        print("[notifications] PROVIDER_PHONE_NUMBER not set; skipping booking SMS", file=sys.stderr)
        return False
    snap = conversation.get_job_snapshot(customer_phone)
    quote = snap.get("quote") or {}
    amin = quote.get("amount_min")
    amax = quote.get("amount_max")
    addr = snap.get("address") or "No address"
    scheduled = snap.get("scheduled_at") or "—"
    body = (
        f"[Junk] BOOKED — {customer_phone} | {addr} | "
        f"{scheduled} | ${amin}–${amax}. Reply to this number to view thread."
    )
    sid = twilio_handler.send_sms(phone, body)
    if sid:
        print(f"[notifications] Booking alert sent to provider (SID {sid})", file=sys.stderr)
    return sid is not None
