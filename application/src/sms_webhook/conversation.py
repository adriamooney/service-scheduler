"""DynamoDB conversation store: one item per customer_phone, last N messages."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import boto3
from botocore.config import Config

MAX_MESSAGES = 20
PK = "customer_phone"


def _client():
    endpoint = os.environ.get("DYNAMODB_ENDPOINT_URL")
    region = os.environ.get("AWS_REGION", "us-west-2")
    kwargs = {"region_name": region}
    if endpoint:
        kwargs["endpoint_url"] = endpoint
    return boto3.client("dynamodb", config=Config(retries={"mode": "standard", "max_attempts": 3}), **kwargs)


def _table_name() -> str:
    return os.environ.get("DYNAMODB_TABLE_NAME", "sms_conversations")


def get_messages(customer_phone: str) -> list[dict[str, str]]:
    """Return the list of messages for this phone (oldest first). Empty list if none."""
    client = _client()
    table = _table_name()
    try:
        resp = client.get_item(
            TableName=table,
            Key={PK: {"S": customer_phone}},
            ProjectionExpression="messages",
        )
        item = resp.get("Item")
        if not item or "messages" not in item:
            return []
        # DynamoDB returns list of maps: [ {"M": {"role": {"S": "user"}, "content": {"S": "..."}, "ts": {"S": "..."}} }, ... ]
        raw = item["messages"].get("L") or []
        out = []
        for entry in raw:
            m = entry.get("M") or {}
            out.append({
                "role": (m.get("role") or {}).get("S", "user"),
                "content": (m.get("content") or {}).get("S", ""),
                "ts": (m.get("ts") or {}).get("S", ""),
            })
        return out
    except client.exceptions.ResourceNotFoundException:
        return []


def append_messages(customer_phone: str, new_messages: list[dict[str, str]]) -> None:
    """Append new_messages to the conversation and trim to last MAX_MESSAGES."""
    client = _client()
    table = _table_name()
    now = datetime.now(timezone.utc).isoformat()
    for m in new_messages:
        m.setdefault("ts", now)

    existing = get_messages(customer_phone)
    combined = existing + new_messages
    trimmed = combined[-MAX_MESSAGES:] if len(combined) > MAX_MESSAGES else combined

    # Serialize for DynamoDB
    messages_attr = {
        "L": [
            {
                "M": {
                    "role": {"S": msg["role"]},
                    "content": {"S": msg["content"]},
                    "ts": {"S": msg.get("ts", "")},
                }
            }
            for msg in trimmed
        ]
    }

    client.put_item(
        TableName=table,
        Item={
            PK: {"S": customer_phone},
            "messages": messages_attr,
            "updated_at": {"S": datetime.now(timezone.utc).isoformat()},
        },
    )


def add_user_message(customer_phone: str, content: str) -> None:
    """Append one user message."""
    append_messages(customer_phone, [{"role": "user", "content": content}])


def add_assistant_message(customer_phone: str, content: str) -> None:
    """Append one assistant message."""
    append_messages(customer_phone, [{"role": "assistant", "content": content}])


def get_messages_for_llm(customer_phone: str) -> list[dict[str, str]]:
    """Return messages in Anthropic format: [ {"role": "user"|"assistant", "content": "..."} ]. No ts."""
    raw = get_messages(customer_phone)
    return [{"role": m["role"], "content": m["content"]} for m in raw]
