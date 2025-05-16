import boto3
from botocore.exceptions import ClientError

def handler(event, context):
    rds = boto3.client('rds')
    try:
        # Attempt to stop; if already stopped or stopping, ignore
        rds.stop_db_instance(DBInstanceIdentifier='stocks')
    except ClientError as e:
        # Ignore "invalid state" errors (already stopping or stopped)
        if e.response.get('Error', {}).get('Code') == 'InvalidDBInstanceState':
            return
        # Propagate any other errors
        raise
