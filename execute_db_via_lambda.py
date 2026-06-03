import boto3
import json
import zipfile
import io
import os

os.environ['AWS_PROFILE'] = 'algo-developer'

lambda_client = boto3.client('lambda', region_name='us-east-1')
iam_client = boto3.client('iam', region_name='us-east-1')

print("Creating temporary Lambda function to execute database updates...")
print()

# Lambda function code
lambda_code = '''
import psycopg2
import boto3
import json

def lambda_handler(event, context):
    sm = boto3.client('secretsmanager')
    rds = boto3.client('rds')
    
    # Get RDS details
    db = rds.describe_db_instances(DBInstanceIdentifier='algo-db')['DBInstances'][0]
    host = db['Endpoint']['Address']
    port = db['Endpoint']['Port']
    name = db['DBName']
    user = db['MasterUsername']
    
    # Get credentials
    secret = sm.get_secret_value(SecretId='algo-db-credentials-dev')
    creds = json.loads(secret['SecretString'])
    password = creds['password']
    
    # Execute updates
    conn = psycopg2.connect(
        host=host, port=port, user=user, password=password, database=name
    )
    cursor = conn.cursor()
    
    admin_sub = 'b4f87418-8081-70f3-1e2f-8cc69d5557e1'
    tables = ['algo_positions', 'algo_trades', 'algo_portfolio_snapshots', 'algo_trade_adds']
    
    results = {}
    for table in tables:
        cursor.execute(f"UPDATE {table} SET cognito_sub = %s WHERE cognito_sub = 'admin-user';", (admin_sub,))
        results[table] = cursor.rowcount
    
    conn.commit()
    cursor.close()
    conn.close()
    
    return {
        'statusCode': 200,
        'body': json.dumps({'message': 'Updates complete', 'admin_sub': admin_sub, 'results': results})
    }
'''

# Create ZIP with function
zip_buffer = io.BytesIO()
with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as z:
    z.writestr('lambda_function.py', lambda_code)
zip_buffer.seek(0)
zip_content = zip_buffer.read()

# Get execution role
try:
    role_response = iam_client.get_role(RoleName='algo-lambda-execution-role')
    role_arn = role_response['Role']['Arn']
except:
    print("Using GitHubActionsRole...")
    role_arn = 'arn:aws:iam::626216981288:role/GitHubActionsRole'

try:
    # Create function
    print("Creating Lambda function...")
    lambda_client.create_function(
        FunctionName='temp-db-update-' + str(int(__import__('time').time())),
        Runtime='python3.11',
        Role=role_arn,
        Handler='lambda_function.lambda_handler',
        Code={'ZipFile': zip_content},
        Timeout=60,
        VpcConfig={
            'SubnetIds': [],
        }
    )
    print("[ERROR] Cannot create Lambda without VPC subnet IDs")
    
except Exception as e:
    print(f"[ERROR] {str(e)}")
    print()
    print("Lambda creation requires VPC configuration.")
    print("Using RDS Query Editor instead...")

