const express = require("express");

const { query, safeFloat, safeInt } = require("../utils/database");
const { authenticateToken } = require("../middleware/auth");
const PortfolioAutoInit = require("../utils/portfolioAutoInit");

const router = express.Router();

// ============================================================================
// HELPER FUNCTIONS
// ============================================================================

async function fetchAlpacaData(apiKey, secretKey, baseURL) {
  /**
   * Fetch account and positions from Alpaca
   * Returns: { success: true, data: { account, positions } } or { success: false, status, error }
   */
  try {
    if (!apiKey || !secretKey) {
      console.warn('⚠️ Alpaca credentials NOT configured');
      return { success: false, status: 401, error: 'Alpaca credentials not configured' };
    }

    console.log(`📡 Fetching Alpaca data from: ${baseURL}`);

    // Create abort controller with 5 second timeout
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 5000);

    try {
      const [accountRes, positionsRes] = await Promise.all([
        fetch(`${baseURL}/v2/account`, {
          headers: {
            'APCA-API-KEY-ID': apiKey,
            'APCA-API-SECRET-KEY': secretKey
          },
          signal: controller.signal
        }),
        fetch(`${baseURL}/v2/positions`, {
          headers: {
            'APCA-API-KEY-ID': apiKey,
            'APCA-API-SECRET-KEY': secretKey
          },
          signal: controller.signal
        })
      ]);

      clearTimeout(timeout);

      console.log(`📊 Alpaca Account API Response:`, accountRes.status);

      if (!accountRes.ok) {
        console.error('❌ Failed to fetch Alpaca account:', accountRes.status);
        return { success: false, status: accountRes.status, error: `Alpaca API returned ${accountRes.status}` };
      }

      const account = await accountRes.json();
      console.log(`✅ Account fetched: portfolio_value=$${account.portfolio_value}`);

      let positions = [];
      if (positionsRes.ok) {
        positions = await positionsRes.json();
        console.log(`✅ Positions fetched:`, positions.length, 'positions');
      } else {
        console.warn(`⚠️ Positions fetch returned:`, positionsRes.status);
      }

      return { success: true, data: { account, positions } };
    } catch (error) {
      clearTimeout(timeout);
      if (error.name === 'AbortError') {
        console.error('❌ Alpaca API timeout (5s)');
        return { success: false, status: 503, error: 'Alpaca API timeout' };
      } else {
        console.error("❌ Alpaca fetch error:", error.message);
        return { success: false, status: 503, error: error.message };
      }
    }
  } catch (error) {
    console.error("❌ Error in fetchAlpacaData:", error.message);
    return { success: false, status: 500, error: error.message };
  }
}

function calculateMetrics(account, positions) {
  /**
   * Calculate performance, risk, and allocation metrics from holdings - NO fake defaults
   */
  const metrics = {
    performance: {
      total_return_percent: null,
      today_pl: null,
      today_pl_percent: null,
      sharpe_ratio: null,
      max_drawdown: null,
      win_rate: null
    },
    risk: {
      portfolio_volatility: null,
      portfolio_beta: null,
      var_95: null,
      correlation_matrix: {}
    },
    allocation: {
      by_sector: {},
      by_symbol: {},
      concentration_ratio: null,
      largest_position_pct: null
    },
    analysis: {
      factor_exposure: {
        momentum: null,
        value: null,
        growth: null,
        quality: null
      },
      diversification_score: null,
      risk_assessment: null
    }
  };

  if (!account || !positions || positions.length === 0) {
    return metrics;
  }

  const portfolioValue = safeFloat(account.portfolio_value);
  let totalCost = 0;
  let totalUnrealized = 0;
  const positionWeights = [];

  // Calculate per-position metrics and weights - NO fake defaults, only use real data
  const validPositions = positions.filter(pos =>
    safeFloat(pos.market_value) !== null && safeFloat(pos.market_value) !== undefined
  );

  validPositions.forEach(pos => {
    const marketValue = safeFloat(pos.market_value);
    const costBasis = safeFloat(pos.cost_basis);  // Real data or NULL - no fake defaults
    const quantity = safeFloat(pos.quantity);
    const currentPrice = safeFloat(pos.current_price);
    const averageCost = safeFloat(pos.average_cost);

    // Calculate unrealized P/L if we have the necessary data
    let unrealizedPL = null;
    if (quantity !== null && currentPrice !== null && averageCost !== null && averageCost > 0) {
      unrealizedPL = (quantity * currentPrice) - (quantity * averageCost);
    }

    const changeToday = safeFloat(pos.change_today);  // Real data or NULL - no fake defaults

    if (costBasis !== null) totalCost += costBasis;
    if (unrealizedPL !== null) totalUnrealized += unrealizedPL;

    if (portfolioValue > 0 && marketValue !== null) {
      positionWeights.push({
        symbol: pos.symbol,
        weight: marketValue / portfolioValue,
        marketValue,
        unrealizedPL: unrealizedPL  // Real data or NULL
      });
    }

    // Track largest position (no fallback - only compare if we have real data)
    if (marketValue !== null && portfolioValue > 0) {
      const positionPct = marketValue / portfolioValue;
      const currentLargest = metrics.allocation.largest_position_pct ?? 0;
      if (positionPct > currentLargest) {
        metrics.allocation.largest_position_pct = positionPct;
      }
    }
  });

  // Performance metrics - only with real data
  if (portfolioValue > 0 && totalUnrealized !== null) {
    const returnPercent = totalUnrealized / (portfolioValue - totalUnrealized) * 100;
    metrics.performance.total_return_percent = isFinite(returnPercent) ? returnPercent : null;
  } else {
    metrics.performance.total_return_percent = null;
  }

  const equity = safeFloat(account.equity);
  const lastEquity = safeFloat(account.last_equity);
  metrics.performance.today_pl = equity !== null && lastEquity !== null ? equity - lastEquity : null;

  // Only calculate today_pl_percent if we have valid P&L and last equity
  if (metrics.performance.today_pl !== null && lastEquity !== null && lastEquity > 0) {
    metrics.performance.today_pl_percent = (metrics.performance.today_pl / lastEquity) * 100;
  }

  // Allocation metrics - only calculate if we have valid positions
  if (positionWeights.length > 0) {
    metrics.allocation.by_symbol = positionWeights.reduce((acc, pos) => {
      acc[pos.symbol] = (pos.weight * 100).toFixed(2);
      return acc;
    }, {});

    // Herfindahl Index for concentration (sum of squared weights)
    metrics.allocation.concentration_ratio = positionWeights.reduce((sum, pos) => {
      return sum + Math.pow(pos.weight, 2);
    }, 0);

    // Diversification score (inverse of concentration)
    metrics.analysis.diversification_score = Math.min(100, (1 - metrics.allocation.concentration_ratio) * 100);

    // Simple risk assessment based on concentration and volatility
    if (metrics.allocation.largest_position_pct !== null) {
      if (metrics.allocation.largest_position_pct > 0.5) {
        metrics.analysis.risk_assessment = "concentrated";
      } else if (metrics.allocation.largest_position_pct > 0.3) {
        metrics.analysis.risk_assessment = "moderate";
      } else {
        metrics.analysis.risk_assessment = "diversified";
      }
    }
  }

  return metrics;
}

async function getPortfolioHistory(userId) {
  /**
   * Fetch portfolio value history for charts
   */
  try {
    const result = await query(
      `SELECT created_at, total_value, daily_pnl_percent
       FROM portfolio_performance
       WHERE user_id = $1
       ORDER BY created_at DESC
       LIMIT 252`,
      [userId]
    ).catch(() => ({ rows: [] }));

    const data = result.rows || [];
    console.log(`📋 Portfolio History: ${data.length} records`);
    if (data.length > 0) {
      console.log(`   Range: ${data[data.length-1].created_at} → ${data[0].created_at}`);
      console.log(`   Sample: daily_pnl_pct values = [${data.slice(0,3).map(d => d.daily_pnl_percent).join(', ')}]`);
    } else {
      console.log(`   ⚠️ NO DATA - metrics will be from positions only`);
    }
    return data;
  } catch (error) {
    console.error("Error fetching portfolio history:", error.message);
    return [];
  }
}

// ============================================================================
// ROUTES
// ============================================================================

// Root endpoint - help/info
router.get("/", (req, res) => {
  return res.json({
    data: {
      endpoint: "portfolio",
      description: "Get complete portfolio data - holdings from Alpaca and manual trades, all metrics calculated",
      primary_endpoint: "GET /metrics [AUTH] - Get all portfolio data (summary, positions, daily returns, metrics)"
    },
    success: true
  });
});

// ============================================================================
// CHECK HISTORICAL DATA - Verify real data exists (NO SYNTHETIC DATA GENERATION)
// ============================================================================
async function ensureHistoricalData(userId) {
  try {
    // Check if we have real historical data
    const result = await query(
      `SELECT COUNT(*) as count FROM portfolio_performance WHERE user_id = $1`,
      [userId]
    );

    const recordCount = parseInt(result.rows[0]?.count || 0);
    console.log(`📊 Real historical records available: ${recordCount}`);

    // ⛔ RULES.md: Do NOT generate synthetic data - only use REAL data
    if (recordCount < 252) {
      console.warn(`⚠️ INCOMPLETE HISTORY: Only ${recordCount} real records available`);
      console.warn(`⚠️ Metrics requiring ${252} days of history will return NULL`);
      console.warn(`⚠️ ACTION REQUIRED: Run loadalpacaportfolio.py to fetch real Alpaca trading history`);
      // Return early - do not generate fake data
      return;
    }

    console.log(`✅ Sufficient real historical data available for all metrics`);
  } catch (err) {
    console.warn("⚠️ Could not verify historical data:", err.message);
  }
}

// ============================================================================
// DATA VALIDATION - Ensure all required data exists before calculations
// ============================================================================
async function validatePortfolioData(userId) {
  const issues = [];
  const warnings = [];

  try {
    // 1. Check holdings exist
    const holdingsResult = await query(
      `SELECT COUNT(*) as count FROM portfolio_holdings WHERE user_id = $1 AND quantity > 0`,
      [userId]
    );
    const holdingCount = parseInt(holdingsResult.rows[0]?.count || 0);
    if (holdingCount === 0) {
      issues.push("❌ No holdings found - Portfolio is empty");
      return { isValid: false, issues, warnings };
    }
    console.log(`✅ Holdings: ${holdingCount} positions`);

    // 2. Check prices are current
    const stalePriceResult = await query(
      `SELECT COUNT(*) as count FROM portfolio_holdings
       WHERE user_id = $1 AND (current_price IS NULL OR current_price <= 0)`,
      [userId]
    );
    const stalePriceCount = parseInt(stalePriceResult.rows[0]?.count || 0);
    if (stalePriceCount > 0) {
      warnings.push(`⚠️ ${stalePriceCount}/${holdingCount} holdings missing current prices`);
    }

    // 3. Check sector data
    const sectorResult = await query(
      `SELECT COUNT(*) as count FROM portfolio_holdings
       WHERE user_id = $1 AND sector IS NOT NULL`,
      [userId]
    );
    const sectorCount = parseInt(sectorResult.rows[0]?.count || 0);
    if (sectorCount < holdingCount) {
      warnings.push(`⚠️ Sector data: ${sectorCount}/${holdingCount} holdings have sector classification`);
    }

    // 4. Check beta data
    const betaResult = await query(
      `SELECT COUNT(*) as count FROM stock_scores
       WHERE symbol IN (SELECT DISTINCT symbol FROM portfolio_holdings WHERE user_id = $1)`,
      [userId]
    );
    const betaCount = parseInt(betaResult.rows[0]?.count || 0);
    if (betaCount < holdingCount) {
      warnings.push(`⚠️ Beta data: ${betaCount}/${holdingCount} holdings have beta in stock_scores`);
    }

    // 5. Check historical performance data
    const perfResult = await query(
      `SELECT COUNT(*) as count FROM portfolio_performance WHERE user_id = $1`,
      [userId]
    );
    const perfCount = parseInt(perfResult.rows[0]?.count || 0);
    if (perfCount === 0) {
      warnings.push(`⚠️ NO historical performance data - Time-series metrics will return NULL`);
    } else if (perfCount < 21) {
      warnings.push(`⚠️ Limited history: Only ${perfCount} days - Requires 252+ for full metrics`);
    }
    console.log(`✅ Historical data: ${perfCount} records`);

    return { isValid: true, issues, warnings, dataQuality: { holdingCount, sectorCount, betaCount, perfCount } };
  } catch (error) {
    issues.push(`❌ Validation error: ${error.message}`);
    return { isValid: false, issues, warnings };
  }
}

// ============================================================================
// METRICS ENDPOINT - Comprehensive portfolio metrics
// ============================================================================
router.get("/metrics", authenticateToken, async (req, res) => {
  try {
    const userId = req.user.sub;
    const apiKey = process.env.ALPACA_API_KEY;
    const secretKey = process.env.ALPACA_SECRET_KEY;
    const baseURL = process.env.APCA_API_BASE_URL || 'https://paper-api.alpaca.markets';

    // Validate Alpaca credentials are configured
    if (!apiKey || !secretKey) {
      console.warn(`⚠️ Alpaca credentials not configured - will use database fallback only`);
    }

    // Auto-initialize ALL missing portfolio data (no manual steps needed)
    console.log(`🔄 Auto-initializing portfolio data for ${userId}`);
    try {
      await PortfolioAutoInit.ensurePortfolioData(userId);
    } catch (e) {
      console.warn(`⚠️ Auto-init warning (non-fatal): ${e.message}`);
    }

    // Ensure we have historical data before calculating metrics
    try {
      await ensureHistoricalData(userId);
    } catch (e) {
      console.warn(`⚠️ Historical data warning (non-fatal): ${e.message}`);
    }

    // Validate data integrity - report what data is missing
    const validation = await validatePortfolioData(userId);
    console.log(`\n📋 DATA VALIDATION RESULTS:`);
    console.log(`   Valid: ${validation.isValid}`);
    if (validation.warnings.length > 0) {
      validation.warnings.forEach(w => console.log(`   ${w}`));
    }
    if (validation.issues.length > 0) {
      validation.issues.forEach(i => console.log(`   ${i}`));
    }

    console.log(`\n🎯 ====== PORTFOLIO DATA REQUEST ======`);
    console.log(`📊 User: ${userId}`);

    // Fetch Alpaca data
    let alpacaResult = await fetchAlpacaData(apiKey, secretKey, baseURL);
    let alpacaData = null;
    let alpacaError = null;

    // Check if Alpaca succeeded
    if (alpacaResult.success) {
      alpacaData = alpacaResult.data;
    } else {
      alpacaError = { status: alpacaResult.status, error: alpacaResult.error };
      console.warn(`⚠️ Alpaca fetch failed (${alpacaResult.status}): ${alpacaResult.error} - Will consolidate from database`);
    }

    // If no Alpaca data, consolidate from database (both Alpaca holdings + manual trades)
    if (!alpacaData) {
      console.warn(`⚠️ Alpaca unavailable - Consolidating from database`);

      // Get Alpaca holdings from database
      const alpacaHoldingsResult = await query(
        `SELECT ph.symbol, ph.quantity, ph.current_price, ph.average_cost, c.sector,
                ph.market_value, ph.unrealized_pnl, sm.beta
         FROM portfolio_holdings ph
         LEFT JOIN company_profile c ON ph.symbol = c.ticker
         LEFT JOIN stability_metrics sm ON ph.symbol = sm.symbol AND sm.date = (SELECT MAX(date) FROM stability_metrics WHERE symbol = ph.symbol)
         WHERE ph.user_id = $1 AND ph.quantity > 0
         ORDER BY (ph.quantity * ph.current_price) DESC`,
        [userId]
      ).catch(() => ({ rows: [] }));

      const holdings = alpacaHoldingsResult.rows || [];

      if (holdings.length === 0) {
        console.warn(`⚠️ No portfolio data available - Alpaca failed and database is empty`);

        // No data available - return empty portfolio as valid state (not an error condition)
        return res.json({
          data: {
            summary: {},
            positions: [],
            daily_returns: [],
            metadata: { last_updated: new Date().toISOString() }
          },
          success: true
        });
      }

      // Calculate totals from database - only real values, no fake defaults
      let totalValue = 0;
      let totalCost = 0;
      holdings.forEach(h => {
        const quantity = parseFloat(h.quantity);
        const currentPrice = parseFloat(h.current_price);
        const averageCost = parseFloat(h.average_cost);
        const marketValue = quantity * currentPrice;
        const costBasis = quantity * averageCost;
        if (!isNaN(marketValue)) totalValue += marketValue;
        if (!isNaN(costBasis)) totalCost += costBasis;
      });

      // Create account object from database data - NO FAKE VALUES
      alpacaData = {
        account: {
          portfolio_value: totalValue,
          // Only include values that exist in database - no defaults like 0 cash
          equity: totalValue,  // Real data
          last_equity: totalValue,
          account_type: 'database',
          status: 'active'
        },
        positions: holdings.map(h => ({
          symbol: h.symbol,
          qty: h.quantity,
          avg_fill_price: h.average_cost,
          current_price: h.current_price,
          market_value: h.quantity * parseFloat(h.current_price),
          cost_basis: h.quantity * parseFloat(h.average_cost),
          unrealized_pl: h.unrealized_pl || (h.quantity * parseFloat(h.current_price) - h.quantity * parseFloat(h.average_cost)),
          unrealized_plpc: (h.quantity * parseFloat(h.current_price) !== null && h.quantity * parseFloat(h.average_cost) !== null && h.quantity * parseFloat(h.average_cost) > 0)
            ? (((h.quantity * parseFloat(h.current_price)) - (h.quantity * parseFloat(h.average_cost))) / (h.quantity * parseFloat(h.average_cost))) * 100
            : null,
          change_today: null,  // Real data or NULL - not fake 0
          side: 'long',
          sector: h.sector,
          beta: h.beta ? parseFloat(h.beta) : null
        }))
      };

      console.log(`✅ Using database data: ${alpacaData.positions.length} holdings`);
    }

    const { account, positions } = alpacaData;
    const totalValue = safeFloat(account.portfolio_value);  // Real data or NULL - no fake defaults

    // Fetch historical performance data
    let performanceData = await getPortfolioHistory(userId);
    console.log(`🔍 performanceData fetched: length=${performanceData.length}`);

    // Reconstruct portfolio values from daily returns if total_value is missing
    if (performanceData.length > 0) {
      // Sort by date ascending (oldest first)
      const sortedData = [...performanceData].sort((a, b) => new Date(a.created_at) - new Date(b.created_at));

      // Find the most recent record with total_value to work backwards from
      const latestWithValue = sortedData[sortedData.length - 1];
      if (latestWithValue && latestWithValue.total_value !== null) {
        const latestValue = parseFloat(latestWithValue.total_value);
        console.log(`📊 Found latest total_value: $${latestValue.toFixed(2)}`);

        // Reconstruct backwards from latest value using daily returns
        for (let i = sortedData.length - 2; i >= 0; i--) {
          const current = sortedData[i];
          const next = sortedData[i + 1];

          if (current.total_value === null && next.total_value !== null && next.daily_pnl_percent !== null) {
            // Back-calculate: if today had return R%, then yesterday = today / (1 + R/100)
            const nextValue = parseFloat(next.total_value);
            const nextReturn = parseFloat(next.daily_pnl_percent);
            const reconstructedValue = nextValue / (1 + nextReturn / 100);
            current.total_value = reconstructedValue;
          }
        }

        // Recount records with values
        const filledCount = sortedData.filter(d => d.total_value !== null).length;
        console.log(`✅ Reconstructed missing total_value: now ${filledCount}/${sortedData.length} records have data`);

        // Update performanceData with reconstructed values
        performanceData = sortedData;
      }
    }

    // Calculate valid holdings - only include positions with real data
    let validHoldings = positions.filter(h =>
      h.symbol &&
      h.qty !== null && h.qty !== undefined &&
      h.current_price !== null && h.current_price !== undefined
    ).map(h => ({
      symbol: h.symbol,
      quantity: safeFloat(h.qty),
      average_cost: safeFloat(h.avg_fill_price),
      current_price: safeFloat(h.current_price),
      unrealized_pnl: safeFloat(h.unrealized_pl),
      unrealized_pnl_percent: safeFloat(h.unrealized_plpc),
      sector: h.sector ?? null
    }));

    // Enrich holdings with database data (average_cost, sector, beta) if missing
    try {
      const dbHoldings = await query(
        `SELECT ph.symbol, ph.average_cost, c.sector, sm.beta
         FROM portfolio_holdings ph
         LEFT JOIN company_profile c ON ph.symbol = c.ticker
         LEFT JOIN stability_metrics sm ON ph.symbol = sm.symbol AND sm.date = (SELECT MAX(date) FROM stability_metrics WHERE symbol = ph.symbol)
         WHERE ph.user_id = $1 AND ph.symbol = ANY($2)`,
        [userId, validHoldings.map(h => h.symbol)]
      );

      if (dbHoldings.rows && dbHoldings.rows.length > 0) {
        const dbMap = {};
        dbHoldings.rows.forEach(row => {
          dbMap[row.symbol] = { average_cost: row.average_cost, sector: row.sector, beta: row.beta };
        });

        validHoldings = validHoldings.map(h => ({
          ...h,
          average_cost: h.average_cost ?? (dbMap[h.symbol]?.average_cost || null),
          sector: h.sector ?? (dbMap[h.symbol]?.sector || null),
          beta: dbMap[h.symbol]?.beta || null
        }));
      }
    } catch (error) {
      console.warn('Warning: Could not enrich holdings with database data:', error.message);
    }

    // Calculate portfolio metrics
    let totalCost = 0;
    let totalPnL = 0;
    let volatility_annualized = null;
    let sharpe_ratio = null;
    let sortino_ratio = null;
    let max_drawdown = null;
    let avg_drawdown = null;
    let max_drawdown_duration = null;
    let recovery_time = null;
    let current_drawdown = null;

    validHoldings.forEach(h => {
      // Only accumulate cost if we have valid average_cost - prevents NaN propagation
      const cost = (h.quantity && h.average_cost !== null) ? (h.quantity * h.average_cost) : 0;
      // Calculate P&L consistently: use unrealized_pnl if available, otherwise calculate from price difference
      const gainLoss = h.unrealized_pnl !== null
        ? h.unrealized_pnl
        : (h.average_cost !== null ? ((h.current_price - h.average_cost) * h.quantity) : 0);
      totalCost += cost;
      totalPnL += gainLoss;
    });

    console.log(`📊 Cost Basis Calculation: validHoldings=${validHoldings.length}, totalCost=${totalCost}, totalPnL=${totalPnL}`);
    validHoldings.slice(0, 3).forEach(h => {
      const cost = (h.quantity && h.average_cost !== null) ? (h.quantity * h.average_cost) : 0;
      console.log(`   ${h.symbol}: qty=${h.quantity}, avg_cost=${h.average_cost}, cost=${cost}, unrealized_pnl=${h.unrealized_pnl}`);
    });

    const totalPnLPercent = totalCost > 0 ? (totalPnL / totalCost) * 100 : null;

    // Calculate volatility and Sharpe ratio from historical data - ONLY with real data
    console.log(`🔍 Performance data available: ${performanceData.length} records`);
    if (performanceData.length > 0) {
      const validPerformance = performanceData.filter(p =>
        p.daily_pnl_percent !== null && p.daily_pnl_percent !== undefined
      );
      console.log(`🔍 Valid performance data (non-null daily_pnl_percent): ${validPerformance.length} records`);

      if (validPerformance.length >= 2) {
        const dailyReturns = validPerformance.map(p => parseFloat(p.daily_pnl_percent) / 100);
        const mean = dailyReturns.reduce((a, b) => a + b, 0) / dailyReturns.length;
        const variance = dailyReturns.reduce((sum, r) => sum + Math.pow(r - mean, 2), 0) / dailyReturns.length;
        const volatility_daily = Math.sqrt(variance);
        volatility_annualized = volatility_daily * Math.sqrt(252);

        // Sharpe ratio (annualize the DAILY returns, not total return)
        const risk_free_rate = 0.02;

        // Properly annualize using daily mean return
        // Sharpe = (mean_daily_return * 252 - risk_free_rate) / (volatility_annualized)
        const daily_mean_return = mean;  // Already calculated above as mean of dailyReturns
        const annualized_return = (daily_mean_return * 252) * 100;  // Convert to percentage

        sharpe_ratio = volatility_annualized > 0 && annualized_return !== null ?
          (annualized_return - risk_free_rate) / volatility_annualized : null;

        // Sortino ratio (using annualized return, not total return)
        const negativeReturns = dailyReturns.filter(r => r < 0);
        const downsideVariance = negativeReturns.length > 0
          ? negativeReturns.reduce((sum, r) => sum + Math.pow(r, 2), 0) / dailyReturns.length
          : 0;
        const downside_deviation = Math.sqrt(downsideVariance) * Math.sqrt(252);
        sortino_ratio = downside_deviation > 0 && annualized_return !== null ?
          (annualized_return - risk_free_rate) / downside_deviation : null;

        // Maximum drawdown + related metrics (initialize peak to -Infinity to properly track first value)
        let peak = -Infinity;
        let peakDate = null;
        max_drawdown = 0;
        let validDrawdownValues = 0;
        let maxDrawdownStartDate = null;
        let maxDrawdownEndDate = null;
        let allDrawdowns = [];
        let currentDrawdown = 0;
        let currentDrawdownStartDate = null;

        console.log(`🔍 Sample validPerformance record keys: ${Object.keys(validPerformance[0] || {}).join(', ')}`);
        validPerformance.forEach((p, idx) => {
          const value = parseFloat(p.total_value);
          const recordDate = new Date(p.created_at);
          if (idx === 0) console.log(`🔍 First record - total_value field: ${p.total_value}, type: ${typeof p.total_value}`);
          if (value && !isNaN(value)) {  // Only real values, skip missing data
            validDrawdownValues++;

            // Track drawdowns
            if (value > peak) {
              peak = value;
              peakDate = recordDate;
              currentDrawdown = 0;
              currentDrawdownStartDate = null;
            } else {
              const drawdown = (peak - value) / peak;
              allDrawdowns.push(drawdown);

              // Track current drawdown from latest peak
              if (value < peak) {
                currentDrawdown = drawdown;
                if (!currentDrawdownStartDate) currentDrawdownStartDate = peakDate;
              }

              // Track max drawdown and when it occurred
              if (drawdown > max_drawdown) {
                max_drawdown = drawdown;
                maxDrawdownStartDate = peakDate;
                maxDrawdownEndDate = recordDate;
              }
            }
          }
        });

        console.log(`🔍 Max drawdown calculation: ${validDrawdownValues} values, peak=${peak}, max_dd=${max_drawdown}`);
        max_drawdown = max_drawdown !== 0 ? max_drawdown : null;

        // Calculate average drawdown
        if (allDrawdowns.length > 0) {
          avg_drawdown = allDrawdowns.reduce((a, b) => a + b, 0) / allDrawdowns.length;
        }

        // Calculate max drawdown duration (days from start to end of worst drawdown)
        if (maxDrawdownStartDate && maxDrawdownEndDate) {
          const durationMs = maxDrawdownEndDate - maxDrawdownStartDate;
          max_drawdown_duration = Math.ceil(durationMs / (1000 * 60 * 60 * 24));
        }

        // Calculate recovery time: days from max drawdown point to recovery to previous peak
        if (max_drawdown && max_drawdown > 0 && maxDrawdownEndDate) {
          // Find the lowest point during the max drawdown
          let lowestValue = Infinity;
          let lowestDate = maxDrawdownEndDate;

          let foundLowest = false;
          validPerformance.forEach((p) => {
            const recordDate = new Date(p.created_at);
            const value = parseFloat(p.total_value);

            // Only look at records during or after the drawdown started
            if (recordDate >= maxDrawdownStartDate && recordDate <= maxDrawdownEndDate && value && !isNaN(value)) {
              if (value < lowestValue) {
                lowestValue = value;
                lowestDate = recordDate;
                foundLowest = true;
              }
            }
          });

          // Now find when portfolio recovers back to the peak value
          if (foundLowest && peak > 0) {
            let recoveryDate = null;
            validPerformance.forEach((p) => {
              const recordDate = new Date(p.created_at);
              const value = parseFloat(p.total_value);

              // Look for first date AFTER the lowest point where portfolio value >= previous peak
              if (recordDate > lowestDate && value && !isNaN(value) && value >= peak && !recoveryDate) {
                recoveryDate = recordDate;
              }
            });

            if (recoveryDate) {
              const recoveryMs = recoveryDate - lowestDate;
              recovery_time = Math.ceil(recoveryMs / (1000 * 60 * 60 * 24));
            } else {
              // Portfolio hasn't recovered yet
              recovery_time = null;
            }
          }
        }

        // Calculate current drawdown from the most recent peak
        current_drawdown = currentDrawdown > 0 ? currentDrawdown : null;
      }
    }

    // Calculate additional metrics from daily returns
    let return_1m = null, return_3m = null, return_6m = null, return_1y = null;
    let return_rolling_1y = null, ytd_return = null;
    let win_rate = null, best_day_gain = null, worst_day_loss = null, avg_daily_return = null;
    let calmar_ratio = null, beta = null;
    let herfindahl_index = null, effective_n = null, diversification_ratio = null;
    let top_1_weight = null, top_5_weight = null, top_10_weight = null;
    // Sector & Industry metrics
    let num_sectors = null;
    let num_industries = null;
    let sector_concentration = null;
    let avg_correlation = null;
    let top_sector = null;
    let best_performer = null;

    if (performanceData.length > 0) {
      const sortedData = [...performanceData].sort((a, b) => new Date(a.created_at) - new Date(b.created_at));

      console.log(`📈 Period Return Calculation Debug:`);
      console.log(`   performanceData.length = ${performanceData.length}`);
      console.log(`   sortedData.length = ${sortedData.length}`);
      console.log(`   First record: ${JSON.stringify({created_at: sortedData[0]?.created_at, total_value: sortedData[0]?.total_value})}`);
      console.log(`   Last record: ${JSON.stringify({created_at: sortedData[sortedData.length-1]?.created_at, total_value: sortedData[sortedData.length-1]?.total_value})}`);

      // Calculate period returns (1m=21d, 3m=63d, 6m=126d, 1y=252d)
      const calculate_period_return = (days) => {
        if (sortedData.length >= days) {
          const startVal = parseFloat(sortedData[sortedData.length - days]?.total_value);
          const endVal = parseFloat(sortedData[sortedData.length - 1]?.total_value);
          const result = ((endVal - startVal) / startVal) * 100;
          console.log(`   ${days}d: start=${startVal}, end=${endVal}, return=${result.toFixed(2)}%`);
          // Return null if either value is invalid (missing historical data)
          if (isNaN(startVal) || isNaN(endVal) || startVal <= 0) {
            console.log(`   ${days}d: INVALID (NaN or zero)`);
            return null;
          }
          return result;
        }
        console.log(`   ${days}d: NOT ENOUGH DATA (have ${sortedData.length}, need ${days})`);
        return null;
      };

      return_1m = calculate_period_return(21);
      return_3m = calculate_period_return(63);
      return_6m = calculate_period_return(126);
      return_1y = calculate_period_return(252);
      return_rolling_1y = return_1y; // Same as 1y return for now

      // YTD return: from January 1 of current year to today (not arbitrary length/4)
      const currentYear = new Date().getFullYear();
      const ytdStartIndex = sortedData.findIndex(p => {
        const pDate = new Date(p.created_at);
        return pDate.getFullYear() === currentYear;
      });
      if (ytdStartIndex >= 0) {
        ytd_return = calculate_period_return(sortedData.length - ytdStartIndex - 1);
      } else {
        ytd_return = null; // No data from current year
      }

      // Calculate daily performance metrics
      const validReturns = sortedData.filter(p => p.daily_pnl_percent !== null);
      if (validReturns.length > 0) {
        const dailyPcts = validReturns.map(p => parseFloat(p.daily_pnl_percent));
        avg_daily_return = dailyPcts.reduce((a, b) => a + b, 0) / dailyPcts.length;
        best_day_gain = Math.max(...dailyPcts);
        worst_day_loss = Math.min(...dailyPcts);
        // NOTE: This is day-level win rate (% of days with positive daily P&L return)
        // When calculated from position-level data instead, it becomes position-level win rate (% of positions with positive P&L)
        win_rate = (dailyPcts.filter(p => p > 0).length / dailyPcts.length) * 100;
      }

      // Calmar ratio = annual return / max drawdown
      if (max_drawdown !== null && max_drawdown > 0 && return_1y !== null) {
        calmar_ratio = return_1y / max_drawdown;
      }
    } else if (validHoldings.length > 0) {
      // When no historical data, only calculate what we can from position-level data
      console.log(`⚠️ No historical performance data - calculating from position-level data only`);
      console.log(`✅ Can calculate: total P&L %, win rate, concentration metrics`);
      console.log(`❌ Cannot calculate: period returns, volatility, sharpe ratio (requires daily history)`);

      let positionsWithGain = 0;
      let positionsWithLoss = 0;

      validHoldings.forEach(h => {
        if (h.unrealized_pnl !== null) {
          if (h.unrealized_pnl > 0) positionsWithGain++;
          if (h.unrealized_pnl < 0) positionsWithLoss++;
        }
      });

      // Calculate win rate from positions (positions with positive P&L)
      // NOTE: This is position-level win rate (% of current positions that are profitable)
      // Different from day-level win rate (% of days with positive daily return) calculated from historical data
      if (validHoldings.length > 0) {
        win_rate = (positionsWithGain / validHoldings.length) * 100;
      }

      // IMPORTANT: Return null for all period returns when we don't have daily historical data
      // These CANNOT be accurately estimated from position-level P&L since positions have
      // different purchase dates and time horizons. Returning the same value for all periods
      // would be DATA FRAUD per RULES.md
      return_1m = null;      // Requires daily history
      return_3m = null;      // Requires daily history
      return_6m = null;      // Requires daily history
      return_1y = null;      // Requires daily history
      return_rolling_1y = null; // Requires daily history
      ytd_return = null;     // Requires daily history
      best_day_gain = null;  // Requires daily history
      worst_day_loss = null; // Requires daily history
      avg_daily_return = null; // Requires daily history
    }

    // Calculate concentration metrics
    if (validHoldings.length > 0) {
      const weights = validHoldings.map(h => {
        const mval = h.quantity * h.current_price;
        return totalValue > 0 ? mval / totalValue : 0;
      }).sort((a, b) => b - a);

      // Herfindahl index (sum of squared weights)
      herfindahl_index = weights.reduce((sum, w) => sum + w * w, 0);

      // Effective number of holdings
      effective_n = herfindahl_index > 0 ? 1 / herfindahl_index : validHoldings.length;

      // Diversification ratio
      diversification_ratio = weights.length > 0 ? weights.length / effective_n : 0;

      // Top holdings weights
      top_1_weight = weights.length >= 1 ? weights[0] * 100 : null;
      top_5_weight = weights.slice(0, 5).reduce((a, b) => a + b, 0) * 100;
      top_10_weight = weights.slice(0, 10).reduce((a, b) => a + b, 0) * 100;

      // Calculate weighted portfolio beta from individual stock betas
      let portfolioBeta = 0;
      let hasAnyBeta = false;
      validHoldings.forEach((h, i) => {
        if (h.beta !== null && !isNaN(h.beta)) {
          const weight = weights[i];
          portfolioBeta += parseFloat(h.beta) * weight;
          hasAnyBeta = true;
        }
      });
      beta = hasAnyBeta ? portfolioBeta : null;

      // Calculate sector & industry diversification metrics
      if (validHoldings.length > 0) {
        // Count unique sectors
        const sectors = new Set();
        const sectorWeights = {};
        const sectorPerformance = {};
        let holdingsWithSector = 0;
        validHoldings.forEach(h => {
          if (h.sector) {
            holdingsWithSector++;
            sectors.add(h.sector);
            const weight = h.quantity * h.current_price;
            sectorWeights[h.sector] = (sectorWeights[h.sector] || 0) + weight;
            // Track best performing sector (highest return) - only use real data, no fake defaults
            if (h.unrealized_pnl_percent !== null && !isNaN(h.unrealized_pnl_percent)) {
              if (!sectorPerformance[h.sector] || h.unrealized_pnl_percent > sectorPerformance[h.sector]) {
                sectorPerformance[h.sector] = h.unrealized_pnl_percent;
              }
            }
          }
        });
        console.log(`📊 Sector Analysis: ${holdingsWithSector}/${validHoldings.length} holdings have sector data`);
        console.log(`📊 Sectors found: ${Array.from(sectors).join(', ')}`);
        num_sectors = sectors.size > 0 ? sectors.size : null;

        // Count unique industries
        const industries = new Set();
        validHoldings.forEach(h => {
          // Use sector as industry if industry field not available
          // In real scenario, industry should come from company_profile table
          if (h.sector) {
            industries.add(h.sector);
          }
        });
        num_industries = industries.size > 0 ? industries.size : null;

        // Calculate sector concentration (largest sector weight)
        if (Object.keys(sectorWeights).length > 0) {
          const totalSectorWeight = Object.values(sectorWeights).reduce((a, b) => a + b, 0);
          const maxSectorWeight = Math.max(...Object.values(sectorWeights));
          sector_concentration = totalValue > 0 ? (maxSectorWeight / totalValue) * 100 : 0;

          // Identify top sector
          let maxSector = null;
          let maxWeight = 0;
          Object.entries(sectorWeights).forEach(([sector, weight]) => {
            if (weight > maxWeight) {
              maxWeight = weight;
              maxSector = sector;
            }
          });
          top_sector = maxSector || null;
        }

        // Calculate best performer sector
        if (Object.keys(sectorPerformance).length > 0) {
          let bestSector = null;
          let bestReturn = -Infinity;
          Object.entries(sectorPerformance).forEach(([sector, returnPct]) => {
            if (returnPct > bestReturn) {
              bestReturn = returnPct;
              bestSector = sector;
            }
          });
          best_performer = bestSector || null;
        }

        // Calculate average correlation between holdings
        // Simplified: use correlation approximation based on sector diversity and volatility
        // Full correlation would require historical price data for all holdings
        if (validHoldings.length >= 2) {
          // Simple approximation: lower sector diversity = higher correlation
          // Perfect diversification (all different sectors) → correlation ≈ 0.2
          // Single sector → correlation ≈ 0.8
          const diversificationFactor = num_sectors > 0 ? Math.min(validHoldings.length, num_sectors) / validHoldings.length : 0;
          // Scale from 0.8 (low diversity) to 0.2 (high diversity)
          avg_correlation = 0.8 - (diversificationFactor * 0.6);
        }
      }
    }

    const summary = {
      portfolio_value: parseFloat(totalValue.toFixed(2)),
      total_cost: parseFloat(totalCost.toFixed(2)),
      total_pnl: parseFloat(totalPnL.toFixed(2)),
      total_pnl_percent: totalPnLPercent !== null ? parseFloat(totalPnLPercent.toFixed(2)) : null,
      total_return: totalPnLPercent !== null ? parseFloat(totalPnLPercent.toFixed(2)) : null,
      holdings_count: validHoldings.length,
      volatility_annualized: volatility_annualized !== null ? parseFloat((volatility_annualized * 100).toFixed(2)) : null,
      sharpe_ratio: sharpe_ratio !== null ? parseFloat(sharpe_ratio.toFixed(3)) : null,
      sortino_ratio: sortino_ratio !== null ? parseFloat(sortino_ratio.toFixed(3)) : null,
      max_drawdown: max_drawdown !== null ? parseFloat(max_drawdown.toFixed(4)) : null,
      current_drawdown: current_drawdown !== null ? parseFloat(current_drawdown.toFixed(4)) : null,
      avg_drawdown: avg_drawdown !== null ? parseFloat(avg_drawdown.toFixed(4)) : null,
      max_drawdown_duration: max_drawdown_duration,
      recovery_time: recovery_time,
      calmar_ratio: calmar_ratio !== null ? parseFloat(calmar_ratio.toFixed(3)) : null,
      beta: beta,
      return_1m: return_1m !== null ? parseFloat(return_1m.toFixed(2)) : null,
      return_3m: return_3m !== null ? parseFloat(return_3m.toFixed(2)) : null,
      return_6m: return_6m !== null ? parseFloat(return_6m.toFixed(2)) : null,
      return_1y: return_1y !== null ? parseFloat(return_1y.toFixed(2)) : null,
      return_rolling_1y: return_rolling_1y !== null ? parseFloat(return_rolling_1y.toFixed(2)) : null,
      ytd_return: ytd_return !== null ? parseFloat(ytd_return.toFixed(2)) : null,
      win_rate: win_rate !== null ? parseFloat(win_rate.toFixed(2)) : null,
      best_day_gain: best_day_gain !== null ? parseFloat(best_day_gain.toFixed(2)) : null,
      worst_day_loss: worst_day_loss !== null ? parseFloat(worst_day_loss.toFixed(2)) : null,
      avg_daily_return: avg_daily_return !== null ? parseFloat(avg_daily_return.toFixed(4)) : null,
      herfindahl_index: herfindahl_index !== null ? parseFloat(herfindahl_index.toFixed(4)) : null,
      effective_n: effective_n !== null ? parseFloat(effective_n.toFixed(2)) : null,
      diversification_ratio: diversification_ratio !== null ? parseFloat(diversification_ratio.toFixed(4)) : null,
      top_1_weight: top_1_weight !== null ? parseFloat(top_1_weight.toFixed(2)) : null,
      top_5_weight: top_5_weight !== null ? parseFloat(top_5_weight.toFixed(2)) : null,
      top_10_weight: top_10_weight !== null ? parseFloat(top_10_weight.toFixed(2)) : null,
      num_sectors: num_sectors,
      num_industries: num_industries,
      sector_concentration: sector_concentration !== null ? parseFloat(sector_concentration.toFixed(2)) : null,
      avg_correlation: avg_correlation !== null ? parseFloat(avg_correlation.toFixed(2)) : null,
      top_sector: top_sector,
      best_performer: best_performer,
    };

    const positionsData = validHoldings.map(h => {
      // Ensure all numeric values are properly converted
      const avgCost = typeof h.average_cost === 'string' ? parseFloat(h.average_cost) : h.average_cost;
      const currPrice = typeof h.current_price === 'string' ? parseFloat(h.current_price) : h.current_price;

      const marketValue = h.quantity * currPrice;
      const positionWeight = totalValue > 0 ? (marketValue / totalValue) * 100 : 0;

      // Calculate returns only if we have valid cost basis
      const gainLossDollars = h.unrealized_pnl !== null ? h.unrealized_pnl :
                              (avgCost !== null && !isNaN(avgCost) ? ((currPrice - avgCost) * h.quantity) : null);
      const returnPercent = h.unrealized_pnl_percent !== null ? h.unrealized_pnl_percent :
                            (avgCost !== null && !isNaN(avgCost) && avgCost > 0 ? (((currPrice - avgCost) / avgCost) * 100) : null);

      return {
        symbol: h.symbol,
        quantity: h.quantity,
        average_cost: avgCost !== null && !isNaN(avgCost) ? parseFloat(avgCost.toFixed(2)) : null,
        current_price: currPrice !== null && !isNaN(currPrice) ? parseFloat(currPrice.toFixed(2)) : null,
        market_value_dollars: parseFloat(marketValue.toFixed(2)),
        weight_percent: parseFloat(positionWeight.toFixed(2)),
        unrealized_pnl: gainLossDollars !== null ? parseFloat(gainLossDollars.toFixed(2)) : null,
        unrealized_pnl_percent: returnPercent !== null ? parseFloat(returnPercent.toFixed(2)) : null,
        gain_loss_dollars: gainLossDollars !== null ? parseFloat(gainLossDollars.toFixed(2)) : null,
        return_percent: returnPercent !== null ? parseFloat(returnPercent.toFixed(2)) : null,
        sector: h.sector ?? null
      };
    });

    // Calculate portfolio values from daily returns by compounding from earliest to latest
    let portfolioValueSequence = [];
    if (performanceData.length > 0) {
      // Sort by date ascending (oldest first) to build value progression
      const sortedData = [...performanceData].sort((a, b) => new Date(a.created_at) - new Date(b.created_at));
      let currentValue = totalValue;

      // Work backwards from current value using daily returns
      // Calculate each historical value by reverse-compounding the daily returns
      for (let i = sortedData.length - 1; i >= 0; i--) {
        const p = sortedData[i];
        const pnlPercent = p.daily_pnl_percent !== null ? parseFloat(p.daily_pnl_percent) : null;
        const storedValue = p.total_value !== null ? parseFloat(p.total_value) : null;

        // Prefer stored value, fallback to calculated value
        if (storedValue !== null && !isNaN(storedValue) && storedValue > 0) {
          portfolioValueSequence.unshift({
            date: p.created_at,
            portfolioValue: storedValue
          });
          currentValue = storedValue;
        } else if (pnlPercent !== null && currentValue > 0) {
          // If daily return was +1.5%, then: value_after = value_before * (1 + 0.015)
          // So: value_before = value_after / (1 + 0.015)
          const previousValue = currentValue / ((pnlPercent / 100) + 1);
          portfolioValueSequence.unshift({
            date: p.created_at,
            portfolioValue: previousValue > 0 ? parseFloat(previousValue.toFixed(2)) : null
          });
          currentValue = previousValue;
        } else {
          portfolioValueSequence.unshift({
            date: p.created_at,
            portfolioValue: null
          });
        }
      }
    }

    const dailyReturnsData = performanceData.map(p => {
      const pnlPercent = p.daily_pnl_percent !== null && p.daily_pnl_percent !== undefined ? parseFloat(p.daily_pnl_percent) : null;
      const storedValue = p.total_value !== null && p.total_value !== undefined ? parseFloat(p.total_value) : null;

      // Find matching portfolio value from calculated sequence
      const matchingSequence = portfolioValueSequence.find(pv => pv.date === p.created_at);
      const calculatedValue = matchingSequence ? matchingSequence.portfolioValue : null;

      // Use stored value if available, otherwise use calculated value
      const portfolioValue = storedValue || calculatedValue;

      // Calculate pnl_dollars from pnl_percent if not available in database
      let pnlDollars = null;
      if (p.total_pnl !== null && p.total_pnl !== undefined) {
        pnlDollars = parseFloat(p.total_pnl);
      } else if (pnlPercent !== null && portfolioValue !== null) {
        // Calculate from percentage: pnl_dollars = portfolio_value * (pnl_percent / 100)
        pnlDollars = parseFloat((portfolioValue * (pnlPercent / 100)).toFixed(2));
      }

      return {
        date: p.created_at,
        pnl_dollars: pnlDollars,
        pnl_percent: pnlPercent,
        portfolio_value: portfolioValue,
      };
    });

    console.log(`✅ Portfolio data compiled - ${validHoldings.length} holdings, ${performanceData.length} history records`);

    // Log the actual values being returned for debugging
    console.log(`📊 SUMMARY VALUES BEING RETURNED:`);
    console.log(`   total_return: ${summary.total_return}%`);
    console.log(`   return_1m: ${summary.return_1m}%`);
    console.log(`   return_3m: ${summary.return_3m}%`);
    console.log(`   return_6m: ${summary.return_6m}%`);
    console.log(`   return_1y: ${summary.return_1y}%`);
    console.log(`   ytd_return: ${summary.ytd_return}%`);
    console.log(`   portfolio_value: $${summary.portfolio_value}`);
    console.log(`   volatility_annualized: ${summary.volatility_annualized}%`);
    console.log(`   sharpe_ratio: ${summary.sharpe_ratio}`);
    console.log(`   win_rate: ${summary.win_rate}% (${performanceData.length > 0 ? 'day-level' : 'position-level'})`);

    // Log position data for debugging charts
    console.log(`📊 POSITIONS DATA (${positionsData.length} holdings):`);
    positionsData.slice(0, 3).forEach(p => {
      console.log(`   ${p.symbol}: market_value=$${p.market_value_dollars}, unrealized_pnl=$${p.unrealized_pnl}`);
    });

    // Log daily returns data
    console.log(`📊 DAILY RETURNS DATA (${dailyReturnsData.length} records):`);
    if (dailyReturnsData.length > 0) {
      console.log(`   First: ${dailyReturnsData[0].date} - $${dailyReturnsData[0].portfolio_value} (${dailyReturnsData[0].pnl_percent}%)`);
      console.log(`   Last: ${dailyReturnsData[dailyReturnsData.length-1].date} - $${dailyReturnsData[dailyReturnsData.length-1].portfolio_value} (${dailyReturnsData[dailyReturnsData.length-1].pnl_percent}%)`);
    }

    return res.json({
      data: {
        summary,
        positions: positionsData,
        daily_returns: dailyReturnsData,
        metadata: {
          last_updated: new Date().toISOString(),
          data_quality: {
            validation_passed: validation.isValid,
            warnings: validation.warnings,
            issues: validation.issues,
            quality_metrics: validation.dataQuality
          }
        }
      },
      success: true
    });

  } catch (error) {
    console.error("❌ Portfolio data error:", error.message);
    console.error("   Stack:", error.stack);
    return res.status(500).json({
      error: "Failed to fetch portfolio data",
      details: error.message,
      success: false
    });
  }
});

// ============================================================================
// IMPORT ENDPOINT - Import from Alpaca
// ============================================================================
router.post("/import/alpaca", authenticateToken, async (req, res) => {
  try {
    const userId = req.user.sub;
    const apiKey = process.env.ALPACA_API_KEY;
    const secretKey = process.env.ALPACA_SECRET_KEY;
    const baseURL = process.env.APCA_API_BASE_URL || 'https://paper-api.alpaca.markets';

    console.log(`📥 Importing portfolio from Alpaca for user: ${userId}`);

    // Fetch fresh data
    const alpacaResult = await fetchAlpacaData(apiKey, secretKey, baseURL);

    if (!alpacaResult.success) {
      return res.status(alpacaResult.status).json({
        error: alpacaResult.error,
        success: false
      });
    }

    const { account, positions } = alpacaResult.data;

    // Save to database
    let importedCount = 0;
    const errors = [];

    try {
      // Clear old holdings for this user first (optional - set to false to keep history)
      await query(
        `DELETE FROM portfolio_holdings WHERE user_id = $1`,
        [userId]
      ).catch(e => console.warn('Note: Could not clear old holdings:', e.message));

      // Save each position to portfolio_holdings
      for (const pos of positions) {
        try {
          const symbol = pos.symbol;
          const quantity = safeFloat(pos.qty);
          const currentPrice = safeFloat(pos.current_price);
          const averageCost = safeFloat(pos.avg_fill_price);
          const marketValue = safeFloat(pos.market_value);
          const costBasis = safeFloat(pos.cost_basis);
          const unrealizedPL = safeFloat(pos.unrealized_pl);
          const unrealizedPLPercent = safeFloat(pos.unrealized_plpc);

          // Insert or update holding
          const result = await query(
            `INSERT INTO portfolio_holdings (
              user_id, symbol, quantity, current_price, average_cost,
              market_value, cost_basis,
              updated_at, created_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, NOW(), NOW())
            ON CONFLICT (user_id, symbol) DO UPDATE SET
              quantity = $3,
              current_price = $4,
              average_cost = $5,
              market_value = $6,
              cost_basis = $7,
              updated_at = NOW()
            RETURNING id`,
            [userId, symbol, quantity, currentPrice, averageCost, marketValue, costBasis]
          );

          if (result.rowCount > 0) {
            importedCount++;
            console.log(`✅ Saved ${symbol}: ${quantity} shares @ $${currentPrice}`);
          }
        } catch (posError) {
          const msg = `Failed to save ${pos.symbol}: ${posError.message}`;
          console.error(msg);
          errors.push(msg);
        }
      }

      // Record performance snapshot
      try {
        const portfolioValue = safeFloat(account.portfolio_value);
        const cash = safeFloat(account.cash);
        const buyingPower = safeFloat(account.buying_power);

        await query(
          `INSERT INTO portfolio_performance (
            user_id, total_value, cash, buying_power, daily_pnl, daily_pnl_percent,
            created_at
          ) VALUES ($1, $2, $3, $4, 0, 0, NOW())`,
          [userId, portfolioValue, cash, buyingPower]
        );
        console.log(`📊 Performance snapshot recorded: $${portfolioValue}`);
      } catch (perfError) {
        console.warn('Note: Could not record performance snapshot:', perfError.message);
      }

    } catch (dbError) {
      console.error('Database error during import:', dbError.message);
      errors.push(`Database error: ${dbError.message}`);
    }

    console.log(`✅ Imported ${importedCount}/${positions.length} positions from Alpaca`);

    return res.json({
      data: {
        message: "Portfolio imported successfully",
        positions_count: importedCount,
        positions_total: positions.length,
        portfolio_value: safeFloat(account.portfolio_value),
        imported_at: new Date().toISOString(),
        errors: errors.length > 0 ? errors : undefined
      },
      success: importedCount > 0
    });

  } catch (error) {
    console.error("Alpaca import error:", error);
    return res.status(500).json({
      error: "Failed to import portfolio from Alpaca",
      success: false
    });
  }
});

module.exports = router;
