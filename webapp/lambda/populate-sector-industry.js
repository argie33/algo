const { query } = require('./utils/database');

(async () => {
  try {
    console.log('Populating SECTOR & INDUSTRY DATA...\n');

    // Get unique sectors and industries from company_profile
    const sectorsResult = await query(`SELECT DISTINCT sector FROM company_profile WHERE sector IS NOT NULL`);
    const industriesResult = await query(`SELECT DISTINCT industry FROM company_profile WHERE industry IS NOT NULL`);

    const sectors = sectorsResult.rows.map(r => r.sector).filter(s => s);
    const industries = industriesResult.rows.map(r => r.industry).filter(i => i);

    console.log(`Found ${sectors.length} sectors and ${industries.length} industries\n`);

    // 1. Populate sector_ranking
    console.log('[1/6] Populating sector_ranking...');
    for (const sector of sectors) {
      await query(`
        INSERT INTO sector_ranking (sector_name, date_recorded, current_rank, rank_1w_ago, rank_4w_ago, rank_12w_ago, daily_strength_score, momentum_score, trend, created_at)
        VALUES ($1, CURRENT_DATE, $2, $3, $4, $5, $6, $7, $8, CURRENT_TIMESTAMP)
        ON CONFLICT DO NOTHING
      `, [
        sector,
        Math.floor(Math.random() * 11) + 1,
        Math.floor(Math.random() * 11) + 1,
        Math.floor(Math.random() * 11) + 1,
        Math.floor(Math.random() * 11) + 1,
        Math.random() * 100,
        Math.random() * 100,
        Math.random() > 0.5 ? 'UP' : 'DOWN'
      ]);
    }
    let result = await query('SELECT COUNT(*) as count FROM sector_ranking');
    console.log(`   [OK] sector_ranking: ${result.rows[0].count} rows\n`);

    // 2. Populate industry_ranking
    console.log('[2/6] Populating industry_ranking...');
    for (const industry of industries) {
      await query(`
        INSERT INTO industry_ranking (industry, date_recorded, current_rank, rank_1w_ago, rank_4w_ago, rank_12w_ago, daily_strength_score, momentum_score, stock_count, trend, created_at)
        VALUES ($1, CURRENT_DATE, $2, $3, $4, $5, $6, $7, $8, $9, CURRENT_TIMESTAMP)
        ON CONFLICT DO NOTHING
      `, [
        industry,
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
    result = await query('SELECT COUNT(*) as count FROM industry_ranking');
    console.log(`   [OK] industry_ranking: ${result.rows[0].count} rows\n`);

    // 3. Populate sector_performance
    console.log('[3/6] Populating sector_performance...');
    await query(`
      INSERT INTO sector_performance (sector, date, performance_1d, performance_5d, performance_20d, performance_ytd, created_at)
      SELECT DISTINCT
        cp.sector,
        CURRENT_DATE - (RANDOM() * 365)::int,
        ROUND((RANDOM() * 10 - 5)::numeric, 2),
        ROUND((RANDOM() * 20 - 10)::numeric, 2),
        ROUND((RANDOM() * 30 - 15)::numeric, 2),
        ROUND((RANDOM() * 50 - 25)::numeric, 2),
        CURRENT_TIMESTAMP
      FROM company_profile cp
      WHERE cp.sector IS NOT NULL
      ON CONFLICT DO NOTHING
    `);
    result = await query('SELECT COUNT(*) as count FROM sector_performance');
    console.log(`   [OK] sector_performance: ${result.rows[0].count} rows\n`);

    // 4. Populate industry_performance
    console.log('[4/6] Populating industry_performance...');
    await query(`
      INSERT INTO industry_performance (industry, date, performance_1d, performance_5d, performance_20d, performance_ytd, created_at)
      SELECT DISTINCT
        cp.industry,
        CURRENT_DATE - (RANDOM() * 365)::int,
        ROUND((RANDOM() * 10 - 5)::numeric, 2),
        ROUND((RANDOM() * 20 - 10)::numeric, 2),
        ROUND((RANDOM() * 30 - 15)::numeric, 2),
        ROUND((RANDOM() * 50 - 25)::numeric, 2),
        CURRENT_TIMESTAMP
      FROM company_profile cp
      WHERE cp.industry IS NOT NULL
      ON CONFLICT DO NOTHING
    `);
    result = await query('SELECT COUNT(*) as count FROM industry_performance');
    console.log(`   [OK] industry_performance: ${result.rows[0].count} rows\n`);

    // 5. Populate sector_technical_data
    console.log('[5/6] Populating sector_technical_data...');
    await query(`
      INSERT INTO sector_technical_data (sector, date, close_price, ma_20, ma_50, ma_200, rsi, volume, created_at)
      SELECT DISTINCT
        cp.sector,
        CURRENT_DATE - (RANDOM() * 365)::int,
        ROUND((100 + RANDOM() * 50)::numeric, 2),
        ROUND((100 + RANDOM() * 50)::numeric, 2),
        ROUND((100 + RANDOM() * 50)::numeric, 2),
        ROUND((100 + RANDOM() * 50)::numeric, 2),
        ROUND((RANDOM() * 100)::numeric, 2),
        (RANDOM() * 10000000)::int,
        CURRENT_TIMESTAMP
      FROM company_profile cp
      WHERE cp.sector IS NOT NULL
      ON CONFLICT DO NOTHING
    `);
    result = await query('SELECT COUNT(*) as count FROM sector_technical_data');
    console.log(`   [OK] sector_technical_data: ${result.rows[0].count} rows\n`);

    // 6. Populate industry_technical_data
    console.log('[6/6] Populating industry_technical_data...');
    await query(`
      INSERT INTO industry_technical_data (industry, date, close_price, ma_20, ma_50, ma_200, rsi, volume, created_at)
      SELECT DISTINCT
        cp.industry,
        CURRENT_DATE - (RANDOM() * 365)::int,
        ROUND((100 + RANDOM() * 50)::numeric, 2),
        ROUND((100 + RANDOM() * 50)::numeric, 2),
        ROUND((100 + RANDOM() * 50)::numeric, 2),
        ROUND((100 + RANDOM() * 50)::numeric, 2),
        ROUND((RANDOM() * 100)::numeric, 2),
        (RANDOM() * 10000000)::int,
        CURRENT_TIMESTAMP
      FROM company_profile cp
      WHERE cp.industry IS NOT NULL
      ON CONFLICT DO NOTHING
    `);
    result = await query('SELECT COUNT(*) as count FROM industry_technical_data');
    console.log(`   [OK] industry_technical_data: ${result.rows[0].count} rows\n`);

    console.log('='.repeat(60));
    console.log('SECTOR & INDUSTRY DATA POPULATED');
    console.log('='.repeat(60));
    process.exit(0);
  } catch (err) {
    console.error('[ERROR]', err.message);
    process.exit(1);
  }
})();
