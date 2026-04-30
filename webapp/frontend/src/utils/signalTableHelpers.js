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
      key === "sma_5" || key === "sma_20" || key === "sma_50" || key === "sma_200" ||
      key === "ema_21" || key === "ema_26" ||
      key === "pivot_price" || key === "buy_zone_start" || key === "buy_zone_end" ||
      key === "range_high" || key === "range_low" || key === "current_price" ||
      key === "exit_trigger_1_price" || key === "exit_trigger_2_price" ||
      key === "exit_trigger_3_price" || key === "exit_trigger_4_price" ||
      key === "macd" || key === "signal_line") {
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
      key === "volume" || key === "avg_volume_50d" ||
      key === "sma_5" || key === "sma_20" || key === "sma_50" || key === "sma_200" ||
      key === "ema_21" || key === "ema_26" ||
      key === "daily_range_pct" || key === "volume_ratio" ||
      key === "strength" || key === "signal_strength" || key === "entry_quality_score" ||
      key === "breakout_quality" || key === "bull_percentage" || key === "close_price" ||
      key === "rsi" || key === "rsi_2" || key === "rsi_14" || key === "adx" || key === "atr" ||
      key === "rs_rating" || key === "mansfield_rs" || key === "sata_score" ||
      key === "range_age_days" || key === "range_strength" || key === "range_position" ||
      key === "confluence_score" || key === "stage_number" || key === "stage_confidence" ||
      key === "macd" || key === "signal_line" ||
      key === "td_buy_setup_count" || key === "td_sell_setup_count" ||
      key === "td_buy_countdown_count" || key === "td_sell_countdown_count") {
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
  // Organized for 100% data parity across Swing Trading, Range, and Mean Reversion strategies
  const defaultPriorityColumns = [
    // Core identification
    "symbol", "company_name", "signal", "signal_type", "date",

    // Price data
    "current_price", "close", "open", "high", "low",

    // Entry/Exit levels
    "entry_price", "buylevel", "stoplevel", "sell_level",
    "initial_stop", "trailing_stop",
    "pivot_price", "buy_zone_start", "buy_zone_end",

    // Profit targets & exit triggers
    "target_price", "target_estimate",
    "profit_target_8pct", "profit_target_20pct", "profit_target_25pct",
    "exit_trigger_1_price", "exit_trigger_2_price", "exit_trigger_3_price", "exit_trigger_4_price",

    // Risk/Reward
    "risk_pct", "risk_reward_ratio", "position_size_recommendation",

    // Market stage & quality
    "market_stage", "stage_number", "stage_confidence", "substage",
    "quality_score", "signal_strength", "entry_quality_score", "breakout_quality",
    "sata_score", "strength", "bull_percentage",

    // Range-specific (for range trading strategy)
    "range_high", "range_low", "range_position", "range_age_days", "range_strength", "range_height_pct",

    // Mean reversion specific (for mean reversion strategy)
    "rsi_2", "pct_above_200sma", "sma_5", "confluence_score",
    "target_1", "target_2",

    // Technical indicators
    "rsi", "rsi_14", "adx", "atr",
    "sma_20", "sma_50", "sma_200", "ema_21", "ema_26",
    "macd", "signal_line",
    "daily_range_pct", "base_type", "base_length_days",

    // Relative position
    "pct_from_ema21", "pct_from_sma50", "pct_from_sma200",

    // Volume analysis
    "volume", "avg_volume_50d", "volume_surge_pct", "volume_ratio", "volume_analysis",

    // RS metrics
    "rs_rating", "mansfield_rs",

    // DeMark indicators
    "td_buy_setup_count", "td_sell_setup_count",
    "td_buy_setup_complete", "td_sell_setup_complete",
    "td_buy_setup_perfected", "td_sell_setup_perfected",
    "td_buy_countdown_count", "td_sell_countdown_count",
    "td_pressure",

    // Position state (swing trading)
    "inposition", "signal_state", "days_in_current_state",
    "current_gain_loss_pct", "current_gain_pct", "current_pnl_pct", "days_in_position",
    "close_price"
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
