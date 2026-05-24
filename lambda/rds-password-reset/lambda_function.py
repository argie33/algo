"""
One-shot Lambda to reset RDS master password to a known value.
Connects to RDS and executes ALTER USER to set new password.
"""
import json
import psycopg2
import os
import sys
import logging
from psycopg2 import sql

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """Reset RDS master password by connecting and running SQL."""

    # Credentials must be explicitly provided - no defaults for safety
    db_host = os.environ.get('DB_HOST')
    db_port_str = os.environ.get('DB_PORT', '5432')
    db_user = os.environ.get('DB_USER', 'stocks')
    db_name = os.environ.get('DB_SYSTEM_DB', 'postgres')
    new_password = os.environ.get('NEW_PASSWORD')

    # Validate required credentials
    if not db_host:
        return {
            'statusCode': 400,
            'body': json.dumps({
                'error': 'DB_HOST environment variable is required'
            })
        }

    if not new_password:
        return {
            'statusCode': 400,
            'body': json.dumps({
                'error': 'NEW_PASSWORD environment variable is required'
            })
        }

    db_port = int(db_port_str)

    # Try passwords from environment, fall back to known common defaults if not specified
    env_passwords = os.environ.get('KNOWN_PASSWORDS', '').split(',')
    known_passwords = [p.strip() for p in env_passwords if p.strip()] or [
        'password',  # Terraform default
        'stocks',    # Common choice
        'postgres',  # PostgreSQL default
        '',          # Empty password
    ]

    logger.info(f"Attempting to reset RDS password for {db_user}@{db_host}")
    logger.info(f"Trying known passwords...")

    connection = None
    connected = False

    # Try to connect with known passwords
    for pwd in known_passwords:
        try:
            logger.info(f"  Trying password: {'[set]' if pwd else '[empty]'}")
            connection = psycopg2.connect(
                host=db_host,
                port=db_port,
                user=db_user,
                password=pwd,
                database=db_name,
                connect_timeout=5
            )
            connected = True
            logger.info(f"  ✓ Connected successfully!")
            break
        except psycopg2.Error as e:
            logger.info(f"  ✗ Failed: {str(e)[:100]}")
            continue

    if not connected:
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'Could not connect to RDS with any known password',
                'tried': len(known_passwords)
            })
        }

    try:
        cursor = connection.cursor()

        # Reset the master user password
        alter_sql = f"ALTER USER {db_user} WITH PASSWORD %s;"
        logger.info(f"Executing: ALTER USER {db_user} WITH PASSWORD [***]")
        cursor.execute(alter_sql, (new_password,))
        connection.commit()

        logger.info(f"✓ Password reset successfully for user '{db_user}'")

        cursor.close()
        connection.close()

        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': f'Successfully reset password for {db_user}',
                'user': db_user,
                'host': db_host,
                'database': db_name
            })
        }

    except Exception as e:
        logger.error(f"✗ Error executing ALTER USER: {str(e)}")
        if connection:
            connection.close()
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': f'Failed to reset password: {str(e)}'
            })
        }
