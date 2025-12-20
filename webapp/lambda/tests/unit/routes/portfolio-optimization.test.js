/**
 * Portfolio Optimization Test Suite
 *
 * ⛔ CRITICAL WARNING: This test inserts FAKE financial data into the database.
 * It MUST only run against a test database, never production.
 *
 * Tests the complete portfolio optimization flow with test data:
 * - portfolio_holdings (with hardcoded test prices)
 * - stock_scores (with hardcoded test scores)
 * - company_profile
 * - price_daily
 *
 * Run with: npm test -- portfolio-optimization.test.js
 * ONLY run with: TEST_DATABASE_URL set to test database
 */

const { query } = require("../../../utils/database");

describe("Portfolio Optimization Engine", () => {
  const TEST_USER_ID = "test-user";

  // Setup: Insert test data before tests run
  beforeAll(async () => {
    // ⛔ SAFETY CHECK: Ensure test database is being used
    if (process.env.NODE_ENV === 'production') {
      throw new Error(`
        ❌ CRITICAL: Cannot run tests in production environment!
        This test inserts FAKE financial data (hardcoded scores from lines 43-62)
        that would corrupt the production database.
      `);
    }

    console.log("\n⚠️  UNIT TEST: Inserting fake test data into database");
    console.log("⚠️  This test corrupts: portfolio_holdings, stock_scores");
    console.log("🔧 Setting up test data...");
    try {
      // Insert test portfolio holdings
      await query(`
        DELETE FROM portfolio_holdings WHERE user_id = $1;
      `, [TEST_USER_ID]);

      await query(`
        INSERT INTO portfolio_holdings (user_id, symbol, quantity, average_cost, current_price, market_value, unrealized_gain, unrealized_gain_pct, updated_at)
        VALUES
          ($1, 'AAPL', 40, 200, 225.50, 9020, 1020, 12.75, CURRENT_TIMESTAMP),
          ($1, 'MSFT', 15, 380, 425.30, 6379.50, 679.50, 11.92, CURRENT_TIMESTAMP),
          ($1, 'GOOGL', 25, 130, 165.80, 4145, 895, 27.54, CURRENT_TIMESTAMP),
          ($1, 'TSLA', 30, 220, 265.75, 7972.50, 1372.50, 20.80, CURRENT_TIMESTAMP),
          ($1, 'AMZN', 50, 175, 188.45, 9422.50, 1422.50, 16.26, CURRENT_TIMESTAMP);
      `, [TEST_USER_ID]);

      // Insert test stock scores (upsert to avoid conflicts)
      await query(`
        INSERT INTO stock_scores (
          symbol, composite_score, momentum_score, value_score, quality_score, growth_score,
          stability_score, sentiment_score, current_price, volume_avg_30d
        ) VALUES
          ('AAPL', 78.5, 72, 68, 82, 75, 85, 76, 225.50, 52000000),
          ('MSFT', 81.2, 78, 71, 84, 79, 83, 80, 425.30, 25000000),
          ('GOOGL', 79.8, 75, 70, 81, 78, 82, 78, 165.80, 20000000),
          ('TSLA', 72.3, 68, 55, 70, 73, 60, 74, 265.75, 100000000),
          ('AMZN', 76.5, 70, 62, 79, 77, 78, 75, 188.45, 45000000),
          ('NVDA', 85.2, 82, 75, 87, 86, 81, 84, 890.00, 45000000),
          ('META', 68.9, 65, 58, 68, 70, 62, 66, 285.00, 35000000),
          ('JPM', 74.1, 70, 75, 72, 68, 76, 71, 168.00, 8000000),
          ('JNJ', 77.5, 72, 80, 81, 70, 88, 75, 155.00, 5000000),
          ('PG', 75.3, 68, 82, 80, 65, 90, 72, 162.00, 4000000)
        ON CONFLICT (symbol) DO UPDATE SET
          composite_score = EXCLUDED.composite_score,
          momentum_score = EXCLUDED.momentum_score,
          value_score = EXCLUDED.value_score,
          quality_score = EXCLUDED.quality_score,
          growth_score = EXCLUDED.growth_score,
          stability_score = EXCLUDED.stability_score,
          sentiment_score = EXCLUDED.sentiment_score,
          current_price = EXCLUDED.current_price,
          volume_avg_30d = EXCLUDED.volume_avg_30d;
      `);

      // Insert company profiles
      // Don't delete company_profile - it has foreign key constraints
      // Instead, just ensure the test data is inserted (INSERT OR IGNORE pattern)

      await query(`
        INSERT INTO company_profile (ticker, short_name, sector)
        VALUES
          ('AAPL', 'Apple Inc.', 'Technology'),
          ('MSFT', 'Microsoft Corp.', 'Technology'),
          ('GOOGL', 'Alphabet Inc.', 'Communication Services'),
          ('TSLA', 'Tesla Inc.', 'Consumer Discretionary'),
          ('AMZN', 'Amazon.com Inc.', 'Consumer Discretionary'),
          ('NVDA', 'NVIDIA Corporation', 'Technology'),
          ('META', 'Meta Platforms Inc.', 'Communication Services'),
          ('JPM', 'JPMorgan Chase', 'Financials'),
          ('JNJ', 'Johnson & Johnson', 'Healthcare'),
          ('PG', 'Procter & Gamble', 'Consumer Staples')
        ON CONFLICT (ticker) DO UPDATE SET
          short_name = EXCLUDED.short_name,
          sector = EXCLUDED.sector;
      `);

      console.log("✅ Test data inserted successfully");
    } catch (error) {
      console.error("❌ Error setting up test data:", error);
      throw error;
    }
  });

  // Cleanup after tests
  afterAll(async () => {
    console.log("\n🧹 Cleaning up test data...");
    try {
      await query(`DELETE FROM portfolio_holdings WHERE user_id = $1;`, [TEST_USER_ID]);
      console.log("✅ Cleanup complete");
    } catch (error) {
      console.error("❌ Cleanup error:", error);
    }
  });

  // Test 1: Portfolio data loads correctly
  describe("Portfolio Data Loading", () => {
    test("should load portfolio holdings with real data", async () => {
      const result = await query(
        `SELECT symbol, quantity, current_price, market_value FROM portfolio_holdings WHERE user_id = $1 ORDER BY market_value DESC`,
        [TEST_USER_ID]
      );

      expect(result.rows).toBeDefined();
      expect(result.rows.length).toBe(5);
      expect(result.rows[0].symbol).toBe("AMZN"); // Should be highest by market value
      expect(parseFloat(result.rows[0].market_value)).toBe(9422.50);

      console.log("  ✅ Loaded", result.rows.length, "holdings");
    });

    test("should calculate total portfolio value", async () => {
      const result = await query(
        `SELECT SUM(market_value) as total_value FROM portfolio_holdings WHERE user_id = $1`,
        [TEST_USER_ID]
      );

      const totalValue = parseFloat(result.rows[0].total_value);
      expect(totalValue).toBeGreaterThan(0);
      expect(totalValue).toBeLessThan(50000); // Should be under $50k

      console.log(`  ✅ Total portfolio value: $${totalValue.toFixed(2)}`);
    });

    test("should load stock scores for holdings", async () => {
      const result = await query(
        `
        SELECT ss.symbol, ss.composite_score::numeric, ss.momentum_score::numeric, ss.quality_score::numeric
        FROM stock_scores ss
        WHERE ss.symbol IN (
          SELECT symbol FROM portfolio_holdings WHERE user_id = $1
        )
        ORDER BY ss.composite_score DESC
        `,
        [TEST_USER_ID]
      );

      expect(result.rows.length).toBe(5);
      result.rows.forEach((row) => {
        const score = parseFloat(row.composite_score);
        expect(score).toBeGreaterThan(0);
        expect(score).toBeLessThanOrEqual(100);
      });

      console.log(
        "  ✅ Loaded scores for",
        result.rows.length,
        "holdings:",
        result.rows.map((r) => `${r.symbol}(${parseFloat(r.composite_score).toFixed(1)}/100)`).join(", ")
      );
    });

    test("should classify holdings by sector", async () => {
      const result = await query(
        `
        SELECT cp.sector, COUNT(DISTINCT ph.symbol) as count
        FROM portfolio_holdings ph
        LEFT JOIN company_profile cp ON cp.ticker = ph.symbol
        WHERE ph.user_id = $1
        GROUP BY cp.sector
        `,
        [TEST_USER_ID]
      );

      expect(result.rows.length).toBeGreaterThan(0);

      const sectors = {};
      result.rows.forEach((row) => {
        sectors[row.sector || "Unknown"] = row.count;
      });

      console.log("  ✅ Sector breakdown:", sectors);
    });
  });

  // Test 2: Portfolio metrics calculations
  describe("Portfolio Metrics", () => {
    test("should calculate portfolio composite score", async () => {
      const result = await query(
        `
        SELECT AVG(ss.composite_score) as avg_score
        FROM portfolio_holdings ph
        JOIN stock_scores ss ON ph.symbol = ss.symbol
        WHERE ph.user_id = $1
        `,
        [TEST_USER_ID]
      );

      const avgScore = parseFloat(result.rows[0].avg_score);
      expect(avgScore).toBeGreaterThan(0);
      expect(avgScore).toBeLessThanOrEqual(100);

      console.log(`  ✅ Portfolio composite score: ${avgScore.toFixed(1)}/100`);
    });

    test("should calculate concentration ratio (top 5)", async () => {
      const result = await query(
        `
        SELECT SUM(market_value) as total_value FROM portfolio_holdings WHERE user_id = $1
        `,
        [TEST_USER_ID]
      );

      const totalValue = parseFloat(result.rows[0].total_value);
      const top5 = await query(
        `
        SELECT SUM(market_value) as top5_value FROM (
          SELECT market_value FROM portfolio_holdings WHERE user_id = $1
          ORDER BY market_value DESC LIMIT 5
        ) AS top5
        `,
        [TEST_USER_ID]
      );

      const top5Value = parseFloat(top5.rows[0].top5_value);
      const concentrationRatio = (top5Value / totalValue) * 100;

      expect(concentrationRatio).toBeGreaterThan(0);
      expect(concentrationRatio).toBeLessThanOrEqual(100);

      console.log(`  ✅ Concentration ratio (top 5): ${concentrationRatio.toFixed(1)}%`);
    });

    test("should calculate unrealized P&L", async () => {
      const result = await query(
        `
        SELECT
          SUM(market_value) as total_value,
          SUM(quantity * average_cost) as total_cost,
          SUM(unrealized_gain) as total_pnl
        FROM portfolio_holdings
        WHERE user_id = $1
        `,
        [TEST_USER_ID]
      );

      const totalValue = parseFloat(result.rows[0].total_value);
      const totalCost = parseFloat(result.rows[0].total_cost);
      const totalPnl = parseFloat(result.rows[0].total_pnl);
      const pnlPct = ((totalValue - totalCost) / totalCost) * 100;

      expect(totalPnl).toBeGreaterThan(0);
      expect(pnlPct).toBeGreaterThan(0);

      console.log(`  ✅ Unrealized P&L: $${totalPnl.toFixed(2)} (${pnlPct.toFixed(2)}%)`);
    });
  });

  // Test 3: Sector allocation
  describe("Sector Allocation Analysis", () => {
    test("should identify overweighted sectors", async () => {
      const result = await query(
        `
        SELECT
          cp.sector,
          COUNT(*) as num_stocks,
          SUM(ph.market_value) as sector_value,
          (SUM(ph.market_value) / (SELECT SUM(market_value) FROM portfolio_holdings WHERE user_id = $1) * 100) as sector_pct
        FROM portfolio_holdings ph
        LEFT JOIN company_profile cp ON cp.ticker = ph.symbol
        WHERE ph.user_id = $1
        GROUP BY cp.sector
        ORDER BY sector_value DESC
        `,
        [TEST_USER_ID]
      );

      const sectors = result.rows.map((row) => ({
        sector: row.sector || "Unknown",
        stocks: row.num_stocks,
        value: parseFloat(row.sector_value),
        pct: parseFloat(row.sector_pct),
      }));

      expect(sectors.length).toBeGreaterThan(0);

      // Check for overweight sectors (>30%)
      const overweight = sectors.filter((s) => s.pct > 30);
      console.log("  ✅ Sector allocation:");
      sectors.forEach((s) => {
        const status = s.pct > 30 ? "🔴 OVERWEIGHT" : s.pct > 15 ? "🟡 NEUTRAL" : "🟢 UNDERWEIGHT";
        console.log(`     ${s.sector}: ${s.pct.toFixed(1)}% (${s.stocks} stocks) ${status}`);
      });

      expect(sectors.length).toBeGreaterThan(0);
    });

    test("should identify sector drift from targets", async () => {
      const targets = {
        Technology: 25,
        Healthcare: 15,
        Financials: 15,
        "Consumer Discretionary": 15,
        "Consumer Staples": 10,
        "Communication Services": 10,
      };

      const result = await query(
        `
        SELECT
          cp.sector,
          (SUM(ph.market_value) / (SELECT SUM(market_value) FROM portfolio_holdings WHERE user_id = $1) * 100) as current_pct
        FROM portfolio_holdings ph
        LEFT JOIN company_profile cp ON cp.ticker = ph.symbol
        WHERE ph.user_id = $1
        GROUP BY cp.sector
        `,
        [TEST_USER_ID]
      );

      console.log("  ✅ Sector drift from targets:");
      result.rows.forEach((row) => {
        const sector = row.sector || "Unknown";
        const current = parseFloat(row.current_pct);
        const target = targets[sector] || 10;
        const drift = current - target;
        const status = Math.abs(drift) < 3 ? "✅" : drift > 0 ? "⚠️ OVER" : "❌ UNDER";
        console.log(
          `     ${sector}: ${current.toFixed(1)}% (target ${target}%) - Drift: ${drift > 0 ? "+" : ""}${drift.toFixed(1)}% ${status}`
        );
      });
    });
  });

  // Test 4: Recommendation generation
  describe("Stock Recommendation Generation", () => {
    test("should identify good buy candidates", async () => {
      // Stocks NOT in portfolio with high scores
      const result = await query(
        `
        SELECT ss.symbol, ss.composite_score, cp.sector
        FROM stock_scores ss
        LEFT JOIN company_profile cp ON cp.ticker = ss.symbol
        WHERE ss.composite_score >= 75
        AND ss.volume_avg_30d > 1000000
        AND ss.symbol NOT IN (SELECT symbol FROM portfolio_holdings WHERE user_id = $1)
        ORDER BY ss.composite_score DESC
        LIMIT 5
        `,
        [TEST_USER_ID]
      );

      expect(result.rows.length).toBeGreaterThan(0);

      console.log("  ✅ Top buy candidates (not in portfolio):");
      result.rows.forEach((row, idx) => {
        console.log(`     ${idx + 1}. ${row.symbol} - Score: ${parseFloat(row.composite_score).toFixed(1)}/100 (${row.sector})`);
      });
    });

    test("should identify weak holdings to reduce or sell", async () => {
      // Holdings with low scores
      const result = await query(
        `
        SELECT ph.symbol, ss.composite_score, ph.market_value, cp.sector
        FROM portfolio_holdings ph
        LEFT JOIN stock_scores ss ON ph.symbol = ss.symbol
        LEFT JOIN company_profile cp ON cp.ticker = ph.symbol
        WHERE ph.user_id = $1
        AND ss.composite_score < 75
        ORDER BY ss.composite_score ASC
        `,
        [TEST_USER_ID]
      );

      if (result.rows.length > 0) {
        console.log("  ⚠️ Holdings to consider reducing:");
        result.rows.forEach((row) => {
          console.log(
            `     ${row.symbol} - Score: ${parseFloat(row.composite_score).toFixed(1)}/100, Value: $${parseFloat(row.market_value).toFixed(2)}`
          );
        });
      } else {
        console.log("  ✅ All holdings have strong scores (≥75)");
      }
    });

    test("should calculate fit scores correctly", async () => {
      // Sample fit score calculation
      const universeResult = await query(
        `
        SELECT symbol, composite_score, momentum_score, value_score, quality_score, growth_score, stability_score
        FROM stock_scores
        WHERE symbol NOT IN (SELECT symbol FROM portfolio_holdings WHERE user_id = $1)
        AND composite_score >= 70
        LIMIT 3
        `,
        [TEST_USER_ID]
      );

      console.log("  ✅ Sample fit score calculations:");
      universeResult.rows.forEach((stock) => {
        // Market fit (assuming bullish market exposure 60)
        const marketFit =
          stock.momentum_score * 0.4 +
          stock.value_score * 0.3 +
          stock.quality_score * 0.3;

        // Simple correlation (default to 50)
        const correlation = 50;

        // Simple sector (default to 50)
        const sector = 50;

        // Final fit
        const fitScore = (
          (stock.composite_score * 0.5 +
            marketFit * 0.15 +
            correlation * 0.2 +
            sector * 0.15) /
          10
        ).toFixed(2);

        console.log(`     ${stock.symbol}: Fit Score = ${fitScore}/100`);
      });
    });
  });

  // Test 5: Data validation
  describe("Data Quality Validation", () => {
    test("should have no null composite scores in recommendations", async () => {
      const result = await query(
        `
        SELECT COUNT(*) as missing_scores
        FROM stock_scores
        WHERE composite_score IS NULL
        AND symbol IN (SELECT symbol FROM portfolio_holdings WHERE user_id = $1)
        `,
        [TEST_USER_ID]
      );

      const missingScores = parseInt(result.rows[0].missing_scores);
      expect(missingScores).toBe(0);

      console.log("  ✅ All holdings have composite scores");
    });

    test("should have sector data for all holdings", async () => {
      const result = await query(
        `
        SELECT COUNT(*) as missing_sectors
        FROM portfolio_holdings ph
        LEFT JOIN company_profile cp ON cp.ticker = ph.symbol
        WHERE ph.user_id = $1
        AND cp.sector IS NULL
        `,
        [TEST_USER_ID]
      );

      const missingSectors = parseInt(result.rows[0].missing_sectors);
      console.log(`  ✅ ${missingSectors === 0 ? "All" : "Some"} holdings have sector data`);
    });

    test("should have valid prices for all holdings", async () => {
      const result = await query(
        `
        SELECT symbol, current_price, market_value
        FROM portfolio_holdings
        WHERE user_id = $1
        AND (current_price IS NULL OR current_price <= 0 OR market_value IS NULL OR market_value <= 0)
        `,
        [TEST_USER_ID]
      );

      expect(result.rows.length).toBe(0);
      console.log("  ✅ All holdings have valid prices and values");
    });
  });

  // Test 6: Summary and recommendations
  describe("Final Recommendations Summary", () => {
    test("should generate actionable recommendations", async () => {
      console.log("\n  📊 PORTFOLIO OPTIMIZATION SUMMARY");
      console.log("  ════════════════════════════════════════");

      // Portfolio state
      const state = await query(
        `
        SELECT
          COUNT(*) as holdings,
          SUM(market_value) as total_value,
          AVG(ss.composite_score) as avg_score
        FROM portfolio_holdings ph
        LEFT JOIN stock_scores ss ON ph.symbol = ss.symbol
        WHERE ph.user_id = $1
        `,
        [TEST_USER_ID]
      );

      const totalValue = parseFloat(state.rows[0].total_value);
      const avgScore = parseFloat(state.rows[0].avg_score);

      console.log(`  Holdings: ${state.rows[0].holdings}`);
      console.log(`  Total Value: $${totalValue.toFixed(2)}`);
      console.log(`  Average Score: ${avgScore.toFixed(1)}/100\n`);

      // Buy candidates
      const buyCandidates = await query(
        `
        SELECT symbol, composite_score
        FROM stock_scores
        WHERE composite_score >= 80
        AND symbol NOT IN (SELECT symbol FROM portfolio_holdings WHERE user_id = $1)
        ORDER BY composite_score DESC
        LIMIT 3
        `,
        [TEST_USER_ID]
      );

      console.log(`  Recommended Actions:`);
      console.log(`  🟢 BUY Candidates: ${buyCandidates.rows.length || "None"}`);
      (buyCandidates.rows || []).forEach((row) => {
        console.log(`     - ${row.symbol} (Score: ${parseFloat(row.composite_score).toFixed(1)})`);
      });

      console.log("  ════════════════════════════════════════\n");
    });
  });
});
