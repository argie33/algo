require('dotenv').config({ path: '.env.local' });
const { query } = require('./webapp/lambda/utils/database');

async function test() {
  try {
    const result = await query(`
      SELECT table_name
      FROM information_schema.tables
      WHERE table_schema = 'public'
      AND table_name LIKE 'commodity%'
      ORDER BY table_name
    `);

    console.log('Commodity tables:');
    result.rows.forEach(row => console.log(' -', row.table_name));

    // Check technicals count
    const techResult = await query(`SELECT COUNT(*) as count FROM commodity_technicals`);
    console.log(`\nTechnicals records: ${techResult.rows[0].count}`);

  } catch (error) {
    console.error('Error:', error.message);
  }
  process.exit(0);
}

test();
