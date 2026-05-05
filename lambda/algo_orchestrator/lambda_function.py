"""
Lambda handler for algo orchestration.
Runs the complete EOD workflow: patrol → remediation → execution.
Triggered by EventBridge scheduler (5:30pm ET daily).

Cold-start optimizations:
  - Lazy-load AWS clients (only initialize when needed)
  - Pre-warm critical Python imports at top level
  - Track cold-start duration via CloudWatch metrics
  - Use subprocess timeouts to prevent hanging processes
"""

import json
import os
import sys
import subprocess
from datetime import datetime
import time

# Pre-warm critical imports (avoid cold-start overhead)
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global clients initialized on first use (lazy-loaded)
_aws_clients = {}

# Environment
EXECUTION_MODE = os.getenv('EXECUTION_MODE', 'paper')
DRY_RUN = os.getenv('DRY_RUN_MODE', 'true').lower() == 'true'
LAMBDA_FUNCTION_NAME = os.getenv('AWS_LAMBDA_FUNCTION_NAME', 'algo-orchestrator')
SNS_TOPIC_ARN = os.getenv('ALERT_SNS_TOPIC_ARN', '')
CLOUDWATCH_LOG_GROUP = f'/aws/lambda/{LAMBDA_FUNCTION_NAME}'

# Cold-start tracking
_cold_start = True
_init_start_time = time.time()


def get_boto3_client(service_name):
    """Lazy-load boto3 clients on first use to reduce cold-start time."""
    global _aws_clients
    if service_name not in _aws_clients:
        import boto3
        _aws_clients[service_name] = boto3.client(service_name)
    return _aws_clients[service_name]


def get_database_credentials():
    """Fetch database credentials from AWS Secrets Manager using ARN."""
    try:
        secrets = get_boto3_client('secretsmanager')
        secret_arn = os.getenv('DATABASE_SECRET_ARN')
        if not secret_arn:
            raise ValueError('DATABASE_SECRET_ARN environment variable not set')
        response = secrets.get_secret_value(SecretId=secret_arn)
        creds = json.loads(response['SecretString'])
        return {
            'DB_HOST': creds['host'],
            'DB_PORT': str(creds['port']),
            'DB_USER': creds['username'],
            'DB_PASSWORD': creds['password'],
            'DB_NAME': creds['dbname'],
        }
    except Exception as e:
        log_error(f"Failed to get database credentials: {str(e)}")
        raise


def get_algo_runtime_secrets():
    """Fetch Alpaca API keys + algo runtime config from Secrets Manager.

    Returns env-var dict to inject. If ALGO_SECRETS_ARN is unset or fetch fails,
    returns {} so the Lambda falls back to paper-trading-without-keys mode.
    """
    secret_arn = os.getenv('ALGO_SECRETS_ARN', '').strip()
    if not secret_arn:
        log_to_cloudwatch("ALGO_SECRETS_ARN not set — paper-only mode without Alpaca keys")
        return {}
    try:
        secrets = get_boto3_client('secretsmanager')
        response = secrets.get_secret_value(SecretId=secret_arn)
        payload = json.loads(response['SecretString'])
        # Map secret JSON keys to env var names the algo code expects
        return {
            'APCA_API_KEY_ID': payload.get('APCA_API_KEY_ID', ''),
            'APCA_API_SECRET_KEY': payload.get('APCA_API_SECRET_KEY', ''),
            'APCA_API_BASE_URL': payload.get('APCA_API_BASE_URL', 'https://paper-api.alpaca.markets'),
            'ALPACA_PAPER_TRADING': payload.get('ALPACA_PAPER_TRADING', 'true'),
        }
    except Exception as e:
        log_to_cloudwatch(f"Could not read algo secret (continuing without Alpaca keys): {e}", 'WARN')
        return {}


def log_to_cloudwatch(message, level='INFO'):
    """Log message to CloudWatch."""
    timestamp = datetime.utcnow().isoformat()
    print(f"[{timestamp}] [{level}] {message}")


def log_error(message):
    """Log error and send alert."""
    log_to_cloudwatch(message, 'ERROR')
    send_alert('ERROR', message)


def send_alert(status, message):
    """Send SNS alert on success/failure."""
    if not SNS_TOPIC_ARN:
        return

    try:
        sns = get_boto3_client('sns')
        subject = f"Algo Orchestrator {status} - {datetime.utcnow().isoformat()}"
        body = f"""
Algo Orchestrator Execution {status}

Time: {datetime.utcnow().isoformat()}
Execution Mode: {EXECUTION_MODE}
Dry Run: {DRY_RUN}

Message:
{message}

View logs: https://console.aws.amazon.com/cloudwatch/home#logsV2:logs-insights$3FqueryDetail$3D~(end~0~start~-3600~timeType~'RELATIVE~unit~'seconds~editorString~'fields*20*40timestamp*2c*20*40message*0a*7c*20filter*20*40message*20like*20*2fExecution*20failed*2f~source~('{CLOUDWATCH_LOG_GROUP}'))
"""
        sns.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject=subject,
            Message=body
        )
    except Exception as e:
        log_to_cloudwatch(f"Failed to send alert: {str(e)}", 'WARN')


def run_command(cmd, description, cwd=None):
    """Run a shell command and capture output."""
    try:
        log_to_cloudwatch(f"Running: {description}")
        # Use Lambda's task root directory if cwd not specified
        if cwd is None:
            cwd = os.environ.get('LAMBDA_TASK_ROOT', '/var/task')

        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=900  # 15 min timeout
        )

        if result.stdout:
            log_to_cloudwatch(f"Output: {result.stdout}")
        if result.stderr:
            log_to_cloudwatch(f"Stderr: {result.stderr}", 'WARN')

        if result.returncode != 0:
            raise Exception(f"Command failed with exit code {result.returncode}")

        return result.stdout
    except subprocess.TimeoutExpired:
        raise Exception(f"Command timed out: {description}")
    except Exception as e:
        log_error(f"Command failed: {description} — {str(e)}")
        raise


def lambda_handler(event, context):
    """
    Main Lambda handler.
    Runs: patrol → remediation → orchestrator
    Optimized for cold-start performance with lazy-loaded AWS clients.
    """
    global _cold_start
    start_time = datetime.utcnow()
    # Lambda context exposes aws_request_id (not request_id)
    execution_id = getattr(context, 'aws_request_id', None) if context else None
    execution_id = execution_id or 'manual'

    try:
        # Track cold-start performance
        init_duration = 0
        if _cold_start:
            init_duration = time.time() - _init_start_time
            _cold_start = False
            log_to_cloudwatch(f"⚠️  Cold start detected (init time: {init_duration:.2f}s)")
            # Publish cold-start metric to CloudWatch
            try:
                cloudwatch = get_boto3_client('cloudwatch')
                cloudwatch.put_metric_data(
                    Namespace='AlgoTrading',
                    MetricData=[
                        {
                            'MetricName': 'LambdaColdStartDuration',
                            'Value': init_duration,
                            'Unit': 'Seconds',
                        }
                    ]
                )
            except Exception as e:
                log_to_cloudwatch(f"Could not publish cold-start metric: {e}", 'WARN')

        log_to_cloudwatch("=" * 80)
        log_to_cloudwatch(f"Algo Orchestrator Starting (Execution ID: {execution_id})")
        log_to_cloudwatch(f"Execution Mode: {EXECUTION_MODE}")
        log_to_cloudwatch(f"Dry Run: {DRY_RUN}")
        log_to_cloudwatch("=" * 80)

        # Get database credentials
        log_to_cloudwatch("Step 1: Fetching database credentials...")
        db_creds = get_database_credentials()
        log_to_cloudwatch("Database credentials retrieved")

        # Get Alpaca algo runtime secret (best-effort; empty dict if absent)
        algo_secrets = get_algo_runtime_secrets()
        if algo_secrets.get('APCA_API_KEY_ID'):
            log_to_cloudwatch("Alpaca credentials retrieved")

        # Set environment for subprocess calls
        env = os.environ.copy()
        env.update(db_creds)
        env.update(algo_secrets)
        env['EXECUTION_MODE'] = EXECUTION_MODE
        env['DRY_RUN'] = 'true' if DRY_RUN else 'false'

        # Step 1: Pre-flight checks
        log_to_cloudwatch("\n" + "=" * 80)
        log_to_cloudwatch("Step 2: Pre-flight Verification")
        log_to_cloudwatch("=" * 80)
        try:
            # Run lightweight component verification
            output = run_command(
                'python3 -c "import algo_config; print(algo_config.EXECUTION_MODE)"',
                "Verify algo configuration"
            )
            log_to_cloudwatch("✅ Algo configuration verified")
        except Exception as e:
            log_error(f"Pre-flight check failed: {str(e)}")
            raise

        # Step 2: Pre-load patrol
        log_to_cloudwatch("\n" + "=" * 80)
        log_to_cloudwatch("Step 3: Pre-Load Data Patrol")
        log_to_cloudwatch("=" * 80)
        try:
            patrol_output = run_command(
                'python3 algo_data_patrol.py --quick',
                "Run quick patrol check"
            )
            if 'CRITICAL' in patrol_output:
                raise Exception("Patrol detected CRITICAL issues before load")
            log_to_cloudwatch("✅ Pre-load patrol passed")
        except Exception as e:
            log_error(f"Pre-load patrol failed: {str(e)}")
            raise

        # Step 3 (skipped in Lambda): EOD loaders run as ECS scheduled tasks separately.
        # The Lambda zip is intentionally minimal (no pandas/polars), so it can't run
        # load*.py files. ECS tasks defined in template-app-ecs-tasks.yml own data
        # loading; this Lambda assumes the data is already fresh by the time the
        # 5:30pm ET schedule fires. The post-load patrol below verifies that.
        log_to_cloudwatch("\n" + "=" * 80)
        log_to_cloudwatch("Step 4: EOD data loading (delegated to ECS — skipped here)")
        log_to_cloudwatch("=" * 80)

        # Step 4: Post-load patrol
        log_to_cloudwatch("\n" + "=" * 80)
        log_to_cloudwatch("Step 5: Post-Load Data Patrol")
        log_to_cloudwatch("=" * 80)
        try:
            patrol_output = run_command(
                'python3 algo_data_patrol.py',
                "Run full patrol validation"
            )
            if 'CRITICAL' in patrol_output:
                raise Exception("Patrol detected CRITICAL issues after load")
            log_to_cloudwatch("✅ Post-load patrol passed")
        except Exception as e:
            log_error(f"Post-load patrol failed: {str(e)}")
            raise

        # Step 5: Auto-remediation
        log_to_cloudwatch("\n" + "=" * 80)
        log_to_cloudwatch("Step 6: Auto-Remediation")
        log_to_cloudwatch("=" * 80)
        try:
            run_command(
                'python3 algo_data_remediation.py',
                "Run auto-remediation"
            )
            log_to_cloudwatch("✅ Auto-remediation complete")
        except Exception as e:
            log_to_cloudwatch(f"⚠️  Remediation encountered issues: {str(e)}", 'WARN')
            # Don't fail — continue to orchestrator

        # Step 6: Execute algo
        log_to_cloudwatch("\n" + "=" * 80)
        log_to_cloudwatch("Step 7: Execute Algo Orchestrator")
        log_to_cloudwatch("=" * 80)
        try:
            if DRY_RUN:
                log_to_cloudwatch("Running in DRY-RUN mode (preview only, no trades executed)")
                orchestrator_cmd = 'python3 algo_orchestrator.py --dry-run'
            else:
                log_to_cloudwatch(f"Running in LIVE mode (execution_mode={EXECUTION_MODE})")
                orchestrator_cmd = 'python3 algo_orchestrator.py'

            orchestrator_output = run_command(orchestrator_cmd, "Execute algo orchestrator")
            log_to_cloudwatch("✅ Algo orchestrator completed")

            # Extract trade summary
            if 'trades' in orchestrator_output.lower():
                log_to_cloudwatch(f"Trade Summary: {orchestrator_output}")

        except Exception as e:
            log_error(f"Orchestrator failed: {str(e)}")
            raise

        # Success
        elapsed = (datetime.utcnow() - start_time).total_seconds()
        log_to_cloudwatch("\n" + "=" * 80)
        log_to_cloudwatch(f"✅ Execution completed successfully ({elapsed:.1f}s)")
        log_to_cloudwatch("=" * 80)

        send_alert('SUCCESS', f"Algo orchestrator completed successfully.\nElapsed time: {elapsed:.1f}s")

        return {
            'statusCode': 200,
            'body': json.dumps({
                'success': True,
                'execution_id': execution_id,
                'elapsed_seconds': elapsed,
                'execution_mode': EXECUTION_MODE,
                'dry_run': DRY_RUN,
                'timestamp': start_time.isoformat(),
            })
        }

    except Exception as e:
        elapsed = (datetime.utcnow() - start_time).total_seconds()
        error_msg = f"Execution failed after {elapsed:.1f}s: {str(e)}"
        log_to_cloudwatch("\n" + "=" * 80)
        log_to_cloudwatch(f"❌ {error_msg}")
        log_to_cloudwatch("=" * 80)

        send_alert('FAILURE', error_msg)

        return {
            'statusCode': 500,
            'body': json.dumps({
                'success': False,
                'execution_id': execution_id,
                'error': str(e),
                'elapsed_seconds': elapsed,
                'timestamp': start_time.isoformat(),
            })
        }
