import sys
sys.path.insert(0, '.')
from utils.db.connection import get_db_connection

with get_db_connection() as conn:
    cur = conn.cursor()
    cur.execute("""
    SELECT column_name, data_type
    FROM information_schema.columns
    WHERE table_name='algo_positions'
    ORDER BY ordinal_position
    """)
    
    columns = cur.fetchall()
    print("Columns in algo_positions:")
    for col_name, data_type in columns:
        print(f"  {col_name}: {data_type}")
