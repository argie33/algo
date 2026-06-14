from utils.database_context import DatabaseContext

with DatabaseContext('read') as cur:
    cur.execute('''
        SELECT DISTINCT status FROM data_loader_status ORDER BY status
    ''')
    rows = cur.fetchall()
    print(f'Unique status values in database:')
    for row in rows:
        print(f'  "{row[0]}"')

    # Check if there are any with non-COMPLETED status recently
    cur.execute('''
        SELECT table_name, status, last_updated
        FROM data_loader_status
        WHERE status IS NOT NULL AND status != 'COMPLETED'
        ORDER BY last_updated DESC
        LIMIT 20
    ''')
    rows = cur.fetchall()
    if rows:
        print(f'\nNon-COMPLETED loaders:')
        for row in rows:
            print(f'  {row[0]:30} {row[1]:15} {str(row[2])[:19]}')
