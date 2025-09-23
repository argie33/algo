require("dotenv").config();
const { Pool } = require("pg");

async function checkDatabaseTables() {
  const pool = new Pool({
    host: process.env.DB_HOST,
    user: process.env.DB_USER,
    password: process.env.DB_PASSWORD,
    database: process.env.DB_NAME,
    port: process.env.DB_PORT,
  });

  try {
    // Check all tables in the database
    const tablesResult = await pool.query(`
      SELECT table_name
      FROM information_schema.tables
      WHERE table_schema = 'public'
      ORDER BY table_name
    `);

    console.log("📊 Available database tables:");
    tablesResult.rows.forEach((row) =>
      console.log(`- ${row.table_name}`)
    );

    // Check for company_profile specifically
    const companyProfileCheck = await pool.query(`
      SELECT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public'
        AND table_name = 'company_profile'
      ) as exists
    `);

    console.log(`\n🏢 company_profile table exists: ${companyProfileCheck.rows[0].exists}`);

    console.log("✅ Database tables check completed successfully");
  } catch (error) {
    console.error("❌ Error:", error.message);
    throw error;
  }
}

checkDatabaseTables();