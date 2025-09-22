const { query } = require("./utils/database");

async function checkTables() {
  try {
    console.log("Checking fundamental_metrics table structure...");

    const result = await query(`
      SELECT column_name, data_type
      FROM information_schema.columns
      WHERE table_name = 'fundamental_metrics'
      ORDER BY ordinal_position
    `);

    console.log("fundamental_metrics columns:");
    result.rows.forEach(row => {
      console.log(`- ${row.column_name} (${row.data_type})`);
    });

    console.log("\nChecking market_data table structure...");

    const result2 = await query(`
      SELECT column_name, data_type
      FROM information_schema.columns
      WHERE table_name = 'market_data'
      ORDER BY ordinal_position
    `);

    console.log("market_data columns:");
    result2.rows.forEach(row => {
      console.log(`- ${row.column_name} (${row.data_type})`);
    });

    // Check sample data
    console.log("\nSample fundamental_metrics data:");
    const sampleResult = await query("SELECT * FROM fundamental_metrics LIMIT 3");
    console.log(sampleResult.rows);

  } catch (error) {
    console.error("Error checking tables:", error);
  }

  process.exit(0);
}

checkTables();