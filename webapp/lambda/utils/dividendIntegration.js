/**
 * Dividend Integration Module
 *
 * Integrates dividend yields into expected returns calculations:
 * - Current dividend yield (income component)
 * - Dividend growth expectations (based on stability and payout ratio)
 * - Dividend sustainability assessment
 * - Total return decomposition (price appreciation + dividend income)
 *
 * This ensures recommendations properly value dividend-paying stocks
 * and consider the income component of total returns
 */

/**
 * Calculate dividend contribution to total return
 *
 * Total Return = Price Appreciation Return + Dividend Yield Return
 *
 * @param {Object} stock - Stock data with dividend information
 * @param {number} stock.current_price - Current stock price
 * @param {number} stock.dividend_yield - Current dividend yield (as percentage, e.g., 3.5)
 * @param {number} stock.payout_ratio - Payout ratio (0-1, e.g., 0.45)
 * @param {number} stock.stability_score - Stability score (0-100)
 * @param {number} stock.growth_score - Growth score (0-100)
 * @returns {Object} Dividend contribution metrics
 */
function calculateDividendContribution(stock) {
  // Only use REAL data - return null if key data missing (NO FAKE DEFAULTS)
  if (stock.stability_score === null || stock.stability_score === undefined) {
    console.warn(`⚠️ Missing stability_score for ${stock.symbol} - cannot calculate dividend contribution`);
    return null;
  }
  if (stock.growth_score === null || stock.growth_score === undefined) {
    console.warn(`⚠️ Missing growth_score for ${stock.symbol} - cannot calculate dividend contribution`);
    return null;
  }

  const dividendYield = (stock.dividend_yield || 0) / 100; // Convert percentage to decimal, 0 if missing
  const payoutRatio = Math.max(0, Math.min(1, stock.payout_ratio || 0)); // Clamp 0-1, 0 if missing
  const stability = stock.stability_score / 100; // Normalize 0-1 (REAL DATA ONLY)
  const growth = stock.growth_score / 100; // Normalize 0-1 (REAL DATA ONLY)

  // Dividend sustainability score: High payout + stable business = more sustainable
  // Low payout + stable business = room to grow dividend
  // High payout + unstable business = risk of dividend cut
  const sustainability = (
    stability * (payoutRatio < 0.6 ? 1.0 : 1.0 - ((payoutRatio - 0.6) * 0.5)) // Penalize high payout
  );

  // Dividend growth expectation based on:
  // - Stability (stable companies maintain or grow dividends)
  // - Growth (growing companies increase dividend)
  // - Payout ratio (low payout = room to grow)
  const growthExpectation = (
    (stability * 0.4 +     // Stable = sustainable growth
     growth * 0.3 +        // Growth = higher dividend growth
     (1 - payoutRatio) * 0.3) // Low payout = room for increases
  );

  // Expected dividend growth rate (3-10% annual based on sustainability)
  const expectedDividendGrowth = 0.03 + (growthExpectation * 0.07); // 3% to 10%

  return {
    currentDividendYield: parseFloat(dividendYield.toFixed(4)),
    expectedDividendGrowth: parseFloat(expectedDividendGrowth.toFixed(4)),
    payoutRatio: parseFloat(payoutRatio.toFixed(2)),
    sustainability: parseFloat(sustainability.toFixed(2)),
    growthExpectation: parseFloat(growthExpectation.toFixed(2)),
    // Income component of total return (just the current dividend)
    incomeReturn: parseFloat(dividendYield.toFixed(4)),
    // Conservative estimate: only 70% of current dividend (assuming some decline risk)
    conservativeIncomeReturn: parseFloat(
      (((stock.dividend_yield || 0) / 100) * 0.7).toFixed(4) // 70% of current - NO fake 2% default
    )
  };
}

/**
 * Adjust expected return to include dividend component
 *
 * Traditional expected return = Price appreciation only
 * Total return = Price appreciation + Dividend yield
 *
 * @param {number} baseReturn - Base expected return from price appreciation (0-0.25)
 * @param {Object} dividendMetrics - Dividend contribution metrics
 * @returns {Object} Adjusted return metrics
 */
function adjustReturnForDividends(baseReturn, dividendMetrics) {
  // Dividend yield is relatively stable compared to price appreciation
  // So it's a reliable component of total return
  const totalReturn = baseReturn + dividendMetrics.incomeReturn;

  // Growth component: Expected dividend growth compounds return
  // (More conservative: only add 25% of expected growth to realized return)
  const growthComponent = dividendMetrics.expectedDividendGrowth * 0.25;

  // Total return including dividend growth (slightly more optimistic)
  const totalReturnWithGrowth = totalReturn + growthComponent;

  return {
    baseAppreciationReturn: parseFloat(baseReturn.toFixed(4)),
    dividendIncomeReturn: parseFloat(dividendMetrics.incomeReturn.toFixed(4)),
    dividendGrowthComponent: parseFloat(growthComponent.toFixed(4)),
    totalReturn: parseFloat(totalReturn.toFixed(4)),
    totalReturnWithGrowth: parseFloat(totalReturnWithGrowth.toFixed(4)),
    // Capped at 0-25% range for portfolio optimization (avoid unrealistic expectations)
    cappedTotalReturn: parseFloat(Math.max(0.01, Math.min(0.25, totalReturn)).toFixed(4)),
    cappedTotalReturnWithGrowth: parseFloat(Math.max(0.01, Math.min(0.25, totalReturnWithGrowth)).toFixed(4))
  };
}

/**
 * Score position based on dividend characteristics
 *
 * Bonuses for:
 * - High dividend yield (income generation)
 * - Sustainable dividends (low payout ratio + stable business)
 * - Growing dividends (stability + growth + low payout)
 *
 * @param {Object} stock - Stock with dividend data
 * @param {Object} dividendMetrics - Dividend contribution metrics
 * @returns {Object} Scoring adjustments
 */
function scoreDividendProfile(stock, dividendMetrics) {
  let dividendBonus = 0;
  let reasoning = [];

  const yieldPct = (stock.dividend_yield || 0);

  // Bonus 1: High dividend yield (income generation bonus)
  if (yieldPct >= 4) {
    dividendBonus += 5; // +5 points for 4%+ yield
    reasoning.push(`High yield (${yieldPct.toFixed(2)}%): Strong income component`);
  } else if (yieldPct >= 2) {
    dividendBonus += 2;
    reasoning.push(`Moderate yield (${yieldPct.toFixed(2)}%): Reasonable income`);
  } else if (yieldPct > 0.5) {
    dividendBonus += 1;
  }

  // Bonus 2: Sustainable dividends (low payout ratio + stable business)
  if (dividendMetrics.payoutRatio < 0.60 && dividendMetrics.sustainability > 0.75) {
    dividendBonus += 3;
    reasoning.push(`Sustainable dividend: Low payout (${(dividendMetrics.payoutRatio * 100).toFixed(1)}%) + stable business`);
  }

  // Bonus 3: Growing dividends (expected growth)
  if (dividendMetrics.expectedDividendGrowth > 0.05) {
    dividendBonus += 2;
    reasoning.push(`Growing dividend: Expected ${(dividendMetrics.expectedDividendGrowth * 100).toFixed(1)}% annual growth`);
  }

  // Penalty: Unsustainable dividend (high payout + unstable)
  if (dividendMetrics.payoutRatio > 0.80 && dividendMetrics.sustainability < 0.50) {
    dividendBonus -= 3;
    reasoning.push(`⚠️ Dividend risk: High payout (${(dividendMetrics.payoutRatio * 100).toFixed(1)}%) + unstable business`);
  }

  return {
    bonus: dividendBonus,
    reasoning,
    hasSignificantYield: yieldPct >= 2,
    isDividendGrower: dividendMetrics.expectedDividendGrowth > 0.05,
    isDividendSustainable: dividendMetrics.sustainability > 0.75
  };
}

/**
 * Portfolio dividend analysis
 *
 * Shows portfolio-level dividend characteristics and income potential
 *
 * @param {Array} stocks - Array of stock holdings
 * @param {Object} weights - Position weights (symbol → weight)
 * @returns {Object} Portfolio dividend metrics
 */
function analyzePortfolioDividends(stocks, weights = {}) {
  let totalDividendYield = 0;
  let totalIncomeReturn = 0;
  let dividendStocks = 0;
  const highYieldPositions = [];
  const growingDividendStocks = [];

  stocks.forEach(stock => {
    const weight = weights[stock.symbol] || 0.05; // Default 5% if weight unknown
    const yieldPct = (stock.dividend_yield || 0) / 100;

    // Portfolio-weighted dividend yield
    totalDividendYield += yieldPct * weight;
    totalIncomeReturn += yieldPct;

    if (yieldPct > 0) {
      dividendStocks++;

      if (yieldPct >= 3) {
        highYieldPositions.push({
          symbol: stock.symbol,
          yield: parseFloat(yieldPct.toFixed(4)),
          weight: parseFloat(weight.toFixed(2))
        });
      }
    }

    // Identify dividend growers
    const metrics = calculateDividendContribution(stock);
    if (metrics.expectedDividendGrowth > 0.05) {
      growingDividendStocks.push({
        symbol: stock.symbol,
        expectedGrowth: parseFloat(metrics.expectedDividendGrowth.toFixed(4))
      });
    }
  });

  return {
    dividendPayingStocks: dividendStocks,
    portfolioWeightedDividendYield: parseFloat((totalDividendYield * 100).toFixed(2)),
    averageDividendYield: parseFloat(((totalIncomeReturn / Math.max(1, dividendStocks)) * 100).toFixed(2)),
    annualIncomeReturn: parseFloat((totalDividendYield * 100).toFixed(2)),
    highYieldPositions,
    growingDividendStocks,
    incomeGenerationRating: dividendStocks === 0 ? 'None' :
                           totalDividendYield >= 0.03 ? 'Strong' :
                           totalDividendYield >= 0.015 ? 'Moderate' : 'Low'
  };
}

/**
 * Recommendation impact considering dividend changes
 *
 * If recommending to increase/decrease dividend payer, show dividend impact
 *
 * @param {Object} stock - Stock being recommended
 * @param {string} action - 'INCREASE' or 'DECREASE'
 * @param {number} currentWeight - Current position weight
 * @param {number} recommendedWeight - Recommended position weight
 * @returns {Object} Dividend impact analysis
 */
function analyzeDividendImpact(stock, action, currentWeight = 0, recommendedWeight = 0) {
  const dividendMetrics = calculateDividendContribution(stock);
  const yieldPct = (stock.dividend_yield || 0) / 100;

  // Impact on portfolio dividend income
  const weightChange = recommendedWeight - currentWeight;
  const incomeImpact = yieldPct * weightChange * 100; // Basis points of portfolio yield change

  return {
    action,
    symbol: stock.symbol,
    currentDividendYield: parseFloat((yieldPct * 100).toFixed(2)),
    weightChange: parseFloat(weightChange.toFixed(4)),
    incomeImpactBps: parseFloat(incomeImpact.toFixed(1)), // Basis points
    annualIncomeChange: parseFloat((incomeImpact / 100).toFixed(4)), // As percentage
    reasoning: incomeImpact > 0 ? `Increases portfolio income by ${incomeImpact.toFixed(0)}bps` :
               incomeImpact < 0 ? `Reduces portfolio income by ${Math.abs(incomeImpact).toFixed(0)}bps` :
               'No income impact'
  };
}

module.exports = {
  calculateDividendContribution,
  adjustReturnForDividends,
  scoreDividendProfile,
  analyzePortfolioDividends,
  analyzeDividendImpact
};
