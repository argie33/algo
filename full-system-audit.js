const pg = require('pg');

const config = {
  host: 'localhost',
  port: 5432,
  user: 'stocks',
  password: 'bed0elAn',
  database: 'stocks'
};

const client = new pg.Client(config);

async function runAudit() {
  try {
    await client.connect();
    console.log('🔍 COMPREHENSIVE SYSTEM AUDIT\n');

    // 1. TABLE SUMMARY
    console.log('📊 DATABASE TABLES:');
    const tableRes = await client.query(`
      SELECT
        schemaname,
        COUNT(*) as table_count
      FROM pg_tables
      WHERE schemaname = 'public'
      GROUP BY schemaname
    `);

    if (tableRes.rows.length > 0) {
      const row = tableRes.rows[0];
      console.log(`  ✓ ${row.table_count} tables in public schema`);

      // Count rows in key tables
      const keyTables = ['stock_symbols', 'daily_prices', 'earnings_history', 'earnings_estimates', 'company_profile', 'sector_ranking'];
      console.log('\n📈 KEY TABLE STATS:');

      for (const table of keyTables) {
        try {
          const countRes = await client.query(`SELECT COUNT(*) FROM ${table}`);
          const count = countRes.rows[0].count;
          const status = count === 0 ? '⚠️ ' : (count > 1000 ? '✓ ' : '⚡ ');
          console.log(`  ${status}${table}: ${count} rows`);
        } catch (e) {
          console.log(`  ✗ ${table}: ${e.message.split('\n')[0]}`);
        }
      }
    }

    // 2. SCHEMA ISSUES
    console.log('\n⚠️  SCHEMA ISSUES:');

    const schemaIssues = [];

    // Check sector_ranking for required columns
    try {
      const sectorRes = await client.query(`
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'sector_ranking'
      `);
      const cols = sectorRes.rows.map(r => r.column_name);
      console.log(`  sector_ranking columns: ${cols.join(', ')}`);
      if (!cols.includes('rank')) schemaIssues.push('sector_ranking: missing "rank" column');
    } catch (e) {
      schemaIssues.push('sector_ranking: ' + e.message.split('\n')[0]);
    }

    if (schemaIssues.length === 0) {
      console.log('  ✓ No critical schema issues');
    } else {
      schemaIssues.forEach(i => console.log(`  ✗ ${i}`));
    }

    // 3. DATA LOADING STATUS
    console.log('\n⏳ DATA POPULATION STATUS:');

    const populationChecks = [
      { name: 'Symbols loaded', table: 'stock_symbols', minRows: 4000 },
      { name: 'Daily prices loaded', table: 'daily_prices', minRows: 100000 },
      { name: 'Earnings data loaded', table: 'earnings_history', minRows: 5000 },
      { name: 'Company profiles loaded', table: 'company_profile', minRows: 4000 },
      { name: 'Earnings estimates loaded', table: 'earnings_estimates', minRows: 1000 },
    ];

    for (const check of populationChecks) {
      try {
        const res = await client.query(`SELECT COUNT(*) FROM ${check.table}`);
        const count = res.rows[0].count;
        const status = count >= check.minRows ? '✓' : (count === 0 ? '✗' : '⚡');
        console.log(`  ${status} ${check.name}: ${count} rows (target ${check.minRows})`);
      } catch (e) {
        console.log(`  ✗ ${check.name}: TABLE ERROR`);
      }
    }

  } catch (error) {
    console.error('❌ Audit failed:', error.message);
  } finally {
    await client.end();
  }
}

runAudit();
