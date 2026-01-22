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
// In development, use 'dev_user' (matches auth.js line 28)
// In production, this should be overridden by actual user_id from authenticated requests
const DEFAULT_USER_ID = process.env.NODE_ENV === 'development' ? 'dev_user' : 'alpaca-user';

// Scheduler instance
let syncScheduler = null;

// Track last sync time to prevent too-frequent syncs
let lastSyncTime = null;
const MIN_SYNC_INTERVAL = 5 * 60 * 1000; // 5 minutes minimum

// Store all active user syncs
const activeSyncs = new Map();

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

// Perform the actual sync (runs in background with timeout to prevent blocking)
async function performAlpacaSync() {
  // Set 30 second timeout to prevent blocking the scheduler
  const syncTimeout = new Promise((_, reject) =>
    setTimeout(() => reject(new Error("Sync timeout: exceeded 30 seconds")), 30000)
  );

  const syncOperation = (async () => {
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

      // Fetch account and positions with 10s timeout each
      let account, positions;
      try {
        [account, positions] = await Promise.race([
          Promise.all([alpaca.getAccount(), alpaca.getPositions()]),
          new Promise((_, reject) =>
            setTimeout(() => reject(new Error("Alpaca API timeout")), 10000)
          ),
        ]);
      } catch (err) {
        console.error("❌ Alpaca API fetch error:", err.message);
        return { status: "error", reason: "fetch_failed", details: err.message };
      }

      if (!account || !positions) {
        console.error("❌ Failed to fetch Alpaca data");
        return { status: "error", reason: "fetch_failed" };
      }

      console.log(
        `✅ [CRON] Retrieved ${positions.length} positions from Alpaca`
      );

      // Batch database operations for better performance
      try {
        // Start deletion and batch inserts together (non-blocking approach)
        await Promise.all([
          // Clear existing holdings
          query("DELETE FROM portfolio_holdings WHERE user_id = $1", [DEFAULT_USER_ID]),
          // Batch insert holdings (use transaction-like approach)
          (async () => {
            // Insert holdings in batches of 10 to avoid massive queries
            for (let i = 0; i < positions.length; i += 10) {
              const batch = positions.slice(i, i + 10);
              await Promise.all(
                batch.map((position) =>
                  query(
                    `INSERT INTO portfolio_holdings
                    (user_id, symbol, quantity, current_price, average_cost, market_value, created_at, updated_at)
                    VALUES ($1, $2, $3, $4, $5, $6, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    ON CONFLICT (user_id, symbol) DO UPDATE SET
                      quantity = $3,
                      current_price = $4,
                      average_cost = $5,
                      market_value = $6,
                      updated_at = CURRENT_TIMESTAMP`,
                    [
                      DEFAULT_USER_ID,
                      position.symbol,
                      position.quantity,
                      position.currentPrice,
                      position.averageEntryPrice,
                      position.marketValue,
                    ]
                  ).catch((err) =>
                    console.warn(`⚠️  Failed to insert/update ${position.symbol}:`, err.message)
                  )
                )
              );
            }
          })(),
        ]);

        // Update portfolio performance
        const portfolioValue = account.portfolioValue || 0;
        const lastEquity = account.lastEquity || portfolioValue;
        const dayChange = portfolioValue - lastEquity;
        const dayChangePercent = lastEquity > 0 ? (dayChange / lastEquity) * 100 : 0;

        await query(
          `INSERT INTO portfolio_performance
          (user_id, date, total_value, daily_pnl, daily_pnl_percent, total_pnl, total_pnl_percent, created_at)
          VALUES ($1, CURRENT_DATE, $2, $3, $4, $5, $6, CURRENT_TIMESTAMP)
          ON CONFLICT (user_id, date) DO UPDATE SET
            total_value = $2,
            daily_pnl = $3,
            daily_pnl_percent = $4,
            total_pnl = $5,
            total_pnl_percent = $6`,
          [DEFAULT_USER_ID, portfolioValue, dayChange, dayChangePercent, dayChange, dayChangePercent]
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
  })();

  try {
    return await Promise.race([syncOperation, syncTimeout]);
  } catch (error) {
    console.error("❌ [CRON] Sync operation failed:", error.message);
    return { status: "error", reason: "timeout_or_error", details: error.message };
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
    // Run sync asynchronously WITHOUT awaiting to prevent blocking the scheduler
    syncScheduler = cron.schedule("*/10 * * * *", () => {
      // Fire and forget - don't await to prevent blocking the event loop
      performAlpacaSync().catch((err) =>
        console.error("❌ [CRON] Scheduled sync error:", err.message)
      );
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
