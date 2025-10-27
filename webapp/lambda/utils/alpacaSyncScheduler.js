/**
 * Alpaca Portfolio Sync Scheduler
 * Automatically syncs portfolio data from Alpaca every 10 minutes
 * Data is fetched and stored in the database for the dashboard to display
 */

const cron = require("node-cron");
const { query } = require("./database");

// Import Alpaca service
const AlpacaService = require("./alpacaService");

// Default user ID for background syncs
const DEFAULT_USER_ID = "alpaca-user";

// Scheduler instance
let syncScheduler = null;

// Track last sync time to prevent too-frequent syncs
let lastSyncTime = null;
const MIN_SYNC_INTERVAL = 5 * 60 * 1000; // 5 minutes minimum

// Get Alpaca service instance
function getAlpacaService() {
  const apiKey = process.env.ALPACA_API_KEY;
  const secretKey = process.env.ALPACA_SECRET_KEY;
  const isPaper = process.env.ALPACA_PAPER_TRADING === "true";

  if (!apiKey || !secretKey) {
    console.error("❌ Alpaca credentials not configured");
    return null;
  }

  return new AlpacaService(apiKey, secretKey, isPaper);
}

// Perform the actual sync
async function performAlpacaSync() {
  try {
    const now = Date.now();

    // Rate limit: don't sync more frequently than MIN_SYNC_INTERVAL
    if (lastSyncTime && now - lastSyncTime < MIN_SYNC_INTERVAL) {
      console.log(
        `⏳ Skipping sync (too recent, last: ${Math.round((now - lastSyncTime) / 1000)}s ago)`
      );
      return { status: "skipped", reason: "rate_limit" };
    }

    console.log(`📊 [CRON] Starting scheduled Alpaca portfolio sync...`);

    const alpaca = getAlpacaService();
    if (!alpaca) {
      return { status: "error", reason: "alpaca_service_unavailable" };
    }

    // Fetch account and positions
    const [account, positions] = await Promise.all([
      alpaca.getAccount(),
      alpaca.getPositions(),
    ]);

    if (!account || !positions) {
      console.error("❌ Failed to fetch Alpaca data");
      return { status: "error", reason: "fetch_failed" };
    }

    console.log(
      `✅ [CRON] Retrieved ${positions.length} positions from Alpaca`
    );

    // Clear existing holdings for the user
    await query("DELETE FROM portfolio_holdings WHERE user_id = $1", [
      DEFAULT_USER_ID,
    ]);

    // Insert new holdings
    for (const position of positions) {
      try {
        await query(
          `INSERT INTO portfolio_holdings
          (user_id, symbol, quantity, current_price, average_cost, market_value, created_at, updated_at)
          VALUES ($1, $2, $3, $4, $5, $6, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)`,
          [
            DEFAULT_USER_ID,
            position.symbol,
            position.qty,
            position.current_price,
            position.avg_entry_price,
            position.market_value,
          ]
        );
      } catch (err) {
        console.warn(`⚠️  Failed to insert ${position.symbol}:`, err.message);
      }
    }

    // Update portfolio performance
    try {
      const portfolioValue = account.portfolioValue || 0;
      const cash = account.cash || 0;
      const lastEquity = account.last_equity || portfolioValue;

      // Calculate daily P&L
      const dailyPnL = portfolioValue - lastEquity;
      const totalReturnPercent =
        (portfolioValue - 100000) / 100000 * 100 || 0;

      await query(
        `INSERT INTO portfolio_performance
        (user_id, date, total_value, daily_pnl, total_pnl, total_pnl_percent, created_at)
        VALUES ($1, CURRENT_DATE, $2, $3, $4, $5, CURRENT_TIMESTAMP)
        ON CONFLICT (user_id, date) DO UPDATE SET
          total_value = $2,
          daily_pnl = $3,
          total_pnl = $4,
          total_pnl_percent = $5`,
        [
          DEFAULT_USER_ID,
          portfolioValue,
          dailyPnL,
          dailyPnL, // total_pnl = daily_pnl for now
          totalReturnPercent,
        ]
      );

      lastSyncTime = now;

      console.log(
        `✅ [CRON] Portfolio sync complete: $${portfolioValue?.toFixed(2)} portfolio value`
      );

      return {
        status: "success",
        holdings_synced: positions.length,
        portfolio_value: portfolioValue,
        timestamp: new Date().toISOString(),
      };
    } catch (dbErr) {
      console.error("❌ Database error during sync:", dbErr.message);
      return { status: "error", reason: "database_error", details: dbErr.message };
    }
  } catch (error) {
    console.error("❌ Alpaca sync error:", error.message);
    return {
      status: "error",
      reason: "sync_failed",
      details: error.message,
    };
  }
}

// Initialize the scheduler
function initializeAlpacaSync() {
  try {
    // Check if credentials are configured
    const apiKey = process.env.ALPACA_API_KEY;
    const secretKey = process.env.ALPACA_SECRET_KEY;

    if (!apiKey || !secretKey) {
      console.warn("⚠️  Alpaca credentials not configured - scheduler skipped");
      return null;
    }

    // Schedule sync every 10 minutes (*/10 * * * *)
    syncScheduler = cron.schedule("*/10 * * * *", async () => {
      await performAlpacaSync();
    });

    console.log(
      "✅ Alpaca portfolio sync scheduler initialized (every 10 minutes)"
    );

    // Also perform an initial sync on startup (after 5 seconds)
    setTimeout(() => {
      performAlpacaSync().catch((err) =>
        console.error("Initial sync error:", err)
      );
    }, 5000);

    return syncScheduler;
  } catch (error) {
    console.error("Failed to initialize Alpaca sync scheduler:", error);
    return null;
  }
}

// Stop the scheduler
function stopAlpacaSync() {
  if (syncScheduler) {
    syncScheduler.stop();
    console.log("✅ Alpaca sync scheduler stopped");
    syncScheduler = null;
  }
}

// Manual trigger for sync (can be called from API)
async function triggerManualSync() {
  return performAlpacaSync();
}

module.exports = {
  initializeAlpacaSync,
  stopAlpacaSync,
  triggerManualSync,
  performAlpacaSync,
};
