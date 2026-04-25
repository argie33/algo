import os
from dotenv import load_dotenv
from pathlib import Path
import psycopg2

load_dotenv(Path('.') / '.env.local')

conn = psycopg2.connect(
    host=os.getenv('DB_HOST'),
    port=os.getenv('DB_PORT'),
    user=os.getenv('DB_USER'),
    password=os.getenv('DB_PASSWORD'),
    database=os.getenv('DB_NAME')
)
cursor = conn.cursor()

tables = [
    'annual_balance_sheet', 'sector_ranking', 'sector_performance',
    'industry_ranking', 'company_profile', 'key_metrics',
    'technical_data_weekly', 'technical_data_monthly'
]

for table in tables:
    try:
        cursor.execute(f'SELECT COUNT(*) FROM {table}')
        count = cursor.fetchone()[0]
        print(f'{table.ljust(30)} : {count}')
    except:
        print(f'{table.ljust(30)} : NOT FOUND')

conn.close()
