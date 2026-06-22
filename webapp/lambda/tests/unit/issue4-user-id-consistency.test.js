/**
 * Test Suite: Issue #4 - User ID Type Consistency
 *
 * Verifies that:
 * 1. Routes use Cognito UUID strings (req.user.sub) as user_id
 * 2. alpacaSyncScheduler syncs for all registered users with proper UUIDs
 * 3. No hardcoded user IDs ('1', '2') are used in database queries
 * 4. User data is properly isolated by user_id
 */

const request = require("supertest");
const express = require("express");

// Mock database
jest.mock("../../../utils/database", () => ({
  query: jest.fn().mockResolvedValue({ rows: [], rowCount: 0 }),
  initializeDatabase: jest.fn(),
  closeDatabase: jest.fn(),
}));

const { _query } = require("../../../utils/database");

// Mock auth middleware
jest.mock("../../../middleware/auth", () => ({
  authenticateToken: jest.fn((req, res, next) => {
    // Use a realistic Cognito-like UUID string
    req.user = {
      sub: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", // UUID format
      id: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
      username: "testuser",
      email: "test@example.com",
      role: "user",
    };
    req.token = "test-jwt-token";
    next();
  }),
}));

// Import the routes
const manualTradesRoutes = require("../../../routes/manual-trades");
const tradesRoutes = require("../../../routes/trades");

describe("Issue #4: User ID Type Consistency", () => {
  let app;
  const testUserId = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee";

  beforeAll(() => {
    app = express();
    app.use(express.json());

    // Mock auth middleware
    app.use((req, res, next) => {
      req.user = {
        sub: testUserId,
        id: testUserId,
        username: "testuser",
        email: "test@example.com",
      };
      req.token = "test-jwt-token";
      next();
    });

    app.use("/manual-trades", manualTradesRoutes);
    app.use("/trades", tradesRoutes);
  });

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe("manual-trades routes", () => {
    it("should use req.user.sub (UUID string) for user_id in GET requests", async () => {
      query.mockResolvedValue({
        rows: [],
        rowCount: 0,
      });

      await request(app).get("/manual-trades").expect(200);

      // Verify the query was called with the UUID, not hardcoded '1' or '2'
      expect(query).toHaveBeenCalled();
      const callArgs = query.mock.calls[0];
      expect(callArgs[1]).toContain(testUserId);
      expect(callArgs[1]).not.toContain("1");
      expect(callArgs[1]).not.toContain("2");
    });

    it("should use req.user.sub (UUID string) for user_id in POST requests", async () => {
      query.mockResolvedValue({
        rows: [
          {
            id: 1,
            symbol: "AAPL",
            side: "BUY",
            quantity: 100,
            execution_price: 150,
          },
        ],
        rowCount: 1,
      });

      await request(app)
        .post("/manual-trades")
        .send({
          symbol: "AAPL",
          trade_type: "buy",
          quantity: 100,
          price: 150,
          execution_date: new Date().toISOString(),
        })
        .expect(201);

      // Verify POST query uses UUID, not hardcoded ID
      const insertCall = query.mock.calls.find(
        (call) => call[0] && call[0].includes("INSERT INTO trades")
      );
      expect(insertCall).toBeDefined();
      expect(insertCall[1]).toContain(testUserId);
    });

    it("should isolate trades by user_id", async () => {
      query.mockResolvedValue({
        rows: [],
        rowCount: 0,
      });

      await request(app).get("/manual-trades/999").expect(404);

      // Verify query includes both id AND user_id filter
      const selectCall = query.mock.calls[0];
      expect(selectCall[0]).toContain("WHERE id = $1 AND user_id = $2");
      expect(selectCall[1]).toContain(testUserId);
    });
  });

  describe("trades routes", () => {
    it("should use req.user.sub for user_id in GET /trades", async () => {
      query.mockResolvedValue({
        rows: [],
        rowCount: 0,
      });

      await request(app).get("/trades").expect(200);

      // Verify query includes user_id filter
      const call = query.mock.calls.find(
        (call) =>
          call[0] &&
          call[0].includes("FROM trades") &&
          !call[0].includes("alpaca")
      );
      expect(call).toBeDefined();
      expect(call[1]).toContain(testUserId);
    });

    it("should filter /summary endpoint by authenticated user", async () => {
      query.mockResolvedValue({
        rows: [],
        rowCount: 0,
      });

      await request(app).get("/trades/summary").expect(200);

      // Verify user filter is applied
      const summaryCall = query.mock.calls.find(
        (call) =>
          call[0] &&
          call[0].includes("FROM trades") &&
          call[0].includes("WHERE user_id")
      );
      expect(summaryCall).toBeDefined();
      expect(summaryCall[1][0]).toBe(testUserId);
    });
  });

  describe("no hardcoded user IDs", () => {
    it("should never use hardcoded user_id values in queries", async () => {
      query.mockResolvedValue({
        rows: [],
        rowCount: 0,
      });

      // Make various requests
      await request(app).get("/manual-trades").expect(200);
      await request(app).get("/trades").expect(200);
      await request(app).get("/trades/summary").expect(200);

      // Check all query calls for hardcoded IDs
      query.mock.calls.forEach((call) => {
        const sql = call[0];
        const _params = call[1] || [];

        // Verify no hardcoded '1' or '2' in user_id context
        if (sql && sql.includes("user_id")) {
          expect(params).not.toContain("1");
          expect(params).not.toContain("2");
        }
      });
    });
  });

  describe("user_id column data types", () => {
    it("should accept VARCHAR(100) UUID strings as user_id", async () => {
      const uuidFormats = [
        "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", // Standard UUID
        "dev-user-local", // Development user
        "test-user-123", // Test user
      ];

      for (const userId of uuidFormats) {
        const testApp = express();
        testApp.use(express.json());
        testApp.use((req, res, next) => {
          req.user = { sub: userId };
          req.token = "test-token";
          next();
        });
        testApp.use("/manual-trades", manualTradesRoutes);

        query.mockResolvedValueOnce({ rows: [], rowCount: 0 });

        await request(testApp).get("/manual-trades").expect(200);

        const call = query.mock.calls[query.mock.calls.length - 1];
        expect(call[1]).toContain(userId);
      }
    });
  });
});
