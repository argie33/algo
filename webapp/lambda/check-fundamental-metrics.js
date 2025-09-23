require("dotenv").config();
const { Pool } = require("pg");

async function checkFundamentalMetrics() {
  const pool = new Pool({
    host: process.env.DB_HOST,
    user: process.env.DB_USER,
    password: process.env.DB_PASSWORD,
    database: process.env.DB_NAME,
    port: process.env.DB_PORT,
  });

  try {
    // Check fundamental_metrics columns
    const columnsResult = await pool.query(`
      SELECT column_name, data_type
      FROM information_schema.columns
      WHERE table_name = 'fundamental_metrics'
      ORDER BY column_name
    `);

    console.log("📊 fundamental_metrics columns:");
    columnsResult.rows.forEach((row) =>
      console.log(`- ${row.column_name} (${row.data_type})`)
    );

    // Check sample data
    const sampleResult = await pool.query(`
      SELECT symbol, pe_ratio, price_to_book, dividend_yield, sector
      FROM fundamental_metrics
      WHERE pe_ratio IS NOT NULL
      LIMIT 5
    `);

    console.log("\n💰 fundamental_metrics sample data:");
    sampleResult.rows.forEach((row) => {
      console.log(
        `- ${row.symbol}: PE=${row.pe_ratio}, PB=${row.price_to_book}, DY=${row.dividend_yield}, Sector=${row.sector}`
      );
    });

    // Check market_data columns
    const marketColumnsResult = await pool.query(`
      SELECT column_name, data_type
      FROM information_schema.columns
      WHERE table_name = 'market_data'
      ORDER BY column_name
    `);

    console.log("\n📈 market_data columns:");
    marketColumnsResult.rows.forEach((row) =>
      console.log(`- ${row.column_name} (${row.data_type})`)
    );

    // Check market_data sample
    const marketSampleResult = await pool.query(`
      SELECT ticker, current_price, market_cap
      FROM market_data
      WHERE current_price IS NOT NULL
      LIMIT 5
    `);

    console.log("\n💲 market_data sample data:");
    marketSampleResult.rows.forEach((row) => {
      console.log(
        `- ${row.ticker}: Price=$${row.current_price}, Cap=$${row.market_cap}`
      );
    });

    console.log("✅ Fundamental metrics check completed successfully");
  } catch (error) {
    console.error("❌ Error:", error.message);
    throw error;
  }
}

checkFundamentalMetrics();
