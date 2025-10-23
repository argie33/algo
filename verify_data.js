const { query } = require('./webapp/lambda/utils/database');

(async () => {
  try {
    console.log('=== DEEP DATA QUALITY CHECK ===\n');

    // Check Oct 21 sectors
    console.log('1️⃣ Oct 21 Sector Data (what API returns):');
    const oct21Sectors = await query('SELECT sector, current_rank, rank_1w_ago, rank_4w_ago, rank_12w_ago FROM sector_ranking WHERE date = $1 ORDER BY sector', ['2025-10-21']);

    console.log(`Found ${oct21Sectors.rows.length} sectors for Oct 21`);
    const allHaveHistory = oct21Sectors.rows.every(r =>
      r.rank_1w_ago !== null && r.rank_4w_ago !== null && r.rank_12w_ago !== null
    );
    console.log(`All have historical data: ${allHaveHistory ? '✅ YES' : '❌ NO'}`);

    // Check if historical values reference the backfilled dates
    console.log('\n2️⃣ Oct 21 → Oct 15 comparison (is Oct 15 backfill being used?):\n');
    const oct21vs15 = await query(`
      SELECT
        sr21.sector,
        sr21.current_rank as oct21_curr,
        sr21.rank_1w_ago as oct21_1w,
        sr15.current_rank as oct15_curr
      FROM sector_ranking sr21
      LEFT JOIN sector_ranking sr15 ON sr21.sector = sr15.sector AND sr15.date = '2025-10-15'
      WHERE sr21.date = '2025-10-21'
      ORDER BY sr21.sector
    `);

    console.log('Sector                  | Oct21 Curr | Oct21 1W | Oct15 Curr | Match?');
    console.log('-'.repeat(75));
    let matches = 0;
    oct21vs15.rows.forEach(r => {
      const match = r.oct21_1w === r.oct15_curr ? '✅' : '❌';
      if (r.oct21_1w === r.oct15_curr) matches++;
      console.log(`${(r.sector || '').padEnd(23)} | ${String(r.oct21_curr).padStart(10)} | ${String(r.oct21_1w).padStart(7)} | ${String(r.oct15_curr).padStart(10)} | ${match}`);
    });
    console.log(`\nMatches: ${matches}/${oct21vs15.rows.length} (Oct 21's 1W values = Oct 15's current ranks)`);

    // Check Oct 21 industries - same check
    console.log('\n3️⃣ Oct 21 Industries with missing historical data:\n');
    const oct21IndMissing = await query(`
      SELECT
        industry,
        current_rank,
        rank_1w_ago,
        rank_4w_ago,
        rank_8w_ago,
        stock_count
      FROM industry_ranking
      WHERE date = '2025-10-21'
        AND (rank_1w_ago IS NULL OR rank_4w_ago IS NULL OR rank_8w_ago IS NULL)
      ORDER BY current_rank
      LIMIT 15
    `);

    console.log(`Industries missing historical data: ${oct21IndMissing.rows.length}\n`);
    oct21IndMissing.rows.slice(0, 10).forEach(i => {
      const industry = i.industry || '[EMPTY NAME]';
      const w1 = i.rank_1w_ago || '—';
      const w4 = i.rank_4w_ago || '—';
      const w8 = i.rank_8w_ago || '—';
      console.log(`  Rank ${String(i.current_rank).padStart(3)}: ${industry.padEnd(35)} | 1W:${String(w1).padStart(3)} 4W:${String(w4).padStart(3)} 8W:${String(w8).padStart(3)}`);
    });

  } catch (e) {
    console.error('Error:', e.message);
    console.error(e.stack);
  }
  process.exit(0);
})();
