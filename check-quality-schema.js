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
    const result = await pool.query(`
      SELECT column_name, data_type FROM information_schema.columns
      WHERE table_name='quality_metrics'
      ORDER BY column_name
    `);

    console.log('Columns in quality_metrics:');
    result.rows.forEach(r => console.log(`  ${r.column_name} (${r.data_type})`));

    // Check a sample row
    const sample = await pool.query('SELECT * FROM quality_metrics LIMIT 1');
    console.log('\nSample row keys:', Object.keys(sample.rows[0] || {}));

    process.exit(0);
  } catch (err) {
    console.error('Error:', err.message);
    process.exit(1);
  }
}

check();
