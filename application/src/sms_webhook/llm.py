"""Anthropic Claude: system prompt and single-turn reply from conversation history."""

from __future__ import annotations

import json
import os
from typing import Any, Tuple

from anthropic import Anthropic

SYSTEM_PROMPT = """You are an SMS assistant for a junk removal service. Be brief and friendly (SMS length).

You have two responsibilities:
1) Talk to the customer in plain SMS-sized English.
2) When you have enough information to estimate a quote, also output a single-line JSON ACTION describing the items and modifiers.

When you output an ACTION, follow this format exactly on a separate line after your SMS reply:

ACTION: {"type": "GENERATE_QUOTE", "items": [...], "modifiers": {...}}

- items: array of objects with keys: name (string), category (\"Small\"|\"Medium\"|\"Large\"|\"XL\"), quantity (int), est_cubic_yards (float).
- modifiers: object with keys (optional): stairs_flights (int), inside_carry (bool), hazardous_count (int), same_day (bool), curbside (bool).

Examples of when to emit an ACTION:
- After you have confirmed the full list of items and basic access details (stairs, inside/curbside, hazardous items).
- Do NOT emit an ACTION on the very first greeting message.

Your visible SMS reply to the customer must NOT contain pricing numbers; pricing is computed by tools. Keep SMS replies to 1–2 short sentences when possible.

When the customer has accepted the quote and chosen a date/time, output:
ACTION: {"type": "BOOK_SLOT", "slot_id": "YYYY-MM-DD_0 or YYYY-MM-DD_1", "address": "optional street address", "access_notes": "optional"}
Use slot_id format: date as YYYY-MM-DD, then _0 for morning (9 AM–12 PM) or _1 for afternoon (1–4 PM)."""


def _client() -> Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY is not set")
    return Anthropic(api_key=api_key)


def _model() -> str:
    return os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")


def _raw_reply(messages: list[dict[str, str]]) -> str:
    """Low-level call to Claude, returning raw text (which may include ACTION line)."""
    if not messages:
        return "Hi! What can we help you remove today?"
    client = _client()
    model = _model()
    resp = client.messages.create(
        model=model,
        max_tokens=256,
        system=SYSTEM_PROMPT,
        messages=messages,
    )
    if not resp.content or not resp.content[0].text:
        return "Sorry, I didn't get that. What do you need removed?"
    return resp.content[0].text.strip()


def reply(messages: list[dict[str, str]]) -> str:
    """
    Backwards-compatible helper: return only the SMS text portion (no ACTION parsing).
    """
    text, _ = reply_with_action(messages)
    return text


def reply_with_action(messages: list[dict[str, str]]) -> Tuple[str, dict[str, Any] | None]:
    """
    Send conversation to Claude and return (sms_text, action_dict_or_None).

    If the model includes a line starting with 'ACTION: ' containing valid JSON,
    that JSON is returned as the action dictionary and the line is removed from
    the SMS text.
    """
    raw = _raw_reply(messages)
    action: dict[str, Any] | None = None

    lines = raw.splitlines()
    kept_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("ACTION:") and action is None:
            payload = stripped[len("ACTION:") :].strip()
            try:
                parsed = json.loads(payload)
                if isinstance(parsed, dict):
                    action = parsed
                    continue  # don't include this line in SMS text
            except json.JSONDecodeError:
                # If JSON is invalid, just treat line as normal text
                pass
        kept_lines.append(line)

    sms_text = "\n".join(kept_lines).strip() or "Sorry, I didn't get that. What do you need removed?"
    return sms_text, action
