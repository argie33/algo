const { Pool } = require('pg');
require('dotenv').config({ path: '.env.local' });

const pool = new Pool({
  host: process.env.DB_HOST,
  port: process.env.DB_PORT,
  user: process.env.DB_USER,
  password: process.env.DB_PASSWORD,
  database: process.env.DB_NAME,
});

async function check() {
  try {
    const tables = ['stock_symbols', 'buy_sell_daily', 'price_daily', 'technical_data_daily'];

    for (const table of tables) {
      const result = await pool.query(`
        SELECT column_name FROM information_schema.columns
        WHERE table_name='${table}'
        ORDER BY column_name
      `);

      console.log(`\n${table}:`);
      result.rows.forEach(r => console.log(`  - ${r.column_name}`));
    }

    process.exit(0);
  } catch (err) {
    console.error('Error:', err.message);
    process.exit(1);
  }
}

check();
