/**
 * Response Formatter Integration Tests - Fixed Version
 * Tests response formatting with correct API structure
 */

const responseFormatter = require("../../../utils/responseFormatter");

describe("Response Formatter Integration Tests - Fixed", () => {
  describe("Success Response Formatting", () => {
    test("should format successful API responses", () => {
      const testData = {
        symbol: "AAPL",
        price: 150.25,
        change: 2.5,
        changePercent: 1.68,
      };

      const formatted = responseFormatter.success(
        testData,
        200,
        { message: "Stock data retrieved successfully" }
      );

      expect(formatted).toBeDefined();
      expect(formatted.response.success).toBe(true);
      expect(formatted.response.data).toEqual(testData);
      expect(formatted.response.message).toBe("Stock data retrieved successfully");
      expect(formatted.response.timestamp).toBeDefined();
      expect(formatted.statusCode).toBe(200);
    });

    test("should handle array data in responses", () => {
      const testArray = [
        { symbol: "AAPL", price: 150.25 },
        { symbol: "GOOGL", price: 2800.5 },
        { symbol: "MSFT", price: 310.75 },
      ];

      const formatted = responseFormatter.success(
        testArray,
        200,
        { message: "Portfolio data retrieved", count: 3 }
      );

      expect(formatted.response.success).toBe(true);
      expect(Array.isArray(formatted.response.data)).toBe(true);
      expect(formatted.response.data.length).toBe(3);
      expect(formatted.response.count).toBe(3);
      expect(formatted.response.message).toBe("Portfolio data retrieved");
    });
  });

  describe("Error Response Formatting", () => {
    test("should format client errors (4xx)", () => {
      const formatted = responseFormatter.error(
        "Invalid symbol provided",
        400,
        { code: "INVALID_SYMBOL" }
      );

      expect(formatted.response.success).toBe(false);
      expect(formatted.response.error).toBe("Invalid symbol provided");
      expect(formatted.response.code).toBe("INVALID_SYMBOL");
      expect(formatted.response.timestamp).toBeDefined();
      expect(formatted.statusCode).toBe(400);
    });

    test("should format server errors (5xx)", () => {
      const formatted = responseFormatter.error(
        "Database connection failed",
        500,
        { code: "DATABASE_ERROR" }
      );

      expect(formatted.response.success).toBe(false);
      expect(formatted.response.error).toBe("Database connection failed");
      expect(formatted.response.code).toBe("DATABASE_ERROR");
      expect(formatted.statusCode).toBe(500);
    });
  });

  describe("Paginated Response Formatting", () => {
    test("should format paginated responses correctly", () => {
      const testData = Array.from({ length: 10 }, (_, i) => ({
        id: i,
        value: `item_${i}`,
      }));

      const paginationMeta = {
        page: 2,
        limit: 10,
        total: 50,
        totalPages: 5,
        hasNext: true,
        hasPrev: true,
      };

      const formatted = responseFormatter.paginated(testData, paginationMeta);

      expect(formatted.response.success).toBe(true);
      expect(formatted.response.data.items.length).toBe(10);
      expect(formatted.response.data.pagination.page).toBe(2);
      expect(formatted.response.data.pagination.hasNext).toBe(true);
      expect(formatted.response.data.pagination.hasPrev).toBe(true);
    });
  });

  describe("Validation Error Formatting", () => {
    test("should format validation errors", () => {
      const errors = [
        { field: "symbol", message: "Symbol is required" },
        { field: "quantity", message: "Quantity must be positive" }
      ];

      const formatted = responseFormatter.validationError(errors);

      expect(formatted.response.success).toBe(false);
      expect(formatted.response.error).toBe("Validation failed");
      expect(Array.isArray(formatted.response.errors)).toBe(true);
      expect(formatted.response.errors.length).toBe(2);
      expect(formatted.statusCode).toBe(422);
    });
  });
});