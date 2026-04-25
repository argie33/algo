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
    console.log('\n📋 buy_sell_daily TABLE SCHEMA:\n');

    const result = await pool.query(`
      SELECT column_name, data_type, is_nullable
      FROM information_schema.columns
      WHERE table_name='buy_sell_daily'
      ORDER BY ordinal_position
    `);

    result.rows.forEach((r, i) => {
      console.log(`${i+1}. ${r.column_name.padEnd(30)} ${r.data_type.padEnd(15)} ${r.is_nullable === 'NO' ? 'NOT NULL' : 'nullable'}`);
    });

    // Show primary keys
    const pk = await pool.query(`
      SELECT constraint_name FROM information_schema.table_constraints
      WHERE table_name='buy_sell_daily' AND constraint_type='PRIMARY KEY'
    `);

    console.log(`\nPrimary Key Constraints:`, pk.rows.map(r => r.constraint_name));

    // Show indexes
    const idx = await pool.query(`
      SELECT indexname, indexdef FROM pg_indexes
      WHERE tablename='buy_sell_daily'
    `);

    console.log(`\nIndexes:`);
    idx.rows.forEach(r => console.log(`  - ${r.indexname}`));

    process.exit(0);
  } catch (err) {
    console.error('Error:', err.message);
    process.exit(1);
  }
}

check();
