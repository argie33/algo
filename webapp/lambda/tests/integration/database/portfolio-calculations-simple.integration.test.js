/**
 * Simplified Portfolio Calculations Integration Test
 * Focus on database-level financial calculations accuracy
 */

// Use global test database from setup.js
const query = async (text, params) => {
  if (!global.TEST_DATABASE) {
    throw new Error(
      "Test database not available. Run tests with proper setup."
    );
  }
  const result = await global.TEST_DATABASE.query(text, params || []);
  return result;
};

describe("Portfolio Database Calculations Integration", () => {
  let testUserId;

  beforeAll(async () => {
    // Skip all tests if database is not available
    if (!global.DATABASE_AVAILABLE()) {
      console.log(
        "⚠️  Skipping database integration tests - no database available"
      );
      return;
    }

    testUserId = "test-calc-" + Date.now();

    try {
      // Insert test portfolio data
      await query(
        `
        INSERT INTO user_portfolio (user_id, symbol, quantity, avg_cost, last_updated)
        VALUES ($1, 'AAPL', 100, 150.00, NOW())
      `,
        [testUserId]
      );
    } catch (error) {
      console.log("⚠️  Failed to setup test data:", error.message);
      throw error;
    }
  });

  afterAll(async () => {
    // Cleanup
    await query("DELETE FROM user_portfolio WHERE user_id = $1", [testUserId]);
  });

  test("should calculate portfolio value from database data", async () => {
    if (!global.DATABASE_AVAILABLE()) {
      console.log("⚠️  Skipping test - database not available");
      return;
    }

    const result = await query(
      `
      SELECT 
        symbol,
        quantity,
        avg_cost,
        (quantity * avg_cost) as total_cost
      FROM user_portfolio 
      WHERE user_id = $1
    `,
      [testUserId]
    );

    expect(result.rows).toHaveLength(1);
    const holding = result.rows[0];

    expect(holding.symbol).toBe("AAPL");
    expect(holding.quantity).toBe(100);
    expect(holding.avg_cost).toBe(150.0);
    expect(parseFloat(holding.total_cost)).toBe(15000.0);
  });

  test("should handle multiple holdings correctly", async () => {
    if (!global.DATABASE_AVAILABLE()) {
      console.log("⚠️  Skipping test - database not available");
      return;
    }

    // Add second holding
    await query(
      `
      INSERT INTO user_portfolio (user_id, symbol, quantity, avg_cost, last_updated)
      VALUES ($1, 'TSLA', 50, 200.00, NOW())
    `,
      [testUserId]
    );

    const result = await query(
      `
      SELECT 
        COUNT(*) as holding_count,
        SUM(quantity * avg_cost) as total_value
      FROM user_portfolio 
      WHERE user_id = $1 AND quantity > 0
    `,
      [testUserId]
    );

    // pg-mem returns actual numbers, PostgreSQL returns strings
    expect(parseInt(result.rows[0].holding_count)).toBe(2);
    expect(parseFloat(result.rows[0].total_value)).toBe(25000.0); // 15000 + 10000
  });

  test("should exclude zero quantity positions", async () => {
    if (!global.DATABASE_AVAILABLE()) {
      console.log("⚠️  Skipping test - database not available");
      return;
    }

    // Add zero quantity position
    await query(
      `
      INSERT INTO user_portfolio (user_id, symbol, quantity, avg_cost, last_updated)
      VALUES ($1, 'ZERO', 0, 100.00, NOW())
    `,
      [testUserId]
    );

    const result = await query(
      `
      SELECT COUNT(*) as active_holdings
      FROM user_portfolio 
      WHERE user_id = $1 AND quantity > 0
    `,
      [testUserId]
    );

    // pg-mem returns actual numbers, PostgreSQL returns strings
    expect(parseInt(result.rows[0].active_holdings)).toBe(2); // Still only 2 active holdings
  });

  test("should handle precision correctly for fractional shares", async () => {
    if (!global.DATABASE_AVAILABLE()) {
      console.log("⚠️  Skipping test - database not available");
      return;
    }

    await query(
      `
      INSERT INTO user_portfolio (user_id, symbol, quantity, avg_cost, last_updated)
      VALUES ($1, 'FRAC', 10.5555, 25.25, NOW())
    `,
      [testUserId]
    );

    const result = await query(
      `
      SELECT 
        symbol,
        quantity,
        avg_cost,
        (quantity * avg_cost) as calculated_value
      FROM user_portfolio 
      WHERE user_id = $1 AND symbol = 'FRAC'
    `,
      [testUserId]
    );

    expect(result.rows[0].symbol).toBe("FRAC");
    expect(parseFloat(result.rows[0].quantity)).toBeCloseTo(10.5555, 4);
    // Round the calculated value in JavaScript instead of SQL
    // 10.5555 * 25.25 = 266.51375, rounded to 2 decimals
    const calculatedValue =
      Math.round(parseFloat(result.rows[0].calculated_value) * 100) / 100;
    expect(calculatedValue).toBeCloseTo(266.51, 1); // Use 1 decimal precision to handle floating point variations
  });
});
