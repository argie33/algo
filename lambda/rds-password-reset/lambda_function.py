"""
One-shot Lambda to reset RDS master password.
SECURITY: Requires NEW_PASSWORD env var. Does NOT accept hardcoded password guesses.
"""

import json
import logging
import os

import boto3
import psycopg2
import psycopg2.sql
from botocore.exceptions import ClientError


logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    """Reset RDS master password by retrieving credentials from Secrets Manager."""

    # All credentials must come from Secrets Manager or env vars, never hardcoded defaults
    db_host = os.environ.get("DB_HOST")
    db_port_str = os.environ.get("DB_PORT", "5432")
    db_user = os.environ.get("DB_USER", "stocks")
    db_name = os.environ.get("DB_SYSTEM_DB", "postgres")
    new_password = os.environ.get("NEW_PASSWORD")
    secret_arn = os.environ.get("DB_SECRET_ARN")

    if not db_host:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "DB_HOST environment variable is required"}),
        }

    if not new_password:
        return {
            "statusCode": 400,
            "body": json.dumps(
                {"error": "NEW_PASSWORD environment variable is required"}
            ),
        }

    db_port = int(db_port_str)

    # SECURITY FIX: Only retrieve current password from Secrets Manager, never guess
    if not secret_arn:
        return {
            "statusCode": 400,
            "body": json.dumps(
                {"error": "DB_SECRET_ARN required to fetch current credentials"}
            ),
        }

    try:
        secrets_client = boto3.client("secretsmanager")
        response = secrets_client.get_secret_value(SecretId=secret_arn)
        secret = json.loads(response["SecretString"])
        current_password = secret.get("password")

        if not current_password:
            return {
                "statusCode": 400,
                "body": json.dumps(
                    {
                        "error": "Could not retrieve current password from Secrets Manager"
                    }
                ),
            }
    except ClientError as e:
        logger.error(f"Failed to retrieve secret: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps(
                {"error": "Failed to retrieve credentials from Secrets Manager"}
            ),
        }

    logger.info(f"Attempting to reset RDS password for {db_user}@{db_host}")

    connection = None
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
        return {
            "statusCode": 500,
            "body": json.dumps(
                {"error": "Could not connect to RDS with provided credentials"}
            ),
        }

    try:
        cursor = connection.cursor()

        # Reset the master user password using parameterized query
        logger.info(f"Resetting password for user '{db_user}'")
        cursor.execute(
            psycopg2.sql.SQL("ALTER USER {} WITH PASSWORD %s").format(
                psycopg2.sql.Identifier(db_user)
            ),
            (new_password,),
        )
        connection.commit()

        logger.info(f"✓ Password reset successfully for user '{db_user}'")

        cursor.close()
        connection.close()

        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "message": f"Successfully reset password for {db_user}",
                    "user": db_user,
                    "host": db_host,
                    "database": db_name,
                }
            ),
        }

    except Exception as e:
        logger.error(f"✗ Error executing ALTER USER: {str(e)}")
        if connection:
            connection.close()
        return {
            "statusCode": 500,
            "body": json.dumps({"error": f"Failed to reset password: {str(e)}"}),
        }
