require("dotenv").config();
const { Pool } = require("pg");

async function checkEconData() {
  const pool = new Pool({
    host: process.env.DB_HOST,
    user: process.env.DB_USER,
    password: process.env.DB_PASSWORD,
    database: process.env.DB_NAME,
    port: process.env.DB_PORT,
  });

  try {
    // Check if econ_data table exists
    const tableExistsResult = await pool.query(`
      SELECT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public'
        AND table_name = 'econ_data'
      ) as exists
    `);

    console.log(`📊 econ_data table exists: ${tableExistsResult.rows[0].exists}`);

    if (tableExistsResult.rows[0].exists) {
      // Check table structure
      const structureResult = await pool.query(`
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_schema = 'public'
        AND table_name = 'econ_data'
        ORDER BY ordinal_position
      `);

      console.log("\n📋 Table structure:");
      structureResult.rows.forEach((col) =>
        console.log(`- ${col.column_name}: ${col.data_type} (nullable: ${col.is_nullable})`)
      );

      // Check if table has data
      const countResult = await pool.query(`
        SELECT COUNT(*) as row_count FROM econ_data
      `);

      console.log(`\n📈 Total rows in econ_data: ${countResult.rows[0].row_count}`);

      // If has data, show sample
      if (parseInt(countResult.rows[0].row_count) > 0) {
        const sampleResult = await pool.query(`
          SELECT * FROM econ_data LIMIT 5
        `);

        console.log("\n📄 Sample data:");
        sampleResult.rows.forEach((row, i) =>
          console.log(`${i + 1}. ${JSON.stringify(row)}`)
        );
      } else {
        console.log("\n⚠️ Table exists but is empty");
      }
    } else {
      console.log("\n❌ econ_data table does not exist in AWS database");
    }

    console.log("\n✅ Economic data check completed");
  } catch (error) {
    console.error("❌ Error:", error.message);
    throw error;
  } finally {
    await pool.end();
  }
}

checkEconData();