"""
Database Schema Initialization Lambda Handler
Initializes all required tables for the stock analytics platform
"""

import json
import os
import sys

# This Lambda should have psycopg2 added as a layer
try:
    import psycopg2
except ImportError:
    print("ERROR: psycopg2 not found. Please add psycopg2 layer to Lambda.")
    raise

from credential_manager import get_credential_manager

# Read schema from packaged SQL file
def load_schema():
    """Load SQL schema from file."""
    try:
        # Try to load from packaged file
        schema_path = os.path.join(os.path.dirname(__file__), 'schema.sql')
        if os.path.exists(schema_path):
            with open(schema_path, 'r') as f:
                return f.read()
    except:
        pass

    # Fallback: inline schema (defined in init_database.py)
    from init_database import SCHEMA
    return SCHEMA

def init_database():
    """Initialize database schema."""
    statements = []
    try:
        cred_manager = get_credential_manager()

        # Get database credentials from Secrets Manager or environment
        db_secret = cred_manager.get_db_credentials()

        db_config = {
            "host": os.getenv("DB_HOST", db_secret.get("host")),
            "port": int(os.getenv("DB_PORT", db_secret.get("port", 5432))),
            "user": os.getenv("DB_USER", db_secret.get("username")),
            "password": db_secret.get("password"),
            "database": os.getenv("DB_NAME", db_secret.get("dbname", "stocks")),
        }

        # Connect to database
        conn = psycopg2.connect(**db_config)
        cur = conn.cursor()

        # Load and execute schema
        schema = load_schema()
        statements = [s.strip() for s in schema.split(';') if s.strip()]

        results = {
            "succeeded": 0,
            "failed": 0,
            "errors": []
        }

        for i, stmt in enumerate(statements, 1):
            try:
                cur.execute(stmt)
                results["succeeded"] += 1
            except Exception as e:
                results["failed"] += 1
                results["errors"].append({
                    "statement": i,
                    "error": str(e)[:100]
                })

        conn.commit()
        cur.close()
        conn.close()

        return results

    except Exception as e:
        return {
            "error": str(e),
            "succeeded": 0,
            "failed": len(statements)
        }

def lambda_handler(event, context):
    """Lambda handler for database initialization."""
    try:
        result = init_database()

        return {
            "statusCode": 200 if result.get("failed", 0) == 0 else 400,
            "body": json.dumps(result, default=str)
        }
    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }

if __name__ == "__main__":
    result = init_database()
    print(json.dumps(result, indent=2, default=str))
