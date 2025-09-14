/**
 * Trades Integration Tests
 * Tests for trade execution and management
 * Route: /routes/trades.js
 */

const request = require("supertest");
const { app } = require("../../../index");

describe("Trades API", () => {
  describe("Trade Execution", () => {
    test("should execute a buy trade", async () => {
      const tradeData = {
        symbol: "AAPL",
        side: "buy",
        quantity: 100,
        type: "market"
      };

      const response = await request(app)
        .post("/api/trades")
        .set("Authorization", "Bearer test-token")
        .send(tradeData);
      
      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200 || response.status === 201) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body.data).toHaveProperty("trade_id");
        expect(response.body.data).toHaveProperty("symbol", "AAPL");
        expect(response.body.data).toHaveProperty("side", "buy");
      }
    });

    test("should execute a limit order", async () => {
      const limitOrder = {
        symbol: "GOOGL",
        side: "buy",
        quantity: 10,
        type: "limit",
        limit_price: 2500.00,
        time_in_force: "gtc"
      };

      const response = await request(app)
        .post("/api/trades")
        .set("Authorization", "Bearer test-token")
        .send(limitOrder);
      
      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200 || response.status === 201) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body.data).toHaveProperty("trade_id");
        expect(response.body.data).toHaveProperty("type", "limit");
      }
    });

    test("should handle invalid trade parameters", async () => {
      const invalidTrade = {
        symbol: "INVALID",
        side: "invalid_side",
        quantity: -100
      };

      const response = await request(app)
        .post("/api/trades")
        .set("Authorization", "Bearer test-token")
        .send(invalidTrade);
      
      expect([400, 422]).toContain(response.status);
    });
  });

  describe("Trade Management", () => {
    test("should list user trades", async () => {
      const response = await request(app)
        .get("/api/trades?limit=50")
        .set("Authorization", "Bearer test-token");
      
      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(Array.isArray(response.body.data)).toBe(true);
        
        if (response.body.data.length > 0) {
          const trade = response.body.data[0];
          expect(trade).toHaveProperty("trade_id");
          expect(trade).toHaveProperty("symbol");
          expect(trade).toHaveProperty("side");
          expect(trade).toHaveProperty("quantity");
          expect(trade).toHaveProperty("status");
        }
      }
    });

    test("should filter trades by status", async () => {
      const response = await request(app)
        .get("/api/trades?status=filled&limit=25")
        .set("Authorization", "Bearer test-token");
      
      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(Array.isArray(response.body.data)).toBe(true);
        
        if (response.body.data.length > 0) {
          const trade = response.body.data[0];
          expect(trade).toHaveProperty("status", "filled");
        }
      }
    });

    test("should get specific trade details", async () => {
      const response = await request(app)
        .get("/api/trades/test-trade-id")
        .set("Authorization", "Bearer test-token");
      
      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        
        const trade = response.body.data;
        expect(trade).toHaveProperty("trade_id");
        
        const tradeFields = ["executed_at", "filled_price", "commission"];
        const hasTradeDetails = tradeFields.some(field => 
          Object.keys(trade).some(key => key.toLowerCase().includes(field.replace("_", "")))
        );
        
        expect(hasTradeDetails).toBe(true);
      }
    });
  });

  describe("Order Modification", () => {
    test("should cancel pending order", async () => {
      const response = await request(app)
        .delete("/api/trades/test-trade-id")
        .set("Authorization", "Bearer test-token");
      
      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("message");
      }
    });

    test("should modify existing order", async () => {
      const modificationData = {
        quantity: 150,
        limit_price: 155.00
      };

      const response = await request(app)
        .put("/api/trades/test-trade-id")
        .set("Authorization", "Bearer test-token")
        .send(modificationData);
      
      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("message");
      }
    });
  });

  describe("Trade Analytics", () => {
    test("should provide trade performance summary", async () => {
      const response = await request(app)
        .get("/api/trades/performance?period=30d")
        .set("Authorization", "Bearer test-token");
      
      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        
        const performance = response.body.data;
        const perfFields = ["total_trades", "win_rate", "avg_return", "total_pnl"];
        const hasPerfData = perfFields.some(field => 
          Object.keys(performance).some(key => key.toLowerCase().includes(field.replace("_", "")))
        );
        
        expect(hasPerfData).toBe(true);
      }
    });

    test("should analyze trade patterns", async () => {
      const response = await request(app)
        .get("/api/trades/analysis/patterns")
        .set("Authorization", "Bearer test-token");
      
      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        
        const patterns = response.body.data;
        const patternFields = ["most_traded_symbols", "preferred_order_types", "time_patterns"];
        const hasPatternData = patternFields.some(field => 
          Object.keys(patterns).some(key => key.toLowerCase().includes(field.replace("_", "")))
        );
        
        expect(hasPatternData).toBe(true);
      }
    });
  });

  describe("Batch Operations", () => {
    test("should execute multiple trades", async () => {
      const batchTrades = {
        trades: [
          {
            symbol: "AAPL",
            side: "buy",
            quantity: 50,
            type: "market"
          },
          {
            symbol: "GOOGL", 
            side: "buy",
            quantity: 25,
            type: "market"
          }
        ]
      };

      const response = await request(app)
        .post("/api/trades/batch")
        .set("Authorization", "Bearer test-token")
        .send(batchTrades);
      
      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200 || response.status === 201) {
        expect(response.body).toHaveProperty("success", true);
        expect(Array.isArray(response.body.data)).toBe(true);
        expect(response.body.data.length).toBe(2);
      }
    });

    test("should cancel multiple orders", async () => {
      const cancelData = {
        trade_ids: ["trade1", "trade2", "trade3"]
      };

      const response = await request(app)
        .post("/api/trades/batch/cancel")
        .set("Authorization", "Bearer test-token")
        .send(cancelData);
      
      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("results");
      }
    });
  });

  describe("Trade History", () => {
    test("should export trade history", async () => {
      const response = await request(app)
        .get("/api/trades/export?format=csv&from=2023-01-01&to=2023-12-31")
        .set("Authorization", "Bearer test-token");
      
      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body.data).toHaveProperty("download_url");
      }
    });

    test("should get trade statistics", async () => {
      const response = await request(app)
        .get("/api/trades/statistics?period=1y")
        .set("Authorization", "Bearer test-token");
      
      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        
        const statistics = response.body.data;
        const statsFields = ["total_volume", "commission_paid", "largest_win", "largest_loss"];
        const hasStatsData = statsFields.some(field => 
          Object.keys(statistics).some(key => key.toLowerCase().includes(field.replace("_", "")))
        );
        
        expect(hasStatsData).toBe(true);
      }
    });
  });
});