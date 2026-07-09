from __future__ import annotations

import logging
import os

import boto3

logger = logging.getLogger()
dynamodb = boto3.resource("dynamodb")

# SECURITY FIX: Fail-fast if TOKEN_BLOCKLIST_TABLE not configured (don't silently default to dev table)
_token_blocklist_table_name = os.environ.get("TOKEN_BLOCKLIST_TABLE")
if not _token_blocklist_table_name:
    raise RuntimeError(
        "[CRITICAL] TOKEN_BLOCKLIST_TABLE environment variable not configured. "
        "Token revocation cannot work without a configured DynamoDB table. "
        "Set TOKEN_BLOCKLIST_TABLE to your environment's token blocklist table name."
    )
token_blocklist_table = dynamodb.Table(_token_blocklist_table_name)


def is_revoked(jti: str) -> bool:
    try:
        response = token_blocklist_table.get_item(Key={"jti": jti})
        return "Item" in response
    except Exception as e:
        raise RuntimeError(f"Operation failed: {e}") from e


def revoke_token(jti: str, exp: int) -> None:
    token_blocklist_table.put_item(
        Item={
            "jti": jti,
            "expires_at": exp,
        }
    )
