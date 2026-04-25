#!/usr/bin/env node
/**
 * Create and populate sector_ranking and industry_ranking tables
 * Reads from comprehensive_market_data.json and inserts into PostgreSQL
 */

const { query } = require("./webapp/lambda/utils/database");
const fs = require("fs");
const path = require("path");

const comprehensivePath = process.platform === 'win32'
  ? "C:\\Users\\arger\\AppData\\Local\\Temp\\comprehensive_market_data.json"
  : "/tmp/comprehensive_market_data.json";

async function createTables() {
  try {
    console.log("📋 Creating sector_ranking table...");
    await query(`
      CREATE TABLE IF NOT EXISTS sector_ranking (
        id SERIAL PRIMARY KEY,
        sector_name VARCHAR(100) NOT NULL,
        current_rank INT,
        rank_1w_ago INT,
        rank_4w_ago INT,
        rank_12w_ago INT,
        momentum_score DECIMAL(10, 4),
        daily_strength_score DECIMAL(10, 4),
        stock_count INT,
        trend VARCHAR(50),
        date_recorded TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      );
      CREATE INDEX IF NOT EXISTS idx_sector_ranking_name ON sector_ranking(sector_name);
      CREATE INDEX IF NOT EXISTS idx_sector_ranking_date ON sector_ranking(date_recorded);
    `);

    console.log("📋 Creating industry_ranking table...");
    await query(`
      CREATE TABLE IF NOT EXISTS industry_ranking (
        id SERIAL PRIMARY KEY,
        industry VARCHAR(100) NOT NULL,
        current_rank INT,
        rank_1w_ago INT,
        rank_4w_ago INT,
        rank_12w_ago INT,
        momentum_score DECIMAL(10, 4),
        daily_strength_score DECIMAL(10, 4),
        stock_count INT,
        trend VARCHAR(50),
        date_recorded TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      );
      CREATE INDEX IF NOT EXISTS idx_industry_ranking_name ON industry_ranking(industry);
      CREATE INDEX IF NOT EXISTS idx_industry_ranking_date ON industry_ranking(date_recorded);
    `);

    console.log("✅ Tables created successfully");

    // Load data from JSON
    if (fs.existsSync(comprehensivePath)) {
      console.log("📁 Loading data from JSON file...");
      const data = JSON.parse(fs.readFileSync(comprehensivePath, "utf-8"));

      // Insert sectors
      if (data.sectors) {
        console.log(`📊 Inserting ${Object.keys(data.sectors).length} sectors...`);
        for (const [key, sector] of Object.entries(data.sectors)) {
          const rank = sector.rank || Object.keys(data.sectors).indexOf(key) + 1;
          await query(
            `INSERT INTO sector_ranking
             (sector_name, current_rank, momentum_score, daily_strength_score, trend, date_recorded)
             VALUES ($1, $2, $3, $4, $5, $6)
             ON CONFLICT DO NOTHING`,
            [
              sector.name || key,
              rank,
              sector.momentumScore || null,
              sector.dailyStrengthScore || null,
              sector.trend || null,
              new Date(data.timestamp)
            ]
          );
        }
      }

      // Insert industries
      if (data.industries) {
        console.log(`📊 Inserting ${Object.keys(data.industries).length} industries...`);
        for (const [key, industry] of Object.entries(data.industries)) {
          const rank = industry.rank || Object.keys(data.industries).indexOf(key) + 1;
          await query(
            `INSERT INTO industry_ranking
             (industry, current_rank, momentum_score, daily_strength_score, trend, date_recorded)
             VALUES ($1, $2, $3, $4, $5, $6)
             ON CONFLICT DO NOTHING`,
            [
              industry.name || key,
              rank,
              industry.momentumScore || null,
              industry.dailyStrengthScore || null,
              industry.trend || null,
              new Date(data.timestamp)
            ]
          );
        }
      }

      console.log("✅ Data inserted successfully");
    } else {
      console.log("⚠️ JSON file not found at " + comprehensivePath);
    }

  } catch (error) {
    console.error("❌ Error:", error.message);
    process.exit(1);
  }
}

createTables().then(() => {
  console.log("✅ Done!");
  process.exit(0);
});
