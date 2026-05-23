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

    # Current credentials (what we know should work - default from Terraform)
    db_host = os.environ.get('DB_HOST', 'algo-db.cojggi2mkthi.us-east-1.rds.amazonaws.com')
    db_port = int(os.environ.get('DB_PORT', '5432'))
    db_user = 'stocks'  # Master user
    db_name = 'postgres'  # System database

    # Try multiple known passwords in order
    known_passwords = [
        'password',  # Default
        'stocks',    # Common choice
        'postgres',  # Default postgres password
        '',          # Empty password
    ]

    # New password to set
    new_password = os.environ.get('NEW_PASSWORD', 'Q6JO2ZiFPsKOfpwb0WGVgmcV0yUg6NAO')

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
