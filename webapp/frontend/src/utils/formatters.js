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
