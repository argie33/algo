#!/usr/bin/env python3
"""Initialize missing database tables for loaders."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.db_connection import get_db_connection
from config.env_loader import load_env
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TABLES = {
    "algo_metrics_daily": """
        CREATE TABLE IF NOT EXISTS algo_metrics_daily (
            date DATE PRIMARY KEY,
            total_actions INTEGER,
            entries INTEGER,
            exits INTEGER,
            avg_signal_score DECIMAL(8, 4),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """
}

def init_tables():
    """Create all required tables."""
    load_env()
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        for table_name, create_sql in TABLES.items():
            try:
                cursor.execute(create_sql)
                logger.info(f"✓ Ensured table exists: {table_name}")
            except Exception as e:
                logger.error(f"✗ Failed to create {table_name}: {e}")
        conn.commit()
        logger.info("Database initialization completed")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    init_tables()
