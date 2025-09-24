#!/usr/bin/env node
/**
 * Setup fundamental_metrics table on AWS RDS PostgreSQL
 * This script creates the missing table that's causing AWS API failures
 */

require("dotenv").config();
const { Pool } = require("pg");

// AWS RDS connection config
const pool = new Pool({
  host: process.env.DB_HOST,
  user: process.env.DB_USER,
  password: process.env.DB_PASSWORD,
  database: process.env.DB_NAME,
  port: process.env.DB_PORT,
  ssl: process.env.DB_SSL === 'true',
});

async function createFundamentalMetricsTable() {
  const client = await pool.connect();

  try {
    console.log("🚀 Creating fundamental_metrics table on AWS RDS...");

    // Create the table using the exact schema from the SQL file
    const createTableSQL = `
    CREATE TABLE IF NOT EXISTS fundamental_metrics (
        symbol VARCHAR(10) PRIMARY KEY,
        company_name VARCHAR(255),
        market_cap BIGINT,
        pe_ratio DECIMAL(10,2),
        pb_ratio DECIMAL(10,2),
        dividend_yield DECIMAL(5,2),
        roe DECIMAL(5,2),
        debt_to_equity DECIMAL(5,2),
        current_ratio DECIMAL(5,2),
        revenue_growth DECIMAL(5,2),
        eps_growth DECIMAL(5,2),
        gross_margin DECIMAL(5,2),
        operating_margin DECIMAL(5,2),
        net_margin DECIMAL(5,2),
        asset_turnover DECIMAL(5,2),
        inventory_turnover DECIMAL(5,2),
        receivables_turnover DECIMAL(5,2),
        days_sales_outstanding DECIMAL(5,2),
        beta DECIMAL(5,2),
        shares_outstanding BIGINT,
        book_value_per_share DECIMAL(10,2),
        price_to_sales DECIMAL(5,2),
        price_to_book DECIMAL(5,2),
        enterprise_value BIGINT,
        ev_to_revenue DECIMAL(5,2),
        ev_to_ebitda DECIMAL(5,2),
        free_cash_flow BIGINT,
        operating_cash_flow BIGINT,
        total_debt BIGINT,
        total_equity BIGINT,
        working_capital BIGINT,
        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        sector VARCHAR(100),
        industry VARCHAR(100)
    )`;

    await client.query(createTableSQL);

    // Create indexes separately
    const indexQueries = [
      "CREATE INDEX IF NOT EXISTS idx_fundamental_metrics_sector ON fundamental_metrics(sector)",
      "CREATE INDEX IF NOT EXISTS idx_fundamental_metrics_industry ON fundamental_metrics(industry)",
      "CREATE INDEX IF NOT EXISTS idx_fundamental_metrics_market_cap ON fundamental_metrics(market_cap)",
      "CREATE INDEX IF NOT EXISTS idx_fundamental_metrics_last_updated ON fundamental_metrics(last_updated)"
    ];

    for (const indexQuery of indexQueries) {
      try {
        await client.query(indexQuery);
      } catch (indexError) {
        console.warn(`⚠️  Index creation warning: ${indexError.message}`);
      }
    }
    console.log("✅ fundamental_metrics table created successfully");

    // Insert sample data for major stocks (from the SQL file)
    const insertSampleDataSQL = `
    INSERT INTO fundamental_metrics (
        symbol, company_name, market_cap, pe_ratio, pb_ratio, dividend_yield, roe,
        sector, industry, shares_outstanding, book_value_per_share
    ) VALUES
    ('AAPL', 'Apple Inc.', 3400000000000, 35.2, 6.8, 0.44, 28.5, 'Technology', 'Consumer Electronics', 15204000000, 32.50),
    ('MSFT', 'Microsoft Corporation', 3200000000000, 32.1, 7.2, 0.68, 35.8, 'Technology', 'Software', 7430000000, 45.20),
    ('GOOGL', 'Alphabet Inc.', 2100000000000, 28.5, 5.8, 0.00, 23.5, 'Technology', 'Internet Services', 12900000000, 110.75),
    ('AMZN', 'Amazon.com Inc.', 1800000000000, 65.8, 9.2, 0.00, 18.2, 'Consumer Cyclical', 'Internet Retail', 10700000000, 89.50),
    ('TSLA', 'Tesla Inc.', 850000000000, 85.2, 12.5, 0.00, 19.3, 'Consumer Cyclical', 'Auto Manufacturers', 3160000000, 28.75),
    ('META', 'Meta Platforms Inc.', 1300000000000, 25.8, 6.1, 0.00, 22.8, 'Technology', 'Internet Services', 2540000000, 52.30),
    ('NVDA', 'NVIDIA Corporation', 2800000000000, 75.2, 22.5, 0.09, 45.2, 'Technology', 'Semiconductors', 24600000000, 45.80),
    ('NFLX', 'Netflix Inc.', 200000000000, 45.5, 8.2, 0.00, 25.5, 'Communication Services', 'Entertainment', 442000000, 52.10),
    ('SPY', 'SPDR S&P 500 ETF Trust', 520000000000, 0.0, 0.0, 1.35, 0.0, 'ETF', 'Index Fund', 900000000, 580.25),
    ('QQQ', 'Invesco QQQ Trust', 240000000000, 0.0, 0.0, 0.52, 0.0, 'ETF', 'Technology ETF', 750000000, 420.15)
    ON CONFLICT (symbol) DO UPDATE SET
        company_name = EXCLUDED.company_name,
        market_cap = EXCLUDED.market_cap,
        pe_ratio = EXCLUDED.pe_ratio,
        pb_ratio = EXCLUDED.pb_ratio,
        dividend_yield = EXCLUDED.dividend_yield,
        roe = EXCLUDED.roe,
        sector = EXCLUDED.sector,
        industry = EXCLUDED.industry,
        shares_outstanding = EXCLUDED.shares_outstanding,
        book_value_per_share = EXCLUDED.book_value_per_share,
        last_updated = CURRENT_TIMESTAMP;
    `;

    await client.query(insertSampleDataSQL);
    console.log("✅ Sample data inserted successfully");

    // Verify the table was created successfully
    const countResult = await client.query('SELECT COUNT(*) as total_records FROM fundamental_metrics');
    console.log(`✅ Table verification: ${countResult.rows[0].total_records} records found`);

    const sampleResult = await client.query('SELECT symbol, company_name, sector, industry FROM fundamental_metrics LIMIT 5');
    console.log("✅ Sample records:");
    sampleResult.rows.forEach(row => {
      console.log(`  - ${row.symbol}: ${row.company_name} (${row.sector})`);
    });

  } catch (error) {
    console.error("❌ Error creating fundamental_metrics table:", error);
    throw error;
  } finally {
    client.release();
  }
}

async function main() {
  try {
    await createFundamentalMetricsTable();
    console.log("🎉 AWS RDS fundamental_metrics table setup completed successfully!");
  } catch (error) {
    console.error("💥 Setup failed:", error.message);
    process.exit(1);
  } finally {
    await pool.end();
  }
}

if (require.main === module) {
  main();
}

module.exports = { createFundamentalMetricsTable };