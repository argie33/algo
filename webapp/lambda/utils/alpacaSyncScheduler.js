/**
 * Alpaca Portfolio Sync Scheduler
 * Automatically syncs portfolio data from Alpaca every 10 minutes
 * Data is fetched and stored in the database for the dashboard to display
 */

const cron = require("node-cron");

const { query } = require("./database");
// Import Alpaca service
const AlpacaService = require("./alpacaService");

// REMOVED: Default user ID - now syncs for all authenticated users
// Each user's portfolio is synced with their actual Cognito UUID (req.user.sub)

// Scheduler instance
let syncScheduler = null;

// Track last sync time to prevent too-frequent syncs
let lastSyncTime = null;
const MIN_SYNC_INTERVAL = 5 * 60 * 1000; // 5 minutes minimum

// Store all active user syncs
const _activeSyncs = new Map();

// Get Alpaca service instance
function getAlpacaService() {
  // Use Alpaca's official naming convention (APCA_*), fall back to alternate names
  const apiKey = process.env.APCA_API_KEY_ID || process.env.ALPACA_API_KEY;
  const secretKey =
    process.env.APCA_API_SECRET_KEY ||
    process.env.ALPACA_API_SECRET ||
    process.env.ALPACA_SECRET_KEY;
  const isPaper = process.env.ALPACA_PAPER_TRADING === "true";

  if (!apiKey || !secretKey) {
    console.error(
      " Alpaca credentials not configured. Set APCA_API_KEY_ID and APCA_API_SECRET_KEY"
    );
    return null;
  }

  return new AlpacaService(apiKey, secretKey, isPaper);
}

// Perform the actual sync for a specific user (runs in background with timeout to prevent blocking)
async function performAlpacaSync(userId = null) {
  // Set 30 second timeout to prevent blocking the scheduler
  const syncTimeout = new Promise((_, reject) =>
    setTimeout(
      () => reject(new Error("Sync timeout: exceeded 30 seconds")),
      30000
    )
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
        console.error(" Alpaca API fetch error:", err.message);
        return {
          status: "error",
          reason: "fetch_failed",
          details: err.message,
        };
      }

      if (!account || !positions) {
        console.error(" Failed to fetch Alpaca data");
        return { status: "error", reason: "fetch_failed" };
      }

      // If no userId provided, sync for all registered users
      const usersToSync = userId ? [userId] : [];
      if (!userId) {
        try {
          const usersResult = await query(
            "SELECT DISTINCT user_id FROM user_dashboard_settings WHERE user_id IS NOT NULL"
          );
          usersToSync.push(
            ...(usersResult.rows || []).map((row) => row.user_id)
          );
          if (usersToSync.length === 0) {
            console.log(` No users to sync`);
            return { status: "skipped", reason: "no_users" };
          }
        } catch (err) {
          console.error(" Failed to fetch users for sync:", err.message);
          return {
            status: "error",
            reason: "user_fetch_failed",
            details: err.message,
          };
        }
      }

      console.log(
        ` [CRON] Retrieved ${positions.length} positions from Alpaca, syncing for ${usersToSync.length} user(s)`
      );

      // Sync for each user
      const syncResults = [];
      for (const currentUserId of usersToSync) {
        try {
          // Batch database operations for better performance
          await Promise.all([
            // Clear existing holdings
            query("DELETE FROM portfolio_holdings WHERE user_id = $1", [
              currentUserId,
            ]),
            // Batch insert holdings (use transaction-like approach)
            (async () => {
              // Insert holdings in batches of 10 to avoid massive queries
              for (let i = 0; i < positions.length; i += 10) {
                const batch = positions.slice(i, i + 10);
                await Promise.all(
                  batch.map((position) =>
                    query(
                      `INSERT INTO portfolio_holdings
                      (user_id, symbol, quantity, current_price, average_cost, created_at, updated_at)
                      VALUES ($1, $2, $3, $4, $5, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)`,
                      [
                        currentUserId,
                        position.symbol,
                        position.quantity,
                        position.currentPrice,
                        position.averageEntryPrice,
                      ]
                    ).catch((err) =>
                      console.warn(
                        `⚠️  Failed to insert ${position.symbol} for user ${currentUserId}:`,
                        err.message
                      )
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
          const dayChangePercent =
            lastEquity > 0 ? (dayChange / lastEquity) * 100 : 0;

          await query(
            `INSERT INTO portfolio_performance
            (user_id, date, total_value, total_gain_loss, total_return_pct, created_at)
            VALUES ($1, CURRENT_DATE, $2, $3, $4, CURRENT_TIMESTAMP)`,
            [currentUserId, portfolioValue, dayChange, dayChangePercent]
          ).catch((err) => {
            if (err.code === "23505") {
              console.warn(
                ` Portfolio performance for user ${currentUserId} for today already recorded, skipping update`
              );
            } else {
              console.error(
                ` Database error during sync for user ${currentUserId}:`,
                err.message
              );
            }
          });

          syncResults.push({
            user_id: currentUserId,
            status: "success",
            holdings_synced: positions.length,
            portfolio_value: portfolioValue,
          });

          console.log(
            ` [CRON] Portfolio sync complete for user ${currentUserId}: $${portfolioValue?.toFixed(2)} portfolio value`
          );
        } catch (dbErr) {
          console.error(
            " Database error during sync for user:",
            currentUserId,
            dbErr.message
          );
          syncResults.push({
            user_id: currentUserId,
            status: "error",
            reason: "database_error",
            details: dbErr.message,
          });
        }
      }

      lastSyncTime = now;

      return {
        status: "success",
        results: syncResults,
        timestamp: new Date().toISOString(),
      };
    } catch (error) {
      console.error(" Alpaca sync error:", error.message);
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
    console.error(" [CRON] Sync operation failed:", error.message);
    return {
      status: "error",
      reason: "timeout_or_error",
      details: error.message,
    };
  }
}

// Initialize the scheduler
function initializeAlpacaSync() {
  try {
    // Check if credentials are configured
    const apiKey = process.env.APCA_API_KEY_ID || process.env.ALPACA_API_KEY;
    const secretKey =
      process.env.APCA_API_SECRET_KEY ||
      process.env.ALPACA_API_SECRET ||
      process.env.ALPACA_SECRET_KEY;

    if (!apiKey || !secretKey) {
      console.warn("⚠️  Alpaca credentials not configured - scheduler skipped");
      return null;
    }

    // Schedule sync every 10 minutes (*/10 * * * *)
    // Run sync asynchronously WITHOUT awaiting to prevent blocking the scheduler
    syncScheduler = cron.schedule("*/10 * * * *", () => {
      // Fire and forget - don't await to prevent blocking the event loop
      performAlpacaSync().catch((err) =>
        console.error(" [CRON] Scheduled sync error:", err.message)
      );
    });

    console.log(
      " Alpaca portfolio sync scheduler initialized (every 10 minutes)"
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
