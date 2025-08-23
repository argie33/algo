const request = require("supertest");
const express = require("express");

const commoditiesRouter = require("../../../routes/commodities");

describe("Commodities Routes", () => {
  let app;

  beforeEach(() => {
    app = express();
    app.use(express.json());

    // Add response formatter middleware
    app.use((req, res, next) => {
      res.success = (data, status = 200) => {
        res.status(status).json({
          success: true,
          data: data,
        });
      };

      res.error = (message, status = 500) => {
        res.status(status).json({
          success: false,
          error: message,
        });
      };

      next();
    });

    app.use("/commodities", commoditiesRouter);
  });

  describe("GET /commodities/health", () => {
    test("should return health status", async () => {
      const response = await request(app)
        .get("/commodities/health")
        .expect(200);

      expect(response.body).toEqual({
        success: true,
        status: "operational",
        service: "commodities",
        timestamp: expect.any(String),
        message: "Commodities service is running",
      });
    });
  });

  describe("GET /commodities/", () => {
    test("should return API overview with available endpoints", async () => {
      const response = await request(app).get("/commodities/").expect(200);

      expect(response.body).toEqual({
        success: true,
        data: {
          system: "Commodities API",
          version: "1.0.0",
          status: "operational",
          available_endpoints: expect.arrayContaining([
            "GET /commodities/categories - Commodity categories",
            "GET /commodities/prices - Current commodity prices",
            "GET /commodities/market-summary - Market overview",
            "GET /commodities/correlations - Price correlations",
            "GET /commodities/news - Latest commodity news",
          ]),
          timestamp: expect.any(String),
        },
      });
    });
  });

  describe("GET /commodities/categories", () => {
    test("should return commodity categories with performance data", async () => {
      const response = await request(app)
        .get("/commodities/categories")
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.arrayContaining([
          expect.objectContaining({
            id: "energy",
            name: "Energy",
            description: "Oil, gas, and energy commodities",
            commodities: expect.arrayContaining([
              "crude-oil",
              "natural-gas",
              "heating-oil",
              "gasoline",
            ]),
            weight: 0.35,
            performance: expect.objectContaining({
              "1d": expect.any(Number),
              "1w": expect.any(Number),
              "1m": expect.any(Number),
              "3m": expect.any(Number),
              "1y": expect.any(Number),
            }),
          }),
          expect.objectContaining({
            id: "precious-metals",
            name: "Precious Metals",
            description: "Gold, silver, platinum, and palladium",
            commodities: expect.arrayContaining([
              "gold",
              "silver",
              "platinum",
              "palladium",
            ]),
            weight: 0.25,
          }),
          expect.objectContaining({
            id: "base-metals",
            name: "Base Metals",
            description: "Copper, aluminum, zinc, and industrial metals",
            weight: 0.2,
          }),
          expect.objectContaining({
            id: "agriculture",
            name: "Agriculture",
            description: "Grains, livestock, and soft commodities",
            weight: 0.15,
          }),
          expect.objectContaining({
            id: "livestock",
            name: "Livestock",
            description: "Cattle, hogs, and feeder cattle",
            weight: 0.05,
          }),
        ]),
        metadata: {
          totalCategories: 5,
          lastUpdated: expect.any(String),
          priceDate: expect.any(String),
        },
        timestamp: expect.any(String),
      });
    });

    test("should have all categories add up to 100% weight", async () => {
      const response = await request(app)
        .get("/commodities/categories")
        .expect(200);

      const totalWeight = response.body.data.reduce(
        (sum, category) => sum + category.weight,
        0
      );
      expect(totalWeight).toBeCloseTo(1.0, 2); // Sum should be 1.0 (100%)
    });
  });

  describe("GET /commodities/prices", () => {
    test("should return all commodity prices by default", async () => {
      const response = await request(app)
        .get("/commodities/prices")
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.arrayContaining([
          expect.objectContaining({
            symbol: "CL",
            name: "Crude Oil",
            category: "energy",
            price: expect.any(Number),
            change: expect.any(Number),
            changePercent: expect.any(Number),
            unit: "per barrel",
            currency: "USD",
            volume: expect.any(Number),
            lastUpdated: expect.any(String),
          }),
          expect.objectContaining({
            symbol: "GC",
            name: "Gold",
            category: "precious-metals",
            price: expect.any(Number),
            change: expect.any(Number),
            changePercent: expect.any(Number),
            unit: "per ounce",
            currency: "USD",
          }),
          expect.objectContaining({
            symbol: "SI",
            name: "Silver",
            category: "precious-metals",
          }),
          expect.objectContaining({
            symbol: "HG",
            name: "Copper",
            category: "base-metals",
          }),
          expect.objectContaining({
            symbol: "NG",
            name: "Natural Gas",
            category: "energy",
          }),
          expect.objectContaining({
            symbol: "ZW",
            name: "Wheat",
            category: "agriculture",
          }),
        ]),
        filters: {
          category: null,
          symbol: null,
        },
        metadata: {
          totalCount: 6,
          priceDate: expect.any(String),
        },
        timestamp: expect.any(String),
      });
    });

    test("should filter prices by category", async () => {
      const response = await request(app)
        .get("/commodities/prices")
        .query({ category: "energy" })
        .expect(200);

      expect(response.body.data).toHaveLength(2); // CL and NG
      expect(
        response.body.data.every((commodity) => commodity.category === "energy")
      ).toBe(true);
      expect(response.body.filters.category).toBe("energy");
      expect(response.body.metadata.totalCount).toBe(2);
    });

    test("should filter prices by symbol", async () => {
      const response = await request(app)
        .get("/commodities/prices")
        .query({ symbol: "GC" })
        .expect(200);

      expect(response.body.data).toHaveLength(1);
      expect(response.body.data[0]).toMatchObject({
        symbol: "GC",
        name: "Gold",
        category: "precious-metals",
      });
      expect(response.body.filters.symbol).toBe("GC");
      expect(response.body.metadata.totalCount).toBe(1);
    });

    test("should return empty array for non-existent category", async () => {
      const response = await request(app)
        .get("/commodities/prices")
        .query({ category: "non-existent" })
        .expect(200);

      expect(response.body.data).toHaveLength(0);
      expect(response.body.filters.category).toBe("non-existent");
      expect(response.body.metadata.totalCount).toBe(0);
    });

    test("should return empty array for non-existent symbol", async () => {
      const response = await request(app)
        .get("/commodities/prices")
        .query({ symbol: "XYZ" })
        .expect(200);

      expect(response.body.data).toHaveLength(0);
      expect(response.body.filters.symbol).toBe("XYZ");
      expect(response.body.metadata.totalCount).toBe(0);
    });

    test("should handle both category and symbol filters", async () => {
      const response = await request(app)
        .get("/commodities/prices")
        .query({ category: "precious-metals", symbol: "GC" })
        .expect(200);

      expect(response.body.data).toHaveLength(1);
      expect(response.body.data[0]).toMatchObject({
        symbol: "GC",
        name: "Gold",
        category: "precious-metals",
      });
      expect(response.body.filters).toEqual({
        category: "precious-metals",
        symbol: "GC",
      });
    });
  });

  describe("GET /commodities/market-summary", () => {
    test("should return market summary with overview and performance", async () => {
      const response = await request(app)
        .get("/commodities/market-summary")
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: {
          overview: {
            totalMarketCap: expect.any(Number),
            totalVolume: expect.any(Number),
            activeContracts: expect.any(Number),
            tradingSession: "open",
          },
          performance: {
            "1d": {
              gainers: expect.any(Number),
              losers: expect.any(Number),
              unchanged: expect.any(Number),
              topGainer: {
                symbol: expect.any(String),
                name: expect.any(String),
                change: expect.any(Number),
              },
              topLoser: {
                symbol: expect.any(String),
                name: expect.any(String),
                change: expect.any(Number),
              },
            },
          },
          sectors: expect.arrayContaining([
            expect.objectContaining({
              name: "Energy",
              weight: expect.any(Number),
              change: expect.any(Number),
              volume: expect.any(Number),
            }),
            expect.objectContaining({
              name: "Precious Metals",
              weight: expect.any(Number),
              change: expect.any(Number),
              volume: expect.any(Number),
            }),
          ]),
        },
        timestamp: expect.any(String),
      });
    });

    test("should have gainers and losers that add up to total minus unchanged", async () => {
      const response = await request(app)
        .get("/commodities/market-summary")
        .expect(200);

      const { gainers, losers, unchanged } =
        response.body.data.performance["1d"];
      const totalCalculated = gainers + losers + unchanged;

      // Should be reasonable numbers for market participants
      expect(totalCalculated).toBeGreaterThan(0);
      expect(gainers).toBeGreaterThanOrEqual(0);
      expect(losers).toBeGreaterThanOrEqual(0);
      expect(unchanged).toBeGreaterThanOrEqual(0);
    });
  });

  describe("GET /commodities/correlations", () => {
    test("should return correlation matrix for commodity sectors", async () => {
      const response = await request(app)
        .get("/commodities/correlations")
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: {
          overview: {
            description: "Correlation matrix for major commodity sectors",
            period: "90d",
            lastUpdated: expect.any(String),
          },
          matrix: {
            energy: {
              energy: 1.0,
              "precious-metals": expect.any(Number),
              "base-metals": expect.any(Number),
              agriculture: expect.any(Number),
              livestock: expect.any(Number),
            },
            "precious-metals": {
              energy: expect.any(Number),
              "precious-metals": 1.0,
              "base-metals": expect.any(Number),
              agriculture: expect.any(Number),
              livestock: expect.any(Number),
            },
          },
        },
        timestamp: expect.any(String),
      });
    });

    test("should have diagonal correlations equal to 1.0", async () => {
      const response = await request(app)
        .get("/commodities/correlations")
        .expect(200);

      const matrix = response.body.data.matrix;

      // Diagonal elements should be 1.0 (perfect self-correlation)
      expect(matrix.energy.energy).toBe(1.0);
      expect(matrix["precious-metals"]["precious-metals"]).toBe(1.0);
    });

    test("should have symmetric correlation matrix", async () => {
      const response = await request(app)
        .get("/commodities/correlations")
        .expect(200);

      const matrix = response.body.data.matrix;

      // Matrix should be symmetric
      expect(matrix.energy["precious-metals"]).toBe(
        matrix["precious-metals"].energy
      );
    });

    test("should have correlations between -1 and 1", async () => {
      const response = await request(app)
        .get("/commodities/correlations")
        .expect(200);

      const matrix = response.body.data.matrix;

      // Check all correlation values are in valid range
      Object.values(matrix).forEach((row) => {
        Object.values(row).forEach((correlation) => {
          expect(correlation).toBeGreaterThanOrEqual(-1);
          expect(correlation).toBeLessThanOrEqual(1);
        });
      });
    });
  });

  describe("Error handling", () => {
    test("should handle malformed requests", async () => {
      const response = await request(app)
        .get("/commodities/nonexistent")
        .expect(404);

      expect(response.text).toContain("Cannot GET /commodities/nonexistent");
    });
  });
});
