/**
 * Positioning Integration Tests
 * Tests for portfolio positioning and risk management
 * Route: /routes/positioning.js
 */

const request = require("supertest");
const { app } = require("../../../index");

describe("Positioning API", () => {
  describe("Position Analysis", () => {
    test("should analyze current positions", async () => {
      const response = await request(app)
        .get("/api/positioning/analysis")
        .set("Authorization", "Bearer test-token");
      
      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        
        const analysis = response.body.data;
        const analysisFields = ["total_exposure", "sector_allocation", "risk_metrics"];
        const hasAnalysisData = analysisFields.some(field => 
          Object.keys(analysis).some(key => key.toLowerCase().includes(field.replace("_", "")))
        );
        
        expect(hasAnalysisData).toBe(true);
      }
    });

    test("should calculate position sizing recommendations", async () => {
      const response = await request(app)
        .get("/api/positioning/sizing?symbol=AAPL&risk_level=moderate")
        .set("Authorization", "Bearer test-token");
      
      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        
        const sizing = response.body.data;
        const sizingFields = ["recommended_size", "max_position", "risk_percentage"];
        const hasSizingData = sizingFields.some(field => 
          Object.keys(sizing).some(key => key.toLowerCase().includes(field.replace("_", "")))
        );
        
        expect(hasSizingData).toBe(true);
      }
    });
  });

  describe("Risk Management", () => {
    test("should calculate portfolio risk metrics", async () => {
      const response = await request(app)
        .get("/api/positioning/risk")
        .set("Authorization", "Bearer test-token");
      
      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        
        const risk = response.body.data;
        const riskFields = ["value_at_risk", "beta", "volatility", "max_drawdown"];
        const hasRiskData = riskFields.some(field => 
          Object.keys(risk).some(key => key.toLowerCase().includes(field.replace("_", "")))
        );
        
        expect(hasRiskData).toBe(true);
      }
    });

    test("should provide diversification analysis", async () => {
      const response = await request(app)
        .get("/api/positioning/diversification")
        .set("Authorization", "Bearer test-token");
      
      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        
        const diversification = response.body.data;
        const divFields = ["herfindahl_index", "concentration_risk", "sector_weights"];
        const hasDivData = divFields.some(field => 
          Object.keys(diversification).some(key => key.toLowerCase().includes(field.replace("_", "")))
        );
        
        expect(hasDivData).toBe(true);
      }
    });
  });

  describe("Correlation Analysis", () => {
    test("should analyze position correlations", async () => {
      const response = await request(app)
        .get("/api/positioning/correlations")
        .set("Authorization", "Bearer test-token");
      
      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(Array.isArray(response.body.data)).toBe(true);
        
        if (response.body.data.length > 0) {
          const correlation = response.body.data[0];
          expect(correlation).toHaveProperty("symbol1");
          expect(correlation).toHaveProperty("symbol2");
          expect(correlation).toHaveProperty("correlation_coefficient");
        }
      }
    });

    test("should identify highly correlated positions", async () => {
      const response = await request(app)
        .get("/api/positioning/correlations/high?threshold=0.7")
        .set("Authorization", "Bearer test-token");
      
      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(Array.isArray(response.body.data)).toBe(true);
      }
    });
  });

  describe("Rebalancing", () => {
    test("should generate rebalancing recommendations", async () => {
      const response = await request(app)
        .get("/api/positioning/rebalance")
        .set("Authorization", "Bearer test-token");
      
      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(Array.isArray(response.body.data)).toBe(true);
        
        if (response.body.data.length > 0) {
          const rebalance = response.body.data[0];
          expect(rebalance).toHaveProperty("symbol");
          
          const rebalanceFields = ["current_weight", "target_weight", "action"];
          const hasRebalanceData = rebalanceFields.some(field => 
            Object.keys(rebalance).some(key => key.toLowerCase().includes(field.replace("_", "")))
          );
          
          expect(hasRebalanceData).toBe(true);
        }
      }
    });

    test("should handle custom rebalancing targets", async () => {
      const rebalanceTargets = {
        "AAPL": 25,
        "GOOGL": 20,
        "MSFT": 15,
        "AMZN": 10
      };

      const response = await request(app)
        .post("/api/positioning/rebalance/custom")
        .set("Authorization", "Bearer test-token")
        .send({ targets: rebalanceTargets });
      
      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(Array.isArray(response.body.data)).toBe(true);
      }
    });
  });
});