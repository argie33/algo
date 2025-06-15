#!/usr/bin/env python3
import psycopg2
from psycopg2.extras import RealDictCursor
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def get_db_config():
    return {
        'host': 'stocks-db-cluster.cluster-cjj7t6dgjjwj.us-east-1.rds.amazonaws.com',
        'port': 5432,
        'database': 'stocksdb',
        'user': 'postgres',
        'password': 'e^?6b&q-9@nMJVZ4',
        'sslmode': 'require'
    }

def check_analyst_data():
    try:
        config = get_db_config()
        conn = psycopg2.connect(**config)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Check total count
        cur.execute("SELECT COUNT(*) as total FROM analyst_upgrade_downgrade")
        total = cur.fetchone()
        print(f"Total records: {total['total']}")
        
        # Check sample data
        cur.execute("""
            SELECT symbol, firm, action, from_grade, to_grade, date 
            FROM analyst_upgrade_downgrade 
            ORDER BY date DESC 
            LIMIT 10
        """)
        
        results = cur.fetchall()
        print("\nSample records:")
        for row in results:
            print(f"Symbol: {row['symbol']}, Firm: {row['firm']}, Action: {row['action']}, "
                  f"From: {row['from_grade']}, To: {row['to_grade']}, Date: {row['date']}")
        
        # Check for empty fields
        cur.execute("""
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN firm IS NULL OR firm = '' THEN 1 END) as empty_firm,
                COUNT(CASE WHEN action IS NULL OR action = '' THEN 1 END) as empty_action,
                COUNT(CASE WHEN from_grade IS NULL OR from_grade = '' THEN 1 END) as empty_from_grade,
                COUNT(CASE WHEN to_grade IS NULL OR to_grade = '' THEN 1 END) as empty_to_grade
            FROM analyst_upgrade_downgrade
        """)
        
        stats = cur.fetchone()
        print(f"\nField statistics:")
        print(f"Total: {stats['total']}")
        print(f"Empty firm: {stats['empty_firm']}")
        print(f"Empty action: {stats['empty_action']}")
        print(f"Empty from_grade: {stats['empty_from_grade']}")
        print(f"Empty to_grade: {stats['empty_to_grade']}")
        
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_analyst_data()
