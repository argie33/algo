/**
 * Safe financial calculation utilities
 * Prevents NaN, undefined, and silent calculation failures in financial displays
 * All functions handle null/undefined/NaN gracefully with sensible defaults
 */

const SAFE_DEFAULTS = {
  ZERO: 0,
  EMPTY_ARRAY: [],
  EMPTY_STRING: "—",
  FALSE: false,
  NULL: null,
};

/**
 * Safe number conversion that rejects invalid values
 */
export const toSafeNumber = (value, defaultValue = SAFE_DEFAULTS.ZERO) => {
  if (value == null) return defaultValue;
  const num = Number(value);
  return isNaN(num) ? defaultValue : num;
};

/**
 * Safe division that handles divide-by-zero
 */
export const safeDivide = (
  numerator,
  denominator,
  defaultValue = SAFE_DEFAULTS.ZERO
) => {
  const num = toSafeNumber(numerator, null);
  const den = toSafeNumber(denominator, null);

  if (num === null || den === null) return defaultValue;
  if (den === 0) return defaultValue;

  const result = num / den;
  return isNaN(result) ? defaultValue : result;
};

/**
 * Safe sum that accumulates numbers safely
 */
export const safeSum = (values, defaultValue = SAFE_DEFAULTS.ZERO) => {
  if (!Array.isArray(values)) return defaultValue;

  let sum = 0;
  let hasValidValue = false;

  for (const val of values) {
    const num = toSafeNumber(val, null);
    if (num !== null) {
      sum += num;
      hasValidValue = true;
    }
  }

  return hasValidValue ? sum : defaultValue;
};

/**
 * Safe percentage calculation
 */
export const safePercentage = (
  part,
  whole,
  defaultValue = SAFE_DEFAULTS.ZERO
) => {
  const p = toSafeNumber(part, null);
  const w = toSafeNumber(whole, null);

  if (p === null || w === null || w === 0) return defaultValue;

  const result = (p / w) * 100;
  return isNaN(result) ? defaultValue : result;
};

/**
 * Safe multiplication for price calculations
 */
export const safeMultiply = (a, b, defaultValue = SAFE_DEFAULTS.ZERO) => {
  const num1 = toSafeNumber(a, null);
  const num2 = toSafeNumber(b, null);

  if (num1 === null || num2 === null) return defaultValue;

  const result = num1 * num2;
  return isNaN(result) ? defaultValue : result;
};

/**
 * Safe subtraction
 */
export const safeSubtract = (
  minuend,
  subtrahend,
  defaultValue = SAFE_DEFAULTS.ZERO
) => {
  const a = toSafeNumber(minuend, null);
  const b = toSafeNumber(subtrahend, null);

  if (a === null || b === null) return defaultValue;

  const result = a - b;
  return isNaN(result) ? defaultValue : result;
};

/**
 * Safe addition
 */
export const safeAdd = (a, b, defaultValue = SAFE_DEFAULTS.ZERO) => {
  const num1 = toSafeNumber(a, null);
  const num2 = toSafeNumber(b, null);

  if (num1 === null && num2 === null) return defaultValue;

  const result = (num1 ?? 0) + (num2 ?? 0);
  return isNaN(result) ? defaultValue : result;
};

/**
 * Safe property accessor with type checking
 */
export const safeGet = (obj, path, defaultValue = SAFE_DEFAULTS.NULL) => {
  if (!obj || typeof obj !== "object") return defaultValue;
  if (typeof path !== "string") return defaultValue;

  const keys = path.split(".");
  let current = obj;

  for (const key of keys) {
    if (current == null || typeof current !== "object") {
      return defaultValue;
    }
    current = current[key];
  }

  return current ?? defaultValue;
};

/**
 * Safe array access that validates structure
 */
export const safeGetArray = (
  data,
  path = "",
  defaultValue = SAFE_DEFAULTS.EMPTY_ARRAY
) => {
  if (!data) return defaultValue;

  let target = data;
  if (path) {
    target = safeGet(data, path, null);
  }

  if (Array.isArray(target)) return target;
  if (target && typeof target === "object" && Array.isArray(target.items))
    return target.items;
  if (target && typeof target === "object" && Array.isArray(target.data))
    return target.data;

  return defaultValue;
};

/**
 * Safe accumulation pattern for financial totals
 * Accumulates values with null-checking
 */
export const safeAccumulate = (
  items,
  accessor,
  defaultValue = SAFE_DEFAULTS.ZERO
) => {
  if (!Array.isArray(items)) return defaultValue;

  let total = 0;
  let hasValidValue = false;

  for (const item of items) {
    if (!item || typeof item !== "object") continue;

    const value =
      typeof accessor === "function"
        ? accessor(item)
        : safeGet(item, String(accessor), null);

    const num = toSafeNumber(value, null);
    if (num !== null) {
      total += num;
      hasValidValue = true;
    }
  }

  return hasValidValue ? total : defaultValue;
};

/**
 * Safe portfolio value calculation from positions
 */
export const safePortfolioValue = (positions) => {
  return safeAccumulate(positions, "position_value", SAFE_DEFAULTS.ZERO);
};

/**
 * Safe P&L percentage calculation
 */
export const safePnlPercentage = (unrealizedPnl, portfolioValue) => {
  const pnl = toSafeNumber(unrealizedPnl, null);
  const value = toSafeNumber(portfolioValue, null);

  if (pnl === null || value === null || value === 0) {
    return null;
  }

  const result = (pnl / value) * 100;
  return isNaN(result) ? null : result;
};

/**
 * Safe R-multiple calculation
 */
export const safeRMultiple = (pnl, risk) => {
  const p = toSafeNumber(pnl, null);
  const r = toSafeNumber(risk, null);

  if (p === null || r === null || r === 0) {
    return null;
  }

  const result = p / r;
  return isNaN(result) ? null : result;
};

/**
 * Safe distance calculation (price1 - price2) / price2 * 100
 */
export const safeDistancePercentage = (currentPrice, targetPrice) => {
  const curr = toSafeNumber(currentPrice, null);
  const target = toSafeNumber(targetPrice, null);

  if (curr === null || target === null || target === 0) {
    return null;
  }

  const distance = ((curr - target) / Math.abs(target)) * 100;
  return isNaN(distance) ? null : distance;
};

/**
 * Safe position risk calculation
 */
export const safePositionRisk = (position) => {
  if (!position || typeof position !== "object") return SAFE_DEFAULTS.ZERO;

  const quantity = toSafeNumber(safeGet(position, "quantity"), null);
  const stopLoss = toSafeNumber(safeGet(position, "stop_loss_price"), null);
  const entryPrice = toSafeNumber(safeGet(position, "avg_entry_price"), null);

  if (quantity === null || stopLoss === null || entryPrice === null) {
    return SAFE_DEFAULTS.ZERO;
  }

  if (stopLoss >= entryPrice) return SAFE_DEFAULTS.ZERO;

  const riskPerShare = entryPrice - stopLoss;
  const totalRisk = riskPerShare * quantity;

  return isNaN(totalRisk) ? SAFE_DEFAULTS.ZERO : totalRisk;
};

/**
 * Safe portfolio composition calculation
 */
export const safeCompositionPct = (itemValue, totalValue) => {
  const item = toSafeNumber(itemValue, null);
  const total = toSafeNumber(totalValue, null);

  if (item === null || total === null || total === 0) {
    return SAFE_DEFAULTS.ZERO;
  }

  const pct = (item / total) * 100;
  return isNaN(pct) ? SAFE_DEFAULTS.ZERO : pct;
};

/**
 * Check if a calculation result is valid (not null/undefined/NaN)
 */
export const isValidCalculation = (value) => {
  if (value === null || value === undefined) return false;
  if (typeof value === "number" && isNaN(value)) return false;
  return true;
};

/**
 * Render number with fallback for invalid calculations
 */
export const renderSafeNumber = (
  value,
  fallback = SAFE_DEFAULTS.EMPTY_STRING,
  decimals = null
) => {
  if (!isValidCalculation(value)) return fallback;

  const num = Number(value);
  if (decimals !== null) {
    return num.toFixed(decimals);
  }
  return String(num);
};

/**
 * Build safe object from potentially null/undefined fields
 */
export const buildSafeObject = (obj, schema) => {
  const result = {};

  if (!obj || typeof obj !== "object") {
    // Fill with defaults if obj is invalid
    for (const [key, defaultValue] of Object.entries(schema)) {
      result[key] = defaultValue;
    }
    return result;
  }

  for (const [key, defaultValue] of Object.entries(schema)) {
    result[key] = safeGet(obj, key, defaultValue);
  }

  return result;
};

/**
 * Validate position data before calculations
 */
export const validatePosition = (position) => {
  if (!position || typeof position !== "object") return null;

  const required = ["symbol", "avg_entry_price", "current_price", "quantity"];
  const missing = required.filter(
    (field) => !Object.prototype.hasOwnProperty.call(position, field)
  );

  if (missing.length > 0) {
    console.warn(
      "[SafeCalculations] Position missing required fields:",
      missing,
      position
    );
    return null;
  }

  return buildSafeObject(position, {
    symbol: position.symbol,
    avg_entry_price: toSafeNumber(position.avg_entry_price, null),
    current_price: toSafeNumber(position.current_price, null),
    quantity: toSafeNumber(position.quantity, null),
    stop_loss_price: toSafeNumber(position.stop_loss_price, null),
    position_value: toSafeNumber(position.position_value, null),
    unrealized_pnl_dollars: toSafeNumber(position.unrealized_pnl_dollars, null),
  });
};
