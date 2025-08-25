const schemaValidator = require("../../utils/schemaValidator");

// Mock dependencies
jest.mock("../../utils/database");
jest.mock("../../utils/logger");

const { query } = require("../../utils/database");
const logger = require("../../utils/logger");

describe("schemaValidator", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    logger.error = jest.fn();
    logger.warn = jest.fn();
    logger.info = jest.fn();
  });

  describe("validateData", () => {
    test("should validate valid stock data", () => {
      const data = {
        symbol: "AAPL",
        name: "Apple Inc.",
        sector: "Technology",
        market_cap: 2500000000000,
        price: 150.25,
        volume: 50000000,
      };

      const result = schemaValidator.validateData("stocks", data);

      expect(result.isValid).toBe(true);
      expect(result.errors).toEqual([]);
    });

    test("should validate required fields", () => {
      const data = {
        name: "Apple Inc.",
        // Missing required 'symbol' field
      };

      const result = schemaValidator.validateData("stocks", data);

      expect(result.isValid).toBe(false);
      expect(result.errors).toContain('Required field "symbol" is missing');
    });

    test("should validate string length constraints", () => {
      const data = {
        symbol: "VERYLONGSYMBOL", // Exceeds maxLength of 10
        name: "Apple Inc.",
      };

      const result = schemaValidator.validateData("stocks", data);

      expect(result.isValid).toBe(false);
      expect(result.errors).toContain(
        'Field "symbol" exceeds maximum length of 10 characters'
      );
    });

    test("should validate numeric constraints", () => {
      const data = {
        symbol: "AAPL",
        name: "Apple Inc.",
        market_cap: -1000000, // Negative value not allowed (min: 0)
      };

      const result = schemaValidator.validateData("stocks", data);

      expect(result.isValid).toBe(false);
      expect(result.errors).toContain('Field "market_cap" must be at least 0');
    });

    test("should validate decimal precision", () => {
      const data = {
        symbol: "AAPL",
        name: "Apple Inc.",
        price: 150.123456, // Exceeds precision of 10,2
      };

      const result = schemaValidator.validateData("stocks", data);

      expect(result.isValid).toBe(false);
      expect(result.errors).toContain(
        'Field "price" exceeds precision constraints (10,2)'
      );
    });

    test("should validate boolean fields", () => {
      const data = {
        symbol: "AAPL",
        name: "Apple Inc.",
        is_active: "yes", // Should be boolean
      };

      const result = schemaValidator.validateData("stocks", data);

      expect(result.isValid).toBe(false);
      expect(result.errors).toContain(
        'Field "is_active" must be a boolean value'
      );
    });

    test("should validate date fields", () => {
      const data = {
        symbol: "AAPL",
        date: "2023-01-01",
        close: 150.0,
      };

      const result = schemaValidator.validateData("stock_prices", data);

      expect(result.isValid).toBe(true);
      expect(result.errors).toEqual([]);
    });

    test("should validate invalid date format", () => {
      const data = {
        symbol: "AAPL",
        date: "invalid-date",
        close: 150.0,
      };

      const result = schemaValidator.validateData("stock_prices", data);

      expect(result.isValid).toBe(false);
      expect(result.errors).toContain(
        'Field "date" must be a valid date format'
      );
    });

    test("should handle unknown table schema", () => {
      const data = { id: 1, name: "test" };

      const result = schemaValidator.validateData("unknown_table", data);

      expect(result.isValid).toBe(false);
      expect(result.errors).toContain("Unknown table schema: unknown_table");
    });

    test("should handle null and undefined values", () => {
      const data = {
        symbol: "AAPL",
        name: null,
        sector: undefined,
      };

      const result = schemaValidator.validateData("stocks", data);

      expect(result.isValid).toBe(false);
      expect(result.errors).toContain('Required field "name" is missing');
    });
  });

  describe("validateTableExists", () => {
    test("should return true if table exists", async () => {
      query.mockResolvedValue({ rows: [{ exists: true }] });

      const result = await schemaValidator.validateTableExists("stocks");

      expect(result).toBe(true);
      expect(query).toHaveBeenCalledWith(
        "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_schema = $1 AND table_name = $2)",
        ["public", "stocks"]
      );
    });

    test("should return false if table does not exist", async () => {
      query.mockResolvedValue({ rows: [{ exists: false }] });

      const result =
        await schemaValidator.validateTableExists("nonexistent_table");

      expect(result).toBe(false);
    });

    test("should handle database errors", async () => {
      const error = new Error("Database connection failed");
      query.mockRejectedValue(error);

      await expect(
        schemaValidator.validateTableExists("stocks")
      ).rejects.toThrow("Database connection failed");
      expect(logger.error).toHaveBeenCalledWith(
        "Error validating table existence:",
        error
      );
    });
  });

  describe("validateColumns", () => {
    const mockColumnsResult = {
      rows: [
        { column_name: "symbol", data_type: "character varying", character_maximum_length: 10, is_nullable: "NO" },
        { column_name: "name", data_type: "character varying", character_maximum_length: 200, is_nullable: "NO" },
        { column_name: "sector", data_type: "character varying", character_maximum_length: 100, is_nullable: "YES" },
        { column_name: "industry", data_type: "character varying", character_maximum_length: 100, is_nullable: "YES" },
        { column_name: "market_cap", data_type: "bigint", is_nullable: "YES" },
        { column_name: "price", data_type: "numeric", numeric_precision: 10, numeric_scale: 2, is_nullable: "YES" },
        { column_name: "volume", data_type: "bigint", is_nullable: "YES" },
        { column_name: "pe_ratio", data_type: "numeric", numeric_precision: 8, numeric_scale: 2, is_nullable: "YES" },
        { column_name: "eps", data_type: "numeric", numeric_precision: 8, numeric_scale: 2, is_nullable: "YES" },
        { column_name: "dividend_yield", data_type: "numeric", numeric_precision: 5, numeric_scale: 4, is_nullable: "YES" },
        { column_name: "beta", data_type: "numeric", numeric_precision: 6, numeric_scale: 3, is_nullable: "YES" },
        { column_name: "exchange", data_type: "character varying", character_maximum_length: 20, is_nullable: "YES" },
        { column_name: "country", data_type: "character varying", character_maximum_length: 50, is_nullable: "YES" },
        { column_name: "currency", data_type: "character varying", character_maximum_length: 3, is_nullable: "YES" },
        { column_name: "is_active", data_type: "boolean", is_nullable: "YES" },
        { column_name: "last_updated", data_type: "timestamp without time zone", is_nullable: "YES" },
      ],
    };

    test("should validate table columns against schema", async () => {
      query.mockResolvedValue(mockColumnsResult);

      const result = await schemaValidator.validateColumns("stocks");

      expect(result.isValid).toBe(true);
      expect(result.missingColumns).toEqual([]);
      expect(result.mismatchedTypes).toEqual([]);
      expect(query).toHaveBeenCalledWith(
        expect.stringContaining("SELECT column_name, data_type"),
        ["stocks"]
      );
    });

    test("should detect missing columns", async () => {
      const incompleteResult = {
        rows: [
          {
            column_name: "symbol",
            data_type: "character varying",
            character_maximum_length: 10,
            is_nullable: "NO",
          },
          // Missing 'name' column
        ],
      };
      query.mockResolvedValue(incompleteResult);

      const result = await schemaValidator.validateColumns("stocks");

      expect(result.isValid).toBe(false);
      expect(result.missingColumns).toContain("name");
    });

    test("should detect type mismatches", async () => {
      const mismatchedResult = {
        rows: [
          {
            column_name: "symbol",
            data_type: "character varying",
            character_maximum_length: 10,
            is_nullable: "NO",
          },
          {
            column_name: "name",
            data_type: "integer", // Wrong type, should be VARCHAR
            is_nullable: "NO",
          },
        ],
      };
      query.mockResolvedValue(mismatchedResult);

      const result = await schemaValidator.validateColumns("stocks");

      expect(result.isValid).toBe(false);
      expect(result.mismatchedTypes).toEqual([
        {
          column: "name",
          expected: "VARCHAR",
          actual: "integer",
        },
      ]);
    });

    test("should handle unknown table schema", async () => {
      await expect(
        schemaValidator.validateColumns("unknown_table")
      ).rejects.toThrow("Unknown table schema: unknown_table");
    });
  });

  describe("validateIndexes", () => {
    const mockIndexesResult = {
      rows: [
        { indexname: "stocks_pkey" },
        { indexname: "idx_stocks_symbol" },
        { indexname: "idx_stock_prices_symbol_date" },
      ],
    };

    test("should validate table indexes", async () => {
      query.mockResolvedValue(mockIndexesResult);

      const result = await schemaValidator.validateIndexes("stock_prices");

      expect(result.isValid).toBe(true);
      expect(result.missingIndexes).toEqual([]);
      expect(query).toHaveBeenCalledWith(
        expect.stringContaining("SELECT indexname FROM pg_indexes"),
        ["stock_prices"]
      );
    });

    test("should detect missing indexes", async () => {
      const incompleteIndexResult = {
        rows: [
          { indexname: "stocks_pkey" },
          // Missing expected indexes
        ],
      };
      query.mockResolvedValue(incompleteIndexResult);

      const result = await schemaValidator.validateIndexes("stock_prices");

      expect(result.isValid).toBe(false);
      expect(result.missingIndexes.length).toBeGreaterThan(0);
    });
  });

  describe("sanitizeInput", () => {
    test("should sanitize basic string input", () => {
      const input = "  Hello World  ";
      const result = schemaValidator.sanitizeInput(input);

      expect(result).toBe("Hello World");
    });

    test("should remove SQL injection attempts", () => {
      const maliciousInput = "'; DROP TABLE stocks; --";
      const result = schemaValidator.sanitizeInput(maliciousInput);

      expect(result).not.toContain("DROP TABLE");
      expect(result).not.toContain(";");
      expect(result).not.toContain("--");
    });

    test("should handle object inputs", () => {
      const input = {
        symbol: "  AAPL  ",
        name: "Apple Inc.",
        malicious: "'; DROP TABLE stocks; --",
      };

      const result = schemaValidator.sanitizeInput(input);

      expect(result.symbol).toBe("AAPL");
      expect(result.name).toBe("Apple Inc.");
      expect(result.malicious).not.toContain("DROP TABLE");
    });

    test("should handle array inputs", () => {
      const input = ["  AAPL  ", "  MSFT  ", "'; DROP TABLE stocks; --"];
      const result = schemaValidator.sanitizeInput(input);

      expect(result[0]).toBe("AAPL");
      expect(result[1]).toBe("MSFT");
      expect(result[2]).not.toContain("DROP TABLE");
    });

    test("should handle null and undefined inputs", () => {
      expect(schemaValidator.sanitizeInput(null)).toBe(null);
      expect(schemaValidator.sanitizeInput(undefined)).toBe(undefined);
    });

    test("should preserve numeric inputs", () => {
      expect(schemaValidator.sanitizeInput(123)).toBe(123);
      expect(schemaValidator.sanitizeInput(123.45)).toBe(123.45);
    });

    test("should preserve boolean inputs", () => {
      expect(schemaValidator.sanitizeInput(true)).toBe(true);
      expect(schemaValidator.sanitizeInput(false)).toBe(false);
    });
  });

  describe("generateCreateTableSQL", () => {
    test("should generate CREATE TABLE SQL for stocks", () => {
      const sql = schemaValidator.generateCreateTableSQL("stocks");

      expect(sql).toContain("CREATE TABLE IF NOT EXISTS stocks");
      expect(sql).toContain("symbol VARCHAR(10) UNIQUE NOT NULL");
      expect(sql).toContain("name VARCHAR(200) NOT NULL");
      expect(sql).toContain("market_cap BIGINT CHECK (market_cap >= 0)");
      expect(sql).toContain("is_active BOOLEAN DEFAULT true");
    });

    test("should generate CREATE TABLE SQL with primary key", () => {
      const sql = schemaValidator.generateCreateTableSQL("stock_prices");

      expect(sql).toContain("CREATE TABLE IF NOT EXISTS stock_prices");
      expect(sql).toContain("PRIMARY KEY (symbol, date)");
    });

    test("should handle unknown table schema", () => {
      expect(() =>
        schemaValidator.generateCreateTableSQL("unknown_table")
      ).toThrow("Unknown table schema: unknown_table");
    });
  });
});
