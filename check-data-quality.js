const { query } = require('./webapp/lambda/utils/database');

(async () => {
  try {
    process.env.DB_HOST = 'localhost';
    process.env.DB_PORT = '5432';
    process.env.DB_USER = 'stocks';
    process.env.DB_PASSWORD = 'bed0elAn';
    process.env.DB_NAME = 'stocks';
    process.env.DB_SSL = 'false';

    console.log('\n=== SECTOR RANKING DATA QUALITY ===\n');
    
    const sectorResult = await query(`
      SELECT 
        COUNT(*) as total,
        COUNT(CASE WHEN rank IS NULL THEN 1 END) as null_rank,
        COUNT(CASE WHEN performance IS NULL THEN 1 END) as null_performance,
        COUNT(CASE WHEN change_pct IS NULL THEN 1 END) as null_change,
        COUNT(CASE WHEN sector_name IS NULL THEN 1 END) as null_name,
        COUNT(DISTINCT sector_name) as distinct_sectors,
        MIN(updated_at) as oldest_update,
        MAX(updated_at) as newest_update
      FROM sector_ranking
    `, undefined);
    
    sectorResult?.rows?.forEach(r => {
      console.log(`Total rows: ${r.total}`);
      console.log(`  - NULL rank: ${r.null_rank} (${((r.null_rank/r.total)*100).toFixed(1)}%)`);
      console.log(`  - NULL performance: ${r.null_performance} (${((r.null_performance/r.total)*100).toFixed(1)}%)`);
      console.log(`  - NULL change_pct: ${r.null_change} (${((r.null_change/r.total)*100).toFixed(1)}%)`);
      console.log(`  - NULL name: ${r.null_name} (${((r.null_name/r.total)*100).toFixed(1)}%)`);
      console.log(`  - Distinct sectors: ${r.distinct_sectors}`);
      console.log(`  - Date range: ${r.oldest_update} to ${r.newest_update}`);
    });

    console.log('\n=== COMPANY PROFILE COMPLETENESS ===\n');
    
    const profileResult = await query(`
      SELECT 
        COUNT(*) as total,
        COUNT(CASE WHEN sector IS NULL THEN 1 END) as null_sector,
        COUNT(CASE WHEN industry IS NULL THEN 1 END) as null_industry,
        COUNT(CASE WHEN market_cap IS NULL THEN 1 END) as null_market_cap,
        COUNT(DISTINCT sector) as distinct_sectors,
        COUNT(DISTINCT industry) as distinct_industries
      FROM company_profile
    `, undefined);
    
    profileResult?.rows?.forEach(r => {
      console.log(`Total stocks: ${r.total}`);
      console.log(`  - NULL sector: ${r.null_sector} (${((r.null_sector/r.total)*100).toFixed(1)}%)`);
      console.log(`  - NULL industry: ${r.null_industry} (${((r.null_industry/r.total)*100).toFixed(1)}%)`);
      console.log(`  - NULL market_cap: ${r.null_market_cap} (${((r.null_market_cap/r.total)*100).toFixed(1)}%)`);
      console.log(`  - Sectors: ${r.distinct_sectors}, Industries: ${r.distinct_industries}`);
    });

    console.log('\n=== PRICE DATA COVERAGE ===\n');
    
    const priceResult = await query(`
      SELECT 
        COUNT(*) as total,
        COUNT(DISTINCT symbol) as symbols,
        MIN(date) as earliest_date,
        MAX(date) as latest_date,
        COUNT(CASE WHEN close IS NULL THEN 1 END) as null_close,
        COUNT(CASE WHEN volume IS NULL THEN 1 END) as null_volume
      FROM price_daily
    `, undefined);
    
    priceResult?.rows?.forEach(r => {
      console.log(`Daily prices: ${r.total} rows across ${r.symbols} symbols`);
      console.log(`  - Date range: ${r.earliest_date} to ${r.latest_date}`);
      console.log(`  - NULL close: ${r.null_close}`);
      console.log(`  - NULL volume: ${r.null_volume}`);
    });

    console.log('\n=== EMPTY/SPARSE TABLES ===\n');
    
    const emptyResult = await query(`
      SELECT 
        tablename,
        CAST(reltuples AS INT) as rows
      FROM pg_tables 
      JOIN pg_class ON relname = tablename
      WHERE schemaname = 'public' AND reltuples < 10
      ORDER BY reltuples DESC
    `, undefined);
    
    emptyResult?.rows?.forEach(r => {
      console.log(`${r.tablename}: ${r.rows} rows`);
    });

    process.exit(0);
  } catch (err) {
    console.error('Fatal error:', err.message);
    process.exit(1);
  }
})();
