const { query } = require('./utils/database');

async function checkPriceSymbols() {
  try {
    console.log('🔍 Checking price_daily table for available symbols...\\n');

    // Check if price_daily table exists
    try {
      const tableCheck = await query(`
        SELECT EXISTS (
          SELECT FROM information_schema.tables
          WHERE table_schema = 'public'
          AND table_name = 'price_daily'
        );
      `);

      if (!tableCheck.rows[0]?.exists) {
        console.log('❌ price_daily table does not exist');
        return;
      }

      console.log('✅ price_daily table exists');

      // Get total count
      const countResult = await query('SELECT COUNT(*) as total FROM price_daily');
      console.log(`📊 Total records: ${countResult.rows[0]?.total || 0}`);

      if (countResult.rows[0]?.total > 0) {
        // Get unique symbols
        const symbolsResult = await query(`
          SELECT symbol, COUNT(*) as record_count,
                 MIN(date) as earliest_date, MAX(date) as latest_date
          FROM price_daily
          GROUP BY symbol
          ORDER BY record_count DESC
          LIMIT 10
        `);

        console.log('\\n📋 Available symbols (top 10 by record count):');
        symbolsResult.rows.forEach(row => {
          console.log(`   • ${row.symbol}: ${row.record_count} records (${row.earliest_date} to ${row.latest_date})`);
        });

        // Check specifically for AAPL
        const aaplCheck = await query(`
          SELECT COUNT(*) as count, MIN(date) as earliest, MAX(date) as latest
          FROM price_daily
          WHERE symbol = 'AAPL'
        `);

        if (aaplCheck.rows[0]?.count > 0) {
          console.log(`\\n✅ AAPL has ${aaplCheck.rows[0].count} records`);
        } else {
          console.log('\\n❌ AAPL has no records in price_daily table');
        }

        // Get a sample symbol that has data
        const sampleSymbol = symbolsResult.rows[0]?.symbol;
        if (sampleSymbol) {
          console.log(`\\n💡 Suggested test symbol: ${sampleSymbol}`);

          // Get latest price data for this symbol
          const latestPrice = await query(`
            SELECT * FROM price_daily
            WHERE symbol = $1
            ORDER BY date DESC
            LIMIT 1
          `, [sampleSymbol]);

          if (latestPrice.rows[0]) {
            console.log('📈 Latest price data:');
            console.log(JSON.stringify(latestPrice.rows[0], null, 2));
          }
        }

      } else {
        console.log('❌ price_daily table is empty');
      }

    } catch (err) {
      console.log('❌ Error checking price_daily table:', err.message);
    }

  } catch (error) {
    console.error('❌ Database connection error:', error.message);
  } finally {
    process.exit(0);
  }
}

checkPriceSymbols();