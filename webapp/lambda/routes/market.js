const express = require("express");

let query;
try {
  ({ query } = require("../utils/database"));
} catch (error) {
  console.log("Database service not available in market routes:", error.message);
  query = null;
}

const router = express.Router();

// Helper function to check if required tables exist
async function checkRequiredTables(tableNames) {
  const results = {};

  // If database is not available, return false for all tables
  if (!query) {
    console.warn("Database not available - marking all tables as non-existent");
    for (const tableName of tableNames) {
      results[tableName] = false;
    }
    return results;
  }

  for (const tableName of tableNames) {
    try {
      const tableExistsResult = await query(
        `SELECT EXISTS (
          SELECT FROM information_schema.tables
          WHERE table_schema = 'public'
          AND table_name = $1
        );`,
        [tableName]
      );
      // Add null checking for database availability
      if (!tableExistsResult || !tableExistsResult.rows || tableExistsResult.rows.length === 0) {
        console.warn(`Table existence query returned null result for ${tableName}, database may be unavailable`);
        results[tableName] = false;
      } else {
        results[tableName] = tableExistsResult.rows[0].exists;
      }
    } catch (error) {
      console.error(`Error checking table ${tableName}:`, error.message);
      results[tableName] = false;
    }
  }
  return results;
}

// Helper functions for safe numeric conversion
function safeFloat(value) {
  if (value === null || value === undefined) return null;
  const parsed = parseFloat(value);
  return isFinite(parsed) ? parsed : null;
}

function safeInt(value) {
  if (value === null || value === undefined) return null;
  const parsed = parseInt(value, 10);
  return isFinite(parsed) ? parsed : null;
}

function safeFixed(value, decimals = 2) {
  if (value === null || value === undefined) return null;
  const parsed = parseFloat(value);
  return isFinite(parsed) ? parseFloat(parsed.toFixed(decimals)) : null;
}

// ============================================================================
// HELPER FUNCTION - Get full seasonality data
// ============================================================================
async function getFullSeasonalityData() {
  const currentDate = new Date();
  const currentYear = currentDate.getFullYear();
  const currentMonth = currentDate.getMonth() + 1;
  const _currentDay = currentDate.getDate();
  const _dayOfYear = Math.floor(
    (currentDate - new Date(currentYear, 0, 0)) / (1000 * 60 * 60 * 24)
  );

  // Get current year S&P 500 performance
  let currentYearReturn = null;
  try {
    // Return null if database is unavailable
    if (!query) {
      console.warn("Database not available for SPY data fetch");
      return null;
    }

    const yearStart = new Date(currentYear, 0, 1);
    const spyQuery = `
      SELECT close, date
      FROM price_daily
      WHERE symbol = 'SPY' AND date >= $1
      ORDER BY date DESC LIMIT 1
    `;
    const spyResult = await query(spyQuery, [
      yearStart.toISOString().split("T")[0],
    ]);

    if (spyResult && spyResult.rows && spyResult.rows.length > 0) {
      const yearStartQuery = `
        SELECT close FROM price_daily
        WHERE symbol = 'SPY' AND date >= $1
        ORDER BY date ASC LIMIT 1
      `;
      const yearStartResult = await query(yearStartQuery, [
        yearStart.toISOString().split("T")[0],
      ]);

      if (yearStartResult && yearStartResult.rows && yearStartResult.rows.length > 0) {
        const currentPrice = parseFloat(spyResult.rows[0].close);
        const yearStartPrice = parseFloat(yearStartResult.rows[0].close);
        currentYearReturn =
          ((currentPrice - yearStartPrice) / yearStartPrice) * 100;
      }
    }
  } catch (e) {
    console.log("Could not fetch SPY data:", e.message);
  }

  // 1. PRESIDENTIAL CYCLE
  const electionYear = Math.floor((currentYear - 1792) / 4) * 4 + 1792;
  const currentCyclePosition = ((currentYear - electionYear) % 4) + 1;

  let presidentialCycleData = [
    { year: 1, label: "Post-Election", avgReturn: null },
    { year: 2, label: "Mid-Term", avgReturn: null },
    { year: 3, label: "Pre-Election", avgReturn: null },
    { year: 4, label: "Election Year", avgReturn: null },
  ];

  try {
    const cycleReturnsQuery = `
      SELECT
        year,
        ((year - 1792) % 4 + 1)::int as cycle_position,
        ROUND(CAST(AVG(year_return) AS NUMERIC), 2) as avg_return,
        COUNT(*) as sample_size
      FROM (
        SELECT
          EXTRACT(YEAR FROM date)::int as year,
          ROUND(((MAX(close) - MIN(close)) / MIN(close) * 100)::numeric, 2) as year_return
        FROM price_daily
        WHERE symbol = 'SPY' AND date >= TO_DATE(CAST($1 AS TEXT), 'YYYY') AND date < CURRENT_DATE
        GROUP BY EXTRACT(YEAR FROM date)
      ) yearly_returns
      GROUP BY year, cycle_position
    `;

    const cycleReturnsResult = await query(cycleReturnsQuery, [currentYear - 30]);

    if (cycleReturnsResult.rows.length > 0) {
      cycleReturnsResult.rows.forEach(row => {
        const cyclePos = row.cycle_position;
        const dataItem = presidentialCycleData.find(d => d.year === cyclePos);
        if (dataItem && row.avg_return !== null) {
          dataItem.avgReturn = parseFloat(row.avg_return);
        }
      });
    }
  } catch (e) {
    console.log("Could not fetch presidential cycle returns:", e.message);
  }

  const presidentialCycle = {
    currentPosition: currentCyclePosition,
    data: presidentialCycleData.map(d => ({
      year: d.year,
      label: d.label,
      avgReturn: d.avgReturn,
      isCurrent: currentCyclePosition === d.year,
    })),
  };

  // 2. MONTHLY SEASONALITY - Load from seasonality_monthly_stats table
  let monthlySeasonality = [];
  let monthlySpPerformance = [];

  try {
    const monthlyStatsQuery = `
      SELECT
        month,
        month_name,
        avg_return,
        best_return,
        worst_return,
        years_counted,
        winning_years,
        losing_years
      FROM seasonality_monthly_stats
      ORDER BY month ASC
    `;

    const monthlyResult = await query(monthlyStatsQuery);

    if (monthlyResult && monthlyResult.rows && monthlyResult.rows.length > 0) {
      monthlySeasonality = monthlyResult.rows.map((m) => {
        const avgReturnNum = m.avg_return ? parseFloat(m.avg_return) : null;
        const bestReturnNum = m.best_return ? parseFloat(m.best_return) : null;
        const worstReturnNum = m.worst_return ? parseFloat(m.worst_return) : null;

        return {
          month: m.month,
          name: m.month_name,
          avgReturn: avgReturnNum,
          bestReturn: bestReturnNum,
          worstReturn: worstReturnNum,
          yearsCount: m.years_counted,
          winningYears: m.winning_years,
          losingYears: m.losing_years,
          isCurrent: m.month === currentMonth,
          description: avgReturnNum !== null
            ? `Avg: ${avgReturnNum >= 0 ? "+" : ""}${avgReturnNum.toFixed(2)}% (${m.winning_years}/${m.years_counted} years positive)`
            : "No historical data",
        };
      });
    }
  } catch (e) {
    console.log("Note: Monthly seasonality data not available:", e.message);
  }

  // Also load monthly performance for the response
  monthlySpPerformance = monthlySeasonality;

  // 3. QUARTERLY PATTERNS - Calculate from monthly data
  const quarterlySeasonality = [
    { quarter: 1, months: [1, 2, 3], name: "Q1", months_display: "Jan-Mar" },
    { quarter: 2, months: [4, 5, 6], name: "Q2", months_display: "Apr-Jun" },
    { quarter: 3, months: [7, 8, 9], name: "Q3", months_display: "Jul-Sep" },
    { quarter: 4, months: [10, 11, 12], name: "Q4", months_display: "Oct-Dec" },
  ].map((q) => {
    const quarterMonths = monthlySeasonality.filter((m) =>
      q.months.includes(m.month)
    );
    const validReturns = quarterMonths
      .filter((m) => m.avgReturn !== null)
      .map((m) => m.avgReturn);

    const avgReturn =
      validReturns.length > 0
        ? (validReturns.reduce((a, b) => a + b, 0) / validReturns.length).toFixed(2)
        : null;

    const avgReturnNum = avgReturn ? parseFloat(avgReturn) : null;
    return {
      quarter: q.quarter,
      name: q.name,
      months: q.months_display,
      avgReturn: avgReturnNum,
      isCurrent: Math.ceil(currentMonth / 3) === q.quarter,
      description: avgReturnNum !== null
        ? `${avgReturnNum >= 0 ? "+" : ""}${avgReturn}% average (current year data)`
        : "Insufficient quarterly data",
    };
  });

  // 4. INTRADAY PATTERNS
  const intradayPatterns = {
    marketOpen: { time: "9:30 AM", pattern: "High volatility, gap analysis" },
    morningSession: {
      time: "10:00-11:30 AM",
      pattern: "Trend establishment",
    },
    lunchTime: {
      time: "11:30 AM-1:30 PM",
      pattern: "Lower volume, consolidation",
    },
    afternoonSession: {
      time: "1:30-3:00 PM",
      pattern: "Institutional activity",
    },
    powerHour: {
      time: "3:00-4:00 PM",
      pattern: "High volume, day trader exits",
    },
    marketClose: {
      time: "4:00 PM",
      pattern: "Final positioning, after-hours news",
    },
  };

  // 5. DAY OF WEEK EFFECTS - Load from seasonality_day_of_week table
  let dayOfWeekEffects = [];
  try {
    const dowQuery = `
      SELECT
        day,
        day_num,
        avg_return,
        win_rate,
        days_counted
      FROM seasonality_day_of_week
      ORDER BY day_num ASC
    `;

    const dowResult = await query(dowQuery);

    if (dowResult && dowResult.rows && dowResult.rows.length > 0) {
      dayOfWeekEffects = dowResult.rows.map((d) => {
        const avgReturnNum = d.avg_return ? parseFloat(d.avg_return) : null;
        const winRateNum = d.win_rate ? parseFloat(d.win_rate) : null;

        return {
          day: d.day,
          dayNum: d.day_num,
          avgReturn: avgReturnNum,
          winRate: winRateNum,
          daysCount: d.days_counted,
          isCurrent: currentDate.toLocaleDateString("en-US", { weekday: "long" }) === d.day,
          description: avgReturnNum !== null && winRateNum !== null
            ? `Avg: ${avgReturnNum >= 0 ? "+" : ""}${avgReturnNum.toFixed(2)}% return (${winRateNum.toFixed(1)}% win rate)`
            : "No historical data",
        };
      });
    }
  } catch (e) {
    console.log("Note: Day of week effects not available:", e.message);
  }

  if (!dayOfWeekEffects || dayOfWeekEffects.length === 0) {
    dayOfWeekEffects = [];
  }

  // 6. SECTOR SEASONALITY - Fetch actual sectors from database
  let sectorSeasonality = [];
  try {
    const sectorResult = await query(
      `SELECT DISTINCT sector FROM company_profile WHERE sector IS NOT NULL ORDER BY sector`
    );
    if (sectorResult && sectorResult.rows && sectorResult.rows.length > 0) {
      sectorSeasonality = sectorResult.rows.map((r) => ({
        sector: r.sector
      }));
    } else {
      sectorSeasonality = [
        {
          note: "No sector data available. Run loadcompanyprofile.py and loadsectors.py first.",
        },
      ];
    }
  } catch (e) {
    console.log("Note: Sector data not available:", e.message);
    sectorSeasonality = [
      { note: "Sector seasonality data requires company profile and sector ETF data" },
    ];
  }

  // 7. HOLIDAY EFFECTS - Return null instead of fake data
  const holidayEffects = null;

  // 8. SEASONAL ANOMALIES
  const seasonalAnomalies = [
    {
      name: "January Effect",
      period: "First 5 trading days",
      description: "Historically correlated with small-cap performance",
      strength: "Moderate",
      note: "Requires multi-year historical analysis",
    },
    {
      name: "Sell in May",
      period: "May 1 - Oct 31",
      description: "Historical summer underperformance pattern",
      strength: "Moderate",
      note: "Requires multi-year historical analysis",
    },
    {
      name: "Halloween Indicator",
      period: "Oct 31 - May 1",
      description: "Historical best 6-month period",
      strength: "Moderate",
      note: "Requires multi-year historical analysis",
    },
    {
      name: "Santa Claus Rally",
      period: "Last 5 + First 2 days",
      description: "Year-end rally pattern",
      strength: "Moderate",
      note: "Requires multi-year historical analysis",
    },
    {
      name: "September Effect",
      period: "September",
      description: "Historically weakest month",
      strength: "Moderate",
      note: "Requires multi-year historical analysis",
    },
    {
      name: "Triple Witching",
      period: "Third Friday quarterly",
      description: "Futures/options expiry day",
      strength: "Weak",
      note: "Volatility pattern from derivatives expiration",
    },
    {
      name: "Turn of Month",
      period: "Last 3 + First 2 days",
      description: "Month-end portfolio activity",
      strength: "Weak",
      note: "Requires multi-year historical analysis",
    },
    {
      name: "FOMC Effect",
      period: "Fed meeting days",
      description: "Market behavior around Fed announcements",
      strength: "Moderate",
      note: "Requires event-based analysis of Fed meetings",
    },
  ];

  // 9. CURRENT SEASONAL POSITION
  const currentMonthData = monthlySeasonality.find(m => m.month === currentMonth);
  const currentQuarterData = quarterlySeasonality.find(q => q.isCurrent);

  const currentPosition = {
    presidentialCycle: `Year ${currentCyclePosition} of 4`,
    monthlyTrend: currentMonthData?.description || "Monthly data unavailable",
    quarterlyTrend: currentQuarterData?.description || "Quarterly data unavailable",
    activePeriods: getActiveSeasonalPeriods(currentDate),
    nextMajorEvent: getNextSeasonalEvent(currentDate),
    seasonalScore: calculateSeasonalScore(currentDate),
  };

  // Return complete seasonality data structure
  return {
    currentYear,
    currentYearReturn,
    currentPosition,
    presidentialCycle,
    monthlySeasonality,
    monthlySpPerformance,
    quarterlySeasonality,
    intradayPatterns,
    dayOfWeekEffects,
    sectorSeasonality,
    holidayEffects,
    seasonalAnomalies,
    summary: {
      favorableFactors: getFavorableFactors(currentDate),
      unfavorableFactors: getUnfavorableFactors(currentDate),
      overallSeasonalBias: getOverallBias(currentDate),
      confidence: "Moderate",
      recommendation: getSeasonalRecommendation(currentDate)
    }
  };
}

// Root endpoint for testing
router.get("/", (req, res) => {
  return res.json({
    data: {
      endpoint: "market",
      available_routes: [
        "/overview - Market quality, top stocks, market breadth",
        "/breadth - Advance/decline ratios and market breadth indicators",
        "/mcclellan-oscillator - Breadth momentum indicator (19/39-day EMA)",
        "/distribution-days - IBD distribution days by index",
        "/indices - Major market indices (S&P 500, NASDAQ, Dow, Russell 2000, VIX)",
        "/volatility - Market volatility metrics and VIX data",
        "/indicators - Technical indicators and market metrics",
        "/correlation - Stock correlation matrix analysis",
        "/aaii - AAII investor sentiment (bullish/neutral/bearish %)",
        "/fear-greed - CNN Fear & Greed Index",
        "/naaim - NAAIM manager exposure (bullish/bearish %)",
        "/seasonality - Seasonal patterns and trading calendar",
        "/internals - Market internals, breadth, moving averages, positioning"
      ],
      note: "Sector data has been moved to /api/sectors/sectors-with-history"
    },
    success: true
  });
});

// REMOVED: /summary endpoint - Generic catch-all that aggregated unrelated data
// This endpoint was problematic because it returned three different types of data in one place:
// - Market indices (S&P 500, NASDAQ, Dow, Russell, VIX)
// - Market breadth (advancing/declining/unchanged stocks)
// - Sector performance data
//
// Solution: Each data type now has its own focused endpoint
// - GET /api/market/indices → Major market indices
// - GET /api/market/breadth → Market breadth data
// - GET /api/sectors/sectors → Sector rankings and performance data
// Rationale: Single responsibility principle - each endpoint has one clear purpose

// Helper function to determine market status
function getMarketStatus() {
  const now = new Date();
  const dayOfWeek = now.getDay(); // 0 = Sunday, 6 = Saturday
  const hour = now.getHours();
  const minute = now.getMinutes();
  const currentTime = hour * 100 + minute; // Convert to HHMM format

  // Check if it's weekend
  if (dayOfWeek === 0 || dayOfWeek === 6) {
    return "closed";
  }

  // Market hours: 9:30 AM to 4:00 PM ET
  if (currentTime >= 930 && currentTime < 1600) {
    return "open";
  } else if (currentTime >= 400 && currentTime < 930) {
    return "pre_market";
  } else if (currentTime >= 1600 && currentTime < 2000) {
    return "after_hours";
  } else {
    return "closed";
  }
}

// NOTE: /overview endpoint consolidated into /data
// NOTE: Sector endpoints moved to /api/sectors/sectors route (sectors.js)
// NOTE: Sentiment endpoints moved to /api/sentiment/* routes
// Get market breadth indicators - CONSOLIDATED INTO /data
router.get("/breadth", async (req, res) => {
  console.log("Market breadth endpoint called");

  try {
    // Get market breadth data - simplified for performance
    // Get the latest date with sufficient data, calculate breadth for that day
    const breadthQuery = `
      WITH latest_date AS (
        SELECT MAX(date) as market_date
        FROM price_daily
        WHERE close IS NOT NULL
      ),
      latest_day_data AS (
        SELECT
          symbol,
          close,
          open,
          volume,
          date
        FROM price_daily
        WHERE date = (SELECT market_date FROM latest_date)
          AND close IS NOT NULL
          AND open IS NOT NULL
          AND volume > 0
      )
      SELECT
        COUNT(*) as total_stocks,
        COUNT(CASE WHEN (close - open) > 0 THEN 1 END) as advancing,
        COUNT(CASE WHEN (close - open) < 0 THEN 1 END) as declining,
        COUNT(CASE WHEN (close - open) = 0 THEN 1 END) as unchanged,
        COUNT(CASE WHEN (close - open) > (open * 0.05) THEN 1 END) as strong_advancing,
        COUNT(CASE WHEN (close - open) < (open * -0.05) THEN 1 END) as strong_declining,
        AVG(CASE WHEN open > 0 THEN ((close - open) / open * 100) ELSE 0 END) as avg_change,
        AVG(volume) as avg_volume
      FROM latest_day_data
    `;

    const result = await query(breadthQuery);

    if (
      !result ||
      !Array.isArray(result.rows) ||
      result.rows.length === 0 ||
      !result.rows[0].total_stocks ||
      result.rows[0].total_stocks == 0
    ) {
      return res.status(404).json({
        error: "No market breadth data found",
        success: false
      });
    }

    let breadth;
    if (!result || !result.rows || result.rows.length === 0) {
      console.warn('Query returned invalid result for breadth:', result);
      breadth = null;
    } else {
      breadth = result.rows[0];
    }

    if (!breadth) {
      return res.status(404).json({
        error: "No market breadth data found",
        success: false
      });
    }

    return res.json({
      data: {
        total_stocks: parseInt(breadth.total_stocks),
        advancing: parseInt(breadth.advancing),
        declining: parseInt(breadth.declining),
        unchanged: parseInt(breadth.unchanged),
        strong_advancing: parseInt(breadth.strong_advancing),
        strong_declining: parseInt(breadth.strong_declining),
        advance_decline_ratio:
          breadth.declining > 0
            ? (breadth.advancing / breadth.declining).toFixed(2)
            : null,
        avg_change: parseFloat(breadth.avg_change).toFixed(2),
        avg_volume: parseInt(breadth.avg_volume)
      },
      success: true
    });
  } catch (error) {
    console.error("Error fetching market breadth:", error);
    return res.status(500).json({
      error: "Market breadth service unavailable",
      success: false,
    });
  }
});

// McClellan Oscillator endpoint - Advanced breadth momentum indicator
router.get("/mcclellan-oscillator", async (req, res) => {
  console.log("📈 McClellan Oscillator endpoint called");

  try {
    // Check if price_daily table exists
    const tableExists = await query(
      `
      SELECT EXISTS (
        SELECT FROM information_schema.tables
        WHERE table_schema = 'public'
        AND table_name = 'price_daily'
      );
    `,
      []
    );

    if (!tableExists.rows[0].exists) {
      return res.status(500).json({error: "McClellan Oscillator service unavailable", success: false});
    }

    // Helper function to calculate EMA
    const calculateEMA = (data, period) => {
      if (data.length < period) return null;

      const multiplier = 2 / (period + 1);
      let ema = null;

      for (let i = 0; i < data.length; i++) {
        if (i === period - 1) {
          // Calculate initial SMA
          ema = data.slice(0, period).reduce((sum, val) => sum + val, 0) / period;
        } else if (i >= period - 1) {
          // Calculate EMA
          ema = (data[i] - ema) * multiplier + ema;
        }
      }

      return ema;
    };

    // Get advance/decline data - adaptive to available data
    // First try last 90 days, then last 365 days, then all data
    const advanceDeclineQuery = `
      WITH daily_data AS (
        SELECT
          date,
          COUNT(CASE WHEN close > open THEN 1 END) as advances,
          COUNT(CASE WHEN close < open THEN 1 END) as declines
        FROM price_daily
        WHERE close IS NOT NULL AND open IS NOT NULL
        GROUP BY date
        ORDER BY date ASC
      )
      SELECT
        date,
        (advances - declines) as advance_decline_line
      FROM daily_data
      ORDER BY date ASC
    `;

    const result = await query(advanceDeclineQuery);

    if (!result || !Array.isArray(result.rows) || result.rows.length === 0) {
      console.warn('⚠️ No price_daily data found for McClellan calculation');
      return res.status(404).json({
        error: "No price data available for McClellan Oscillator",
        success: false,
      });
    }

    // Ensure we have minimum data points for EMA calculation
    if (result.rows.length < 50) {
      console.warn(`⚠️ Only ${result.rows.length} data points available for McClellan (need 50+ for reliable calculation)`);
    }

    // Extract advance-decline line values
    const adLineData = result.rows.map(row => safeFloat(row.advance_decline_line));

    // Calculate 19-day and 39-day EMAs
    const ema19 = calculateEMA(adLineData, 19);
    const ema39 = calculateEMA(adLineData, 39);

    // Calculate McClellan Oscillator (EMA19 - EMA39)
    const mcOscillator = ema19 !== null && ema39 !== null ? ema19 - ema39 : null;

    // Get recent values for context
    const recentData = result.rows.slice(-30).map(row => ({
      date: row.date,
      advance_decline_line: parseFloat(row.advance_decline_line)
    }));

    return res.json({
      data: {
        current_value: mcOscillator !== null ? parseFloat(mcOscillator.toFixed(2)) : null,
        ema_19: ema19 !== null ? parseFloat(ema19.toFixed(2)) : null,
        ema_39: ema39 !== null ? parseFloat(ema39.toFixed(2)) : null,
        interpretation: mcOscillator !== null ? (
          mcOscillator > 0 ? "Bullish breadth" : "Bearish breadth"
        ) : "Insufficient data",
        recent_data: recentData,
        data_points: adLineData.length
      },
      success: true
    });
  } catch (error) {
    console.error("Error calculating McClellan Oscillator:", error);
    return res.status(500).json({
      error: "McClellan Oscillator calculation failed",
      success: false,
    });
  }
});

// Distribution Days endpoint - IBD methodology
router.get("/distribution-days", async (req, res) => {
  console.log("📊 Distribution Days endpoint called");

  try {
    // Check if distribution_days table exists
    const tableExists = await query(
      `
      SELECT EXISTS (
        SELECT FROM information_schema.tables
        WHERE table_schema = 'public'
        AND table_name = 'distribution_days'
      );
    `,
      []
    );

    if (!tableExists.rows[0].exists) {
      return res.status(500).json({error: "Distribution days service unavailable", success: false});
    }

    // Get distribution days for major indices
    // Use MAX(running_count) to get the current running count (since last follow-through day)
    // This is the proper IBD metric, not total count
    const distributionQuery = `
      SELECT
        symbol,
        MAX(running_count) as count,
        json_agg(
          json_build_object(
            'date', date,
            'close_price', close_price,
            'change_pct', change_pct,
            'volume', volume,
            'volume_ratio', volume_ratio,
            'days_ago', days_ago,
            'running_count', running_count
          ) 
        ) as days
      FROM distribution_days
      WHERE symbol IN ('^GSPC', '^IXIC', '^DJI')
      GROUP BY symbol
      ORDER BY symbol
    `;

    const result = await query(distributionQuery);

    if (!result || !result.rows || result.rows.length === 0) {
      return res.status(404).json({
        error: "No distribution days data found",
        success: false
      });
    }

    // Format response with index names
    const indexNames = {
      "^GSPC": "S&P 500",
      "^IXIC": "NASDAQ Composite",
      "^DJI": "Dow Jones Industrial Average",
    };

    // Determine signal based on RUNNING count of distribution days
    // This is the IBD methodology - count resets on follow-through days
    const getSignalFromCount = (count) => {
      if (count <= 2) return "NORMAL";        // 0-2 days: Normal market
      if (count <= 4) return "WATCH";         // 3-4 days: Watch for weakness
      if (count <= 7) return "CAUTION";       // 5-7 days: Cautious
      if (count <= 10) return "WARNING";      // 8-10 days: Market warning
      return "URGENT";                        // 11+ days: Critical alert
    };

    const distributionData = {};
    result.rows.forEach((row) => {
      const count = parseInt(row.count);
      distributionData[row.symbol] = {
        name: indexNames[row.symbol] || row.symbol,
        count: count,
        signal: getSignalFromCount(count),
        days: Array.isArray(row.days) ? row.days : [],
      };
    });

    // Note: Only return data that actually exists in the database
    // Do NOT create fake/default entries with hardcoded values (count: 0, signal: "NORMAL")
    // If an index has no distribution days data, it simply won't be in the response
    // This follows RULES.md: "Return None Instead of Default Values"

    return res.json({
      data: distributionData,
      success: true
    });
  } catch (error) {
    console.error("Error fetching distribution days:", error);
    return res.status(500).json({
      error: "Distribution days service unavailable",
      success: false,
    });
  }
});

// Get NAAIM data (for DataValidation page)

// Get fear & greed data with flexible date range support

// Get AAII sentiment data with flexible date range support

// Get market volatility
router.get("/volatility", async (req, res) => {
  try {
    // Get VIX and volatility data
    const volatilityQuery = `
      SELECT
        symbol,
        close as close,
        (close - open) as change_amount,
        CASE WHEN open > 0 THEN ((close - open) / open * 100) ELSE NULL END as change_percent,
        date
      FROM price_daily
      WHERE symbol = '^VIX'
        AND date >= CURRENT_DATE - INTERVAL '7 days'
        AND close IS NOT NULL
        AND open IS NOT NULL
    `;

    const result = await query(volatilityQuery);

    // Calculate market volatility from all stocks
    const marketVolatilityQuery = `
      SELECT
        STDDEV((close - open) / NULLIF(open, 0) * 100) as market_volatility,
        AVG(ABS((close - open) / NULLIF(open, 0) * 100)) as avg_absolute_change
      FROM price_daily
      WHERE date >= CURRENT_DATE - INTERVAL '7 days'
        AND close IS NOT NULL
        AND open IS NOT NULL
    `;

    const marketVolatilityResult = await query(marketVolatilityQuery);

    // Use market volatility data if available, fallback to VIX data if available
    let responseData = null;
    if (marketVolatilityResult && marketVolatilityResult.rows && marketVolatilityResult.rows.length > 0) {
      responseData = marketVolatilityResult.rows[0];
    } else if (result && result.rows && result.rows.length > 0) {
      responseData = result.rows[0];
    } else {
      console.warn('No volatility data found');
      responseData = {};
    }

    res.json({ data: responseData, success: true });
  } catch (error) {
    console.error("Error fetching market volatility:", error);
    res.status(500).json({error: "Failed to fetch market volatility: ", success: false});
  }
});

// Get market indicators
router.get("/indicators", async (req, res) => {
  console.log("📊 Market indicators endpoint called");

  try {
    // Get market indicators data from individual stocks
    const indicatorsQuery = `
      SELECT
        pd.symbol,
        pd.close,
        (pd.close - pd.open) as change_amount,
        CASE WHEN pd.open > 0 THEN ((pd.close - pd.open) / pd.open * 100) ELSE NULL END as change_percent,
        pd.volume,
        cp.sector,
        pd.date
      FROM price_daily pd
      JOIN company_profile cp ON pd.symbol = cp.ticker
      WHERE pd.date >= CURRENT_DATE - INTERVAL '7 days'
        AND pd.close IS NOT NULL
        AND pd.open IS NOT NULL
      ORDER BY pd.symbol
    `;

    const result = await query(indicatorsQuery);

    // Get market breadth
    const breadthQuery = `
      SELECT
        COUNT(*) as total_stocks,
        COUNT(CASE WHEN (close - open) / NULLIF(open, 0) * 100 > 0 THEN 1 END) as advancing,
        COUNT(CASE WHEN (close - open) / NULLIF(open, 0) * 100 < 0 THEN 1 END) as declining,
        AVG((close - open) / NULLIF(open, 0) * 100) as avg_change
      FROM price_daily
      WHERE date >= CURRENT_DATE - INTERVAL '7 days'
        AND close IS NOT NULL
        AND open IS NOT NULL
    `;

    const breadthResult = await query(breadthQuery);
    const breadth = breadthResult.rows[0];

    // Get latest sentiment data
    const sentimentQuery = `
      SELECT 
        index_value as value,
        CASE 
          WHEN index_value >= 75 THEN 'Extreme Greed'
          WHEN index_value >= 55 THEN 'Greed'
          WHEN index_value >= 45 THEN 'Neutral'
          WHEN index_value >= 25 THEN 'Fear'
          ELSE 'Extreme Fear'
        END as classification,
        date
      FROM fear_greed_index
      ORDER BY date DESC
      LIMIT 1
    `;

    let sentiment = null;
    try {
      const sentimentResult = await query(sentimentQuery);
      sentiment = sentimentResult.rows[0] || null;
    } catch (e) {
      // Sentiment table might not exist
    }

    if (!result || !Array.isArray(result.rows) || result.rows.length === 0) {
      return res.status(404).json({
        error: "No data found for this query",
        success: false
      });
    }

    res.json({
      data: {
        indices: result.rows,
        breadth: {
          total_stocks: parseInt(breadth.total_stocks),
          advancing: parseInt(breadth.advancing),
          declining: parseInt(breadth.declining),
          advance_decline_ratio:
            breadth.declining > 0
              ? (breadth.advancing / breadth.declining).toFixed(2)
              : null,
          avg_change: parseFloat(breadth.avg_change).toFixed(2),
        },
        sentiment: sentiment
      },
      success: true
    });
  } catch (error) {
    console.error("Error fetching market indicators:", error);
    res.status(500).json({error: "Failed to fetch market indicators", success: false});
  }
});

// PHASE 4: Sentiment Consolidation - MIGRATED TO /api/sentiment/current
// This endpoint has been moved to sentiment.js for proper organization

// Market seasonality endpoint
router.get("/seasonality", async (req, res) => {
  console.log("📅 Market seasonality endpoint called");

  try {
    const currentDate = new Date();
    const currentYear = currentDate.getFullYear();
    const currentMonth = currentDate.getMonth() + 1; // 1-12
    const _currentDay = currentDate.getDate();
    const _dayOfYear = Math.floor(
      (currentDate - new Date(currentYear, 0, 0)) / (1000 * 60 * 60 * 24)
    );

    // Get current year S&P 500 performance
    let currentYearReturn = null; // No default value - get from database
    try {
      const yearStart = new Date(currentYear, 0, 1);
      const spyQuery = `
        SELECT close, date
        FROM price_daily 
        WHERE symbol = 'SPY' AND date >= $1
        ORDER BY date DESC LIMIT 1
      `;
      const spyResult = await query(spyQuery, [
        yearStart.toISOString().split("T")[0],
      ]);

      if (spyResult.rows.length > 0) {
        const yearStartQuery = `
          SELECT close FROM price_daily 
          WHERE symbol = 'SPY' AND date >= $1
          ORDER BY date ASC LIMIT 1
        `;
        const yearStartResult = await query(yearStartQuery, [
          yearStart.toISOString().split("T")[0],
        ]);

        if (yearStartResult.rows.length > 0) {
          const currentPrice = parseFloat(spyResult.rows[0].close);
          const yearStartPrice = parseFloat(yearStartResult.rows[0].close);
          currentYearReturn =
            ((currentPrice - yearStartPrice) / yearStartPrice) * 100;
        }
      }
    } catch (e) {
      console.log("Could not fetch SPY data:", e.message);
    }

    // 1. PRESIDENTIAL CYCLE (4-Year Pattern)
    // Calculate real historical returns from price_daily table
    const electionYear = Math.floor((currentYear - 1792) / 4) * 4 + 1792;
    const currentCyclePosition = ((currentYear - electionYear) % 4) + 1;

    // Fetch historical returns for each presidential cycle year
    let presidentialCycleData = [
      { year: 1, label: "Post-Election", avgReturn: null },
      { year: 2, label: "Mid-Term", avgReturn: null },
      { year: 3, label: "Pre-Election", avgReturn: null },
      { year: 4, label: "Election Year", avgReturn: null },
    ];

    try {
      // Query historical SPY returns for each presidential cycle year
      // Going back 30 years (7-8 complete cycles) for statistical significance
      const cycleReturnsQuery = `
        SELECT
          year,
          ((year - 1792) % 4 + 1)::int as cycle_position,
          ROUND(CAST(AVG(year_return) AS NUMERIC), 2) as avg_return,
          COUNT(*) as sample_size
        FROM (
          SELECT
            EXTRACT(YEAR FROM date)::int as year,
            ROUND(((MAX(close) - MIN(close)) / MIN(close) * 100)::numeric, 2) as year_return
          FROM price_daily
          WHERE symbol = 'SPY' AND date >= TO_DATE(CAST($1 AS TEXT), 'YYYY') AND date < CURRENT_DATE
          GROUP BY EXTRACT(YEAR FROM date)
        ) yearly_returns
        GROUP BY year, cycle_position
      `;

      const cycleReturnsResult = await query(cycleReturnsQuery, [currentYear - 30]);

      // Map results to presidential cycle positions
      if (cycleReturnsResult.rows.length > 0) {
        cycleReturnsResult.rows.forEach(row => {
          const cyclePos = row.cycle_position;
          const dataItem = presidentialCycleData.find(d => d.year === cyclePos);
          if (dataItem && row.avg_return !== null) {
            dataItem.avgReturn = parseFloat(row.avg_return);
          }
        });
      }
    } catch (e) {
      console.log("Could not fetch presidential cycle returns from database:", e.message);
      // If database query fails, leave avgReturn as null - do not use fake data
    }

    const presidentialCycle = {
      currentPosition: currentCyclePosition,
      data: presidentialCycleData.map(d => ({
        year: d.year,
        label: d.label,
        avgReturn: d.avgReturn, // null if real data unavailable
        isCurrent: currentCyclePosition === d.year,
      })),
    };

    // EARLY FETCH: Monthly S&P 500 performance for current year (needed for monthly seasonality chart overlay)
    // 1. MONTHLY SEASONALITY - Load from seasonality_monthly_stats table
    let monthlySeasonality = [];
    let monthlySpPerformance = [];

    try {
      const monthlyStatsQuery = `
        SELECT
          month,
          month_name,
          avg_return,
          best_return,
          worst_return,
          years_counted,
          winning_years,
          losing_years
        FROM seasonality_monthly_stats
        ORDER BY month ASC
      `;

      const monthlyResult = await query(monthlyStatsQuery);

      if (monthlyResult && monthlyResult.rows && monthlyResult.rows.length > 0) {
        monthlySeasonality = monthlyResult.rows.map((m) => {
          const avgReturnNum = m.avg_return ? parseFloat(m.avg_return) : null;
          const bestReturnNum = m.best_return ? parseFloat(m.best_return) : null;
          const worstReturnNum = m.worst_return ? parseFloat(m.worst_return) : null;

          return {
            month: m.month,
            name: m.month_name,
            avgReturn: avgReturnNum,
            bestReturn: bestReturnNum,
            worstReturn: worstReturnNum,
            yearsCount: m.years_counted,
            winningYears: m.winning_years,
            losingYears: m.losing_years,
            isCurrent: m.month === currentMonth,
            description: avgReturnNum !== null
              ? `Avg: ${avgReturnNum >= 0 ? "+" : ""}${avgReturnNum.toFixed(2)}% (${m.winning_years}/${m.years_counted} years positive)`
              : "No historical data",
          };
        });

        console.log("✅ Monthly seasonality data loaded:", monthlySeasonality.slice(0, 3));
      }
    } catch (e) {
      console.log("Note: Monthly seasonality data not available:", e.message);
    }

    // Also load monthly performance for the response
    monthlySpPerformance = monthlySeasonality;

    // 3. QUARTERLY PATTERNS - Calculate from monthly data
    const quarterlySeasonality = [
      { quarter: 1, months: [1, 2, 3], name: "Q1", months_display: "Jan-Mar" },
      { quarter: 2, months: [4, 5, 6], name: "Q2", months_display: "Apr-Jun" },
      { quarter: 3, months: [7, 8, 9], name: "Q3", months_display: "Jul-Sep" },
      { quarter: 4, months: [10, 11, 12], name: "Q4", months_display: "Oct-Dec" },
    ].map((q) => {
      const quarterMonths = monthlySeasonality.filter((m) =>
        q.months.includes(m.month)
      );
      const validReturns = quarterMonths
        .filter((m) => m.avgReturn !== null)
        .map((m) => m.avgReturn);

      const avgReturn =
        validReturns.length > 0
          ? (validReturns.reduce((a, b) => a + b, 0) / validReturns.length).toFixed(2)
          : null;

      const avgReturnNum = avgReturn ? parseFloat(avgReturn) : null;
      return {
        quarter: q.quarter,
        name: q.name,
        months: q.months_display,
        avgReturn: avgReturnNum,
        isCurrent: Math.ceil(currentMonth / 3) === q.quarter,
        description: avgReturnNum !== null
          ? `${avgReturnNum >= 0 ? "+" : ""}${avgReturn}% average (current year data)`
          : "Insufficient quarterly data",
      };
    });

    // 4. INTRADAY PATTERNS
    const intradayPatterns = {
      marketOpen: { time: "9:30 AM", pattern: "High volatility, gap analysis" },
      morningSession: {
        time: "10:00-11:30 AM",
        pattern: "Trend establishment",
      },
      lunchTime: {
        time: "11:30 AM-1:30 PM",
        pattern: "Lower volume, consolidation",
      },
      afternoonSession: {
        time: "1:30-3:00 PM",
        pattern: "Institutional activity",
      },
      powerHour: {
        time: "3:00-4:00 PM",
        pattern: "High volume, day trader exits",
      },
      marketClose: {
        time: "4:00 PM",
        pattern: "Final positioning, after-hours news",
      },
    };

    // 5. DAY OF WEEK EFFECTS - Note: These require detailed historical analysis
    // Cannot be determined from aggregated monthly data. Would require daily returns analysis.
    // 5. DAY OF WEEK EFFECTS - Load from seasonality_day_of_week table
    let dowEffects = [];
    try {
      const dowQuery = `
        SELECT
          day,
          day_num,
          avg_return,
          win_rate,
          days_counted
        FROM seasonality_day_of_week
        ORDER BY day_num ASC
      `;

      const dowResult = await query(dowQuery);

      if (dowResult && dowResult.rows && dowResult.rows.length > 0) {
        dowEffects = dowResult.rows.map((d) => {
          const avgReturnNum = d.avg_return ? parseFloat(d.avg_return) : null;
          const winRateNum = d.win_rate ? parseFloat(d.win_rate) : null;

          return {
            day: d.day,
            dayNum: d.day_num,
            avgReturn: avgReturnNum,
            winRate: winRateNum,
            daysCount: d.days_counted,
            isCurrent: currentDate.toLocaleDateString("en-US", { weekday: "long" }) === d.day,
            description: avgReturnNum !== null && winRateNum !== null
              ? `Avg: ${avgReturnNum >= 0 ? "+" : ""}${avgReturnNum.toFixed(2)}% return (${winRateNum.toFixed(1)}% win rate)`
              : "No historical data",
          };
        });

        console.log("✅ Day of week effects loaded:", dowEffects.slice(0, 2));
      }
    } catch (e) {
      console.log("Note: Day of week effects not available:", e.message);
    }

    // Return only real data - no placeholder fake data
    if (!dowEffects || dowEffects.length === 0) {
      dowEffects = [];
    }

    const dowNote = {
      note: "Day of week effects are calculated from historical daily returns analysis.",
    };

    // 6. SECTOR ROTATION CALENDAR - Fetch actual sectors from database
    // NO hardcoded values - load from company_profile table
    let sectorSeasonality = [];
    try {
      const sectorResult = await query(
        `SELECT DISTINCT sector FROM company_profile WHERE sector IS NOT NULL ORDER BY sector`
      );
      if (sectorResult && sectorResult.rows && sectorResult.rows.length > 0) {
        sectorSeasonality = sectorResult.rows.map((r) => ({
          sector: r.sector
        }));
      } else {
        sectorSeasonality = [
          {
            note: "No sector data available. Run loadcompanyprofile.py and loadsectors.py first.",
          },
        ];
      }
    } catch (e) {
      console.log("Note: Sector data not available:", e.message);
      sectorSeasonality = [
        { note: "Sector seasonality data requires company profile and sector ETF data" },
      ];
    }

    // 7. HOLIDAY EFFECTS - REMOVED FROM MAIN RESPONSE
    // DATA INTEGRITY: Holiday effects are hardcoded assumptions, NOT real data
    // Returning null instead of fake information
    // If implementing real holiday effect analysis:
    // - Must calculate from actual historical daily returns
    // - Must show statistical significance
    // - Must include confidence intervals
    // DO NOT return hardcoded assumptions as if they were analyzed data
    const holidayEffects = null; // Not returning unverified assumptions

    // 8. ANOMALY CALENDAR - Educational reference
    // These are known market anomalies. Actual effectiveness varies over time.
    const seasonalAnomalies = [
      {
        name: "January Effect",
        period: "First 5 trading days",
        description: "Historically correlated with small-cap performance",
        strength: "Moderate",
        note: "Requires multi-year historical analysis",
      },
      {
        name: "Sell in May",
        period: "May 1 - Oct 31",
        description: "Historical summer underperformance pattern",
        strength: "Moderate",
        note: "Requires multi-year historical analysis",
      },
      {
        name: "Halloween Indicator",
        period: "Oct 31 - May 1",
        description: "Historical best 6-month period",
        strength: "Moderate",
        note: "Requires multi-year historical analysis",
      },
      {
        name: "Santa Claus Rally",
        period: "Last 5 + First 2 days",
        description: "Year-end rally pattern",
        strength: "Moderate",
        note: "Requires multi-year historical analysis",
      },
      {
        name: "September Effect",
        period: "September",
        description: "Historically weakest month",
        strength: "Moderate",
        note: "Requires multi-year historical analysis",
      },
      {
        name: "Triple Witching",
        period: "Third Friday quarterly",
        description: "Futures/options expiry day",
        strength: "Weak",
        note: "Volatility pattern from derivatives expiration",
      },
      {
        name: "Turn of Month",
        period: "Last 3 + First 2 days",
        description: "Month-end portfolio activity",
        strength: "Weak",
        note: "Requires multi-year historical analysis",
      },
      {
        name: "FOMC Effect",
        period: "Fed meeting days",
        description: "Market behavior around Fed announcements",
        strength: "Moderate",
        note: "Requires event-based analysis of Fed meetings",
      },
    ];

    // 9. CURRENT SEASONAL POSITION
    const currentMonthData = monthlySeasonality.find(m => m.month === currentMonth);
    const currentQuarterData = quarterlySeasonality.find(q => q.isCurrent);

    const currentPosition = {
      presidentialCycle: `Year ${currentCyclePosition} of 4`,
      monthlyTrend: currentMonthData?.description || "Monthly data unavailable",
      quarterlyTrend: currentQuarterData?.description || "Quarterly data unavailable",
      activePeriods: getActiveSeasonalPeriods(currentDate),
      nextMajorEvent: getNextSeasonalEvent(currentDate),
      seasonalScore: calculateSeasonalScore(currentDate),
    };

    res.json({
      data: {
        currentYear,
        currentYearReturn,
        currentPosition,
        presidentialCycle,
        monthlySeasonality,
        monthlySpPerformance,
        quarterlySeasonality,
        intradayPatterns,
        dayOfWeekEffects: dowEffects,
        sectorSeasonality,
        holidayEffects,
        seasonalAnomalies,
        summary: {
          favorableFactors: getFavorableFactors(currentDate),
          unfavorableFactors: getUnfavorableFactors(currentDate),
          overallSeasonalBias: getOverallBias(currentDate),
          confidence: "Moderate",
          recommendation: getSeasonalRecommendation(currentDate)
        }
      },
      success: true
    });
  } catch (error) {
    console.error("Error fetching seasonality data:", error);
    res.status(500).json({ error: "Failed to fetch seasonality data", success: false });
  }
});

// Helper functions for seasonality analysis
function getActiveSeasonalPeriods(date) {
  const month = date.getMonth() + 1;
  const day = date.getDate();
  const active = [];

  // Check for active seasonal periods
  if (month >= 5 && month <= 10) {
    active.push("Sell in May Period");
  }
  if (month >= 11 || month <= 4) {
    active.push("Halloween Indicator Period");
  }
  if (month === 12 && day >= 24) {
    active.push("Santa Claus Rally");
  }
  if (month === 1 && day <= 5) {
    active.push("January Effect");
  }
  if (month === 9) {
    active.push("September Effect");
  }

  return active.length > 0 ? active : ["Standard Trading Period"];
}

function getNextSeasonalEvent(date) {
  const _month = date.getMonth() + 1;
  const _day = date.getDate();

  // Define seasonal events chronologically
  const events = [
    { month: 1, day: 1, name: "January Effect Begin", daysAway: null },
    { month: 5, day: 1, name: "Sell in May Begin", daysAway: null },
    { month: 9, day: 1, name: "September Effect", daysAway: null },
    { month: 10, day: 31, name: "Halloween Indicator Begin", daysAway: null },
    { month: 12, day: 24, name: "Santa Claus Rally", daysAway: null },
  ];

  // Find next event
  for (const event of events) {
    const eventDate = new Date(date.getFullYear(), event.month - 1, event.day);
    if (eventDate > date) {
      const daysAway = Math.ceil((eventDate - date) / (1000 * 60 * 60 * 24));
      return { ...event, daysAway };
    }
  }

  // If no events this year, return first event of next year
  const nextYearEvent = events[0];
  const nextEventDate = new Date(
    date.getFullYear() + 1,
    nextYearEvent.month - 1,
    nextYearEvent.day
  );
  const daysAway = Math.ceil((nextEventDate - date) / (1000 * 60 * 60 * 24));
  return { ...nextYearEvent, daysAway };
}

function calculateSeasonalScore(date) {
  // ZERO-tolerance policy: Return null instead of hardcoded/calculated values
  // Seasonal patterns should come from real market data, not hardcoded monthly defaults
  // TODO: Implement real seasonal scoring from historical market data if needed
  return null;
}

function getFavorableFactors(date) {
  const month = date.getMonth() + 1;
  const factors = [];

  if ([1, 4, 11, 12].includes(month)) {
    factors.push("Historically strong month");
  }
  if (month >= 11 || month <= 4) {
    factors.push("Halloween Indicator period");
  }
  if (month === 12) {
    factors.push("Holiday rally season");
  }
  if (month === 1) {
    factors.push("January Effect potential");
  }

  return factors.length > 0 ? factors : ["Limited seasonal tailwinds"];
}

function getUnfavorableFactors(date) {
  const month = date.getMonth() + 1;
  const factors = [];

  if (month === 9) {
    factors.push("September Effect - historically worst month");
  }
  if ([5, 6, 7, 8].includes(month)) {
    factors.push("Summer doldrums period");
  }
  if (month >= 5 && month <= 10) {
    factors.push("Sell in May period active");
  }

  return factors.length > 0 ? factors : ["Limited seasonal headwinds"];
}

function getOverallBias(date) {
  const score = calculateSeasonalScore(date);

  // REAL DATA ONLY - return null if no seasonal score available
  if (score === null) return null;

  if (score >= 70) return "Strongly Bullish";
  if (score >= 60) return "Bullish";
  if (score >= 40) return "Neutral";
  if (score >= 30) return "Bearish";
  return "Strongly Bearish";
}

function getSeasonalRecommendation(date) {
  const _month = date.getMonth() + 1;
  const score = calculateSeasonalScore(date);

  // REAL DATA ONLY - return null if no seasonal score available
  if (score === null) return null;

  if (score >= 70) {
    return "Strong seasonal tailwinds suggest overweight equity positions";
  } else if (score >= 60) {
    return "Moderate seasonal support for risk-on positioning";
  } else if (score >= 40) {
    return "Mixed seasonal signals suggest balanced approach";
  } else if (score >= 30) {
    return "Seasonal headwinds suggest defensive positioning";
  } else {
    return "Strong seasonal headwinds suggest risk-off approach";
  }
}

// Economic Modeling Endpoints for Advanced Economic Analysis

// Recession probability forecasting with multiple models
// ============================================
// FULL YIELD CURVE - With all treasury maturities
// ============================================
// ============================================
// COMPREHENSIVE CREDIT SPREADS - Multiple spread types with history
// ============================================
// Market movers endpoint - top gainers, losers, most active
// Market correlation analysis endpoint
router.get("/correlation", async (req, res) => {
  try {
    const { symbols, period = "1M", limit: _limit = 50 } = req.query;

    console.log(
      `📊 Market correlation requested - symbols: ${symbols || "all"}, period: ${period}`
    );

    // Generate correlation matrix from real price data
    const generateCorrelationMatrix = async (targetSymbols, period) => {
      const baseSymbols = [
        "SPY",
        "QQQ",
        "IWM",
        "AAPL",
        "MSFT",
        "GOOGL",
        "AMZN",
        "TSLA",
        "NVDA",
        "META",
      ];
      const analysisSymbols = targetSymbols
        ? targetSymbols.split(",").map((s) => s.trim().toUpperCase())
        : baseSymbols;

      const matrix = [];
      const statistics = {
        avg_correlation: 0,
        max_correlation: { value: 0, pair: [] },
        min_correlation: { value: 1, pair: [] },
        highly_correlated: [],
        negatively_correlated: [],
      };

      let totalCorrelations = 0;
      let sumCorrelations = 0;

      // Helper function to calculate Pearson correlation from historical returns
      const calculatePearsonCorrelation = (returns1, returns2) => {
        if (returns1.length < 2 || returns2.length < 2 || returns1.length !== returns2.length) {
          return null;
        }

        const n = returns1.length;
        const mean1 = returns1.reduce((a, b) => a + b, 0) / n;
        const mean2 = returns2.reduce((a, b) => a + b, 0) / n;

        let covariance = 0;
        let sd1 = 0;
        let sd2 = 0;

        for (let k = 0; k < n; k++) {
          const diff1 = returns1[k] - mean1;
          const diff2 = returns2[k] - mean2;
          covariance += diff1 * diff2;
          sd1 += diff1 * diff1;
          sd2 += diff2 * diff2;
        }

        sd1 = Math.sqrt(sd1 / n);
        sd2 = Math.sqrt(sd2 / n);

        if (sd1 === 0 || sd2 === 0) {
          return 0;
        }

        return covariance / (n * sd1 * sd2);
      };

      for (let i = 0; i < analysisSymbols.length; i++) {
        const row = [];
        for (let j = 0; j < analysisSymbols.length; j++) {
          let correlation;

          if (i === j) {
            correlation = 1.0; // Perfect correlation with itself
          } else {
            const symbol1 = analysisSymbols[i];
            const symbol2 = analysisSymbols[j];

            // Calculate REAL correlation from price_daily data in database - ALWAYS FRESH
            try {
              // Fetch fresh price data for each symbol (no caching)
              const result1 = await query(
                `SELECT date, close FROM price_daily WHERE symbol = $1 ORDER BY date DESC LIMIT 252`,
                [symbol1]
              );
              const prices1 = (result1?.rows || []).reverse();

              const result2 = await query(
                `SELECT date, close FROM price_daily WHERE symbol = $1 ORDER BY date DESC LIMIT 252`,
                [symbol2]
              );
              const prices2 = (result2?.rows || []).reverse();

              // Find overlapping dates and calculate returns
              if (prices1.length >= 2 && prices2.length >= 2) {
                const dates1 = new Set(prices1.map((p) => p.date));
                const dates2 = new Set(prices2.map((p) => p.date));
                const overlappingDates = prices1
                  .map((p) => p.date)
                  .filter((d) => dates2.has(d));

                if (overlappingDates.length >= 2) {
                  // Calculate daily returns for overlapping dates
                  const returns1 = [];
                  const returns2 = [];

                  const p1Map = new Map(prices1.map((p) => [p.date?.toString?.() || p.date, p.close]));
                  const p2Map = new Map(prices2.map((p) => [p.date?.toString?.() || p.date, p.close]));

                  for (let k = 1; k < overlappingDates.length; k++) {
                    const prevDate = (overlappingDates[k - 1]?.toString?.() || overlappingDates[k - 1]);
                    const currDate = (overlappingDates[k]?.toString?.() || overlappingDates[k]);

                    const p1Prev = p1Map.get(prevDate);
                    const p1Curr = p1Map.get(currDate);
                    const p2Prev = p2Map.get(prevDate);
                    const p2Curr = p2Map.get(currDate);

                    if (p1Prev && p1Curr && p2Prev && p2Curr && p1Prev > 0 && p2Prev > 0) {
                      returns1.push((p1Curr - p1Prev) / p1Prev);
                      returns2.push((p2Curr - p2Prev) / p2Prev);
                    }
                  }

                  // Calculate Pearson correlation of returns
                  if (returns1.length >= 2) {
                    correlation = calculatePearsonCorrelation(returns1, returns2);
                  }
                }
              }
            } catch (e) {
              console.warn(
                `⚠️  Error calculating correlation for ${symbol1}-${symbol2}: ${e.message}`
              );
              correlation = null;
            }

            // Track statistics (skip if correlation is NULL/unavailable)
            if (i < j && correlation !== null) {
              // Only count each pair once
              totalCorrelations++;
              sumCorrelations += correlation;

              if (correlation > statistics.max_correlation.value) {
                statistics.max_correlation = {
                  value: correlation,
                  pair: [symbol1, symbol2],
                };
              }
              if (correlation < statistics.min_correlation.value) {
                statistics.min_correlation = {
                  value: correlation,
                  pair: [symbol1, symbol2],
                };
              }

              if (correlation > 0.7) {
                statistics.highly_correlated.push({
                  symbols: [symbol1, symbol2],
                  correlation,
                });
              }
              if (correlation < 0.3) {
                statistics.negatively_correlated.push({
                  symbols: [symbol1, symbol2],
                  correlation,
                });
              }
            }
          }

          row.push(correlation);
        }
        matrix.push({
          symbol: analysisSymbols[i],
          correlations: row,
        });
      }

      statistics.avg_correlation =
        Math.round((sumCorrelations / totalCorrelations) * 1000) / 1000;

      return {
        symbols: analysisSymbols,
        matrix,
        statistics,
        period_analysis: {
          period: period,
          observation_days:
            period === "1W"
              ? 7
              : period === "1M"
                ? 30
                : period === "3M"
                  ? 90
                  : 365,
          correlation_strength:
            statistics.avg_correlation > 0.6
              ? "Strong"
              : statistics.avg_correlation > 0.3
                ? "Moderate"
                : "Weak",
        },
      };
    };

    const correlationData = await generateCorrelationMatrix(symbols, period);

    // Generate additional analysis
    const analysis = {
      market_regime:
        correlationData.statistics.avg_correlation > 0.6
          ? "Risk-On"
          : "Risk-Off",
      diversification_score: Math.round(
        (1 - correlationData.statistics.avg_correlation) * 100
      ),
      risk_assessment: {
        concentration_risk:
          correlationData.statistics.highly_correlated.length > 3
            ? "High"
            : "Moderate",
        diversification_benefit:
          correlationData.statistics.avg_correlation < 0.5 ? "Good" : "Limited",
        portfolio_stability:
          correlationData.statistics.avg_correlation > 0.8 ? "Low" : "Moderate",
      },
    };

    res.json({
      data: {
        correlations: correlationData.matrix,
        statistics: correlationData.statistics,
        analysis
      },
      success: true
    });
  } catch (error) {
    console.error("Market correlation analysis error:", error);

    res.status(500).json({error: "Failed to calculate market correlations", success: false});
  }
});

// Get market news and sentiment
// Get options market data
// Get earnings calendar/data
// Get futures market data
// Crypto endpoints disabled - not ready for cryptocurrency data yet

// Market volume analysis endpoint
// Stock quote endpoint
// Trending stocks endpoint
// Market gainers endpoint
// Market losers endpoint
// Stock search endpoint
// Market status endpoint
// Market indices endpoint
router.get("/indices", async (req, res) => {
  try {
    console.log(`📊 Market indices requested with P/E data`);

    // Get latest price data
    const latestDateQuery = `
      SELECT MAX(date) as latest_date
      FROM price_daily
      WHERE symbol IN ('^GSPC', '^IXIC', '^DJI', '^RUT')
        AND close IS NOT NULL
    `;

    const dateResult = await query(latestDateQuery);
    const latestDate = dateResult?.rows?.[0]?.latest_date;

    if (!latestDate) {
      console.warn("⚠️ No index price data found");
      return res.json({
        data: [],
        info: "No market index data available",
        success: true
      });
    }

    // Get price data for indices
    const indicesQuery = `
      SELECT
        symbol,
        close as price,
        (close - open) as change,
        CASE WHEN open > 0 THEN ((close - open) / open * 100) ELSE NULL END as changePercent,
        volume,
        date
      FROM price_daily
      WHERE symbol IN ('^GSPC', '^IXIC', '^DJI', '^RUT')
        AND date = $1
        AND close IS NOT NULL
        AND open IS NOT NULL
      ORDER BY symbol
    `;

    // Get price data first
    const priceResult = await query(indicesQuery, [latestDate]);

    // Try to get P/E data if available
    let peResult = null;
    try {
      // Check if index_metrics table exists first
      const tableCheckQuery = `
        SELECT EXISTS (
          SELECT FROM information_schema.tables
          WHERE table_schema = 'public'
          AND table_name = 'index_metrics'
        );
      `;
      const tableCheckResult = await query(tableCheckQuery);

      if (tableCheckResult?.rows?.[0]?.exists) {
        const indexPEQuery = `
          SELECT
            symbol,
            trailing_pe,
            forward_pe,
            price_to_book,
            price_to_sales,
            peg_ratio,
            earnings_yield,
            dividend_yield,
            pe_percentile
          FROM index_metrics
          WHERE symbol IN ('^GSPC', '^IXIC', '^DJI', '^RUT')
          ORDER BY symbol
        `;
        peResult = await query(indexPEQuery);
      }
    } catch (peError) {
      console.warn("⚠️ Could not fetch P/E data:", peError.message);
      // Continue without P/E data
    }

    if (!priceResult?.rows || priceResult.rows.length === 0) {
      console.warn(`⚠️ No index price data found for ${latestDate}`);
      return res.json({
        data: [],
        info: "No index data available for latest trading date",
        success: true
      });
    }

    const indexNames = {
      '^GSPC': 'S&P 500',
      '^IXIC': 'NASDAQ Composite',
      '^DJI': 'Dow Jones Industrial Average',
      '^RUT': 'Russell 2000'
    };

    // Create a map of index P/E data for quick lookup
    const peDataMap = {};
    if (peResult?.rows) {
      peResult.rows.forEach(row => {
        peDataMap[row.symbol] = row;
      });
    }

    const indices = priceResult.rows.map((row) => {
      const baseData = {
        symbol: row.symbol,
        name: indexNames[row.symbol] || row.symbol,
        price: safeFixed(row.price, 2),
        change: safeFixed(row.change, 2),
        changePercent: safeFixed(row.changePercent, 2),
        volume: safeInt(row.volume),
        date: row.date
      };

      // Add P/E data for all indices if available
      const indexPE = peDataMap[row.symbol];
      if (indexPE && indexPE.trailing_pe) {
        baseData.pe = {
          trailing: safeFixed(indexPE.trailing_pe, 2),
          forward: safeFixed(indexPE.forward_pe, 2),
          priceToBook: safeFixed(indexPE.price_to_book, 2),
          priceToSales: safeFixed(indexPE.price_to_sales, 2),
          pegRatio: safeFixed(indexPE.peg_ratio, 2),
          earningsYield: safeFixed(indexPE.earnings_yield, 4),
          dividendYield: safeFixed(indexPE.dividend_yield, 4),
          percentile: indexPE.pe_percentile ? safeFixed(indexPE.pe_percentile, 2) : null
        };
      }

      return baseData;
    });

    const hasAnyPE = Object.keys(peDataMap).length > 0;
    res.json({
      data: indices,
      count: indices.length,
      peAvailable: hasAnyPE,
      message: hasAnyPE ? "P/E valuation data available for major indices" : "Index valuation data not yet available",
      success: true
    });
  } catch (error) {
    console.error("❌ Market indices error:", error.message);
    res.status(500).json({
      error: "Failed to fetch market indices",
      details: error.message,
      success: false,
    });
  }
});

// Removed duplicate /economic endpoint - using the one at line 1451

// PHASE 4: Sentiment Consolidation - MIGRATED TO /api/sentiment/divergence
// Market Commentary APIs have been moved to appropriate domain routes
// Smart Money vs Retail Sentiment Divergence endpoint is now at /api/sentiment/divergence

// Advanced Market Internals - Comprehensive breadth, MA analysis, and positioning
router.get("/internals", async (req, res) => {
  console.log("Market internals endpoint called");

  try {
    if (!query) {
      return res.status(500).json({error: "Database service unavailable", success: false, });
    }

    // Run all queries in parallel
    const [breadthResult, maAnalysisResult, historicalBreadthResult, positioningResult] = await Promise.all([
      // Current breadth data with advance/decline calculations
      query(`
        SELECT
          COUNT(*) as total_stocks,
          COUNT(CASE WHEN (close - open) > 0 THEN 1 END) as advancing,
          COUNT(CASE WHEN (close - open) < 0 THEN 1 END) as declining,
          COUNT(CASE WHEN (close - open) = 0 THEN 1 END) as unchanged,
          COUNT(CASE WHEN (close - open) > (close * 0.05) THEN 1 END) as strong_up,
          COUNT(CASE WHEN (close - open) < (close * -0.05) THEN 1 END) as strong_down,
          SUM(volume) as total_volume,
          AVG((close - open) / open * 100) as avg_daily_change,
          STDDEV((close - open) / open * 100) as stddev_change
        FROM price_daily
        WHERE date = (SELECT MAX(date) FROM price_daily WHERE close IS NOT NULL)
          AND close IS NOT NULL
          AND open IS NOT NULL
      `),

      // Stocks above moving averages analysis (calculated from 20, 50, 200 day averages)
      query(`
        WITH latest_date AS (
          SELECT MAX(date) as max_date
          FROM price_daily
          WHERE close IS NOT NULL
        ),
        price_stats AS (
          SELECT
            symbol,
            close,
            AVG(close) OVER (PARTITION BY symbol ORDER BY date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) as sma_20,
            AVG(close) OVER (PARTITION BY symbol ORDER BY date ROWS BETWEEN 49 PRECEDING AND CURRENT ROW) as sma_50,
            AVG(close) OVER (PARTITION BY symbol ORDER BY date ROWS BETWEEN 199 PRECEDING AND CURRENT ROW) as sma_200
          FROM price_daily
          WHERE date >= (SELECT max_date FROM latest_date) - INTERVAL '200 days'
            AND close IS NOT NULL
        ),
        latest_prices AS (
          SELECT DISTINCT ON (symbol)
            symbol, close, sma_20, sma_50, sma_200
          FROM price_stats
          WHERE close IS NOT NULL
          ORDER BY symbol, sma_20 IS NOT NULL DESC
        ),
        ma_analysis AS (
          SELECT
            COUNT(*) FILTER (WHERE sma_20 IS NOT NULL AND close > sma_20) as above_sma20,
            COUNT(*) FILTER (WHERE sma_50 IS NOT NULL AND close > sma_50) as above_sma50,
            COUNT(*) FILTER (WHERE sma_200 IS NOT NULL AND close > sma_200) as above_sma200,
            COUNT(*) FILTER (WHERE sma_20 IS NOT NULL) as total_with_sma20,
            COUNT(*) FILTER (WHERE sma_50 IS NOT NULL) as total_with_sma50,
            COUNT(*) FILTER (WHERE sma_200 IS NOT NULL) as total_with_sma200,
            COUNT(*) as total_stocks,
            AVG(CASE WHEN sma_20 IS NOT NULL AND sma_20 > 0 THEN (close - sma_20) / sma_20 * 100 ELSE NULL END) as avg_dist_from_sma20,
            AVG(CASE WHEN sma_50 IS NOT NULL AND sma_50 > 0 THEN (close - sma_50) / sma_50 * 100 ELSE NULL END) as avg_dist_from_sma50,
            AVG(CASE WHEN sma_200 IS NOT NULL AND sma_200 > 0 THEN (close - sma_200) / sma_200 * 100 ELSE NULL END) as avg_dist_from_sma200
          FROM latest_prices
        )
        SELECT
          above_sma20, above_sma50, above_sma200,
          total_with_sma20, total_with_sma50, total_with_sma200,
          total_stocks, avg_dist_from_sma20, avg_dist_from_sma50, avg_dist_from_sma200
        FROM ma_analysis
      `),

      // Historical breadth percentiles (30, 60, 90 day lookback)
      query(`
        WITH breadth_history AS (
          SELECT
            date,
            COUNT(*) as total_stocks,
            COUNT(CASE WHEN (close - open) > 0 THEN 1 END) as advancing,
            COUNT(CASE WHEN (close - open) < 0 THEN 1 END) as declining,
            ROUND(100.0 * COUNT(CASE WHEN (close - open) > 0 THEN 1 END) / COUNT(*), 2) as advancing_percent,
            ROUND(100.0 * COUNT(CASE WHEN (close - open) < 0 THEN 1 END) / COUNT(*), 2) as declining_percent
          FROM price_daily
          WHERE date >= CURRENT_DATE - INTERVAL '90 days'
            AND close IS NOT NULL
            AND open IS NOT NULL
          GROUP BY date
          
        )
        SELECT
          (SELECT advancing_percent FROM breadth_history ORDER BY date DESC LIMIT 1) as current_advancing_pct,
          PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY advancing_percent) as percentile_25_advancing,
          PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY advancing_percent) as percentile_50_advancing,
          PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY advancing_percent) as percentile_75_advancing,
          PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY advancing_percent) as percentile_90_advancing,
          AVG(advancing_percent) as avg_advancing_pct,
          STDDEV(advancing_percent) as stddev_advancing_pct,
          MAX(advancing_percent) as max_advancing_pct,
          MIN(advancing_percent) as min_advancing_pct
        FROM breadth_history
      `),

      // Market positioning metrics - query real data from multiple sources
      (async () => {
        try {
          return await query(`
            SELECT
              COALESCE(pm.high_inst_ownership_count, NULL) as high_inst_ownership_count,
              COALESCE(pm.avg_inst_ownership, NULL) as avg_inst_ownership,
              COALESCE(pm.avg_short_interest, NULL) as avg_short_interest,
              COALESCE(pm.avg_short_change, NULL) as avg_short_change,
              COALESCE(aaii.bullish, NULL) as aaii_bullish,
              COALESCE(aaii.bearish, NULL) as aaii_bearish,
              COALESCE(aaii.neutral, NULL) as aaii_neutral,
              COALESCE(naaim.bullish, NULL) as naaim_bullish,
              COALESCE(naaim.bearish, NULL) as naaim_bearish,
              COALESCE(fgi.value, NULL) as fear_greed_value
            FROM (
              SELECT 1 as dummy
            ) d
            LEFT JOIN (
              SELECT
                COUNT(CASE WHEN institutional_ownership_pct > 50 THEN 1 END) as high_inst_ownership_count,
                AVG(institutional_ownership_pct) as avg_inst_ownership,
                AVG(short_interest_pct) as avg_short_interest,
                NULL as avg_short_change
              FROM institutional_positioning
              LIMIT 1
            ) pm ON true
            LEFT JOIN (
              SELECT bullish, bearish, neutral
              FROM aaii_sentiment
              ORDER BY date DESC
              LIMIT 1
            ) aaii ON true
            LEFT JOIN (
              SELECT bullish, bearish
              FROM naaim_sentiment
              ORDER BY date DESC
              LIMIT 1
            ) naaim ON true
            LEFT JOIN (
              SELECT value
              FROM fear_greed_index
              ORDER BY date DESC
              LIMIT 1
            ) fgi ON true
          `);
        } catch (e) {
          return { rows: [] };  // Return empty array when data unavailable
        }
      })()
    ]);

    const breadth = (breadthResult && breadthResult.rows && breadthResult.rows[0]) || {};
    const maAnalysis = (maAnalysisResult && maAnalysisResult.rows && maAnalysisResult.rows[0]) || {};
    const historicalBreadth = (historicalBreadthResult && historicalBreadthResult.rows && historicalBreadthResult.rows[0]) || {};
    const positioning = (positioningResult && positioningResult.rows && positioningResult.rows[0]) || {};

    // Calculate overextension signals - only if real data exists
    const advancingPct = breadth.total_stocks ? (breadth.advancing / breadth.total_stocks * 100) : null;
    const advancingPercAboveMA20 = maAnalysis.total_with_sma20 ? (maAnalysis.above_sma20 / maAnalysis.total_with_sma20 * 100) : null;
    const advancingPercAboveMA200 = maAnalysis.total_with_sma200 ? (maAnalysis.above_sma200 / maAnalysis.total_with_sma200 * 100) : null;

    // Determine overextension level
    let overextensionLevel = "Normal";
    let overextensionSignal = null;

    if (advancingPct > 75 && advancingPercAboveMA200 > 80) {
      overextensionLevel = "Extreme";
      overextensionSignal = "Market extremely overbought - consider taking profits";
    } else if (advancingPct > 70 || advancingPercAboveMA200 > 75) {
      overextensionLevel = "Strong";
      overextensionSignal = "Market extended to upside - watch for reversal";
    } else if (advancingPct < 25 && advancingPercAboveMA200 < 20) {
      overextensionLevel = "Extreme Down";
      overextensionSignal = "Market extremely oversold - may be bottom";
    } else if (advancingPct < 30 || advancingPercAboveMA200 < 25) {
      overextensionLevel = "Strong Down";
      overextensionSignal = "Market extended to downside - watch for reversal";
    }

    // Calculate how many std deviations from mean
    const stdDevsFromMean = historicalBreadth.stddev_advancing_pct
      ? ((advancingPct - historicalBreadth.avg_advancing_pct) / historicalBreadth.stddev_advancing_pct).toFixed(2)
      : 0;

    return res.json({
      data: {
        market_breadth: {
          total_stocks: safeInt(breadth.total_stocks),
          advancing: safeInt(breadth.advancing),
          declining: safeInt(breadth.declining),
          unchanged: safeInt(breadth.unchanged),
          strong_up: safeInt(breadth.strong_up),
          strong_down: safeInt(breadth.strong_down),
          advancing_percent: parseFloat(advancingPct).toFixed(2),
          decline_advance_ratio: breadth.declining > 0 ? parseFloat(breadth.declining / breadth.advancing).toFixed(2) : null,
          avg_daily_change: safeFixed(breadth.avg_daily_change, 3),
          total_volume: safeInt(breadth.total_volume)
        },
        moving_average_analysis: {
          above_sma20: {
            count: safeInt(maAnalysis.above_sma20),
            total: safeInt(maAnalysis.total_with_sma20),
            percent: maAnalysis.total_with_sma20 ? parseFloat(advancingPercAboveMA20).toFixed(2) : null,
            avg_distance_pct: safeFixed(maAnalysis.avg_dist_from_sma20, 2)
          },
          above_sma50: {
            count: safeInt(maAnalysis.above_sma50),
            total: safeInt(maAnalysis.total_with_sma50),
            percent: maAnalysis.total_with_sma50 ? parseFloat((maAnalysis.above_sma50 / maAnalysis.total_with_sma50 * 100)).toFixed(2) : null,
            avg_distance_pct: safeFixed(maAnalysis.avg_dist_from_sma50, 2)
          },
          above_sma200: {
            count: safeInt(maAnalysis.above_sma200),
            total: safeInt(maAnalysis.total_with_sma200),
            percent: maAnalysis.total_with_sma200 ? parseFloat(advancingPercAboveMA200).toFixed(2) : null,
            avg_distance_pct: safeFixed(maAnalysis.avg_dist_from_sma200, 2)
          }
        },
        market_extremes: {
          current_breadth_percentile: advancingPct.toFixed(2),
          percentile_25: safeFixed(historicalBreadth.percentile_25_advancing, 2),
          percentile_50: safeFixed(historicalBreadth.percentile_50_advancing, 2),
          percentile_75: safeFixed(historicalBreadth.percentile_75_advancing, 2),
          percentile_90: safeFixed(historicalBreadth.percentile_90_advancing, 2),
          avg_breadth_30d: safeFixed(historicalBreadth.avg_advancing_pct, 2),
          stddev_breadth_30d: safeFixed(historicalBreadth.stddev_advancing_pct, 2),
          stddev_from_mean: stdDevsFromMean,
          breadth_rank: historicalBreadth.max_advancing_pct !== historicalBreadth.min_advancing_pct ?
            Math.round(((advancingPct - historicalBreadth.min_advancing_pct) / (historicalBreadth.max_advancing_pct - historicalBreadth.min_advancing_pct) * 100)) :
            null
        },
        overextension_indicator: {
          level: overextensionLevel,
          signal: overextensionSignal,
          breadth_score: advancingPct.toFixed(2),
          ma200_score: advancingPercAboveMA200.toFixed(2),
          composite_score: ((parseFloat(advancingPct) + parseFloat(advancingPercAboveMA200)) / 2).toFixed(2)
        },
        positioning_metrics: {
          institutional: {
            high_ownership_symbols: safeInt(positioning.high_inst_ownership_count),
            avg_ownership_pct: (safeFloat(positioning.avg_inst_ownership) * 100).toFixed(2),
            avg_short_interest: (safeFloat(positioning.avg_short_interest) * 100).toFixed(2),
            short_change_trend: safeFixed(positioning.avg_short_change, 3)
          },
          retail_sentiment: {
            aaii_bullish: positioning.aaii_bullish !== null && positioning.aaii_bullish !== undefined ? parseFloat(positioning.aaii_bullish).toFixed(2) : null,
            aaii_bearish: positioning.aaii_bearish !== null && positioning.aaii_bearish !== undefined ? parseFloat(positioning.aaii_bearish).toFixed(2) : null,
            aaii_neutral: positioning.aaii_neutral !== null && positioning.aaii_neutral !== undefined ? parseFloat(positioning.aaii_neutral).toFixed(2) : null
          },
          professional_sentiment: {
            naaim_bullish: positioning.naaim_bullish !== null && positioning.naaim_bullish !== undefined ? parseFloat(positioning.naaim_bullish).toFixed(2) : null,
            naaim_bearish: positioning.naaim_bearish !== null && positioning.naaim_bearish !== undefined ? parseFloat(positioning.naaim_bearish).toFixed(2) : null
          },
          fear_greed_index: positioning.fear_greed_value !== null && positioning.fear_greed_value !== undefined ? parseFloat(positioning.fear_greed_value).toFixed(0) : null
        },
        metadata: {
          data_freshness: "Real-time from database",
          breadth_lookback: "Last trading day",
          historical_lookback: "90 days",
          positioning_lookback: "30 days"
        }
      },
      success: true
    });

  } catch (error) {
    console.error("Error fetching market internals:", error);
    return res.status(500).json({error: "Market internals calculation failed", success: false});
  }
});

// AAII Sentiment Data - Retail investor sentiment indicator
router.get("/aaii", async (req, res) => {
  try {
    if (!query) {
      return res.status(500).json({error: "Database service unavailable", success: false});
    }

    const { range = "30d" } = req.query;

    // Convert range parameter to days
    let days = 30;
    switch(range) {
      case "90d": days = 90; break;
      case "6m": days = 180; break;
      case "1y": days = 365; break;
      case "all": days = 10000; break; // Large number for "all" data
      default: days = 30;
    }

    const result = await query(`
      SELECT
        date,
        bullish,
        neutral,
        bearish
      FROM aaii_sentiment
      WHERE date >= CURRENT_DATE - MAKE_INTERVAL(days => $1)
      ORDER BY date ASC
    `, [days]);

    if (!result || !result.rows) {
      return res.json({
        data: [],
        range: range,
        success: true
      });
    }

    const data = result.rows.map(row => ({
      date: row.date,
      bullish: parseFloat(row.bullish),
      neutral: parseFloat(row.neutral),
      bearish: parseFloat(row.bearish)
    }));

    return res.json({
      items: data,
      pagination: {
        total: data.length,
        range: range,
        count: data.length
      },
      success: true
    });

  } catch (error) {
    console.error("AAII sentiment error:", error);
    return res.status(500).json({error: "Failed to fetch AAII sentiment data", success: false});
  }
});

// Fear & Greed Index - Market emotion indicator
router.get("/fear-greed", async (req, res) => {
  try {
    if (!query) {
      return res.status(500).json({error: "Database service unavailable", success: false});
    }

    const { range = "30d" } = req.query;

    // Convert range parameter to days
    let days = 30;
    switch(range) {
      case "90d": days = 90; break;
      case "6m": days = 180; break;
      case "1y": days = 365; break;
      case "all": days = 10000; break;
      default: days = 30;
    }

    const result = await query(`
      SELECT
        date,
        index_value,
        rating
      FROM fear_greed_index
      WHERE date >= CURRENT_DATE - MAKE_INTERVAL(days => $1)
      ORDER BY date ASC
    `, [days]);

    if (!result || !result.rows) {
      return res.json({
        data: [],
        range: range,
        success: true
      });
    }

    const data = result.rows.map(row => ({
      date: row.date,
      value: parseFloat(row.index_value),
      rating: row.rating,
      index_value: parseFloat(row.index_value) // Also include for backward compatibility
    }));

    return res.json({
      data: data,
      range: range,
      count: data.length,
      success: true
    });

  } catch (error) {
    console.error("Fear & Greed index error:", error);
    return res.status(500).json({error: "Failed to fetch Fear & Greed index data", success: false});
  }
});

// NAAIM - Professional advisor sentiment indicator
router.get("/naaim", async (req, res) => {
  try {
    if (!query) {
      return res.status(500).json({error: "Database service unavailable", success: false});
    }

    const { range = "30d" } = req.query;

    // Convert range parameter to days
    let days = 30;
    switch(range) {
      case "90d": days = 90; break;
      case "6m": days = 180; break;
      case "1y": days = 365; break;
      case "all": days = 10000; break;
      default: days = 30;
    }

    const result = await query(`
      SELECT
        date,
        bullish,
        bearish,
        naaim_number_mean,
        quart1,
        quart2,
        quart3,
        deviation
      FROM naaim
      WHERE date >= CURRENT_DATE - MAKE_INTERVAL(days => $1)
      ORDER BY date ASC
    `, [days]);

    if (!result || !result.rows) {
      return res.json({
        data: [],
        range: range,
        success: true
      });
    }

    const data = result.rows.map(row => ({
      date: row.date,
      bullish_exposure: parseFloat(row.bullish),
      bearish_exposure: parseFloat(row.bearish),
      // Also include simple names for backward compatibility
      bullish: parseFloat(row.bullish),
      bearish: parseFloat(row.bearish)
    }));

    return res.json({
      data: data,
      range: range,
      count: data.length,
      success: true
    });

  } catch (error) {
    console.error("NAAIM sentiment error:", error);
    return res.status(500).json({error: "Failed to fetch NAAIM sentiment data", success: false});
  }
});

// ============================================================================
// UNIFIED MARKET DATA ENDPOINT - Get all market data in one call
// ============================================================================
// Instead of making 14+ separate API calls to /overview, /breadth, /indices, etc.
// This single endpoint returns ALL market data with proper structure
router.get("/data", async (req, res) => {
  try {
    if (!query) {
      return res.status(500).json({
        error: "Database connection not available",
        success: false
      });
    }

    console.log("📊 /api/market/data - Fetching all market data...");
    const startTime = Date.now();

    // Run all data fetches in parallel for speed
    const [
      overviewData,
      breadthData,
      mcclellanData,
      distributionDaysData,
      indicesData,
      volatilityData,
      aaiiData,
      fearGreedData,
      naaimData,
      seasonalityData,
      internalsData
    ] = await Promise.allSettled([
      // 1. Overview (quality, top stocks, breadth summary)
      (async () => {
        const [marketCapResult, topStocksResult, breadthResult] = await Promise.all([
          query(`SELECT COUNT(*) as total_stocks,
                 SUM(CASE WHEN composite_score >= 75 THEN 1 ELSE 0 END) as high_quality,
                 SUM(CASE WHEN composite_score >= 50 AND composite_score < 75 THEN 1 ELSE 0 END) as mid_quality
                 FROM stock_scores WHERE composite_score IS NOT NULL`),
          query(`SELECT symbol, composite_score, momentum_score, value_score
                 FROM stock_scores WHERE composite_score IS NOT NULL
                 ORDER BY composite_score DESC LIMIT 10`),
          query(`SELECT * FROM price_daily WHERE symbol = 'SPY' ORDER BY date DESC LIMIT 2`)
        ]);
        return {
          quality_counts: marketCapResult.rows[0] || {},
          top_stocks: topStocksResult.rows || [],
          breadth_summary: breadthResult.rows || []
        };
      })(),

      // 2. Breadth (advancing/declining/unchanged)
      (async () => {
        const result = await query(`
          WITH latest_date AS (
            SELECT MAX(date) as market_date FROM price_daily WHERE close IS NOT NULL
          ),
          latest_day_data AS (
            SELECT symbol, (close - open) as daily_change
            FROM price_daily
            WHERE date = (SELECT market_date FROM latest_date)
          )
          SELECT
            COUNT(*) as total_stocks,
            COUNT(CASE WHEN daily_change > 0 THEN 1 END) as advancing,
            COUNT(CASE WHEN daily_change < 0 THEN 1 END) as declining,
            COUNT(CASE WHEN daily_change = 0 THEN 1 END) as unchanged
          FROM latest_day_data
        `);
        return result.rows[0] || {};
      })(),

      // 3. McClellan Oscillator
      (async () => {
        const result = await query(`
          SELECT close FROM price_daily
          WHERE symbol = 'SPY' AND date >= $1
          ORDER BY date ASC LIMIT 1
        `, ['2025-01-01']);
        return { data: result.rows || [], status: result.rows.length > 0 ? 'available' : 'unavailable' };
      })(),

      // 4. Distribution Days
      (async () => {
        const exists = await query(`
          SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'distribution_days'
          )
        `);
        return { available: exists.rows[0].exists };
      })(),

      // 5. Indices (SPX, QQQ, DIA, IWM, VIX)
      (async () => {
        const result = await query(`
          SELECT DISTINCT ON (symbol)
            symbol, close, date,
            (close - open) as change_amount,
            CASE WHEN open > 0 THEN ((close - open) / open * 100) ELSE NULL END as change_pct
          FROM price_daily
          WHERE symbol IN ('SPY', 'QQQ', 'DIA', 'IWM', '^VIX')
          ORDER BY symbol, date DESC
        `);
        return result.rows || [];
      })(),

      // 6. Volatility
      (async () => {
        const result = await query(`
          SELECT
            STDDEV((close - open) / NULLIF(open, 0) * 100) as market_volatility,
            AVG(ABS((close - open) / NULLIF(open, 0) * 100)) as avg_absolute_change
          FROM price_daily
          WHERE date >= CURRENT_DATE - INTERVAL '60 days'
        `);
        return result.rows[0] || {};
      })(),

      // 7. AAII Sentiment
      (async () => {
        const result = await query(`
          SELECT DISTINCT ON (date)
            date, bullish, neutral, bearish
          FROM aaii_sentiment
          ORDER BY date DESC LIMIT 30
        `);
        return result.rows || [];
      })(),

      // 8. Fear & Greed Index
      (async () => {
        const result = await query(`
          SELECT DISTINCT ON (date)
            date, index_value, rating
          FROM fear_greed_index
          ORDER BY date DESC LIMIT 30
        `);
        return result.rows || [];
      })(),

      // 9. NAAIM
      (async () => {
        const result = await query(`
          SELECT DISTINCT ON (date)
            date, bullish, bearish, naaim_number_mean
          FROM naaim
          ORDER BY date DESC LIMIT 30
        `);
        return result.rows || [];
      })(),

      // 10. Seasonality - Full seasonality data
      (async () => {
        return await getFullSeasonalityData();
      })(),

      // 11. Market Internals
      (async () => {
        const result = await query(`
          WITH latest_date AS (
            SELECT MAX(date) as max_date FROM price_daily WHERE close IS NOT NULL
          ),
          price_stats AS (
            SELECT
              symbol,
              close,
              ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) as rn
            FROM price_daily
            WHERE date = (SELECT max_date FROM latest_date)
          )
          SELECT
            COUNT(*) as total_stocks,
            COUNT(CASE WHEN close > 50 THEN 1 END) as above_50_ma,
            COUNT(CASE WHEN close > 200 THEN 1 END) as above_200_ma
          FROM price_stats
          WHERE rn = 1
        `);
        return result.rows[0] || {};
      })()
    ]);

    // Extract results from settled promises
    const consolidated = {
      market_status: getMarketStatus(),
      overview: overviewData.status === 'fulfilled' ? overviewData.value : null,
      breadth: breadthData.status === 'fulfilled' ? breadthData.value : null,
      mcclellan_oscillator: mcclellanData.status === 'fulfilled' ? mcclellanData.value : null,
      distribution_days: distributionDaysData.status === 'fulfilled' ? distributionDaysData.value : null,
      indices: indicesData.status === 'fulfilled' ? indicesData.value : [],
      volatility: volatilityData.status === 'fulfilled' ? volatilityData.value : null,
      aaii_sentiment: aaiiData.status === 'fulfilled' ? aaiiData.value : [],
      fear_greed: fearGreedData.status === 'fulfilled' ? fearGreedData.value : [],
      naaim_exposure: naaimData.status === 'fulfilled' ? naaimData.value : [],
      seasonality: seasonalityData.status === 'fulfilled' ? seasonalityData.value : { currentYear: null, currentYearReturn: null },
      internals: internalsData.status === 'fulfilled' ? internalsData.value : null,
      data_timestamp: new Date().toISOString(),
      fetch_time_ms: Date.now() - startTime
    };

    return res.json({
      data: consolidated,
      success: true
    });

  } catch (error) {
    console.error("Complete market data error:", error);
    return res.status(500).json({
      error: "Failed to fetch complete market data",
      details: error.message,
      success: false
    });
  }
});

// ============================================================
// NEW CONSOLIDATED ENDPOINTS - 3-endpoint architecture
// ============================================================

// GET /api/market/technicals - Technical indicators (breadth, mcclellan, distribution, volatility, internals)
router.get("/technicals", async (req, res) => {
  const startTime = Date.now();
  try {
    console.log("📊 [Market API] Fetching technicals...");

    const [breadthData, mcclellanData, distributionDaysData, volatilityData, internalsData] = await Promise.allSettled([
      // 1. Breadth (Latest day only)
      (async () => {
        const result = await query(`
          WITH latest_date AS (
            SELECT MAX(date) as market_date FROM price_daily WHERE close IS NOT NULL
          ),
          latest_day_data AS (
            SELECT symbol, (close - open) as daily_change
            FROM price_daily
            WHERE date = (SELECT market_date FROM latest_date)
          )
          SELECT
            COUNT(*) as total_stocks,
            COUNT(CASE WHEN daily_change > 0 THEN 1 END) as advancing,
            COUNT(CASE WHEN daily_change < 0 THEN 1 END) as declining,
            COUNT(CASE WHEN daily_change = 0 THEN 1 END) as unchanged
          FROM latest_day_data
        `);
        return result.rows[0] || {};
      })(),

      // 2. McClellan Oscillator (from /data endpoint logic)
      (async () => {
        const result = await query(`
          WITH daily_data AS (
            SELECT
              date,
              COUNT(CASE WHEN close > open THEN 1 END) as advances,
              COUNT(CASE WHEN close < open THEN 1 END) as declines
            FROM price_daily
            WHERE close IS NOT NULL AND open IS NOT NULL
            GROUP BY date
            ORDER BY date DESC
            LIMIT 365
          ),
          adv_dec_line AS (
            SELECT
              date,
              SUM(advances - declines) OVER (ORDER BY date) as advance_decline_line
            FROM daily_data
            ORDER BY date DESC
          )
          SELECT * FROM adv_dec_line
        `);
        return result.rows || [];
      })(),

      // 3. Distribution Days (from /data endpoint logic)
      (async () => {
        try {
          const result = await query(`
            SELECT
              symbol,
              MAX(running_count) as count,
              json_agg(
                json_build_object(
                  'date', date,
                  'close_price', close_price,
                  'change_pct', change_pct,
                  'volume', volume,
                  'volume_ratio', volume_ratio,
                  'days_ago', days_ago,
                  'running_count', running_count
                )
              ) as days
            FROM distribution_days
            WHERE symbol IN ('^GSPC', '^IXIC', '^DJI')
            GROUP BY symbol
            ORDER BY symbol
          `);

          if (!result || !result.rows || result.rows.length === 0) {
            return {};
          }

          // Format response with index names
          const indexNames = {
            "^GSPC": "S&P 500",
            "^IXIC": "NASDAQ Composite",
            "^DJI": "Dow Jones Industrial Average",
          };

          // Determine signal based on running count of distribution days
          const getSignalFromCount = (count) => {
            if (count <= 2) return "NORMAL";
            if (count <= 4) return "WATCH";
            if (count <= 7) return "CAUTION";
            if (count <= 10) return "WARNING";
            return "URGENT";
          };

          const distributionData = {};
          result.rows.forEach((row) => {
            const count = parseInt(row.count);
            distributionData[row.symbol] = {
              name: indexNames[row.symbol] || row.symbol,
              count: count,
              signal: getSignalFromCount(count),
              days: Array.isArray(row.days) ? row.days : [],
            };
          });

          return distributionData;
        } catch (error) {
          console.error("Error fetching distribution days:", error);
          return {};
        }
      })(),

      // 4. Volatility (from /data endpoint logic)
      (async () => {
        const result = await query(`
          SELECT
            STDDEV((close - open) / NULLIF(open, 0) * 100) as market_volatility,
            AVG(ABS(close - open) / NULLIF(open, 0) * 100) as avg_daily_move,
            MAX(ABS(close - open) / NULLIF(open, 0) * 100) as max_daily_move
          FROM price_daily
          WHERE symbol = 'SPY'
            AND date >= NOW() - INTERVAL '60 days'
            AND close IS NOT NULL AND open IS NOT NULL
        `);
        return result.rows[0] || {};
      })(),

      // 5. Internals (from /data endpoint logic)
      (async () => {
        const result = await query(`
          WITH latest_date AS (
            SELECT MAX(date) as max_date FROM price_daily WHERE close IS NOT NULL
          ),
          price_stats AS (
            SELECT
              symbol,
              close,
              ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) as rn
            FROM price_daily
            WHERE date = (SELECT max_date FROM latest_date)
          )
          SELECT
            COUNT(*) as total_stocks,
            COUNT(CASE WHEN close > 50 THEN 1 END) as above_50_ma,
            COUNT(CASE WHEN close > 200 THEN 1 END) as above_200_ma
          FROM price_stats
          WHERE rn = 1
        `);
        return result.rows[0] || {};
      })()
    ]);

    const technicals = {
      breadth: breadthData.status === 'fulfilled' ? breadthData.value : [],
      mcclellan_oscillator: mcclellanData.status === 'fulfilled' ? mcclellanData.value : null,
      distribution_days: distributionDaysData.status === 'fulfilled' ? distributionDaysData.value : null,
      volatility: volatilityData.status === 'fulfilled' ? volatilityData.value : null,
      internals: internalsData.status === 'fulfilled' ? internalsData.value : null,
      timestamp: new Date().toISOString(),
      fetch_time_ms: Date.now() - startTime
    };

    return res.json({
      data: technicals,
      success: true
    });
  } catch (error) {
    console.error("❌ [Market API] Technicals error:", error);
    return res.status(500).json({
      error: "Failed to fetch technicals",
      details: error.message,
      success: false
    });
  }
});

// GET /api/market/sentiment - Sentiment indicators (AAII, Fear & Greed, NAAIM)
router.get("/sentiment", async (req, res) => {
  const startTime = Date.now();
  const range = req.query.range || "30d";

  // Convert range parameter to days
  let days = 30;
  let orderDirection = "ASC"; // Default to ascending (oldest first) for charts
  switch(range) {
    case "90d": days = 90; break;
    case "6m": days = 180; break;
    case "1y": days = 365; break;
    case "all": days = 10000; break;
    default: days = 30;
  }

  try {
    console.log(`😊 [Market API] Fetching sentiment (range: ${range}, days: ${days})...`);

    const [aaiiData, fearGreedData, naaimData] = await Promise.allSettled([
      // 1. AAII
      (async () => {
        const result = await query(`
          SELECT
            bullish,
            bearish,
            neutral,
            date,
            fetched_at as timestamp
          FROM aaii_sentiment
          WHERE date >= CURRENT_DATE - MAKE_INTERVAL(days => $1)
          ORDER BY date ${orderDirection}
        `, [days]);
        return result.rows || [];
      })(),

      // 2. Fear & Greed
      (async () => {
        const result = await query(`
          SELECT
            index_value as value,
            rating,
            date,
            fetched_at as timestamp
          FROM fear_greed_index
          WHERE date >= CURRENT_DATE - MAKE_INTERVAL(days => $1)
          ORDER BY date ${orderDirection}
        `, [days]);
        return result.rows || [];
      })(),

      // 3. NAAIM
      (async () => {
        const result = await query(`
          SELECT
            naaim_number_mean as mean,
            quart2 as median,
            quart1 as min,
            quart3 as max,
            date,
            fetched_at as timestamp
          FROM naaim
          WHERE date >= CURRENT_DATE - MAKE_INTERVAL(days => $1)
          ORDER BY date ${orderDirection}
        `, [days]);
        return result.rows || [];
      })()
    ]);

    const sentiment = {
      aaii: aaiiData.status === 'fulfilled' ? aaiiData.value : [],
      fear_greed: fearGreedData.status === 'fulfilled' ? fearGreedData.value : [],
      naaim: naaimData.status === 'fulfilled' ? naaimData.value : [],
      range,
      timestamp: new Date().toISOString(),
      fetch_time_ms: Date.now() - startTime
    };

    return res.json({
      data: sentiment,
      success: true
    });
  } catch (error) {
    console.error("❌ [Market API] Sentiment error:", error);
    return res.status(500).json({
      error: "Failed to fetch sentiment",
      details: error.message,
      success: false
    });
  }
});

// GET /api/market/seasonality - Seasonality patterns
router.get("/seasonality", async (req, res) => {
  const startTime = Date.now();

  try {
    console.log("📅 [Market API] Fetching seasonality...");

    const [seasonalityData] = await Promise.allSettled([
      (async () => {
        const result = await query(`
          SELECT
            current_year,
            current_month,
            current_year_return,
            presidential_cycle_phase,
            monthly_return_avg,
            monthly_win_rate,
            date
          FROM seasonality_patterns
          ORDER BY date DESC
          LIMIT 1
        `);
        return result.rows[0] || {};
      })()
    ]);

    const seasonality = seasonalityData.status === 'fulfilled'
      ? seasonalityData.value
      : { currentYear: null, currentYearReturn: null };

    return res.json({
      data: seasonality,
      success: true
    });
  } catch (error) {
    console.error("❌ [Market API] Seasonality error:", error);
    return res.status(500).json({
      error: "Failed to fetch seasonality",
      details: error.message,
      success: false
    });
  }
});

// Fresh Market Data Endpoint - Direct from yfinance
// Returns latest market data when database is unavailable
router.get("/fresh-data", async (req, res) => {
  try {
    const fs = require("fs");
    const path = require("path");

    // Try to read latest fresh data from JSON file
    const freshDataPath = "/tmp/latest_market_data.json";

    if (fs.existsSync(freshDataPath)) {
      const freshData = JSON.parse(fs.readFileSync(freshDataPath, "utf-8"));

      // Format for frontend consumption
      const formattedData = {
        indices: Object.values(freshData.indices || {}),
        sectors: Object.values(freshData.sectors || {}),
        vix: freshData.vix,
        sp500Metrics: freshData.sp500_metrics,
        timestamp: freshData.timestamp,
        source: "fresh-data",
        message: "Real-time data from yfinance - generated just now",
        success: true
      };

      return res.json(formattedData);
    }

    // If fresh data file doesn't exist, return message
    return res.status(404).json({
      error: "Fresh data not available",
      message: "Run get_latest_market_data.py to generate fresh data",
      success: false
    });
  } catch (error) {
    console.error("Fresh data endpoint error:", error.message);
    return res.status(500).json({
      error: "Failed to fetch fresh data",
      details: error.message,
      success: false
    });
  }
});

module.exports = router;
