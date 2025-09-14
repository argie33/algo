const express = require("express");
const request = require("supertest");
const {
  createValidationMiddleware,
  validateBody,
  validateQuery,
  validationSchemas,
  commonValidations,
  sanitizers,
  sanitizeString,
  sanitizeNumber,
  sanitizeInteger,
  sanitizeArray,
  isValidEmail,
  isValidSymbol,
  isValidDate,
} = require("../../../middleware/validation");

const app = express();
app.use(express.json());

describe("Validation Middleware", () => {
  describe("Sanitization Functions", () => {
    describe("sanitizeString", () => {
      test("should sanitize string correctly", () => {
        expect(sanitizeString("  test string  ")).toBe("test string");
        expect(sanitizeString("  very long string that should be truncated  ", 10)).toBe("very long ");
        expect(sanitizeString(123)).toBe("");
        expect(sanitizeString(null)).toBe("");
      });
    });

    describe("sanitizeNumber", () => {
      test("should sanitize number correctly", () => {
        expect(sanitizeNumber("123.45")).toBe(123.45);
        expect(sanitizeNumber("invalid")).toBeNull();
        expect(sanitizeNumber("5", 10, 20)).toBe(10);
        expect(sanitizeNumber("25", 10, 20)).toBe(20);
        expect(sanitizeNumber("15", 10, 20)).toBe(15);
      });
    });

    describe("sanitizeInteger", () => {
      test("should sanitize integer correctly", () => {
        expect(sanitizeInteger("123")).toBe(123);
        expect(sanitizeInteger("123.45")).toBe(123);
        expect(sanitizeInteger("invalid")).toBeNull();
        expect(sanitizeInteger("5", 10, 20)).toBe(10);
        expect(sanitizeInteger("25", 10, 20)).toBe(20);
      });
    });

    describe("sanitizeArray", () => {
      test("should sanitize array correctly", () => {
        expect(sanitizeArray([1, 2, 3])).toEqual([1, 2, 3]);
        expect(sanitizeArray("not array")).toEqual([]);
        expect(sanitizeArray([1, 2, 3, 4, 5], 3)).toEqual([1, 2, 3]);
      });
    });
  });

  describe("Validation Functions", () => {
    describe("isValidEmail", () => {
      test("should validate email correctly", () => {
        expect(isValidEmail("test@example.com")).toBe(true);
        expect(isValidEmail("invalid.email")).toBe(false);
        expect(isValidEmail("test@")).toBe(false);
        expect(isValidEmail("@example.com")).toBe(false);
      });
    });

    describe("isValidSymbol", () => {
      test("should validate stock symbol correctly", () => {
        expect(isValidSymbol("AAPL")).toBe(true);
        expect(isValidSymbol("MSFT")).toBe(true);
        expect(isValidSymbol("ABC123")).toBe(false);
        expect(isValidSymbol("a")).toBe(true); // Single letter symbols are valid (e.g., "F" for Ford)
        expect(isValidSymbol("TOOLONGSTOCK")).toBe(false);
        expect(isValidSymbol(123)).toBe(false);
      });
    });

    describe("isValidDate", () => {
      test("should validate date correctly", () => {
        expect(isValidDate("2023-01-01")).toBe(true);
        expect(isValidDate("2023-12-31")).toBe(true);
        expect(isValidDate("invalid-date")).toBe(false);
        expect(isValidDate("2023-13-01")).toBe(false);
      });
    });
  });

  describe("Sanitizers Object", () => {
    describe("string sanitizer", () => {
      test("should sanitize with options", () => {
        expect(sanitizers.string("  test  ")).toBe("test");
        expect(sanitizers.string("  long string  ", { maxLength: 5 })).toBe("long ");
        expect(sanitizers.string("test123!", { alphaNumOnly: true })).toBe("test123");
        expect(sanitizers.string("<script>", { escapeHTML: true })).toBe("&lt;script&gt;");
      });
    });
  });

  describe("Validation Schemas", () => {
    describe("symbol schema", () => {
      test("should sanitize and validate symbol", () => {
        const schema = validationSchemas.symbol;
        expect(schema.sanitizer("  aapl  ")).toBe("AAPL");
        expect(schema.sanitizer("aapl-123")).toBe("AAPL123");
        expect(schema.validator("AAPL")).toBe(true);
        expect(schema.validator("TOOLONGSTOCK")).toBe(false);
      });
    });

    describe("symbols schema", () => {
      test("should sanitize and validate multiple symbols", () => {
        const schema = validationSchemas.symbols;
        expect(schema.sanitizer("aapl,msft,googl")).toBe("AAPL,MSFT,GOOGL");
        expect(schema.sanitizer("  aapl , msft , googl  ")).toBe("AAPL,MSFT,GOOGL");
        expect(schema.validator("AAPL,MSFT,GOOGL")).toBe(true);
        expect(schema.validator("AAPL,TOOLONGSTOCK")).toBe(false);
      });
    });

    describe("limit schema", () => {
      test("should sanitize and validate limit", () => {
        const schema = validationSchemas.limit;
        expect(schema.sanitizer("50")).toBe(50);
        expect(schema.sanitizer("0")).toBe(1);
        expect(schema.sanitizer("2000")).toBe(1000);
        expect(schema.validator(50)).toBe(true);
        expect(schema.validator(0)).toBe(false);
        expect(schema.validator(2000)).toBe(false);
      });
    });
  });

  describe("createValidationMiddleware", () => {
    test("should validate required fields", async () => {
      app.get("/test-required", createValidationMiddleware({
        symbol: validationSchemas.symbol,
      }), (req, res) => {
        res.json({ success: true, validated: req.validated });
      });

      const response = await request(app)
        .get("/test-required");

      expect(response.status).toBe(422);
      expect(response.body.errors).toBeDefined();
      expect(response.body.errors[0].code).toBe("REQUIRED_FIELD_MISSING");
    });

    test("should validate and sanitize valid input", async () => {
      app.get("/test-valid", createValidationMiddleware({
        symbol: validationSchemas.symbol,
        limit: validationSchemas.limit,
      }), (req, res) => {
        res.json({ success: true, validated: req.validated });
      });

      const response = await request(app)
        .get("/test-valid?symbol=aapl&limit=25");

      expect(response.status).toBe(200);
      expect(response.body.validated.symbol).toBe("AAPL");
      expect(response.body.validated.limit).toBe(25);
    });

    test("should apply default values", async () => {
      app.get("/test-defaults", createValidationMiddleware({
        limit: validationSchemas.limit,
        sortOrder: validationSchemas.sortOrder,
      }), (req, res) => {
        res.json({ success: true, validated: req.validated });
      });

      const response = await request(app)
        .get("/test-defaults");

      expect(response.status).toBe(200);
      expect(response.body.validated.limit).toBe(50);
      expect(response.body.validated.sortOrder).toBe("asc");
    });

    test("should handle validation errors", async () => {
      app.get("/test-invalid", createValidationMiddleware({
        symbol: validationSchemas.symbol,
      }), (req, res) => {
        res.json({ success: true, validated: req.validated });
      });

      const response = await request(app)
        .get("/test-invalid?symbol=TOOLONGSTOCK");

      expect(response.status).toBe(422);
      expect(response.body.errors).toBeDefined();
      expect(response.body.errors[0].code).toBe("VALIDATION_FAILED");
    });
  });

  describe("validateBody", () => {
    test("should validate request body", async () => {
      app.post("/test-body", validateBody({
        symbol: {
          required: true,
          sanitizer: (value) => value.toUpperCase(),
          validator: (value) => /^[A-Z]{1,10}$/.test(value),
          errorMessage: "Invalid symbol format"
        }
      }), (req, res) => {
        res.json({ success: true, validated: req.validatedBody });
      });

      const response = await request(app)
        .post("/test-body")
        .send({ symbol: "aapl" });

      expect(response.status).toBe(200);
      expect(response.body.validated.symbol).toBe("AAPL");
    });

    test("should handle body validation errors", async () => {
      app.post("/test-body-error", validateBody({
        symbol: {
          required: true,
          validator: (value) => /^[A-Z]{1,5}$/.test(value),
          errorMessage: "Symbol must be 1-5 uppercase letters"
        }
      }), (req, res) => {
        res.json({ success: true });
      });

      const response = await request(app)
        .post("/test-body-error")
        .send({ symbol: "TOOLONG" });

      expect(response.status).toBe(422);
      expect(response.body.errors[0].message).toBe("Symbol must be 1-5 uppercase letters");
    });
  });

  describe("validateQuery", () => {
    test("should validate query parameters", async () => {
      app.get("/test-query", validateQuery({
        limit: {
          required: false,
          sanitizer: (value) => parseInt(value),
          validator: (value) => value > 0 && value <= 100,
          default: 10
        }
      }), (req, res) => {
        res.json({ success: true, validated: req.validatedQuery });
      });

      const response = await request(app)
        .get("/test-query?limit=50");

      expect(response.status).toBe(200);
      expect(response.body.validated.limit).toBe(50);
    });

    test("should apply default values in query validation", async () => {
      app.get("/test-query-default", validateQuery({
        limit: {
          required: false,
          default: 25
        }
      }), (req, res) => {
        res.json({ success: true, validated: req.validatedQuery });
      });

      const response = await request(app)
        .get("/test-query-default");

      expect(response.status).toBe(200);
      expect(response.body.validated.limit).toBe(25);
    });

    test("should handle query validation errors", async () => {
      app.get("/test-query-error", validateQuery({
        limit: {
          required: true,
          validator: (value) => parseInt(value) > 0,
          errorMessage: "Limit must be positive"
        }
      }), (req, res) => {
        res.json({ success: true });
      });

      const response = await request(app)
        .get("/test-query-error");

      expect(response.status).toBe(422);
      expect(response.body.errors[0].code).toBe("REQUIRED_FIELD_MISSING");
    });
  });

  describe("Common Validations", () => {
    describe("pagination", () => {
      test("should validate pagination parameters", async () => {
        app.get("/test-pagination", commonValidations.pagination, (req, res) => {
          res.json({ success: true, validated: req.validated });
        });

        const response = await request(app)
          .get("/test-pagination?limit=25&offset=50");

        expect(response.status).toBe(200);
        expect(response.body.validated.limit).toBe(25);
        expect(response.body.validated.offset).toBe(50);
      });

      test("should apply pagination defaults", async () => {
        app.get("/test-pagination-defaults", commonValidations.pagination, (req, res) => {
          res.json({ success: true, validated: req.validated });
        });

        const response = await request(app)
          .get("/test-pagination-defaults");

        expect(response.status).toBe(200);
        expect(response.body.validated.limit).toBe(50);
        expect(response.body.validated.offset).toBe(0);
      });
    });

    describe("symbolParam", () => {
      test("should validate symbol parameter", async () => {
        app.get("/test-symbol/:symbol", commonValidations.symbolParam, (req, res) => {
          res.json({ success: true, validated: req.validated });
        });

        const response = await request(app)
          .get("/test-symbol/AAPL");

        expect(response.status).toBe(200);
        expect(response.body.validated.symbol).toBe("AAPL");
      });
    });

    describe("screeningFilters", () => {
      test("should validate screening filters", async () => {
        app.get("/test-screening", commonValidations.screeningFilters, (req, res) => {
          res.json({ success: true, validated: req.validated });
        });

        const response = await request(app)
          .get("/test-screening?priceMin=10&priceMax=100&marketCapMin=1000000&sector=Technology");

        expect(response.status).toBe(200);
        expect(response.body.validated.priceMin).toBe(10);
        expect(response.body.validated.priceMax).toBe(100);
        expect(response.body.validated.marketCapMin).toBe(1000000);
        expect(response.body.validated.sector).toBe("Technology");
      });
    });

    describe("dateRange", () => {
      test("should validate date range", async () => {
        app.get("/test-dates", commonValidations.dateRange, (req, res) => {
          res.json({ success: true, validated: req.validated });
        });

        const response = await request(app)
          .get("/test-dates?startDate=2023-01-01&endDate=2023-12-31");

        expect(response.status).toBe(200);
        expect(response.body.validated.startDate).toBe("2023-01-01");
        expect(response.body.validated.endDate).toBe("2023-12-31");
      });
    });
  });

  describe("Complex Validation Scenarios", () => {
    test("should handle multiple validation errors", async () => {
      app.get("/test-multiple-errors", createValidationMiddleware({
        symbol: validationSchemas.symbol,
        limit: {
          required: true,
          type: "number",
          validator: (value) => value >= 1 && value <= 1000,
          errorMessage: "Limit must be between 1 and 1000",
        },
      }), (req, res) => {
        res.json({ success: true });
      });

      const response = await request(app)
        .get("/test-multiple-errors?symbol=TOOLONGSTOCK&limit=5000");

      expect(response.status).toBe(422);
      expect(response.body.errors).toHaveLength(2);
      expect(response.body.errors[0].field).toBe("symbol");
      expect(response.body.errors[1].field).toBe("limit");
    });

    test("should handle mixed query and params validation", async () => {
      app.get("/test-mixed/:symbol", createValidationMiddleware({
        symbol: validationSchemas.symbol,
        limit: validationSchemas.limit,
      }), (req, res) => {
        res.json({ success: true, validated: req.validated });
      });

      const response = await request(app)
        .get("/test-mixed/AAPL?limit=25");

      expect(response.status).toBe(200);
      expect(response.body.validated.symbol).toBe("AAPL");
      expect(response.body.validated.limit).toBe(25);
    });

    test("should sanitize dangerous input", async () => {
      app.get("/test-sanitize", createValidationMiddleware({
        symbol: validationSchemas.symbol,
      }), (req, res) => {
        res.json({ success: true, validated: req.validated });
      });

      const response = await request(app)
        .get("/test-sanitize?symbol=aa<script>pl");

      expect(response.status).toBe(200);
      expect(response.body.validated.symbol).toBe("AASCRIPTPL");
    });

    test("should handle edge cases", async () => {
      app.get("/test-edge-cases", createValidationMiddleware({
        sortBy: validationSchemas.sortBy,
        timeframe: validationSchemas.timeframe,
      }), (req, res) => {
        res.json({ success: true, validated: req.validated });
      });

      const response = await request(app)
        .get("/test-edge-cases?sortBy=price&timeframe=1Day");

      expect(response.status).toBe(200);
      expect(response.body.validated.sortBy).toBe("price");
      expect(response.body.validated.timeframe).toBe("1Day");
    });

    test("should reject invalid sort fields", async () => {
      app.get("/test-invalid-sort", createValidationMiddleware({
        sortBy: validationSchemas.sortBy,
      }), (req, res) => {
        res.json({ success: true });
      });

      const response = await request(app)
        .get("/test-invalid-sort?sortBy=invalidField");

      expect(response.status).toBe(422);
      expect(response.body.errors[0].message).toBe("Invalid sort field");
    });

    test("should reject invalid timeframes", async () => {
      app.get("/test-invalid-timeframe", createValidationMiddleware({
        timeframe: validationSchemas.timeframe,
      }), (req, res) => {
        res.json({ success: true });
      });

      const response = await request(app)
        .get("/test-invalid-timeframe?timeframe=InvalidTimeframe");

      expect(response.status).toBe(422);
      expect(response.body.errors[0].message).toBe("Invalid timeframe");
    });
  });
});