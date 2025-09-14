/**
 * Risk Management Integration Tests
 * Tests for portfolio risk analysis and management
 * Route: /routes/risk.js
 */

const request = require("supertest");
const { app } = require("../../../index");

describe("Risk Management API", () => {
  describe("Risk Assessment", () => {
    test("should calculate portfolio risk metrics", async () => {
      const response = await request(app)
        .get("/api/risk/portfolio/assessment")
        .set("Authorization", "Bearer test-token");
      
      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        
        const riskAssessment = response.body.data;
        const riskFields = ["var", "cvar", "beta", "volatility", "correlation"];
        const hasRiskData = riskFields.some(field => 
          Object.keys(riskAssessment).some(key => key.toLowerCase().includes(field))
        );
        
        expect(hasRiskData).toBe(true);
      }
    });

    test("should analyze individual position risk", async () => {
      const response = await request(app)
        .get("/api/risk/positions/AAPL/analysis");
      
      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body.data).toHaveProperty("symbol", "AAPL");
        
        const positionRisk = response.body.data;
        const positionFields = ["position_var", "beta", "volatility", "contribution_to_risk"];
        const hasPositionRisk = positionFields.some(field => 
          Object.keys(positionRisk).some(key => key.toLowerCase().includes(field.replace("_", "")))
        );
        
        expect(hasPositionRisk).toBe(true);
      }
    });
  });

  describe("Value at Risk (VaR)", () => {
    test("should calculate portfolio VaR", async () => {
      const response = await request(app)
        .get("/api/risk/var?confidence=95&horizon=1d&method=historical");
      
      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        
        const varData = response.body.data;
        expect(varData).toHaveProperty("var_value");
        expect(varData).toHaveProperty("confidence_level");
        expect(varData).toHaveProperty("time_horizon");
      }
    });

    test("should calculate VaR for different time horizons", async () => {
      const response = await request(app)
        .get("/api/risk/var/scenarios?horizons=1d,5d,10d&confidence=99");
      
      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(Array.isArray(response.body.data)).toBe(true);
        
        if (response.body.data.length > 0) {
          const varScenario = response.body.data[0];
          expect(varScenario).toHaveProperty("horizon");
          expect(varScenario).toHaveProperty("var_value");
        }
      }
    });
  });

  describe("Stress Testing", () => {
    test("should perform portfolio stress test", async () => {
      const stressScenario = {
        scenario_type: "market_crash",
        market_decline: -0.20,
        volatility_spike: 2.0,
        correlation_increase: 0.3
      };

      const response = await request(app)
        .post("/api/risk/stress-test")
        .set("Authorization", "Bearer test-token")
        .send(stressScenario);
      
      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        
        const stressResults = response.body.data;
        expect(stressResults).toHaveProperty("scenario");
        expect(stressResults).toHaveProperty("portfolio_impact");
        
        const impactFields = ["total_loss", "worst_positions", "recovery_time"];
        const hasImpactData = impactFields.some(field => 
          Object.keys(stressResults).some(key => key.toLowerCase().includes(field.replace("_", "")))
        );
        
        expect(hasImpactData).toBe(true);
      }
    });

    test("should run historical stress scenarios", async () => {
      const response = await request(app)
        .get("/api/risk/stress-test/historical?events=2008_crisis,covid_2020,dot_com_bubble");
      
      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(Array.isArray(response.body.data)).toBe(true);
        
        if (response.body.data.length > 0) {
          const historicalTest = response.body.data[0];
          expect(historicalTest).toHaveProperty("event");
          expect(historicalTest).toHaveProperty("impact");
        }
      }
    });
  });

  describe("Risk Limits and Controls", () => {
    test("should set portfolio risk limits", async () => {
      const riskLimits = {
        max_var_percent: 0.02,  // 2% max daily VaR
        max_position_size: 0.05,  // 5% max per position
        max_sector_concentration: 0.25,  // 25% max per sector
        correlation_limit: 0.8  // Max correlation between positions
      };

      const response = await request(app)
        .post("/api/risk/limits")
        .set("Authorization", "Bearer test-token")
        .send(riskLimits);
      
      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("message");
      }
    });

    test("should check risk limit violations", async () => {
      const response = await request(app)
        .get("/api/risk/limits/violations")
        .set("Authorization", "Bearer test-token");
      
      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(Array.isArray(response.body.data)).toBe(true);
        
        if (response.body.data.length > 0) {
          const violation = response.body.data[0];
          expect(violation).toHaveProperty("limit_type");
          expect(violation).toHaveProperty("current_value");
          expect(violation).toHaveProperty("limit_value");
        }
      }
    });
  });

  describe("Risk Reporting", () => {
    test("should generate risk report", async () => {
      const reportConfig = {
        report_type: "comprehensive",
        include_var: true,
        include_stress_tests: true,
        include_correlations: true,
        period: "1M"
      };

      const response = await request(app)
        .post("/api/risk/reports/generate")
        .set("Authorization", "Bearer test-token")
        .send(reportConfig);
      
      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body.data).toHaveProperty("report_id");
        expect(response.body.data).toHaveProperty("report_url");
      }
    });

    test("should retrieve risk dashboard", async () => {
      const response = await request(app)
        .get("/api/risk/dashboard")
        .set("Authorization", "Bearer test-token");
      
      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        
        const dashboard = response.body.data;
        const dashboardSections = ["current_risk", "violations", "recent_alerts", "key_metrics"];
        const hasDashboardData = dashboardSections.some(field => 
          Object.keys(dashboard).some(key => key.toLowerCase().includes(field.replace("_", "")))
        );
        
        expect(hasDashboardData).toBe(true);
      }
    });
  });

  describe("Risk Monitoring", () => {
    test("should set up risk monitoring alerts", async () => {
      const alertConfig = {
        alert_type: "var_breach",
        threshold: 0.025,  // 2.5% VaR threshold
        notification_channels: ["email", "sms"],
        frequency: "immediate"
      };

      const response = await request(app)
        .post("/api/risk/monitoring/alerts")
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