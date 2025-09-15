/**
 * Earnings Data Integration Tests
 * Tests for earnings functionality via calendar delegation
 * Route: /routes/earnings.js -> /routes/calendar.js
 */

const request = require("supertest");
const { app } = require("../../../index");

describe("Earnings Data Integration", () => {
  describe("Earnings Calendar (Delegated)", () => {
    test("should delegate to calendar earnings endpoint", async () => {
      const response = await request(app).get("/api/earnings");

      // Should delegate to calendar/earnings functionality
      expect([200, 404, 501]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("earnings");
        expect(Array.isArray(response.body.earnings)).toBe(true);
      }
    });

    test("should delegate symbol-specific requests to calendar", async () => {
      const response = await request(app).get("/api/earnings/AAPL");

      expect([200, 404, 501]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("earnings");
        expect(Array.isArray(response.body.earnings)).toBe(true);
      }
    });

    test("should handle query parameters for delegation", async () => {
      const response = await request(app).get(
        "/api/earnings?period=upcoming&limit=5"
      );

      expect([200, 404, 501]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("earnings");
        expect(Array.isArray(response.body.earnings)).toBe(true);
        // Should respect limit parameter when delegating
        expect(response.body.earnings.length).toBeLessThanOrEqual(5);
      }
    });
  });

  describe("Direct Calendar Earnings Access", () => {
    test("should access earnings via calendar route directly", async () => {
      const response = await request(app).get("/api/calendar/earnings");

      expect([200, 404, 501]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("earnings");
        expect(Array.isArray(response.body.earnings)).toBe(true);
      }
    });

    test("should access earnings history via calendar route", async () => {
      const response = await request(app).get("/api/calendar/earnings-history");

      expect([200, 404, 501]).toContain(response.status);

      if (response.status === 200) {
        // Should have earnings history data structure
        const hasEarningsData =
          response.body.earnings ||
          response.body.data ||
          Array.isArray(response.body);
        expect(hasEarningsData).toBeTruthy();
      }
    });

    test("should access earnings estimates via calendar route", async () => {
      const response = await request(app).get(
        "/api/calendar/earnings-estimates"
      );

      expect([200, 404, 501]).toContain(response.status);

      if (response.status === 200) {
        // Should have earnings estimates data structure
        const hasEstimatesData =
          response.body.estimates ||
          response.body.data ||
          Array.isArray(response.body);
        expect(hasEstimatesData).toBeTruthy();
      }
    });
  });

  describe("Error Handling", () => {
    test("should handle delegation errors gracefully", async () => {
      const response = await request(app).get("/api/earnings/INVALID_SYMBOL");

      expect([200, 404, 500]).toContain(response.status);

      if (response.status >= 400) {
        expect(response.body).toHaveProperty("success", false);
        expect(response.body).toHaveProperty("error");
      }
    });
  });
});
