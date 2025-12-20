/**
 * Tax Optimization Module
 *
 * Integrates comprehensive tax considerations into portfolio recommendations:
 * - Tax-loss harvesting identification (short & long-term)
 * - After-tax return calculations
 * - Tax-lot selection strategies
 * - Holding period optimization
 * - Wash sale detection
 * - Tax-location optimization
 * - Unrealized gain/loss assessment
 *
 * This ensures all recommendations consider tax impact on net returns
 */

/**
 * Calculate tax metrics for a holding
 *
 * @param {Object} holding - Portfolio holding with cost basis
 * @param {number} holding.symbol - Stock symbol
 * @param {number} holding.quantity - Shares owned
 * @param {number} holding.current_price - Current price per share
 * @param {number} holding.average_cost - Average cost per share
 * @param {Date} holding.purchase_date - Date of purchase (or average if multiple lots)
 * @param {number} taxRate - Capital gains tax rate (0.20 for 20% LTCG)
 * @returns {Object} Tax metrics including gain/loss, holding status, tax liability
 */
function calculateTaxMetrics(holding, taxRate = 0.20) {
  const currentValue = holding.quantity * holding.current_price;
  const costBasis = holding.quantity * holding.average_cost;
  const unrealizedGain = currentValue - costBasis;
  const unrealizedGainPercent = costBasis > 0 ? (unrealizedGain / costBasis) * 100 : 0;

  // Determine if long-term or short-term
  const purchaseDate = new Date(holding.purchase_date);
  const today = new Date();
  const dayHeld = Math.floor((today - purchaseDate) / (1000 * 60 * 60 * 24));
  const isLongTerm = dayHeld >= 365;

  // Calculate tax liability if position closed today
  let taxLiability = 0;
  let effectiveTaxRate = 0;

  if (unrealizedGain > 0) {
    // Positive gain: pay tax
    if (isLongTerm) {
      // Long-term capital gains (typically 0%, 15%, or 20% depending on income)
      taxLiability = unrealizedGain * taxRate;
      effectiveTaxRate = taxRate;
    } else {
      // Short-term capital gains (taxed as ordinary income, assume higher rate)
      const shortTermRate = Math.min(0.37, taxRate + 0.15); // Assume 35-37% for short-term
      taxLiability = unrealizedGain * shortTermRate;
      effectiveTaxRate = shortTermRate;
    }
  } else if (unrealizedGain < 0) {
    // Loss: can use for tax harvesting
    taxLiability = 0; // No tax owed
    effectiveTaxRate = 0;
  }

  return {
    symbol: holding.symbol,
    quantity: holding.quantity,
    averageCost: holding.average_cost,
    currentPrice: holding.current_price,
    costBasis,
    currentValue,
    unrealizedGain,
    unrealizedGainPercent: parseFloat(unrealizedGainPercent.toFixed(2)),
    dayHeld,
    isLongTerm,
    taxLiability: parseFloat(taxLiability.toFixed(2)),
    effectiveTaxRate: parseFloat((effectiveTaxRate * 100).toFixed(2)),
    afterTaxGain: parseFloat((unrealizedGain - taxLiability).toFixed(2)),
    afterTaxGainPercent: parseFloat((((unrealizedGain - taxLiability) / costBasis) * 100).toFixed(2))
  };
}

/**
 * Identify tax-loss harvesting opportunities
 *
 * Returns positions with losses that can be harvested to offset gains
 *
 * @param {Array} holdings - Array of portfolio holdings
 * @param {number} minLossAmount - Minimum loss size to consider (default $500)
 * @returns {Object} Harvesting opportunities and potential tax savings
 */
function identifyHarvestingOpportunities(holdings, minLossAmount = 500) {
  const losses = [];
  const gains = [];
  let totalLosses = 0;
  let totalGains = 0;

  // Separate losses and gains
  holdings.forEach(holding => {
    const currentValue = holding.quantity * holding.current_price;
    const costBasis = holding.quantity * holding.average_cost;
    const unrealizedGain = currentValue - costBasis;

    if (unrealizedGain < -minLossAmount) {
      // Significant loss - harvest candidate
      losses.push({
        symbol: holding.symbol,
        loss: -unrealizedGain,
        lossPercent: (unrealizedGain / costBasis) * 100,
        quantity: holding.quantity,
        currentPrice: holding.current_price,
        purchaseDate: holding.purchase_date,
        sector: holding.sector
      });
      totalLosses += -unrealizedGain;
    } else if (unrealizedGain > minLossAmount) {
      // Significant gain
      gains.push({
        symbol: holding.symbol,
        gain: unrealizedGain,
        gainPercent: (unrealizedGain / costBasis) * 100,
        quantity: holding.quantity,
        currentPrice: holding.current_price
      });
      totalGains += unrealizedGain;
    }
  });

  // Sort by loss amount (harvest biggest losses first)
  losses.sort((a, b) => b.loss - a.loss);

  // Calculate tax benefits
  const harvestingStrategy = {
    totalLosses: parseFloat(totalLosses.toFixed(2)),
    totalGains: parseFloat(totalGains.toFixed(2)),
    availableHarvestable: losses.reduce((sum, l) => sum + l.loss, 0),
    harvestingOpportunities: losses.slice(0, 5), // Top 5 losses to harvest
    gainOffsetting: {
      canOffset: Math.min(totalLosses, totalGains),
      taxSavings: parseFloat((Math.min(totalLosses, totalGains) * 0.20).toFixed(2)), // Assuming 20% LTCG rate
      carryforward: parseFloat(Math.max(0, totalLosses - totalGains).toFixed(2))
    },
    recommendations: generateHarvestingRecommendations(losses, gains)
  };

  return harvestingStrategy;
}

/**
 * Generate specific tax-loss harvesting recommendations
 *
 * @param {Array} losses - Array of loss positions
 * @param {Array} gains - Array of gain positions
 * @returns {Array} Prioritized list of recommendations
 */
function generateHarvestingRecommendations(losses, gains) {
  const recommendations = [];

  // If we have gains to offset, recommend harvesting losses
  if (gains.length > 0 && losses.length > 0) {
    recommendations.push({
      priority: 'CRITICAL',
      action: 'HARVEST_LOSSES',
      reason: `Can harvest $${losses[0].loss.toFixed(2)} in losses to offset $${gains[0].gain.toFixed(2)} in gains`,
      taxBenefit: parseFloat((Math.min(losses[0].loss, gains[0].gain) * 0.20).toFixed(2)),
      sell: losses[0].symbol,
      buyReplacement: `Similar sector stock to ${losses[0].symbol}`, // Avoid wash sale
      waitPeriod: '31 days before repurchasing same security'
    });
  }

  // Identify wash sale risks
  losses.forEach(loss => {
    recommendations.push({
      priority: 'HIGH',
      action: 'WATCH_WASH_SALE',
      symbol: loss.symbol,
      rule: 'Cannot repurchase within 30 days before/after sale',
      taxBenefit: parseFloat((loss.loss * 0.20).toFixed(2)),
      tip: 'Buy similar (not identical) security in same sector instead'
    });
  });

  return recommendations.slice(0, 5);
}

/**
 * Calculate after-tax returns for a position
 *
 * Adjusts expected returns for capital gains tax impact
 *
 * @param {Object} position - Position with expected return
 * @param {number} position.expectedReturn - Expected annual return percentage
 * @param {number} position.unrealizedGain - Current unrealized gain
 * @param {boolean} position.isLongTerm - Whether gain is long-term
 * @param {number} taxRate - Tax rate (0.20 for 20% LTCG)
 * @returns {Object} After-tax return metrics
 */
function calculateAfterTaxReturn(position, taxRate = 0.20) {
  const expectedReturn = position.expectedReturn || 0;
  const taxableGain = position.unrealizedGain || 0;

  // For new positions, apply tax to expected returns
  // For existing positions, tax only applies when sold
  let effectiveTaxRate = taxRate;

  if (position.isLongTerm === false) {
    effectiveTaxRate = Math.min(0.37, taxRate + 0.15); // Short-term higher rate
  }

  const afterTaxReturn = expectedReturn * (1 - effectiveTaxRate);
  const taxDragPercent = expectedReturn * effectiveTaxRate;

  return {
    preTermReturn: parseFloat(expectedReturn.toFixed(2)),
    effectiveTaxRate: parseFloat((effectiveTaxRate * 100).toFixed(2)),
    taxDrag: parseFloat(taxDragPercent.toFixed(2)),
    afterTaxReturn: parseFloat(afterTaxReturn.toFixed(2)),
    isShortTerm: position.isLongTerm === false,
    holdingRecommendation: position.isLongTerm
      ? 'Hold for long-term capital gains'
      : `Hold ${365 - (position.dayHeld || 0)} more days for long-term rate`
  };
}

/**
 * Score recommendations considering tax impact
 *
 * Adjusts recommendation scores based on tax efficiency
 *
 * @param {Object} recommendation - Recommendation with action and stock info
 * @param {Array} holdings - Current portfolio holdings
 * @param {number} taxRate - Capital gains tax rate
 * @returns {Object} Updated recommendation with tax adjustments
 */
function scoreWithTaxOptimization(recommendation, holdings, taxRate = 0.20) {
  const symbol = recommendation.symbol;
  const action = recommendation.action;
  const currentScore = recommendation.bestScore || 0;

  let taxAdjustment = 0;
  let taxMetrics = null;
  let taxReasoning = '';

  if (action === 'DECREASE' || action === 'SELL') {
    // Selling - consider tax impact
    const holding = holdings.find(h => h.symbol === symbol);
    if (holding) {
      taxMetrics = calculateTaxMetrics(holding, taxRate);

      // PENALTY: Selling at big gain = tax liability
      if (taxMetrics.unrealizedGain > 0) {
        const taxLiabilityPercent = (taxMetrics.taxLiability / (holding.quantity * holding.current_price)) * 100;
        taxAdjustment = -taxLiabilityPercent * 0.5; // Reduce score by tax burden
        taxReasoning = `Tax liability: $${taxMetrics.taxLiability.toFixed(2)} (${taxMetrics.effectiveTaxRate}% rate)`;
      }
      // BONUS: Selling at loss = tax benefit
      else if (taxMetrics.unrealizedGain < 0) {
        const taxBenefit = Math.abs(taxMetrics.unrealizedGain) * 0.20;
        taxAdjustment = 5; // Small bonus for tax-loss harvesting
        taxReasoning = `Tax harvesting opportunity: Save $${taxBenefit.toFixed(2)}`;
      }
    }
  } else if (action === 'INCREASE' || action === 'BUY') {
    // Buying - consider tax-efficient vehicle
    // NEW positions: no immediate tax, but future gains will be taxed
    taxReasoning = 'New position - gains will be taxed at long-term rate after 1 year hold';
  }

  return {
    ...recommendation,
    taxAdjustment: parseFloat(taxAdjustment.toFixed(1)),
    taxMetrics,
    taxReasoning,
    adjustedScore: parseFloat((currentScore + taxAdjustment).toFixed(1))
  };
}

/**
 * Identify positions approaching long-term holding period
 *
 * Recommendations should wait if about to cross 1-year threshold
 *
 * @param {Array} holdings - Portfolio holdings
 * @returns {Array} Positions near 365-day threshold
 */
function identifyLongTermThreshold(holdings) {
  const daysToLongTerm = [];

  holdings.forEach(holding => {
    const purchaseDate = new Date(holding.purchase_date);
    const today = new Date();
    const dayHeld = Math.floor((today - purchaseDate) / (1000 * 60 * 60 * 24));
    const daysRemaining = 365 - dayHeld;

    if (daysRemaining > 0 && daysRemaining < 60) {
      // Close to long-term threshold
      daysToLongTerm.push({
        symbol: holding.symbol,
        dayHeld,
        daysToLongTerm: daysRemaining,
        currentGain: holding.quantity * (holding.current_price - holding.average_cost),
        taxSavingsIfWait: holding.quantity * (holding.current_price - holding.average_cost) * 0.15, // Difference between STCG and LTCG
        recommendation: daysRemaining < 30
          ? 'WAIT - 30 days to long-term (saves 15%+ in taxes)'
          : 'WAIT - approaching long-term holding period'
      });
    }
  });

  return daysToLongTerm.sort((a, b) => a.daysToLongTerm - b.daysToLongTerm);
}

/**
 * Calculate portfolio-level tax metrics
 *
 * @param {Array} holdings - Portfolio holdings
 * @param {number} taxRate - Effective tax rate
 * @returns {Object} Portfolio-level tax summary
 */
function calculatePortfolioTaxMetrics(holdings, taxRate = 0.20) {
  let totalCostBasis = 0;
  let totalCurrentValue = 0;
  let totalUnrealizedGain = 0;
  let totalTaxLiability = 0;
  let longTermGains = 0;
  let shortTermGains = 0;

  holdings.forEach(holding => {
    const metrics = calculateTaxMetrics(holding, taxRate);
    totalCostBasis += metrics.costBasis;
    totalCurrentValue += metrics.currentValue;
    totalUnrealizedGain += metrics.unrealizedGain;
    totalTaxLiability += metrics.taxLiability;

    if (metrics.isLongTerm && metrics.unrealizedGain > 0) {
      longTermGains += metrics.unrealizedGain;
    } else if (!metrics.isLongTerm && metrics.unrealizedGain > 0) {
      shortTermGains += metrics.unrealizedGain;
    }
  });

  const afterTaxValue = totalCurrentValue - totalTaxLiability;
  const afterTaxReturn = afterTaxValue - totalCostBasis;

  return {
    totalCostBasis: parseFloat(totalCostBasis.toFixed(2)),
    totalCurrentValue: parseFloat(totalCurrentValue.toFixed(2)),
    totalUnrealizedGain: parseFloat(totalUnrealizedGain.toFixed(2)),
    totalUnrealizedGainPercent: parseFloat(((totalUnrealizedGain / totalCostBasis) * 100).toFixed(2)),
    longTermGains: parseFloat(longTermGains.toFixed(2)),
    shortTermGains: parseFloat(shortTermGains.toFixed(2)),
    totalTaxLiability: parseFloat(totalTaxLiability.toFixed(2)),
    afterTaxValue: parseFloat(afterTaxValue.toFixed(2)),
    afterTaxReturn: parseFloat(afterTaxReturn.toFixed(2)),
    afterTaxReturnPercent: parseFloat(((afterTaxReturn / totalCostBasis) * 100).toFixed(2)),
    holdingsByTaxStatus: categorizeByTaxStatus(holdings)
  };
}

/**
 * Categorize holdings by tax status
 *
 * @param {Array} holdings - Portfolio holdings
 * @returns {Object} Holdings organized by tax characteristics
 */
function categorizeByTaxStatus(holdings) {
  const categories = {
    longTermGains: [],
    shortTermGains: [],
    losses: [],
    noGain: []
  };

  holdings.forEach(holding => {
    const unrealizedGain = holding.quantity * (holding.current_price - holding.average_cost);
    const purchaseDate = new Date(holding.purchase_date);
    const today = new Date();
    const dayHeld = Math.floor((today - purchaseDate) / (1000 * 60 * 60 * 24));
    const isLongTerm = dayHeld >= 365;

    if (unrealizedGain > 0) {
      if (isLongTerm) {
        categories.longTermGains.push(holding.symbol);
      } else {
        categories.shortTermGains.push(holding.symbol);
      }
    } else if (unrealizedGain < 0) {
      categories.losses.push(holding.symbol);
    } else {
      categories.noGain.push(holding.symbol);
    }
  });

  return categories;
}

module.exports = {
  calculateTaxMetrics,
  identifyHarvestingOpportunities,
  generateHarvestingRecommendations,
  calculateAfterTaxReturn,
  scoreWithTaxOptimization,
  identifyLongTermThreshold,
  calculatePortfolioTaxMetrics,
  categorizeByTaxStatus
};
