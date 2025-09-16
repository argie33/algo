/**
 * Unit tests for SchemaValidator
 */

// Mock database module
const mockQuery = jest.fn();
jest.mock("../../../utils/database", () => ({
  query: mockQuery,
}));

// Mock logger
const mockLogger = {
  error: jest.fn(),
  warn: jest.fn(),
  info: jest.fn(),
};
jest.mock("../../../utils/logger", () => mockLogger);

const {
  validateData,
  validateTableStructure,
  validateDatabaseIntegrity,
  generateCreateTableSQL,
  getTableSchema,
  listTables,
  sanitizeInput,
  validateTableExists,
  validateColumns,
  validateIndexes,
  safeQuery,
  schemas,
} = require("../../../utils/schemaValidator");

describe("Schema Validator", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe("validateData", () => {
    test("should validate valid stock data successfully", () => {
      const stockData = {
        symbol: "AAPL",
        name: "Apple Inc.",
        sector: "Technology",
        market_cap: 2500000000000,
        price: 150.5,
        is_active: true,
      };

      const result = validateData("stocks", stockData);

      expect(result.valid).toBe(true);
      expect(result.isValid).toBe(true);
      expect(result.errors).toHaveLength(0);
      expect(result.data).toHaveProperty("symbol", "AAPL");
      expect(result.data).toHaveProperty("name", "Apple Inc.");
    });

    test("should fail validation for missing required fields", () => {
      const invalidData = {
        sector: "Technology",
        // Missing required 'symbol' and 'name'
      };

      const result = validateData("stocks", invalidData);

      expect(result.valid).toBe(false);
      expect(result.isValid).toBe(false);
      expect(result.errors).toContain('Required field "symbol" is missing');
      expect(result.errors).toContain('Required field "name" is missing');
      expect(result.errorDetails).toHaveLength(2);
    });

    test("should fail validation for unknown table", () => {
      const result = validateData("nonexistent_table", {});

      expect(result.valid).toBe(false);
      expect(result.isValid).toBe(false);
      expect(result.errors).toContain(
        "Unknown table schema: nonexistent_table"
      );
    });

    test("should fail validation for unknown field", () => {
      const invalidData = {
        symbol: "AAPL",
        name: "Apple Inc.",
        unknown_field: "value",
      };

      const result = validateData("stocks", invalidData);

      expect(result.valid).toBe(false);
      expect(result.errors).toContain(
        'Unknown field "unknown_field" for table "stocks"'
      );
    });

    test("should validate VARCHAR field with max length constraint", () => {
      const longSymbolData = {
        symbol: "VERYLONGSYMBOL", // Exceeds 10 char limit
        name: "Test Company",
      };

      const result = validateData("stocks", longSymbolData);

      expect(result.valid).toBe(false);
      expect(result.errors).toContain(
        'Field "symbol" exceeds maximum length of 10 characters'
      );
    });

    test("should validate INTEGER field constraints", () => {
      const invalidQuarter = {
        symbol: "AAPL",
        report_date: "2023-01-01",
        quarter: 5, // Exceeds max of 4
      };

      const result = validateData("earnings_reports", invalidQuarter);

      expect(result.valid).toBe(false);
      expect(result.errors).toContain('Field "quarter" must be at most 4');
    });

    test("should validate DECIMAL precision constraints", () => {
      const precisionData = {
        symbol: "AAPL",
        report_date: "2023-01-01",
        eps_reported: 123.123456, // Too many decimal places for precision 8,2
      };

      const result = validateData("earnings_reports", precisionData);

      expect(result.valid).toBe(false);
      expect(result.errors).toContain(
        'Field "eps_reported" exceeds precision constraints (8,2)'
      );
    });

    test("should validate BOOLEAN field types", () => {
      const booleanData = {
        symbol: "AAPL",
        name: "Apple Inc.",
        is_active: "invalid_boolean",
      };

      const result = validateData("stocks", booleanData);

      expect(result.valid).toBe(false);
      expect(result.errors).toContain(
        'Field "is_active" must be a boolean value'
      );
    });

    test("should validate DATE field format", () => {
      const dateData = {
        symbol: "AAPL",
        report_date: "invalid-date",
      };

      const result = validateData("earnings_reports", dateData);

      expect(result.valid).toBe(false);
      expect(result.errors).toContain(
        'Field "report_date" must be a valid date format'
      );
    });

    test("should allow null values for non-required fields", () => {
      const nullData = {
        symbol: "AAPL",
        name: "Apple Inc.",
        sector: null, // Optional field
        market_cap: null,
      };

      const result = validateData("stocks", nullData);

      expect(result.valid).toBe(true);
      expect(result.data).toHaveProperty("sector", null);
    });
  });

  describe("validateTableStructure", () => {
    test("should validate existing table with correct structure", async () => {
      // Mock table exists
      mockQuery.mockResolvedValueOnce({
        rows: [{ exists: true }],
      });

      // Mock table columns with all required columns
      mockQuery.mockResolvedValueOnce({
        rows: [
          {
            column_name: "symbol",
            data_type: "character varying",
            is_nullable: "NO",
            column_default: null,
          },
          {
            column_name: "name",
            data_type: "character varying",
            is_nullable: "NO",
            column_default: null,
          },
          {
            column_name: "sector",
            data_type: "character varying",
            is_nullable: "YES",
            column_default: null,
          },
          {
            column_name: "industry",
            data_type: "character varying",
            is_nullable: "YES",
            column_default: null,
          },
          {
            column_name: "market_cap",
            data_type: "bigint",
            is_nullable: "YES",
            column_default: null,
          },
          {
            column_name: "price",
            data_type: "numeric",
            is_nullable: "YES",
            column_default: null,
          },
          {
            column_name: "volume",
            data_type: "bigint",
            is_nullable: "YES",
            column_default: null,
          },
          {
            column_name: "pe_ratio",
            data_type: "numeric",
            is_nullable: "YES",
            column_default: null,
          },
          {
            column_name: "eps",
            data_type: "numeric",
            is_nullable: "YES",
            column_default: null,
          },
          {
            column_name: "dividend_yield",
            data_type: "numeric",
            is_nullable: "YES",
            column_default: null,
          },
          {
            column_name: "beta",
            data_type: "numeric",
            is_nullable: "YES",
            column_default: null,
          },
          {
            column_name: "exchange",
            data_type: "character varying",
            is_nullable: "YES",
            column_default: null,
          },
          {
            column_name: "country",
            data_type: "character varying",
            is_nullable: "YES",
            column_default: null,
          },
          {
            column_name: "currency",
            data_type: "character varying",
            is_nullable: "YES",
            column_default: null,
          },
          {
            column_name: "is_active",
            data_type: "boolean",
            is_nullable: "YES",
            column_default: "true",
          },
          {
            column_name: "last_updated",
            data_type: "timestamp without time zone",
            is_nullable: "YES",
            column_default: null,
          },
        ],
      });

      const result = await validateTableStructure("stocks");

      expect(result.valid).toBe(true);
      expect(result.errors).toHaveLength(0);
      expect(result.actualColumns).toContain("symbol");
      expect(result.expectedColumns).toContain("symbol");
    });

    test("should fail validation for non-existent table", async () => {
      mockQuery.mockResolvedValueOnce({
        rows: [{ exists: false }],
      });

      const result = await validateTableStructure("stocks");

      expect(result.valid).toBe(false);
      expect(result.errors).toContain("Table 'stocks' does not exist");
    });

    test("should fail validation for unknown schema", async () => {
      const result = await validateTableStructure("unknown_table");

      expect(result.valid).toBe(false);
      expect(result.errors).toContain(
        "Schema validation failed: No schema defined for table: unknown_table"
      );
    });

    test("should handle database errors gracefully", async () => {
      const dbError = new Error("Database connection failed");
      mockQuery.mockRejectedValueOnce(dbError);

      const result = await validateTableStructure("stocks");

      expect(result.valid).toBe(false);
      expect(result.errors).toContain(
        "Schema validation failed: Database connection failed"
      );
      expect(mockLogger.error).toHaveBeenCalledWith("Schema validation error", {
        error: dbError,
        tableName: "stocks",
      });
    });

    test("should detect missing columns", async () => {
      mockQuery.mockResolvedValueOnce({
        rows: [{ exists: true }],
      });

      mockQuery.mockResolvedValueOnce({
        rows: [
          {
            column_name: "symbol",
            data_type: "character varying",
            is_nullable: "NO",
            column_default: null,
          },
          // Missing 'name' column
        ],
      });

      const result = await validateTableStructure("stocks");

      expect(result.valid).toBe(false);
      expect(result.errors).toContain(
        "Missing column 'name' in table 'stocks'"
      );
    });

    test("should warn about extra columns", async () => {
      mockQuery.mockResolvedValueOnce({
        rows: [{ exists: true }],
      });

      // Include all required columns plus extra
      mockQuery.mockResolvedValueOnce({
        rows: [
          {
            column_name: "symbol",
            data_type: "character varying",
            is_nullable: "NO",
            column_default: null,
          },
          {
            column_name: "name",
            data_type: "character varying",
            is_nullable: "NO",
            column_default: null,
          },
          {
            column_name: "sector",
            data_type: "character varying",
            is_nullable: "YES",
            column_default: null,
          },
          {
            column_name: "industry",
            data_type: "character varying",
            is_nullable: "YES",
            column_default: null,
          },
          {
            column_name: "market_cap",
            data_type: "bigint",
            is_nullable: "YES",
            column_default: null,
          },
          {
            column_name: "price",
            data_type: "numeric",
            is_nullable: "YES",
            column_default: null,
          },
          {
            column_name: "volume",
            data_type: "bigint",
            is_nullable: "YES",
            column_default: null,
          },
          {
            column_name: "pe_ratio",
            data_type: "numeric",
            is_nullable: "YES",
            column_default: null,
          },
          {
            column_name: "eps",
            data_type: "numeric",
            is_nullable: "YES",
            column_default: null,
          },
          {
            column_name: "dividend_yield",
            data_type: "numeric",
            is_nullable: "YES",
            column_default: null,
          },
          {
            column_name: "beta",
            data_type: "numeric",
            is_nullable: "YES",
            column_default: null,
          },
          {
            column_name: "exchange",
            data_type: "character varying",
            is_nullable: "YES",
            column_default: null,
          },
          {
            column_name: "country",
            data_type: "character varying",
            is_nullable: "YES",
            column_default: null,
          },
          {
            column_name: "currency",
            data_type: "character varying",
            is_nullable: "YES",
            column_default: null,
          },
          {
            column_name: "is_active",
            data_type: "boolean",
            is_nullable: "YES",
            column_default: "true",
          },
          {
            column_name: "last_updated",
            data_type: "timestamp without time zone",
            is_nullable: "YES",
            column_default: null,
          },
          {
            column_name: "extra_column",
            data_type: "text",
            is_nullable: "YES",
            column_default: null,
          },
        ],
      });

      const result = await validateTableStructure("stocks");

      expect(result.valid).toBe(true);
      expect(mockLogger.warn).toHaveBeenCalledWith(
        "Extra column 'extra_column' found in table 'stocks'"
      );
    });
  });

  describe("validateDatabaseIntegrity", () => {
    test("should validate all tables successfully", async () => {
      // Mock successful validation for all calls
      mockQuery.mockResolvedValue({
        rows: [{ exists: true }],
      });

      // Mock minimal column structure for each table
      mockQuery.mockResolvedValue({
        rows: [
          {
            column_name: "symbol",
            data_type: "character varying",
            is_nullable: "NO",
            column_default: null,
          },
        ],
      });

      const result = await validateDatabaseIntegrity();

      expect(result.valid).toBe(true);
      expect(result.errors).toHaveLength(0);
      expect(result.tableResults).toBeDefined();
      expect(result.checkedAt).toBeDefined();
    });

    test("should collect errors from failed table validations", async () => {
      // Mock table doesn't exist
      mockQuery.mockResolvedValueOnce({
        rows: [{ exists: false }],
      });

      const result = await validateDatabaseIntegrity();

      expect(result.valid).toBe(false);
      expect(result.errors.length).toBeGreaterThan(0);
      expect(result.tableResults).toBeDefined();
    });
  });

  describe("generateCreateTableSQL", () => {
    test("should generate CREATE TABLE SQL for stocks table", () => {
      const sql = generateCreateTableSQL("stocks");

      expect(sql).toContain("CREATE TABLE IF NOT EXISTS stocks");
      expect(sql).toContain("symbol VARCHAR(10)");
      expect(sql).toContain("name VARCHAR(200)");
      expect(sql).toContain("market_cap BIGINT");
      expect(sql).toContain("NOT NULL");
    });

    test("should include DECIMAL precision in SQL", () => {
      const sql = generateCreateTableSQL("earnings_reports");

      expect(sql).toContain("eps_reported DECIMAL(8,2)");
    });

    test("should include PRIMARY KEY constraint", () => {
      const sql = generateCreateTableSQL("stock_prices");

      expect(sql).toContain("PRIMARY KEY (symbol, date)");
    });

    test("should include CHECK constraints for minimum values", () => {
      const sql = generateCreateTableSQL("stocks");

      expect(sql).toContain("CHECK (market_cap >= 0)");
      expect(sql).toContain("CHECK (price >= 0)");
    });

    test("should include indexes in SQL", () => {
      const sql = generateCreateTableSQL("stock_symbols");

      expect(sql).toContain("CREATE INDEX IF NOT EXISTS");
    });

    test("should handle unknown table", () => {
      expect(() => generateCreateTableSQL("unknown_table")).toThrow(
        "Unknown table schema: unknown_table"
      );
    });

    test("should include default values", () => {
      const sql = generateCreateTableSQL("stocks");

      expect(sql).toContain("is_active BOOLEAN DEFAULT true");
    });

    test("should include UNIQUE constraints", () => {
      const sql = generateCreateTableSQL("stocks");

      expect(sql).toContain("symbol VARCHAR(10) UNIQUE");
    });
  });

  describe("getTableSchema", () => {
    test("should return schema for existing table", () => {
      const schema = getTableSchema("stocks");

      expect(schema).toBeDefined();
      expect(schema.required).toContain("symbol");
      expect(schema.columns).toHaveProperty("symbol");
    });

    test("should return null for unknown table", () => {
      const schema = getTableSchema("unknown_table");

      expect(schema).toBeNull();
    });
  });

  describe("listTables", () => {
    test("should return array of table names", () => {
      const tables = listTables();

      expect(Array.isArray(tables)).toBe(true);
      expect(tables).toContain("stocks");
      expect(tables).toContain("stock_prices");
      expect(tables.length).toBeGreaterThan(0);
    });
  });

  describe("sanitizeInput", () => {
    test("should sanitize string inputs", () => {
      const maliciousInput = "'; DROP TABLE users; --";
      const sanitized = sanitizeInput(maliciousInput);

      expect(sanitized).not.toContain("'");
      expect(sanitized).not.toContain(";");
      expect(sanitized).not.toContain("DROP");
    });

    test("should handle null and undefined inputs", () => {
      expect(sanitizeInput(null)).toBeNull();
      expect(sanitizeInput(undefined)).toBeUndefined();
    });

    test("should sanitize arrays recursively", () => {
      const arrayInput = ["safe", "'; DROP TABLE users; --"];
      const sanitized = sanitizeInput(arrayInput);

      expect(Array.isArray(sanitized)).toBe(true);
      expect(sanitized[0]).toBe("safe");
      expect(sanitized[1]).not.toContain("DROP");
    });

    test("should sanitize objects recursively", () => {
      const objectInput = {
        safe: "value",
        malicious: "'; DROP TABLE users; --",
      };
      const sanitized = sanitizeInput(objectInput);

      expect(sanitized.safe).toBe("value");
      expect(sanitized.malicious).not.toContain("DROP");
    });

    test("should preserve numbers and booleans", () => {
      expect(sanitizeInput(123)).toBe(123);
      expect(sanitizeInput(true)).toBe(true);
    });

    test("should trim whitespace from strings", () => {
      const input = "  clean input  ";
      const sanitized = sanitizeInput(input);

      expect(sanitized).toBe("clean input");
    });
  });

  describe("validateTableExists", () => {
    test("should return true for existing table", async () => {
      mockQuery.mockResolvedValueOnce({
        rows: [{ exists: true }],
      });

      const exists = await validateTableExists("stocks");

      expect(exists).toBe(true);
      expect(mockQuery).toHaveBeenCalledWith(
        "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_schema = $1 AND table_name = $2)",
        ["public", "stocks"]
      );
    });

    test("should return false for non-existent table", async () => {
      mockQuery.mockResolvedValueOnce({
        rows: [{ exists: false }],
      });

      const exists = await validateTableExists("nonexistent");

      expect(exists).toBe(false);
    });

    test("should handle database errors", async () => {
      const dbError = new Error("Connection failed");
      mockQuery.mockRejectedValueOnce(dbError);

      await expect(validateTableExists("stocks")).rejects.toThrow(
        "Connection failed"
      );
      expect(mockLogger.error).toHaveBeenCalledWith(
        "Error validating table existence:",
        dbError
      );
    });
  });

  describe("validateColumns", () => {
    test("should validate columns successfully", async () => {
      mockQuery.mockResolvedValueOnce({
        rows: [
          {
            column_name: "symbol",
            data_type: "character varying",
            is_nullable: "NO",
            column_default: null,
          },
          {
            column_name: "name",
            data_type: "character varying",
            is_nullable: "NO",
            column_default: null,
          },
          {
            column_name: "sector",
            data_type: "character varying",
            is_nullable: "YES",
            column_default: null,
          },
          {
            column_name: "industry",
            data_type: "character varying",
            is_nullable: "YES",
            column_default: null,
          },
          {
            column_name: "market_cap",
            data_type: "bigint",
            is_nullable: "YES",
            column_default: null,
          },
          {
            column_name: "price",
            data_type: "numeric",
            is_nullable: "YES",
            column_default: null,
          },
          {
            column_name: "volume",
            data_type: "bigint",
            is_nullable: "YES",
            column_default: null,
          },
          {
            column_name: "pe_ratio",
            data_type: "numeric",
            is_nullable: "YES",
            column_default: null,
          },
          {
            column_name: "eps",
            data_type: "numeric",
            is_nullable: "YES",
            column_default: null,
          },
          {
            column_name: "dividend_yield",
            data_type: "numeric",
            is_nullable: "YES",
            column_default: null,
          },
          {
            column_name: "beta",
            data_type: "numeric",
            is_nullable: "YES",
            column_default: null,
          },
          {
            column_name: "exchange",
            data_type: "character varying",
            is_nullable: "YES",
            column_default: null,
          },
          {
            column_name: "country",
            data_type: "character varying",
            is_nullable: "YES",
            column_default: null,
          },
          {
            column_name: "currency",
            data_type: "character varying",
            is_nullable: "YES",
            column_default: null,
          },
          {
            column_name: "is_active",
            data_type: "boolean",
            is_nullable: "YES",
            column_default: "true",
          },
          {
            column_name: "last_updated",
            data_type: "timestamp without time zone",
            is_nullable: "YES",
            column_default: null,
          },
        ],
      });

      const result = await validateColumns("stocks");

      expect(result.valid).toBe(true);
      expect(result.isValid).toBe(true);
      expect(result.missingColumns).toHaveLength(0);
      expect(result.mismatchedTypes).toHaveLength(0);
    });

    test("should detect missing columns", async () => {
      mockQuery.mockResolvedValueOnce({
        rows: [
          {
            column_name: "symbol",
            data_type: "character varying",
            is_nullable: "NO",
            column_default: null,
          },
          // Missing 'name' column
        ],
      });

      const result = await validateColumns("stocks");

      expect(result.valid).toBe(false);
      expect(result.missingColumns).toContain("name");
    });

    test("should detect type mismatches", async () => {
      mockQuery.mockResolvedValueOnce({
        rows: [
          {
            column_name: "symbol",
            data_type: "text",
            is_nullable: "NO",
            column_default: null,
          }, // Should be VARCHAR
          {
            column_name: "name",
            data_type: "character varying",
            is_nullable: "NO",
            column_default: null,
          },
        ],
      });

      const result = await validateColumns("stocks");

      expect(result.valid).toBe(false);
      expect(result.mismatchedTypes).toEqual(
        expect.arrayContaining([
          expect.objectContaining({
            column: "symbol",
            expected: "VARCHAR",
            actual: "text",
          }),
        ])
      );
    });

    test("should handle unknown table schema", async () => {
      await expect(validateColumns("unknown_table")).rejects.toThrow(
        "Unknown table schema: unknown_table"
      );
    });

    test("should handle database errors", async () => {
      const dbError = new Error("Query failed");
      mockQuery.mockRejectedValueOnce(dbError);

      await expect(validateColumns("stocks")).rejects.toThrow("Query failed");
      expect(mockLogger.error).toHaveBeenCalled();
    });
  });

  describe("validateIndexes", () => {
    test("should validate indexes successfully", async () => {
      mockQuery.mockResolvedValueOnce({
        rows: [
          { indexname: "stocks_symbol_idx" },
          { indexname: "stocks_exchange_idx" },
          { indexname: "stocks_sector_idx" },
        ],
      });

      const result = await validateIndexes("stocks");

      expect(result.valid).toBe(true);
      expect(result.missingIndexes).toHaveLength(0);
    });

    test("should return valid for table without indexes", async () => {
      const result = await validateIndexes("fear_greed_index"); // Table with only created_at index

      expect(result.valid).toBe(true);
      expect(result.missingIndexes).toBeDefined();
    });

    test("should handle database errors", async () => {
      const dbError = new Error("Index query failed");
      mockQuery.mockRejectedValueOnce(dbError);

      await expect(validateIndexes("stocks")).rejects.toThrow(
        "Index query failed"
      );
      expect(mockLogger.error).toHaveBeenCalled();
    });
  });

  describe("safeQuery", () => {
    test("should execute query successfully", async () => {
      const expectedResult = { rows: [{ count: 5 }] };

      // Clear previous mock calls
      mockQuery.mockClear();
      mockQuery.mockResolvedValueOnce(expectedResult);

      const result = await safeQuery("SELECT COUNT(*) as count FROM test");

      expect(result).toEqual(expectedResult);
      expect(mockQuery).toHaveBeenCalledWith(
        "SELECT COUNT(*) as count FROM test",
        []
      );
    });

    test("should return null on database error and log warning", async () => {
      const dbError = new Error("Connection timeout");

      // Clear previous mock calls
      mockQuery.mockClear();
      mockQuery.mockRejectedValueOnce(dbError);

      const result = await safeQuery("SELECT * FROM test", ["param"]);

      expect(result).toBeNull();
      expect(mockLogger.warn).toHaveBeenCalledWith(
        "Safe query failed, database may be unavailable",
        expect.objectContaining({
          error: "Connection timeout",
          queryText: "SELECT * FROM test",
        })
      );
    });

    test("should truncate long query text in logs", async () => {
      const longQuery = "SELECT " + "column, ".repeat(50) + "FROM test";
      const dbError = new Error("Query too long");

      // Clear previous mock calls
      mockQuery.mockClear();
      mockQuery.mockRejectedValueOnce(dbError);

      await safeQuery(longQuery);

      expect(mockLogger.warn).toHaveBeenCalledWith(
        "Safe query failed, database may be unavailable",
        expect.objectContaining({
          queryText: expect.stringMatching(/\.\.\.$/),
        })
      );
    });
  });

  describe("field sanitization", () => {
    test("should sanitize VARCHAR fields", () => {
      const data = {
        symbol: "  AAPL  ",
        name: "Apple Inc.",
      };

      const result = validateData("stocks", data);

      expect(result.data.symbol).toBe("AAPL"); // Trimmed
      expect(result.data.name).toBe("Apple Inc.");
    });

    test("should convert string numbers to proper types", () => {
      const data = {
        symbol: "AAPL",
        name: "Apple Inc.",
        market_cap: "1000000000", // String number
        price: "150.50", // String decimal
        is_active: "true", // String boolean
      };

      const result = validateData("stocks", data);

      expect(result.data.market_cap).toBe(1000000000);
      expect(result.data.price).toBe(150.5);
      expect(result.data.is_active).toBe(true);
    });

    test("should handle boolean conversion edge cases", () => {
      const testCases = [
        { value: true, expected: true },
        { value: false, expected: false },
        { value: "true", expected: true },
        { value: "false", expected: false },
        { value: 1, expected: true },
        { value: 0, expected: false },
      ];

      testCases.forEach(({ value, expected }) => {
        const data = {
          symbol: "TEST",
          name: "Test",
          is_active: value,
        };

        const result = validateData("stocks", data);
        expect(result.data.is_active).toBe(expected);
      });
    });

    test("should convert date strings to ISO format", () => {
      const data = {
        symbol: "AAPL",
        report_date: "2023-01-15",
      };

      const result = validateData("earnings_reports", data);

      expect(result.data.report_date).toMatch(
        /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}.\d{3}Z$/
      );
    });
  });

  describe("edge cases and error scenarios", () => {
    test("should handle empty data object", () => {
      const result = validateData("stocks", {});

      expect(result.valid).toBe(false);
      expect(result.errors).toContain('Required field "symbol" is missing');
      expect(result.errors).toContain('Required field "name" is missing');
    });

    test("should validate complex table with multiple constraints", () => {
      const complexData = {
        user_id: "user123",
        symbol: "AAPL",
        broker: "alpaca",
        quantity: 100.5,
        market_value: 15050.0,
        cost_basis: 14000.0,
        pnl: 1050.0,
        current_price: 150.5,
      };

      const result = validateData("portfolio_holdings", complexData);

      expect(result.valid).toBe(true);
      expect(result.data.quantity).toBe(100.5);
    });

    test("should handle very long strings gracefully", () => {
      const longString = "x".repeat(1000);
      const data = {
        symbol: longString,
        name: "Test",
      };

      const result = validateData("stocks", data);

      expect(result.valid).toBe(false);
      expect(result.errors).toContain(
        'Field "symbol" exceeds maximum length of 10 characters'
      );
    });
  });

  describe("schemas export", () => {
    test("should export schemas object", () => {
      expect(schemas).toBeDefined();
      expect(schemas.stocks).toBeDefined();
      expect(schemas.stock_prices).toBeDefined();
      expect(typeof schemas).toBe("object");
    });
  });
});
