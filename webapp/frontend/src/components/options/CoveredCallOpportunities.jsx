import React, { useState, useMemo } from "react";
import {
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Box,
  TextField,
  Paper,
  CircularProgress,
  Alert,
  Chip,
  Typography,
  Grid,
  useTheme,
  alpha,
} from "@mui/material";
import {
  ExpandMore as ExpandMoreIcon,
  TrendingUp as TrendingUpIcon,
  TrendingDown as TrendingDownIcon,
  TrendingFlat as TrendingFlatIcon,
} from "@mui/icons-material";
import { useQuery } from "@tanstack/react-query";
import { getApiUrl } from "../../utils/apiUrl";

const API_BASE = getApiUrl();

function CoveredCallOpportunities() {
  const theme = useTheme();
  const [symbolFilter, setSymbolFilter] = useState("");
  const [minProbFilter, setMinProbFilter] = useState("70");
  const [minPremiumFilter, setMinPremiumFilter] = useState("1.5");
  const [sortBy, setSortBy] = useState("premium_pct");
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(25);

  // Build query parameters
  const queryParams = useMemo(() => {
    const params = new URLSearchParams({
      limit: rowsPerPage,
      page: page + 1,
      sort_by: sortBy,
      min_probability: minProbFilter || 70,
      min_premium_pct: minPremiumFilter || 1.5,
    });

    if (symbolFilter.trim()) {
      params.append("symbol", symbolFilter.trim().toUpperCase());
    }

    return params.toString();
  }, [symbolFilter, minProbFilter, minPremiumFilter, sortBy, page, rowsPerPage]);

  // Fetch opportunities with cache-busting and fresh data settings
  const { data, isLoading, error } = useQuery({
    queryKey: ["coveredCalls", queryParams],
    queryFn: async () => {
      // Add cache-busting timestamp to ensure fresh data
      const separator = queryParams ? "&" : "?";
      const url = `${API_BASE}/api/strategies/covered-calls?${queryParams}${separator}_t=${Date.now()}`;
      const response = await fetch(url);
      if (!response.ok) throw new Error("Failed to fetch opportunities");
      return response.json();
    },
    staleTime: 0, // Always fresh - NO caching
    gcTime: 0, // Disable garbage collection cache
    refetchOnWindowFocus: true, // Refetch when window regains focus
    refetchInterval: 30000, // Refetch every 30 seconds for fresh data
  });

  const items = data?.items || [];

  // Helpers
  const formatPercent = (value) => (value !== null && value !== undefined ? `${value.toFixed(2)}%` : "—");
  const formatPrice = (value) => (value !== null && value !== undefined ? `$${value.toFixed(2)}` : "—");
  const formatNumber = (value) => (value !== null && value !== undefined ? value.toFixed(2) : "—");

  // Convert database signals to user-friendly sell-side terminology
  const getDisplaySignal = (signal) => {
    if (signal === "STRONG_BUY") return "EXECUTE";
    if (signal === "BUY") return "GOOD";
    if (signal === "WAIT") return "WAIT";
    return "AVOID";
  };

  const getSignalConfig = (signal) => {
    const displaySignal = getDisplaySignal(signal);
    if (displaySignal === "EXECUTE" || displaySignal === "GOOD") {
      return {
        color: theme.palette.success.main,
        textColor: theme.palette.success.dark,
        bgColor: alpha(theme.palette.success.main, 0.1),
        borderColor: alpha(theme.palette.success.main, 0.2),
      };
    } else if (displaySignal === "WAIT") {
      return {
        color: theme.palette.warning.main,
        textColor: theme.palette.warning.dark,
        bgColor: alpha(theme.palette.warning.main, 0.1),
        borderColor: alpha(theme.palette.warning.main, 0.2),
      };
    }
    return {
      color: theme.palette.error.main,
      textColor: theme.palette.error.dark,
      bgColor: alpha(theme.palette.error.main, 0.1),
      borderColor: alpha(theme.palette.error.main, 0.2),
    };
  };

  const getTrendIcon = (trend) => {
    if (trend === "uptrend") return <TrendingUpIcon sx={{ fontSize: 18, color: theme.palette.success.main }} />;
    if (trend === "downtrend") return <TrendingDownIcon sx={{ fontSize: 18, color: theme.palette.error.main }} />;
    return <TrendingFlatIcon sx={{ fontSize: 18, color: theme.palette.warning.main }} />;
  };

  // Data field component
  const DataField = ({ label, value, format = "text", color = null, unit = "" }) => {
    let displayValue = value;
    if (format === "currency" && value) {
      displayValue = `$${parseFloat(value).toFixed(2)}`;
    } else if (format === "percent" && value !== null && value !== undefined) {
      displayValue = `${parseFloat(value).toFixed(2)}%`;
    } else if (format === "number" && value !== null && value !== undefined) {
      displayValue = parseFloat(value).toFixed(2);
    } else if (!value && value !== 0) {
      displayValue = "—";
    }

    return (
      <Box sx={{ mb: 1 }}>
        <Typography variant="caption" sx={{ color: "text.secondary", display: "block", mb: 0.5, fontWeight: 600 }}>
          {label}
        </Typography>
        <Typography
          variant="body2"
          sx={{
            fontWeight: 600,
            color: color || "text.primary",
            fontSize: "0.95rem",
          }}
        >
          {displayValue} {unit}
        </Typography>
      </Box>
    );
  };

  // Decision logic: Why this is a good opportunity to SELL the call
  const getDecisionLogic = (row) => {
    const reasons = [];

    // Premium quality - core reason to sell
    if (row.premium_pct >= 5) reasons.push(`✓ Excellent premium (${row.premium_pct.toFixed(2)}% income)`);
    else if (row.premium_pct >= 2.5) reasons.push(`✓ Good premium (${row.premium_pct.toFixed(2)}% income)`);
    else if (row.premium_pct >= 1.5) reasons.push(`✓ Decent premium (${row.premium_pct.toFixed(2)}% income)`);

    // IV elevated = better premium for call sellers
    if (row.iv_rank >= 70) reasons.push(`✓ Very high IV (${row.iv_rank.toFixed(0)} rank) = better premium for sellers`);
    else if (row.iv_rank >= 50) reasons.push(`✓ High IV (${row.iv_rank.toFixed(0)} rank) = attractive premium`);

    // Safety metrics
    if (row.probability_of_profit >= 80) reasons.push(`✓ High probability (${row.probability_of_profit}% PoP) - likely to keep full premium`);
    else if (row.probability_of_profit >= 70) reasons.push(`✓ Good probability (${row.probability_of_profit}% PoP) - solid profit chance`);

    // Trend stability
    if (row.trend === "uptrend") reasons.push("✓ Uptrend = lower assignment risk");
    else if (row.trend === "sideways") reasons.push("✓ Sideways = predictable income");

    // Stock quality
    if (row.composite_score >= 65) reasons.push(`✓ Quality stock (${row.composite_score.toFixed(0)}/100)`);
    else if (row.composite_score >= 50) reasons.push(`✓ Good quality (${row.composite_score.toFixed(0)}/100)`);

    // Volatility
    if (!row.high_beta_warning) reasons.push("✓ Manageable volatility");

    return reasons;
  };

  if (isLoading) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", py: 4 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (error) {
    return (
      <Alert severity="error" sx={{ mb: 2 }}>
        Error loading opportunities: {error.message}
      </Alert>
    );
  }

  return (
    <Box>
      {/* Filters */}
      <Paper sx={{ p: 2, mb: 3 }}>
        <Typography variant="h6" sx={{ mb: 2, fontWeight: 700 }}>
          Filters & Sorting
        </Typography>
        <Grid container spacing={2}>
          <Grid item xs={12} sm={6} md={2.5}>
            <TextField
              label="Stock Symbol"
              value={symbolFilter}
              onChange={(e) => {
                setSymbolFilter(e.target.value);
                setPage(0);
              }}
              placeholder="AAPL"
              size="small"
              fullWidth
            />
          </Grid>
          <Grid item xs={12} sm={6} md={2.5}>
            <TextField
              label="Min PoP %"
              type="number"
              value={minProbFilter}
              onChange={(e) => {
                setMinProbFilter(e.target.value);
                setPage(0);
              }}
              placeholder="70"
              size="small"
              fullWidth
            />
          </Grid>
          <Grid item xs={12} sm={6} md={2.5}>
            <TextField
              label="Min Premium %"
              type="number"
              value={minPremiumFilter}
              onChange={(e) => {
                setMinPremiumFilter(e.target.value);
                setPage(0);
              }}
              placeholder="1.5"
              size="small"
              fullWidth
            />
          </Grid>
          <Grid item xs={12} sm={6} md={2.5}>
            <TextField
              select
              label="Sort By"
              value={sortBy}
              onChange={(e) => {
                setSortBy(e.target.value);
                setPage(0);
              }}
              size="small"
              fullWidth
              SelectProps={{ native: true }}
            >
              <option value="premium_pct">Premium % (Best)</option>
              <option value="probability_of_profit">PoP % (Best)</option>
              <option value="expected_annual_return">Annual Return</option>
              <option value="expiration_date">Days to Expire</option>
            </TextField>
          </Grid>
        </Grid>
      </Paper>

      {/* Summary */}
      <Box sx={{ mb: 2 }}>
        <Typography variant="body2" sx={{ color: "text.secondary" }}>
          Found <strong>{data?.pagination?.total || 0}</strong> opportunities
        </Typography>
      </Box>

      {/* Accordion List */}
      {items.length === 0 ? (
        <Alert severity="info">No opportunities found with current filters</Alert>
      ) : (
        <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
          {items.map((row, idx) => {
            const config = getSignalConfig(row.entry_signal);

            return (
              <Accordion key={`${row.symbol}-${row.id}`} defaultExpanded={idx === 0}>
                {/* SUMMARY */}
                <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                  <Grid container alignItems="center" spacing={2} sx={{ width: "100%" }}>
                    {/* Signal Badge */}
                    <Grid item xs="auto">
                      <Chip
                        label={getDisplaySignal(row.entry_signal)}
                        sx={{
                          backgroundColor: alpha(config.color, 0.25),
                          color: config.textColor,
                          fontWeight: 700,
                          height: 32,
                          border: `1.5px solid ${config.color}`,
                        }}
                      />
                    </Grid>

                    {/* Symbol & Price */}
                    <Grid item xs={12} sm="auto" sx={{ flexGrow: { xs: 1, sm: 0 }, minWidth: { sm: 150 } }}>
                      <Box sx={{ display: "flex", flexDirection: "column", gap: 0.5 }}>
                        <Typography variant="h5" fontWeight={700}>
                          {row.symbol}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          {formatPrice(row.stock_price)}
                        </Typography>
                      </Box>
                    </Grid>

                    {/* Key Metrics on Right */}
                    <Grid item xs={12} sm sx={{ flexGrow: 1 }}>
                      <Grid container spacing={2} sx={{ ml: 0 }}>
                        <Grid item xs={6} sm="auto">
                          <Box sx={{ minWidth: 70 }}>
                            <Typography variant="caption" color="text.secondary" fontWeight={600} sx={{ display: "block", fontSize: "0.7rem", mb: 0.25 }}>
                              PREMIUM
                            </Typography>
                            <Typography variant="caption" fontWeight={700} sx={{ fontSize: "0.9rem", color: theme.palette.success.main }}>
                              {formatPercent(row.premium_pct)}
                            </Typography>
                          </Box>
                        </Grid>

                        <Grid item xs={6} sm="auto">
                          <Box sx={{ minWidth: 60 }}>
                            <Typography variant="caption" color="text.secondary" fontWeight={600} sx={{ display: "block", fontSize: "0.7rem", mb: 0.25 }}>
                              PoP
                            </Typography>
                            <Typography variant="caption" fontWeight={700} sx={{ fontSize: "0.9rem" }}>
                              {row.probability_of_profit}%
                            </Typography>
                          </Box>
                        </Grid>

                        <Grid item xs={6} sm="auto">
                          <Box sx={{ minWidth: 60 }}>
                            <Typography variant="caption" color="text.secondary" fontWeight={600} sx={{ display: "block", fontSize: "0.7rem", mb: 0.25 }}>
                              DAYS
                            </Typography>
                            <Typography variant="caption" fontWeight={700} sx={{ fontSize: "0.9rem" }}>
                              {row.days_to_expiration}d
                            </Typography>
                          </Box>
                        </Grid>

                        <Grid item xs={6} sm="auto">
                          <Box sx={{ minWidth: 60 }}>
                            <Typography variant="caption" color="text.secondary" fontWeight={600} sx={{ display: "block", fontSize: "0.7rem", mb: 0.25 }}>
                              TREND
                            </Typography>
                            <Box>{getTrendIcon(row.trend)}</Box>
                          </Box>
                        </Grid>

                        <Grid item xs={6} sm="auto">
                          <Box sx={{ minWidth: 70 }}>
                            <Typography variant="caption" color="text.secondary" fontWeight={600} sx={{ display: "block", fontSize: "0.7rem", mb: 0.25 }}>
                              ANNUAL
                            </Typography>
                            <Typography variant="caption" fontWeight={700} sx={{ fontSize: "0.9rem", color: theme.palette.success.main }}>
                              {formatPercent(row.expected_annual_return)}
                            </Typography>
                          </Box>
                        </Grid>
                      </Grid>
                    </Grid>
                  </Grid>
                </AccordionSummary>

                {/* DETAILS */}
                <AccordionDetails
                  sx={{
                    backgroundColor: "background.paper",
                    borderTop: `2px solid ${alpha(config.borderColor, 0.3)}`,
                    pt: 3,
                    pb: 3,
                    px: 3,
                  }}
                >
                  <Grid container spacing={3}>
                    {/* WHY SELL THIS CALL */}
                    <Grid item xs={12} sm={6} md={4} lg={3}>
                      <Box sx={{ mb: 2 }}>
                        <Typography variant="subtitle2" sx={{ fontWeight: 700, fontSize: "0.8rem", letterSpacing: "0.3px", textTransform: "uppercase" }}>
                          Why Sell
                        </Typography>
                      </Box>
                      <Box sx={{ display: "flex", flexDirection: "column", gap: 0.75 }}>
                        {getDecisionLogic(row).map((reason, idx) => (
                          <Typography key={idx} variant="caption" sx={{ fontWeight: 500, lineHeight: 1.4 }}>
                            {reason}
                          </Typography>
                        ))}
                      </Box>
                    </Grid>

                    {/* STRIKE OPTIONS */}
                    <Grid item xs={12} sm={6} md={4} lg={3}>
                      <Box sx={{ mb: 2 }}>
                        <Typography variant="subtitle2" sx={{ fontWeight: 700, fontSize: "0.8rem", letterSpacing: "0.3px", textTransform: "uppercase" }}>
                          Strike Options
                        </Typography>
                      </Box>
                      <DataField label="Conservative" value={row.conservative_strike} format="currency" />
                      <DataField label="✓ Recommended" value={row.recommended_strike} format="currency" color={theme.palette.success.main} />
                      <DataField label="Aggressive" value={row.aggressive_strike} format="currency" />
                      <DataField label="Secondary" value={row.secondary_strike} format="currency" />
                    </Grid>

                    {/* INCOME & PROFIT */}
                    <Grid item xs={12} sm={6} md={4} lg={3}>
                      <Box sx={{ mb: 2 }}>
                        <Typography variant="subtitle2" sx={{ fontWeight: 700, fontSize: "0.8rem", letterSpacing: "0.3px", textTransform: "uppercase" }}>
                          Income & Profit
                        </Typography>
                      </Box>
                      <DataField label="Premium per share" value={row.premium} format="currency" color={theme.palette.success.main} />
                      <DataField label="Max Profit" value={row.max_profit} format="currency" />
                      <DataField label="Max Profit %" value={row.max_profit_pct} format="percent" />
                      <DataField label="Max Loss" value={row.max_loss_amount} format="currency" color={theme.palette.error.main} />
                    </Grid>

                    {/* PROBABILITY & SAFETY */}
                    <Grid item xs={12} sm={6} md={4} lg={3}>
                      <Box sx={{ mb: 2 }}>
                        <Typography variant="subtitle2" sx={{ fontWeight: 700, fontSize: "0.8rem", letterSpacing: "0.3px", textTransform: "uppercase" }}>
                          Probability
                        </Typography>
                      </Box>
                      <DataField label="Probability of Profit" value={row.probability_of_profit} format="number" unit="%" />
                      <DataField label="Risk/Reward Ratio" value={row.risk_reward_ratio} format="number" />
                      <DataField label="IV Rank" value={row.iv_rank} format="number" unit="%" />
                      <DataField label="Liquidity Score" value={row.liquidity_score} format="number" unit="/100" />
                    </Grid>

                    {/* TECHNICAL SETUP */}
                    <Grid item xs={12} sm={6} md={4} lg={3}>
                      <Box sx={{ mb: 2 }}>
                        <Typography variant="subtitle2" sx={{ fontWeight: 700, fontSize: "0.8rem", letterSpacing: "0.3px", textTransform: "uppercase" }}>
                          Technical
                        </Typography>
                      </Box>
                      <DataField label="Trend" value={row.trend} />
                      <DataField label="RSI" value={row.rsi} format="number" />
                      <DataField label="Distance to Resistance" value={row.distance_to_resistance_pct} format="percent" />
                      <DataField label="SMA 50" value={row.sma_50} format="currency" />
                    </Grid>

                    {/* EXIT PLAN */}
                    <Grid item xs={12} sm={6} md={4} lg={3}>
                      <Box sx={{ mb: 2 }}>
                        <Typography variant="subtitle2" sx={{ fontWeight: 700, fontSize: "0.8rem", letterSpacing: "0.3px", textTransform: "uppercase" }}>
                          Exit Targets
                        </Typography>
                      </Box>
                      <DataField label="25% Profit" value={row.take_profit_25_target} format="currency" />
                      <DataField label="50% Profit ⭐" value={row.take_profit_50_target} format="currency" color={theme.palette.warning.main} />
                      <DataField label="75% Profit" value={row.take_profit_75_target} format="currency" />
                      <DataField label="Stop Loss" value={row.stop_loss_level} format="currency" color={theme.palette.error.main} />
                    </Grid>

                    {/* STOCK QUALITY */}
                    <Grid item xs={12} sm={6} md={4} lg={3}>
                      <Box sx={{ mb: 2 }}>
                        <Typography variant="subtitle2" sx={{ fontWeight: 700, fontSize: "0.8rem", letterSpacing: "0.3px", textTransform: "uppercase" }}>
                          Quality & Sentiment
                        </Typography>
                      </Box>
                      <DataField label="Composite Score" value={row.composite_score} format="number" unit="/100" />
                      <DataField label="Momentum Score" value={row.momentum_score} format="number" unit="/100" />
                      <DataField label="Analyst Bullish" value={row.analyst_bullish_ratio ? row.analyst_bullish_ratio * 100 : null} format="number" unit="%" />
                      <DataField label="Analyst Price Target" value={row.analyst_price_target} format="currency" />
                    </Grid>

                    {/* GREEKS & VOLATILITY */}
                    <Grid item xs={12} sm={6} md={4} lg={3}>
                      <Box sx={{ mb: 2 }}>
                        <Typography variant="subtitle2" sx={{ fontWeight: 700, fontSize: "0.8rem", letterSpacing: "0.3px", textTransform: "uppercase" }}>
                          Greeks & Vol
                        </Typography>
                      </Box>
                      <DataField label="Delta" value={row.delta} format="number" />
                      <DataField label="Theta" value={row.theta} format="number" />
                      <DataField label="Beta" value={row.beta} format="number" />
                      <DataField label="Confidence" value={row.entry_confidence} format="number" unit="/10" />
                    </Grid>

                    {/* TIMING & RISKS */}
                    <Grid item xs={12} sm={6} md={4} lg={3}>
                      <Box sx={{ mb: 2 }}>
                        <Typography variant="subtitle2" sx={{ fontWeight: 700, fontSize: "0.8rem", letterSpacing: "0.3px", textTransform: "uppercase" }}>
                          Timing & Risks
                        </Typography>
                      </Box>
                      <DataField label="Days to Expiration" value={row.days_to_expiration} format="number" unit="d" />
                      <DataField label="Days Profit Available" value={row.days_profit_available} format="number" unit="d" />
                      <DataField label="Days to Earnings" value={row.days_to_earnings} format="number" unit="d" />
                      <Typography variant="caption" sx={{ fontWeight: 600, mt: 1, display: "block" }}>
                        {row.low_liquidity_warning && "⚠️ Low Liquidity"}
                        {row.high_beta_warning && " ⚠️ High Beta"}
                        {!row.low_liquidity_warning && !row.high_beta_warning && "✓ Low Risk"}
                      </Typography>
                    </Grid>

                    {/* MARKET STRUCTURE & LIQUIDITY */}
                    <Grid item xs={12} sm={6} md={4} lg={3}>
                      <Box sx={{ mb: 2 }}>
                        <Typography variant="subtitle2" sx={{ fontWeight: 700, fontSize: "0.8rem", letterSpacing: "0.3px", textTransform: "uppercase" }}>
                          Market Structure
                        </Typography>
                      </Box>
                      <DataField label="Bid-Ask Spread" value={row.bid_ask_spread_pct} format="percent" />
                      <DataField label="Open Interest Rank" value={row.open_interest_rank} format="number" />
                      <DataField label="Implied Volatility" value={row.implied_volatility} format="percent" />
                      <DataField label="Avg Daily Premium" value={row.avg_daily_premium} format="currency" />
                    </Grid>

                    {/* OPPORTUNITY SCORING */}
                    <Grid item xs={12} sm={6} md={4} lg={3}>
                      <Box sx={{ mb: 2 }}>
                        <Typography variant="subtitle2" sx={{ fontWeight: 700, fontSize: "0.8rem", letterSpacing: "0.3px", textTransform: "uppercase" }}>
                          Opportunity Scores
                        </Typography>
                      </Box>
                      <DataField label="Opportunity Score" value={row.opportunity_score} format="number" unit="/100" color={row.opportunity_score >= 75 ? theme.palette.success.main : row.opportunity_score >= 50 ? theme.palette.warning.main : theme.palette.error.main} />
                      <DataField label="Timing Score" value={row.timing_score} format="number" unit="/100" />
                      <DataField label="Sell Now Score" value={row.sell_now_score} format="number" unit="/100" color={row.sell_now_score >= 75 ? theme.palette.success.main : theme.palette.warning.main} />
                      <DataField label="Strike Quality Score" value={row.strike_quality_score} format="number" unit="/100" />
                    </Grid>

                    {/* REGIME & RISK SCORING */}
                    <Grid item xs={12} sm={6} md={4} lg={3}>
                      <Box sx={{ mb: 2 }}>
                        <Typography variant="subtitle2" sx={{ fontWeight: 700, fontSize: "0.8rem", letterSpacing: "0.3px", textTransform: "uppercase" }}>
                          Market & Risk Regime
                        </Typography>
                      </Box>
                      <DataField label="Market Regime Score" value={row.market_regime_score} format="number" unit="/100" />
                      <DataField label="Vol Regime Score" value={row.vol_regime_score} format="number" unit="/100" />
                      <DataField label="Earnings Risk Score" value={row.earnings_risk_score} format="number" unit="/100" />
                      <DataField label="Execution Score" value={row.execution_score} format="number" unit="/100" />
                    </Grid>

                    {/* ENTRY & MANAGEMENT */}
                    <Grid item xs={12} sm={6} md={4} lg={3}>
                      <Box sx={{ mb: 2 }}>
                        <Typography variant="subtitle2" sx={{ fontWeight: 700, fontSize: "0.8rem", letterSpacing: "0.3px", textTransform: "uppercase" }}>
                          Entry & Management
                        </Typography>
                      </Box>
                      <Box sx={{ mb: 1 }}>
                        <Typography variant="caption" sx={{ color: "text.secondary", display: "block", mb: 0.5, fontWeight: 600 }}>
                          Entry Signal
                        </Typography>
                        <Typography variant="body2" sx={{ fontWeight: 600, color: "text.primary", fontSize: "0.95rem" }}>
                          {row.entry_signal}
                        </Typography>
                      </Box>
                      <DataField label="Entry Confidence" value={row.entry_confidence} format="number" unit="/10" />
                      <Box sx={{ mb: 1 }}>
                        <Typography variant="caption" sx={{ color: "text.secondary", display: "block", mb: 0.5, fontWeight: 600 }}>
                          Management Strategy
                        </Typography>
                        <Typography variant="body2" sx={{ fontWeight: 500, color: "text.primary", fontSize: "0.9rem", lineHeight: 1.4 }}>
                          {row.management_strategy || "—"}
                        </Typography>
                      </Box>
                    </Grid>

                    {/* RETURN & RISK METRICS */}
                    <Grid item xs={12} sm={6} md={4} lg={3}>
                      <Box sx={{ mb: 2 }}>
                        <Typography variant="subtitle2" sx={{ fontWeight: 700, fontSize: "0.8rem", letterSpacing: "0.3px", textTransform: "uppercase" }}>
                          Return & Risk
                        </Typography>
                      </Box>
                      <DataField label="Risk-Adjusted Return" value={row.risk_adjusted_return} format="percent" color={theme.palette.success.main} />
                      <DataField label="Max Loss %" value={row.max_loss_pct} format="percent" color={theme.palette.error.main} />
                      <DataField label="Avg Daily Premium" value={row.avg_daily_premium} format="currency" />
                      <DataField label="SMA 200" value={row.sma_200} format="currency" />
                    </Grid>

                    {/* ANALYST & MARKET SENTIMENT */}
                    <Grid item xs={12} sm={6} md={4} lg={3}>
                      <Box sx={{ mb: 2 }}>
                        <Typography variant="subtitle2" sx={{ fontWeight: 700, fontSize: "0.8rem", letterSpacing: "0.3px", textTransform: "uppercase" }}>
                          Analysts & Sentiment
                        </Typography>
                      </Box>
                      <DataField label="Analyst Count" value={row.analyst_count} format="number" />
                      <DataField label="Analyst Bullish %" value={row.analyst_bullish_ratio ? row.analyst_bullish_ratio * 100 : null} format="number" unit="%" />
                      <DataField label="Analyst Target" value={row.analyst_price_target} format="currency" />
                      <DataField label="Market Sentiment" value={row.market_sentiment} />
                    </Grid>

                    {/* TECHNICAL DEPTH */}
                    <Grid item xs={12} sm={6} md={4} lg={3}>
                      <Box sx={{ mb: 2 }}>
                        <Typography variant="subtitle2" sx={{ fontWeight: 700, fontSize: "0.8rem", letterSpacing: "0.3px", textTransform: "uppercase" }}>
                          Technical Depth
                        </Typography>
                      </Box>
                      <DataField label="Support Level" value={row.sma_200} format="currency" />
                      <DataField label="Resistance Level" value={row.resistance_level} format="currency" />
                      <DataField label="Distance to Resist" value={row.distance_to_resistance_pct} format="percent" />
                      <DataField label="SMA 50" value={row.sma_50} format="currency" />
                    </Grid>
                  </Grid>
                </AccordionDetails>
              </Accordion>
            );
          })}
        </Box>
      )}
    </Box>
  );
}

export default CoveredCallOpportunities;
