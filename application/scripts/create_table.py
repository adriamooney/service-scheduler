#!/usr/bin/env python3
"""Create the DynamoDB conversations table (local or AWS). Set DYNAMODB_ENDPOINT_URL for local."""

import os
import sys
from pathlib import Path

import boto3
from dotenv import load_dotenv

# Load .env from application/ or repo root so AWS_REGION etc. are set
_app_dir = Path(__file__).resolve().parent.parent
_repo_root = _app_dir.parent
load_dotenv(_app_dir / ".env")
load_dotenv(_repo_root / ".env")
load_dotenv(_repo_root / ".env.local")

TABLE_NAME = os.environ.get("DYNAMODB_TABLE_NAME", "sms_conversations")


def main():
    endpoint = os.environ.get("DYNAMODB_ENDPOINT_URL")
    region = os.environ.get("AWS_REGION", "us-west-2")
    kwargs = {"region_name": region}
    if endpoint:
        kwargs["endpoint_url"] = endpoint
    client = boto3.client("dynamodb", **kwargs)
    try:
        client.create_table(
            TableName=TABLE_NAME,
            KeySchema=[{"AttributeName": "customer_phone", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "customer_phone", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        print(f"Created table: {TABLE_NAME}")
    except client.exceptions.ResourceInUseException:
        print(f"Table {TABLE_NAME} already exists.", file=sys.stderr)
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
