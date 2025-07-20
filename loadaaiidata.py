#!/usr/bin/env python3
# AAII data loader - sentiment and allocation data
# Trigger deploy-app-stocks workflow - loadaaiidata update v6.2 - SSL PRODUCTION TEST - comprehensive SSL certificate validation
import sys
import time
import logging
import json
import os
import gc
import resource
import math

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
from datetime import datetime

import boto3
import pandas as pd
import requests
from io import BytesIO

# -------------------------------
# Script metadata & logging setup   
# -------------------------------
SCRIPT_NAME = "loadaaiidata.py"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

# -------------------------------
# Memory-logging helper (RSS in MB)
# -------------------------------
def get_rss_mb():
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform.startswith("linux"):
        return usage / 1024
    return usage / (1024 * 1024)

def log_mem(stage: str):
    logging.info(f"[MEM] {stage}: {get_rss_mb():.1f} MB RSS")

# -------------------------------
# Retry settings
# -------------------------------
MAX_DOWNLOAD_RETRIES = 5  
RETRY_DELAY = 3.0  # seconds between download retries
BACKOFF_MULTIPLIER = 2.0  # exponential backoff multiplier

# -------------------------------
# AAII Sentiment columns
# -------------------------------
SENTIMENT_COLUMNS = ["date", "bullish", "neutral", "bearish"]
COL_LIST = ", ".join(SENTIMENT_COLUMNS)

# -------------------------------
# Direct URL to the AAII sentiment survey Excel file
# -------------------------------
AAII_EXCEL_URL = "https://www.aaii.com/files/surveys/sentiment.xls"

# -------------------------------
# DB config loader
# -------------------------------
def get_db_config():
    secret_str = boto3.client("secretsmanager") \
                     .get_secret_value(SecretId=os.environ["DB_SECRET_ARN"])["SecretString"]
    sec = json.loads(secret_str)
    return {
        "host":   sec["host"],
        "port":   int(sec.get("port", 5432)),
        "user":   sec["username"],
        "password": sec["password"],
        "dbname": sec["dbname"]
    }

# -------------------------------
# Download AAII sentiment data
# -------------------------------
def get_aaii_sentiment_data():
    """
    Downloads the AAII sentiment survey Excel file and extracts historical data.
    Returns a DataFrame with the columns: Date, Bullish, Neutral, and Bearish.
    """
    logging.info(f"🔄 Starting AAII sentiment data download from: {AAII_EXCEL_URL}")
    
    # Custom headers to mimic a browser request for an Excel file
    headers = {
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/115.0.0.0 Safari/537.36")
        "Referer": "https://www.aaii.com/"
        "Accept": "application/vnd.ms-excel, application/vnd.openxmlformats-officedocument.spreadsheetml.sheet, */*"
        "Accept-Language": "en-US,en;q=0.9"
    }
    
    for attempt in range(1, MAX_DOWNLOAD_RETRIES + 1):
        try:
            logging.info(f"Download attempt {attempt}/{MAX_DOWNLOAD_RETRIES}")
            response = requests.get(AAII_EXCEL_URL, headers=headers, allow_redirects=True, timeout=30)
            response.raise_for_status()
            
            # Check the content-type header for debugging
            content_type = response.headers.get("Content-Type", "")
            content_length = response.headers.get("Content-Length", "unknown")
            logging.info(f"✅ Response received - Content-Type: {content_type}, Content-Length: {content_length}")
            
            # If the response looks like HTML rather than an Excel file, raise an error
            if "html" in content_type.lower():
                logging.error(f"❌ Server returned HTML instead of Excel file")
                logging.error(f"❌ Response preview: {response.content[:500]}")
                raise ValueError("Server returned HTML instead of an Excel file. Check the URL or headers.")
            
            # Validate file size
            if len(response.content) < 1000:  # Excel files should be larger than 1KB
                logging.error(f"❌ Response too small ({len(response.content)} bytes) - likely not an Excel file")
                raise ValueError(f"Response too small ({len(response.content)} bytes) - likely not an Excel file")
            
            # Load the Excel file from the downloaded bytes using xlrd
            excel_data = BytesIO(response.content)
            logging.info("📊 Attempting to parse Excel file...")
            df = pd.read_excel(excel_data, skiprows=3, engine="xlrd")
            
            # Remove extra whitespace from column names
            df.columns = df.columns.str.strip()
            
            # We need at least these columns; adjust if necessary
            required_cols = ["Date", "Bullish", "Neutral", "Bearish"]
            logging.info(f"📋 Found columns: {df.columns.tolist()}")
            
            missing_cols = [col for col in required_cols if col not in df.columns]
            if missing_cols:
                logging.error(f"❌ Missing required columns: {missing_cols}")
                logging.error(f"❌ Available columns: {df.columns.tolist()}")
                raise ValueError(f"Expected columns {missing_cols} not found. Found columns: {df.columns.tolist()}")
            
            # Select only the required columns
            df = df[required_cols]
            logging.info(f"✅ Selected {len(df)} rows with required columns")
            
            # Clean percentage columns: remove "%" and convert to numeric
            for col in ["Bullish", "Neutral", "Bearish"]:
                df[col] = df[col].astype(str).str.replace("%", "", regex=False).str.strip()
                df[col] = pd.to_numeric(df[col], errors="coerce")
            
            # Convert the Date column to datetime and then to string in YYYY-MM-DD format
            df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
            df = df.dropna(subset=["Date"])  # Drop rows where date conversion failed
            df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")
            
            # Sort by Date (oldest first) and reset index
            df.sort_values("Date", inplace=True)
            df.reset_index(drop=True, inplace=True)
            
            logging.info(f"Successfully downloaded AAII sentiment data: {len(df)} records")
            return df
            
        except Exception as e:
            logging.error(f"❌ Download attempt {attempt} failed: {e}")
            logging.error(f"❌ Error type: {type(e).__name__}")
            import traceback
            logging.error(f"❌ Stack trace: {traceback.format_exc()}")
            if attempt < MAX_DOWNLOAD_RETRIES:
                retry_delay = RETRY_DELAY * (BACKOFF_MULTIPLIER ** (attempt - 1))
                logging.info(f"⏳ Retrying in {retry_delay:.1f} seconds... (attempt {attempt}/{MAX_DOWNLOAD_RETRIES})")
                time.sleep(retry_delay)
            else:
                logging.error(f"❌ CRITICAL: Failed to download AAII sentiment data after {MAX_DOWNLOAD_RETRIES} attempts")
                logging.error(f"❌ Final error: {e}")
                raise Exception(f"Failed to download AAII sentiment data after {MAX_DOWNLOAD_RETRIES} attempts: {e}")

# -------------------------------
# Main loader with batched inserts
# -------------------------------
def load_sentiment_data(cur, conn):
    logging.info("Loading AAII sentiment data")
    
    try:
        # Download the sentiment data
        df = get_aaii_sentiment_data()
        
        if df.empty:
            logging.warning("No sentiment data downloaded")
            return 0, 0, []
        
        # Convert DataFrame to list of tuples for batch insert
        rows = []
        for _, row in df.iterrows():
            rows.append([
                row["Date"],
                None if pd.isna(row["Bullish"]) else float(row["Bullish"]),
                None if pd.isna(row["Neutral"]) else float(row["Neutral"]),
                None if pd.isna(row["Bearish"]) else float(row["Bearish"])
            ])
        
        if not rows:
            logging.warning("No valid rows after processing")
            return 0, 0, []
        
        # Batch insert the data
        sql = f"INSERT INTO aaii_sentiment ({COL_LIST}) VALUES %s"
        execute_values(cur, sql, rows)
        conn.commit()
        
        inserted = len(rows)
        logging.info(f"Successfully inserted {inserted} sentiment records")
        
        return len(df), inserted, []
        
    except Exception as e:
        logging.error(f"Error loading sentiment data: {e}")
        return 0, 0, [str(e)]

# -------------------------------
# Entrypoint
# -------------------------------
if __name__ == "__main__":
    try:
        logging.info(f"🚀 Starting {SCRIPT_NAME} execution")
        log_mem("startup")
        
        # Log all environment variables for debugging
        logging.info("🔍 Environment Variables:")
        env_vars_to_check = [
            "DB_SECRET_ARN", "AWS_REGION", "AWS_DEFAULT_REGION",
            "NODE_ENV", "DB_HOST", "DB_PORT", "DB_NAME", "DB_USER"
        ]
        for var in env_vars_to_check:
            value = os.environ.get(var, "NOT_SET")
            if "SECRET" in var and value != "NOT_SET":
                logging.info(f"  {var}: {value[:20]}...***REDACTED***")
            else:
                logging.info(f"  {var}: {value}")
        
        # Log ECS task metadata if available
        try:
            import urllib.request
            metadata_uri = os.environ.get('ECS_CONTAINER_METADATA_URI_V4')
            if metadata_uri:
                logging.info(f"🔍 ECS Metadata URI: {metadata_uri}")
                try:
                    with urllib.request.urlopen(f"{metadata_uri}/task", timeout=5) as response:
                        task_metadata = json.loads(response.read().decode())
                    logging.info(f"🔍 ECS Task ARN: {task_metadata.get('TaskARN', 'Unknown')}")
                    logging.info(f"🔍 ECS Cluster: {task_metadata.get('Cluster', 'Unknown')}")
                    logging.info(f"🔍 ECS Availability Zone: {task_metadata.get('AvailabilityZone', 'Unknown')}")
                except Exception as e:
                    logging.warning(f"⚠️ Could not fetch ECS metadata: {e}")
            else:
                logging.info("🔍 ECS Metadata URI not available (not running in ECS)")
        except Exception as e:
            logging.warning(f"⚠️ Error checking ECS metadata: {e}")
        
        # Check AWS configuration
        logging.info("🔍 AWS Configuration:")
        logging.info(f"  AWS Region: {boto3.Session().region_name}")
        try:
            sts_client = boto3.client('sts')
            identity = sts_client.get_caller_identity()
            logging.info(f"  AWS Account: {identity.get('Account', 'Unknown')}")
            logging.info(f"  AWS User/Role: {identity.get('Arn', 'Unknown')}")
        except Exception as e:
            logging.warning(f"⚠️ Could not get AWS identity: {e}")
        
        # Validate CloudFormation Stack Outputs and Variable Passing
        logging.info("🔍 CloudFormation Stack Validation:")
        try:
            cf_client = boto3.client('cloudformation')
            
            # Check main app stack
            try:
                main_stack_name = 'stocks-app-stack'
                main_response = cf_client.describe_stacks(StackName=main_stack_name)
                main_stack = main_response['Stacks'][0]
                logging.info(f"  Main Stack Status: {main_stack['StackStatus']}")
                
                # Check for required outputs
                outputs = {output['OutputKey']: output['OutputValue'] for output in main_stack.get('Outputs', [])}
                required_outputs = ['VpcId', 'PrivateSubnetA', 'PrivateSubnetB', 'DatabaseUrl']
                for output_key in required_outputs:
                    if output_key in outputs:
                        logging.info(f"  ✅ {output_key}: {outputs[output_key]}")
                    else:
                        logging.warning(f"  ❌ Missing output: {output_key}")
                        
            except Exception as e:
                logging.warning(f"  ⚠️ Could not access main stack: {e}")
            
            # Check webapp stack
            try:
                webapp_stack_name = 'stocks-webapp-dev'
                webapp_response = cf_client.describe_stacks(StackName=webapp_stack_name)
                webapp_stack = webapp_response['Stacks'][0]
                logging.info(f"  Webapp Stack Status: {webapp_stack['StackStatus']}")
                
            except Exception as e:
                logging.warning(f"  ⚠️ Could not access webapp stack: {e}")
                
        except Exception as e:
            logging.warning(f"⚠️ CloudFormation validation error: {e}")
        
        # Validate Security Groups and Network Configuration
        logging.info("🔍 Security Group and Network Validation:")
        try:
            ec2_client = boto3.client('ec2')
            
            # Get VPC information
            vpc_id = os.environ.get('VPC_ID')
            if vpc_id:
                logging.info(f"  VPC ID: {vpc_id}")
                
                # Check VPC exists
                try:
                    vpc_response = ec2_client.describe_vpcs(VpcIds=[vpc_id])
                    vpc = vpc_response['Vpcs'][0]
                    logging.info(f"  ✅ VPC State: {vpc['State']}")
                    logging.info(f"  ✅ VPC CIDR: {vpc['CidrBlock']}")
                except Exception as e:
                    logging.error(f"  ❌ VPC validation error: {e}")
            else:
                logging.warning("  ⚠️ VPC_ID environment variable not set")
            
            # Check subnet configuration
            subnet_ids = []
            for subnet_env in ['SUBNET_A_ID', 'SUBNET_B_ID', 'PRIVATE_SUBNET_A', 'PRIVATE_SUBNET_B']:
                subnet_id = os.environ.get(subnet_env)
                if subnet_id:
                    subnet_ids.append(subnet_id)
                    logging.info(f"  Subnet {subnet_env}: {subnet_id}")
            
            if subnet_ids:
                try:
                    subnet_response = ec2_client.describe_subnets(SubnetIds=subnet_ids)
                    for subnet in subnet_response['Subnets']:
                        logging.info(f"  ✅ Subnet {subnet['SubnetId']}: {subnet['State']} (AZ: {subnet['AvailabilityZone']})")
                        logging.info(f"     CIDR: {subnet['CidrBlock']}, VPC: {subnet['VpcId']}")
                except Exception as e:
                    logging.error(f"  ❌ Subnet validation error: {e}")
            
            # Check security groups
            sg_ids = []
            for sg_env in ['SECURITY_GROUP_ID', 'ECS_SECURITY_GROUP', 'RDS_SECURITY_GROUP']:
                sg_id = os.environ.get(sg_env)
                if sg_id:
                    sg_ids.append(sg_id)
                    logging.info(f"  Security Group {sg_env}: {sg_id}")
            
            if sg_ids:
                try:
                    sg_response = ec2_client.describe_security_groups(GroupIds=sg_ids)
                    for sg in sg_response['SecurityGroups']:
                        logging.info(f"  ✅ Security Group {sg['GroupId']}: {sg['GroupName']}")
                        
                        # Check inbound rules for database access
                        for rule in sg['IpPermissions']:
                            if rule.get('FromPort') == 5432:  # PostgreSQL port
                                logging.info(f"     PostgreSQL Rule: Port {rule['FromPort']}, Protocol {rule['IpProtocol']}")
                                for source_sg in rule.get('UserIdGroupPairs', []):
                                    logging.info(f"       Source SG: {source_sg['GroupId']}")
                                for cidr in rule.get('IpRanges', []):
                                    logging.info(f"       Source CIDR: {cidr['CidrIp']}")
                                    
                except Exception as e:
                    logging.error(f"  ❌ Security group validation error: {e}")
                    
        except Exception as e:
            logging.warning(f"⚠️ Network validation error: {e}")
        
        # Network interface information
        logging.info("🔍 Network Configuration:")
        try:
            import netifaces
            interfaces = netifaces.interfaces()
            for interface in interfaces:
                addrs = netifaces.ifaddresses(interface)
                if netifaces.AF_INET in addrs:
                    for addr in addrs[netifaces.AF_INET]:
                        logging.info(f"  Interface {interface}: {addr['addr']}")
        except ImportError:
            logging.info("  netifaces not available, using basic socket info")
            import socket
            hostname = socket.gethostname()
            ip_address = socket.gethostbyname(hostname)
            logging.info(f"  Hostname: {hostname}")
            logging.info(f"  IP Address: {ip_address}")
        except Exception as e:
            logging.warning(f"⚠️ Could not get network info: {e}")

        # Connect to DB with enhanced error handling
        logging.info("🔌 Loading database configuration...")
        cfg = get_db_config()
        
        # Log detailed connection info for debugging
        logging.info(f"🔌 DB Connection Details:")
        logging.info(f"  Host: {cfg['host']}")
        logging.info(f"  Port: {cfg['port']}")
        logging.info(f"  Database: {cfg['dbname']}")
        logging.info(f"  User: {cfg['user']}")
        logging.info(f"  SSL Mode: require")
        
        # Get container IP for debugging
        import socket
        try:
            container_ip = socket.gethostbyname(socket.gethostname())
            logging.info(f"🔌 Container IP: {container_ip}")
        except Exception as e:
            logging.warning(f"⚠️ Could not determine container IP: {e}")
        
        # Download RDS CA certificate if not present
        import urllib.request
        import os
        
        ca_cert_path = '/tmp/rds-ca-2019-root.pem'
        if not os.path.exists(ca_cert_path):
            try:
                logging.info("📥 Downloading RDS CA certificate...")
                ca_cert_url = 'https://s3.amazonaws.com/rds-downloads/rds-ca-2019-root.pem'
                urllib.request.urlretrieve(ca_cert_url, ca_cert_path)
                logging.info(f"✅ Downloaded RDS CA certificate to {ca_cert_path}")
            except Exception as e:
                logging.warning(f"⚠️ Could not download RDS CA certificate: {e}")
                ca_cert_path = None
        else:
            logging.info(f"✅ Using existing RDS CA certificate at {ca_cert_path}")

        # Attempt connection with retry logic
        max_retries = 3
        retry_delay = 5
        
        for attempt in range(1, max_retries + 1):
            try:
                logging.info(f"🔌 Connection attempt {attempt}/{max_retries} to {cfg['host']}:{cfg['port']}")
                
                # Test basic connectivity first
                logging.info("🔌 Testing basic network connectivity...")
                test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                test_socket.settimeout(10)
                test_result = test_socket.connect_ex((cfg["host"], cfg["port"]))
                
                if test_result == 0:
                    logging.info("✅ Network connectivity test passed")
                    
                    # Get additional network info for successful connection
                    local_addr = test_socket.getsockname()
                    peer_addr = test_socket.getpeername()
                    logging.info(f"🔍 Local socket: {local_addr[0]}:{local_addr[1]}")
                    logging.info(f"🔍 Remote socket: {peer_addr[0]}:{peer_addr[1]}")
                    
                else:
                    logging.error(f"❌ Network connectivity test failed with code: {test_result}")
                    
                    # Diagnose network connectivity issues
                    if test_result == 111:  # Connection refused
                        logging.error("🔍 DIAGNOSIS: Connection refused - PostgreSQL may not be running or not accepting connections")
                    elif test_result == 113:  # No route to host
                        logging.error("🔍 DIAGNOSIS: No route to host - network routing or security group issue")
                    elif test_result == 110:  # Connection timed out
                        logging.error("🔍 DIAGNOSIS: Connection timeout - likely security group blocking or RDS not accessible")
                    else:
                        logging.error(f"🔍 DIAGNOSIS: Unknown network error code {test_result}")
                        
                test_socket.close()
                
                # Clean connection pattern (auto-negotiate SSL) - Group 1 test v2
                logging.info(f"🔌 Connection attempt {attempt}/{max_retries} to {cfg['host']}:{cfg['port']}")
                logging.info("✅ Clean connection pattern: Auto-negotiate SSL v2")
                
                conn = psycopg2.connect(
                    host=cfg["host"], port=cfg["port"],
                    user=cfg["user"], password=cfg["password"],
                    dbname=cfg["dbname"],
                    cursor_factory=RealDictCursor
                )
                
                logging.info("✅ Database connection established successfully")
                break
                
            except psycopg2.OperationalError as e:
                error_msg = str(e)
                logging.error(f"❌ PostgreSQL connection error (attempt {attempt}/{max_retries}): {error_msg}")
                
                # Parse specific error types
                if "pg_hba.conf" in error_msg:
                    logging.error("🔍 DIAGNOSIS: pg_hba.conf entry missing - this is a server-side PostgreSQL configuration issue")
                    if "no encryption" in error_msg:
                        logging.error("🔍 DIAGNOSIS: Server requires encrypted connection")
                elif "Connection refused" in error_msg:
                    logging.error("🔍 DIAGNOSIS: PostgreSQL server not accepting connections on this port")
                elif "timeout" in error_msg:
                    logging.error("🔍 DIAGNOSIS: Connection timeout - network or server performance issue")
                
                if attempt < max_retries:
                    logging.info(f"⏳ Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    logging.error(f"❌ All {max_retries} connection attempts failed")
                    raise
                    
            except Exception as e:
                logging.error(f"❌ Unexpected connection error (attempt {attempt}/{max_retries}): {e}")
                if attempt < max_retries:
                    logging.info(f"⏳ Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    raise
        conn.autocommit = False
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Recreate aaii_sentiment table
        logging.info("Recreating aaii_sentiment table...")
        cur.execute("DROP TABLE IF EXISTS aaii_sentiment;")
        cur.execute("""
            CREATE TABLE aaii_sentiment (
                id          SERIAL PRIMARY KEY,
                date        DATE         NOT NULL UNIQUE,
                bullish     DOUBLE PRECISION,
                neutral     DOUBLE PRECISION,
                bearish     DOUBLE PRECISION,
                fetched_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()

        # Load sentiment data
        total, inserted, failed = load_sentiment_data(cur, conn)

        # Record last run
        cur.execute("""
          INSERT INTO last_updated (script_name, last_run)
          VALUES (%s, NOW())
          ON CONFLICT (script_name) DO UPDATE
            SET last_run = EXCLUDED.last_run;
        """, (SCRIPT_NAME,))
        conn.commit()

        peak = get_rss_mb()
        logging.info(f"[MEM] peak RSS: {peak:.1f} MB")
        logging.info(f"AAII Sentiment — total: {total}, inserted: {inserted}, failed: {len(failed)}")

        cur.close()
        conn.close()
        logging.info("All done.")
    except Exception as e:
        logging.error(f"❌ CRITICAL ERROR in AAII loader: {e}")
        import traceback
        logging.error(f"❌ Full traceback: {traceback.format_exc()}")
        sys.exit(1) 