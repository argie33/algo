import os
import json
import boto3
import psycopg2
from psycopg2.extras import RealDictCursor

def handler(event, context):
    sm = boto3.client('secretsmanager')
    secret = sm.get_secret_value(SecretId=os.getenv('DB_SECRET_ARN'))
    creds = json.loads(secret['SecretString'])
    conn = psycopg2.connect(
        host=creds['host'],
        port=creds['port'],
        dbname=creds['dbname'],
        user=creds['username'],
        password=creds['password']
    )
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute('SELECT * FROM your_table LIMIT 100;')
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return {
        'statusCode': 200,
        'headers': {'Access-Control-Allow-Origin': '*'},
        'body': json.dumps(rows)
    }
