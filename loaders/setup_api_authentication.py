"""
Setup API Authentication Infrastructure
Creates tables and indexes needed for API key authentication.
Run once after init_database.py.
"""

import os
import psycopg2
from dotenv import load_dotenv
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

# Load environment
env_file = Path(__file__).parent.parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)


def setup_api_auth():
    """Create API authentication tables and indexes."""
    conn = psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=int(os.getenv('DB_PORT', 5432)),
        user=os.getenv('DB_USER', 'stocks'),
        password=os.getenv('DB_PASSWORD', ''),
        database=os.getenv('DB_NAME', 'stocks'),
    )
    cur = conn.cursor()

    try:
        logger.info("Setting up API authentication infrastructure...")

        # 1. API keys table
        logger.info("  [1/3] Creating api_keys table...")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                id SERIAL PRIMARY KEY,
                key_hash VARCHAR(255) NOT NULL UNIQUE,  -- bcrypt hash of actual key
                key_prefix VARCHAR(10),  -- first 10 chars of key for logs (readable format: sk_*)
                app_name VARCHAR(100) NOT NULL,
                description TEXT,
                permissions VARCHAR[] DEFAULT ARRAY['read:stocks'],
                rate_limit_per_hour INTEGER DEFAULT 1000,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                last_used_at TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE,
                UNIQUE(app_name)
            );
        """)
        logger.info("    ✓ api_keys table created")

        # 2. API requests log table
        logger.info("  [2/3] Creating api_requests_log table...")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS api_requests_log (
                id BIGSERIAL PRIMARY KEY,
                api_key_id INTEGER REFERENCES api_keys(id) ON DELETE SET NULL,
                endpoint VARCHAR(200) NOT NULL,
                method VARCHAR(10),  -- GET, POST, PUT, DELETE
                status_code INTEGER,
                response_time_ms INTEGER,
                user_agent VARCHAR(500),
                source_ip VARCHAR(45),  -- supports IPv6
                request_body_size INTEGER,
                response_body_size INTEGER,
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        logger.info("    ✓ api_requests_log table created")

        # 3. Create indexes for fast lookups and reporting
        logger.info("  [3/3] Creating indexes for performance...")
        indexes = [
            ("api_keys_key_hash_idx", "CREATE INDEX IF NOT EXISTS api_keys_key_hash_idx ON api_keys(key_hash)"),
            ("api_keys_is_active_idx", "CREATE INDEX IF NOT EXISTS api_keys_is_active_idx ON api_keys(is_active) WHERE is_active = TRUE"),
            ("api_requests_key_idx", "CREATE INDEX IF NOT EXISTS api_requests_key_idx ON api_requests_log(api_key_id)"),
            ("api_requests_endpoint_idx", "CREATE INDEX IF NOT EXISTS api_requests_endpoint_idx ON api_requests_log(endpoint)"),
            ("api_requests_created_idx", "CREATE INDEX IF NOT EXISTS api_requests_created_idx ON api_requests_log(created_at DESC)"),
            ("api_requests_status_idx", "CREATE INDEX IF NOT EXISTS api_requests_status_idx ON api_requests_log(status_code)"),
        ]

        for index_name, index_sql in indexes:
            try:
                cur.execute(index_sql)
            except Exception as e:
                if "already exists" not in str(e).lower():
                    logger.info(f"      Warning: {str(e)[:100]}")

        logger.info("    ✓ Indexes created")

        conn.commit()
        logger.info("\n✅ API authentication infrastructure setup complete")
        return True

    except Exception as e:
        conn.rollback()
        logger.info(f"\n❌ Setup failed: {e}")
        return False

    finally:
        cur.close()
        conn.close()


if __name__ == '__main__':
    import sys
    success = setup_api_auth()
    sys.exit(0 if success else 1)
