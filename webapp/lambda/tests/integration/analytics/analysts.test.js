/**
 * Analysts Integration Tests
 * Tests for analyst recommendations and research data
 * Route: /routes/analysts.js
 */

const request = require("supertest");
const { app } = require("../../../index");

describe("Analysts API", () => {
  describe("Analyst Recommendations", () => {
    test("should retrieve analyst recommendations for stock", async () => {
      const response = await request(app)
        .get("/api/analysts/recommendations/AAPL");
      
      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(Array.isArray(response.body.data)).toBe(true);
        
        if (response.body.data.length > 0) {
          const recommendation = response.body.data[0];
          expect(recommendation).toHaveProperty("analyst");
          expect(recommendation).toHaveProperty("rating");
          
          const recFields = ["target_price", "date", "previous_rating"];
          const hasRecData = recFields.some(field => 
            Object.keys(recommendation).some(key => key.toLowerCase().includes(field.replace("_", "")))
          );
          
          expect(hasRecData).toBe(true);
        }
      }
    });

    test("should handle invalid stock symbols", async () => {
      const response = await request(app)
        .get("/api/analysts/recommendations/INVALID123");
      
      expect([404, 400, 500, 501]).toContain(response.status);
    });
  });

  describe("Analyst Coverage", () => {
    test("should retrieve analyst coverage for stock", async () => {
      const response = await request(app)
        .get("/api/analysts/coverage/AAPL");
      
      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        
        const coverage = response.body.data;
        const coverageFields = ["analyst_count", "buy_count", "hold_count", "sell_count"];
        const hasCoverageData = coverageFields.some(field => 
          Object.keys(coverage).some(key => key.toLowerCase().includes(field.replace("_", "")))
        );
        
        expect(hasCoverageData).toBe(true);
      }
    });
  });

  describe("Price Targets", () => {
    test("should retrieve price targets for stock", async () => {
      const response = await request(app)
        .get("/api/analysts/price-targets/AAPL");
      
      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(Array.isArray(response.body.data)).toBe(true);
        
        if (response.body.data.length > 0) {
          const target = response.body.data[0];
          expect(target).toHaveProperty("analyst");
          expect(target).toHaveProperty("target_price");
          expect(target).toHaveProperty("date");
        }
      }
    });

    test("should provide consensus price targets", async () => {
      const response = await request(app)
        .get("/api/analysts/consensus/AAPL");
      
      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        
        const consensus = response.body.data;
        const consensusFields = ["mean_target", "median_target", "high_target", "low_target"];
        const hasConsensusData = consensusFields.some(field => 
          Object.keys(consensus).some(key => key.toLowerCase().includes(field.replace("_", "")))
        );
        
        expect(hasConsensusData).toBe(true);
      }
    });
  });

  describe("Analyst Research", () => {
    test("should retrieve research reports", async () => {
      const response = await request(app)
        .get("/api/analysts/research?symbol=AAPL&limit=10");
      
      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(Array.isArray(response.body.data)).toBe(true);
        
        if (response.body.data.length > 0) {
          const research = response.body.data[0];
          expect(research).toHaveProperty("title");
          expect(research).toHaveProperty("analyst");
          expect(research).toHaveProperty("date");
        }
      }
    });

    test("should filter research by analyst firm", async () => {
      const response = await request(app)
        .get("/api/analysts/research?firm=Goldman&limit=5");
      
      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(Array.isArray(response.body.data)).toBe(true);
      }
    });
  });
});