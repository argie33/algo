// Database setup script for integration tests
const fs = require("fs");

const { Pool } = require("pg");

async function setupDatabase() {
  console.log("Setting up test database...");

  // First, try connecting to postgres database to create stocks database
  const adminPool = new Pool({
    host: "localhost",
    port: 5432,
    user: "postgres",
    password: "", // Try without password first
    database: "postgres",
  });

  let client;
  try {
    client = await adminPool.connect();
    console.log("Connected to PostgreSQL as postgres user");

    // Create user and database
    try {
      await client.query("CREATE USER stocks WITH PASSWORD 'stocks'");
      console.log("Created user: stocks");
    } catch (err) {
      if (err.message.includes("already exists")) {
        console.log("User stocks already exists");
      } else {
        console.log("Error creating user:", err.message);
      }
    }

    try {
      await client.query("CREATE DATABASE stocks OWNER stocks");
      console.log("Created database: stocks");
    } catch (err) {
      if (err.message.includes("already exists")) {
        console.log("Database stocks already exists");
      } else {
        console.log("Error creating database:", err.message);
      }
    }

    try {
      await client.query("GRANT ALL PRIVILEGES ON DATABASE stocks TO stocks");
      console.log("Granted privileges to stocks user");
    } catch (err) {
      console.log("Error granting privileges:", err.message);
    }
  } catch (err) {
    console.log("Could not connect as postgres user:", err.message);
    console.log("Trying alternative approach...");
  } finally {
    if (client) client.release();
    await adminPool.end();
  }

  // Now connect to stocks database to create schema and data
  const stocksPool = new Pool({
    host: "localhost",
    port: 5432,
    user: "stocks",
    password: "stocks",
    database: "stocks",
  });

  try {
    const stocksClient = await stocksPool.connect();
    console.log("Connected to stocks database");

    // Create schema
    console.log("Creating database schema...");
    const schemaSQL = fs.readFileSync("setup_database.sql", "utf8");
    await stocksClient.query(schemaSQL);
    console.log("Schema created successfully");

    // Insert test data
    console.log("Seeding test data...");
    const seedSQL = fs.readFileSync("seed_test_data.sql", "utf8");
    await stocksClient.query(seedSQL);
    console.log("Test data seeded successfully");

    // Verify setup
    const tableCount = await stocksClient.query(`
      SELECT COUNT(*) FROM information_schema.tables 
      WHERE table_schema = 'public'
    `);
    console.log(`Created ${tableCount.rows[0].count} tables`);

    const signalCount = await stocksClient.query(
      "SELECT COUNT(*) FROM buy_sell_daily"
    );
    console.log(`Inserted ${signalCount.rows[0].count} trading signals`);

    stocksClient.release();
    console.log("Database setup completed successfully!");
  } catch (err) {
    console.error("Error setting up stocks database:", err.message);
    throw new Error(`Database setup failed: ${err.message}`);
  } finally {
    await stocksPool.end();
  }

  console.log("\nDatabase setup complete!");
  console.log("Connection details:");
  console.log("  Host: localhost");
  console.log("  Port: 5432");
  console.log("  Database: stocks");
  console.log("  Username: stocks");
  console.log("  Password: stocks");
  console.log("\nSet environment variables:");
  console.log("export DB_HOST=localhost");
  console.log("export DB_PORT=5432");
  console.log("export DB_USER=stocks");
  console.log("export DB_PASSWORD=stocks");
  console.log("export DB_NAME=stocks");
}

if (require.main === module) {
  setupDatabase().catch(console.error);
}

module.exports = { setupDatabase };
