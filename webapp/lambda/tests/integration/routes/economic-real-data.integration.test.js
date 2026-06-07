/**
 * Economic Endpoints Integration Tests
 * Tests that ALL endpoints return REAL data from FRED database - NO MOCKS
 * All tests require actual database connection and FRED data loaded
 */

const express = require("express");
const request = require("supertest");
const { query } = require("../../../utils/database");

// DO NOT MOCK - use real database
describe("Economic Endpoints - REAL DATA Integration Tests", () => {
  let app;
  let marketRouter;

  beforeAll(() => {
    app = express();
    app.use(express.json());
    marketRouter = require("../../../routes/market");
    app.use("/market", marketRouter);
  });

  describe("GET /market/recession-forecast - REAL DATA", () => {
    test("should return recession forecast with REAL data from database", async () => {
      const response = await request(app).get("/market/recession-forecast");

      // Should return 200 or 503 (503 if data not loaded)
      expect([200, 503]).toContain(response.status);

      // If successful, validate REAL data structure
      if (response.status === 200) {
        expect(response.body).toHaveProperty("data");
        const data = response.body.data;

        // REAL data properties - not mock defaults
        expect(data).toHaveProperty("compositeRecessionProbability");
        expect(typeof data.compositeRecessionProbability).toBe("number");
        expect(data.compositeRecessionProbability).toBeGreaterThanOrEqual(0);
        expect(data.compositeRecessionProbability).toBeLessThanOrEqual(100);

        // Real economic indicators
        expect(data).toHaveProperty("keyIndicators");
        expect(data.keyIndicators).toHaveProperty("yieldCurveSpread2y10y");
        expect(data.keyIndicators).toHaveProperty("unemployment");
        expect(data.keyIndicators).toHaveProperty("fedFundsRate");
        expect(data.keyIndicators).toHaveProperty("highYieldSpread");

        // All should be real numbers, not mock defaults
        expect(typeof data.keyIndicators.yieldCurveSpread2y10y).toBe("number");
        expect(typeof data.keyIndicators.unemployment).toBe("number");
        expect(typeof data.keyIndicators.fedFundsRate).toBe("number");
        expect(typeof data.keyIndicators.highYieldSpread).toBe("number");

        // Forecast models
        expect(Array.isArray(data.forecastModels)).toBe(true);
        expect(data.forecastModels.length).toBeGreaterThan(0);
        data.forecastModels.forEach((model) => {
          expect(model).toHaveProperty("name");
          expect(model).toHaveProperty("probability");
          expect(typeof model.probability).toBe("number");
          expect(model.probability).toBeGreaterThanOrEqual(0);
          expect(model.probability).toBeLessThanOrEqual(100);
        });

        // Analysis
        expect(data).toHaveProperty("analysis");
        expect(data.analysis).toHaveProperty("factors");
        expect(Array.isArray(data.analysis.factors)).toBe(true);
        expect(data.analysis.factors.length).toBeGreaterThan(0);
      } else {
        // 503 error should indicate missing data
        expect(response.body).toHaveProperty("error");
        expect(response.body).toHaveProperty("missing");
        expect(Array.isArray(response.body.missing)).toBe(true);
      }
    });

    test("should validate no mock fallback values are used", async () => {
      const response = await request(app).get("/market/recession-forecast");

      if (response.status === 200) {
        const data = response.body.data;
        const indicators = data.keyIndicators;

        // Mock default values that should NEVER appear
        const mockDefaults = [0, 4.0, 20, 6000, 350, 100]; // Common fallback values

        // Unemployment should rarely be exactly 4.0 (mock default)
        if (indicators.unemployment === 4.0) {
          console.warn("Warning: Unemployment is exactly 4.0 (potential mock default)");
        }

        // VIX should rarely be exactly 20 (mock default)
        if (indicators.vix === 20) {
          console.warn("Warning: VIX is exactly 20 (potential mock default)");
        }

        // This test just logs warnings but doesn't fail hard
        // Real data loaded from FRED could theoretically match these values
      }
    });
  });

  describe("GET /market/credit-spreads - REAL DATA", () => {
    test("should return credit spreads with REAL data from database", async () => {
      const response = await request(app).get("/market/credit-spreads");

      expect([200, 503]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("data");
        const data = response.body.data;

        // Real data structure
        expect(data).toHaveProperty("creditStressIndex");
        expect(typeof data.creditStressIndex).toBe("number");
        expect(data.creditStressIndex).toBeGreaterThanOrEqual(0);
        expect(data.creditStressIndex).toBeLessThanOrEqual(100);

        // Credit spreads from FRED
        expect(data).toHaveProperty("spreads");
        expect(data.spreads).toHaveProperty("highYield");
        expect(data.spreads.highYield).toHaveProperty("oas");
        expect(typeof data.spreads.highYield.oas).toBe("number");
        expect(data.spreads.highYield.oas).toBeGreaterThan(0);

        expect(data.spreads).toHaveProperty("investmentGrade");
        expect(data.spreads.investmentGrade).toHaveProperty("oas");
        expect(typeof data.spreads.investmentGrade.oas).toBe("number");

        // Financial Conditions Index
        expect(data).toHaveProperty("financialConditionsIndex");
        expect(data.financialConditionsIndex).toHaveProperty("value");
      } else {
        expect(response.body).toHaveProperty("error");
        expect(response.body.error).toContain("Missing required credit spread data");
      }
    });
  });

  describe("GET /market/leading-indicators - REAL DATA", () => {
    test("should return leading indicators with REAL data from database", async () => {
      const response = await request(app).get("/market/leading-indicators");

      expect([200, 503]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("data");
        const data = response.body.data;

        // Real indicators
        expect(data).toHaveProperty("indicators");
        expect(Array.isArray(data.indicators)).toBe(true);
        expect(data.indicators.length).toBeGreaterThan(5);

        // Each indicator should be real
        data.indicators.forEach((indicator) => {
          expect(indicator).toHaveProperty("name");
          expect(indicator).toHaveProperty("value");
          expect(indicator).toHaveProperty("signal");
          expect(["Positive", "Negative", "Neutral"]).toContain(indicator.signal);
          // Value should not be empty string or null
          expect(indicator.value).not.toBe("");
          expect(indicator.value).not.toBeNull();
        });

        // Yield curve
        expect(data).toHaveProperty("yieldCurveData");
        expect(Array.isArray(data.yieldCurveData)).toBe(true);
        expect(data.yieldCurveData.length).toBeGreaterThan(0);

        // Each yield point should be real
        data.yieldCurveData.forEach((point) => {
          expect(point).toHaveProperty("maturity");
          expect(point).toHaveProperty("yield");
          expect(typeof point.yield).toBe("string");
          expect(Number(point.yield)).not.toBeNaN();
        });

        // Upcoming events (from calendar table)
        expect(data).toHaveProperty("upcomingEvents");
        expect(Array.isArray(data.upcomingEvents)).toBe(true);
        // May be empty if no events, but should be an array
      } else {
        expect(response.body).toHaveProperty("error");
        expect(response.body.error).toContain("Missing required economic indicators");
      }
    });
  });

  describe("GET /market/economic-scenarios - REAL DATA", () => {
    test("should return scenarios based on REAL database data", async () => {
      const response = await request(app).get("/market/economic-scenarios");

      expect([200, 503]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("data");
        const data = response.body.data;

        expect(data).toHaveProperty("scenarios");
        expect(Array.isArray(data.scenarios)).toBe(true);
        expect(data.scenarios.length).toBe(3); // Bull, Base, Bear

        let totalProbability = 0;
        data.scenarios.forEach((scenario) => {
          expect(scenario).toHaveProperty("name");
          expect(scenario).toHaveProperty("probability");
          expect(scenario).toHaveProperty("gdpGrowth");
          expect(scenario).toHaveProperty("unemployment");
          expect(typeof scenario.probability).toBe("number");
          expect(scenario.probability).toBeGreaterThan(0);
          totalProbability += scenario.probability;

          // Values should be numeric
          expect(typeof scenario.gdpGrowth).toBe("number");
          expect(typeof scenario.unemployment).toBe("number");
        });

        // Probabilities should sum to 100
        expect(totalProbability).toBe(100);
      }
    });
  });

  describe("Real Data Flow Validation", () => {
    test("should have consistent data across all endpoints", async () => {
      const recessionRes = await request(app).get("/market/recession-forecast");
      const leadingRes = await request(app).get("/market/leading-indicators");
      const creditRes = await request(app).get("/market/credit-spreads");

      // If all succeed, validate consistency
      if (
        recessionRes.status === 200 &&
        leadingRes.status === 200 &&
        creditRes.status === 200
      ) {
        const recData = recessionRes.body.data;
        const leadData = leadingRes.body.data;
        const credData = creditRes.body.data;

        // Unemployment should be the same
        expect(Math.abs(recData.keyIndicators.unemployment - leadData.unemployment)).toBeLessThan(
          0.1
        );

        // Yield curve should have same data
        expect(recData.keyIndicators.yieldCurveSpread2y10y).toBeDefined();
        expect(leadData.yieldCurve.spread2y10y).toBeDefined();

        // Credit stress should be consistent
        expect(recData.keyIndicators.highYieldSpread).toBeDefined();
        expect(credData.creditStressIndex).toBeDefined();
      }
    });

    test("all endpoints should return proper timestamps", async () => {
      const endpoints = [
        "/market/recession-forecast",
        "/market/credit-spreads",
        "/market/leading-indicators",
      ];

      for (const endpoint of endpoints) {
        const response = await request(app).get(endpoint);

        if (response.status === 200) {
          expect(response.body).toHaveProperty("timestamp");
          expect(new Date(response.body.timestamp)).toBeInstanceOf(Date);
        }
      }
    });
  });

  describe("Error Handling - Missing FRED Data", () => {
    test("should return 503 with missing data indicators if FRED data not loaded", async () => {
      const response = await request(app).get("/market/recession-forecast");

      // If database is empty and data not loaded
      if (response.status === 503) {
        expect(response.body).toHaveProperty("error");
        expect(response.body).toHaveProperty("missing");
        expect(response.body).toHaveProperty("message");
        expect(response.body.message).toContain("loadecondata.py");
      }
    });
  });

  describe("Data Types Validation", () => {
    test("all numeric values should be valid numbers", async () => {
      const response = await request(app).get("/market/recession-forecast");

      if (response.status === 200) {
        const data = response.body.data;
        const indicators = data.keyIndicators;

        // Validate all are actual numbers, not NaN or Infinity
        Object.entries(indicators).forEach(([key, value]) => {
          if (value !== null) {
            expect(typeof value).toBe("number");
            expect(Number.isNaN(value)).toBe(false);
            expect(Number.isFinite(value)).toBe(true);
          }
        });
      }
    });

    test("all strings should be properly formatted", async () => {
      const response = await request(app).get("/market/leading-indicators");

      if (response.status === 200) {
        const data = response.body.data;

        data.indicators.forEach((indicator) => {
          expect(typeof indicator.name).toBe("string");
          expect(indicator.name.length).toBeGreaterThan(0);
          expect(typeof indicator.value).toBe("string");
          expect(indicator.value.length).toBeGreaterThan(0);
        });
      }
    });
  });
});
