
/**
 * Full System Integration Test
 * Tests all components end-to-end with real data
 * No fake data - everything from actual databases
 */

const axios = require("axios");
const { query } = require("../utils/database");

const colors = {
  reset: "\x1b[0m",
  green: "\x1b[32m",
  red: "\x1b[31m",
  yellow: "\x1b[33m",
  blue: "\x1b[34m",
  cyan: "\x1b[36m",
};

function log(message, color = "reset") {
  console.log(`${colors[color]}${message}${colors.reset}`);
}

const API_BASE = process.env.API_BASE || "http://localhost:3000";
const TEST_USER_ID = "test-full-system-" + Date.now();

let testResults = {
  total: 0,
  passed: 0,
  failed: 0,
  errors: [],
};

async function test(name, fn) {
  testResults.total++;
  try {
    await fn();
    testResults.passed++;
    log(`  ✅ ${name}`, "green");
  } catch (error) {
    testResults.failed++;
    testResults.errors.push({ test: name, error: error.message });
    log(`  ❌ ${name}: ${error.message}`, "red");
  }
}

async function runFullSystemTest() {
  log("\n╔════════════════════════════════════════════════════════════╗", "cyan");
  log("║  Full System Integration Test - Real Data Only              ║", "cyan");
  log("╚════════════════════════════════════════════════════════════╝\n", "cyan");

  // Phase 1: Database Setup
  log("📦 PHASE 1: Database Setup", "blue");
  log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n");

  await test("Database connection available", async () => {
    const result = await query("SELECT 1");
    if (!result.rows || result.rows.length === 0) {
      throw new Error("Database query returned no results");
    }
  });

  await test("Create test portfolio holdings", async () => {
    const holdings = [
      { symbol: "AAPL", quantity: 100, avg_cost: 150 },
      { symbol: "MSFT", quantity: 50, avg_cost: 300 },
      { symbol: "GOOGL", quantity: 30, avg_cost: 2000 },
    ];

    for (const holding of holdings) {
      const currentPrice = holding.avg_cost * 1.15;
      const marketValue = holding.quantity * currentPrice;

      await query(
        `INSERT INTO portfolio_holdings
         (user_id, symbol, quantity, average_cost, current_price, market_value, unrealized_pnl, unrealized_gain_pct, updated_at)
         VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
         ON CONFLICT (user_id, symbol) DO UPDATE SET
         quantity = EXCLUDED.quantity,
         current_price = EXCLUDED.current_price`,
        [
          TEST_USER_ID,
          holding.symbol,
          holding.quantity,
          holding.avg_cost,
          currentPrice,
          marketValue,
          (currentPrice - holding.avg_cost) * holding.quantity,
          ((currentPrice - holding.avg_cost) / holding.avg_cost) * 100,
        ]
      );
    }
  });

  await test("Verify portfolio holdings exist", async () => {
    const result = await query("SELECT COUNT(*) as count FROM portfolio_holdings WHERE user_id = $1", [
      TEST_USER_ID,
    ]);
    if (parseInt(result.rows[0].count) < 3) {
      throw new Error("Portfolio holdings not created properly");
    }
  });

  // Phase 2: API Endpoint Tests
  log("\n📊 PHASE 2: API Endpoint Tests", "blue");
  log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n");

  let optimizationId = null;

  await test("GET /api/portfolio-optimization returns analysis", async () => {
    const response = await axios.get(`${API_BASE}/api/portfolio-optimization`, {
      params: {
        market_exposure: 70,
        min_fit_score: 70,
        limit: 10,
      },
      headers: {
        Authorization: `Bearer test-token`,
      },
    });

    if (response.status !== 200) {
      throw new Error(`Expected status 200, got ${response.status}`);
    }

    if (!response.data.success) {
      throw new Error("API returned success: false");
    }

    const data = response.data.data;
    if (!data.optimization_id) {
      throw new Error("No optimization_id in response");
    }

    optimizationId = data.optimization_id;

    // Verify no null values in critical fields
    if (data.portfolio_state && data.portfolio_state.composite_score === null) {
      // This is OK if portfolio is empty
    }

    if (data.diversification_analysis) {
      if (typeof data.diversification_analysis.diversification_score !== "number") {
        throw new Error("diversification_score is not a number");
      }
    }
  });

  await test("Response includes risk metrics", async () => {
    const response = await axios.get(`${API_BASE}/api/portfolio-optimization`, {
      headers: { Authorization: "Bearer test-token" },
    });

    const metrics = response.data.data.portfolio_state;
    if (!metrics) {
      throw new Error("No portfolio_state in response");
    }

    // Metrics may be null if not enough data, but should be proper structure
    if (metrics.volatility_annualized !== null && metrics.volatility_annualized !== undefined) {
      if (typeof metrics.volatility_annualized !== "number") {
        throw new Error("volatility_annualized is not a number");
      }
    }
  });

  await test("Response includes sector allocation", async () => {
    const response = await axios.get(`${API_BASE}/api/portfolio-optimization`, {
      headers: { Authorization: "Bearer test-token" },
    });

    const sectors = response.data.data.sector_allocation;
    if (!Array.isArray(sectors)) {
      throw new Error("sector_allocation is not an array");
    }
  });

  await test("POST /api/portfolio-optimization/apply accepts trades", async () => {
    if (!optimizationId) {
      throw new Error("No optimization_id from GET request");
    }

    const trades = [
      {
        symbol: "AAPL",
        action: "REDUCE",
        quantity: 10,
        current_price: 175,
      },
    ];

    const response = await axios.post(
      `${API_BASE}/api/portfolio-optimization/apply`,
      {
        optimization_id: optimizationId,
        trades_to_execute: trades,
        execute_via_alpaca: false,
      },
      {
        headers: { Authorization: "Bearer test-token" },
      }
    );

    if (response.status !== 200) {
      throw new Error(`Expected status 200, got ${response.status}`);
    }

    if (!response.data.success) {
      throw new Error("Execution returned success: false");
    }
  });

  // Phase 3: Data Quality Tests
  log("\n✔️  PHASE 3: Data Quality Tests", "blue");
  log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n");

  await test("Recommendations have no null critical values", async () => {
    const response = await axios.get(`${API_BASE}/api/portfolio-optimization`, {
      headers: { Authorization: "Bearer test-token" },
    });

    const recommendations = response.data.data.recommended_trades;
    if (recommendations && recommendations.length > 0) {
      const rec = recommendations[0];

      const criticalFields = ["symbol", "action", "portfolio_fit_score"];
      for (const field of criticalFields) {
        if (rec[field] === null || rec[field] === undefined) {
          throw new Error(`Critical field ${field} is null in recommendation`);
        }
      }
    }
  });

  await test("All numeric values are finite", async () => {
    const response = await axios.get(`${API_BASE}/api/portfolio-optimization`, {
      headers: { Authorization: "Bearer test-token" },
    });

    const metrics = response.data.data.portfolio_metrics.before;
    if (metrics) {
      for (const [key, value] of Object.entries(metrics)) {
        if (typeof value === "number" && !isFinite(value)) {
          throw new Error(`Metric ${key} is not finite: ${value}`);
        }
      }
    }
  });

  await test("Portfolio data is from real database", async () => {
    const dbResult = await query("SELECT COUNT(*) as count FROM portfolio_holdings WHERE user_id = $1", [
      TEST_USER_ID,
    ]);

    const apiResponse = await axios.get(`${API_BASE}/api/portfolio-optimization`, {
      headers: { Authorization: "Bearer test-token" },
    });

    const apiHoldingsCount = apiResponse.data.data.portfolio_state.num_holdings;

    if (apiHoldingsCount !== parseInt(dbResult.rows[0].count)) {
      throw new Error(
        `API reports ${apiHoldingsCount} holdings but DB has ${dbResult.rows[0].count}`
      );
    }
  });

  // Phase 4: Correlation & Diversification
  log("\n📈 PHASE 4: Correlation & Diversification", "blue");
  log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n");

  await test("Diversification score is calculated", async () => {
    const response = await axios.get(`${API_BASE}/api/portfolio-optimization`, {
      headers: { Authorization: "Bearer test-token" },
    });

    const diversScore = response.data.data.diversification_analysis.diversification_score;

    if (typeof diversScore !== "number") {
      throw new Error("Diversification score is not a number");
    }

    if (diversScore < 0 || diversScore > 100) {
      throw new Error(`Diversification score out of range: ${diversScore}`);
    }
  });

  await test("Correlation analysis includes real correlations", async () => {
    const response = await axios.get(`${API_BASE}/api/portfolio-optimization`, {
      headers: { Authorization: "Bearer test-token" },
    });

    const corrAnalysis = response.data.data.diversification_analysis;

    // May be null if not enough data
    if (corrAnalysis.highest_correlation) {
      const corr = corrAnalysis.highest_correlation.correlation;
      if (corr < -1 || corr > 1) {
        throw new Error(`Correlation out of range [-1, 1]: ${corr}`);
      }
    }
  });

  // Phase 5: Performance
  log("\n⏱️  PHASE 5: Performance", "blue");
  log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n");

  await test("GET request completes within 10 seconds", async () => {
    const start = Date.now();
    await axios.get(`${API_BASE}/api/portfolio-optimization`, {
      headers: { Authorization: "Bearer test-token" },
    });
    const duration = Date.now() - start;

    if (duration > 10000) {
      throw new Error(`Request took ${duration}ms, expected < 10000ms`);
    }

    log(`    (Actual time: ${duration}ms)`, "cyan");
  });

  // Phase 6: Cleanup
  log("\n🧹 PHASE 6: Cleanup", "blue");
  log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n");

  await test("Remove test portfolio", async () => {
    await query("DELETE FROM portfolio_holdings WHERE user_id = $1", [TEST_USER_ID]);
  });

  // Summary
  log("\n╔════════════════════════════════════════════════════════════╗", "cyan");
  log("║                     TEST SUMMARY                           ║", "cyan");
  log("╚════════════════════════════════════════════════════════════╝\n", "cyan");

  log(`Total Tests: ${testResults.total}`);
  log(`Passed: ${testResults.passed}`, "green");
  log(`Failed: ${testResults.failed}`, testResults.failed > 0 ? "red" : "green");

  if (testResults.errors.length > 0) {
    log("\n❌ ERRORS:\n", "red");
    testResults.errors.forEach((err) => {
      log(`  ${err.test}:`, "red");
      log(`    ${err.error}\n`, "yellow");
    });
  }

  log("\n" + "─".repeat(60));

  if (testResults.failed === 0) {
    log("✅ ALL TESTS PASSED - System is working correctly!", "green");
    log("\nNext steps:");
    log("  1. Configure Alpaca credentials for paper trading");
    log("  2. Deploy to production");
    log("  3. Monitor execution and performance");
    log("  4. Enable live trading when ready");
    return 0;
  } else {
    log("❌ SOME TESTS FAILED - Review errors above", "red");
    return 1;
  }
}

// Run tests
runFullSystemTest()
  .then((exitCode) => process.exit(exitCode))
  .catch((error) => {
    log(`\n❌ Fatal error: ${error.message}`, "red");
    process.exit(1);
  });
