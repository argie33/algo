const fs = require("fs");
const path = require("path");

const { Pool } = require("pg");

async function runDatabaseFixes() {
  console.log("Running database schema fixes...");

  // Database configuration from .env
  const dbConfig = {
    host: process.env.DB_HOST || "localhost",
    port: parseInt(process.env.DB_PORT) || 5432,
    user: process.env.DB_USER || "postgres",
    password: process.env.DB_PASSWORD || "password",
    database: process.env.DB_NAME || "stocks",
  };

  console.log("Database config:", {
    host: dbConfig.host,
    port: dbConfig.port,
    user: dbConfig.user,
    database: dbConfig.database,
    hasPassword: !!dbConfig.password,
  });

  const pool = new Pool(dbConfig);

  try {
    console.log("Connecting to database...");
    const client = await pool.connect();
    console.log("Connected successfully!");

    // Read and execute the fix script
    const fixScript = fs.readFileSync("add_security_name_column.sql", "utf8");
    console.log("Executing database fixes...");

    const result = await client.query(fixScript);
    console.log("Database fixes completed successfully!");

    // Show any results/notices
    if (result.rows && result.rows.length > 0) {
      console.log("Results:");
      result.rows.forEach((row) => console.log(row));
    }

    client.release();
  } catch (error) {
    console.error("Error running database fixes:", error.message);
    console.error("Full error:", error);
    process.exit(1);
  } finally {
    await pool.end();
  }

  console.log("Database fix script completed successfully!");
}

// Load environment variables
require("dotenv").config();

if (require.main === module) {
  runDatabaseFixes().catch(console.error);
}

module.exports = { runDatabaseFixes };
