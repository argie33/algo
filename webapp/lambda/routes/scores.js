const express = require("express");

const { query } = require("../utils/database");

const router = express.Router();

// Root endpoint - returns available sub-endpoints
router.get("/", (req, res) => {
  return res.json({
    data: {
      endpoint: "scores",
      available_routes: [
        "/stockscores - Get stock scores with filtering and sorting (comprehensive data with momentum, quality, value, growth, positioning, stability metrics)"
      ]
    },
    success: true
  });
});

// Helper function to safely convert values to integer
function safeInt(value) {
  if (value === null || value === undefined) return null;
  const num = parseInt(value);
  return isNaN(num) ? null : num;
}

// Helper function to safely convert values to float
function safeFloat(value) {
  if (value === null || value === undefined) return null;
  const num = parseFloat(value);
  return isNaN(num) ? null : num;
}

// Helper: Remove all null values from objects (recursively)
function removeNullValues(obj) {
  if (!obj || typeof obj !== 'object') return obj;

  if (Array.isArray(obj)) {
    return obj.map(item => removeNullValues(item));
  }

  const cleaned = {};
  for (const [key, value] of Object.entries(obj)) {
    if (value === null || value === undefined) {
      continue; // Skip null/undefined values entirely
    }
    if (typeof value === 'object') {
      cleaned[key] = removeNullValues(value);
    } else {
      cleaned[key] = value;
    }
  }
  return cleaned;
}

// Helper: Convert all numeric fields in an object from strings to numbers
// Only converts fields that should be numeric (database might return them as VARCHAR)
function convertMetricValuesToNumbers(metrics) {
  if (!metrics) return metrics;

  const converted = { ...metrics };
  const numericFields = [
    'return_on_equity_pct', 'return_on_assets_pct', 'gross_margin_pct', 'operating_margin_pct',
    'profit_margin_pct', 'fcf_to_net_income', 'operating_cf_to_net_income', 'debt_to_equity',
    'current_ratio', 'quick_ratio', 'earnings_surprise_avg', 'eps_growth_stability', 'payout_ratio',
    'return_on_invested_capital_pct', 'revenue_growth_3y_cagr', 'eps_growth_3y_cagr',
    'operating_income_growth_yoy', 'roe_trend', 'sustainable_growth_rate', 'fcf_growth_yoy',
    'net_income_growth_yoy', 'gross_margin_trend', 'operating_margin_trend', 'net_margin_trend',
    'quarterly_growth_momentum', 'asset_growth_yoy', 'ocf_growth_yoy', 'volatility_12m',
    'downside_volatility', 'max_drawdown_52w', 'beta', 'volume_consistency', 'turnover_velocity',
    'volatility_volume_ratio', 'daily_spread', 'current_price', 'momentum_3m',
    'momentum_6m', 'momentum_12m', 'price_vs_sma_50', 'price_vs_sma_200', 'price_vs_52w_high',
    'rsi', 'macd', 'trailing_pe', 'forward_pe', 'price_to_book', 'price_to_sales_ttm', 'peg_ratio',
    'ev_to_revenue', 'ev_to_ebitda', 'dividend_yield', 'institutional_ownership_pct',
    'top_10_institutions_pct', 'institutional_holders_count', 'insider_ownership_pct',
    'short_ratio', 'short_interest_pct', 'short_percent_of_float', 'ad_rating'
  ];

  numericFields.forEach(field => {
    if (field in converted) {
      converted[field] = safeFloat(converted[field]);
    }
  });

  return converted;
}

// Helper function to BATCH fetch factor input metrics for multiple symbols
// Returns {data: {...}, errors: [...], failedTables: [...], partialSuccess: boolean}
async function getFactorMetricsInBatch(symbols) {
  console.log(`📍 getFactorMetricsInBatch called with ${symbols.length} symbols:`, symbols);
  const result = {
    data: {},
    errors: [],
    failedTables: [],
    partialSuccess: false
  };

  try {
    if (!symbols || symbols.length === 0) return result;

    const tables = [
      ['quality_metrics', 'quality_metrics'],
      ['growth_metrics', 'growth_metrics'],
      ['stability_metrics', 'stability_metrics'],
      ['momentum_metrics', 'momentum_metrics'],
      ['value_metrics', 'value_metrics'],
      ['positioning_metrics', 'positioning_metrics']
    ];
    console.log(`📊 Processing ${tables.length} tables for batch fetch`);

    let successCount = 0;

    // Batch query each table for ALL symbols at once
    for (const [key, table] of tables) {
      try {
        const placeholders = symbols.map((_, i) => `$${i + 1}`).join(',');
        // Use DISTINCT ON to get only the latest row per symbol (most recent date)
        // positioning_metrics doesn't have a date column, so handle differently
        // For value_metrics, prioritize records with non-null values over purely recent records
        let metricsQuery;
        if (table === 'positioning_metrics') {
          // Join with key_metrics to get short_percent_of_float since it doesn't exist in positioning_metrics table
          // key_metrics uses 'ticker' column while positioning_metrics uses 'symbol'
          metricsQuery = `
            SELECT
              pm.symbol, pm.institutional_ownership_pct, pm.top_10_institutions_pct,
              pm.institutional_holders_count, pm.insider_ownership_pct, pm.short_ratio,
              pm.short_interest_pct, pm.ad_rating,
              km.short_percent_of_float
            FROM ${table} pm
            LEFT JOIN key_metrics km ON pm.symbol = km.ticker
            WHERE pm.symbol IN (${placeholders})
          `;
        } else if (table === 'value_metrics') {
          // For value_metrics, merge data from multiple dates to get complete records
          // 2025-12-10 has forward_pe, 2025-12-09 has other metrics - combine via COALESCE
          metricsQuery = `
            WITH ranked AS (
              SELECT symbol, trailing_pe, forward_pe, price_to_book, price_to_sales_ttm,
                     peg_ratio, ev_to_revenue, ev_to_ebitda, dividend_yield, payout_ratio, date,
                     ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) as rn
              FROM ${table}
              WHERE symbol IN (${placeholders})
            ),
            latest_row AS (
              SELECT symbol, trailing_pe, forward_pe, price_to_book, price_to_sales_ttm,
                     peg_ratio, ev_to_revenue, ev_to_ebitda, dividend_yield, payout_ratio, date
              FROM ranked WHERE rn = 1
            ),
            prev_row AS (
              SELECT symbol, trailing_pe, forward_pe, price_to_book, price_to_sales_ttm,
                     peg_ratio, ev_to_revenue, ev_to_ebitda, dividend_yield, payout_ratio, date
              FROM ranked WHERE rn = 2
            )
            SELECT
              l.symbol,
              COALESCE(l.trailing_pe, p.trailing_pe) as trailing_pe,
              COALESCE(l.forward_pe, p.forward_pe) as forward_pe,
              COALESCE(l.price_to_book, p.price_to_book) as price_to_book,
              COALESCE(l.price_to_sales_ttm, p.price_to_sales_ttm) as price_to_sales_ttm,
              COALESCE(l.peg_ratio, p.peg_ratio) as peg_ratio,
              COALESCE(l.ev_to_revenue, p.ev_to_revenue) as ev_to_revenue,
              COALESCE(l.ev_to_ebitda, p.ev_to_ebitda) as ev_to_ebitda,
              COALESCE(l.dividend_yield, p.dividend_yield) as dividend_yield,
              COALESCE(l.payout_ratio, p.payout_ratio) as payout_ratio,
              COALESCE(l.date, p.date) as date
            FROM latest_row l
            LEFT JOIN prev_row p ON l.symbol = p.symbol
          `;
        } else {
          metricsQuery = `
            SELECT DISTINCT ON (symbol)
              symbol, * FROM ${table}
            WHERE symbol IN (${placeholders})
            ORDER BY symbol, date DESC
          `;
        }
        const queryResult = await query(metricsQuery, symbols);

        if (table === 'positioning_metrics') {
          console.log(`✅ positioning_metrics query executed successfully`);
          console.log(`📊 Rows returned:`, (queryResult.rows || []).length);
          if ((queryResult.rows || []).length > 0) {
            console.log(`🔹 Sample row:`, queryResult.rows[0]);
          } else {
            console.log(`⚠️  NO ROWS RETURNED for positioning_metrics! Query returned empty result set.`);
          }
        }

        // Group results by symbol
        for (const row of queryResult.rows || []) {
          const sym = row.symbol;
          if (!result.data[sym]) result.data[sym] = {};

          const rowData = { ...row };
          delete rowData.symbol;
          delete rowData.date;
          // Convert numeric string fields to actual numbers (RULES.md: proper data types)
          result.data[sym][key] = convertMetricValuesToNumbers(rowData);
        }
        successCount++;
      } catch (err) {
        const errorMsg = `Failed to fetch ${table} metrics: ${err.message}`;
        console.error('❌ Batch fetch error:', errorMsg);
        if (table === 'positioning_metrics') {
          console.error(`🔴 POSITIONING_METRICS QUERY ERROR:`);
          console.error(`   Message:`, err.message);
          console.error(`   Stack:`, err.stack);
          console.error(`   Query attempted:`, metricsQuery);
          console.error(`   Parameters:`, symbols);
        }
        result.errors.push({
          table,
          error: err.message,
          timestamp: new Date().toISOString()
        });
        result.failedTables.push(table);
      }
    }

    // Track if this was a partial success
    result.partialSuccess = successCount > 0 && result.failedTables.length > 0;
    result.successfulTables = tables.length - result.failedTables.length;
    result.totalTables = tables.length;

    return result;
  } catch (error) {
    const errorMsg = `Critical error in batch fetch: ${error.message}`;
    console.error('❌', errorMsg);
    result.errors.push({
      level: 'critical',
      error: errorMsg,
      stack: error.stack,
      timestamp: new Date().toISOString()
    });
    return result;
  }
}

// Helper function to BATCH fetch RSI and MACD data for momentum metrics
// Returns {data: {...}, errors: [...], partialSuccess: boolean}
async function getRSIAndMACDDataInBatch(symbols) {
  const result = {
    data: {},
    errors: [],
    partialSuccess: false
  };

  try {
    if (!symbols || symbols.length === 0) return result;

    // Fetch from technical_data_daily table - use DISTINCT ON to get latest date per symbol
    try {
      const placeholders = symbols.map((_, i) => `$${i + 1}`).join(',');
      const query_str = `
        SELECT DISTINCT ON (symbol)
          symbol, rsi, macd, date
        FROM technical_data_daily
        WHERE symbol IN (${placeholders})
        ORDER BY symbol, date DESC
      `;
      const queryResult = await query(query_str, symbols);

      for (const row of queryResult.rows || []) {
        const sym = row.symbol;
        result.data[sym] = {
          rsi: safeFloat(row.rsi),
          macd: safeFloat(row.macd),
          date: row.date
        };
      }
      result.fetchedCount = queryResult.rows.length;
    } catch (err) {
      const errorMsg = `Failed to fetch RSI/MACD from technical_data_daily: ${err.message}`;
      console.error('❌ Batch fetch error:', errorMsg);
      result.errors.push({
        table: 'technical_data_daily',
        error: err.message,
        timestamp: new Date().toISOString()
      });
      result.partialSuccess = Object.keys(result.data).length > 0;
    }

    return result;
  } catch (error) {
    const errorMsg = `Critical error in RSI/MACD batch fetch: ${error.message}`;
    console.error('❌', errorMsg);
    result.errors.push({
      level: 'critical',
      error: errorMsg,
      timestamp: new Date().toISOString()
    });
    return result;
  }
}

// Helper function to BATCH fetch insider data (transactions & roster) for multiple symbols
async function getInsiderDataInBatch(symbols) {
  try {
    if (!symbols || symbols.length === 0) return {};

    const insiderMap = {};

    // Initialize map for each symbol
    for (const sym of symbols) {
      insiderMap[sym] = {
        insider_transactions: [],
        insider_roster: [],
        institutional_positioning: []
      };
    }

    // Fetch insider transactions (90-day lookback)
    try {
      const placeholders = symbols.map((_, i) => `$${i + 1}`).join(',');
      const txnQuery = `
        SELECT symbol, insider_name, position, transaction_type, shares, value,
               transaction_date, ownership_type
        FROM insider_transactions
        WHERE symbol IN (${placeholders})
        AND transaction_date >= CURRENT_DATE - INTERVAL '90 days'
        ORDER BY symbol, transaction_date DESC
      `;
      const txnResult = await query(txnQuery, symbols);
      for (const row of txnResult.rows || []) {
        const sym = row.symbol;
        if (insiderMap[sym]) {
          insiderMap[sym].insider_transactions.push({
            insider_name: row.insider_name,
            position: row.position,
            transaction_type: row.transaction_type,
            shares: safeInt(row.shares),
            value: safeFloat(row.value),
            transaction_date: row.transaction_date,
            ownership_type: row.ownership_type
          });
        }
      }
    } catch (err) {
      console.warn(`⚠️  Failed to fetch insider_transactions:`, err.message);
    }

    // Fetch insider roster (current holdings)
    try {
      const placeholders = symbols.map((_, i) => `$${i + 1}`).join(',');
      const rosterQuery = `
        SELECT symbol, insider_name, position, most_recent_transaction,
               latest_transaction_date, shares_owned_directly, position_direct_date
        FROM insider_roster
        WHERE symbol IN (${placeholders})
        ORDER BY symbol, shares_owned_directly DESC
      `;
      const rosterResult = await query(rosterQuery, symbols);
      for (const row of rosterResult.rows || []) {
        const sym = row.symbol;
        if (insiderMap[sym]) {
          insiderMap[sym].insider_roster.push({
            insider_name: row.insider_name,
            position: row.position,
            most_recent_transaction: row.most_recent_transaction,
            latest_transaction_date: row.latest_transaction_date,
            shares_owned_directly: safeInt(row.shares_owned_directly),
            position_direct_date: row.position_direct_date
          });
        }
      }
    } catch (err) {
      console.warn(`⚠️  Failed to fetch insider_roster:`, err.message);
    }

    // Fetch institutional positioning (smart money - mutual funds, hedge funds, etc)
    try {
      const placeholders = symbols.map((_, i) => `$${i + 1}`).join(',');
      const instQuery = `
        SELECT symbol, institution_type, institution_name, position_size,
               position_change_percent, market_share, filing_date, quarter
        FROM institutional_positioning
        WHERE symbol IN (${placeholders})
        AND institution_type IN ('HEDGE_FUND', 'MUTUAL_FUND')
        ORDER BY symbol, filing_date DESC, position_size DESC
        LIMIT 20 OFFSET 0
      `;
      const instResult = await query(instQuery, symbols);
      for (const row of instResult.rows || []) {
        const sym = row.symbol;
        if (insiderMap[sym]) {
          insiderMap[sym].institutional_positioning.push({
            institution_type: row.institution_type,
            institution_name: row.institution_name,
            position_size: safeFloat(row.position_size),
            position_change_percent: safeFloat(row.position_change_percent),
            market_share: safeFloat(row.market_share),
            filing_date: row.filing_date,
            quarter: row.quarter
          });
        }
      }
    } catch (err) {
      console.warn(`⚠️  Failed to fetch institutional_positioning:`, err.message);
    }

    return insiderMap;
  } catch (error) {
    console.error('Error fetching insider data in batch:', error);
    return {};
  }
}

// Standard columns returned from stock_scores table
const SCORE_COLUMNS = [
  'symbol',
  'company_name',
  'composite_score',
  'momentum_score',
  'momentum_3m',
  'momentum_6m',
  'momentum_12m',
  'value_score',
  'quality_score',
  'growth_score',
  'positioning_score',
  'stability_score',
  'beta',
  'short_interest',
  'accumulation_distribution',
  'last_updated'
];

// Allowed sort columns for safety
const ALLOWED_SORT_COLUMNS = [
  'composite_score',
  'momentum_score',
  'value_score',
  'quality_score',
  'growth_score',
  'stability_score',
  'positioning_score',
  'current_price'
];

// Unified query builder for stock scores
async function queryScores(options = {}) {
  const {
    limit = 50,
    offset = 0,
    search = '',
    sortBy = 'composite_score',
    sortOrder = 'DESC',
    symbols = null,
    singleSymbol = null,
    filter = null // for filtering by composite_score IS NOT NULL, etc
  } = options;

  // Validate and sanitize parameters
  const validatedLimit = Math.max(1, Math.min(parseInt(limit, 10) || 50, 1000));
  const validatedOffset = Math.max(0, safeInt(offset) || 0);
  const validatedSort = ALLOWED_SORT_COLUMNS.includes(sortBy) ? sortBy : 'composite_score';
  const validatedOrder = sortOrder.toUpperCase() === 'ASC' ? 'ASC' : 'DESC';

  // Build WHERE clauses
  let whereConditions = [];
  let queryParams = [];
  let paramIndex = 1;

  // Exclude SPACs and blank check companies - filter by multiple naming patterns
  whereConditions.push(`NOT EXISTS (SELECT 1 FROM stock_symbols WHERE symbol = ss.symbol AND (security_name ILIKE '%SPAC%' OR security_name ILIKE '%Special Purpose%' OR security_name ILIKE '%Equity Partners%' OR security_name ILIKE '%Blank Check%' OR security_name ILIKE '%Acquisition Company%'))`);

  // Add search filter
  if (search) {
    whereConditions.push(`ss.symbol ILIKE $${paramIndex}`);
    queryParams.push(`%${search.toUpperCase()}%`);
    paramIndex++;
  }

  // Add symbols filter
  if (symbols && symbols.length > 0) {
    const placeholders = symbols.map(() => `$${paramIndex++}`).join(',');
    whereConditions.push(`ss.symbol IN (${placeholders})`);
    queryParams.push(...symbols.map(s => s.toUpperCase()));
  }

  // Add single symbol filter
  if (singleSymbol) {
    whereConditions.push(`ss.symbol = $${paramIndex}`);
    queryParams.push(singleSymbol.toUpperCase());
    paramIndex++;
  }

  // Add custom filter (e.g., for /top endpoint)
  if (filter) {
    whereConditions.push(filter);
  }

  const whereClause = whereConditions.length > 0 ? 'WHERE ' + whereConditions.join(' AND ') : '';

  // Build SELECT columns
  const selectCols = SCORE_COLUMNS.join(', ');

  // Count query for pagination
  const countQuery = `SELECT COUNT(*) as total FROM stock_scores ss ${whereClause}`;
  const countResult = await query(countQuery, queryParams);
  const totalCount = safeInt(countResult.rows[0]?.total) || 0;

  // Data query with pagination
  const dataQuery = `
    SELECT ${selectCols}
    FROM stock_scores ss
    ${whereClause}
    ORDER BY ss.${validatedSort} ${validatedOrder} NULLS LAST, ss.symbol ASC
    LIMIT $${paramIndex} OFFSET $${paramIndex + 1}
  `;

  const dataParams = [...queryParams, validatedLimit, validatedOffset];
  const result = await query(dataQuery, dataParams);

  // BATCH fetch factor metrics for ALL stocks at once (not per-stock)
  const symbolList = (result.rows || []).map(row => row.symbol.toUpperCase());
  const metricsMap = await getFactorMetricsInBatch(symbolList);
  const insiderMap = await getInsiderDataInBatch(symbolList);
  const rsiMacdMap = await getRSIAndMACDDataInBatch(symbolList);

  // Log batch fetch warnings (partial failures are OK, allow data to display)
  // Per RULES.md: Return real data when available, null when unavailable (not fake defaults)
  if (metricsMap.errors && metricsMap.errors.length > 0) {
    console.warn(`⚠️  Some factor metrics unavailable (partial):`, metricsMap.errors.map(e => e.table || e.error).join(', '));
  }
  if (insiderMap.errors && insiderMap.errors.length > 0) {
    console.warn(`⚠️  Some insider data unavailable (partial):`, insiderMap.errors.map(e => e.error).join(', '));
  }
  if (rsiMacdMap.errors && rsiMacdMap.errors.length > 0) {
    console.warn(`⚠️  Some RSI/MACD data unavailable (partial):`, rsiMacdMap.errors.map(e => e.error).join(', '));
  }

  // Allow partial success - return available data with nulls for unavailable data
  // Prevent complete failure unless NO data was returned at all
  const hasAnyData = metricsMap.partialSuccess || Object.keys(metricsMap.data).length > 0 ||
                     insiderMap.partialSuccess || Object.keys(insiderMap).length > 1 ||
                     rsiMacdMap.partialSuccess || Object.keys(rsiMacdMap.data).length > 0;

  if (!hasAnyData && symbolList.length > 0) {
    console.error('❌ COMPLETE DATA FETCH FAILURE: All batch fetches failed');
    const error = new Error("Unable to fetch stock data - all critical sources failed");
    error.statusCode = 503;
    throw error;
  }

  // Format results with factor input metrics and insider data
  const stocks = [];
  for (const row of result.rows || []) {
    const stock = {
      symbol: row.symbol,
      company_name: row.company_name,
      composite_score: row.composite_score == null ? null : parseFloat(row.composite_score),
      momentum_score: row.momentum_score == null ? null : parseFloat(row.momentum_score),
      momentum_3m: row.momentum_3m == null ? null : parseFloat(row.momentum_3m),
      momentum_6m: row.momentum_6m == null ? null : parseFloat(row.momentum_6m),
      momentum_12m: row.momentum_12m == null ? null : parseFloat(row.momentum_12m),
      value_score: row.value_score == null ? null : parseFloat(row.value_score),
      quality_score: row.quality_score == null ? null : parseFloat(row.quality_score),
      growth_score: row.growth_score == null ? null : parseFloat(row.growth_score),
      positioning_score: row.positioning_score == null ? null : parseFloat(row.positioning_score),
      stability_score: row.stability_score == null ? null : parseFloat(row.stability_score),
      last_updated: row.last_updated
    };

    // Populate top-level momentum fields from momentum_inputs if they're still null
    // This ensures we always have the momentum values available
    const momentumMetrics = metricsMap.data[row.symbol.toUpperCase()]?.momentum_metrics;
    if (momentumMetrics && stock.momentum_3m == null && momentumMetrics.momentum_3m != null) {
      stock.momentum_3m = parseFloat(momentumMetrics.momentum_3m);
    }
    if (momentumMetrics && stock.momentum_6m == null && momentumMetrics.momentum_6m != null) {
      stock.momentum_6m = parseFloat(momentumMetrics.momentum_6m);
    }
    if (momentumMetrics && stock.momentum_12m == null && momentumMetrics.momentum_12m != null) {
      stock.momentum_12m = parseFloat(momentumMetrics.momentum_12m);
    }

    // Attach factor metrics from batch result (already fetched)
    // Helper: Remove metadata fields from metric objects
    const cleanMetrics = (metrics) => {
      if (!metrics) return metrics;
      const { id, created_at, fetched_at, ...cleaned } = metrics;
      return cleaned;
    };

    // Map database field names to frontend-expected field names
    const metrics = metricsMap.data[row.symbol.toUpperCase()];
    if (metrics) {
      stock.quality_inputs = cleanMetrics(metrics.quality_metrics);
      stock.growth_inputs = cleanMetrics(metrics.growth_metrics);
      stock.stability_inputs = cleanMetrics(metrics.stability_metrics);

      // Add beta to stability_inputs (factor metric from stock_scores table)
      if (stock.stability_inputs && row.beta != null) {
        stock.stability_inputs.beta = parseFloat(row.beta);
      }

      // Add volatility_risk_component to stability_inputs (derived from downside_volatility)
      if (stock.stability_inputs) {
        if (metrics.stability_metrics && metrics.stability_metrics.downside_volatility != null) {
          // volatility_risk_component is the inverse: lower downside vol = higher risk component score
          stock.stability_inputs.volatility_risk_component = 100 - metrics.stability_metrics.downside_volatility;
        } else {
          stock.stability_inputs.volatility_risk_component = null;
        }
      }


      // Map momentum metrics field names to match frontend expectations
      // Note: Database has momentum_3m/6m/12m, current_price, price_vs_sma_50/200, price_vs_52w_high, rsi, macd
      if (metrics.momentum_metrics) {
        // Get RSI and MACD from either momentum_metrics or rsiMacdMap
        const rsiValue = metrics.momentum_metrics.rsi || (rsiMacdMap.data[row.symbol.toUpperCase()] && rsiMacdMap.data[row.symbol.toUpperCase()].rsi);
        const macdValue = metrics.momentum_metrics.macd || (rsiMacdMap.data[row.symbol.toUpperCase()] && rsiMacdMap.data[row.symbol.toUpperCase()].macd);

        const cleaned = cleanMetrics(metrics.momentum_metrics);
        stock.momentum_inputs = {
          ...cleaned,
          momentum_12_3: cleaned.momentum_12m
          // Removed: id, created_at, rsi, macd (duplicates), momentum_12m (use momentum_12_3 instead)
        };
        delete stock.momentum_inputs.momentum_12m; // Remove duplicate, use momentum_12_3 instead

        // Also add RSI and MACD to top-level stock object (frontend expects them there)
        stock.rsi = rsiValue;
        stock.macd = macdValue;
      }

      // Map value metrics field names to match frontend expectations
      // Note: Database has trailing_pe, forward_pe, price_to_book, price_to_sales_ttm, ev_to_revenue, ev_to_ebitda, dividend_yield, payout_ratio, peg_ratio
      if (metrics.value_metrics) {
        const cleaned = cleanMetrics(metrics.value_metrics);
        stock.value_inputs = {
          ...cleaned,
          stock_pe: cleaned.trailing_pe,
          stock_forward_pe: cleaned.forward_pe,
          stock_pb: cleaned.price_to_book,
          stock_ps: cleaned.price_to_sales_ttm,
          stock_ev_revenue: cleaned.ev_to_revenue,
          stock_ev_ebitda: cleaned.ev_to_ebitda,
          stock_dividend_yield: cleaned.dividend_yield,
          peg_ratio: cleaned.peg_ratio,
          // stock_fcf_yield removed completely
        };
      }

      // Map positioning metrics field names to match frontend expectations
      // Note: Database has institutional_ownership_pct, top_10_institutions_pct, insider_ownership_pct, short_ratio, short_interest_pct, short_percent_of_float, ad_rating
      if (metrics.positioning_metrics) {
        const cleaned = cleanMetrics(metrics.positioning_metrics);
        stock.positioning_inputs = {
          institutional_ownership_pct: cleaned.institutional_ownership_pct,
          top_10_institutions_pct: cleaned.top_10_institutions_pct,
          institutional_holders_count: cleaned.institutional_holders_count,
          insider_ownership_pct: cleaned.insider_ownership_pct,
          short_ratio: cleaned.short_ratio,
          short_interest_pct: cleaned.short_interest_pct,
          short_percent_of_float: cleaned.short_percent_of_float,
          ad_rating: cleaned.ad_rating // Synced from stock_scores.momentum_intraweek by loader
        };

        // Build score_breakdown object from positioning inputs for frontend display
        stock.score_breakdown = {
          institutional: cleaned.institutional_ownership_pct,
          insider: cleaned.insider_ownership_pct,
          short_interest: cleaned.short_interest_pct,
          smart_money: null // Will be calculated from institutional_positioning data below
        };
      }
    }

    // Calculate smart_money score from institutional positioning (hedge funds + mutual funds activity)
    const insiderData = insiderMap[row.symbol.toUpperCase()];
    if (insiderData && insiderData.institutional_positioning && insiderData.institutional_positioning.length > 0) {
      // Average the position change percent for recent filings (smart money flow)
      const recentChanges = insiderData.institutional_positioning
        .slice(0, 5) // Top 5 most recent/largest positions
        .map(p => safeFloat(p.position_change_percent))
        .filter(v => v !== null);

      if (recentChanges.length > 0) {
        const smartMoneyScore = recentChanges.reduce((a, b) => a + b, 0) / recentChanges.length;
        if (stock.score_breakdown) {
          stock.score_breakdown.smart_money = smartMoneyScore;
        }
      }
    }
    // NOTE: insider_transactions and insider_roster removed - not displayed in UI

    stocks.push(stock);
  }

  return {
    stocks,
    count: stocks.length,
    total: totalCount,
    limit: validatedLimit,
    offset: validatedOffset
  };
}

// REMOVED: Router-level diagnostic middleware
// This was logging ALL requests causing performance degradation
// Moved debug logging to separate debug routes only

// Paginated stock scores endpoint
router.get("/stockscores", async (req, res) => {
  try {
    const result = await queryScores({
      limit: req.query.limit,
      offset: req.query.offset,
      search: req.query.search,
      sortBy: req.query.sortBy,
      sortOrder: req.query.sortOrder
    });
    const page = Math.floor(result.offset / result.limit) + 1;
    const totalPages = Math.ceil(result.total / result.limit);
    const hasNext = page < totalPages;
    const hasPrev = page > 1;
    // Remove all null values from stocks before returning
    const cleanedStocks = removeNullValues(result.stocks);
    res.json({ items: cleanedStocks, pagination: { page, limit: result.limit, total: result.total, totalPages, hasNext, hasPrev }, success: true });
  } catch (error) {
    console.error("Error fetching stock scores:", error);
    const statusCode = error.statusCode || 500;
    res.status(statusCode).json({ error: error.message || "Failed to fetch stock scores", success: false });
  }
});

// REMOVED: /top endpoint (duplicate of /stockscores with hardcoded filter)
// REMOVED: /leaders and /stability-leaders endpoints (consolidated into /stockscores)
// TopPerformersByCategory component now fetches directly from stockscores endpoint

// REMOVED: /sector/:name and /industry/:name endpoints
// These endpoints are now consolidated in sectors.js for better organization:
// - GET /api/sectors/sector/:name - Returns sector ranking data
// - GET /api/sectors/trend/industry/:industryName - Returns industry trend data
// - GET /api/sectors/technical-details/industry/:industryName - Returns industry technical analysis
//
// Consolidation rationale:
// - Clearer API structure: /api/sectors/* for all sector/industry endpoints
// - Avoids redundancy: Multiple endpoints for the same data removed
// - Better RESTful design: Hierarchical path structure (sector → industry)

module.exports = router;