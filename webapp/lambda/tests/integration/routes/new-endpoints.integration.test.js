/**
 * New Endpoints Integration Tests
 * Tests newly implemented endpoints: market correlation, momentum scoring, active orders, dashboard metrics
 */

const request = require("supertest");

const baseURL = "http://localhost:3001"; // Real server
const auth = { Authorization: "Bearer mock-access-token" };

describe("New Endpoints Integration Tests", () => {
  // Market Correlation Tests
  describe("Market Correlation API", () => {
    test("GET /api/market/correlation - should return correlation matrix", async () => {
      const response = await request(baseURL)
        .get("/api/market/correlation")
        .set(auth)
        .expect(200);

      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("correlation_matrix");
      expect(response.body.data).toHaveProperty("analysis");
      expect(response.body.data.correlation_matrix).toHaveProperty("symbols");
      expect(response.body.data.correlation_matrix).toHaveProperty("matrix");
      expect(response.body.data.correlation_matrix).toHaveProperty(
        "statistics"
      );
      expect(Array.isArray(response.body.data.correlation_matrix.symbols)).toBe(
        true
      );
      expect(Array.isArray(response.body.data.correlation_matrix.matrix)).toBe(
        true
      );
    });

    test("GET /api/market/correlation with symbol filter - should filter results", async () => {
      const response = await request(baseURL)
        .get("/api/market/correlation?symbols=AAPL,MSFT")
        .set(auth)
        .expect(200);

      expect(response.body).toHaveProperty("success", true);
      expect(response.body.data.correlation_matrix.symbols).toEqual([
        "AAPL",
        "MSFT",
      ]);
    });

    test("GET /api/market/correlation with period parameter - should accept different periods", async () => {
      const response = await request(baseURL)
        .get("/api/market/correlation?period=1W")
        .set(auth)
        .expect(200);

      expect(response.body).toHaveProperty("success", true);
      expect(response.body.data.correlation_matrix.period_analysis.period).toBe(
        "1W"
      );
    });
  });

  // Momentum Scoring Tests
  describe("Momentum Scoring API", () => {
    test("GET /api/scores/momentum - should return momentum scores", async () => {
      const response = await request(baseURL)
        .get("/api/scores/momentum")
        .set(auth)
        .expect(200);

      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("scores");
      expect(response.body.data).toHaveProperty("summary");
      expect(Array.isArray(response.body.data.scores)).toBe(true);

      if (response.body.data.scores.length > 0) {
        const score = response.body.data.scores[0];
        expect(score).toHaveProperty("symbol");
        expect(score).toHaveProperty("momentum_score");
        expect(score).toHaveProperty("components");
        expect(score).toHaveProperty("signals");
        expect(score.components).toHaveProperty("price_momentum");
        expect(score.components).toHaveProperty("volume_momentum");
        expect(score.components).toHaveProperty("technical_momentum");
        expect(score.components).toHaveProperty("trend_momentum");
      }
    });

    test("GET /api/scores/momentum with parameters - should respect limit and timeframe", async () => {
      const response = await request(baseURL)
        .get("/api/scores/momentum?limit=10&timeframe=1d")
        .set(auth)
        .expect(200);

      expect(response.body).toHaveProperty("success", true);
      expect(response.body.data.scores.length).toBeLessThanOrEqual(10);
      expect(response.body.data.summary.timeframe).toBe("1d");
    });
  });

  // Active Orders Tests
  describe("Active Orders API", () => {
    test("GET /api/orders/active - should return active orders", async () => {
      const response = await request(baseURL)
        .get("/api/orders/active")
        .set(auth)
        .expect(200);

      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("orders");
      expect(response.body.data).toHaveProperty("summary");
      expect(Array.isArray(response.body.data.orders)).toBe(true);

      if (response.body.data.orders.length > 0) {
        const order = response.body.data.orders[0];
        expect(order).toHaveProperty("order_id");
        expect(order).toHaveProperty("symbol");
        expect(order).toHaveProperty("side");
        expect(order).toHaveProperty("order_type");
        expect(order).toHaveProperty("status");
        expect(order).toHaveProperty("quantity");
        expect(order).toHaveProperty("created_at");
        expect(["BUY", "SELL"]).toContain(order.side);
        expect([
          "PENDING",
          "PARTIALLY_FILLED",
          "PENDING_CANCEL",
          "PENDING_REPLACE",
        ]).toContain(order.status);
      }
    });

    test("GET /api/orders/active with symbol filter - should filter by symbol", async () => {
      const response = await request(baseURL)
        .get("/api/orders/active?symbol=AAPL")
        .set(auth)
        .expect(200);

      expect(response.body).toHaveProperty("success", true);
      expect(response.body.data.filters.symbol).toBe("AAPL");

      // All returned orders should be for AAPL if any are returned
      if (response.body.data.orders.length > 0) {
        response.body.data.orders.forEach((order) => {
          expect(order.symbol).toBe("AAPL");
        });
      }
    });

    test("GET /api/orders/active with side filter - should filter by side", async () => {
      const response = await request(baseURL)
        .get("/api/orders/active?side=BUY")
        .set(auth)
        .expect(200);

      expect(response.body).toHaveProperty("success", true);
      expect(response.body.data.filters.side).toBe("BUY");

      // All returned orders should be BUY orders if any are returned
      if (response.body.data.orders.length > 0) {
        response.body.data.orders.forEach((order) => {
          expect(order.side).toBe("BUY");
        });
      }
    });
  });

  // Dashboard Metrics Tests
  describe("Dashboard Metrics API", () => {
    test("GET /api/metrics/dashboard - should return comprehensive dashboard data", async () => {
      const response = await request(baseURL)
        .get("/api/metrics/dashboard")
        .set(auth)
        .expect(200);

      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("dashboard");
      expect(response.body.data).toHaveProperty("insights");
      expect(response.body.data).toHaveProperty("market_status");

      const dashboard = response.body.data.dashboard;
      expect(dashboard).toHaveProperty("portfolio");
      expect(dashboard).toHaveProperty("market");
      expect(dashboard).toHaveProperty("performance");
      expect(dashboard).toHaveProperty("trading");
      expect(dashboard).toHaveProperty("alerts");
      expect(dashboard).toHaveProperty("top_holdings");
      expect(dashboard).toHaveProperty("watchlist");

      // Validate portfolio data structure
      expect(dashboard.portfolio).toHaveProperty("total_value");
      expect(dashboard.portfolio).toHaveProperty("daily_change");
      expect(dashboard.portfolio).toHaveProperty("allocation");
      expect(typeof dashboard.portfolio.total_value).toBe("number");
      expect(typeof dashboard.portfolio.daily_change).toBe("number");

      // Validate market data structure
      expect(dashboard.market).toHaveProperty("indices");
      expect(dashboard.market).toHaveProperty("sentiment");
      expect(dashboard.market.indices).toHaveProperty("spy");
      expect(dashboard.market.indices).toHaveProperty("qqq");

      // Validate performance data structure
      expect(dashboard.performance).toHaveProperty("returns");
      expect(dashboard.performance).toHaveProperty("risk_metrics");
      expect(dashboard.performance.returns).toHaveProperty("today");
      expect(dashboard.performance.risk_metrics).toHaveProperty("beta");

      // Validate trading data structure
      expect(dashboard.trading).toHaveProperty("orders");
      expect(dashboard.trading).toHaveProperty("volume");
      expect(dashboard.trading.orders).toHaveProperty("active");

      // Validate insights array
      expect(Array.isArray(response.body.data.insights)).toBe(true);
      expect(response.body.data.insights.length).toBeGreaterThan(0);
    });

    test("GET /api/metrics/dashboard with period parameter - should accept different periods", async () => {
      const response = await request(baseURL)
        .get("/api/metrics/dashboard?period=1W")
        .set(auth)
        .expect(200);

      expect(response.body).toHaveProperty("success", true);
      expect(response.body.data.dashboard.period_analyzed).toBe("1W");
    });

    test("GET /api/metrics/dashboard should include market status", async () => {
      const response = await request(baseURL)
        .get("/api/metrics/dashboard")
        .set(auth)
        .expect(200);

      expect(response.body).toHaveProperty("success", true);
      expect(response.body.data.market_status).toHaveProperty("is_open");
      expect(response.body.data.market_status).toHaveProperty("next_session");
      expect(response.body.data.market_status).toHaveProperty("timezone");
      expect(typeof response.body.data.market_status.is_open).toBe("boolean");
    });
  });

  // Error Handling Tests
  describe("Error Handling", () => {
    test("should handle invalid parameters gracefully", async () => {
      // Test with invalid correlation period
      const response = await request(baseURL)
        .get("/api/market/correlation?period=invalid")
        .set(auth)
        .expect(200); // Should still work, using default

      expect(response.body).toHaveProperty("success", true);
    });

    test("should handle missing authentication gracefully", async () => {
      const response = await request(baseURL).get("/api/scores/momentum");

      // Check if authentication is enabled or bypassed
      if (response.status === 401) {
        // Authentication is enforced
        expect(response.body).toHaveProperty("success", false);
      } else if (response.status === 200) {
        // Authentication is bypassed (development mode)
        expect(response.body).toHaveProperty("success", true);
      } else {
        throw new Error(`Unexpected status code: ${response.status}`);
      }
    });
  });

  // Symbol Financial Ratios Tests
  describe("Symbol Financial Ratios API", () => {
    test("GET /api/financials/ratios/:symbol - should return financial ratios", async () => {
      const response = await request(baseURL)
        .get("/api/financials/ratios/AAPL")
        .set(auth)
        .expect(200);

      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("ratios");
      expect(response.body.data.ratios).toHaveProperty("symbol", "AAPL");
      expect(response.body.data.ratios).toHaveProperty("valuation_ratios");
      expect(response.body.data.ratios).toHaveProperty("profitability_ratios");
      expect(response.body.data.ratios).toHaveProperty("liquidity_ratios");
      expect(response.body.data.ratios).toHaveProperty("leverage_ratios");
      expect(response.body.data.ratios).toHaveProperty("efficiency_ratios");
      expect(response.body.data.ratios).toHaveProperty("growth_ratios");
    });

    test("GET /api/financials/ratios/:symbol - should include peer comparison", async () => {
      const response = await request(baseURL)
        .get("/api/financials/ratios/MSFT")
        .set(auth)
        .expect(200);

      expect(response.body).toHaveProperty("success", true);
      expect(response.body.data).toHaveProperty("peer_comparison");
      expect(response.body.data.peer_comparison).toHaveProperty(
        "industry_averages"
      );
      expect(response.body.data.peer_comparison).toHaveProperty(
        "percentile_ranking"
      );
      expect(response.body.data.peer_comparison).toHaveProperty(
        "relative_performance"
      );
    });

    test("GET /api/financials/ratios/:symbol - should include analysis", async () => {
      const response = await request(baseURL)
        .get("/api/financials/ratios/GOOGL")
        .set(auth)
        .expect(200);

      expect(response.body).toHaveProperty("success", true);
      expect(response.body.data).toHaveProperty("analysis");
      expect(response.body.data.analysis).toHaveProperty("strengths");
      expect(response.body.data.analysis).toHaveProperty("concerns");
      expect(response.body.data.analysis).toHaveProperty("overall_score");
      expect(response.body.data.analysis).toHaveProperty("investment_grade");
      expect(Array.isArray(response.body.data.analysis.strengths)).toBe(true);
      expect(Array.isArray(response.body.data.analysis.concerns)).toBe(true);
    });
  });

  // Data Quality Tests
  describe("Data Quality Validation", () => {
    test("momentum scores should be within valid ranges", async () => {
      const response = await request(baseURL)
        .get("/api/scores/momentum")
        .set(auth)
        .expect(200);

      expect(response.body).toHaveProperty("success", true);

      if (response.body.data.scores.length > 0) {
        response.body.data.scores.forEach((score) => {
          expect(score.momentum_score).toBeGreaterThanOrEqual(0);
          expect(score.momentum_score).toBeLessThanOrEqual(100);
          expect(score.components.price_momentum).toBeGreaterThanOrEqual(0);
          expect(score.components.price_momentum).toBeLessThanOrEqual(100);
        });
      }
    });

    test("correlation values should be within valid ranges", async () => {
      const response = await request(baseURL)
        .get("/api/market/correlation")
        .set(auth)
        .expect(200);

      expect(response.body).toHaveProperty("success", true);

      const matrix = response.body.data.correlation_matrix.matrix;
      matrix.forEach((row) => {
        row.correlations.forEach((correlation) => {
          expect(correlation).toBeGreaterThanOrEqual(-1);
          expect(correlation).toBeLessThanOrEqual(1);
        });
      });
    });

    test("financial ratios should be realistic values", async () => {
      const response = await request(baseURL)
        .get("/api/financials/ratios/AAPL")
        .set(auth)
        .expect(200);

      const ratios = response.body.data.ratios;

      // Valuation ratios should be positive
      expect(ratios.valuation_ratios.price_to_earnings).toBeGreaterThan(0);
      expect(ratios.valuation_ratios.price_to_book).toBeGreaterThan(0);

      // Profitability ratios should be reasonable
      expect(ratios.profitability_ratios.net_profit_margin).toBeGreaterThan(0);
      expect(ratios.profitability_ratios.net_profit_margin).toBeLessThan(100);

      // Liquidity ratios should be positive
      expect(ratios.liquidity_ratios.current_ratio).toBeGreaterThan(0);
      expect(ratios.liquidity_ratios.quick_ratio).toBeGreaterThan(0);
    });

    test("dashboard financial values should be realistic", async () => {
      const response = await request(baseURL)
        .get("/api/metrics/dashboard")
        .set(auth)
        .expect(200);

      expect(response.body).toHaveProperty("success", true);

      const portfolio = response.body.data.dashboard.portfolio;
      expect(portfolio.total_value).toBeGreaterThan(0);
      expect(portfolio.cash_balance).toBeGreaterThanOrEqual(0);
      expect(portfolio.buying_power).toBeGreaterThanOrEqual(0);
      expect(portfolio.positions_count).toBeGreaterThanOrEqual(0);

      // Allocation percentages should sum to approximately 100%
      const allocation = portfolio.allocation;
      const total =
        allocation.stocks +
        allocation.etfs +
        allocation.cash +
        allocation.crypto;
      expect(total).toBeGreaterThan(95); // Allow for some rounding
      expect(total).toBeLessThan(105);
    });
  });
});
