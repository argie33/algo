const { query } = require('./webapp/lambda/utils/database');

(async () => {
  try {
    process.env.DB_HOST = 'localhost';
    process.env.DB_PORT = '5432';
    process.env.DB_USER = 'stocks';
    process.env.DB_PASSWORD = 'bed0elAn';
    process.env.DB_NAME = 'stocks';
    process.env.DB_SSL = 'false';

    console.log('\n=== TABLE ROW COUNTS ===\n');
    
    const result = await query(`
      SELECT 
        schemaname,
        tablename,
        CAST(reltuples AS INT) as estimated_rows
      FROM pg_tables 
      JOIN pg_class ON relname = tablename
      WHERE schemaname = 'public'
      ORDER BY reltuples DESC
    `, undefined);
    
    result?.rows?.forEach(r => {
      console.log(`${r.tablename.padEnd(35)} ${r.estimated_rows?.toString().padStart(10)} rows`);
    });

    console.log('\n=== CHECKING FOR NULL/EMPTY DATA ===\n');
    
    const tables = ['daily_prices', 'weekly_prices', 'company_stats', 'sector_ranking', 'industry_ranking', 'earnings_data', 'earnings_estimates'];
    
    for (const table of tables) {
      try {
        const countResult = await query(`SELECT COUNT(*) as cnt FROM ${table}`, undefined);
        console.log(`${table.padEnd(30)}: ${countResult?.rows?.[0]?.cnt || 0} rows`);
      } catch (e) {
        console.log(`${table.padEnd(30)}: ERROR - ${e.message?.split('\n')[0]}`);
      }
    }
    
    process.exit(0);
  } catch (err) {
    console.error('Fatal error:', err.message);
    process.exit(1);
  }
})();
