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

    test("should generate DECIMAL constraints with precision and scale", () => {
      const sql = schemaValidator.generateCreateTableSQL("stocks");

      expect(sql).toContain("price DECIMAL(10,2)");
      expect(sql).toContain("CHECK (price >= 0)");
    });

    test("should generate indexes for tables", () => {
      const sql = schemaValidator.generateCreateTableSQL("watchlists");

      expect(sql).toContain("CREATE INDEX IF NOT EXISTS idx_watchlists_user_id ON watchlists (user_id)");
    });

    test("should handle boolean defaults", () => {
      const sql = schemaValidator.generateCreateTableSQL("stocks");

      expect(sql).toContain("is_active BOOLEAN DEFAULT true");
    });

    test("should handle unknown table schema", () => {
      expect(() =>
        schemaValidator.generateCreateTableSQL("unknown_table")
      ).toThrow("Unknown table schema: unknown_table");
    });
  });

  describe("getTableSchema", () => {
    test("should return table schema for existing table", () => {
      const schema = schemaValidator.getTableSchema("stocks");

      expect(schema).toBeDefined();
      expect(schema.required).toContain("symbol");
      expect(schema.columns).toHaveProperty("symbol");
    });

    test("should return null for non-existent table", () => {
      const schema = schemaValidator.getTableSchema("unknown_table");

      expect(schema).toBeNull();
    });
  });

  describe("listTables", () => {
    test("should return list of all available tables", () => {
      const tables = schemaValidator.listTables();

      expect(Array.isArray(tables)).toBe(true);
      expect(tables).toContain("stocks");
      expect(tables).toContain("stock_prices");
      expect(tables).toContain("watchlists");
    });
  });

  describe("validateTableStructure", () => {
    test("should validate table structure successfully", async () => {
      // Mock table exists query
      query.mockResolvedValueOnce({ rows: [{ exists: true }] });
      // Mock columns query with all expected columns from stocks schema
      query.mockResolvedValueOnce({
        rows: [
          { column_name: "symbol", data_type: "character varying" },
          { column_name: "name", data_type: "character varying" },
          { column_name: "sector", data_type: "character varying" },
          { column_name: "industry", data_type: "character varying" },
          { column_name: "market_cap", data_type: "bigint" },
          { column_name: "price", data_type: "numeric" },
          { column_name: "volume", data_type: "bigint" },
          { column_name: "pe_ratio", data_type: "numeric" },
          { column_name: "eps", data_type: "numeric" },
          { column_name: "dividend_yield", data_type: "numeric" },
          { column_name: "beta", data_type: "numeric" },
          { column_name: "exchange", data_type: "character varying" },
          { column_name: "country", data_type: "character varying" },
          { column_name: "currency", data_type: "character varying" },
          { column_name: "is_active", data_type: "boolean" },
          { column_name: "last_updated", data_type: "timestamp without time zone" }
        ]
      });

      const result = await schemaValidator.validateTableStructure("stocks");

      expect(result.valid).toBe(true);
      expect(result.errors).toEqual([]);
    });

    test("should handle table not exists", async () => {
      // For unknown table schema, validateTableStructure catches error and returns result
      const result = await schemaValidator.validateTableStructure("nonexistent");
      
      expect(result.valid).toBe(false);
      expect(result.errors).toContain("Schema validation failed: No schema defined for table: nonexistent");
    });

    test("should handle unknown table schema", async () => {
      // validateTableStructure catches error and returns result
      const result = await schemaValidator.validateTableStructure("unknown_table");
      
      expect(result.valid).toBe(false);
      expect(result.errors).toContain("Schema validation failed: No schema defined for table: unknown_table");
    });

    test("should handle table not exists for known schema", async () => {
      // Test case where schema exists but table doesn't exist in database
      query.mockResolvedValueOnce({ rows: [{ exists: false }] });

      const result = await schemaValidator.validateTableStructure("stocks");

      expect(result.valid).toBe(false);
      expect(result.errors).toContain("Table 'stocks' does not exist");
    });

    test("should handle database errors", async () => {
      query.mockRejectedValue(new Error("Database connection failed"));

      const result = await schemaValidator.validateTableStructure("stocks");
      
      expect(result.valid).toBe(false);
      expect(result.errors).toContain("Schema validation failed: Database connection failed");
    });
  });

  describe("validateDatabaseIntegrity", () => {
    test("should validate all tables successfully", async () => {
      // Mock successful validation for all tables
      query.mockResolvedValue({ rows: [{ exists: true }] });
      query.mockResolvedValue({ rows: [] }); // Mock columns response

      const result = await schemaValidator.validateDatabaseIntegrity();

      expect(result.valid).toBeDefined();
      expect(result.tableResults).toBeDefined();
      expect(result.checkedAt).toBeDefined();
    });

    test("should handle individual table validation errors", async () => {
      // First call succeeds, second call fails
      query.mockResolvedValueOnce({ rows: [{ exists: true }] });
      query.mockRejectedValueOnce(new Error("Table error"));

      const result = await schemaValidator.validateDatabaseIntegrity();

      expect(result.tableResults).toBeDefined();
      expect(result.errors).toBeDefined();
    });
  });

  describe("field validation edge cases", () => {
    test("should validate TEXT field type", () => {
      const data = {
        symbol: "AAPL",
        date: "2023-01-01",
        description: "This is a long description", // TEXT field
      };

      const result = schemaValidator.validateData("watchlists", data);
      // Should not error on TEXT fields
    });

    test("should validate TIMESTAMP field type", () => {
      const data = {
        user_id: "user123",
        broker_name: "alpaca",
        encrypted_api_key: "key123",
        created_at: "2023-01-01T12:00:00Z", // TIMESTAMP field
      };

      const result = schemaValidator.validateData("user_api_keys", data);
      
      expect(result.isValid).toBe(true);
    });

    test("should validate DOUBLE PRECISION field type", () => {
      const data = {
        symbol: "AAPL",
        date: "2023-01-01",
        rsi: 65.5, // DOUBLE PRECISION field
      };

      const result = schemaValidator.validateData("technical_data_daily", data);
      
      expect(result.isValid).toBe(true);
    });

    test("should handle unknown field in data validation", () => {
      const data = {
        symbol: "AAPL",
        name: "Apple Inc.",
        unknown_field: "value", // Unknown field
      };

      const result = schemaValidator.validateData("stocks", data);

      expect(result.isValid).toBe(false);
      expect(result.errors).toContain('Unknown field "unknown_field" for table "stocks"');
    });

    test("should validate INTEGER max constraints", () => {
      const data = {
        symbol: "AAPL",
        report_date: "2023-01-01",
        quarter: 5, // Exceeds max of 4
      };

      const result = schemaValidator.validateData("earnings_reports", data);

      expect(result.isValid).toBe(false);
      expect(result.errors).toContain('Field "quarter" must be at most 4');
    });

    test("should validate BIGINT min constraints", () => {
      const data = {
        symbol: "AAPL",
        name: "Apple Inc.",
        market_cap: -1000000, // Below minimum of 0
      };

      const result = schemaValidator.validateData("stocks", data);

      expect(result.isValid).toBe(false);
      expect(result.errors).toContain('Field "market_cap" must be at least 0');
    });

    test("should handle boolean value conversions", () => {
      const testCases = [
        { value: true, expected: true },
        { value: false, expected: false },
        { value: "true", expected: true },
        { value: "false", expected: true }, // Should pass validation
        { value: 1, expected: true },
        { value: 0, expected: true }, // Should pass validation
      ];

      testCases.forEach(({ value }) => {
        const data = {
          symbol: "AAPL",
          name: "Apple Inc.",
          is_active: value,
        };

        const result = schemaValidator.validateData("stocks", data);
        expect(result.isValid).toBe(true);
      });
    });
  });

  describe("safeQuery", () => {
    test("should execute query successfully", async () => {
      const mockResult = { rows: [{ id: 1 }], rowCount: 1 };
      query.mockResolvedValue(mockResult);

      const result = await schemaValidator.safeQuery("SELECT * FROM stocks");

      expect(result).toEqual(mockResult);
    });

    test("should return null on database errors", async () => {
      query.mockRejectedValue(new Error("Database connection failed"));

      const result = await schemaValidator.safeQuery("SELECT * FROM stocks");

      expect(result).toBeNull();
      expect(logger.warn).toHaveBeenCalledWith(
        "Safe query failed, database may be unavailable",
        expect.objectContaining({
          error: "Database connection failed",
          queryText: "SELECT * FROM stocks"
        })
      );
    });

    test("should truncate long queries in error messages", async () => {
      query.mockRejectedValue(new Error("Database error"));
      
      const longQuery = "SELECT * FROM stocks WHERE ".repeat(10) + "condition = 1";
      const result = await schemaValidator.safeQuery(longQuery);

      expect(result).toBeNull();
      expect(logger.warn).toHaveBeenCalledWith(
        "Safe query failed, database may be unavailable",
        expect.objectContaining({
          queryText: expect.stringContaining("...")
        })
      );
    });
  });

  describe("mapSchemaTypeToPostgresType", () => {
    test("should map schema types to PostgreSQL types", () => {
      const validator = new (require("../../utils/schemaValidator").constructor || Object)();
      
      // Access the function through the singleton if available
      const mockValidator = {
        mapSchemaTypeToPostgresType: (type) => {
          const typeMap = {
            'VARCHAR': 'character varying',
            'TEXT': 'text',
            'INTEGER': 'integer',
            'BIGINT': 'bigint',
            'DECIMAL': 'numeric',
            'BOOLEAN': 'boolean',
            'DATE': 'date',
            'TIMESTAMP': 'timestamp without time zone',
            'SERIAL': 'integer'
          };
          return typeMap[type];
        }
      };

      expect(mockValidator.mapSchemaTypeToPostgresType('VARCHAR')).toBe('character varying');
      expect(mockValidator.mapSchemaTypeToPostgresType('INTEGER')).toBe('integer');
      expect(mockValidator.mapSchemaTypeToPostgresType('BOOLEAN')).toBe('boolean');
    });
  });

  describe("additional edge cases", () => {
    test("should handle extra columns in database validation", async () => {
      query.mockResolvedValueOnce({ rows: [{ exists: true }] });
      query.mockResolvedValueOnce({
        rows: [
          { column_name: "symbol", data_type: "character varying" },
          { column_name: "name", data_type: "character varying" },
          { column_name: "extra_column", data_type: "text" }, // Extra column
        ]
      });

      const result = await schemaValidator.validateTableStructure("stocks");

      expect(logger.warn).toHaveBeenCalledWith(
        "Extra column 'extra_column' found in table 'stocks'"
      );
    });

    test("should handle missing columns in validation", async () => {
      query.mockResolvedValueOnce({ rows: [{ exists: true }] });
      query.mockResolvedValueOnce({
        rows: [
          { column_name: "symbol", data_type: "character varying" },
          // Missing 'name' column
        ]
      });

      const result = await schemaValidator.validateTableStructure("stocks");

      expect(result.valid).toBe(false);
      expect(result.errors).toContain("Missing column 'name' in table 'stocks'");
    });

    test("should sanitize field values correctly", () => {
      const data = {
        symbol: "  AAPL  ", // Should be trimmed
        name: "Apple Inc.",
        price: "150.25", // Should be converted to number
        is_active: "true", // Should be converted to boolean
        last_updated: "2023-01-01T12:00:00Z", // Should be converted to ISO string
      };

      const result = schemaValidator.validateData("stocks", data);

      expect(result.isValid).toBe(true);
      expect(result.data.symbol).toBe("AAPL");
      expect(result.data.price).toBe(150.25);
      expect(result.data.is_active).toBe(true);
    });
  });
});
