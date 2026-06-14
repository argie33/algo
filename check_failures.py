from utils.database_context import DatabaseContext

with DatabaseContext('read') as cur:
    cur.execute('''
        SELECT table_name, status, error_message, last_updated
        FROM data_loader_status
        WHERE status IN ('FAILED', 'ERROR', 'TIMEOUT')
        ORDER BY last_updated DESC
        LIMIT 10
    ''')
    rows = cur.fetchall()
    if rows:
        print('Recent loader failures:')
        for row in rows:
            error_str = (row[2][:60] if row[2] else "No error message")
            print(f'{row[0]:30} {row[1]:10} {str(row[3])[:19]} {error_str}')
    else:
        print('No recorded failures - all loaders currently OK or no status')
