const request = require("supertest");
const express = require("express");

// Mock dependencies
jest.mock("../../utils/responseFormatter", () => ({
  validationError: jest.fn((errors) => ({
    response: {
      success: false,
      error: "Validation failed",
      details: errors,
    },
  })),
}));

// Import after mocking
const {
  createValidationMiddleware,
  validateBody,
  validateQuery,
  validationSchemas,
  commonValidations,
  sanitizeString,
  sanitizeNumber,
  sanitizeInteger,
  sanitizeArray,
  isValidEmail,
  isValidSymbol,
  isValidDate,
} = require("../../middleware/validation");

describe("Validation Middleware", () => {
  let app;

  beforeAll(() => {
    app = express();
    app.use(express.json());
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  describe("Sanitization Functions", () => {
    describe("sanitizeString", () => {
      it("should trim and limit string length", () => {
        expect(sanitizeString("  hello world  ")).toBe("hello world");
        expect(sanitizeString("a".repeat(150))).toHaveLength(100);
        expect(sanitizeString(123)).toBe("");
        expect(sanitizeString(null)).toBe("");
      });

      it("should respect custom maxLength", () => {
        expect(sanitizeString("hello world", 5)).toBe("hello");
        expect(sanitizeString("hi", 10)).toBe("hi");
      });
    });

    describe("sanitizeNumber", () => {
      it("should parse and validate numbers", () => {
        expect(sanitizeNumber("123.45")).toBe(123.45);
        expect(sanitizeNumber("invalid")).toBeNull();
        expect(sanitizeNumber("50", 0, 100)).toBe(50);
      });

      it("should enforce min and max constraints", () => {
        expect(sanitizeNumber("-10", 0, 100)).toBe(0);
        expect(sanitizeNumber("150", 0, 100)).toBe(100);
        expect(sanitizeNumber("50", null, null)).toBe(50);
      });
    });

    describe("sanitizeInteger", () => {
      it("should parse integers and enforce constraints", () => {
        expect(sanitizeInteger("42")).toBe(42);
        expect(sanitizeInteger("42.7")).toBe(42);
        expect(sanitizeInteger("invalid")).toBeNull();
        expect(sanitizeInteger("-5", 0, 100)).toBe(0);
        expect(sanitizeInteger("150", 0, 100)).toBe(100);
      });
    });

    describe("sanitizeArray", () => {
      it("should validate and limit array length", () => {
        expect(sanitizeArray([1, 2, 3])).toEqual([1, 2, 3]);
        expect(sanitizeArray("not array")).toEqual([]);
        expect(sanitizeArray(new Array(150).fill(1))).toHaveLength(100);
        expect(sanitizeArray([1, 2, 3], 2)).toEqual([1, 2]);
      });
    });
  });

  describe("Validation Functions", () => {
    describe("isValidEmail", () => {
      it("should validate email formats", () => {
        expect(isValidEmail("user@example.com")).toBe(true);
        expect(isValidEmail("test.email+tag@domain.co.uk")).toBe(true);
        expect(isValidEmail("invalid-email")).toBe(false);
        expect(isValidEmail("@example.com")).toBe(false);
        expect(isValidEmail("user@")).toBe(false);
        expect(isValidEmail("")).toBe(false);
      });
    });

    describe("isValidSymbol", () => {
      it("should validate stock symbols", () => {
        expect(isValidSymbol("AAPL")).toBe(true);
        expect(isValidSymbol("MSFT")).toBe(true);
        expect(isValidSymbol("BRK.B")).toBe(false); // Contains dot
        expect(isValidSymbol("aapl")).toBe(true); // Converts to uppercase internally
        expect(isValidSymbol("TOOLONGSTOCK")).toBe(false); // Too long
        expect(isValidSymbol("")).toBe(false);
        expect(isValidSymbol(123)).toBe(false);
      });
    });

    describe("isValidDate", () => {
      it("should validate date strings", () => {
        expect(isValidDate("2023-12-25")).toBe(true);
        expect(isValidDate("2023-02-29")).toBe(true); // JavaScript Date accepts this (creates valid date)
        expect(isValidDate("invalid-date")).toBe(false);
        expect(isValidDate("")).toBe(false);
      });
    });
  });

  describe("Validation Schemas", () => {
    describe("symbol schema", () => {
      it("should sanitize and validate symbols", () => {
        const schema = validationSchemas.symbol;
        expect(schema.sanitizer("  aapl  ")).toBe("AAPL");
        expect(schema.sanitizer("brk.b")).toBe("BRKB");
        expect(schema.validator("AAPL")).toBe(true);
        expect(schema.validator("TOOLONGSTOCK")).toBe(false);
      });
    });

    describe("symbols schema", () => {
      it("should handle comma-separated symbols", () => {
        const schema = validationSchemas.symbols;
        expect(schema.sanitizer("aapl,msft,googl")).toBe("AAPL,MSFT,GOOGL");
        expect(schema.sanitizer("  aapl , msft , googl  ")).toBe(
          "AAPL,MSFT,GOOGL"
        );
        expect(schema.validator("AAPL,MSFT")).toBe(true);
        expect(schema.validator("")).toBe(false);
      });

      it("should limit number of symbols", () => {
        const manySymbols = new Array(60).fill("AAPL").join(",");
        const sanitized = validationSchemas.symbols.sanitizer(manySymbols);
        expect(sanitized.split(",")).toHaveLength(50);
      });
    });

    describe("pagination schemas", () => {
      it("should validate limit and offset", () => {
        expect(validationSchemas.limit.sanitizer("25")).toBe(25);
        expect(validationSchemas.limit.sanitizer("2000")).toBe(1000); // Max limit
        expect(validationSchemas.limit.sanitizer("0")).toBe(1); // Min limit

        expect(validationSchemas.offset.sanitizer("10")).toBe(10);
        expect(validationSchemas.offset.sanitizer("-5")).toBe(0); // Min offset
      });
    });

    describe("date schema", () => {
      it("should sanitize and validate dates", () => {
        const schema = validationSchemas.date;
        expect(schema.sanitizer("2023-12-25")).toBe("2023-12-25");
        expect(schema.sanitizer("invalid")).toBeNull();
        expect(schema.validator("2023-12-25")).toBe(true);
        expect(schema.validator(null)).toBe(true); // Optional
      });
    });

    describe("sortBy schema", () => {
      it("should validate allowed sort fields", () => {
        const schema = validationSchemas.sortBy;
        expect(schema.validator("price")).toBe(true);
        expect(schema.validator("marketCap")).toBe(true);
        expect(schema.validator("invalidField")).toBe(false);
        expect(schema.validator("")).toBe(true); // Optional
      });
    });

    describe("sortOrder schema", () => {
      it("should sanitize and validate sort order", () => {
        const schema = validationSchemas.sortOrder;
        expect(schema.sanitizer("DESC")).toBe("desc");
        expect(schema.sanitizer("invalid")).toBe("asc");
        expect(schema.validator("asc")).toBe(true);
        expect(schema.validator("desc")).toBe(true);
        expect(schema.validator("invalid")).toBe(false);
      });
    });
  });

  describe("createValidationMiddleware", () => {
    it("should validate required fields", async () => {
      const middleware = createValidationMiddleware({
        symbol: validationSchemas.symbol,
      });

      app.get("/test-required", middleware, (req, res) => {
        res.json({ success: true, validated: req.validated });
      });

      // Missing required field
      await request(app).get("/test-required").expect(422);

      // Valid required field
      await request(app).get("/test-required?symbol=AAPL").expect(200);
    });

    it("should apply default values", async () => {
      const middleware = createValidationMiddleware({
        limit: validationSchemas.limit,
      });

      app.get("/test-defaults", middleware, (req, res) => {
        res.json({ validated: req.validated });
      });

      const response = await request(app).get("/test-defaults").expect(200);

      expect(response.body.validated.limit).toBe(50); // Default value
    });

    it("should sanitize input values", async () => {
      const middleware = createValidationMiddleware({
        symbol: validationSchemas.symbol,
      });

      app.get("/test-sanitize", middleware, (req, res) => {
        res.json({ validated: req.validated });
      });

      const response = await request(app)
        .get("/test-sanitize?symbol=  aapl  ")
        .expect(200);

      expect(response.body.validated.symbol).toBe("AAPL");
    });

    it("should handle validation failures", async () => {
      const middleware = createValidationMiddleware({
        symbol: validationSchemas.symbol,
      });

      app.get("/test-validation", middleware, (req, res) => {
        res.json({ success: true });
      });

      await request(app)
        .get("/test-validation?symbol=TOOLONGSTOCK")
        .expect(422);
    });

    it("should process multiple fields", async () => {
      const middleware = createValidationMiddleware({
        symbol: validationSchemas.symbol,
        limit: validationSchemas.limit,
        sortBy: validationSchemas.sortBy,
      });

      app.get("/test-multiple", middleware, (req, res) => {
        res.json({ validated: req.validated });
      });

      const response = await request(app)
        .get("/test-multiple?symbol=AAPL&limit=25&sortBy=price")
        .expect(200);

      expect(response.body.validated).toEqual({
        symbol: "AAPL",
        limit: 25,
        sortBy: "price",
      });
    });
  });

  describe("validateBody", () => {
    it("should validate request body", async () => {
      const schema = {
        symbol: {
          required: true,
          sanitizer: (value) => value.toUpperCase(),
          validator: (value) => /^[A-Z]{1,10}$/.test(value),
          errorMessage: "Invalid symbol",
        },
      };

      const middleware = validateBody(schema);
      app.post("/test-body", middleware, (req, res) => {
        res.json({ validatedBody: req.validatedBody });
      });

      // Valid body
      const response = await request(app)
        .post("/test-body")
        .send({ symbol: "aapl" })
        .expect(200);

      expect(response.body.validatedBody.symbol).toBe("AAPL");

      // Missing required field
      await request(app).post("/test-body").send({}).expect(422);

      // Invalid field
      await request(app)
        .post("/test-body")
        .send({ symbol: "TOOLONGSTOCK" })
        .expect(422);
    });
  });

  describe("validateQuery", () => {
    it("should validate query parameters", async () => {
      const schema = {
        limit: {
          required: false,
          sanitizer: (value) => parseInt(value),
          validator: (value) => value > 0 && value <= 100,
          default: 10,
        },
      };

      const middleware = validateQuery(schema);
      app.get("/test-query", middleware, (req, res) => {
        res.json({ validatedQuery: req.validatedQuery });
      });

      // No query param (should use default)
      let response = await request(app).get("/test-query").expect(200);
      expect(response.body.validatedQuery.limit).toBe(10);

      // Valid query param
      response = await request(app).get("/test-query?limit=25").expect(200);
      expect(response.body.validatedQuery.limit).toBe(25);

      // Invalid query param
      await request(app).get("/test-query?limit=200").expect(422);
    });
  });

  describe("Common Validations", () => {
    describe("pagination", () => {
      it("should validate pagination parameters", async () => {
        app.get(
          "/test-pagination",
          commonValidations.pagination,
          (req, res) => {
            res.json({ validated: req.validated });
          }
        );

        const response = await request(app)
          .get("/test-pagination?limit=25&offset=10")
          .expect(200);

        expect(response.body.validated).toEqual({
          limit: 25,
          offset: 10,
        });

        // Test defaults
        const defaultResponse = await request(app)
          .get("/test-pagination")
          .expect(200);

        expect(defaultResponse.body.validated).toEqual({
          limit: 50,
          offset: 0,
        });
      });
    });

    describe("symbolParam", () => {
      it("should validate single symbol parameter", async () => {
        app.get("/test-symbol", commonValidations.symbolParam, (req, res) => {
          res.json({ validated: req.validated });
        });

        const response = await request(app)
          .get("/test-symbol?symbol=aapl")
          .expect(200);

        expect(response.body.validated.symbol).toBe("AAPL");

        await request(app).get("/test-symbol").expect(422); // Missing required symbol
      });
    });

    describe("symbolsParam", () => {
      it("should validate multiple symbols parameter", async () => {
        app.get("/test-symbols", commonValidations.symbolsParam, (req, res) => {
          res.json({ validated: req.validated });
        });

        const response = await request(app)
          .get("/test-symbols?symbols=aapl,msft,googl")
          .expect(200);

        expect(response.body.validated.symbols).toBe("AAPL,MSFT,GOOGL");

        await request(app).get("/test-symbols").expect(422); // Missing required symbols
      });
    });

    describe("dateRange", () => {
      it("should validate date range parameters", async () => {
        app.get("/test-dates", commonValidations.dateRange, (req, res) => {
          res.json({ validated: req.validated });
        });

        const response = await request(app)
          .get("/test-dates?startDate=2023-01-01&endDate=2023-12-31")
          .expect(200);

        expect(response.body.validated).toEqual({
          startDate: "2023-01-01",
          endDate: "2023-12-31",
        });

        // Optional dates should work
        await request(app).get("/test-dates").expect(200);
      });
    });

    describe("screeningFilters", () => {
      it("should validate screening filter parameters", async () => {
        app.get(
          "/test-screening",
          commonValidations.screeningFilters,
          (req, res) => {
            res.json({ validated: req.validated });
          }
        );

        const response = await request(app)
          .get(
            "/test-screening?priceMin=10&priceMax=100&sector=Technology&sortBy=price&sortOrder=desc&limit=25"
          )
          .expect(200);

        expect(response.body.validated).toMatchObject({
          priceMin: 10,
          priceMax: 100,
          sector: "Technology",
          sortBy: "price",
          sortOrder: "desc",
          limit: 25,
          offset: 0, // Default
        });

        // Test with minimal parameters
        const minimalResponse = await request(app)
          .get("/test-screening")
          .expect(200);

        expect(minimalResponse.body.validated).toEqual({
          limit: 50,
          offset: 0,
          sortOrder: "asc",
        });
      });
    });
  });

  describe("Error Handling", () => {
    it("should return structured error responses", async () => {
      const middleware = createValidationMiddleware({
        symbol: validationSchemas.symbol,
        limit: validationSchemas.limit,
      });

      app.get("/test-errors", middleware, (req, res) => {
        res.json({ success: true });
      });

      const response = await request(app)
        .get("/test-errors?symbol=TOOLONGSTOCK&limit=5000")
        .expect(422);

      expect(response.body).toMatchObject({
        success: false,
        error: "Validation failed",
        details: expect.arrayContaining([
          expect.objectContaining({
            field: "symbol",
            code: "VALIDATION_FAILED",
          }),
        ]),
      });
    });
  });

  describe("Edge Cases", () => {
    it("should handle empty strings appropriately", async () => {
      const middleware = createValidationMiddleware({
        symbol: { ...validationSchemas.symbol, required: false },
      });

      app.get("/test-empty", middleware, (req, res) => {
        res.json({ validated: req.validated });
      });

      // Empty string should be treated as not provided
      const response = await request(app)
        .get("/test-empty?symbol=")
        .expect(200);

      expect(response.body.validated).toEqual({});
    });

    it("should handle null and undefined values", async () => {
      const schema = {
        optionalField: {
          required: false,
          sanitizer: (value) => (value ? value.toString() : null),
          validator: (value) => value === null || value.length > 0,
        },
      };

      const middleware = validateBody(schema);
      app.post("/test-null", middleware, (req, res) => {
        res.json({ validatedBody: req.validatedBody });
      });

      // Null value
      const response = await request(app)
        .post("/test-null")
        .send({ optionalField: null })
        .expect(200);

      expect(response.body.validatedBody).toEqual({});

      // Undefined (not provided)
      const response2 = await request(app)
        .post("/test-null")
        .send({})
        .expect(200);

      expect(response2.body.validatedBody).toEqual({});
    });
  });
});
