/**
 * Hook wrapper for safe financial data processing
 * Combines useApiQuery with automatic null/undefined safety for calculations
 *
 * Usage:
 *   const { data, positions, portfolio } = useSafeFinancialData(
 *     ['positions'],
 *     () => api.get('/api/positions'),
 *     {
 *       schema: {
 *         positions: [],
 *         portfolio: { total_value: 0, unrealized_pnl_dollars: 0 }
 *       }
 *     }
 *   );
 */

import { useMemo } from "react";
import { useApiQuery } from "./useApiQuery";
import {
  toSafeNumber,
  safeGet,
  safeGetArray,
  safeAccumulate,
  isValidCalculation,
  buildSafeObject,
  validatePosition,
} from "../utils/safeCalculations";

/**
 * Validate and normalize API response with schema
 */
export const applySchema = (data, schema) => {
  if (!data || typeof data !== "object") {
    return buildSafeObject({}, schema);
  }

  const result = {};
  for (const [key, defaultValue] of Object.entries(schema)) {
    const value = safeGet(data, key, null);

    if (value === null) {
      result[key] = defaultValue;
    } else if (
      typeof defaultValue === "object" &&
      !Array.isArray(defaultValue)
    ) {
      result[key] = typeof value === "object" ? value : defaultValue;
    } else if (Array.isArray(defaultValue)) {
      result[key] = Array.isArray(value) ? value : defaultValue;
    } else {
      result[key] = value ?? defaultValue;
    }
  }

  return result;
};

/**
 * Safe hook for financial data with automatic schema validation
 */
export const useSafeFinancialData = (queryKey, queryFn, options = {}) => {
  const { schema = {}, ...queryOptions } = options;

  const {
    data: rawData,
    loading,
    error,
    refetch,
  } = useApiQuery(queryKey, queryFn, queryOptions);

  // Apply schema and validate data
  const normalizedData = useMemo(() => {
    if (!rawData) {
      return buildSafeObject({}, schema);
    }

    return applySchema(rawData, schema);
  }, [rawData, schema]);

  return {
    data: rawData,
    normalizedData,
    loading,
    error,
    refetch,
  };
};

/**
 * Safe portfolio calculations from positions
 */
export const useSafePortfolioCalculations = (positions, portfolio = {}) => {
  return useMemo(() => {
    const posArray = safeGetArray(positions, "", []);

    // Validate all positions
    const validPositions = posArray
      .map((p) => validatePosition(p))
      .filter((p) => p !== null);

    // Calculate totals
    const totalValue = safeAccumulate(validPositions, "position_value", 0);
    const totalPnl = safeAccumulate(
      validPositions,
      "unrealized_pnl_dollars",
      0
    );
    const totalRisk = safeAccumulate(
      validPositions,
      (p) => {
        const qty = toSafeNumber(safeGet(p, "quantity"), null);
        const entry = toSafeNumber(safeGet(p, "avg_entry_price"), null);
        const stop = toSafeNumber(safeGet(p, "stop_loss_price"), null);

        if (qty === null || entry === null || stop === null) return 0;
        if (stop >= entry) return 0;

        return (entry - stop) * qty;
      },
      0
    );

    // Verify portfolio total if provided
    const portfolioTotal = toSafeNumber(
      safeGet(portfolio, "total_value"),
      null
    );
    const finalTotal = portfolioTotal !== null ? portfolioTotal : totalValue;

    // Calculate risk percentage
    const riskPct = finalTotal > 0 ? (totalRisk / finalTotal) * 100 : 0;

    // Calculate P&L percentage
    const pnlPct = finalTotal > 0 ? (totalPnl / finalTotal) * 100 : null;

    return {
      validPositions,
      totalValue,
      totalPnl,
      totalRisk,
      riskPct,
      pnlPct,
      positionCount: validPositions.length,
      hasValidData: validPositions.length > 0,
    };
  }, [positions, portfolio]);
};

/**
 * Safe number formatting for financial displays
 */
export const useSafeFormatting = () => {
  return useMemo(
    () => ({
      formatPrice: (value, decimals = 2) => {
        const num = toSafeNumber(value, null);
        return num === null ? "—" : `$${num.toFixed(decimals)}`;
      },

      formatPercent: (value, decimals = 1) => {
        const num = toSafeNumber(value, null);
        return num === null ? "—" : `${num.toFixed(decimals)}%`;
      },

      formatNumber: (value, decimals = 0) => {
        const num = toSafeNumber(value, null);
        return num === null ? "—" : num.toFixed(decimals);
      },

      formatRMultiple: (value) => {
        const num = toSafeNumber(value, null);
        return num === null ? "—" : `${num > 0 ? "+" : ""}${num.toFixed(2)}R`;
      },

      isValid: isValidCalculation,
    }),
    []
  );
};

/**
 * Safe performance calculations from trade data
 */
export const useSafePerformanceMetrics = (trades = [], performance = {}) => {
  return useMemo(() => {
    const tradeArray = safeGetArray(trades, "", []);
    const closedTrades = tradeArray.filter(
      (t) => safeGet(t, "status") === "closed"
    );

    const metrics = {
      totalTrades: closedTrades.length,
      totalReturn: toSafeNumber(safeGet(performance, "total_return_pct"), null),
      winRate: toSafeNumber(safeGet(performance, "win_rate_pct"), null),
      sharpe: toSafeNumber(safeGet(performance, "sharpe_annualized"), null),
      sortino: toSafeNumber(safeGet(performance, "sortino_annualized"), null),
      calmar: toSafeNumber(safeGet(performance, "calmar_ratio"), null),
      maxDrawdown: toSafeNumber(safeGet(performance, "max_drawdown_pct"), null),
      profitFactor: toSafeNumber(safeGet(performance, "profit_factor"), null),
      expectancy: toSafeNumber(safeGet(performance, "expectancy_r"), null),
      avgWin: toSafeNumber(safeGet(performance, "avg_win_pct"), null),
      avgLoss: toSafeNumber(safeGet(performance, "avg_loss_pct"), null),
      avgWinR: toSafeNumber(safeGet(performance, "avg_win_r"), null),
      avgLossR: toSafeNumber(safeGet(performance, "avg_loss_r"), null),
      grossWins: toSafeNumber(safeGet(performance, "gross_win_dollars"), null),
      grossLosses: toSafeNumber(
        safeGet(performance, "gross_loss_dollars"),
        null
      ),
      totalPnl: toSafeNumber(safeGet(performance, "total_pnl_dollars"), null),
    };

    // Add validation flags
    metrics.hasValidMetrics =
      Object.values(metrics).filter((v) => v !== null && typeof v === "number")
        .length > 0;

    return metrics;
  }, [trades, performance]);
};

export default {
  useSafeFinancialData,
  useSafePortfolioCalculations,
  useSafeFormatting,
  useSafePerformanceMetrics,
  applySchema,
};
