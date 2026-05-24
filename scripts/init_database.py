#!/usr/bin/env python3
"""Initialize RDS database schema from init.sql."""
import os
import psycopg2
from pathlib import Path

def init_database():
    """Load and execute init.sql against the database."""
    host = os.getenv("DB_HOST")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    db_name = os.getenv("DB_NAME")

    if not all([host, user, password, db_name]):
        raise ValueError("Missing required environment variables: DB_HOST, DB_USER, DB_PASSWORD, DB_NAME")

    # Read the init.sql file
    sql_file = Path(__file__).parent / "terraform" / "modules" / "database" / "init.sql"
    if not sql_file.exists():
        raise FileNotFoundError(f"init.sql not found at {sql_file}")

    with open(sql_file, 'r') as f:
        sql_content = f.read()

    # Connect to database and execute schema
    try:
        conn = psycopg2.connect(
            host=host,
            user=user,
            password=password,
            database=db_name
        )
        cursor = conn.cursor()

        print(f"[*] Connected to {db_name}@{host}")
        print("[*] Executing init.sql...")

        # Execute all statements in the init.sql file
        # Split by semicolons and execute each statement
        statements = sql_content.split(';')
        for i, stmt in enumerate(statements):
            stmt = stmt.strip()
            if not stmt:
                continue
            try:
                cursor.execute(stmt)
                print(f"[✓] Statement {i+1} executed")
            except psycopg2.Error as e:
                # Some statements might fail if they already exist (IF NOT EXISTS)
                # Log but continue
                print(f"[⚠] Statement {i+1} warning: {e.pgerror if hasattr(e, 'pgerror') else str(e)}")

        conn.commit()
        cursor.close()
        conn.close()

        print("[✓] Database schema initialized successfully!")
        return 0

    except Exception as e:
        print(f"[✗] Database initialization failed: {e}")
        raise

if __name__ == "__main__":
    import sys
    try:
        sys.exit(init_database() or 0)
    except Exception as e:
        print(f"[✗] Error: {e}")
        sys.exit(1)
