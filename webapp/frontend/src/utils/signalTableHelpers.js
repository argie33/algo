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

  // Format currency fields (prices, levels, targets, moving averages)
  if (key.includes("price") || key.includes("level") || key.includes("target") ||
      key === "close" || key === "open" || key === "high" || key === "low" ||
      key === "sma_50" || key === "sma_200" || key === "ema_21" ||
      key === "pivot_price" || key === "buy_zone_start" || key === "buy_zone_end") {
    return formatCurrency(value);
  }

  // Format percentage fields
  if (key.includes("pct") || key.includes("percent") ||
      key === "risk_reward_ratio" || key === "volume_ratio" ||
      key === "daily_range_pct" || key === "signal_strength" || key === "bull_percentage" || key === "strength") {
    const num = Number(value);
    if (key === "risk_reward_ratio") {
      return `${num.toFixed(1)}:1`;
    }
    if (key === "volume_ratio") {
      return `${num.toFixed(2)}x`;
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
      key === "volume" || key === "sma_50" || key === "sma_200" || key === "ema_21" ||
      key === "daily_range_pct" || key === "volume_ratio" ||
      key === "strength" || key === "signal_strength" || key === "bull_percentage" || key === "close_price" ||
      key === "rsi" || key === "adx" || key === "atr") {
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
    "symbol", "company_name", "signal", "signal_type", "date",
    "current_price", "close", "open", "high", "low", "daily_range_pct",
    "buylevel", "stoplevel", "selllevel", "target_price",
    "profit_target_8pct", "profit_target_20pct", "profit_target_25pct",
    "risk_reward_ratio", "risk_pct", "position_size_recommendation",
    "market_stage", "stage_number", "stage_confidence", "substage", "quality_score",
    "signal_type", "pivot_price", "buy_zone_start", "buy_zone_end",
    "exit_trigger_1_price", "exit_trigger_2_price", "exit_trigger_3_price", "exit_trigger_4_price",
    "initial_stop", "trailing_stop", "base_type", "base_length_days",
    "next_earnings_date", "days_to_earnings",
    "rsi", "adx", "atr",
    "ema_21", "sma_50", "sma_200",
    "pct_from_ema_21", "pct_from_sma_50", "pct_from_sma_200",
    "volume", "avg_volume_50d", "volume_surge_pct", "volume_ratio", "volume_analysis",
    "rs_rating", "breakout_quality", "strength", "signal_strength", "bull_percentage", "close_price",
    "signal_state", "days_in_current_state", "current_gain_loss_pct", "current_gain_pct", "days_in_position",
    "inposition", "sell_level", "entry_price", "mansfield_rs", "sata_score", "entry_quality_score"
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
