const express = require("express");

const { query } = require("../utils/database");

const router = express.Router();

// Root endpoint - returns available sub-endpoints
router.get("/", (req, res) => {
  return res.json({
    data: {
      endpoint: "economic",
      description: "Economic indicators and financial conditions data",
      available_routes: [
        "GET /leading-indicators - Comprehensive leading, lagging, and coincident economic indicators with 50+ data points",
        "GET /yield-curve-full - Treasury yield curve (3M-30Y) AND credit spreads with 60-day historical data - consolidated endpoint",
        "GET /calendar - Upcoming economic events with dates and forecasts"
      ]
    },
    success: true
  });
});

// ============================================
// LEADING INDICATORS - Comprehensive overview
// ============================================
router.get("/leading-indicators", async (req, res) => {
  console.log("📈 Leading indicators endpoint called");

  try {
    // Get latest AND historical values for trend analysis
    // Query for economic indicators including full yield curve data
    const economicQuery = `
      SELECT
        series_id,
        value,
        date,
        ROW_NUMBER() OVER (PARTITION BY series_id ORDER BY date DESC) as rn
      FROM economic_data
      WHERE series_id IN (
        -- OFFICIAL LEI COMPONENTS (10)
        'UNRATE', 'PAYEMS', 'CPIAUCSL', 'GDPC1', 'HOUST', 'ICSA', 'T10Y2Y', 'BUSLOANS', 'SP500', 'VIXCLS',
        -- LAGGING INDICATORS (7)
        'UEMPMEAN', 'PRIME', 'MMNRNJ', 'ISITC', 'TOTALSA', 'IMPGS', 'LBMVRTQ',
        -- COINCIDENT/SECONDARY INDICATORS (5)
        'INDPRO', 'UMCSENT', 'MICH', 'RSXFS', 'EMSRATIO',
        -- ADDITIONAL SECONDARY
        'FEDFUNDS',
        -- NEW ECONOMIC INDICATORS (4) - Labor, Commodity, Credit, Housing
        'CIVPART', 'DCOILWTICO', 'MORTGAGE30US', 'BAMLH0A0HYM2',
        -- MONEY SUPPLY & FEDERAL POLICY
        'M1NS', 'M2SL', 'WALCL',
        -- INFLATION INDICATORS
        'CPILFESL', 'PPIACO',
        -- PRODUCTION & CAPACITY
        'CUMFSL', 'PERMIT',
        -- Full yield curve maturities for comprehensive chart
        'DGS3MO', 'DGS6MO', 'DGS1', 'DGS2', 'DGS3', 'DGS5', 'DGS7',
        'DGS10', 'DGS20', 'DGS30'
      )
      ORDER BY series_id, date DESC
    `;

    // Also fetch upcoming economic calendar events
    const calendarQuery = `
      SELECT
        event_name,
        event_date,
        event_time,
        importance,
        category,
        forecast_value,
        previous_value
      FROM economic_calendar
      WHERE event_date >= CURRENT_DATE
        AND event_date <= CURRENT_DATE + INTERVAL '120 days'
      ORDER BY event_date, event_time
      LIMIT 100
    `;

    // Execute both queries in parallel with error handling
    let result = { rows: [] };
    let calendarResult = { rows: [] };

    try {
      const [ecResult, calResult] = await Promise.all([
        query(economicQuery).catch(e => {
          console.warn("Economic data table not available:", e.message);
          return { rows: [] };
        }),
        query(calendarQuery).catch(e => {
          console.warn("Economic calendar table not available:", e.message);
          return { rows: [] };
        })
      ]);
      result = ecResult;
      calendarResult = calResult;
    } catch (e) {
      console.warn("Could not fetch economic data:", e.message);
      result = { rows: [] };
      calendarResult = { rows: [] };
    }

    const indicators = {};
    const historicalData = {}; // Store historical data for trends
    const seriesCount = {};

    console.log(`[DATA] Leading indicators query returned ${result.rows?.length || 0} data points`);
    console.log(`📅 Economic calendar events found: ${calendarResult?.rows?.length || 0}`);

    // Parse results - group by series and collect historical values
    // Data-driven limits based on frequency and available data:
    // - Quarterly (GDP): All points for long history
    // - Monthly indicators: All/most available points
    // - Weekly/Daily: Balance between detail and readability
    const maxHistoricalPoints = {
      // Quarterly Data (Low frequency = Keep all)
      'GDPC1': 50,        // GDP: All quarterly releases (~2+ years)

      // Monthly Data (Keep all for trend analysis)
      'UNRATE': 50,       // Unemployment: ~4+ years available
      'FEDFUNDS': 50,     // Fed Funds: ~4+ years available
      'CPIAUCSL': 30,     // CPI: ~2.5 years available
      'PAYEMS': 30,       // Payroll: ~2+ years available
      'INDPRO': 25,       // Industrial Production: Recent data only
      'HOUST': 20,        // Housing Starts: Recent data only
      'MICH': 20,         // Michigan Sentiment: ~1 year available

      // Weekly/Daily Data (Cap for chart readability)
      'ICSA': 60,         // Initial Claims: ~1+ year recent
      'SP500': 50,        // Stock prices: ~1 year daily
      'VIXCLS': 60,       // VIX: ~10 months daily

      // Yield Curve (Daily data, recent focus)
      'DGS10': 30,        // 10-Year Treasury: Recent only
      'DGS2': 30,         // 2-Year Treasury: Recent only
      'DGS3MO': 30,       // 3-Month Treasury: Recent only
      'T10Y2Y': 30,       // 2y10y Spread: Derived, recent
    };

    result.rows.forEach((row) => {
      const sid = row.series_id;
      const maxPoints = maxHistoricalPoints[sid] || 20;

      // Initialize series if not seen before
      if (!historicalData[sid]) {
        historicalData[sid] = [];
        seriesCount[sid] = 0;
      }

      // Keep the first occurrence as the latest value
      if (seriesCount[sid] === 0) {
        indicators[sid] = {
          value: parseFloat(row.value),
          date: row.date,
        };
        console.log(`  [OK] ${sid}: ${row.value} (${row.date})`);
      }

      // Collect historical data points - use series-specific max
      if (seriesCount[sid] < maxPoints) {
        historicalData[sid].push({
          value: parseFloat(row.value),
          date: row.date,
        });
        seriesCount[sid]++;
      }
    });

    // Helper function to calculate trend data
    const calculateTrend = (seriesId) => {
      const hist = historicalData[seriesId];
      if (!hist || hist.length < 2) return { change: null, trend: null };

      const current = hist[0].value;
      const previous = hist[1].value;
      const changePercent = ((current - previous) / Math.abs(previous)) * 100;
      const trend = current > previous ? "up" : current < previous ? "down" : "stable";

      return {
        change: Math.abs(changePercent) < 0.01 ? 0 : parseFloat(changePercent.toFixed(2)),
        trend: trend,
      };
    };

    // VALIDATE required series exist - FAIL if missing (NO FALLBACK)
    const requiredSeries = ['UNRATE', 'PAYEMS', 'CPIAUCSL', 'GDPC1', 'DGS10', 'DGS2', 'T10Y2Y', 'SP500', 'VIXCLS', 'FEDFUNDS', 'INDPRO', 'HOUST', 'MICH', 'ICSA', 'BUSLOANS'];
    const missingSeries = requiredSeries.filter(s => !indicators[s]);
    if (missingSeries.length > 0) {
      console.error(`[ERROR] MISSING REQUIRED SERIES: ${missingSeries.join(', ')}`);
      return res.status(500).json({
        error: "Missing required economic indicators from FRED database",
        success: false,
        missing: missingSeries,
        message: "Please run loadecondata.py to load economic indicators",
        details: `Found ${result.rows.length} series, but missing ${missingSeries.length} critical indicators`
      });
    }

    // Calculate yield curve data
    const spread2y10y = indicators["T10Y2Y"] ? indicators["T10Y2Y"].value : null;
    const isInverted = spread2y10y !== null && spread2y10y < 0;

    const indicatorsArray = [
          {
            name: "Unemployment Rate",
            category: "LEI", // Official Leading Economic Indicator
            value: indicators["UNRATE"] ? indicators["UNRATE"].value.toFixed(1) + "%" : null,
            rawValue: indicators["UNRATE"] ? indicators["UNRATE"].value : null,
            unit: "%",
            change: historicalData["UNRATE"] && historicalData["UNRATE"].length > 1
              ? ((indicators["UNRATE"].value - historicalData["UNRATE"][1].value) / historicalData["UNRATE"][1].value * 100).toFixed(2)
              : null,
            trend: historicalData["UNRATE"] && historicalData["UNRATE"].length > 1
              ? (indicators["UNRATE"].value > historicalData["UNRATE"][1].value ? "up" : indicators["UNRATE"].value < historicalData["UNRATE"][1].value ? "down" : "stable")
              : null,
            signal: indicators["UNRATE"] ? (indicators["UNRATE"].value < 4.5 ? "Positive" : indicators["UNRATE"].value > 6 ? "Negative" : null) : null,
            description: "Percentage of labor force actively seeking employment",
            strength: indicators["UNRATE"] ? Math.min(100, Math.max(0, 100 - (indicators["UNRATE"].value - 3) * 10)) : null,
            importance: "high",
            date: indicators["UNRATE"] ? indicators["UNRATE"].date : null,
            history: historicalData["UNRATE"] ? historicalData["UNRATE"].reverse() : [], // Reverse to be chronological for charts
          },
          {
            name: "Inflation (CPI)",
            category: "LEI", // Official Leading Economic Indicator
            value: indicators["CPIAUCSL"] ? indicators["CPIAUCSL"].value.toFixed(1) : null,
            rawValue: indicators["CPIAUCSL"] ? indicators["CPIAUCSL"].value : null,
            unit: "Index",
            ...calculateTrend("CPIAUCSL"),
            signal: indicators["CPIAUCSL"] ? (indicators["CPIAUCSL"].value < 260 ? "Positive" : indicators["CPIAUCSL"].value > 310 ? "Negative" : null) : null,
            description: "Consumer Price Index measuring inflation",
            strength: indicators["CPIAUCSL"] ? Math.min(100, Math.max(0, 100 - Math.abs(indicators["CPIAUCSL"].value - 280))) : null,
            importance: "high",
            date: indicators["CPIAUCSL"] ? indicators["CPIAUCSL"].date : null,
            history: historicalData["CPIAUCSL"] ? historicalData["CPIAUCSL"].reverse() : [],
          },
          {
            name: "Fed Funds Rate",
            category: "LEI", // Official Leading Economic Indicator
            value: indicators["FEDFUNDS"] ? indicators["FEDFUNDS"].value.toFixed(2) + "%" : null,
            rawValue: indicators["FEDFUNDS"] ? indicators["FEDFUNDS"].value : null,
            unit: "%",
            ...calculateTrend("FEDFUNDS"),
            signal: indicators["FEDFUNDS"] ? (indicators["FEDFUNDS"].value < 2 ? "Positive" : indicators["FEDFUNDS"].value > 4 ? "Negative" : null) : null,
            description: "Federal Reserve target interest rate",
            strength: indicators["FEDFUNDS"] ? Math.min(100, Math.max(0, 100 - indicators["FEDFUNDS"].value * 15)) : null,
            importance: "high",
            date: indicators["FEDFUNDS"] ? indicators["FEDFUNDS"].date : null,
            history: historicalData["FEDFUNDS"] ? historicalData["FEDFUNDS"].reverse() : [],
          },
          {
            name: "GDP Growth",
            category: "LEI", // Official Leading Economic Indicator
            value: indicators["GDPC1"] ? (indicators["GDPC1"].value / 1000).toFixed(1) + "T" : null,
            rawValue: indicators["GDPC1"] ? indicators["GDPC1"].value : null,
            unit: "Billions",
            ...calculateTrend("GDPC1"),
            signal: indicators["GDPC1"] ? (indicators["GDPC1"].value > 20000 ? "Positive" : indicators["GDPC1"].value < 18000 ? "Negative" : null) : null,
            description: "Real Gross Domestic Product",
            strength: indicators["GDPC1"] ? Math.min(100, Math.max(0, (indicators["GDPC1"].value - 18000) / 50)) : null,
            importance: "high",
            date: indicators["GDPC1"] ? indicators["GDPC1"].date : null,
            history: historicalData["GDPC1"] ? historicalData["GDPC1"].reverse() : [],
          },
          {
            name: "Payroll Employment",
            category: "LEI", // Official Leading Economic Indicator
            value: indicators["PAYEMS"] ? (indicators["PAYEMS"].value / 1000).toFixed(1) + "M" : null,
            rawValue: indicators["PAYEMS"] ? indicators["PAYEMS"].value : null,
            unit: "Thousands",
            ...calculateTrend("PAYEMS"),
            signal: indicators["PAYEMS"] ? (indicators["PAYEMS"].value > 155000 ? "Positive" : indicators["PAYEMS"].value < 145000 ? "Negative" : null) : null,
            description: "Total nonfarm payroll employment",
            strength: indicators["PAYEMS"] ? Math.min(100, Math.max(0, (indicators["PAYEMS"].value - 140000) / 200)) : null,
            importance: "high",
            date: indicators["PAYEMS"] ? indicators["PAYEMS"].date : null,
            history: historicalData["PAYEMS"] ? historicalData["PAYEMS"].reverse() : [],
          },
          {
            name: "Housing Starts",
            category: "LEI", // Official Leading Economic Indicator
            value: indicators["HOUST"] ? indicators["HOUST"].value.toFixed(0) + "K" : null,
            rawValue: indicators["HOUST"] ? indicators["HOUST"].value : null,
            unit: "Thousands",
            ...calculateTrend("HOUST"),
            signal: indicators["HOUST"] ? (indicators["HOUST"].value > 1500 ? "Positive" : indicators["HOUST"].value < 1200 ? "Negative" : null) : null,
            description: "Number of new residential construction projects started",
            strength: indicators["HOUST"] ? Math.min(100, Math.max(0, (indicators["HOUST"].value - 1000) / 10)) : null,
            importance: "medium",
            date: indicators["HOUST"] ? indicators["HOUST"].date : null,
            history: historicalData["HOUST"] ? historicalData["HOUST"].reverse() : [],
          },
          {
            name: "Consumer Sentiment",
            category: "SECONDARY", // Additional Economic Indicator
            value: indicators["MICH"] ? indicators["MICH"].value.toFixed(1) : null,
            rawValue: indicators["MICH"] ? indicators["MICH"].value : null,
            unit: "Index",
            ...calculateTrend("MICH"),
            signal: indicators["MICH"] ? (indicators["MICH"].value > 80 ? "Positive" : indicators["MICH"].value < 60 ? "Negative" : null) : null,
            description: "Consumer confidence and spending expectations",
            strength: indicators["MICH"] ? Math.min(100, Math.max(0, indicators["MICH"].value - 20)) : null,
            importance: "high",
            date: indicators["MICH"] ? indicators["MICH"].date : null,
            history: historicalData["MICH"] ? historicalData["MICH"].reverse() : [],
          },
          {
            name: "Industrial Production",
            category: "SECONDARY", // Additional Economic Indicator
            value: indicators["INDPRO"] ? indicators["INDPRO"].value.toFixed(1) : null,
            rawValue: indicators["INDPRO"] ? indicators["INDPRO"].value : null,
            unit: "Index",
            ...calculateTrend("INDPRO"),
            signal: indicators["INDPRO"] ? (indicators["INDPRO"].value > 100 ? "Positive" : indicators["INDPRO"].value < 95 ? "Negative" : null) : null,
            description: "Measure of real output for all manufacturing, mining, and utilities facilities",
            strength: indicators["INDPRO"] ? Math.min(100, Math.max(0, (indicators["INDPRO"].value - 90) * 2)) : null,
            importance: "medium",
            date: indicators["INDPRO"] ? indicators["INDPRO"].date : null,
            history: historicalData["INDPRO"] ? historicalData["INDPRO"].reverse() : [],
          },
          {
            name: "Initial Jobless Claims",
            category: "LEI", // Official Leading Economic Indicator
            value: indicators["ICSA"] ? (indicators["ICSA"].value / 1000).toFixed(0) + "K" : null,
            rawValue: indicators["ICSA"] ? indicators["ICSA"].value : null,
            unit: "Thousands",
            ...calculateTrend("ICSA"),
            signal: indicators["ICSA"] ? (indicators["ICSA"].value < 225 ? "Positive" : indicators["ICSA"].value > 275 ? "Negative" : null) : null,
            description: "Weekly unemployment insurance claims",
            strength: indicators["ICSA"] ? Math.min(100, Math.max(0, 100 - (indicators["ICSA"].value - 200) / 2)) : null,
            importance: "medium",
            date: indicators["ICSA"] ? indicators["ICSA"].date : null,
            history: historicalData["ICSA"] ? historicalData["ICSA"].reverse() : [],
          },
          {
            name: "Business Loans",
            category: "LEI", // Official Leading Economic Indicator
            value: indicators["BUSLOANS"] ? (indicators["BUSLOANS"].value / 1000).toFixed(1) + "B" : null,
            rawValue: indicators["BUSLOANS"] ? indicators["BUSLOANS"].value : null,
            unit: "Billions",
            ...calculateTrend("BUSLOANS"),
            signal: indicators["BUSLOANS"] ? (indicators["BUSLOANS"].value > 2000000 ? "Positive" : indicators["BUSLOANS"].value < 1800000 ? "Negative" : null) : null,
            description: "Commercial and industrial loans outstanding",
            strength: indicators["BUSLOANS"] ? Math.min(100, Math.max(0, (indicators["BUSLOANS"].value - 1700000) / 10000)) : null,
            importance: "medium",
            date: indicators["BUSLOANS"] ? indicators["BUSLOANS"].date : null,
            history: historicalData["BUSLOANS"] ? historicalData["BUSLOANS"].reverse() : [],
          },
          {
            name: "S&P 500 Index",
            category: "LEI", // Official Leading Economic Indicator
            value: indicators["SP500"] ? indicators["SP500"].value.toFixed(0) : null,
            rawValue: indicators["SP500"] ? indicators["SP500"].value : null,
            unit: "Index",
            ...calculateTrend("SP500"),
            signal: indicators["SP500"] ? (indicators["SP500"].value > 5500 ? "Positive" : indicators["SP500"].value < 4500 ? "Negative" : null) : null,
            description: "S&P 500 stock market index - leading indicator of economic activity",
            strength: indicators["SP500"] ? Math.min(100, Math.max(0, (indicators["SP500"].value - 4000) / 30)) : null,
            importance: "high",
            date: indicators["SP500"] ? indicators["SP500"].date : null,
            history: historicalData["SP500"] ? historicalData["SP500"].reverse() : [],
          },
          {
            name: "Market Volatility (VIX)",
            category: "LEI", // Official Leading Economic Indicator
            value: indicators["VIXCLS"] ? indicators["VIXCLS"].value.toFixed(1) : null,
            rawValue: indicators["VIXCLS"] ? indicators["VIXCLS"].value : null,
            unit: "Index",
            ...calculateTrend("VIXCLS"),
            signal: indicators["VIXCLS"] ? (indicators["VIXCLS"].value < 15 ? "Positive" : indicators["VIXCLS"].value > 25 ? "Negative" : null) : null,
            description: "CBOE Volatility Index - fear gauge and market sentiment",
            strength: indicators["VIXCLS"] ? Math.min(100, Math.max(0, 100 - indicators["VIXCLS"].value * 3)) : null,
            importance: "high",
            date: indicators["VIXCLS"] ? indicators["VIXCLS"].date : null,
            history: historicalData["VIXCLS"] ? historicalData["VIXCLS"].reverse() : [],
          },
          {
            name: "Yield Curve (2Y-10Y Spread)",
            category: "LEI", // Official Leading Economic Indicator
            value: indicators["T10Y2Y"] ? indicators["T10Y2Y"].value.toFixed(2) + " %" : null,
            rawValue: indicators["T10Y2Y"] ? indicators["T10Y2Y"].value : null,
            unit: "%",
            ...calculateTrend("T10Y2Y"),
            signal: indicators["T10Y2Y"] ? (indicators["T10Y2Y"].value > 0 ? "Positive" : indicators["T10Y2Y"].value < -0.5 ? "Negative" : null) : null,
            description: "Difference between 10-year and 2-year Treasury yields - recession predictor",
            strength: indicators["T10Y2Y"] ? Math.min(100, Math.max(0, 50 + indicators["T10Y2Y"].value * 50)) : null,
            importance: "high",
            date: indicators["T10Y2Y"] ? indicators["T10Y2Y"].date : null,
            history: historicalData["T10Y2Y"] ? historicalData["T10Y2Y"].reverse() : [],
          },
        ].filter(ind => ind.rawValue !== null); // Filter out indicators with no data

    // Return in standard format with data wrapper and success field
    res.json({
      data: {
        indicators: indicatorsArray
      },
      success: true
    });
  } catch (error) {
    console.error("Leading indicators error:", error);
    res.status(500).json({
      error: "Failed to fetch leading indicators",
      success: false
    });
  }
});

// ============================================
// YIELD CURVE - Full maturity yields with history
// ============================================
// Consolidated from market routes for API cleanliness

router.get("/yield-curve-full", async (req, res) => {
  console.log("📈 Treasury Yield Curve & Credit Spreads endpoint called");

  try {
    // Fetch treasury maturity yields with 60-day history - only request what might exist
    const yieldCurveQuery = `
      SELECT
        series_id,
        value,
        date
      FROM economic_data
      WHERE series_id IN (
        'DGS3MO', 'DGS6MO', 'DGS1', 'DGS2', 'DGS3', 'DGS5', 'DGS7', 'DGS10', 'DGS20', 'DGS30',
        'T10Y2Y', 'T10Y3M', 'T10Y3MM',
        'BAMLH0A0HYM2', 'BAMLH0A0IG', 'BAMLH0A0PRI', 'BAA', 'AAA', 'VIXCLS'
      )
      ORDER BY date DESC, series_id
      LIMIT 500
    `;

    const result = await query(yieldCurveQuery);
    const dataBySeriesAndDate = {};

    // Organize data by series and date
    result.rows.forEach(row => {
      const key = `${row.series_id}`;
      if (!dataBySeriesAndDate[key]) {
        dataBySeriesAndDate[key] = [];
      }
      dataBySeriesAndDate[key].push({
        date: row.date,
        value: parseFloat(row.value)
      });
    });

    // Sort each series by date (oldest first for charting)
    Object.keys(dataBySeriesAndDate).forEach(key => {
      dataBySeriesAndDate[key].sort((a, b) => new Date(a.date) - new Date(b.date));
    });

    // Get latest values for current curve - only include maturities we have data for
    const currentCurve = {};
    const maturityMap = {
      'DGS3MO': '3M',
      'DGS6MO': '6M',
      'DGS1': '1Y',
      'DGS2': '2Y',
      'DGS3': '3Y',
      'DGS5': '5Y',
      'DGS7': '7Y',
      'DGS10': '10Y',
      'DGS20': '20Y',
      'DGS30': '30Y'
    };

    Object.entries(maturityMap).forEach(([seriesId, maturity]) => {
      const value = dataBySeriesAndDate[seriesId]?.[dataBySeriesAndDate[seriesId].length - 1]?.value;
      if (value !== undefined && value !== null) {
        currentCurve[maturity] = value;
      }
    });

    const treasurySpreads = {
      'T10Y2Y': dataBySeriesAndDate['T10Y2Y']?.[dataBySeriesAndDate['T10Y2Y'].length - 1]?.value || null,
      'T10Y3M': dataBySeriesAndDate['T10Y3M']?.[dataBySeriesAndDate['T10Y3M'].length - 1]?.value || null,
    };

    // Calculate if curve is inverted
    const spread2y10y = treasurySpreads['T10Y2Y'];
    const isInverted = spread2y10y !== null && spread2y10y < 0;

    // Credit spreads data - only include what we have
    const creditSpreads = {};
    if (dataBySeriesAndDate['BAMLH0A0HYM2']) {
      creditSpreads.highYield = {
        value: dataBySeriesAndDate['BAMLH0A0HYM2'][dataBySeriesAndDate['BAMLH0A0HYM2'].length - 1].value
      };
    }
    if (dataBySeriesAndDate['BAMLH0A0IG']) {
      creditSpreads.investmentGrade = {
        value: dataBySeriesAndDate['BAMLH0A0IG'][dataBySeriesAndDate['BAMLH0A0IG'].length - 1].value
      };
    }
    if (dataBySeriesAndDate['BAA']) {
      creditSpreads.baaYield = {
        value: dataBySeriesAndDate['BAA'][dataBySeriesAndDate['BAA'].length - 1].value
      };
    }
    if (dataBySeriesAndDate['AAA']) {
      creditSpreads.aaaYield = {
        value: dataBySeriesAndDate['AAA'][dataBySeriesAndDate['AAA'].length - 1].value
      };
    }
    if (dataBySeriesAndDate['VIXCLS']) {
      creditSpreads.vix = {
        value: dataBySeriesAndDate['VIXCLS'][dataBySeriesAndDate['VIXCLS'].length - 1].value
      };
    }

    console.log(`✅ Yield curve data: ${Object.keys(currentCurve).length} maturities, spreads: ${Object.keys(treasurySpreads).filter(k => treasurySpreads[k] !== null).length}, isInverted: ${isInverted}`);

    res.json({
      data: {
        currentCurve,
        spreads: treasurySpreads,
        isInverted,
        history: {
          'DGS3MO': dataBySeriesAndDate['DGS3MO'] || [],
          'DGS6MO': dataBySeriesAndDate['DGS6MO'] || [],
          'DGS1': dataBySeriesAndDate['DGS1'] || [],
          'DGS2': dataBySeriesAndDate['DGS2'] || [],
          'DGS3': dataBySeriesAndDate['DGS3'] || [],
          'DGS5': dataBySeriesAndDate['DGS5'] || [],
          'DGS7': dataBySeriesAndDate['DGS7'] || [],
          'DGS10': dataBySeriesAndDate['DGS10'] || [],
          'DGS20': dataBySeriesAndDate['DGS20'] || [],
          'DGS30': dataBySeriesAndDate['DGS30'] || [],
          'T10Y2Y': dataBySeriesAndDate['T10Y2Y'] || [],
          'T10Y3M': dataBySeriesAndDate['T10Y3M'] || [],
        },
        credit: {
          currentSpreads: creditSpreads,
          history: {
            'BAMLH0A0HYM2': dataBySeriesAndDate['BAMLH0A0HYM2'] || [],
            'BAMLH0A0IG': dataBySeriesAndDate['BAMLH0A0IG'] || [],
            'BAMLH0A0PRI': dataBySeriesAndDate['BAMLH0A0PRI'] || [],
            'BAA': dataBySeriesAndDate['BAA'] || [],
            'AAA': dataBySeriesAndDate['AAA'] || [],
            'VIXCLS': dataBySeriesAndDate['VIXCLS'] || [],
          }
        },
        source: "Federal Reserve Economic Data (FRED)"
      },
      success: true
    });
  } catch (error) {
    console.error("Yield curve error:", error);
    res.status(500).json({
      error: "Failed to fetch yield curve data",
      success: false
    });
  }
});

// CONSOLIDATED: Credit spreads data is now included in /yield-curve-full endpoint
// This endpoint has been consolidated with Treasury yield curve data for cleaner API

// ============================================
// ECONOMIC CALENDAR - Upcoming events
// ============================================
router.get("/calendar", async (req, res) => {
  try {
    const { start_date, end_date, importance, country } = req.query;
    console.log(
      `📅 Economic calendar requested - start: ${start_date}, end: ${end_date}, importance: ${importance}, country: ${country}`
    );

    // Build WHERE clause dynamically
    let whereClause = "WHERE event_date >= COALESCE(NULLIF($1, '')::date, CURRENT_DATE)";
    const queryParams = [start_date];
    let paramCount = 1;

    if (end_date) {
      paramCount++;
      whereClause += ` AND event_date <= NULLIF($${paramCount}, '')::date`;
      queryParams.push(end_date);
    }

    if (importance) {
      paramCount++;
      whereClause += ` AND importance = $${paramCount}`;
      queryParams.push(importance);
    }

    if (country) {
      paramCount++;
      whereClause += ` AND country = $${paramCount}`;
      queryParams.push(country);
    }

    const calendarResult = await query(
      `
      SELECT
        event_id,
        event_name,
        country,
        category,
        importance,
        event_date,
        event_time,
        timezone,
        forecast_value,
        previous_value,
        actual_value,
        unit,
        frequency,
        source,
        description
      FROM economic_calendar
      ${whereClause}
      ORDER BY event_date ASC, event_time ASC
      LIMIT 100
    `,
      queryParams
    );

    res.json({
      data: {
        events: calendarResult.rows || [],
        period: {
          start: start_date || "auto",
          end: end_date || "auto"
        }
      },
      success: true
    });
  } catch (error) {
    console.error("Economic calendar error:", error);
    return res.status(500).json({
      error: "Failed to fetch economic calendar data",
      success: false
    });
  }
});

module.exports = router;
