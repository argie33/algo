const pg = require('pg');

const config = {
  host: 'localhost',
  port: 5432,
  user: 'stocks',
  password: 'bed0elAn',
  database: 'stocks'
};

const client = new pg.Client(config);

async function checkSchema() {
  try {
    await client.connect();

    console.log('=== SCHEMA ANALYSIS ===\n');

    // Check sector_ranking structure
    console.log('1️⃣  sector_ranking table:');
    try {
      const sectorCols = await client.query(`
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_name = 'sector_ranking'
        ORDER BY ordinal_position
      `);

      if (sectorCols.rows.length > 0) {
        console.log('  Columns found:');
        sectorCols.rows.forEach(r => {
          console.log(`    - ${r.column_name} (${r.data_type})`);
        });
      } else {
        console.log('  ✗ Table exists but no columns');
      }
    } catch (e) {
      console.log('  ✗ Table error:', e.message.split('\n')[0]);
    }

    // Check earnings_estimates
    console.log('\n2️⃣  earnings_estimates table:');
    try {
      const countRes = await client.query('SELECT COUNT(*) FROM earnings_estimates');
      console.log(`  Data: ${countRes.rows[0].count} rows`);
    } catch (e) {
      console.log('  ✗ Error:', e.message.split('\n')[0]);
    }

    // Check company_profile
    console.log('\n3️⃣  company_profile table:');
    try {
      const countRes = await client.query('SELECT COUNT(*) FROM company_profile');
      console.log(`  Data: ${countRes.rows[0].count} rows`);
    } catch (e) {
      console.log('  ✗ Error:', e.message.split('\n')[0]);
    }

    // List all tables
    console.log('\n4️⃣  All tables with row counts:');
    const allTables = await client.query(`
      SELECT tablename
      FROM pg_tables
      WHERE schemaname = 'public'
      ORDER BY tablename
    `);

    const tableList = [];
    for (const tbl of allTables.rows) {
      try {
        const countRes = await client.query(`SELECT COUNT(*) FROM "${tbl.tablename}"`);
        const count = countRes.rows[0].count;
        tableList.push({ name: tbl.tablename, count });
      } catch (e) {
        tableList.push({ name: tbl.tablename, count: 'ERROR' });
      }
    }

    // Show summary
    console.log(`  Total ${tableList.length} tables`);
    const withData = tableList.filter(t => typeof t.count === 'number' && t.count > 0);
    console.log(`  ${withData.length} tables with data\n`);

    withData.slice(0, 30).forEach(t => {
      const status = t.count > 10000 ? '✓' : (t.count === 0 ? '⚠️' : '⚡');
      console.log(`  ${status} ${t.name}: ${t.count}`);
    });

  } catch (error) {
    console.error('Error:', error.message);
  } finally {
    await client.end();
  }
}

checkSchema();
