from __future__ import annotations

import logging
import os

import boto3

logger = logging.getLogger()
dynamodb = boto3.resource("dynamodb")
token_blocklist_table = dynamodb.Table(os.environ.get("TOKEN_BLOCKLIST_TABLE", "algo-token-blocklist-dev"))


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
