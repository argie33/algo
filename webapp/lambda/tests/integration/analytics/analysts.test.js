/**
 * Analysts Integration Tests
 * Tests for analyst recommendations and research data
 * Route: /routes/analysts.js
 *
 * INTEGRATION TEST - Uses REAL database and REAL services (NO MOCKS)
 */

const request = require("supertest");
const { app } = require("../../../index");

describe("Analysts API Integration", () => {
  describe("Analyst Recommendations", () => {
    test("should retrieve analyst recommendations for stock", async () => {
      const response = await request(app).get("/api/analysts/AAPL");

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("symbol", "AAPL");
      expect(response.body.data).toBeDefined();

      expect(response.body.data).toHaveProperty("upgrades_downgrades");
      expect(response.body.data).toHaveProperty("revenue_estimates");
      expect(response.body.data).toHaveProperty("eps_estimates");
      expect(Array.isArray(response.body.data.upgrades_downgrades)).toBe(true);
      expect(Array.isArray(response.body.data.revenue_estimates)).toBe(true);
      expect(Array.isArray(response.body.data.eps_estimates)).toBe(true);

      expect(response.body).toHaveProperty("counts");
      expect(response.body.counts).toHaveProperty("upgrades_downgrades");
      expect(response.body.counts).toHaveProperty("revenue_estimates");
      expect(response.body.counts).toHaveProperty("eps_estimates");
    });

    test("should handle invalid stock symbols", async () => {
      const response = await request(app).get("/api/analysts/INVALID123");

      expect([200, 404]).toContain(response.status);
      if (response.status === 404) {
        expect(response.body).toHaveProperty("success", false);
        expect(response.body).toHaveProperty("error");
      }
    });
  });

  describe("Analyst Coverage", () => {
    test("should return error for individual analyst coverage (not available from yfinance)", async () => {
      const response = await request(app).get("/api/analysts/coverage/AAPL");
      expect(response.status).toBe(404);
    });
  });

  describe("Price Targets", () => {
    test("should retrieve price targets for stock", async () => {
      const response = await request(app).get("/api/analysts/price-targets/AAPL");

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body.data).toBeDefined();

      expect(response.body.data).toHaveProperty("symbol", "AAPL");
      expect(response.body.data).toHaveProperty("price_targets");
      expect(Array.isArray(response.body.data.price_targets)).toBe(true);
      expect(response.body.data.price_targets.length).toBeGreaterThan(0);

      const target = response.body.data.price_targets[0];
      expect(target).toHaveProperty("analyst_firm");
      expect(target).toHaveProperty("target_price");
      expect(target).toHaveProperty("target_date");
      expect(typeof target.analyst_firm).toBe("string");
      expect(typeof target.target_price).toBe("number");
      expect(target.target_price).toBeGreaterThan(0);
    });

    test("should provide consensus price targets", async () => {
      const response = await request(app).get("/api/analysts/consensus/AAPL");

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body.data).toBeDefined();

      const consensus = response.body.data;
      expect(consensus).toHaveProperty("symbol", "AAPL");
      expect(consensus).toHaveProperty("target_high_price");
      expect(consensus).toHaveProperty("target_low_price");
      expect(consensus).toHaveProperty("target_mean_price");
      expect(consensus).toHaveProperty("recommendation_key");
      expect(consensus).toHaveProperty("analyst_opinion_count");

      expect(typeof consensus.target_high_price).toBe("number");
      expect(typeof consensus.target_low_price).toBe("number");
      expect(typeof consensus.target_mean_price).toBe("number");
      expect(typeof consensus.analyst_opinion_count).toBe("number");
      expect(consensus.target_high_price).toBeGreaterThan(consensus.target_low_price);
    });
  });

  describe("Analyst Research", () => {
    test("should retrieve research reports", async () => {
      const response = await request(app).get("/api/analysts/research?symbol=AAPL&limit=10");

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(Array.isArray(response.body.data)).toBe(true);
      expect(response.body.data.length).toBeGreaterThan(0);

      const research = response.body.data[0];
      expect(research).toHaveProperty("symbol", "AAPL");
      expect(research).toHaveProperty("analyst_firm");
      expect(research).toHaveProperty("report_title");
      expect(research).toHaveProperty("report_summary");
      expect(research).toHaveProperty("report_date");
      expect(typeof research.analyst_firm).toBe("string");
      expect(typeof research.report_title).toBe("string");
      expect(typeof research.report_summary).toBe("string");
    });

    test("should filter research by analyst firm", async () => {
      const response = await request(app).get("/api/analysts/research?firm=Goldman&limit=5");

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(Array.isArray(response.body.data)).toBe(true);

      if (response.body.data.length > 0) {
        response.body.data.forEach((report) => {
          expect(report.analyst_firm).toContain("Goldman");
        });
      }
    });
  });
});
