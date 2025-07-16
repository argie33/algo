#!/usr/bin/env python3
"""
Enhanced Data Loader Framework
Provides optimized, reliable, and well-monitored data loading capabilities
with comprehensive error handling and performance optimization.
"""

import os
import sys
import json
import time
import logging
import traceback
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Any
from contextlib import contextmanager
import boto3
import psycopg2
from psycopg2.extras import execute_values
from psycopg2.pool import ThreadedConnectionPool

# Configure comprehensive logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('/tmp/data_loader.log', mode='a')
    ]
)
logger = logging.getLogger(__name__)

class DataLoaderOptimizer:
    """
    Enhanced data loader with performance optimization and reliability features.
    Implements best practices for high-volume data loading operations.
    """
    
    def __init__(self, loader_name: str, table_name: str, batch_size: int = 1000):
        """
        Initialize the enhanced data loader.
        
        Args:
            loader_name: Name of the data loader for logging
            table_name: Target database table
            batch_size: Number of records to process in each batch
        """
        self.loader_name = loader_name
        self.table_name = table_name
        self.batch_size = batch_size
        self.start_time = time.time()
        self.metrics = {
            'records_processed': 0,
            'records_inserted': 0,
            'records_updated': 0,
            'records_failed': 0,
            'batches_processed': 0,
            'errors': [],
            'performance': {}
        }
        
        # Initialize database configuration
        self.db_config = self._get_database_config()
        self.connection_pool = None
        
        logger.info(f"🚀 Initializing {loader_name} for table {table_name} with batch size {batch_size}")
    
    def _get_database_config(self) -> Dict[str, str]:
        """Get database configuration from AWS Secrets Manager."""
        db_secret_arn = os.environ.get("DB_SECRET_ARN")
        if not db_secret_arn:
            raise ValueError("DB_SECRET_ARN environment variable not set")
        
        try:
            client = boto3.client("secretsmanager")
            response = client.get_secret_value(SecretId=db_secret_arn)
            secret = json.loads(response["SecretString"])
            
            config = {
                'host': secret["host"],
                'port': secret.get("port", "5432"),
                'user': secret["username"], 
                'password': secret["password"],
                'database': secret["dbname"]
            }
            
            logger.info(f"✅ Database configuration loaded for {config['host']}:{config['port']}")
            return config
            
        except Exception as e:
            logger.error(f"❌ Failed to get database config: {e}")
            raise
    
    def initialize_connection_pool(self, min_connections: int = 1, max_connections: int = 5):
        """Initialize database connection pool for optimized performance."""
        try:
            self.connection_pool = ThreadedConnectionPool(
                min_connections,
                max_connections,
                host=self.db_config['host'],
                port=self.db_config['port'],
                user=self.db_config['user'],
                password=self.db_config['password'],
                database=self.db_config['database'],
                # Performance optimizations
                options='-c statement_timeout=300000',  # 5 minutes
                connect_timeout=30,
                keepalives_idle=600,
                keepalives_interval=30,
                keepalives_count=3
            )
            
            logger.info(f"✅ Connection pool initialized: {min_connections}-{max_connections} connections")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize connection pool: {e}")
            raise
    
    @contextmanager
    def get_connection(self):
        """Context manager for database connections with automatic cleanup."""
        if not self.connection_pool:
            self.initialize_connection_pool()
        
        connection = None
        try:
            connection = self.connection_pool.getconn()
            connection.autocommit = False
            yield connection
            
        except Exception as e:
            if connection:
                connection.rollback()
            logger.error(f"❌ Database connection error: {e}")
            raise
            
        finally:
            if connection:
                self.connection_pool.putconn(connection)
    
    def validate_table_schema(self, required_columns: List[Dict[str, str]]) -> bool:
        """
        Validate that the target table exists and has required columns.
        
        Args:
            required_columns: List of column definitions with name and type
            
        Returns:
            True if table schema is valid
        """
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    # Check if table exists
                    cursor.execute("""
                        SELECT EXISTS (
                            SELECT FROM information_schema.tables 
                            WHERE table_schema = 'public' 
                            AND table_name = %s
                        )
                    """, (self.table_name,))
                    
                    if not cursor.fetchone()[0]:
                        logger.error(f"❌ Table {self.table_name} does not exist")
                        return False
                    
                    # Get existing columns
                    cursor.execute("""
                        SELECT column_name, data_type 
                        FROM information_schema.columns 
                        WHERE table_name = %s AND table_schema = 'public'
                        ORDER BY ordinal_position
                    """, (self.table_name,))
                    
                    existing_columns = {row[0]: row[1] for row in cursor.fetchall()}
                    
                    # Validate required columns
                    missing_columns = []
                    for col_def in required_columns:
                        col_name = col_def['name']
                        if col_name not in existing_columns:
                            missing_columns.append(col_name)
                    
                    if missing_columns:
                        logger.error(f"❌ Missing required columns in {self.table_name}: {missing_columns}")
                        return False
                    
                    logger.info(f"✅ Table {self.table_name} schema validation passed")
                    return True
                    
        except Exception as e:
            logger.error(f"❌ Schema validation failed: {e}")
            return False
    
    def batch_insert_with_conflict_resolution(self, 
                                            data: List[Dict[str, Any]], 
                                            conflict_columns: List[str],
                                            update_columns: List[str] = None) -> Dict[str, int]:
        """
        Perform optimized batch insert with conflict resolution.
        
        Args:
            data: List of record dictionaries to insert
            conflict_columns: Columns that define uniqueness for conflict resolution
            update_columns: Columns to update on conflict (defaults to all non-key columns)
            
        Returns:
            Dictionary with insert/update counts
        """
        if not data:
            return {'inserted': 0, 'updated': 0, 'failed': 0}
        
        batch_start = time.time()
        result = {'inserted': 0, 'updated': 0, 'failed': 0}
        
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    # Get column names from first record
                    columns = list(data[0].keys())
                    
                    # Build INSERT ... ON CONFLICT query
                    placeholders = ', '.join(['%s'] * len(columns))
                    column_list = ', '.join(columns)
                    conflict_list = ', '.join(conflict_columns)
                    
                    if update_columns is None:
                        update_columns = [col for col in columns if col not in conflict_columns]
                    
                    update_clause = ', '.join([f"{col} = EXCLUDED.{col}" for col in update_columns])
                    
                    query = f"""
                        INSERT INTO {self.table_name} ({column_list})
                        VALUES %s
                        ON CONFLICT ({conflict_list})
                        DO UPDATE SET {update_clause}
                    """
                    
                    # Convert data to tuples
                    values = [tuple(record[col] for col in columns) for record in data]
                    
                    # Execute batch insert
                    execute_values(
                        cursor, query, values,
                        template=None, page_size=self.batch_size,
                        fetch=False
                    )
                    
                    # Get affected row count
                    affected_rows = cursor.rowcount
                    result['inserted'] = affected_rows  # This includes both inserts and updates
                    
                    conn.commit()
                    
                    batch_duration = time.time() - batch_start
                    logger.info(f"✅ Batch processed: {len(data)} records, {affected_rows} affected in {batch_duration:.2f}s")
                    
        except Exception as e:
            result['failed'] = len(data)
            error_msg = f"Batch insert failed: {e}"
            logger.error(f"❌ {error_msg}")
            self.metrics['errors'].append({
                'timestamp': datetime.now().isoformat(),
                'error': error_msg,
                'batch_size': len(data)
            })
            
        return result
    
    def process_data_with_validation(self, 
                                   data_source_func,
                                   data_validator_func,
                                   conflict_columns: List[str],
                                   **kwargs) -> Dict[str, Any]:
        """
        Complete data processing pipeline with validation and optimization.
        
        Args:
            data_source_func: Function that yields data records
            data_validator_func: Function to validate each record
            conflict_columns: Columns for conflict resolution
            **kwargs: Additional arguments for data source function
            
        Returns:
            Processing results and metrics
        """
        logger.info(f"🔄 Starting data processing for {self.loader_name}")
        
        batch_buffer = []
        
        try:
            # Process data in batches
            for record in data_source_func(**kwargs):
                # Validate record
                if data_validator_func and not data_validator_func(record):
                    self.metrics['records_failed'] += 1
                    continue
                
                batch_buffer.append(record)
                self.metrics['records_processed'] += 1
                
                # Process batch when buffer is full
                if len(batch_buffer) >= self.batch_size:
                    result = self.batch_insert_with_conflict_resolution(
                        batch_buffer, conflict_columns
                    )
                    
                    self.metrics['records_inserted'] += result['inserted']
                    self.metrics['records_failed'] += result['failed']
                    self.metrics['batches_processed'] += 1
                    
                    batch_buffer = []
            
            # Process remaining records
            if batch_buffer:
                result = self.batch_insert_with_conflict_resolution(
                    batch_buffer, conflict_columns
                )
                
                self.metrics['records_inserted'] += result['inserted']
                self.metrics['records_failed'] += result['failed']
                self.metrics['batches_processed'] += 1
            
            # Calculate final metrics
            total_duration = time.time() - self.start_time
            self.metrics['performance'] = {
                'total_duration_seconds': total_duration,
                'records_per_second': self.metrics['records_processed'] / total_duration if total_duration > 0 else 0,
                'batches_per_second': self.metrics['batches_processed'] / total_duration if total_duration > 0 else 0
            }
            
            logger.info(f"✅ Data processing completed for {self.loader_name}")
            self._log_final_metrics()
            
            return {
                'success': True,
                'metrics': self.metrics,
                'loader_name': self.loader_name,
                'table_name': self.table_name
            }
            
        except Exception as e:
            error_msg = f"Data processing failed: {e}"
            logger.error(f"❌ {error_msg}")
            logger.error(traceback.format_exc())
            
            return {
                'success': False,
                'error': error_msg,
                'metrics': self.metrics,
                'loader_name': self.loader_name,
                'table_name': self.table_name
            }
        
        finally:
            if self.connection_pool:
                self.connection_pool.closeall()
    
    def _log_final_metrics(self):
        """Log comprehensive final metrics."""
        metrics = self.metrics
        perf = metrics['performance']
        
        logger.info("📊 FINAL PROCESSING METRICS:")
        logger.info(f"   📝 Loader: {self.loader_name}")
        logger.info(f"   🗃️  Table: {self.table_name}")
        logger.info(f"   📊 Records Processed: {metrics['records_processed']:,}")
        logger.info(f"   ✅ Records Inserted: {metrics['records_inserted']:,}")
        logger.info(f"   ❌ Records Failed: {metrics['records_failed']:,}")
        logger.info(f"   🔄 Batches Processed: {metrics['batches_processed']:,}")
        logger.info(f"   ⏱️  Total Duration: {perf['total_duration_seconds']:.2f}s")
        logger.info(f"   🚀 Records/sec: {perf['records_per_second']:.2f}")
        logger.info(f"   📦 Batches/sec: {perf['batches_per_second']:.2f}")
        
        if metrics['errors']:
            logger.warning(f"   ⚠️  Errors encountered: {len(metrics['errors'])}")
        
        # Success rate calculation
        total_attempted = metrics['records_processed']
        success_rate = (metrics['records_inserted'] / total_attempted * 100) if total_attempted > 0 else 0
        logger.info(f"   📈 Success Rate: {success_rate:.2f}%")


# Utility functions for common data loading patterns
def create_data_validator(required_fields: List[str], field_validators: Dict[str, callable] = None):
    """Create a data validation function with required fields and custom validators."""
    
    def validator(record: Dict[str, Any]) -> bool:
        # Check required fields
        for field in required_fields:
            if field not in record or record[field] is None:
                return False
        
        # Check custom field validators
        if field_validators:
            for field, validator_func in field_validators.items():
                if field in record and not validator_func(record[field]):
                    return False
        
        return True
    
    return validator


def log_data_loader_start(loader_name: str, description: str):
    """Standard logging for data loader startup."""
    logger.info("=" * 80)
    logger.info(f"🚀 STARTING DATA LOADER: {loader_name}")
    logger.info(f"📝 Description: {description}")
    logger.info(f"⏰ Start Time: {datetime.now().isoformat()}")
    logger.info("=" * 80)


def log_data_loader_end(loader_name: str, success: bool, metrics: Dict[str, Any] = None):
    """Standard logging for data loader completion."""
    status = "✅ SUCCESS" if success else "❌ FAILED"
    logger.info("=" * 80)
    logger.info(f"{status}: {loader_name} COMPLETED")
    logger.info(f"⏰ End Time: {datetime.now().isoformat()}")
    
    if metrics:
        logger.info(f"📊 Final Metrics: {json.dumps(metrics, indent=2)}")
    
    logger.info("=" * 80)


if __name__ == "__main__":
    """Example usage of the enhanced data loader framework."""
    
    # Example: Stock symbols loader
    def example_data_source():
        """Example data source that yields records."""
        yield {'symbol': 'AAPL', 'name': 'Apple Inc.', 'exchange': 'NASDAQ'}
        yield {'symbol': 'GOOGL', 'name': 'Alphabet Inc.', 'exchange': 'NASDAQ'}
    
    # Example: Data validator
    validator = create_data_validator(
        required_fields=['symbol', 'name', 'exchange'],
        field_validators={
            'symbol': lambda x: len(x) <= 10 and x.isupper(),
            'exchange': lambda x: x in ['NASDAQ', 'NYSE', 'AMEX']
        }
    )
    
    # Initialize and run loader
    loader = DataLoaderOptimizer("example_loader", "stock_symbols", batch_size=1000)
    
    result = loader.process_data_with_validation(
        data_source_func=example_data_source,
        data_validator_func=validator,
        conflict_columns=['symbol']
    )
    
    print(json.dumps(result, indent=2))