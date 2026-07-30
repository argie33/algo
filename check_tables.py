import sys
sys.path.insert(0, '.')
from utils.db.connection import get_db_connection

with get_db_connection() as conn:
    cur = conn.cursor()
    cur.execute("""
    SELECT table_name 
    FROM information_schema.tables 
    WHERE table_schema='public'
    ORDER BY table_name
    """)
    
    tables = cur.fetchall()
    print("Tables in database:")
    for (table_name,) in tables:
        print(f"  {table_name}")
