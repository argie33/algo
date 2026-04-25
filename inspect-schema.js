const { query } = require('./webapp/lambda/utils/database');

(async () => {
  try {
    process.env.DB_HOST = 'localhost';
    process.env.DB_PORT = '5432';
    process.env.DB_USER = 'stocks';
    process.env.DB_PASSWORD = 'bed0elAn';
    process.env.DB_NAME = 'stocks';
    process.env.DB_SSL = 'false';

    const tables = ['sector_ranking', 'industry_ranking', 'company_profile', 'price_daily', 'earnings_estimates'];
    
    for (const table of tables) {
      console.log(`\n=== ${table.toUpperCase()} ===`);
      try {
        const result = await query(`
          SELECT column_name, data_type 
          FROM information_schema.columns 
          WHERE table_name = '${table}'
          ORDER BY ordinal_position
        `, undefined);
        result?.rows?.forEach(r => {
          console.log(`  ${r.column_name.padEnd(25)} ${r.data_type}`);
        });
      } catch (e) {
        console.log(`  ERROR: ${e.message?.split('\n')[0]}`);
      }
    }

    process.exit(0);
  } catch (err) {
    console.error('Fatal error:', err.message);
    process.exit(1);
  }
})();
