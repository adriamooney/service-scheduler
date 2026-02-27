"""Unit tests for inbound SMS: parse, mock LLM, mock Twilio."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.sms_webhook.main import app
from src.sms_webhook import twilio_handler, conversation, llm


client = TestClient(app)


def test_parse_inbound():
    form = {"From": "+15551234567", "Body": "Hello I need a couch removed"}
    from_phone, body = twilio_handler.parse_inbound(form)
    assert from_phone == "+15551234567"
    assert body == "Hello I need a couch removed"

    form2 = {"From": "  +15559999999  ", "Body": ""}
    from_phone2, body2 = twilio_handler.parse_inbound(form2)
    assert from_phone2 == "+15559999999"
    assert body2 == ""


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@patch.dict(os.environ, {
    "TWILIO_ACCOUNT_SID": "ACtest",
    "TWILIO_AUTH_TOKEN": "testtoken",
    "TWILIO_PHONE_NUMBER": "+15550000000",
    "ANTHROPIC_API_KEY": "sk-test",
    "DYNAMODB_TABLE_NAME": "test_conversations",
})
@patch("src.sms_webhook.throttling.check_reply_allowed", return_value=("ALLOW_FULL_REPLY", None))
@patch("src.sms_webhook.twilio_handler.send_sms")
@patch("src.sms_webhook.llm.reply_with_action")
@patch("src.sms_webhook.conversation.add_user_message")
@patch("src.sms_webhook.conversation.add_assistant_message")
@patch("src.sms_webhook.conversation.get_messages_for_llm")
def test_inbound_flow(
    mock_get_messages,
    mock_add_assistant,
    mock_add_user,
    mock_llm_reply,
    mock_send_sms,
    mock_throttle,
):
    mock_get_messages.return_value = [{"role": "user", "content": "Hi"}]
    mock_llm_reply.return_value = ("What do you need removed?", None)
    mock_send_sms.return_value = "SM123"

    # Don't validate signature in test (no TWILIO_WEBHOOK_URL)
    resp = client.post(
        "/api/sms/inbound",
        data={"From": "+15551112222", "Body": "Hi"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code == 200
    mock_add_user.assert_called_once_with("+15551112222", "Hi")
    mock_llm_reply.assert_called_once()
    mock_add_assistant.assert_called_once_with("+15551112222", "What do you need removed?")
    mock_send_sms.assert_called_once_with("+15551112222", "What do you need removed?")


def test_inbound_missing_from():
    resp = client.post(
        "/api/sms/inbound",
        data={"Body": "Hello"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code == 400
