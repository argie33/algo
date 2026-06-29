"""
One-shot Lambda to reset RDS master password with strength validation and approval trail.
SECURITY: Requires NEW_PASSWORD env var with strength validation. No weak passwords allowed.
Logs all reset events to CloudWatch. Sends SNS notification for audit trail.
"""

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, TypedDict

import boto3
import psycopg2
import psycopg2.sql
from botocore.exceptions import ClientError


class PasswordValidationResult(TypedDict):
    """Type definition for password validation result."""

    valid: bool
    errors: list[str]


logger = logging.getLogger()
logger.setLevel(logging.INFO)

cloudwatch = boto3.client("cloudwatch")
sns = boto3.client("sns")


def validate_password_strength(password: str) -> PasswordValidationResult:
    """Validate password meets minimum strength requirements.

    Returns dict with 'valid' bool and 'errors' list of failure reasons.
    Requirements:
    - Minimum 16 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit
    - At least one special character (!@#$%^&*)
    """
    errors = []

    if not password:
        return {"valid": False, "errors": ["Password cannot be empty"]}

    if len(password) < 16:
        errors.append(f"Password too short: {len(password)} chars (minimum 16)")

    if not re.search(r"[A-Z]", password):
        errors.append("Password must contain at least one uppercase letter")

    if not re.search(r"[a-z]", password):
        errors.append("Password must contain at least one lowercase letter")

    if not re.search(r"\d", password):
        errors.append("Password must contain at least one digit")

    if not re.search(r"[!@#$%^&*\-_=+\[\]{}|;:',.<>?/~`]", password):
        errors.append("Password must contain at least one special character")

    return {"valid": len(errors) == 0, "errors": errors}


def lambda_handler(event: Any, context: Any) -> dict[str, int | str]:  # noqa: C901
    """Reset RDS master password with strength validation and audit trail."""

    timestamp = datetime.now(timezone.utc).isoformat()

    # All credentials must come from Secrets Manager or env vars, never hardcoded defaults
    db_host = os.environ.get("DB_HOST")
    # CRITICAL: Port must be explicitly configured, no defaults
    db_port_str = os.environ.get("DB_PORT")
    db_user = os.environ.get("DB_USER")
    db_name = os.environ.get("DB_SYSTEM_DB")
    new_password = os.environ.get("NEW_PASSWORD")
    secret_arn = os.environ.get("DB_SECRET_ARN")
    sns_topic_arn = os.environ.get("PASSWORD_RESET_SNS_TOPIC")

    if not db_host:
        error_msg = "DB_HOST environment variable is required"
        logger.error(error_msg)
        return {
            "statusCode": 400,
            "body": json.dumps({"error": error_msg}),
        }

    if not db_user:
        error_msg = "DB_USER environment variable is required"
        logger.error(error_msg)
        return {
            "statusCode": 400,
            "body": json.dumps({"error": error_msg}),
        }

    if not new_password:
        error_msg = "NEW_PASSWORD environment variable is required"
        logger.error(error_msg)
        return {
            "statusCode": 400,
            "body": json.dumps({"error": error_msg}),
        }

    if not db_name:
        error_msg = "DB_SYSTEM_DB environment variable is required"
        logger.error(error_msg)
        return {
            "statusCode": 400,
            "body": json.dumps({"error": error_msg}),
        }

    # Validate password strength before attempting reset
    validation = validate_password_strength(new_password)
    if not validation["valid"]:
        error_details = "; ".join(validation["errors"])
        logger.error(f"Password validation failed: {error_details}")
        cloudwatch.put_metric_data(
            Namespace="RDS/Security",
            MetricData=[
                {
                    "MetricName": "PasswordResetValidationFailure",
                    "Value": 1,
                    "Unit": "Count",
                    "Timestamp": datetime.now(timezone.utc),
                    "Dimensions": [
                        {"Name": "Database", "Value": db_host},
                        {"Name": "Reason", "Value": "WeakPassword"},
                    ],
                }
            ],
        )

        # Send SNS alert for weak password attempt
        validation_message = {
            "event": "RDS_PASSWORD_RESET",
            "timestamp": timestamp,
            "status": "VALIDATION_FAILED",
            "database_host": db_host,
            "database_user": db_user,
            "reason": "Weak password rejected",
            "validation_errors": validation["errors"],
            "message": "RDS password reset rejected: supplied password does not meet strength requirements",
        }

        if sns_topic_arn:
            try:
                sns.publish(
                    TopicArn=sns_topic_arn,
                    Subject=f"RDS Password Reset REJECTED - Weak Password - {db_host}",
                    Message=json.dumps(validation_message, indent=2),
                )
            except ClientError as e:
                logger.error(f"Failed to send SNS alert for validation failure: {e}")

        return {
            "statusCode": 400,
            "body": json.dumps(
                {
                    "error": "Password does not meet strength requirements",
                    "details": validation["errors"],
                }
            ),
        }

    # CRITICAL: Port must be explicitly provided
    if not db_port_str:
        error_msg = "DB_PORT environment variable is required"
        logger.error(error_msg)
        return {
            "statusCode": 400,
            "body": json.dumps({"error": error_msg}),
        }

    try:
        db_port = int(db_port_str)
    except ValueError:
        error_msg = f"DB_PORT must be a valid integer, got: {db_port_str}"
        logger.error(error_msg)
        return {
            "statusCode": 400,
            "body": json.dumps({"error": error_msg}),
        }

    # SECURITY FIX: Only retrieve current password from Secrets Manager, never guess
    if not secret_arn:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "DB_SECRET_ARN required to fetch current credentials"}),
        }

    try:
        secrets_client = boto3.client("secretsmanager")
        response = secrets_client.get_secret_value(SecretId=secret_arn)
        secret = json.loads(response["SecretString"])
        current_password = secret.get("password")

        if not current_password:
            error_msg = "Could not retrieve current password from Secrets Manager"
            logger.error(error_msg)

            secret_message = {
                "event": "RDS_PASSWORD_RESET",
                "timestamp": timestamp,
                "status": "FAILED",
                "database_host": db_host,
                "database_user": db_user,
                "reason": "Could not retrieve current password from Secrets Manager",
                "message": error_msg,
            }

            if sns_topic_arn:
                try:
                    sns.publish(
                        TopicArn=sns_topic_arn,
                        Subject=f"RDS Password Reset FAILED - Missing Secret - {db_host}",
                        Message=json.dumps(secret_message, indent=2),
                    )
                except ClientError as e:
                    logger.error(f"Failed to send SNS alert for missing secret: {e}")

            return {
                "statusCode": 400,
                "body": json.dumps({"error": error_msg}),
            }
    except ClientError as e:
        logger.error(f"Failed to retrieve secret: {e}")

        secret_message = {
            "event": "RDS_PASSWORD_RESET",
            "timestamp": timestamp,
            "status": "FAILED",
            "database_host": db_host,
            "database_user": db_user,
            "reason": "Failed to retrieve credentials from Secrets Manager",
            "error": str(e),
            "message": "RDS password reset failed: could not access Secrets Manager",
        }

        if sns_topic_arn:
            try:
                sns.publish(
                    TopicArn=sns_topic_arn,
                    Subject=f"RDS Password Reset FAILED - Secrets Manager Error - {db_host}",
                    Message=json.dumps(secret_message, indent=2),
                )
            except ClientError as e:
                logger.error(f"Failed to send SNS alert for secrets manager error: {e}")

        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Failed to retrieve credentials from Secrets Manager"}),
        }

    logger.info(f"Attempting to reset RDS password for {db_user}@{db_host}")

    try:
        logger.info("Connecting to RDS with current credentials...")
        connection = psycopg2.connect(
            host=db_host,
            port=db_port,
            user=db_user,
            password=current_password,
            database=db_name,
            connect_timeout=5,
        )
        logger.info("✓ Connected successfully!")
    except psycopg2.Error as e:
        logger.error(f"Failed to connect: {str(e)[:100]}")

        conn_message = {
            "event": "RDS_PASSWORD_RESET",
            "timestamp": timestamp,
            "status": "FAILED",
            "database_host": db_host,
            "database_port": db_port,
            "database_user": db_user,
            "database_name": db_name,
            "reason": "Could not connect to RDS with provided credentials",
            "error": str(e)[:200],
            "message": f"RDS password reset failed: connection error to {db_host}",
        }

        if sns_topic_arn:
            try:
                sns.publish(
                    TopicArn=sns_topic_arn,
                    Subject=f"RDS Password Reset FAILED - Connection Error - {db_host}",
                    Message=json.dumps(conn_message, indent=2),
                )
            except ClientError as e:
                logger.error(f"Failed to send SNS alert for connection error: {e}")

        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Could not connect to RDS with provided credentials"}),
        }

    try:
        with connection:
            cursor = connection.cursor()

            # Reset the master user password using parameterized query
            logger.info(f"Resetting password for user '{db_user}'")
            cursor.execute(
                psycopg2.sql.SQL("ALTER USER {} WITH PASSWORD %s").format(psycopg2.sql.Identifier(db_user)),
                (new_password,),
            )
            connection.commit()

            logger.info(f"✓ Password reset successfully for user '{db_user}'")

            # Log password reset event to CloudWatch with structured metrics
            cloudwatch.put_metric_data(
                Namespace="RDS/Security",
                MetricData=[
                    {
                        "MetricName": "PasswordResetSuccess",
                        "Value": 1,
                        "Unit": "Count",
                        "Timestamp": datetime.now(timezone.utc),
                        "Dimensions": [
                            {"Name": "Database", "Value": db_host},
                            {"Name": "User", "Value": db_user},
                            {"Name": "RotationType", "Value": "Quarterly"},
                        ],
                    }
                ],
            )

            # Send SNS notification for audit trail and approval record
            audit_message = {
                "event": "RDS_PASSWORD_RESET",
                "timestamp": timestamp,
                "status": "SUCCESS",
                "database_host": db_host,
                "database_port": db_port,
                "database_user": db_user,
                "database_name": db_name,
                "password_strength_verified": True,
                "message": f"RDS password reset completed for user '{db_user}' on {db_host}",
            }

            if sns_topic_arn:
                try:
                    sns.publish(
                        TopicArn=sns_topic_arn,
                        Subject=f"RDS Password Reset - {db_user}@{db_host}",
                        Message=json.dumps(audit_message, indent=2),
                    )
                    logger.info(f"SNS notification sent to {sns_topic_arn}")
                except ClientError as e:
                    logger.warning(
                        f"Failed to send SNS notification: {e}. Password reset succeeded but audit notification failed."
                    )
            else:
                logger.warning(
                    "PASSWORD_RESET_SNS_TOPIC not configured. Password reset succeeded but no audit notification sent."
                )

            return {
                "statusCode": 200,
                "body": json.dumps(
                    {
                        "message": f"Successfully reset password for {db_user}",
                        "user": db_user,
                        "host": db_host,
                        "database": db_name,
                        "timestamp": timestamp,
                    }
                ),
            }

    except (json.JSONDecodeError, ValueError) as e:
        logger.error(f"✗ Error executing ALTER USER: {e!s}")
        reset_error = e

        # Log failed reset attempt to CloudWatch
        cloudwatch.put_metric_data(
            Namespace="RDS/Security",
            MetricData=[
                {
                    "MetricName": "PasswordResetFailure",
                    "Value": 1,
                    "Unit": "Count",
                    "Timestamp": datetime.now(timezone.utc),
                    "Dimensions": [
                        {"Name": "Database", "Value": db_host},
                        {"Name": "User", "Value": db_user},
                        {"Name": "ErrorType", "Value": type(reset_error).__name__},
                    ],
                }
            ],
        )

        # Send SNS notification of failure
        failure_message = {
            "event": "RDS_PASSWORD_RESET",
            "timestamp": timestamp,
            "status": "FAILED",
            "database_host": db_host,
            "database_user": db_user,
            "error": str(reset_error),
            "message": f"Failed to reset RDS password for {db_user}@{db_host}",
        }

        if sns_topic_arn:
            try:
                sns.publish(
                    TopicArn=sns_topic_arn,
                    Subject=f"RDS Password Reset FAILED - {db_user}@{db_host}",
                    Message=json.dumps(failure_message, indent=2),
                )
            except ClientError as e:
                logger.error(f"Failed to send SNS alert for password reset failure: {e}")

        return {
            "statusCode": 500,
            "body": json.dumps({"error": f"Failed to reset password: {reset_error!s}"}),
        }
