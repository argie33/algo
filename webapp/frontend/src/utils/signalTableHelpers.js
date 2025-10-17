/**
 * Signal Table Helper Functions
 * Provides reusable utilities for dynamic signal table rendering across pages
 */

import { formatCurrency } from './formatters';

/**
 * Intelligently format cell values based on field name
 */
export const formatCellValue = (value, key) => {
  if (value === null || value === undefined || value === "" || value === "None") {
    return "—";
  }

  // Format currency fields
  if (key.includes("price") || key.includes("level") || key.includes("target") ||
      key === "close" || key === "open" || key === "high" || key === "low") {
    return formatCurrency(value);
  }

  // Format percentage fields
  if (key.includes("pct") || key.includes("percent") || key.includes("ratio") ||
      key === "risk_reward_ratio") {
    const num = Number(value);
    if (key === "risk_reward_ratio") {
      return `${num.toFixed(1)}:1`;
    }
    return `${num.toFixed(2)}%`;
  }

  // Format date fields
  if (key.includes("date") && typeof value === "string") {
    try {
      return new Date(value).toLocaleDateString();
    } catch {
      return value;
    }
  }

  // Format numbers with decimals
  if (typeof value === "number") {
    return Number.isInteger(value) ? value : value.toFixed(2);
  }

  return String(value);
};

/**
 * Determine column alignment based on field name
 */
export const getCellAlign = (key) => {
  if (key.includes("price") || key.includes("level") || key.includes("target") ||
      key.includes("pct") || key.includes("percent") || key.includes("ratio") ||
      key === "close" || key === "open" || key === "high" || key === "low" ||
      key === "volume") {
    return "right";
  }
  return "left";
};

/**
 * Get dynamic columns from signals data with priority ordering
 * Prioritizes important columns first, then alphabetizes the rest
 */
export const getDynamicColumns = (signals, customPriorityColumns = null) => {
  if (!signals || signals.length === 0) {
    return [];
  }

  // Default priority columns - customize via parameter if needed
  const defaultPriorityColumns = [
    "symbol", "company_name", "signal", "date",
    "current_price", "close", "open", "high", "low",
    "buylevel", "stoplevel", "selllevel", "target_price", "profit_target_20pct", "profit_target_25pct",
    "risk_reward_ratio", "risk_pct", "market_stage", "stage_confidence", "sata_score",
    "entry_quality_score", "next_earnings_date", "days_to_earnings",
    "rsi", "adx", "atr",
    "pct_from_ema_21", "pct_from_sma_50", "pct_from_sma_200",
    "volume", "volume_ratio", "volume_analysis",
    "signal_state", "days_in_current_state", "current_gain_loss_pct"
  ];

  const priorityColumns = customPriorityColumns || defaultPriorityColumns;

  // Get all keys from first signal
  const allKeys = Object.keys(signals[0] || {});

  // Sort: priority columns first (in order), then rest alphabetically
  const sortedKeys = [
    ...priorityColumns.filter(col => allKeys.includes(col)),
    ...allKeys.filter(col => !priorityColumns.includes(col)).sort()
  ];

  return sortedKeys;
};

/**
 * Format column header name for display
 */
export const formatColumnHeader = (columnKey) => {
  return columnKey
    .replace(/_/g, " ")
    .split(" ")
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
};
