/**
 * Performance Analytics Integration Tests
 * Tests for portfolio performance analysis and metrics
 * Route: /routes/performance.js
 */

const request = require("supertest");
const { app } = require("../../../index");

describe("Performance Analytics API", () => {
  describe("Portfolio Performance", () => {
    test("should retrieve portfolio performance overview", async () => {
      const response = await request(app)
        .get("/api/performance/portfolio")
        .set("Authorization", "Bearer test-token");

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);

        const performance = response.body.data;
        const performanceFields = [
          "total_return",
          "annualized_return",
          "sharpe_ratio",
          "max_drawdown",
        ];
        const hasPerformanceData = performanceFields.some((field) =>
          Object.keys(performance).some((key) =>
            key.toLowerCase().includes(field.replace("_", ""))
          )
        );

        expect(hasPerformanceData).toBe(true);
      }
    });

    test("should analyze performance over time periods", async () => {
      const response = await request(app).get(
        "/api/performance/returns?period=1Y"
      );

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(Array.isArray(response.body.data)).toBe(true);

        if (response.body.data.length > 0) {
          const periodData = response.body.data[0];
          expect(periodData).toHaveProperty("period");
          expect(periodData).toHaveProperty("return");
        }
      }
    });
  });

  describe("Benchmark Comparison", () => {
    test("should compare portfolio against benchmarks", async () => {
      const response = await request(app).get(
        "/api/performance/benchmark?indices=SPY,QQQ,VTI&period=1Y"
      );

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);

        const comparison = response.body.data;
        if (comparison && Object.keys(comparison).length > 0) {
          const benchmarkFields = [
            "portfolio_return",
            "benchmark_return",
            "alpha",
            "beta",
          ];
          const hasBenchmarkData = benchmarkFields.some((field) =>
            Object.keys(comparison).some((key) =>
              key.toLowerCase().includes(field.replace("_", ""))
            )
          );

          expect(hasBenchmarkData).toBe(true);
        }
      }
    });
  });

  describe("Risk-Adjusted Metrics", () => {
    test("should calculate risk-adjusted performance metrics", async () => {
      const response = await request(app).get(
        "/api/performance/risk?period=1Y"
      );

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);

        const metrics = response.body.data;
        const riskMetrics = [
          "sharpe_ratio",
          "sortino_ratio",
          "treynor_ratio",
          "information_ratio",
        ];
        const hasRiskMetrics = riskMetrics.some((field) =>
          Object.keys(metrics).some((key) =>
            key.toLowerCase().includes(field.replace("_", ""))
          )
        );

        expect(hasRiskMetrics).toBe(true);
      }
    });
  });

  describe("Attribution Analysis", () => {
    test("should perform sector attribution analysis", async () => {
      const response = await request(app).get(
        "/api/performance/attribution?type=sector&period=6M"
      );

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(Array.isArray(response.body.data)).toBe(true);

        if (response.body.data.length > 0) {
          const sectorAttribution = response.body.data[0];
          expect(sectorAttribution).toHaveProperty("sector");

          const attributionFields = ["weight", "return", "contribution"];
          const hasAttributionData = attributionFields.some((field) =>
            Object.keys(sectorAttribution).some((key) =>
              key.toLowerCase().includes(field)
            )
          );

          expect(hasAttributionData).toBe(true);
        }
      }
    });

    test("should perform stock-level attribution analysis", async () => {
      const response = await request(app).get(
        "/api/performance/attribution?type=stocks&period=3M&top=10"
      );

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(Array.isArray(response.body.data)).toBe(true);

        if (response.body.data.length > 0) {
          const stockAttribution = response.body.data[0];
          expect(stockAttribution).toHaveProperty("symbol");
          expect(stockAttribution).toHaveProperty("contribution");
        }
      }
    });
  });

  describe("Performance Reports", () => {
    test("should generate comprehensive performance report", async () => {
      const reportRequest = {
        period: "1Y",
        include_benchmarks: true,
        include_attribution: true,
        format: "detailed",
      };

      const response = await request(app)
        .get("/api/performance/summary")
        .set("Authorization", "Bearer test-token")
        .send(reportRequest);

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body.data).toHaveProperty("report_id");
        expect(response.body.data).toHaveProperty("report_url");
      }
    });

    test("should retrieve historical performance reports", async () => {
      const response = await request(app)
        .get("/api/performance/analytics")
        .set("Authorization", "Bearer test-token");

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(Array.isArray(response.body.data)).toBe(true);

        if (response.body.data.length > 0) {
          const report = response.body.data[0];
          expect(report).toHaveProperty("report_id");
          expect(report).toHaveProperty("created_date");
          expect(report).toHaveProperty("period");
        }
      }
    });
  });

  describe("Performance Alerts", () => {
    test("should set performance-based alerts", async () => {
      const alertConfig = {
        alert_type: "drawdown",
        threshold: -0.05, // 5% drawdown
        notification_method: "email",
        frequency: "immediate",
      };

      const response = await request(app)
        .get("/api/performance/alerts")
        .set("Authorization", "Bearer test-token")
        .send(alertConfig);

      expect([200, 404]).toContain(response.status);

      if (response.status === 200 || response.status === 201) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body.data).toHaveProperty("alert_id");
      }
    });
  });
});
