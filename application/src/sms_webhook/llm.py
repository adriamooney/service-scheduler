"""Anthropic Claude: system prompt and single-turn reply from conversation history."""

from __future__ import annotations

import os
from typing import Any

from anthropic import Anthropic

SYSTEM_PROMPT = """You are an SMS assistant for a junk removal service. Be brief and friendly (SMS length).
Ask what they need removed and gather a short description. Do not give prices or book times yet; tell them we'll follow up with a quote and scheduling options.
Keep replies to 1-2 short sentences when possible."""


def _client() -> Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY is not set")
    return Anthropic(api_key=api_key)


def _model() -> str:
    return os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")


def reply(messages: list[dict[str, str]]) -> str:
    """
    Send conversation to Claude and return the assistant's reply.
    messages: [ {"role": "user"|"assistant", "content": "..."}, ... ]
    """
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
