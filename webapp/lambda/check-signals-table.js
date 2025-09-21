const { query } = require("./utils/database");

async function checkSignalsTable() {
  try {
    const result = await query(`
      SELECT column_name, data_type
      FROM information_schema.columns
      WHERE table_name = 'swing_trading_signals'
      ORDER BY ordinal_position
    `);

    console.log("swing_trading_signals table structure:");
    result.rows.forEach((row) =>
      console.log(`- ${row.column_name}: ${row.data_type}`)
    );

    // Check sample data
    const sampleData = await query(`
      SELECT * FROM swing_trading_signals LIMIT 3
    `);

    console.log("\nSample data:");
    if (sampleData.rows.length > 0) {
      console.log("Columns:", Object.keys(sampleData.rows[0]));
      sampleData.rows.forEach((row, i) => {
        console.log(`Row ${i + 1}:`, row);
      });
    } else {
      console.log("No data in swing_trading_signals table");
    }

    console.log("✅ Signals table check completed successfully");
  } catch (error) {
    console.error("Error checking swing_trading_signals:", error);
    throw error;
  }
}

checkSignalsTable();
