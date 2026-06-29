import json
import psycopg2
import os
from datetime import date


def lambda_handler(event, context):
    try:
        conn = psycopg2.connect(
            host=os.environ['DB_HOST'],
            user=os.environ['DB_USER'],
            password=os.environ['DB_PASSWORD'],
            database=os.environ.get('DB_NAME', 'stocks'),
            port=int(os.environ.get('DB_PORT', 5432)),
            sslmode='require'
        )
        cur = conn.cursor()
        cur.execute('DELETE FROM economic_data WHERE series_id = %s', ('DXY_ICE',))
        cur.execute(
            'INSERT INTO economic_data (series_id, date, value) VALUES (%s, %s, %s)',
            ('DXY_ICE', date.today().isoformat(), 101.13)
        )
        conn.commit()
        cur.close()
        conn.close()
        return {"statusCode": 200, "body": json.dumps({"success": True, "message": "Seeded DXY_ICE"})}
    except Exception as e:
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}
