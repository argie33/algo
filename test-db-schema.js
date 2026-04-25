require('dotenv').config({ path: '.env.local' });
const pg = require('pg');

const config = {
  host: process.env.DB_HOST || 'localhost',
  port: process.env.DB_PORT || 5432,
  user: process.env.DB_USER || 'stocks',
  password: process.env.DB_PASSWORD,
  database: process.env.DB_NAME || 'stocks'
};

console.log('Connecting to:', { ...config, password: '***' });

const client = new pg.Client(config);

(async () => {
  try {
    await client.connect();
    
    const result = await client.query(`
      SELECT column_name, data_type
      FROM information_schema.columns
      WHERE table_name = 'annual_balance_sheet'
      ORDER BY ordinal_position
    `);
    
    console.log('\nAnnual Balance Sheet Columns:');
    result.rows.forEach(row => {
      console.log(`  ${row.column_name}: ${row.data_type}`);
    });
    
    // Also get a sample row
    const sample = await client.query(
      'SELECT * FROM annual_balance_sheet WHERE symbol = $1 LIMIT 1',
      ['AAPL']
    );
    
    if (sample.rows.length > 0) {
      console.log('\nSample AAPL row keys:', Object.keys(sample.rows[0]));
    }
    
    await client.end();
  } catch (err) {
    console.error('Error:', err.message);
    process.exit(1);
  }
})();
