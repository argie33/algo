const { query } = require('./webapp/lambda/utils/database');

process.env.DB_HOST = 'localhost';
process.env.DB_PORT = '5432';
process.env.DB_USER = 'stocks';
process.env.DB_PASSWORD = 'bed0elAn';
process.env.DB_NAME = 'stocks';
process.env.DB_SSL = 'false';

(async () => {
  try {
    console.log('Testing database connection...');
    const result = await query('SELECT 1 as test', []);
    console.log('✅ Connection OK:', result.rows[0]);

    console.log('\nTesting query performance...');
    const start = Date.now();
    const result2 = await query('SELECT COUNT(*) as cnt FROM stock_symbols', []);
    console.log(`✅ Query OK (${Date.now() - start}ms): ${result2.rows[0].cnt} symbols`);

    console.log('\nTesting long-running query...');
    const start2 = Date.now();
    const result3 = await query('SELECT * FROM company_profile LIMIT 10', []);
    console.log(`✅ Long query OK (${Date.now() - start2}ms): ${result3.rows.length} rows`);

    process.exit(0);
  } catch (err) {
    console.error('❌ Error:', err.message);
    process.exit(1);
  }
})();
