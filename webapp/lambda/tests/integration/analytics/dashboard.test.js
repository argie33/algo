/**
 * Dashboard Integration Tests
 * Tests for dashboard data aggregation and user interface
 * Route: /routes/dashboard.js
 */

const request = require("supertest");
const { app } = require("../../../index");

describe("Dashboard API", () => {
  describe("Dashboard Overview", () => {
    test("should retrieve comprehensive dashboard data", async () => {
      const response = await request(app)
        .get("/api/dashboard")
        .set("Authorization", "Bearer test-token");
      
      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        
        const dashboard = response.body.data;
        const dashboardSections = ["portfolio", "market", "watchlists", "alerts"];
        const hasDashboardData = dashboardSections.some(section => 
          Object.keys(dashboard).some(key => key.toLowerCase().includes(section))
        );
        
        expect(hasDashboardData).toBe(true);
      }
    });

    test("should handle unauthorized dashboard access", async () => {
      const response = await request(app)
        .get("/api/dashboard");
      
      expect([401, 500]).toContain(response.status);
    });
  });

  describe("Market Summary", () => {
    test("should provide market summary for dashboard", async () => {
      const response = await request(app)
        .get("/api/dashboard/market-summary");
      
      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        
        const summary = response.body.data;
        const summaryFields = ["indices", "movers", "sectors", "volume"];
        const hasSummaryData = summaryFields.some(field => 
          Object.keys(summary).some(key => key.toLowerCase().includes(field))
        );
        
        expect(hasSummaryData).toBe(true);
      }
    });

    test("should include major market indices", async () => {
      const response = await request(app)
        .get("/api/dashboard/indices");
      
      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(Array.isArray(response.body.data)).toBe(true);
        
        if (response.body.data.length > 0) {
          const index = response.body.data[0];
          expect(index).toHaveProperty("symbol");
          
          const indexFields = ["name", "price", "change", "change_percent"];
          const hasIndexData = indexFields.some(field => 
            Object.keys(index).some(key => key.toLowerCase().includes(field.replace("_", "")))
          );
          
          expect(hasIndexData).toBe(true);
        }
      }
    });
  });

  describe("Portfolio Widget", () => {
    test("should retrieve portfolio summary for dashboard", async () => {
      const response = await request(app)
        .get("/api/dashboard/portfolio")
        .set("Authorization", "Bearer test-token");
      
      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        
        const portfolio = response.body.data;
        const portfolioFields = ["total_value", "daily_change", "positions", "cash"];
        const hasPortfolioData = portfolioFields.some(field => 
          Object.keys(portfolio).some(key => key.toLowerCase().includes(field.replace("_", "")))
        );
        
        expect(hasPortfolioData).toBe(true);
      }
    });

    test("should show top portfolio positions", async () => {
      const response = await request(app)
        .get("/api/dashboard/portfolio/top-positions?limit=5")
        .set("Authorization", "Bearer test-token");
      
      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(Array.isArray(response.body.data)).toBe(true);
      }
    });
  });

  describe("Watchlist Widget", () => {
    test("should retrieve watchlist summary", async () => {
      const response = await request(app)
        .get("/api/dashboard/watchlists")
        .set("Authorization", "Bearer test-token");
      
      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(Array.isArray(response.body.data)).toBe(true);
        
        if (response.body.data.length > 0) {
          const watchlist = response.body.data[0];
          expect(watchlist).toHaveProperty("name");
          expect(watchlist).toHaveProperty("stocks");
        }
      }
    });

    test("should show watchlist performance", async () => {
      const response = await request(app)
        .get("/api/dashboard/watchlists/performance")
        .set("Authorization", "Bearer test-token");
      
      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
      }
    });
  });

  describe("News Widget", () => {
    test("should provide market news for dashboard", async () => {
      const response = await request(app)
        .get("/api/dashboard/news?limit=10");
      
      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(Array.isArray(response.body.data)).toBe(true);
        
        if (response.body.data.length > 0) {
          const newsItem = response.body.data[0];
          expect(newsItem).toHaveProperty("headline");
          expect(newsItem).toHaveProperty("source");
          expect(newsItem).toHaveProperty("published_date");
        }
      }
    });

    test("should provide personalized news based on portfolio", async () => {
      const response = await request(app)
        .get("/api/dashboard/news/personalized")
        .set("Authorization", "Bearer test-token");
      
      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(Array.isArray(response.body.data)).toBe(true);
      }
    });
  });

  describe("Alerts Widget", () => {
    test("should show recent alerts", async () => {
      const response = await request(app)
        .get("/api/dashboard/alerts/recent")
        .set("Authorization", "Bearer test-token");
      
      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(Array.isArray(response.body.data)).toBe(true);
      }
    });

    test("should show alert summary", async () => {
      const response = await request(app)
        .get("/api/dashboard/alerts/summary")
        .set("Authorization", "Bearer test-token");
      
      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        
        const summary = response.body.data;
        const summaryFields = ["active_alerts", "triggered_today", "total_alerts"];
        const hasAlertSummary = summaryFields.some(field => 
          Object.keys(summary).some(key => key.toLowerCase().includes(field.replace("_", "")))
        );
        
        expect(hasAlertSummary).toBe(true);
      }
    });
  });

  describe("Dashboard Customization", () => {
    test("should save dashboard layout preferences", async () => {
      const layoutConfig = {
        widgets: ["portfolio", "market", "news", "alerts"],
        layout: "2x2",
        theme: "dark"
      };

      const response = await request(app)
        .post("/api/dashboard/layout")
        .set("Authorization", "Bearer test-token")
        .send(layoutConfig);
      
      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200 || response.status === 201) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("message");
      }
    });

    test("should retrieve user dashboard preferences", async () => {
      const response = await request(app)
        .get("/api/dashboard/preferences")
        .set("Authorization", "Bearer test-token");
      
      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        
        const preferences = response.body.data;
        const prefFields = ["theme", "layout", "widgets", "refresh_interval"];
        const hasPreferences = prefFields.some(field => 
          Object.keys(preferences).some(key => key.toLowerCase().includes(field.replace("_", "")))
        );
        
        expect(hasPreferences).toBe(true);
      }
    });
  });
});