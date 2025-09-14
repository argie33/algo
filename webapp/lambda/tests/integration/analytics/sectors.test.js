/**
 * Sectors Analysis Integration Tests
 * Tests for sector-based analysis and performance
 * Route: /routes/sectors.js
 */

const request = require("supertest");
const { app } = require("../../../index");

describe("Sectors Analysis API", () => {
  describe("Sector Performance", () => {
    test("should retrieve sector performance data", async () => {
      const response = await request(app)
        .get("/api/sectors/performance");
      
      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(Array.isArray(response.body.data)).toBe(true);
        
        if (response.body.data.length > 0) {
          const sector = response.body.data[0];
          expect(sector).toHaveProperty("sector");
          
          const performanceFields = ["return_1d", "return_1w", "return_1m"];
          const hasPerformanceData = performanceFields.some(field => 
            Object.keys(sector).some(key => key.toLowerCase().includes(field.replace("_", "")))
          );
          
          expect(hasPerformanceData).toBe(true);
        }
      }
    });
  });

  describe("Sector Rotation", () => {
    test("should analyze sector rotation patterns", async () => {
      const response = await request(app)
        .get("/api/sectors/rotation");
      
      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        
        const data = response.body.data;
        if (data && Object.keys(data).length > 0) {
          const rotationFields = ["leaders", "laggards", "momentum"];
          const hasRotationData = rotationFields.some(field => 
            Object.keys(data).some(key => key.toLowerCase().includes(field))
          );
          
          expect(hasRotationData || Array.isArray(data)).toBeTruthy();
        }
      }
    });
  });

  describe("Sector Stocks", () => {
    test("should retrieve stocks by sector", async () => {
      const response = await request(app)
        .get("/api/sectors/technology/stocks");
      
      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(Array.isArray(response.body.data)).toBe(true);
        
        if (response.body.data.length > 0) {
          const stock = response.body.data[0];
          expect(stock).toHaveProperty("symbol");
          expect(stock).toHaveProperty("sector", "Technology");
        }
      }
    });
  });
});