#!/usr/bin/env python3
"""
Test configuration and health check utilities.
"""
import os
import sys
import logging
import time
import psycopg2
import json

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stdout,
    format='[%(asctime)s] %(levelname)s %(name)s: %(message)s'
)
logger = logging.getLogger("test_config")

def check_environment():
    """Check that all required environment variables are set"""
    logger.info("=== Environment Check ===")
    
    required_vars = [
        'DB_SECRET_ARN',
        'PYTHONPATH',
        'PYTHONUNBUFFERED'
    ]
    
    missing_vars = []
    for var in required_vars:
        value = os.environ.get(var)
        if value:
            logger.info(f"✓ {var}: {value}")
        else:
            logger.error(f"✗ {var}: NOT SET")
            missing_vars.append(var)
    
    if missing_vars:
        logger.error(f"Missing environment variables: {missing_vars}")
        return False
    
    logger.info("All required environment variables are set")
    return True

def check_database():
    """Check database connectivity"""
    logger.info("=== Database Check ===")
    
    try:
        # Import mock boto3 to get credentials
        sys.path.insert(0, os.path.dirname(__file__))
        import mock_boto3
        sys.modules['boto3'] = mock_boto3
        
        import boto3
        client = boto3.client('secretsmanager')
        response = client.get_secret_value(SecretId='test-db-secret')
        credentials = json.loads(response['SecretString'])
        
        # Test database connection
        conn = psycopg2.connect(
            host=credentials['host'],
            port=credentials['port'],
            user=credentials['username'],
            password=credentials['password'],
            database=credentials['dbname']
        )
        
        # Test basic query
        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        version = cursor.fetchone()[0]
        logger.info(f"✓ Database connected: {version}")
        
        # Check tables
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
            ORDER BY table_name;
        """)
        tables = [row[0] for row in cursor.fetchall()]
        logger.info(f"✓ Available tables: {', '.join(tables)}")
        
        cursor.close()
        conn.close()
        
        return True
        
    except Exception as e:
        logger.error(f"✗ Database check failed: {str(e)}")
        return False

def check_mock_services():
    """Check that mock AWS services are working"""
    logger.info("=== Mock Services Check ===")
    
    try:
        # Import mock boto3
        sys.path.insert(0, os.path.dirname(__file__))
        import mock_boto3
        sys.modules['boto3'] = mock_boto3
        
        import boto3
        
        # Test Secrets Manager
        sm_client = boto3.client('secretsmanager')
        secret = sm_client.get_secret_value(SecretId='test-db-secret')
        logger.info("✓ Secrets Manager mock working")
        
        # Test S3
        s3_client = boto3.client('s3')
        response = s3_client.put_object(Bucket='test-bucket', Key='test-key', Body=b'test')
        logger.info("✓ S3 mock working")
        
        # Test SNS
        sns_client = boto3.client('sns')
        response = sns_client.publish(TopicArn='test-topic', Message='test message')
        logger.info("✓ SNS mock working")
        
        # Test SQS
        sqs_client = boto3.client('sqs')
        response = sqs_client.send_message(QueueUrl='test-queue', MessageBody='test message')
        logger.info("✓ SQS mock working")
        
        return True
        
    except Exception as e:
        logger.error(f"✗ Mock services check failed: {str(e)}")
        return False

def wait_for_database(max_retries=30, retry_interval=2):
    """Wait for database to be ready"""
    logger.info("=== Waiting for Database ===")
    
    for attempt in range(max_retries):
        try:
            # Import mock boto3 to get credentials
            sys.path.insert(0, os.path.dirname(__file__))
            import mock_boto3
            sys.modules['boto3'] = mock_boto3
            
            import boto3
            client = boto3.client('secretsmanager')
            response = client.get_secret_value(SecretId='test-db-secret')
            credentials = json.loads(response['SecretString'])
            
            conn = psycopg2.connect(
                host=credentials['host'],
                port=credentials['port'],
                user=credentials['username'],
                password=credentials['password'],
                database=credentials['dbname']
            )
            conn.close()
            
            logger.info("✓ Database is ready!")
            return True
            
        except psycopg2.OperationalError:
            logger.info(f"Database not ready (attempt {attempt + 1}/{max_retries}), waiting...")
            time.sleep(retry_interval)
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}")
            time.sleep(retry_interval)
    
    logger.error("✗ Database failed to become ready")
    return False

def main():
    """Run all health checks"""
    logger.info("=== Test Environment Health Check ===")
    
    checks = [
        ("Environment Variables", check_environment),
        ("Database Connection", check_database),
        ("Mock AWS Services", check_mock_services)
    ]
    
    all_passed = True
    for check_name, check_func in checks:
        logger.info(f"\n--- {check_name} ---")
        if not check_func():
            all_passed = False
    
    logger.info(f"\n=== Summary ===")
    if all_passed:
        logger.info("🎉 All health checks passed!")
        return 0
    else:
        logger.error("❌ Some health checks failed!")
        return 1

if __name__ == "__main__":
    sys.exit(main())
