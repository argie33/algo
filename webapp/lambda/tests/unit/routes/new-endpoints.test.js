/**
 * New Endpoints Unit Tests
 * Unit tests for newly implemented endpoints using mocked dependencies
 */

const request = require("supertest");
const express = require("express");

// Import route modules
const marketRoutes = require("../../../routes/market");
const scoringRoutes = require("../../../routes/scoring");
const ordersRoutes = require("../../../routes/orders");
const metricsRoutes = require("../../../routes/metrics");

// Mock middleware
const mockAuth = (req, res, next) => {
  req.user = { sub: "test-user", email: "test@example.com" };
  req.token = "test-token";
  next();
};

const mockResponseFormatter = (req, res, next) => {
  res.success = (message, data) => {
    res.json({ success: true, message, data });
  };
  res.error = (message, statusCode, details) => {
    res
      .status(statusCode || 500)
      .json({ success: false, error: message, details });
  };
  next();
};

// Create test app
function createTestApp(routes) {
  const app = express();
  app.use(express.json());
  app.use(mockResponseFormatter);
  app.use(mockAuth);
  app.use("/", routes);
  return app;
}

describe("New Endpoints Unit Tests", () => {
  describe("Market Correlation Endpoint", () => {
    const app = createTestApp(marketRoutes);

    test("GET /correlation - should return correlation matrix with default parameters", async () => {
      const response = await request(app).get("/correlation").expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty("correlation_matrix");
      expect(response.body.data).toHaveProperty("analysis");
      expect(response.body.data.correlation_matrix).toHaveProperty("symbols");
      expect(response.body.data.correlation_matrix).toHaveProperty("matrix");
      expect(response.body.data.correlation_matrix).toHaveProperty(
        "statistics"
      );

      // Verify matrix structure
      const matrix = response.body.data.correlation_matrix.matrix;
      expect(Array.isArray(matrix)).toBe(true);
      if (matrix.length > 0) {
        expect(matrix[0]).toHaveProperty("symbol");
        expect(matrix[0]).toHaveProperty("correlations");
        expect(Array.isArray(matrix[0].correlations)).toBe(true);
      }

      // Verify statistics
      const stats = response.body.data.correlation_matrix.statistics;
      expect(stats).toHaveProperty("avg_correlation");
      expect(stats).toHaveProperty("max_correlation");
      expect(stats).toHaveProperty("min_correlation");
      expect(typeof stats.avg_correlation).toBe("number");
    });

    test("GET /correlation with symbol filter - should filter symbols", async () => {
      const response = await request(app)
        .get("/correlation?symbols=AAPL,MSFT")
        .expect(200);

      expect(response.body.success).toBe(true);
      const symbols = response.body.data.correlation_matrix.symbols;
      expect(symbols).toEqual(["AAPL", "MSFT"]);
    });

    test("GET /correlation with period parameter - should use specified period", async () => {
      const response = await request(app)
        .get("/correlation?period=1W")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.correlation_matrix.period_analysis.period).toBe(
        "1W"
      );
    });

    test("GET /correlation - should include analysis and recommendations", async () => {
      const response = await request(app).get("/correlation").expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.analysis).toHaveProperty("market_regime");
      expect(response.body.data.analysis).toHaveProperty(
        "diversification_score"
      );
      expect(response.body.data.analysis).toHaveProperty("risk_assessment");
      expect(Array.isArray(response.body.data.recommendations)).toBe(true);
    });
  });

  describe("Momentum Scoring Endpoint", () => {
    const app = createTestApp(scoringRoutes);

    test("GET /momentum - should return momentum scores with default parameters", async () => {
      const response = await request(app).get("/momentum").expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty("scores");
      expect(response.body.data).toHaveProperty("summary");
      expect(response.body.data).toHaveProperty("methodology");

      // Verify scores structure
      const scores = response.body.data.scores;
      expect(Array.isArray(scores)).toBe(true);
      if (scores.length > 0) {
        const score = scores[0];
        expect(score).toHaveProperty("symbol");
        expect(score).toHaveProperty("momentum_score");
        expect(score).toHaveProperty("components");
        expect(score).toHaveProperty("metrics");
        expect(score).toHaveProperty("signals");

        // Verify components
        expect(score.components).toHaveProperty("price_momentum");
        expect(score.components).toHaveProperty("volume_momentum");
        expect(score.components).toHaveProperty("technical_momentum");
        expect(score.components).toHaveProperty("trend_momentum");

        // Verify signals
        expect(score.signals).toHaveProperty("strength");
        expect(score.signals).toHaveProperty("direction");
        expect(score.signals).toHaveProperty("confidence");
        expect(["Strong", "Moderate", "Weak"]).toContain(
          score.signals.strength
        );
        expect(["Bullish", "Bearish"]).toContain(score.signals.direction);
      }
    });

    test("GET /momentum with limit parameter - should respect limit", async () => {
      const response = await request(app).get("/momentum?limit=5").expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.scores.length).toBeLessThanOrEqual(5);
    });

    test("GET /momentum with timeframe parameter - should use specified timeframe", async () => {
      const response = await request(app)
        .get("/momentum?timeframe=1d")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.summary.timeframe).toBe("1d");
    });

    test("GET /momentum - should include summary statistics", async () => {
      const response = await request(app).get("/momentum").expect(200);

      expect(response.body.success).toBe(true);
      const summary = response.body.data.summary;
      expect(summary).toHaveProperty("total_analyzed");
      expect(summary).toHaveProperty("avg_momentum");
      expect(summary).toHaveProperty("strong_momentum");
      expect(summary).toHaveProperty("weak_momentum");
      expect(summary).toHaveProperty("bullish_signals");
      expect(summary).toHaveProperty("bearish_signals");
      expect(summary).toHaveProperty("market_sentiment");
      expect(["Bullish", "Bearish"]).toContain(summary.market_sentiment);
    });
  });

  describe("Active Orders Endpoint", () => {
    const app = createTestApp(ordersRoutes);

    test("GET /active - should return active orders with default parameters", async () => {
      const response = await request(app).get("/active").expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty("orders");
      expect(response.body.data).toHaveProperty("summary");
      expect(response.body.data).toHaveProperty("filters");
      expect(response.body.data).toHaveProperty("actions");

      // Verify orders structure
      const orders = response.body.data.orders;
      expect(Array.isArray(orders)).toBe(true);
      if (orders.length > 0) {
        const order = orders[0];
        expect(order).toHaveProperty("order_id");
        expect(order).toHaveProperty("symbol");
        expect(order).toHaveProperty("side");
        expect(order).toHaveProperty("order_type");
        expect(order).toHaveProperty("status");
        expect(order).toHaveProperty("quantity");
        expect(order).toHaveProperty("created_at");
        expect(order).toHaveProperty("market_conditions");
        expect(order).toHaveProperty("order_flags");

        // Verify valid values
        expect(["BUY", "SELL"]).toContain(order.side);
        expect([
          "PENDING",
          "PARTIALLY_FILLED",
          "PENDING_CANCEL",
          "PENDING_REPLACE",
        ]).toContain(order.status);
        expect([
          "LIMIT",
          "STOP",
          "STOP_LIMIT",
          "MARKET",
          "TRAILING_STOP",
        ]).toContain(order.order_type);
        expect(typeof order.quantity).toBe("number");
        expect(order.quantity).toBeGreaterThan(0);
      }
    });

    test("GET /active with symbol filter - should filter by symbol", async () => {
      const response = await request(app)
        .get("/active?symbol=AAPL")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.filters.symbol).toBe("AAPL");

      // All orders should be for AAPL (if any exist)
      const orders = response.body.data.orders;
      orders.forEach((order) => {
        expect(order.symbol).toBe("AAPL");
      });
    });

    test("GET /active with side filter - should filter by side", async () => {
      const response = await request(app).get("/active?side=BUY").expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.filters.side).toBe("BUY");

      // All orders should be BUY orders (if any exist)
      const orders = response.body.data.orders;
      orders.forEach((order) => {
        expect(order.side).toBe("BUY");
      });
    });

    test("GET /active - should include summary statistics", async () => {
      const response = await request(app).get("/active").expect(200);

      expect(response.body.success).toBe(true);
      const summary = response.body.data.summary;
      expect(summary).toHaveProperty("total_orders");
      expect(summary).toHaveProperty("total_value");
      expect(summary).toHaveProperty("buy_orders");
      expect(summary).toHaveProperty("sell_orders");
      expect(summary).toHaveProperty("partially_filled");
      expect(summary).toHaveProperty("pending_orders");
      expect(summary).toHaveProperty("order_types");
      expect(summary).toHaveProperty("avg_execution_probability");
      expect(typeof summary.total_orders).toBe("number");
      expect(typeof summary.total_value).toBe("number");
    });
  });

  describe("Dashboard Metrics Endpoint", () => {
    const app = createTestApp(metricsRoutes);

    test("GET /dashboard - should return comprehensive dashboard data", async () => {
      const response = await request(app).get("/dashboard").expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty("dashboard");
      expect(response.body.data).toHaveProperty("insights");
      expect(response.body.data).toHaveProperty("market_status");

      // Verify dashboard structure
      const dashboard = response.body.data.dashboard;
      expect(dashboard).toHaveProperty("portfolio");
      expect(dashboard).toHaveProperty("market");
      expect(dashboard).toHaveProperty("performance");
      expect(dashboard).toHaveProperty("trading");
      expect(dashboard).toHaveProperty("alerts");
      expect(dashboard).toHaveProperty("top_holdings");
      expect(dashboard).toHaveProperty("watchlist");
      expect(dashboard).toHaveProperty("last_updated");

      // Verify portfolio section
      expect(dashboard.portfolio).toHaveProperty("total_value");
      expect(dashboard.portfolio).toHaveProperty("daily_change");
      expect(dashboard.portfolio).toHaveProperty("allocation");
      expect(typeof dashboard.portfolio.total_value).toBe("number");
      expect(typeof dashboard.portfolio.daily_change).toBe("number");

      // Verify market section
      expect(dashboard.market).toHaveProperty("indices");
      expect(dashboard.market).toHaveProperty("sentiment");
      expect(dashboard.market.indices).toHaveProperty("spy");
      expect(dashboard.market.indices).toHaveProperty("qqq");

      // Verify performance section
      expect(dashboard.performance).toHaveProperty("returns");
      expect(dashboard.performance).toHaveProperty("risk_metrics");
      expect(dashboard.performance.returns).toHaveProperty("today");
      expect(dashboard.performance.risk_metrics).toHaveProperty("beta");
    });

    test("GET /dashboard with period parameter - should use specified period", async () => {
      const response = await request(app)
        .get("/dashboard?period=1W")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.dashboard.period_analyzed).toBe("1W");
    });

    test("GET /dashboard - should include market status", async () => {
      const response = await request(app).get("/dashboard").expect(200);

      expect(response.body.success).toBe(true);
      const marketStatus = response.body.data.market_status;
      expect(marketStatus).toHaveProperty("is_open");
      expect(marketStatus).toHaveProperty("next_session");
      expect(marketStatus).toHaveProperty("timezone");
      expect(typeof marketStatus.is_open).toBe("boolean");
      expect(marketStatus.timezone).toBe("EST");
    });

    test("GET /dashboard - should include insights array", async () => {
      const response = await request(app).get("/dashboard").expect(200);

      expect(response.body.success).toBe(true);
      const insights = response.body.data.insights;
      expect(Array.isArray(insights)).toBe(true);
      expect(insights.length).toBeGreaterThan(0);
      insights.forEach((insight) => {
        expect(typeof insight).toBe("string");
      });
    });
  });

  describe("Symbol Financial Ratios Endpoint", () => {
    const financialsRoutes = require("../../../routes/financials");
    const app = createTestApp(financialsRoutes);

    test("GET /ratios/:symbol - should return financial ratios for valid symbol", async () => {
      const response = await request(app).get("/ratios/AAPL").expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty("ratios");
      expect(response.body.data.ratios).toHaveProperty("symbol", "AAPL");
      expect(response.body.data.ratios).toHaveProperty("valuation_ratios");
      expect(response.body.data.ratios).toHaveProperty("profitability_ratios");
      expect(response.body.data.ratios).toHaveProperty("liquidity_ratios");
      expect(response.body.data.ratios).toHaveProperty("leverage_ratios");
      expect(response.body.data.ratios).toHaveProperty("efficiency_ratios");
      expect(response.body.data.ratios).toHaveProperty("growth_ratios");

      // Verify valuation ratios structure
      const valuation = response.body.data.ratios.valuation_ratios;
      expect(valuation).toHaveProperty("price_to_earnings");
      expect(valuation).toHaveProperty("forward_pe");
      expect(valuation).toHaveProperty("price_to_book");
      expect(valuation).toHaveProperty("price_to_sales");
      expect(valuation).toHaveProperty("ev_to_ebitda");

      // Verify profitability ratios structure
      const profitability = response.body.data.ratios.profitability_ratios;
      expect(profitability).toHaveProperty("net_profit_margin");
      expect(profitability).toHaveProperty("return_on_equity");
      expect(profitability).toHaveProperty("return_on_assets");
      expect(profitability).toHaveProperty("gross_margin");
    });

    test("GET /ratios/:symbol - should include peer comparison", async () => {
      const response = await request(app).get("/ratios/MSFT").expect(200);

      expect(response.body.success).toBe(true);
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

      const industryAvg = response.body.data.peer_comparison.industry_averages;
      expect(industryAvg).toHaveProperty("pe_ratio");
      expect(industryAvg).toHaveProperty("pb_ratio");
      expect(industryAvg).toHaveProperty("profit_margin");
    });

    test("GET /ratios/:symbol - should include analysis and recommendations", async () => {
      const response = await request(app).get("/ratios/GOOGL").expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty("analysis");
      expect(response.body.data.analysis).toHaveProperty("strengths");
      expect(response.body.data.analysis).toHaveProperty("concerns");
      expect(response.body.data.analysis).toHaveProperty("overall_score");
      expect(response.body.data.analysis).toHaveProperty("investment_grade");

      expect(Array.isArray(response.body.data.analysis.strengths)).toBe(true);
      expect(Array.isArray(response.body.data.analysis.concerns)).toBe(true);
      expect(typeof response.body.data.analysis.overall_score).toBe("number");
      expect(response.body.data.analysis.overall_score).toBeGreaterThanOrEqual(
        0
      );
      expect(response.body.data.analysis.overall_score).toBeLessThanOrEqual(
        100
      );
    });

    test("GET /ratios/:symbol - should handle unknown symbols", async () => {
      const response = await request(app).get("/ratios/UNKNOWN").expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.ratios.symbol).toBe("UNKNOWN");
      // Should still return data with calculated ratios
      expect(response.body.data.ratios).toHaveProperty("valuation_ratios");
      expect(response.body.data.ratios).toHaveProperty("profitability_ratios");
    });
  });

  describe("Data Validation Tests", () => {
    test("correlation values should be valid numbers between -1 and 1", async () => {
      const app = createTestApp(marketRoutes);
      const response = await request(app).get("/correlation").expect(200);

      const matrix = response.body.data.correlation_matrix.matrix;
      matrix.forEach((row) => {
        row.correlations.forEach((correlation) => {
          expect(typeof correlation).toBe("number");
          expect(correlation).toBeGreaterThanOrEqual(-1);
          expect(correlation).toBeLessThanOrEqual(1);
          expect(isNaN(correlation)).toBe(false);
        });
      });
    });

    test("momentum scores should be valid numbers between 0 and 100", async () => {
      const app = createTestApp(scoringRoutes);
      const response = await request(app).get("/momentum").expect(200);

      const scores = response.body.data.scores;
      scores.forEach((score) => {
        expect(typeof score.momentum_score).toBe("number");
        expect(score.momentum_score).toBeGreaterThanOrEqual(0);
        expect(score.momentum_score).toBeLessThanOrEqual(100);
        expect(isNaN(score.momentum_score)).toBe(false);

        // Validate component scores
        Object.values(score.components).forEach((component) => {
          expect(typeof component).toBe("number");
          expect(component).toBeGreaterThanOrEqual(0);
          expect(component).toBeLessThanOrEqual(100);
        });
      });
    });

    test("financial ratios should be realistic values", async () => {
      const financialsRoutes = require("../../../routes/financials");
      const app = createTestApp(financialsRoutes);
      const response = await request(app).get("/ratios/AAPL").expect(200);

      const ratios = response.body.data.ratios;

      // Valuation ratios should be positive
      expect(ratios.valuation_ratios.price_to_earnings).toBeGreaterThan(0);
      expect(ratios.valuation_ratios.price_to_book).toBeGreaterThan(0);

      // Profitability ratios should be reasonable
      expect(ratios.profitability_ratios.net_profit_margin).toBeGreaterThan(0);
      expect(ratios.profitability_ratios.net_profit_margin).toBeLessThan(100);
      expect(ratios.profitability_ratios.return_on_equity).toBeGreaterThan(0);

      // Liquidity ratios should be positive
      expect(ratios.liquidity_ratios.current_ratio).toBeGreaterThan(0);
      expect(ratios.liquidity_ratios.quick_ratio).toBeGreaterThan(0);
    });

    test("dashboard financial values should be realistic", async () => {
      const app = createTestApp(metricsRoutes);
      const response = await request(app).get("/dashboard").expect(200);

      const portfolio = response.body.data.dashboard.portfolio;
      expect(portfolio.total_value).toBeGreaterThan(0);
      expect(portfolio.cash_balance).toBeGreaterThanOrEqual(0);
      expect(portfolio.buying_power).toBeGreaterThanOrEqual(0);
      expect(portfolio.positions_count).toBeGreaterThanOrEqual(0);

      // Check allocation percentages
      const allocation = portfolio.allocation;
      expect(allocation.stocks).toBeGreaterThanOrEqual(0);
      expect(allocation.stocks).toBeLessThanOrEqual(100);
      expect(allocation.etfs).toBeGreaterThanOrEqual(0);
      expect(allocation.etfs).toBeLessThanOrEqual(100);
      expect(allocation.cash).toBeGreaterThanOrEqual(0);
      expect(allocation.cash).toBeLessThanOrEqual(100);
    });
  });
});
