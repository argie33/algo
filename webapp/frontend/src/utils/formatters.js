import numeral from "numeral";

// Format currency values
export const formatCurrency = (value, decimals = 2) => {
  if (value === null || value === undefined) return "N/A";

  const num = parseFloat(value);
  if (isNaN(num)) return "N/A";

  if (Math.abs(num) >= 1e12) {
    return numeral(num).format("$0.00a").replace("t", "T");
  } else if (Math.abs(num) >= 1e9) {
    return numeral(num).format("$0.00a").replace("b", "B");
  } else if (Math.abs(num) >= 1e6) {
    return numeral(num).format("$0.00a").replace("m", "M");
  } else if (Math.abs(num) >= 1e3) {
    return numeral(num).format("$0.00a").replace("k", "K");
  } else {
    return numeral(num).format(`$0.${"0".repeat(decimals)}`);
  }
};

// Format percentage values
export const formatPercentage = (value, decimals = 2) => {
  if (value === null || value === undefined) return "N/A";

  const num = parseFloat(value);
  if (isNaN(num)) return "N/A";

  return numeral(num / 100).format(`0.${"0".repeat(decimals)}%`);
};

// Format percentage change values with proper sign display
export const formatPercentageChange = (value, decimals = 2) => {
  if (value === null || value === undefined) return "N/A";

  const num = parseFloat(value);
  if (isNaN(num)) return "N/A";

  const formatted = numeral(Math.abs(num)).format(`0.${"0".repeat(decimals)}`);
  if (num > 0) {
    return `+${formatted}%`;
  } else if (num < 0) {
    return `-${formatted}%`;
  } else {
    return `${formatted}%`;
  }
};

// Alias for formatPercentage
export const formatPercent = formatPercentage;

// Format decimal values as percentages (e.g., 0.927 -> 92.70%)
// Use this for API values that are already in decimal format
export const formatDecimalAsPercent = (value, decimals = 2) => {
  if (value === null || value === undefined) return "N/A";

  const num = parseFloat(value);
  if (isNaN(num)) return "N/A";

  return numeral(num).format(`0.${"0".repeat(decimals)}%`);
};

// Format large numbers with abbreviations
export const formatNumber = (value, decimals = 2) => {
  if (value === null || value === undefined) return "N/A";

  const num = parseFloat(value);
  if (isNaN(num)) return "N/A";

  if (Math.abs(num) >= 1e12) {
    return numeral(num).format("0.00a").replace("t", "T");
  } else if (Math.abs(num) >= 1e9) {
    return numeral(num).format("0.00a").replace("b", "B");
  } else if (Math.abs(num) >= 1e6) {
    return numeral(num).format("0.00a").replace("m", "M");
  } else if (Math.abs(num) >= 1e3) {
    return numeral(num).format("0.00a").replace("k", "K");
  } else {
    return numeral(num).format(`0.${"0".repeat(decimals)}`);
  }
};

// Format numbers with commas but no abbreviations (for portfolio values, etc.)
export const formatExactNumber = (value, decimals = 0) => {
  if (value === null || value === undefined) return "N/A";

  const num = parseFloat(value);
  if (isNaN(num)) return "N/A";

  return numeral(num).format(`0,0.${"0".repeat(decimals)}`);
};

// Format ratio values
export const formatRatio = (value, decimals = 2) => {
  if (value === null || value === undefined) return "N/A";

  const num = parseFloat(value);
  if (isNaN(num)) return "N/A";

  return numeral(num).format(`0.${"0".repeat(decimals)}`);
};

// Get color for percentage change
export const getChangeColor = (value) => {
  if (value === null || value === undefined) return "#666";

  const num = parseFloat(value);
  if (isNaN(num)) return "#666";

  if (num > 0) return "#2e7d32"; // green
  if (num < 0) return "#d32f2f"; // red
  return "#666"; // neutral
};

// Get arrow icon for change
export const getChangeIcon = (value) => {
  if (value === null || value === undefined) return "";

  const num = parseFloat(value);
  if (isNaN(num)) return "";

  if (num > 0) return "↗";
  if (num < 0) return "↘";
  return "→";
};

// Format date strings
export const formatDate = (dateString) => {
  if (!dateString) return "N/A";

  try {
    const date = new Date(dateString);
    return date.toLocaleDateString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch (error) {
    return "Invalid Date";
  }
};

// Format datetime strings
export const formatDateTime = (dateString) => {
  if (!dateString) return "N/A";

  try {
    const date = new Date(dateString);
    return date.toLocaleDateString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch (error) {
    return "Invalid Date";
  }
};

// Debounce function for search inputs
export const debounce = (func, wait) => {
  let timeout;
  return function executedFunction(...args) {
    const later = () => {
      clearTimeout(timeout);
      func(...args);
    };
    clearTimeout(timeout);
    timeout = setTimeout(later, wait);
  };
};

// Calculate market cap size category
export const getMarketCapCategory = (marketCap) => {
  if (!marketCap) return "Unknown";

  const cap = parseFloat(marketCap);
  if (isNaN(cap)) return "Unknown";

  if (cap >= 200e9) return "Mega Cap";
  if (cap >= 10e9) return "Large Cap";
  if (cap >= 2e9) return "Mid Cap";
  if (cap >= 300e6) return "Small Cap";
  if (cap >= 50e6) return "Micro Cap";
  return "Nano Cap";
};

// Get financial health score based on key metrics
export const getFinancialHealthScore = (metrics) => {
  if (!metrics) return { score: 0, grade: "F", color: "#d32f2f" };

  let score = 0;
  let factors = 0;

  // P/E ratio (lower is better, but not too low)
  if (metrics.trailing_pe && metrics.trailing_pe > 0) {
    if (metrics.trailing_pe < 15) score += 20;
    else if (metrics.trailing_pe < 25) score += 15;
    else if (metrics.trailing_pe < 35) score += 10;
    else score += 5;
    factors++;
  }

  // Debt to equity (lower is better)
  if (metrics.debt_to_equity !== null && metrics.debt_to_equity !== undefined) {
    if (metrics.debt_to_equity < 0.3) score += 20;
    else if (metrics.debt_to_equity < 0.6) score += 15;
    else if (metrics.debt_to_equity < 1.0) score += 10;
    else score += 5;
    factors++;
  }

  // Current ratio (higher is better)
  if (metrics.current_ratio) {
    if (metrics.current_ratio > 2) score += 20;
    else if (metrics.current_ratio > 1.5) score += 15;
    else if (metrics.current_ratio > 1) score += 10;
    else score += 5;
    factors++;
  }

  // ROE (higher is better)
  if (metrics.return_on_equity_pct) {
    if (metrics.return_on_equity_pct > 20) score += 20;
    else if (metrics.return_on_equity_pct > 15) score += 15;
    else if (metrics.return_on_equity_pct > 10) score += 10;
    else if (metrics.return_on_equity_pct > 5) score += 5;
    factors++;
  }

  // Revenue growth (higher is better)
  if (metrics.revenue_growth_pct) {
    if (metrics.revenue_growth_pct > 20) score += 20;
    else if (metrics.revenue_growth_pct > 10) score += 15;
    else if (metrics.revenue_growth_pct > 5) score += 10;
    else if (metrics.revenue_growth_pct > 0) score += 5;
    factors++;
  }

  const finalScore = factors > 0 ? score / factors : 0;

  let grade, color;
  if (finalScore >= 18) {
    grade = "A";
    color = "#2e7d32";
  } else if (finalScore >= 15) {
    grade = "B";
    color = "#388e3c";
  } else if (finalScore >= 12) {
    grade = "C";
    color = "#f57c00";
  } else if (finalScore >= 8) {
    grade = "D";
    color = "#f57c00";
  } else {
    grade = "F";
    color = "#d32f2f";
  }

  return { score: finalScore, grade, color };
};

// ========== PROFESSIONAL FACTOR INPUT FORMATTING ==========
/**
 * Format factor input values consistently for display
 * Handles percentages, decimals, ratios, and special cases
 * @param {string} fieldName - The field name (e.g., 'gross_margin_pct')
 * @param {number} value - The raw value to format
 * @returns {string} - Professionally formatted value suitable for display
 */
export const formatFactorInput = (fieldName, value) => {
  // Handle null/undefined values
  if (value === null || value === undefined || value === 'null') {
    return 'N/A';
  }

  const numValue = parseFloat(value);
  if (isNaN(numValue)) {
    return 'N/A';
  }

  const fieldNameLower = fieldName.toLowerCase();

  // ========== PERCENTAGE FIELDS (Display with %) ==========
  // Fields explicitly marked as _pct (percentage fields)
  if (fieldNameLower.endsWith('_pct') || fieldNameLower.includes('_percent')) {
    return `${numValue.toFixed(2)}%`;
  }

  // Growth metrics (CAGR, YoY growth)
  if (fieldNameLower.includes('growth') || fieldNameLower.includes('cagr')) {
    return `${numValue.toFixed(2)}%`;
  }

  // Momentum and return metrics
  if (fieldNameLower.includes('momentum') || fieldNameLower.includes('return')) {
    return `${numValue.toFixed(2)}%`;
  }

  // Price vs SMA/range metrics
  if (fieldNameLower.includes('price_vs') || fieldNameLower.includes('vs_sma') || fieldNameLower.includes('vs_52w')) {
    return `${numValue.toFixed(2)}%`;
  }

  // Trend metrics (displayed as percentage point changes)
  if (fieldNameLower.includes('trend')) {
    if (fieldNameLower.includes('margin') || fieldNameLower.includes('roe') || fieldNameLower.includes('roa')) {
      return `${numValue.toFixed(2)} pp`;
    }
    return `${numValue.toFixed(2)}%`;
  }

  // Volatility, drawdown, and risk metrics
  if (fieldNameLower.includes('volatility') || fieldNameLower.includes('drawdown') || fieldNameLower.includes('spread') || fieldNameLower.includes('range')) {
    return `${numValue.toFixed(2)}%`;
  }

  // Surprise metrics (earnings surprise) - are percentages
  if (fieldNameLower.includes('surprise')) {
    return `${numValue.toFixed(2)}%`;
  }

  // ========== DECIMAL/RATIO FIELDS (Display without %) ==========
  // Ratios (current_ratio, quick_ratio, debt_to_equity)
  if (fieldNameLower.includes('ratio') || fieldNameLower.includes('_to_')) {
    // Special cases: payout_ratio and dividend_yield should be percentages
    if (fieldNameLower.includes('payout') || fieldNameLower.includes('dividend_yield')) {
      return `${(numValue * 100).toFixed(2)}%`;
    }
    return numValue.toFixed(2);
  }

  // Margin fields (gross_margin, operating_margin, profit_margin)
  if (fieldNameLower.includes('margin')) {
    if (numValue < 10) {
      return `${(numValue * 100).toFixed(2)}%`;
    }
    return `${numValue.toFixed(2)}%`;
  }

  // Beta and other market metrics
  if (fieldNameLower === 'beta' || fieldNameLower.includes('beta')) {
    return numValue.toFixed(2);
  }

  // Liquidity/Volume consistency metrics (0-100 scale)
  if (fieldNameLower.includes('consistency') || fieldNameLower.includes('velocity') || fieldNameLower.includes('rating')) {
    return numValue.toFixed(1);
  }

  // ROE, ROA, and other profitability metrics
  if (fieldNameLower.includes('return_on')) {
    if (numValue < 10) {
      return `${(numValue * 100).toFixed(2)}%`;
    }
    return `${numValue.toFixed(2)}%`;
  }

  // Ownership percentages
  if (fieldNameLower.includes('ownership') || fieldNameLower.includes('insider') || fieldNameLower.includes('short_percent')) {
    if (numValue < 10) {
      return `${(numValue * 100).toFixed(2)}%`;
    }
    return `${numValue.toFixed(2)}%`;
  }

  // EPS and earnings metrics
  if (fieldNameLower.includes('eps') || fieldNameLower.includes('earnings')) {
    if (fieldNameLower.includes('stability')) {
      return numValue.toFixed(2);
    }
    return `${numValue.toFixed(2)}%`;
  }

  // Price metrics and valuations (P/E, P/B, P/S, EV metrics)
  if (fieldNameLower.includes('stock_') || fieldNameLower.includes('_pe') || fieldNameLower.includes('_pb') ||
      fieldNameLower.includes('_ps') || fieldNameLower.includes('peg') || fieldNameLower.includes('_ev_')) {
    return numValue.toFixed(2);
  }

  // FCF and cash flow metrics
  if (fieldNameLower.includes('fcf') || fieldNameLower.includes('_cf_') || fieldNameLower.includes('cash_flow')) {
    if (numValue < 10) {
      return numValue.toFixed(2);
    }
    return `${numValue.toFixed(2)}%`;
  }

  // Default: display as-is with 2 decimal places
  return numValue.toFixed(2);
};

/**
 * Get professional human-readable labels for factor fields
 * @param {string} fieldName - The field name
 * @returns {string} - Formatted label
 */
export const getFactorFieldLabel = (fieldName) => {
  const labelMap = {
    // Momentum
    momentum_3m: 'Momentum (3M)',
    momentum_6m: 'Momentum (6M)',
    momentum_12m: 'Momentum (12M)',
    momentum_12_3: 'Momentum Spread (12M-3M)',
    price_vs_sma_50: 'Price vs SMA 50',
    price_vs_sma_200: 'Price vs SMA 200',
    price_vs_52w_high: 'Price vs 52W High',

    // Growth
    revenue_growth_3y_cagr: 'Revenue Growth (3Y CAGR)',
    eps_growth_3y_cagr: 'EPS Growth (3Y CAGR)',
    operating_income_growth_yoy: 'Operating Income Growth (YoY)',
    roe_trend: 'ROE Trend',
    sustainable_growth_rate: 'Sustainable Growth Rate',
    fcf_growth_yoy: 'FCF Growth (YoY)',
    net_income_growth_yoy: 'Net Income Growth (YoY)',
    gross_margin_trend: 'Gross Margin Trend',
    operating_margin_trend: 'Operating Margin Trend',
    net_margin_trend: 'Net Margin Trend',
    quarterly_growth_momentum: 'Quarterly Growth Momentum',

    // Quality
    return_on_equity_pct: 'Return on Equity (ROE)',
    return_on_assets_pct: 'Return on Assets (ROA)',
    gross_margin_pct: 'Gross Margin',
    operating_margin_pct: 'Operating Margin',
    profit_margin_pct: 'Profit Margin',
    fcf_to_net_income: 'FCF to Net Income',
    operating_cf_to_net_income: 'Operating CF to Net Income',
    debt_to_equity: 'Debt to Equity',
    current_ratio: 'Current Ratio',
    quick_ratio: 'Quick Ratio',
    earnings_surprise_avg: 'Earnings Surprise (Avg)',
    eps_growth_stability: 'EPS Growth Stability',
    payout_ratio: 'Payout Ratio',

    // Stability
    volatility_12m_pct: 'Volatility (12M)',
    max_drawdown_52w_pct: 'Max Drawdown (52W)',
    beta: 'Beta',
    volume_consistency: 'Volume Consistency',
    turnover_velocity: 'Turnover Velocity',
    volatility_volume_ratio: 'Volatility/Volume Ratio',
    daily_spread: 'Daily Spread',
    range_52w_pct: '52W Range',

    // Value
    stock_pb: 'Price to Book (P/B)',
    stock_pe: 'Price to Earnings (P/E)',
    stock_ps: 'Price to Sales (P/S)',
    peg_ratio: 'PEG Ratio',
    stock_ev_ebitda: 'EV to EBITDA',
    stock_ev_revenue: 'EV to Revenue',
    stock_dividend_yield: 'Dividend Yield',

    // Positioning
    institution_count: 'Institutional Holders',
    insider_ownership_pct: 'Insider Ownership',
    short_percent_of_float: 'Short % of Float',
    institutional_ownership_pct: 'Institutional Ownership',
    institutional_ownership: 'Institutional Ownership',
    insider_ownership: 'Insider Ownership',
    short_ratio: 'Short Ratio',
    acc_dist_rating: 'Accumulation/Distribution',
  };

  return labelMap[fieldName] || fieldName.replace(/_/g, ' ').split(' ').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ');
};

// Consistent technical indicator status helper
// This version does NOT return JSX, only keys for icon and color
export const getTechStatus = (indicator, value) => {
  if (value === null || value === undefined)
    return { icon: "info", color: "text.secondary", label: "N/A" };
  switch (indicator) {
    case "rsi":
      if (value > 70)
        return { icon: "up", color: "error.main", label: "Overbought" };
      if (value < 30)
        return { icon: "down", color: "primary.main", label: "Oversold" };
      return { icon: "neutral", color: "success.main", label: "Neutral" };
    case "macd":
      if (value > 0)
        return { icon: "up", color: "success.main", label: "Bullish" };
      if (value < 0)
        return { icon: "down", color: "error.main", label: "Bearish" };
      return { icon: "flat", color: "warning.main", label: "Flat" };
    case "adx":
      if (value >= 25)
        return { icon: "up", color: "success.main", label: "Trending" };
      return { icon: "flat", color: "info.main", label: "Weak" };
    case "atr":
      if (value > 2)
        return { icon: "up", color: "warning.main", label: "High Volatility" };
      return { icon: "flat", color: "info.main", label: "Low Volatility" };
    case "mfi":
      if (value > 80)
        return { icon: "up", color: "error.main", label: "Overbought" };
      if (value < 20)
        return { icon: "down", color: "primary.main", label: "Oversold" };
      return { icon: "neutral", color: "success.main", label: "Neutral" };
    case "roc":
    case "mom":
      if (value > 0)
        return { icon: "up", color: "success.main", label: "Positive" };
      if (value < 0)
        return { icon: "down", color: "error.main", label: "Negative" };
      return { icon: "flat", color: "info.main", label: "Flat" };
    case "bbands_upper":
    case "bbands_middle":
    case "bbands_lower":
      return { icon: "neutral", color: "info.main", label: "" };
    case "sma_10":
    case "sma_20":
    case "sma_50":
    case "sma_150":
    case "sma_200":
    case "ema_4":
    case "ema_9":
    case "ema_21":
      return { icon: "neutral", color: "secondary.main", label: "" };
    case "pivot_high":
      if (value)
        return { icon: "up", color: "success.main", label: "Pivot High" };
      return { icon: "neutral", color: "info.main", label: "" };
    case "pivot_low":
      if (value)
        return { icon: "down", color: "primary.main", label: "Pivot Low" };
      return { icon: "neutral", color: "info.main", label: "" };
    default:
      return { icon: "info", color: "text.secondary", label: "" };
  }
};
