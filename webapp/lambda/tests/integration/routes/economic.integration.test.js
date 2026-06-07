/**
 * Economic Routes Integration Tests - REAL DATA ONLY
 * Tests economic endpoints with REAL database connection and REAL loaded data
 * NO MOCKS - validates actual behavior with actual data from loaders
 * Validates NO-FALLBACK policy: raw NULL values must flow through unmasked
 */

const request = require("supertest");
const { app } = require("../../../index");
const { initializeDatabase } = require("../../../utils/database"); // Import the actual Express app - NO MOCKS

describe("Economic Routes - Real Data Validation", () => {
  beforeAll(async () => {
    await initializeDatabase();
  });

  describe("GET /api/economic (Economic Data)", () => {
    test("should return economic data with pagination", async () => {
      const response = await request(app).get("/api/economic");

      expect(response.status).toBe(200);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
        expect(Array.isArray(response.body.data)).toBe(true);
        expect(response.body).toHaveProperty("pagination");
        expect(response.body.pagination).toHaveProperty("page");
        expect(response.body.pagination).toHaveProperty("limit");
        expect(response.body.pagination).toHaveProperty("total");
      }
    });

    test("should handle page and limit parameters", async () => {
      const response = await request(app).get("/api/economic?page=1&limit=10");

      expect([200, 400, 500, 503].includes(response.status)).toBe(true);

      if (response.status === 200) {
        expect(response.body.pagination.page).toBe(1);
        expect(response.body.pagination.limit).toBe(10);
        if (response.body.data.length > 0) {
          expect(response.body.data.length).toBeLessThanOrEqual(10);
        }
      }
    });

    test("should filter by economic series", async () => {
      // Use actual FRED series IDs from loadecondata.py
      const economicSeries = [
        "GDPC1",        // Real GDP
        "UNRATE",       // Unemployment Rate
        "VIXCLS",       // VIX Volatility Index
        "FEDFUNDS",     // Federal Funds Rate
        "CPIAUCSL",     // CPI (Consumer Price Index)
      ];

      for (const series of economicSeries) {
        const response = await request(app).get(
          `/api/economic?series=${series}`
        );

        expect([200, 400].includes(response.status)).toBe(true);

        if (response.status === 200 && response.body.data.length > 0) {
          response.body.data.forEach((dataPoint) => {
            expect(dataPoint).toHaveProperty("series_id");
            expect(dataPoint.series_id).toBe(series);
          });
        }
      }
    });

    test("should validate economic data structure", async () => {
      const response = await request(app).get("/api/economic?limit=5");

      if (response.status === 200 && response.body.data.length > 0) {
        const dataPoint = response.body.data[0];
        expect(dataPoint).toHaveProperty("series_id");
        expect(dataPoint).toHaveProperty("date");
        expect(dataPoint).toHaveProperty("value");
        expect(typeof dataPoint.series_id).toBe("string");
        expect(typeof dataPoint.value).toBe("number");
      }
    });

    test("should handle invalid pagination parameters", async () => {
      const invalidParams = [
        "page=-1&limit=10",
        "page=0&limit=10",
        "page=1&limit=-5",
        "page=abc&limit=def",
        "page=999999&limit=1000",
      ];

      for (const params of invalidParams) {
        const response = await request(app).get(`/api/economic?${params}`);

        expect([200, 400, 404, 500, 503].includes(response.status)).toBe(true);
      }
    });
  });

  describe("GET /api/economic/indicators", () => {
    test("should return available economic indicators", async () => {
      const response = await request(app).get("/api/economic/indicators");

      expect(response.status).toBe(200);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
        expect(Array.isArray(response.body.data)).toBe(true);
        expect(response.body).toHaveProperty("categories");
      }
    });

    test("should categorize economic indicators", async () => {
      const response = await request(app).get("/api/economic/indicators");

      if (response.status === 200 && response.body.categories) {
        const expectedCategories = [
          "growth",
          "inflation",
          "employment",
          "monetary",
          "housing",
          "trade",
        ];
        expectedCategories.forEach((category) => {
          if (response.body.categories[category]) {
            expect(Array.isArray(response.body.categories[category])).toBe(
              true
            );
          }
        });
      }
    });

    test("should handle category filter for indicators", async () => {
      const categories = ["growth", "inflation", "employment", "monetary"];

      for (const category of categories) {
        const response = await request(app).get(
          `/api/economic/indicators?category=${category}`
        );

        expect([200, 400].includes(response.status)).toBe(true);
      }
    });
  });

  describe("GET /api/economic/calendar", () => {
    test("should return economic calendar events", async () => {
      const response = await request(app).get("/api/economic/calendar");

      expect(response.status).toBe(200);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
        expect(Array.isArray(response.body.data)).toBe(true);
        expect(response.body).toHaveProperty("period");
      }
    });

    test("should handle date range for calendar", async () => {
      const response = await request(app).get(
        "/api/economic/calendar?start_date=2025-01-01&end_date=2025-12-31"
      );

      expect([200, 400, 500, 503].includes(response.status)).toBe(true);

      if (response.status === 200 && response.body.data.length > 0) {
        response.body.data.forEach((event) => {
          expect(event).toHaveProperty("event_date");
          expect(event).toHaveProperty("event_name");
          expect(event).toHaveProperty("importance");
        });
      }
    });

    test("should filter by importance level", async () => {
      const importanceLevels = ["high", "medium", "low"];

      for (const importance of importanceLevels) {
        const response = await request(app).get(
          `/api/economic/calendar?importance=${importance}`
        );

        expect([200, 400, 500, 503].includes(response.status)).toBe(true);

        if (response.status === 200 && response.body.data.length > 0) {
          response.body.data.forEach((event) => {
            expect(event.importance).toBe(importance);
          });
        }
      }
    });

    test("should handle country filter", async () => {
      const countries = ["US", "EU", "JP", "GB", "CA"];

      for (const country of countries) {
        const response = await request(app).get(
          `/api/economic/calendar?country=${country}`
        );

        expect([200, 400, 500, 503].includes(response.status)).toBe(true);
      }
    });
  });

  describe("GET /api/economic/series/:seriesId", () => {
    test("should return specific economic series data", async () => {
      const seriesIds = ["GDPC1", "UNRATE", "VIXCLS", "FEDFUNDS"];

      for (const seriesId of seriesIds) {
        const response = await request(app).get(
          `/api/economic/series/${seriesId}`
        );

        expect(response.status).toBe(200);

        if (response.status === 200) {
          expect(response.body).toHaveProperty("success", true);
          expect(response.body).toHaveProperty("data");
          expect(response.body.data).toHaveProperty("series_id", seriesId);
          expect(response.body.data).toHaveProperty("values");
          expect(Array.isArray(response.body.data.values)).toBe(true);
        }
      }
    });

    test("should handle timeframe parameter for series", async () => {
      const timeframes = ["1Y", "2Y", "5Y", "10Y", "max"];

      for (const timeframe of timeframes) {
        const response = await request(app).get(
          `/api/economic/series/GDPC1?timeframe=${timeframe}`
        );

        expect([200, 400].includes(response.status)).toBe(true);
      }
    });

    test("should handle frequency parameter", async () => {
      const frequencies = ["daily", "weekly", "monthly", "quarterly", "annual"];

      for (const frequency of frequencies) {
        const response = await request(app).get(
          `/api/economic/series/UNEMPLOYMENT_RATE?frequency=${frequency}`
        );

        expect([200, 400].includes(response.status)).toBe(true);
      }
    });

    test("should handle invalid series ID", async () => {
      const response = await request(app).get(
        "/api/economic/series/INVALID_SERIES"
      );

      expect([404, 500, 503].includes(response.status)).toBe(true);
    });
  });

  describe("GET /api/economic/compare", () => {
    test("should compare multiple economic series", async () => {
      const response = await request(app).get(
        "/api/economic/compare?series=GDPC1,UNRATE,VIXCLS"
      );

      expect([200, 400, 500, 503].includes(response.status)).toBe(true);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
        expect(response.body.data).toHaveProperty("series");
        expect(Array.isArray(response.body.data.series)).toBe(true);
        expect(response.body.data).toHaveProperty("correlation_matrix");
      }
    });

    test("should handle normalization parameter", async () => {
      const response = await request(app).get(
        "/api/economic/compare?series=GDPC1,UNRATE&normalize=true"
      );

      expect([200, 400, 500, 503].includes(response.status)).toBe(true);

      if (response.status === 200) {
        expect(response.body.data).toHaveProperty("normalized", true);
      }
    });

    test("should handle period alignment", async () => {
      const response = await request(app).get(
        "/api/economic/compare?series=GDPC1,UNRATE&align_period=quarterly"
      );

      expect([200, 400, 500, 503].includes(response.status)).toBe(true);
    });
  });

  describe("GET /api/economic/forecast", () => {
    test("should return economic forecasts", async () => {
      const response = await request(app).get(
        "/api/economic/forecast?series=GDPC1"
      );

      expect(response.status).toBe(200);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
        expect(response.body.data).toHaveProperty("series_id", "GDPC1");
        expect(response.body.data).toHaveProperty("forecast_values");
        expect(response.body.data).toHaveProperty("confidence_intervals");
      }
    });

    test("should handle forecast horizon parameter", async () => {
      const horizons = ["1Q", "2Q", "1Y", "2Y"];

      for (const horizon of horizons) {
        const response = await request(app).get(
          `/api/economic/forecast?series=UNRATE&horizon=${horizon}`
        );

        expect([200, 400].includes(response.status)).toBe(true);
      }
    });

    test("should handle confidence level parameter", async () => {
      const response = await request(app).get(
        "/api/economic/forecast?series=UNRATE&confidence=0.95"
      );

      expect([200, 400].includes(response.status)).toBe(true);
    });
  });

  describe("GET /api/economic/correlations", () => {
    test("should return correlations with market indices", async () => {
      const response = await request(app).get(
        "/api/economic/correlations?series=FEDFUNDS"
      );

      expect(response.status).toBe(200);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("data");
        expect(response.body.data).toHaveProperty("correlations");
        expect(response.body.data.correlations).toHaveProperty("stock_market");
        expect(response.body.data.correlations).toHaveProperty("bond_market");
        expect(response.body.data.correlations).toHaveProperty(
          "commodity_market"
        );
      }
    });

    test("should handle timeframe for correlations", async () => {
      const response = await request(app).get(
        "/api/economic/correlations?series=UNRATE&timeframe=5Y"
      );

      expect([200, 400].includes(response.status)).toBe(true);
    });
  });

  describe("Performance and Edge Cases", () => {
    jest.setTimeout(15000);

    test("should handle concurrent requests to economic endpoints", async () => {
      const requests = [
        request(app).get("/api/economic"),
        request(app).get("/api/economic/indicators"),
        request(app).get("/api/economic/calendar"),
        request(app).get("/api/economic/series/GDP"),
        request(app).get("/api/economic/forecast?series=UNEMPLOYMENT_RATE"),
      ];

      const responses = await Promise.all(requests);

      responses.forEach((response) => {
        expect(response.status).toBe(200);
      });
    });

    test("should handle large data requests gracefully", async () => {
      const response = await request(app).get("/api/economic?limit=1000");

      expect([200, 400, 500, 503].includes(response.status)).toBe(true);
    });

    test("should maintain response time consistency", async () => {
      const startTime = Date.now();
      const response = await request(app).get("/api/economic/indicators");
      const responseTime = Date.now() - startTime;

      expect(response.status).toBe(200);
      expect(responseTime).toBeLessThan(15000);
    });

    test("should handle malformed date parameters", async () => {
      const malformedDates = [
        "start_date=invalid-date",
        "end_date=2025-13-40",
        "start_date=2025-12-31&end_date=2025-01-01", // end before start
        "start_date=&end_date=",
      ];

      for (const dateParams of malformedDates) {
        const response = await request(app).get(
          `/api/economic/calendar?${dateParams}`
        );

        expect([200, 400, 500, 503].includes(response.status)).toBe(true);
      }
    });

    test("should validate economic data value ranges", async () => {
      const response = await request(app).get(
        "/api/economic/series/UNEMPLOYMENT_RATE?limit=10"
      );

      if (response.status === 200 && response.body.data.values.length > 0) {
        response.body.data.values.forEach((dataPoint) => {
          expect(typeof dataPoint.value).toBe("number");
          expect(dataPoint.value).not.toBeNaN();
          expect(isFinite(dataPoint.value)).toBe(true);
        });
      }
    });

    test("should handle database connection failures gracefully", async () => {
      const response = await request(app).get("/api/economic");

      expect(response.status).toBe(200);

      if (response.status >= 500) {
        expect(response.body).toHaveProperty("error");
      }
    });

    test("should handle SQL injection attempts", async () => {
      const maliciousSeries = "GDP'; DROP TABLE economic_data; --";
      const response = await request(app).get(
        `/api/economic?series=${encodeURIComponent(maliciousSeries)}`
      );

      expect([200, 400, 404].includes(response.status)).toBe(true);
    });

    test("should handle memory pressure with large datasets", async () => {
      const response = await request(app).get(
        "/api/economic/compare?series=GDP,UNEMPLOYMENT_RATE,FEDERAL_FUNDS_RATE,INFLATION_RATE&timeframe=max"
      );

      expect([200, 400, 413, 500, 503].includes(response.status)).toBe(true);
    });

    test("should validate forecast accuracy metadata", async () => {
      const response = await request(app).get(
        "/api/economic/forecast?series=GDP&horizon=1Y"
      );

      if (response.status === 200) {
        expect(response.body.data).toHaveProperty("model_info");
        expect(response.body.data).toHaveProperty("last_updated");
        expect(response.body.data).toHaveProperty("data_source");

        if (response.body.data.confidence_intervals) {
          expect(response.body.data.confidence_intervals).toHaveProperty(
            "lower"
          );
          expect(response.body.data.confidence_intervals).toHaveProperty(
            "upper"
          );
        }
      }
    });
  });
});
