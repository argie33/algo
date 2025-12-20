/**
 * REAL Portfolio Optimization Engine
 * Integrates with Alpaca + Database for actual portfolio optimization
 *
 * Features:
 * - Analyzes REAL portfolio metrics (beta, alpha, Sharpe, volatility)
 * - Identifies metric weaknesses
 * - Recommends trades to improve metrics
 * - Before/after simulation with actual numbers
 */

const { query } = require('./database');
const AlpacaService = require('./alpacaService');

/**
 * Main portfolio optimizer
 */
async function optimizePortfolio(userId, options = {}) {
  const {
    maxRecommendations = 10,
    minStockScore = 65,
    maxPositionSize = 0.15,
  } = options;

  try {
    // Step 1: Get portfolio (from Alpaca with DB fallback)
    const portfolio = await getPortfolioFromAlpaca(userId);

    if (!portfolio || portfolio.holdings.length === 0) {
      const emptyMetrics = calculatePortfolioMetrics(null);
      return {
        success: true,
        message: 'Portfolio is empty',
        current: {
          portfolio: { holdings: [], totalValue: 0, count: 0 },
          metrics: emptyMetrics,
          weaknesses: [],
        },
        recommendations: [],
        simulated: {
          improvements: compareMetrics(emptyMetrics, emptyMetrics),
        },
      };
    }

    // Step 2: Calculate metrics
    const metrics = calculatePortfolioMetrics(portfolio);

    // Step 3: Identify weaknesses
    const weaknesses = identifyWeakMetrics(metrics);

    // Step 4: Get candidate stocks
    const candidates = await getCandidateStocks(
      minStockScore,
      portfolio.holdings.map(h => h.symbol),
      maxRecommendations * 3
    );

    // Step 5: Generate recommendations
    const recommendations = generateRecommendations(
      portfolio,
      metrics,
      weaknesses,
      candidates,
      maxRecommendations
    );

    // Step 6: Simulate
    const simulated = simulatePortfolio(portfolio, recommendations);
    const simulatedMetrics = calculatePortfolioMetrics(simulated);

    return {
      success: true,
      current: {
        portfolio,
        metrics,
        weaknesses,
      },
      recommendations,
      simulated: {
        portfolio: simulated,
        metrics: simulatedMetrics,
        improvements: compareMetrics(metrics, simulatedMetrics),
      },
    };

  } catch (error) {
    console.error('❌ Optimizer error:', error.message);
    return {
      success: false,
      error: error.message,
      current: null,
      recommendations: [],
    };
  }
}

/**
 * Get portfolio from Alpaca (with database fallback for stock scores)
 */
async function getPortfolioFromAlpaca(userId) {
  try {
    const apiKey = process.env.ALPACA_API_KEY;
    const secretKey = process.env.ALPACA_SECRET_KEY;
    const isPaper = process.env.ALPACA_PAPER_TRADING !== 'false';

    if (!apiKey || !secretKey) {
      console.log('⚠️ Alpaca credentials not configured, using database portfolio');
      return await getPortfolioWithMetrics(userId);
    }

    const alpaca = new AlpacaService(apiKey, secretKey, isPaper);

    // Get positions from Alpaca
    const positions = await alpaca.getPositions();

    if (!positions || positions.length === 0) {
      console.log('📍 No positions in Alpaca account, falling back to database');
      return await getPortfolioWithMetrics(userId);
    }

    console.log(`✅ Fetched ${positions.length} positions from Alpaca`);

    // Convert positions to holdings and enrich with stock scores
    const holdings = [];

    for (const position of positions) {
      // Position is already formatted by AlpacaService
      const holding = {
        symbol: position.symbol,
        quantity: position.quantity,
        current_price: null, // Will be fetched from DB
        market_value: position.marketValue,
        average_cost: position.costBasis ? position.costBasis / position.quantity : null,
      };

      // Get stock scores from database
      try {
        const scoreResult = await query(
          `SELECT composite_score, momentum_score, quality_score, stability_score,
                  growth_score, value_score, sentiment_score, positioning_score
           FROM stock_scores WHERE symbol = $1 LIMIT 1`,
          [holding.symbol]
        );

        if (scoreResult.rows && scoreResult.rows.length > 0) {
          const scores = scoreResult.rows[0];
          holding.composite_score = scores.composite_score ? parseFloat(scores.composite_score) : null;
          holding.momentum_score = scores.momentum_score ? parseFloat(scores.momentum_score) : null;
          holding.quality_score = scores.quality_score ? parseFloat(scores.quality_score) : null;
          holding.stability_score = scores.stability_score ? parseFloat(scores.stability_score) : null;
          holding.growth_score = scores.growth_score ? parseFloat(scores.growth_score) : null;
          holding.value_score = scores.value_score ? parseFloat(scores.value_score) : null;
          holding.sentiment_score = scores.sentiment_score ? parseFloat(scores.sentiment_score) : null;
          holding.positioning_score = scores.positioning_score ? parseFloat(scores.positioning_score) : null;
        } else {
          // Use null instead of fake defaults when data is unavailable
          holding.composite_score = null;
          holding.momentum_score = null;
          holding.quality_score = null;
          holding.stability_score = null;
          holding.growth_score = null;
          holding.value_score = null;
          holding.sentiment_score = null;
          holding.positioning_score = null;
        }
      } catch (scoreError) {
        console.warn(`⚠️ Could not get scores for ${holding.symbol}:`, scoreError.message);
        // Use null instead of fake defaults
        holding.composite_score = null;
        holding.momentum_score = null;
        holding.quality_score = null;
        holding.stability_score = null;
        holding.growth_score = null;
        holding.value_score = null;
        holding.sentiment_score = null;
        holding.positioning_score = null;
      }

      holdings.push(holding);
    }

    const totalValue = holdings.reduce((sum, h) => sum + h.market_value, 0);

    // Calculate weights
    const holdingsWithWeights = holdings.map(h => ({
      ...h,
      weight: totalValue > 0 ? h.market_value / totalValue : 0,
    }));

    return {
      holdings: holdingsWithWeights,
      totalValue: parseFloat(totalValue),
      count: holdings.length,
      source: 'alpaca',
    };

  } catch (error) {
    console.error('❌ Alpaca portfolio fetch failed:', error.message);
    console.log('📍 Falling back to database portfolio');
    return await getPortfolioWithMetrics(userId);
  }
}

/**
 * Get portfolio with real metrics from database
 */
async function getPortfolioWithMetrics(userId) {
  const q = `
    SELECT
      ph.symbol,
      ph.quantity,
      ph.average_cost,
      ph.current_price,
      ph.market_value,
      ss.composite_score,
      ss.momentum_score,
      ss.value_score,
      ss.quality_score,
      ss.growth_score,
      ss.stability_score,
      ss.sentiment_score,
      ss.positioning_score,
      ss.volume_avg_30d,
      cp.sector
    FROM portfolio_holdings ph
    LEFT JOIN stock_scores ss ON ph.symbol = ss.symbol
    LEFT JOIN company_profile cp ON cp.ticker = ph.symbol
    WHERE ph.user_id = $1 AND ph.quantity > 0
    ORDER BY ph.market_value DESC
  `;

  try {
    const result = await query(q, [userId]);
    const holdings = result.rows || [];

    if (holdings.length === 0) return null;

    // REAL DATA ONLY - Filter out holdings with missing critical data
    const validHoldings = holdings.filter(h =>
      h.market_value !== null && h.market_value !== undefined &&
      h.current_price !== null && h.current_price !== undefined &&
      h.quantity !== null && h.quantity !== undefined
    );

    const totalValue = validHoldings.reduce((sum, h) =>
      sum + parseFloat(h.market_value), 0);

    const holdingsWithWeights = validHoldings.map(h => ({
      ...h,
      market_value: parseFloat(h.market_value),
      current_price: parseFloat(h.current_price),
      quantity: parseInt(h.quantity),
      // SCORES: Use NULL if missing, NEVER default to 50 (fake neutral)
      composite_score: h.composite_score !== null && h.composite_score !== undefined ? parseFloat(h.composite_score) : null,
      momentum_score: h.momentum_score !== null && h.momentum_score !== undefined ? parseFloat(h.momentum_score) : null,
      quality_score: h.quality_score !== null && h.quality_score !== undefined ? parseFloat(h.quality_score) : null,
      stability_score: h.stability_score !== null && h.stability_score !== undefined ? parseFloat(h.stability_score) : null,
      weight: totalValue > 0 ? parseFloat(h.market_value) / totalValue : null,
    }));

    return {
      holdings: holdingsWithWeights,
      totalValue: totalValue > 0 ? parseFloat(totalValue) : null,
      count: validHoldings.length,
    };

  } catch (error) {
    console.error('Portfolio query error:', error);
    return null;
  }
}

/**
 * Calculate REAL portfolio metrics - DATA INTEGRITY: Return NULL for missing data
 *
 * IMPORTANT: This function uses ESTIMATED values (beta, alpha, volatility, return)
 * These are PROXY CALCULATIONS based on scores, NOT real market data.
 *
 * DEPRECATED APPROACH:
 * - Estimated Beta from quality/stability scores
 * - Estimated Alpha from momentum score
 * - Estimated Volatility from stability score
 * - Estimated Expected Return from composite/momentum scores
 *
 * CORRECT APPROACH (future):
 * - Fetch real Beta from price correlation with market (SPY)
 * - Fetch real Alpha from historical excess returns vs benchmark
 * - Calculate real Volatility from historical price returns
 * - Use real expected returns from analyst forecasts or historical data
 *
 * CURRENT STATUS: Returns NULL when insufficient real data (no hardcoded defaults)
 */
function calculatePortfolioMetrics(portfolio) {
  if (!portfolio || portfolio.holdings.length === 0) {
    // DATA INTEGRITY: Return NULL for all metrics when no holdings (not fake defaults)
    return {
      beta: null,                 // No holdings = unknown beta
      alpha: null,                // No holdings = unknown alpha
      sharpeRatio: null,          // No holdings = unknown Sharpe
      sortinoRatio: null,         // No holdings = unknown Sortino
      volatility: null,           // No holdings = unknown volatility
      expectedReturn: null,       // No holdings = unknown return
      concentration: null,        // No holdings = unknown concentration
      diversification: null,      // No holdings = unknown diversification
      averageComposite: null,     // No holdings = no average
      averageQuality: null,       // No holdings = no average
      averageStability: null,     // No holdings = no average
      holdingCount: 0,
    };
  }

  const { holdings, totalValue } = portfolio;
  // NOTE: riskFreeRate is hardcoded - should come from real Treasury data
  const riskFreeRate = 0.02;

  // Only use holdings with real score data - NO fake defaults
  const holdingsWithScores = holdings.filter(h =>
    h.quality_score !== null && h.quality_score !== undefined &&
    h.stability_score !== null && h.stability_score !== undefined &&
    h.momentum_score !== null && h.momentum_score !== undefined &&
    h.composite_score !== null && h.composite_score !== undefined &&
    h.weight !== null && h.weight !== undefined
  );

  // Calculate averages from REAL DATA ONLY (filter out NULL values)
  const realComposites = holdings.filter(h => h.composite_score !== null && h.composite_score !== undefined).map(h => parseFloat(h.composite_score));
  const realQualities = holdings.filter(h => h.quality_score !== null && h.quality_score !== undefined).map(h => parseFloat(h.quality_score));
  const realStabilities = holdings.filter(h => h.stability_score !== null && h.stability_score !== undefined).map(h => parseFloat(h.stability_score));

  const avgComposite = realComposites.length > 0 ? realComposites.reduce((a, b) => a + b, 0) / realComposites.length : null;
  const avgQuality = realQualities.length > 0 ? realQualities.reduce((a, b) => a + b, 0) / realQualities.length : null;
  const avgStability = realStabilities.length > 0 ? realStabilities.reduce((a, b) => a + b, 0) / realStabilities.length : null;

  // ESTIMATED metrics - these are PROXY CALCULATIONS, not real market data
  // TODO: Replace with real data from market sources
  const beta = holdingsWithScores.length > 0 ? holdingsWithScores.reduce((sum, h) => {
    const quality = Math.max(0, Math.min(100, parseFloat(h.quality_score)));
    const stability = Math.max(0, Math.min(100, parseFloat(h.stability_score)));
    // ESTIMATED: Higher quality/stability = lower beta (less systematic risk)
    const estimatedBeta = 0.8 + (0.4 * (quality / 100)) - (0.2 * ((stability - 50) / 100));
    return sum + (h.weight * Math.max(0.5, Math.min(1.5, estimatedBeta)));
  }, 0) : null;

  // ESTIMATED: Alpha from momentum (assumes momentum = excess return)
  const alpha = holdingsWithScores.length > 0 ? holdingsWithScores.reduce((sum, h) => {
    const momentum = Math.max(0, Math.min(100, parseFloat(h.momentum_score)));
    // ESTIMATED: Momentum 50 = 0% alpha, 100 = 8% alpha
    const estimatedAlpha = ((momentum - 50) / 100) * 0.08;
    return sum + (h.weight * estimatedAlpha);
  }, 0) : null;

  // ESTIMATED: Volatility from stability (assumes stability = lower volatility)
  const volatility = holdingsWithScores.length > 0 ? holdingsWithScores.reduce((sum, h) => {
    const stability = Math.max(0, Math.min(100, parseFloat(h.stability_score)));
    // ESTIMATED: Stability 100 = 0% vol, Stability 0 = 20% vol
    const vol = 0.20 * (1 - (stability / 100));
    return sum + (h.weight * vol);
  }, 0) : null;

  // ESTIMATED: Expected return from composite and momentum
  const expectedReturn = holdingsWithScores.length > 0 ? holdingsWithScores.reduce((sum, h) => {
    const composite = Math.max(0, Math.min(100, parseFloat(h.composite_score)));
    const momentum = Math.max(0, Math.min(100, parseFloat(h.momentum_score)));
    // ESTIMATED: Composite 100 = 8% return, Momentum adds ±4% adjustment
    const ret = 0.08 * (composite / 100) + 0.04 * ((momentum - 50) / 100);
    return sum + (h.weight * ret);
  }, 0) : null;

  // Sharpe Ratio - only if real data available
  const sharpeRatio = volatility !== null && volatility > 0 && expectedReturn !== null ? (expectedReturn - riskFreeRate) / volatility : null;

  // Sortino Ratio - return NULL (requires separate downside deviation calculation, not 1.2× Sharpe)
  const sortinoRatio = null; // Cannot estimate - requires downside deviation calculation

  // Concentration: Top 3 weight
  const top3Weight = holdings.slice(0, 3).reduce((sum, h) => sum + h.weight, 0);
  const concentration = top3Weight > 0 ? top3Weight : null;

  return {
    beta: beta !== null ? parseFloat(Math.max(0.5, Math.min(2.0, beta)).toFixed(2)) : null,
    alpha: alpha !== null ? parseFloat(alpha.toFixed(4)) : null,
    sharpeRatio: sharpeRatio !== null ? parseFloat(sharpeRatio.toFixed(2)) : null,
    sortinoRatio: sortinoRatio, // NULL - cannot estimate properly
    volatility: volatility !== null ? parseFloat(volatility.toFixed(4)) : null,
    expectedReturn: expectedReturn !== null ? parseFloat(expectedReturn.toFixed(4)) : null,
    concentration: concentration !== null ? parseFloat(concentration.toFixed(3)) : null,
    diversification: holdings.length > 1 ? parseFloat((1 / holdings.length).toFixed(3)) : null,
    averageComposite: avgComposite !== null ? parseFloat(avgComposite.toFixed(1)) : null,
    averageQuality: avgQuality !== null ? parseFloat(avgQuality.toFixed(1)) : null,
    averageStability: avgStability !== null ? parseFloat(avgStability.toFixed(1)) : null,
    holdingCount: holdings.length,
  };
}

/**
 * Identify weak metrics
 */
function identifyWeakMetrics(metrics) {
  const weaknesses = [];

  if (metrics.beta > 1.2) {
    weaknesses.push({
      metric: 'beta',
      value: metrics.beta,
      problem: `Portfolio too risky (beta ${metrics.beta} > 1.2)`,
      target: 1.0,
      priority: 'high',
    });
  }

  if (metrics.sharpeRatio < 1.0 && metrics.sharpeRatio > 0) {
    weaknesses.push({
      metric: 'sharpeRatio',
      value: metrics.sharpeRatio,
      problem: `Weak risk-adjusted returns (Sharpe ${metrics.sharpeRatio} < 1.0)`,
      target: 1.5,
      priority: 'high',
    });
  }

  if (metrics.concentration > 0.40) {
    weaknesses.push({
      metric: 'concentration',
      value: metrics.concentration,
      problem: `Concentrated portfolio (top 3 = ${(metrics.concentration * 100).toFixed(0)}% > 40%)`,
      target: 0.30,
      priority: 'medium',
    });
  }

  if (metrics.holdingCount < 8) {
    weaknesses.push({
      metric: 'diversification',
      value: metrics.holdingCount,
      problem: `Underdiversified (${metrics.holdingCount} holdings < 8)`,
      target: 15,
      priority: 'medium',
    });
  }

  if (metrics.averageComposite < 65) {
    weaknesses.push({
      metric: 'quality',
      value: metrics.averageComposite,
      problem: `Low portfolio quality (avg score ${metrics.averageComposite.toFixed(1)} < 65)`,
      target: 75,
      priority: 'high',
    });
  }

  return weaknesses;
}

/**
 * Get candidate stocks
 */
async function getCandidateStocks(minScore, excludeSymbols, limit) {
  const q = `
    SELECT
      symbol,
      composite_score,
      momentum_score,
      quality_score,
      stability_score,
      growth_score,
      value_score,
      sentiment_score,
      positioning_score,
      current_price,
      volume_avg_30d,
      (SELECT sector FROM company_profile cp WHERE cp.ticker = ss.symbol LIMIT 1) as sector
    FROM stock_scores ss
    WHERE composite_score >= $1
      AND symbol != ALL($2)
      AND current_price > 0
      AND volume_avg_30d > 500000
    ORDER BY composite_score DESC
    LIMIT $3
  `;

  try {
    const result = await query(q, [minScore, excludeSymbols, limit]);
    const rows = result.rows || [];

    // Ensure all numeric fields are parsed correctly - NO fake data
    return rows.map(row => ({
      ...row,
      composite_score: row.composite_score !== null && row.composite_score !== undefined ? parseFloat(row.composite_score) : null,
      momentum_score: row.momentum_score !== null && row.momentum_score !== undefined ? parseFloat(row.momentum_score) : null,
      quality_score: row.quality_score !== null && row.quality_score !== undefined ? parseFloat(row.quality_score) : null,
      stability_score: row.stability_score !== null && row.stability_score !== undefined ? parseFloat(row.stability_score) : null,
      growth_score: row.growth_score !== null && row.growth_score !== undefined ? parseFloat(row.growth_score) : null,
      value_score: row.value_score !== null && row.value_score !== undefined ? parseFloat(row.value_score) : null,
      sentiment_score: row.sentiment_score !== null && row.sentiment_score !== undefined ? parseFloat(row.sentiment_score) : null,
      positioning_score: row.positioning_score !== null && row.positioning_score !== undefined ? parseFloat(row.positioning_score) : null,
      current_price: row.current_price !== null && row.current_price !== undefined ? parseFloat(row.current_price) : null,
      volume_avg_30d: row.volume_avg_30d !== null && row.volume_avg_30d !== undefined ? parseFloat(row.volume_avg_30d) : null,
    }));
  } catch (error) {
    console.error('Candidate stocks error:', error);
    return [];
  }
}

/**
 * Generate recommendations
 */
function generateRecommendations(portfolio, metrics, weaknesses, candidates, maxRecs) {
  const recs = [];
  const added = new Set();

  // Priority 1: Fix concentration by selling poor performers
  if (metrics.concentration > 0.35) {
    const weakHoldings = portfolio.holdings
      .filter(h => h.composite_score < 60)
      .sort((a, b) => a.composite_score - b.composite_score)
      .slice(0, 2);

    weakHoldings.forEach(hold => {
      recs.push({
        action: 'SELL',
        symbol: hold.symbol,
        reason: `Low quality (${hold.composite_score.toFixed(0)}) - reduce concentration`,
        quantity: Math.ceil(hold.quantity * 0.5),
        priority: 'high',
      });
      added.add(hold.symbol);
    });
  }

  // Priority 2: Fix weak metrics with targeted buys
  if (weaknesses.some(w => w.metric === 'beta' && w.value > 1.2)) {
    const defensive = candidates
      .filter(c => c.stability_score > 70 && c.quality_score > 70)
      .slice(0, 2);

    defensive.forEach(stock => {
      if (!added.has(stock.symbol) && recs.length < maxRecs) {
        recs.push({
          action: 'BUY',
          symbol: stock.symbol,
          reason: `Defensive (stability ${stock.stability_score.toFixed(0)}) to reduce beta`,
          targetWeight: 0.06,
          priority: 'high',
        });
        added.add(stock.symbol);
      }
    });
  }

  if (weaknesses.some(w => w.metric === 'quality')) {
    const quality = candidates
      .filter(c => c.quality_score > 75)
      .slice(0, 2);

    quality.forEach(stock => {
      if (!added.has(stock.symbol) && recs.length < maxRecs) {
        recs.push({
          action: 'BUY',
          symbol: stock.symbol,
          reason: `High quality (${stock.quality_score.toFixed(0)}) to improve portfolio`,
          targetWeight: 0.08,
          priority: 'high',
        });
        added.add(stock.symbol);
      }
    });
  }

  // Priority 2.5: Improve Sharpe ratio by adding momentum/growth stocks
  if (weaknesses.some(w => w.metric === 'sharpeRatio' && w.value < 1.0)) {
    const growth = candidates
      .filter(c => c.momentum_score > 70 && !added.has(c.symbol))
      .slice(0, Math.min(2, maxRecs - recs.length));

    growth.forEach(stock => {
      if (recs.length < maxRecs) {
        recs.push({
          action: 'BUY',
          symbol: stock.symbol,
          reason: `Growth momentum (${stock.momentum_score.toFixed(0)}) to improve Sharpe ratio`,
          targetWeight: 0.06,
          priority: 'high',
        });
        added.add(stock.symbol);
      }
    });
  }

  // Priority 2.7: Improve alpha by adding growth stocks
  if (weaknesses.some(w => w.metric === 'alpha' && w.value < 0.03) && recs.length < maxRecs) {
    const alphaCandidates = candidates
      .filter(c => c.growth_score > 70 && !added.has(c.symbol))
      .slice(0, Math.min(1, maxRecs - recs.length));

    alphaCandidates.forEach(stock => {
      if (recs.length < maxRecs) {
        recs.push({
          action: 'BUY',
          symbol: stock.symbol,
          reason: `High growth (${stock.growth_score.toFixed(0)}) to improve alpha`,
          targetWeight: 0.05,
          priority: 'medium',
        });
        added.add(stock.symbol);
      }
    });
  }

  // Priority 3.5: Sector diversification (ensure across multiple sectors) - use real data only
  const currentSectors = new Set(
    portfolio.holdings
      .filter(h => h.sector !== null && h.sector !== undefined)
      .map(h => h.sector)
  );
  const targetSectors = Math.max(4, Math.ceil(portfolio.holdings.length / 2));

  if (currentSectors.size < targetSectors && recs.length < maxRecs) {
    const availableSectors = new Map();

    // Group candidates by sector - only those with real sector data
    candidates.forEach(c => {
      if (c.sector !== null && c.sector !== undefined) {
        const sector = c.sector;
        if (!availableSectors.has(sector)) {
          availableSectors.set(sector, []);
        }
        if (!added.has(c.symbol)) {
          availableSectors.get(sector).push(c);
        }
      }
    });

    // Recommend from sectors we don't have
    for (const [sector, stocks] of availableSectors) {
      if (!currentSectors.has(sector) && recs.length < maxRecs && stocks.length > 0) {
        const best = stocks[0]; // Get highest-scored stock in sector
        recs.push({
          action: 'BUY',
          symbol: best.symbol,
          reason: `Sector diversification (${sector})`,
          targetWeight: 0.05,
          priority: 'medium',
        });
        added.add(best.symbol);
        currentSectors.add(sector);
      }
    }
  }

  // Priority 4: General diversification for remaining slots
  if (metrics.concentration > 0.30 && recs.length < maxRecs) {
    const diversify = candidates
      .filter(c => !added.has(c.symbol))
      .slice(0, Math.min(3, maxRecs - recs.length));

    diversify.forEach(stock => {
      recs.push({
        action: 'BUY',
        symbol: stock.symbol,
        reason: 'General diversification',
        targetWeight: 0.04,
        priority: 'low',
      });
      added.add(stock.symbol);
    });
  }

  return recs.slice(0, maxRecs);
}

/**
 * Simulate portfolio after trades
 */
function simulatePortfolio(portfolio, recommendations) {
  let sim = JSON.parse(JSON.stringify(portfolio));

  recommendations.forEach(rec => {
    if (rec.action === 'SELL') {
      // Reduce weight of selling stock (don't remove completely)
      const holding = sim.holdings.find(h => h.symbol === rec.symbol);
      if (holding) {
        // Reduce weight by 50% (moderate sell)
        holding.weight = holding.weight * 0.5;
      }
    } else if (rec.action === 'BUY') {
      const exists = sim.holdings.find(h => h.symbol === rec.symbol);
      if (!exists) {
        // Add new holding - only if target weight is specified (no fake defaults)
        if (rec.targetWeight !== null && rec.targetWeight !== undefined) {
          sim.holdings.push({
            symbol: rec.symbol,
            weight: rec.targetWeight,
            composite_score: rec.composite_score ?? null,
            momentum_score: rec.momentum_score ?? null,
            quality_score: rec.quality_score ?? null,
            stability_score: rec.stability_score ?? null,
            growth_score: rec.growth_score ?? null,
            value_score: rec.value_score ?? null,
            sentiment_score: rec.sentiment_score ?? null,
            positioning_score: rec.positioning_score ?? null,
          });
        }
      } else {
        // Increase weight of existing holding by 20%
        exists.weight = exists.weight * 1.2;
      }
    }
  });

  // Renormalize weights to sum to 1.0 - only use real weight values
  const validHoldings = sim.holdings.filter(h => h.weight !== null && h.weight !== undefined);
  const totalWeight = validHoldings.reduce((sum, h) => sum + parseFloat(h.weight), 0);
  if (totalWeight > 0) {
    sim.holdings = sim.holdings.map(h => ({
      ...h,
      weight: h.weight / totalWeight,
    }));
  }

  return sim;
}

/**
 * Compare metrics before/after
 */
function compareMetrics(before, after) {
  return {
    beta: {
      before: before.beta,
      after: after.beta,
      improved: after.beta < before.beta,
      change: (after.beta - before.beta).toFixed(2),
    },
    sharpeRatio: {
      before: before.sharpeRatio,
      after: after.sharpeRatio,
      improved: after.sharpeRatio > before.sharpeRatio,
      change: (after.sharpeRatio - before.sharpeRatio).toFixed(2),
    },
    concentration: {
      before: before.concentration,
      after: after.concentration,
      improved: after.concentration < before.concentration,
      change: (after.concentration - before.concentration).toFixed(3),
    },
    quality: {
      before: before.averageComposite,
      after: after.averageComposite,
      improved: after.averageComposite > before.averageComposite,
      change: (after.averageComposite - before.averageComposite).toFixed(1),
    },
  };
}

module.exports = {
  optimizePortfolio,
  getPortfolioFromAlpaca,
  getPortfolioWithMetrics,
  calculatePortfolioMetrics,
  identifyWeakMetrics,
  getCandidateStocks,
};
