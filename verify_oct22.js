const db = require('./webapp/lambda/utils/database');

(async () => {
  try {
    console.log('=== POST-LOADER VERIFICATION ===\n');

    const oct22 = await db.query('SELECT sector, current_rank, rank_1w_ago, rank_4w_ago, rank_12w_ago FROM sector_ranking WHERE date = $1 ORDER BY sector', ['2025-10-22']);

    console.log(`Oct 22 sectors: ${oct22.rows.length}`);
    if (oct22.rows.length > 0) {
      let allHave = true;
      oct22.rows.forEach(r => {
        if (r.rank_1w_ago === null || r.rank_4w_ago === null || r.rank_12w_ago === null) {
          allHave = false;
        }
      });
      console.log(`All have historical data: ${allHave ? '✅ YES' : '❌ NO'}\n`);

      if (allHave) {
        console.log('Oct 22 Sector Rankings with Historical:');
        console.log('Sector                  | Current | 1W Ago | 4W Ago | 12W Ago');
        console.log('-'.repeat(70));
        oct22.rows.forEach(r => {
          console.log(`${(r.sector || '').padEnd(23)} | ${String(r.current_rank).padStart(7)} | ${String(r.rank_1w_ago).padStart(6)} | ${String(r.rank_4w_ago).padStart(6)} | ${String(r.rank_12w_ago).padStart(7)}`);
        });
      }
    } else {
      console.log('❌ Oct 22 not yet created');
    }

  } catch (e) {
    console.error('Error:', e.message);
  }
  process.exit(0);
})();
