
// Simple test to check ETF analytics route
const request = require('supertest');
const express = require('express');

// Set up test environment
process.env.NODE_ENV = "test";
process.env.DB_HOST = "localhost";
process.env.DB_USER = "postgres";
process.env.DB_PASSWORD = "password";
process.env.DB_NAME = "stocks";
process.env.DB_PORT = "5432";
process.env.DB_SSL = "false";

const app = express();

// Add the etf route
const etfRouter = require('./routes/etf');
app.use('/api/etf', etfRouter);

async function testAnalytics() {
  try {
    console.log("🧪 Testing ETF analytics route...");

    const response = await request(app)
      .get("/api/etf/SPY/analytics")
      .timeout(5000);

    console.log(`📊 Status: ${response.status}`);
    console.log(`📊 Response:`, response.body);

    if (response.status !== 200) {
      console.error("❌ Test failed - expected 200, got", response.status);
    } else {
      console.log("✅ Test passed!");
    }
  } catch (error) {
    console.error("❌ Test error:", error.message);
  }
  process.exit(0);
}

testAnalytics();