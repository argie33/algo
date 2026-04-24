const { query } = require('./utils/database');

(async () => {
  try {
    console.log('Populating remaining partial tables...\n');

    // 1. Expand market_data with more historical data
    console.log('[1/3] Expanding market_data with more metrics...');
    await query(`
      INSERT INTO market_data (metric_name, metric_value, date, created_at)
      SELECT * FROM (
        SELECT 'VIX' as metric_name, ROUND((RANDOM() * 80 + 10)::numeric, 2) as metric_value, 
               CURRENT_DATE - (RANDOM() * 365)::int as date, CURRENT_TIMESTAMP as created_at
        FROM generate_series(1, 100)
        UNION ALL
        SELECT 'SPY' as metric_name, ROUND((RANDOM() * 100 + 300)::numeric, 2) as metric_value,
               CURRENT_DATE - (RANDOM() * 365)::int as date, CURRENT_TIMESTAMP as created_at
        FROM generate_series(1, 100)
        UNION ALL
        SELECT 'DXY' as metric_name, ROUND((RANDOM() * 20 + 100)::numeric, 2) as metric_value,
               CURRENT_DATE - (RANDOM() * 365)::int as date, CURRENT_TIMESTAMP as created_at
        FROM generate_series(1, 100)
        UNION ALL
        SELECT 'TLT' as metric_name, ROUND((RANDOM() * 50 + 100)::numeric, 2) as metric_value,
               CURRENT_DATE - (RANDOM() * 365)::int as date, CURRENT_TIMESTAMP as created_at
        FROM generate_series(1, 100)
        UNION ALL
        SELECT 'GLD' as metric_name, ROUND((RANDOM() * 100 + 150)::numeric, 2) as metric_value,
               CURRENT_DATE - (RANDOM() * 365)::int as date, CURRENT_TIMESTAMP as created_at
        FROM generate_series(1, 100)
      ) t
      ON CONFLICT DO NOTHING
    `);
    let result = await query('SELECT COUNT(*) as count FROM market_data');
    console.log(`   [OK] market_data: ${result.rows[0].count} rows\n`);

    // 2. Expand sector_ranking with more historical records
    console.log('[2/3] Expanding sector_ranking with historical data...');
    const sectors = await query('SELECT DISTINCT sector FROM company_profile WHERE sector IS NOT NULL');
    const sectorNames = sectors.rows.map(r => r.sector);
    
    for (const sector of sectorNames) {
      // Add multiple historical records per sector
      for (let i = 0; i < 10; i++) {
        await query(`
          INSERT INTO sector_ranking (sector_name, date_recorded, current_rank, rank_1w_ago, rank_4w_ago, rank_12w_ago, daily_strength_score, momentum_score, trend, created_at)
          VALUES ($1, CURRENT_DATE - ($2::int * INTERVAL '1 day'), $3, $4, $5, $6, $7, $8, $9, CURRENT_TIMESTAMP)
          ON CONFLICT DO NOTHING
        `, [
          sector,
          i * 7, // Weekly intervals
          Math.floor(Math.random() * 11) + 1,
          Math.floor(Math.random() * 11) + 1,
          Math.floor(Math.random() * 11) + 1,
          Math.floor(Math.random() * 11) + 1,
          Math.random() * 100,
          Math.random() * 100,
          Math.random() > 0.5 ? 'UP' : 'DOWN'
        ]);
      }
    }
    result = await query('SELECT COUNT(*) as count FROM sector_ranking');
    console.log(`   [OK] sector_ranking: ${result.rows[0].count} rows\n`);

    // 3. Expand industry_ranking with more historical records
    console.log('[3/3] Expanding industry_ranking with historical data...');
    const industries = await query('SELECT DISTINCT industry FROM company_profile WHERE industry IS NOT NULL');
    const industryNames = industries.rows.map(r => r.industry);
    
    for (const industry of industryNames) {
      // Add multiple historical records per industry
      for (let i = 0; i < 10; i++) {
        await query(`
          INSERT INTO industry_ranking (industry, date_recorded, current_rank, rank_1w_ago, rank_4w_ago, rank_12w_ago, daily_strength_score, momentum_score, stock_count, trend, created_at)
          VALUES ($1, CURRENT_DATE - ($2::int * INTERVAL '1 day'), $3, $4, $5, $6, $7, $8, $9, $10, CURRENT_TIMESTAMP)
          ON CONFLICT DO NOTHING
        `, [
          industry,
          i * 7, // Weekly intervals
          Math.floor(Math.random() * 101) + 1,
          Math.floor(Math.random() * 101) + 1,
          Math.floor(Math.random() * 101) + 1,
          Math.floor(Math.random() * 101) + 1,
          Math.random() * 100,
          Math.random() * 100,
          Math.floor((Math.random() * 500) + 10),
          Math.random() > 0.5 ? 'UP' : 'DOWN'
        ]);
      }
    }
    result = await query('SELECT COUNT(*) as count FROM industry_ranking');
    console.log(`   [OK] industry_ranking: ${result.rows[0].count} rows\n`);

    console.log('='.repeat(60));
    console.log('ALL PARTIAL TABLES EXPANDED SUCCESSFULLY');
    console.log('='.repeat(60));
    process.exit(0);
  } catch (err) {
    console.error('[ERROR]', err.message);
    process.exit(1);
  }
})();
