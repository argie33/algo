#!/usr/bin/env python3
"""
Database Helper - Clean abstraction for ALL inserts (S3 or standard)
Loaders don't need to know HOW data is inserted, just WHAT to insert.
Automatically chooses best method based on environment.
"""

import os
import logging
from typing import List, Tuple, Dict, Any
import psycopg2
from datetime import datetime

# Optional S3 bulk insert (only imported if USE_S3_STAGING=true)
try:
    from s3_bulk_insert import S3BulkInsert
    HAS_S3 = True
except ImportError:
    HAS_S3 = False

logger = logging.getLogger(__name__)


class DatabaseHelper:
    """
    Universal database insertion helper.
    Automatically chooses between S3 bulk load or standard inserts.

    Usage:
        db = DatabaseHelper(db_config)
        db.insert('price_daily', columns, rows)
        db.close()
    """

    def __init__(self, db_config: Dict[str, Any]):
        """
        Initialize database helper.

        Args:
            db_config: Dict with host, port, user, password, dbname
        """
        self.db_config = db_config
        self.conn = None

        # S3 configuration (only used if enabled)
        self.use_s3 = os.environ.get('USE_S3_STAGING', 'false').lower() == 'true'
        self.s3_bucket = os.environ.get('S3_STAGING_BUCKET', 'stocks-app-data')
        self.rds_role = os.environ.get('RDS_S3_ROLE_ARN', '')

        # Log insertion method
        if self.use_s3 and HAS_S3 and self.rds_role:
            logger.info("✓ Using S3 bulk loading (1000x faster)")
        else:
            logger.info("✓ Using standard database inserts")

    def connect(self):
        """Connect to database"""
        if not self.conn:
            try:
                self.conn = psycopg2.connect(**self.db_config)
                self.conn.autocommit = True
            except Exception as e:
                logger.error(f"Database connection failed: {e}")
                raise

    def close(self):
        """Close database connection"""
        if self.conn:
            try:
                self.conn.close()
            except:
                pass
            self.conn = None

    def insert(self, table_name: str, columns: List[str], rows: List[Tuple]) -> int:
        """
        Insert rows into database.
        Automatically chooses S3 bulk load or standard inserts.

        Args:
            table_name: Target table name
            columns: List of column names
            rows: List of tuples (one tuple per row)

        Returns:
            Number of rows inserted
        """
        if not rows:
            logger.warning(f"{table_name}: No rows to insert")
            return 0

        # Try S3 bulk load first (if enabled)
        if self.use_s3 and HAS_S3 and self.rds_role:
            try:
                logger.info(f"{table_name}: Using S3 bulk load for {len(rows)} rows")
                return self._insert_s3(table_name, columns, rows)
            except Exception as e:
                logger.warning(f"{table_name}: S3 bulk load failed ({str(e)[:50]}), falling back to standard inserts")
                # Fall through to standard insert below

        # Standard insert (fallback or primary method)
        return self._insert_standard(table_name, columns, rows)

    def _insert_s3(self, table_name: str, columns: List[str], rows: List[Tuple]) -> int:
        """Insert via S3 bulk load (1000x faster)"""
        self.connect()
        bulk = S3BulkInsert(self.s3_bucket, self.db_config)
        inserted = bulk.insert_bulk(table_name, columns, rows, self.rds_role)
        return inserted

    def _insert_standard(self, table_name: str, columns: List[str], rows: List[Tuple]) -> int:
        """Insert using standard database inserts (slower but reliable)"""
        self.connect()

        if not self.conn:
            logger.error(f"{table_name}: Failed to connect to database")
            return 0

        try:
            cursor = self.conn.cursor()

            # Build INSERT statement
            col_list = ", ".join(columns)
            placeholders = ", ".join(["%s"] * len(columns))
            sql = f"INSERT INTO {table_name} ({col_list}) VALUES ({placeholders})"

            # Insert rows
            inserted = 0
            for row in rows:
                try:
                    cursor.execute(sql, row)
                    inserted += 1
                except psycopg2.IntegrityError:
                    # Skip duplicates
                    pass
                except Exception as e:
                    logger.debug(f"{table_name}: Row insert error: {str(e)[:50]}")

            self.conn.commit()
            logger.info(f"{table_name}: Inserted {inserted}/{len(rows)} rows")
            return inserted

        except Exception as e:
            logger.error(f"{table_name}: Insert failed: {e}")
            if self.conn:
                self.conn.rollback()
            return 0
        finally:
            if cursor:
                cursor.close()
