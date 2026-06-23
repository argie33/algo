#!/usr/bin/env python3
"""
RDS Credential Rotation Lambda Function

Rotates RDS master user password every 30 days:
1. Fetch current credentials from Secrets Manager
2. Connect to RDS using current credentials
3. Generate new password
4. Update RDS user password
5. Store new credentials in Secrets Manager
6. Update secret version stage
"""

import json
import logging
import secrets
import string
from typing import Any, cast

import boto3
import psycopg2

logger = logging.getLogger()
logger.setLevel(logging.INFO)

secrets_client = boto3.client("secretsmanager")


def get_secret_dict(secret_id: str, stage: str = "AWSCURRENT") -> dict[str, Any]:
    """Fetch secret from Secrets Manager."""
    try:
        response = secrets_client.get_secret_value(SecretId=secret_id, VersionStage=stage)
        return cast(dict[str, Any], json.loads(response["SecretString"]))
    except Exception as e:
        logger.error(f"Failed to get secret {secret_id}: {e}")
        raise


def set_secret_version(secret_id: str, secret_value: dict[str, Any]) -> str:
    """Create new secret version in Secrets Manager."""
    try:
        response = secrets_client.put_secret_value(
            SecretId=secret_id,
            ClientRequestToken=None,  # Auto-generate token
            SecretString=json.dumps(secret_value),
            VersionStages=["AWSPENDING"],
        )
        return cast(str, response["VersionId"])
    except Exception as e:
        logger.error(f"Failed to put secret {secret_id}: {e}")
        raise


def update_rds_password(host: str, port: int, username: str, current_password: str, new_password: str) -> bool:
    """Connect to RDS and update the master user password."""
    import psycopg2
    import psycopg2.sql

    try:
        conn = psycopg2.connect(
            host=host,
            port=port,
            user=username,
            password=current_password,
            database="postgres",
        )
        cur = conn.cursor()

        cur.execute(
            psycopg2.sql.SQL("ALTER USER {} WITH PASSWORD %s").format(psycopg2.sql.Identifier(username)),
            (new_password,),
        )

        conn.commit()
        cur.close()
        conn.close()

        logger.info(f"Successfully updated password for RDS user {username}")
        return True

    except Exception as e:
        logger.error(f"Failed to update RDS password: {e}")
        raise


def finish_secret(secret_id: str, version_id: str) -> None:
    """Mark the AWSPENDING version as AWSCURRENT."""
    try:
        secrets_client.update_secret_version_stage(
            SecretId=secret_id,
            VersionStage="AWSCURRENT",
            MoveToVersionId=version_id,
            RemoveFromVersionId=None,
        )
        logger.info(f"Marked version {version_id} as AWSCURRENT for {secret_id}")
    except Exception as e:
        logger.error(f"Failed to finish secret rotation: {e}")
        raise


def generate_password(length: int = 32) -> str:
    """Generate a secure random password."""
    # Mix of uppercase, lowercase, digits, and special characters
    characters = string.ascii_letters + string.digits + "!@#$%^&*-_=+"
    password = "".join(secrets.choice(characters) for _ in range(length))
    return password


def handler(event: Any, context: Any) -> dict[str, Any]:
    """
    Main Lambda handler for RDS credential rotation.

    Event format:
    {
        "ClientRequestToken": "...",
        "SecretId": "...",
        "Step": "create|set|finish",
        "SecretVersion": "..."
    }
    """

    secret_id = event["SecretId"]
    event["ClientRequestToken"]
    step = event["Step"]
    secret_version = event["SecretVersion"]

    logger.info(f"Rotation step: {step} for secret {secret_id}")

    try:
        if step == "create":
            logger.info(f"Creating new secret version for {secret_id}")

            current_secret = get_secret_dict(secret_id, "AWSCURRENT")

            new_password = generate_password()

            new_secret = current_secret.copy()
            new_secret["password"] = new_password

            version_id = set_secret_version(secret_id, new_secret)
            logger.info(f"Created new secret version {version_id}")

        elif step == "set":
            logger.info(f"Setting new password in RDS for {secret_id}")

            pending_secret = get_secret_dict(secret_id, "AWSPENDING")

            current_secret = get_secret_dict(secret_id, "AWSCURRENT")

            update_rds_password(
                host=current_secret["host"],
                port=int(current_secret.get("port", 5432)),
                username=current_secret["username"],
                current_password=current_secret["password"],
                new_password=pending_secret["password"],
            )

            logger.info("Successfully updated RDS password")

        # Step 3: Finish rotation by marking AWSPENDING as AWSCURRENT
        elif step == "finish":
            logger.info(f"Finishing rotation for {secret_id}")

            # Verify the new password works by connecting to RDS
            pending_secret = get_secret_dict(secret_id, "AWSPENDING")

            try:
                conn = psycopg2.connect(
                    host=pending_secret["host"],
                    port=int(pending_secret.get("port", 5432)),
                    user=pending_secret["username"],
                    password=pending_secret["password"],
                    database="postgres",
                )
                conn.close()
                logger.info("Verified new credentials work on RDS")
            except Exception as e:
                logger.error(f"Failed to verify new credentials: {e}")
                raise

            # Mark as current
            finish_secret(secret_id, secret_version)
            logger.info("Rotation completed successfully")

        else:
            raise ValueError(f"Invalid step: {step}")

        return {
            "statusCode": 200,
            "body": json.dumps(f"Rotation {step} completed successfully"),
        }

    except Exception as e:
        logger.error(f"Rotation failed at step {step}: {e}")
        raise
