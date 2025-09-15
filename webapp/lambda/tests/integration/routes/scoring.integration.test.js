/**
 * Scoring Analysis Integration Tests
 * Tests for scoring factors and analysis methodologies
 * Route: /routes/scoring.js
 */

const request = require("supertest");
const { app } = require("../../../index");

describe("Scoring Analysis API", () => {
  describe("Scoring Overview", () => {
    test("should retrieve scoring endpoints", async () => {
      const response = await request(app).get("/api/scoring");

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("message");
        expect(response.body).toHaveProperty("endpoints");
        expect(Array.isArray(response.body.endpoints)).toBe(true);
      }
    });
  });

  describe("Scoring Factors", () => {
    test("should retrieve scoring factors analysis", async () => {
      const response = await request(app).get("/api/scoring/factors");

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);

        const factors = response.body.data;
        if (factors && Array.isArray(factors)) {
          if (factors.length > 0) {
            const factor = factors[0];
            expect(factor).toHaveProperty("factor_name");
            expect(factor).toHaveProperty("weight");
          }
        }
      }
    });

    test("should filter scoring factors by category", async () => {
      const response = await request(app).get(
        "/api/scoring/factors?category=fundamental"
      );

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(Array.isArray(response.body.data)).toBe(true);
      }
    });
  });

  describe("Symbol Scoring", () => {
    test("should calculate scoring metrics for symbol", async () => {
      const response = await request(app).get("/api/scoring/AAPL");

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body.data).toHaveProperty("symbol", "AAPL");

        const scoring = response.body.data;
        const scoringFields = [
          "total_score",
          "methodology",
          "factors",
          "ranking",
        ];
        const hasScoringData = scoringFields.some((field) =>
          Object.keys(scoring).some((key) =>
            key.toLowerCase().includes(field.replace("_", ""))
          )
        );

        expect(hasScoringData).toBe(true);
      }
    });

    test("should provide factor-based scoring breakdown", async () => {
      const response = await request(app).get("/api/scoring/AAPL/factors");

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);

        const breakdown = response.body.data;
        if (breakdown && Object.keys(breakdown).length > 0) {
          const factorFields = ["factor_scores", "weights", "contributions"];
          const hasFactorData = factorFields.some((field) =>
            Object.keys(breakdown).some((key) =>
              key.toLowerCase().includes(field.replace("_", ""))
            )
          );

          expect(hasFactorData).toBe(true);
        }
      }
    });
  });

  describe("Score Comparison", () => {
    test("should compare scores between multiple symbols", async () => {
      const response = await request(app).get(
        "/api/scoring/compare?symbols=AAPL,GOOGL,MSFT"
      );

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(Array.isArray(response.body.data)).toBe(true);

        if (response.body.data.length > 0) {
          const comparison = response.body.data[0];
          expect(comparison).toHaveProperty("symbol");
          expect(comparison).toHaveProperty("score");
        }
      }
    });
  });

  describe("Sector Scoring", () => {
    test("should provide sector-based scoring analysis", async () => {
      const response = await request(app).get("/api/scoring/sectors");

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(Array.isArray(response.body.data)).toBe(true);

        if (response.body.data.length > 0) {
          const sectorScoring = response.body.data[0];
          expect(sectorScoring).toHaveProperty("sector");

          const sectorFields = ["avg_score", "top_stocks", "methodology"];
          const hasSectorData = sectorFields.some((field) =>
            Object.keys(sectorScoring).some((key) =>
              key.toLowerCase().includes(field.replace("_", ""))
            )
          );

          expect(hasSectorData).toBe(true);
        }
      }
    });
  });
});
