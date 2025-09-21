const { query } = require("./utils/database");

async function checkTables() {
  try {
    const result = await query(`
      SELECT table_name
      FROM information_schema.tables
      WHERE table_schema = 'public'
      AND table_name LIKE '%metrics%'
    `);

    console.log('Tables with "metrics" in name:');
    result.rows.forEach((row) => console.log("-", row.table_name));

    // Also check key_metrics specifically
    const keyMetricsCheck = await query(`
      SELECT EXISTS (
        SELECT FROM information_schema.tables
        WHERE table_schema = 'public'
        AND table_name = 'key_metrics'
      ) as exists
    `);

    console.log("\nkey_metrics table exists:", keyMetricsCheck.rows[0].exists);

    // Check fundamental_metrics specifically
    const fundamentalMetricsCheck = await query(`
      SELECT EXISTS (
        SELECT FROM information_schema.tables
        WHERE table_schema = 'public'
        AND table_name = 'fundamental_metrics'
      ) as exists
    `);

    console.log(
      "fundamental_metrics table exists:",
      fundamentalMetricsCheck.rows[0].exists
    );

    console.log("✅ Tables check completed successfully");
  } catch (error) {
    console.error("Error checking tables:", error);
    throw error;
  }
}

checkTables();
