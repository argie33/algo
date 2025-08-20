#!/usr/bin/env node

const {
  SecretsManagerClient,
  GetSecretValueCommand,
} = require("@aws-sdk/client-secrets-manager");
const { Pool } = require("pg");

// Configure AWS SDK v3
const secretsManager = new SecretsManagerClient({
  region: process.env.AWS_REGION || "us-east-1",
});

async function getDbConfig() {
  try {
    console.log("Getting DB credentials from Secrets Manager...");
    const secretArn = process.env.DB_SECRET_ARN;
    if (!secretArn) {
      throw new Error("DB_SECRET_ARN environment variable not set");
    }

    const command = new GetSecretValueCommand({ SecretId: secretArn });
    const result = await secretsManager.send(command);
    const secret = JSON.parse(result.SecretString);

    return {
      host: secret.host,
      port: parseInt(secret.port) || 5432,
      user: secret.username,
      password: secret.password,
      database: secret.dbname,
    };
  } catch (error) {
    console.error("Error getting DB config:", error);
    throw error;
  }
}

async function testTechnicalTables() {
  let pool;

  try {
    // Get database configuration
    const dbConfig = await getDbConfig();
    console.log(
      `Connecting to database: ${dbConfig.host}:${dbConfig.port}/${dbConfig.database}`
    );

    // Create connection pool
    pool = new Pool(dbConfig);

    // Test connection
    const client = await pool.connect();
    console.log("✅ Database connection successful!");

    // Check if technical tables exist
    console.log("\n=== CHECKING TECHNICAL TABLES ===");
    const tableCheckQuery = `
            SELECT table_name, table_type 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name LIKE '%technical%'
            ORDER BY table_name;
        `;

    const tables = await client.query(tableCheckQuery);
    console.log("Technical tables found:");
    tables.rows.forEach((row) => {
      console.log(`  - ${row.table_name} (${row.table_type})`);
    });

    if (tables.rows.length === 0) {
      console.log("❌ No technical tables found!");
      return;
    }

    // Check each technical table
    for (const tableRow of tables.rows) {
      const tableName = tableRow.table_name;
      console.log(`\n=== ANALYZING TABLE: ${tableName} ===`);

      // Get table structure
      const structureQuery = `
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns 
                WHERE table_schema = 'public' 
                AND table_name = $1
                ORDER BY ordinal_position;
            `;

      const structure = await client.query(structureQuery, [tableName]);
      console.log("Table structure:");
      structure.rows.forEach((col) => {
        console.log(
          `  - ${col.column_name}: ${col.data_type} (${col.is_nullable === "YES" ? "nullable" : "not null"})`
        );
      });

      // Get row count
      const countQuery = `SELECT COUNT(*) as count FROM ${tableName};`;
      const countResult = await client.query(countQuery);
      const rowCount = parseInt(countResult.rows[0].count);
      console.log(`Total rows: ${rowCount}`);

      if (rowCount === 0) {
        console.log("❌ Table is empty!");
        continue;
      }

      // Get date range
      const dateColumns = structure.rows
        .filter(
          (col) =>
            col.data_type === "date" ||
            col.column_name.toLowerCase().includes("date")
        )
        .map((col) => col.column_name);

      if (dateColumns.length > 0) {
        const dateCol = dateColumns[0];
        const dateRangeQuery = `
                    SELECT 
                        MIN(${dateCol}) as min_date,
                        MAX(${dateCol}) as max_date,
                        COUNT(DISTINCT ${dateCol}) as unique_dates
                    FROM ${tableName};
                `;

        const dateRange = await client.query(dateRangeQuery);
        const range = dateRange.rows[0];
        console.log(
          `Date range: ${range.min_date} to ${range.max_date} (${range.unique_dates} unique dates)`
        );
      }

      // Get symbol count
      const symbolColumns = structure.rows
        .filter((col) => col.column_name.toLowerCase().includes("symbol"))
        .map((col) => col.column_name);

      if (symbolColumns.length > 0) {
        const symbolCol = symbolColumns[0];
        const symbolQuery = `
                    SELECT 
                        COUNT(DISTINCT ${symbolCol}) as unique_symbols,
                        COUNT(*) as total_records
                    FROM ${tableName};
                `;

        const symbolResult = await client.query(symbolQuery);
        const symbols = symbolResult.rows[0];
        console.log(
          `Symbols: ${symbols.unique_symbols} unique symbols, ${symbols.total_records} total records`
        );

        // Get sample symbols
        const sampleQuery = `
                    SELECT ${symbolCol} as symbol, COUNT(*) as records
                    FROM ${tableName}
                    GROUP BY ${symbolCol}
                    ORDER BY records DESC
                    LIMIT 5;
                `;

        const sampleResult = await client.query(sampleQuery);
        console.log("Top symbols by record count:");
        sampleResult.rows.forEach((row) => {
          console.log(`  - ${row.symbol}: ${row.records} records`);
        });
      }

      // Get recent data sample
      console.log("\nRecent data sample (last 3 records):");
      const sampleQuery = `SELECT * FROM ${tableName} ORDER BY id DESC LIMIT 3;`;
      const sampleResult = await client.query(sampleQuery);

      if (sampleResult.rows.length > 0) {
        console.log("Sample records:");
        sampleResult.rows.forEach((row, index) => {
          console.log(`  Record ${index + 1}:`, JSON.stringify(row, null, 2));
        });
      }
    }

    // Check stock_symbols table for company names
    console.log("\n=== CHECKING STOCK_SYMBOLS TABLE ===");
    const stockSymbolsQuery = `
            SELECT 
                symbol, 
                company_name,
                sector,
                industry
            FROM stock_symbols 
            WHERE symbol IN ('AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA')
            ORDER BY symbol;
        `;

    const stockSymbols = await client.query(stockSymbolsQuery);
    console.log("Sample stock symbols:");
    stockSymbols.rows.forEach((row) => {
      console.log(`  - ${row.symbol}: ${row.company_name} (${row.sector})`);
    });

    // Test a query similar to what the API would run
    console.log("\n=== TESTING API-LIKE QUERIES ===");

    // Check if technical_data_daily exists and has recent data
    const apiTestQuery = `
            SELECT 
                t.symbol,
                s.company_name,
                t.date,
                t.rsi,
                t.macd,
                t.sma_20,
                t.sma_50
            FROM technical_data_daily t
            JOIN stock_symbols s ON t.symbol = s.symbol
            WHERE t.date >= CURRENT_DATE - INTERVAL '30 days'
            ORDER BY t.date DESC, t.symbol
            LIMIT 10;
        `;

    try {
      const apiTest = await client.query(apiTestQuery);
      console.log("Recent technical data (API-style query):");
      if (apiTest.rows.length === 0) {
        console.log("❌ No recent technical data found!");
      } else {
        apiTest.rows.forEach((row) => {
          console.log(
            `  - ${row.symbol} (${row.company_name}) on ${row.date}: RSI=${row.rsi}, MACD=${row.macd}, SMA20=${row.sma_20}`
          );
        });
      }
    } catch (error) {
      console.log("❌ API-style query failed:", error.message);
    }

    client.release();
  } catch (error) {
    console.error("❌ Error testing technical tables:", error);
  } finally {
    if (pool) {
      await pool.end();
    }
  }
}

// Main execution
async function main() {
  console.log("🔍 Testing Technical Database Tables...\n");
  await testTechnicalTables();
  console.log("\n✅ Technical database test completed!");
}

if (require.main === module) {
  main().catch(console.error);
}

module.exports = { testTechnicalTables };
