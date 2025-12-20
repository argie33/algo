const { query } = require("./utils/database");

async function findMarketCap() {
  try {
    const result = await query(`
      SELECT table_name, column_name
      FROM information_schema.columns
      WHERE column_name ILIKE '%market%' OR column_name ILIKE '%cap%'
      ORDER BY table_name, column_name
    `);

    console.log("Tables with market/cap columns:");
    result.rows.forEach((row) =>
      console.log(`- ${row.table_name}.${row.column_name}`)
    );

    // Check company_profile specifically
    const companyProfileColumns = await query(`
      SELECT column_name
      FROM information_schema.columns
      WHERE table_name = 'company_profile'
      ORDER BY ordinal_position
    `);

    console.log("\ncompany_profile columns:");
    companyProfileColumns.rows.forEach((row) =>
      console.log(`- ${row.column_name}`)
    );

    // Check for market_cap in any table
    const marketCapSearch = await query(`
      SELECT table_name, column_name
      FROM information_schema.columns
      WHERE column_name = 'market_cap'
    `);

    console.log("\nTables with market_cap column:");
    marketCapSearch.rows.forEach((row) =>
      console.log(`- ${row.table_name}.${row.column_name}`)
    );

    console.log("✅ Market cap search completed successfully");
  } catch (error) {
    console.error("Error finding market_cap:", error);
    throw error;
  }
}

findMarketCap();
