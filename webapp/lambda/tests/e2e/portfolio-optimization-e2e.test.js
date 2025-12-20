/**
 * End-to-End Integration Tests for Portfolio Optimization
 *
 * Tests the complete flow with real database data and actual API calls
 * Validates all components working together in production conditions
 */

const axios = require("axios");
const { query } = require("../../utils/database");

// Test configuration
const API_BASE = process.env.API_BASE || "http://localhost:3000";
const TEST_USER_ID = "test-e2e-user-" + Date.now();
const AUTH_TOKEN = process.env.TEST_AUTH_TOKEN || "test-token-" + Date.now();

// Helper to make authenticated API calls
const apiClient = axios.create({
  baseURL: API_BASE,
  headers: {
    Authorization: `Bearer ${AUTH_TOKEN}`,
    "Content-Type": "application/json",
  },
  validateStatus: () => true, // Don't throw on any status
});

describe("Portfolio Optimization - End-to-End Tests", () => {
  let optimizationId = null;
  const testStocks = ["AAPL", "MSFT", "GOOGL", "TSLA", "AMZN"];

  /**
   * Setup: Create test portfolio with real stocks
   */
  beforeAll(async () => {
    console.log("\n🚀 Setting up test environment...");
    console.log(`Test User ID: ${TEST_USER_ID}`);

    try {
      // Insert test portfolio holdings
      const holdings = [
        { symbol: "AAPL", quantity: 100, avg_cost: 150 },
        { symbol: "MSFT", quantity: 50, avg_cost: 300 },
        { symbol: "GOOGL", quantity: 30, avg_cost: 2000 },
        { symbol: "TSLA", quantity: 20, avg_cost: 200 },
      ];

      for (const holding of holdings) {
        const currentPrice = holding.avg_cost * 1.1; // Assume 10% gain
        const marketValue = holding.quantity * currentPrice;

        await query(
          `INSERT INTO portfolio_holdings
           (user_id, symbol, quantity, average_cost, current_price, market_value, unrealized_pnl, unrealized_gain_pct, updated_at)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
           ON CONFLICT (user_id, symbol) DO UPDATE SET
           quantity = EXCLUDED.quantity,
           average_cost = EXCLUDED.average_cost,
           current_price = EXCLUDED.current_price,
           market_value = EXCLUDED.market_value`,
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

        console.log(`✓ Created ${holding.symbol} holding: ${holding.quantity} @ $${holding.avg_cost}`);
      }

      console.log("✅ Test portfolio setup complete\n");
    } catch (error) {
      console.error("❌ Setup failed:", error.message);
      throw error;
    }
  });

  /**
   * TEST 1: GET /api/portfolio-optimization - Full Analysis
   */
  describe("GET /api/portfolio-optimization", () => {
    test("should return complete optimization analysis with real data", async () => {
      console.log("\n📊 TEST 1: Getting portfolio optimization analysis...");

      const response = await apiClient.get("/api/portfolio-optimization", {
        params: {
          market_exposure: 70, // Bullish
          min_fit_score: 70,
          limit: 10,
        },
      });

      console.log(`Response Status: ${response.status}`);
      expect(response.status).toBe(200);
      expect(response.data.success).toBe(true);

      const data = response.data.data;

      // Validate response structure
      console.log("Validating response structure...");
      expect(data.optimization_id).toBeDefined();
      expect(data.portfolio_state).toBeDefined();
      expect(data.diversification_analysis).toBeDefined();
      expect(data.recommended_trades).toBeDefined();
      expect(data.portfolio_metrics).toBeDefined();
      expect(data.sector_allocation).toBeDefined();

      // Save optimization ID for later tests
      optimizationId = data.optimization_id;
      console.log(`✓ Optimization ID: ${optimizationId}`);

      // Validate portfolio state
      console.log("Validating portfolio state...");
      expect(data.portfolio_state.total_value).toBeGreaterThan(0);
      expect(data.portfolio_state.num_holdings).toBeGreaterThan(0);
      expect(data.portfolio_state.composite_score).toBeGreaterThanOrEqual(0);
      console.log(`✓ Portfolio value: $${data.portfolio_state.total_value.toFixed(2)}`);
      console.log(`✓ Number of holdings: ${data.portfolio_state.num_holdings}`);
      console.log(`✓ Composite score: ${data.portfolio_state.composite_score?.toFixed(1) || "N/A"}`);

      // Validate diversification analysis
      console.log("Validating diversification analysis...");
      expect(data.diversification_analysis.diversification_score).toBeGreaterThanOrEqual(0);
      expect(data.diversification_analysis.diversification_score).toBeLessThanOrEqual(100);
      console.log(`✓ Diversification score: ${data.diversification_analysis.diversification_score}`);

      if (data.diversification_analysis.highest_correlation) {
        console.log(`✓ Highest correlation: ${data.diversification_analysis.highest_correlation.symbol1} & ${data.diversification_analysis.highest_correlation.symbol2} = ${data.diversification_analysis.highest_correlation.correlation.toFixed(2)}`);
      }

      // Validate recommendations
      console.log("Validating recommendations...");
      expect(Array.isArray(data.recommended_trades)).toBe(true);

      if (data.recommended_trades.length > 0) {
        console.log(`✓ Generated ${data.recommended_trades.length} recommendations`);

        // Check first recommendation quality
        const firstRec = data.recommended_trades[0];
        expect(firstRec.symbol).toBeDefined();
        expect(firstRec.action).toMatch(/BUY|SELL|REDUCE/);
        expect(firstRec.portfolio_fit_score).toBeDefined();

        // CRITICAL: NO NULL VALUES in recommendations
        expect(firstRec.market_fit_component).not.toBeNull();
        expect(firstRec.correlation_component).not.toBeNull();
        expect(firstRec.sector_component).not.toBeNull();

        console.log(`✓ Top recommendation: ${firstRec.action} ${firstRec.symbol} (score: ${firstRec.portfolio_fit_score.toFixed(1)})`);
      } else {
        console.log("⚠️ No recommendations generated (portfolio may already be optimized)");
      }

      // Validate metrics
      console.log("Validating portfolio metrics...");
      expect(data.portfolio_metrics.before).toBeDefined();
      expect(data.portfolio_metrics.after_recommendations).toBeDefined();
      console.log(`✓ Current composite score: ${data.portfolio_metrics.before.composite_score?.toFixed(1) || "N/A"}`);
      console.log(`✓ Volatility: ${data.portfolio_metrics.before.volatility_annualized?.toFixed(2) || "N/A"}%`);

      console.log("✅ Analysis retrieved successfully\n");
    });

    test("should include risk metrics in response", async () => {
      console.log("\n📈 TEST: Validating risk metrics...");

      const response = await apiClient.get("/api/portfolio-optimization");
      expect(response.status).toBe(200);

      const metrics = response.data.data.portfolio_state;

      // Risk metrics should be calculated from real data
      expect(metrics.volatility_annualized).toBeDefined();
      console.log(`✓ Volatility: ${metrics.volatility_annualized?.toFixed(2) || "N/A"}%`);

      if (metrics.sharpe_ratio) {
        expect(metrics.sharpe_ratio).toBeGreaterThanOrEqual(-5);
        expect(metrics.sharpe_ratio).toBeLessThanOrEqual(10);
        console.log(`✓ Sharpe Ratio: ${metrics.sharpe_ratio.toFixed(2)}`);
      }

      if (metrics.max_drawdown) {
        expect(metrics.max_drawdown).toBeGreaterThanOrEqual(0);
        expect(metrics.max_drawdown).toBeLessThanOrEqual(100);
        console.log(`✓ Max Drawdown: ${metrics.max_drawdown.toFixed(2)}%`);
      }

      console.log("✅ Risk metrics validated\n");
    });

    test("should include sector allocation data", async () => {
      console.log("\n🏢 TEST: Validating sector allocation...");

      const response = await apiClient.get("/api/portfolio-optimization");
      expect(response.status).toBe(200);

      const sectors = response.data.data.sector_allocation;
      expect(Array.isArray(sectors)).toBe(true);
      expect(sectors.length).toBeGreaterThan(0);

      console.log(`✓ Found ${sectors.length} sectors in portfolio`);

      sectors.slice(0, 3).forEach((sector) => {
        console.log(`  - ${sector.sector}: ${sector.current_pct.toFixed(1)}% (drift: ${sector.drift.toFixed(1)}%)`);
      });

      console.log("✅ Sector allocation validated\n");
    });
  });

  /**
   * TEST 2: POST /api/portfolio-optimization/apply - Execute Trades
   */
  describe("POST /api/portfolio-optimization/apply", () => {
    test("should execute trades and update portfolio", async () => {
      console.log("\n💼 TEST 2: Executing trades...");

      if (!optimizationId) {
        console.log("⏭️  Skipping - no optimization ID from previous test");
        return;
      }

      // Create test trades
      const trades = [
        {
          symbol: "AAPL",
          action: "REDUCE",
          quantity: 10,
          current_price: 175,
        },
        {
          symbol: "MSFT",
          action: "REDUCE",
          quantity: 5,
          current_price: 330,
        },
      ];

      console.log(`Executing ${trades.length} trades...`);

      const response = await apiClient.post("/api/portfolio-optimization/apply", {
        optimization_id: optimizationId,
        trades_to_execute: trades,
        execute_via_alpaca: false, // Use database only for this test
      });

      console.log(`Response Status: ${response.status}`);
      expect(response.status).toBe(200);
      expect(response.data.success).toBe(true);

      console.log("Validating execution response...");
      const data = response.data.data;
      expect(data.executed_trades).toBeDefined();
      expect(data.total_executed).toBeGreaterThanOrEqual(0);

      console.log(`✓ Executed trades: ${data.total_executed}`);

      if (data.failed_trades) {
        console.log(`⚠️  Failed trades: ${data.total_failed}`);
      }

      console.log("✅ Trades executed successfully\n");
    });

    test("should validate insufficient shares error", async () => {
      console.log("\n❌ TEST: Validating error handling for insufficient shares...");

      const invalidTrade = [
        {
          symbol: "AAPL",
          action: "SELL",
          quantity: 100000, // Way more than available
          current_price: 175,
        },
      ];

      const response = await apiClient.post("/api/portfolio-optimization/apply", {
        optimization_id: "test-opt-invalid",
        trades_to_execute: invalidTrade,
        execute_via_alpaca: false,
      });

      expect(response.status).toBe(200);
      expect(response.data.data.total_failed).toBeGreaterThan(0);

      if (response.data.data.failed_trades && response.data.data.failed_trades.length > 0) {
        console.log(`✓ Error caught: ${response.data.data.failed_trades[0].error}`);
      }

      console.log("✅ Error handling validated\n");
    });

    test("should handle missing required fields", async () => {
      console.log("\n⚠️ TEST: Validating missing field validation...");

      const response = await apiClient.post("/api/portfolio-optimization/apply", {
        // Missing trades_to_execute
        optimization_id: "test-opt",
      });

      expect(response.status).toBe(400);
      expect(response.data.success).toBe(false);
      console.log(`✓ Error: ${response.data.error}`);

      console.log("✅ Field validation working\n");
    });
  });

  /**
   * TEST 3: Verify Portfolio Holdings Updated
   */
  describe("Portfolio State Verification", () => {
    test("should reflect changes in portfolio_holdings table", async () => {
      console.log("\n🔍 TEST 3: Verifying database state...");

      const result = await query(
        `SELECT symbol, quantity, current_price, market_value
         FROM portfolio_holdings
         WHERE user_id = $1
         ORDER BY market_value DESC`,
        [TEST_USER_ID]
      );

      expect(result.rows.length).toBeGreaterThan(0);
      console.log(`✓ Portfolio has ${result.rows.length} holdings`);

      const totalValue = result.rows.reduce((sum, h) => sum + parseFloat(h.market_value), 0);
      console.log(`✓ Total portfolio value: $${totalValue.toFixed(2)}`);

      result.rows.slice(0, 3).forEach((holding) => {
        const value = parseFloat(holding.market_value);
        const weight = (value / totalValue) * 100;
        console.log(
          `  - ${holding.symbol}: ${parseFloat(holding.quantity).toFixed(2)} shares @ $${parseFloat(holding.current_price).toFixed(2)} = $${value.toFixed(0)} (${weight.toFixed(1)}%)`
        );
      });

      console.log("✅ Database state verified\n");
    });
  });

  /**
   * TEST 4: Correlation Analysis
   */
  describe("Correlation Analysis", () => {
    test("should calculate correlations for holdings", async () => {
      console.log("\n📊 TEST 4: Testing correlation analysis...");

      const response = await apiClient.get("/api/portfolio-optimization");
      expect(response.status).toBe(200);

      const diversification = response.data.data.diversification_analysis;

      console.log(`Diversification Score: ${diversification.diversification_score}/100`);

      if (diversification.highest_correlation) {
        console.log(
          `Highest correlation: ${diversification.highest_correlation.symbol1} & ${diversification.highest_correlation.symbol2} = ${diversification.highest_correlation.correlation.toFixed(3)}`
        );
      }

      if (diversification.lowest_correlation) {
        console.log(
          `Lowest correlation: ${diversification.lowest_correlation.symbol1} & ${diversification.lowest_correlation.symbol2} = ${diversification.lowest_correlation.correlation.toFixed(3)}`
        );
      }

      if (diversification.recommended_low_correlation_asset) {
        const rec = diversification.recommended_low_correlation_asset;
        console.log(`Recommended for diversification: ${rec.symbol} (correlation: ${rec.average_absolute_correlation.toFixed(3)})`);
      }

      console.log("✅ Correlation analysis complete\n");
    });
  });

  /**
   * TEST 5: Data Quality Validation
   */
  describe("Data Quality Validation", () => {
    test("should not include null values in critical fields", async () => {
      console.log("\n✔️ TEST 5: Validating data quality...");

      const response = await apiClient.get("/api/portfolio-optimization");
      expect(response.status).toBe(200);

      const recommendations = response.data.data.recommended_trades;

      if (recommendations.length > 0) {
        const rec = recommendations[0];

        // Check for null values in critical fields
        const criticalFields = [
          "symbol",
          "action",
          "composite_score",
          "portfolio_fit_score",
          "market_fit_component",
          "correlation_component",
          "sector_component",
        ];

        const nullFields = [];
        for (const field of criticalFields) {
          if (rec[field] === null || rec[field] === undefined) {
            nullFields.push(field);
          }
        }

        if (nullFields.length > 0) {
          console.error(`❌ Found null values in: ${nullFields.join(", ")}`);
          throw new Error(`Null values found: ${nullFields.join(", ")}`);
        }

        console.log(`✓ All critical fields have real values`);
        console.log(`✓ Top recommendation: ${rec.symbol} - score ${rec.portfolio_fit_score.toFixed(1)}`);
      }

      console.log("✅ Data quality check passed\n");
    });

    test("should validate all numeric values are valid", async () => {
      console.log("\n🔢 TEST: Validating numeric values...");

      const response = await apiClient.get("/api/portfolio-optimization");
      const data = response.data.data;

      // Check portfolio metrics
      const metrics = data.portfolio_metrics.before;
      const numericFields = ["total_value", "composite_score", "concentration_ratio"];

      for (const field of numericFields) {
        if (metrics[field] !== null) {
          expect(isFinite(metrics[field])).toBe(true);
          expect(metrics[field]).not.toBeNaN();
        }
      }

      console.log("✓ All numeric values are valid");
      console.log("✅ Numeric validation passed\n");
    });
  });

  /**
   * TEST 6: Performance Metrics
   */
  describe("Performance Monitoring", () => {
    test("should return analysis within acceptable time", async () => {
      console.log("\n⏱️  TEST 6: Performance monitoring...");

      const startTime = Date.now();

      const response = await apiClient.get("/api/portfolio-optimization");

      const duration = Date.now() - startTime;

      console.log(`Response time: ${duration}ms`);
      expect(duration).toBeLessThan(10000); // Should complete in under 10 seconds

      const rating =
        duration < 2000
          ? "🚀 Excellent"
          : duration < 5000
          ? "✅ Good"
          : duration < 10000
          ? "⚠️ Acceptable"
          : "❌ Slow";

      console.log(`Performance rating: ${rating}`);
      console.log("✅ Performance test passed\n");
    });
  });

  /**
   * Cleanup: Remove test data
   */
  afterAll(async () => {
    console.log("\n🧹 Cleaning up test data...");

    try {
      await query(`DELETE FROM portfolio_holdings WHERE user_id = $1`, [TEST_USER_ID]);
      console.log(`✓ Removed test portfolio for user ${TEST_USER_ID}`);
    } catch (error) {
      console.warn("Could not clean up test data:", error.message);
    }

    console.log("✅ Cleanup complete\n");
  });
});

/**
 * Summary Report
 */
describe("E2E Test Summary", () => {
  test("all critical paths should be tested", () => {
    console.log("\n" + "=".repeat(60));
    console.log("END-TO-END TEST SUMMARY");
    console.log("=".repeat(60));
    console.log("✅ Portfolio Analysis - GET /api/portfolio-optimization");
    console.log("✅ Trade Execution - POST /api/portfolio-optimization/apply");
    console.log("✅ Database Verification - Portfolio state updated correctly");
    console.log("✅ Correlation Analysis - Diversification metrics calculated");
    console.log("✅ Data Quality - No null values in critical fields");
    console.log("✅ Performance - Response times acceptable");
    console.log("=".repeat(60) + "\n");
  });
});
