"""DynamoDB conversation store: one item per customer_phone, last N messages."""

from __future__ import annotations

import os
from decimal import Decimal
from datetime import datetime, timezone
from typing import Any

import boto3
from boto3.dynamodb.types import TypeSerializer, TypeDeserializer
from botocore.config import Config

MAX_MESSAGES = 20
PK = "customer_phone"
DEFAULT_STATUS = "NEW"

_SERIALIZER = TypeSerializer()
_DESERIALIZER = TypeDeserializer()


def _client():
    endpoint = os.environ.get("DYNAMODB_ENDPOINT_URL")
    region = os.environ.get("AWS_REGION", "us-west-2")
    kwargs = {"region_name": region}
    if endpoint:
        kwargs["endpoint_url"] = endpoint
    return boto3.client("dynamodb", config=Config(retries={"mode": "standard", "max_attempts": 3}), **kwargs)


def _table_name() -> str:
    return os.environ.get("DYNAMODB_TABLE_NAME", "sms_conversations")


def _floats_to_decimal(value: Any) -> Any:
    """Recursively convert floats to Decimal so DynamoDB serializer accepts them."""
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {k: _floats_to_decimal(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_floats_to_decimal(v) for v in value]
    return value


def _to_ddb(value: Any) -> dict[str, Any]:
    """Serialize a Python value to DynamoDB attribute format (floats converted to Decimal)."""
    return _SERIALIZER.serialize(_floats_to_decimal(value))


def _from_ddb(attr: dict[str, Any]) -> Any:
    """Deserialize a DynamoDB attribute value to Python."""
    return _DESERIALIZER.deserialize(attr)


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

    # Serialize for DynamoDB (keep explicit structure for messages)
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

    # Use update_item so we don't clobber other attributes (status, quote, etc.)
    client.update_item(
        TableName=table,
        Key={PK: {"S": customer_phone}},
        UpdateExpression="SET messages = :messages, updated_at = :updated_at",
        ExpressionAttributeValues={
            ":messages": messages_attr,
            ":updated_at": {"S": now},
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


def get_status(customer_phone: str) -> str:
    """Return the current conversation status or DEFAULT_STATUS if not set."""
    client = _client()
    table = _table_name()
    try:
        resp = client.get_item(
            TableName=table,
            Key={PK: {"S": customer_phone}},
            ProjectionExpression="status",
        )
    except client.exceptions.ResourceNotFoundException:
        return DEFAULT_STATUS
    item = resp.get("Item") or {}
    status_attr = item.get("status")
    if not status_attr:
        return DEFAULT_STATUS
    # status is stored as a simple string attribute
    return _from_ddb(status_attr)


def set_status(customer_phone: str, status: str) -> None:
    """Set the conversation status without overwriting other attributes."""
    client = _client()
    table = _table_name()
    now = datetime.now(timezone.utc).isoformat()
    client.update_item(
        TableName=table,
        Key={PK: {"S": customer_phone}},
        UpdateExpression="SET #s = :status, updated_at = :updated_at",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={
            ":status": _to_ddb(status),
            ":updated_at": _to_ddb(now),
        },
    )


def update_job_fields(
    customer_phone: str,
    *,
    items: list[dict[str, Any]] | None = None,
    quote: dict[str, Any] | None = None,
    scheduled_at: str | None = None,
    address: str | None = None,
    access_notes: str | None = None,
) -> None:
    """
    Update structured job-related fields on the conversation item.

    Any argument left as None is not modified.
    Uses ExpressionAttributeNames because 'items' and others are DynamoDB reserved words.
    Only names that appear in the UpdateExpression are sent (DynamoDB rejects unused names).
    """
    update_expr_parts: list[str] = []
    expr_values: dict[str, dict[str, Any]] = {}
    expr_names: dict[str, str] = {}

    if items is not None:
        update_expr_parts.append("#items = :items")
        expr_names["#items"] = "items"
        expr_values[":items"] = _to_ddb(items)
    if quote is not None:
        update_expr_parts.append("#quote = :quote")
        expr_names["#quote"] = "quote"
        expr_values[":quote"] = _to_ddb(quote)
    if scheduled_at is not None:
        update_expr_parts.append("#scheduled_at = :scheduled_at")
        expr_names["#scheduled_at"] = "scheduled_at"
        expr_values[":scheduled_at"] = _to_ddb(scheduled_at)
    if address is not None:
        update_expr_parts.append("#address = :address")
        expr_names["#address"] = "address"
        expr_values[":address"] = _to_ddb(address)
    if access_notes is not None:
        update_expr_parts.append("#access_notes = :access_notes")
        expr_names["#access_notes"] = "access_notes"
        expr_values[":access_notes"] = _to_ddb(access_notes)

    if not update_expr_parts:
        return

    now = datetime.now(timezone.utc).isoformat()
    update_expr_parts.append("#updated_at = :updated_at")
    expr_names["#updated_at"] = "updated_at"
    expr_values[":updated_at"] = _to_ddb(now)

    client = _client()
    table = _table_name()
    client.update_item(
        TableName=table,
        Key={PK: {"S": customer_phone}},
        UpdateExpression="SET " + ", ".join(update_expr_parts),
        ExpressionAttributeNames=expr_names,
        ExpressionAttributeValues=expr_values,
    )


def get_job_snapshot(customer_phone: str) -> dict[str, Any]:
    """
    Return status, quote, scheduled_at, address, access_notes for notifications/display.
    Missing attributes are omitted or defaulted.
    """
    client = _client()
    table = _table_name()
    try:
        resp = client.get_item(
            TableName=table,
            Key={PK: {"S": customer_phone}},
            ProjectionExpression="#s, quote, scheduled_at, #a, access_notes",
            ExpressionAttributeNames={"#s": "status", "#a": "address"},
        )
    except client.exceptions.ResourceNotFoundException:
        return {"status": DEFAULT_STATUS}
    item = resp.get("Item") or {}
    out: dict[str, Any] = {"status": _from_ddb(item["status"]) if "status" in item else DEFAULT_STATUS}
    if "quote" in item:
        out["quote"] = _from_ddb(item["quote"])
    if "scheduled_at" in item:
        out["scheduled_at"] = _from_ddb(item["scheduled_at"])
    if "address" in item:
        out["address"] = _from_ddb(item["address"])
    if "access_notes" in item:
        out["access_notes"] = _from_ddb(item["access_notes"])
    return out
