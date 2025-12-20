import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "../contexts/AuthContext";
import { useDocumentTitle } from "../hooks/useDocumentTitle";
import {
  Box,
  Button,
  Card,
  CardContent,
  CardHeader,
  CircularProgress,
  Container,
  Grid,
  Typography,
  useTheme,
  useMediaQuery,
} from "@mui/material";
import {
  LineChart,
  Line,
  AreaChart,
  Area,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  Legend,
  ComposedChart,
  ScatterChart,
  Scatter,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
} from "recharts";
import {
  TrendingUp,
  TrendingDown,
  ShowChart,
  Assessment,
  AccountBalance,
  Warning,
  CheckCircle,
  Info,
  Refresh,
  ArrowUpward,
  ArrowDownward,
} from "@mui/icons-material";
import {
  getPortfolioData,
} from "../services/api";
import ManualPositionsDialog from "../components/ManualPositionsDialog";
import ManualTradesDialog from "../components/ManualTradesDialog";

// ============ STAT CARD COMPONENT ============
const StatCard = ({ icon: Icon, label, value, unit = "", color = "primary", interpretation = "" }) => {
  const theme = useTheme();

  return (
    <Card
      sx={{
        height: "100%",
        background: theme.palette.mode === "dark"
          ? `linear-gradient(135deg, ${theme.palette.background.paper} 0%, ${theme.palette.background.default} 100%)`
          : `linear-gradient(135deg, #ffffff 0%, ${theme.palette.grey[50]} 100%)`,
        borderLeft: `4px solid ${theme.palette[color]?.main || theme.palette.primary.main}`,
        boxShadow: theme.palette.mode === "dark" ? "0 2px 8px rgba(0,0,0,0.3)" : "0 2px 4px rgba(0,0,0,0.05)",
        transition: "all 0.3s ease",
        "&:hover": {
          boxShadow: theme.palette.mode === "dark" ? "0 4px 12px rgba(0,0,0,0.4)" : "0 4px 8px rgba(0,0,0,0.1)",
          transform: "translateY(-2px)",
        },
      }}
    >
      <CardContent>
        <Box display="flex" justifyContent="space-between" alignItems="flex-start" mb={1}>
          <Icon sx={{ color: `${theme.palette[color]?.main || theme.palette.primary.main}`, fontSize: 28 }} />
        </Box>
        <Typography variant="h4" sx={{ fontWeight: 700, mb: 0.5 }}>
          {value}
          {unit && <span style={{ fontSize: "0.6em", marginLeft: "4px" }}>{unit}</span>}
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
          {label}
        </Typography>
        {interpretation && (
          <Typography variant="caption" sx={{ color: theme.palette.text.secondary, display: "block", fontStyle: "italic" }}>
            {interpretation}
          </Typography>
        )}
      </CardContent>
    </Card>
  );
};

// ============ SANITIZATION HELPERS ============
// Filter out unreasonable metric values that indicate data issues
const isSaneMetricValue = (value) => {
  if (value === null || value === undefined) return true;
  // Unreasonably high returns (>10000%) indicate calculation errors
  if (Math.abs(value) > 10000) return false;
  return true;
};

const sanitizeMetricValue = (value, unit = "%") => {
  if (value === null || value === undefined) return "N/A";
  if (!isSaneMetricValue(value)) return "N/A";
  return value;
};

// ============ METRIC BOX COMPONENT ============
const MetricBox = ({ label, value, unit = "" }) => {
  const theme = useTheme();
  return (
    <Box sx={{ p: 2, backgroundColor: theme.palette.background.default, borderRadius: 1 }}>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
        {label}
      </Typography>
      <Typography variant="h6" sx={{ fontWeight: 600 }}>
        {value}
        {unit && <span style={{ fontSize: "0.7em", marginLeft: "4px" }}>{unit}</span>}
      </Typography>
    </Box>
  );
};

// ============ MAIN PORTFOLIO DASHBOARD ============
export default function PortfolioDashboard() {
  useDocumentTitle("Portfolio Dashboard");
  const { user } = useAuth();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("md"));

  // Fetch comprehensive portfolio data from CONSOLIDATED endpoint
  // Returns: account, holdings, metrics (performance, risk, allocation, analysis), charts
  const { data: portfolioData, isLoading: isLoading, refetch: refetchPortfolio } = useQuery({
    queryKey: ["portfolioData"],
    queryFn: () => getPortfolioData(),
    staleTime: 60000,
  });

  // Map portfolio response to expected data structure
  // ENDPOINT FORMAT: { summary, positions, daily_returns, metadata }
  const summary = portfolioData?.data?.summary || {};
  const positions = portfolioData?.data?.positions || [];
  const dailyReturns = portfolioData?.data?.daily_returns || [];
  const metadata = portfolioData?.data?.metadata || {};

  // Diagnostic logging for metrics flow
  console.log('📊 Portfolio Summary Data:', {
    portfolio_value: summary.portfolio_value,
    total_pnl: summary.total_pnl,
    total_return: summary.total_return,
    return_1m: summary.return_1m,
    return_1y: summary.return_1y,
    volatility: summary.volatility_annualized,
    sharpe_ratio: summary.sharpe_ratio,
    holdings_count: summary.holdings_count
  });
  console.log('📈 Positions:', positions.length, 'holdings');

  // Wrap in metricsData structure for consistency with rest of component
  const metricsData = {
    data: {
      summary: {
        // Portfolio value metrics
        portfolio_value: summary.portfolio_value,
        total_cost: summary.total_cost,
        total_pnl: summary.total_pnl || null,
        total_pnl_percent: summary.total_pnl_percent || null,
        total_return: summary.total_return || null,
        holdings_count: summary.holdings_count || 0,

        // Risk metrics
        volatility_annualized: summary.volatility_annualized,
        sharpe_ratio: summary.sharpe_ratio,
        sortino_ratio: summary.sortino_ratio,
        calmar_ratio: summary.calmar_ratio,
        max_drawdown: summary.max_drawdown,
        beta: summary.beta,

        // Return periods
        return_1m: summary.return_1m,
        return_3m: summary.return_3m,
        return_6m: summary.return_6m,
        return_1y: summary.return_1y,
        return_3y: summary.return_3y,
        return_rolling_1y: summary.return_rolling_1y,
        ytd_return: summary.ytd_return,

        // Daily performance
        win_rate: summary.win_rate,
        best_day_gain: summary.best_day_gain,
        worst_day_loss: summary.worst_day_loss,
        avg_daily_return: summary.avg_daily_return,

        // Concentration
        herfindahl_index: summary.herfindahl_index,
        effective_n: summary.effective_n,
        diversification_ratio: summary.diversification_ratio,
        top_1_weight: summary.top_1_weight,
        top_5_weight: summary.top_5_weight,
        top_10_weight: summary.top_10_weight,
      },
      positions: positions,
      daily_returns: dailyReturns,
      benchmark_metrics: summary,
      metadata: metadata
    }
  };

  const metricsLoading = isLoading;
  const refetchMetrics = refetchPortfolio;

  // Alpaca sync state
  const [isSyncing, setIsSyncing] = useState(false);
  const [syncStatus, setSyncStatus] = useState(null);


  // Handle unified portfolio sync (Alpaca + Manual + Trades)
  const handleAlpacaSync = async () => {
    setIsSyncing(true);
    setSyncStatus(null);
    try {
      // First import from Alpaca
      console.log("📡 Step 1: Importing from Alpaca...");
      const alpacaResponse = await fetch("/api/portfolio/import/alpaca", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": "Bearer dev-bypass-token"
        },
      });

      const alpacaResult = await alpacaResponse.json();
      console.log("✅ Alpaca import complete:", alpacaResult);

      // Then consolidate all data sources (Alpaca + Manual + Trades)
      console.log("🔄 Step 2: Consolidating from all sources...");
      const consolidateResponse = await fetch("/api/portfolio/sync", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": "Bearer dev-bypass-token"
        },
      });

      const consolidateResult = await consolidateResponse.json();
      console.log("✅ Portfolio consolidated:", consolidateResult);

      if (consolidateResult.success) {
        const { consolidated_holdings, total_value, sources_synced } = consolidateResult.data;
        const message = `✅ Portfolio synced! ${consolidated_holdings} holdings from Alpaca (${sources_synced.alpaca_positions}), Manual (${sources_synced.manual_positions}), and Trades (${sources_synced.from_trades}) | Total Value: $${total_value.toLocaleString()}`;
        setSyncStatus({ type: "success", message });
        // Refetch all queries to show updated data
        refetchMetrics();
      } else {
        setSyncStatus({ type: "error", message: `❌ Sync failed: ${consolidateResult.error}` });
      }
    } catch (error) {
      setSyncStatus({ type: "error", message: `❌ Sync error: ${error.message}` });
    } finally {
      setIsSyncing(false);
    }
  };

  // Signals (if available)
  const signals = portfolioData?.data?.signals || [];
  const performanceChartData = useMemo(() => {
    return metricsData?.data?.daily_returns?.slice(-252).map((val, idx) => ({
      date: idx,
      return: val,
      cumulative: val,
    })) || [];
  }, [metricsData]);

  // Compute sector data from positions
  const sectorData = useMemo(() => {
    if (!positions || positions.length === 0) {
      return [];
    }

    const sectorMap = {};
    let totalValue = 0;

    // Aggregate positions by sector
    positions.forEach((pos) => {
      const sector = pos.sector || 'Other';
      const value = pos.market_value_dollars != null ? Math.abs(pos.market_value_dollars) : null;
      const return_pct = pos.return_percent != null ? pos.return_percent : null;

      if (!sectorMap[sector]) {
        sectorMap[sector] = { weight: 0, return: 0, count: 0 };
      }
      // Only accumulate if values are not null (per RULES.md - no fake data)
      if (value != null) {
        sectorMap[sector].weight += value;
        totalValue += value;
      }
      if (return_pct != null) {
        sectorMap[sector].return += return_pct;
        sectorMap[sector].count += 1;
      } else {
        sectorMap[sector].count += 1; // Still count the position even if return is missing
      }
    });

    // Convert to chart data
    return Object.entries(sectorMap)
      .map(([sector, data]) => ({
        sector,
        weight: totalValue > 0 ? (data.weight / totalValue) * 100 : 0,
        return: data.count > 0 ? data.return / data.count : 0,
      }))
      .sort((a, b) => b.weight - a.weight);
  }, [positions]);

  // Extract SPY benchmark metrics from real performance data
  const benchmarkData = useMemo(() => {
    const metrics = metricsData?.data?.benchmark_metrics;
    if (!metrics) {
      return { return: null, risk: null };
    }
    return {
      // Use annual return (1Y) as primary, fallback to shorter periods
      return: metrics.return_1y || metrics.return_6m || metrics.return_3m || metrics.return_1m || null,
      risk: metrics.volatility || null,
      volatility: metrics.volatility,
      sharpeRatio: metrics.sharpe_ratio,
      alpha: metrics.alpha,
      outperformance: metrics.outperformance,
      correlation: metrics.correlation_with_spy,
    };
  }, [metricsData]);

  // ============ MAIN RENDER ============
  if (metricsLoading) {
    return (
      <Container maxWidth="lg" sx={{ py: 4 }}>
        <Box display="flex" justifyContent="center" alignItems="center" minHeight="400px">
          <CircularProgress />
        </Box>
      </Container>
    );
  }

  const hasData = (Object.values(summary).some(v => v !== 0 && v !== undefined)) || (positions && positions.length > 0);

  return (
    <Container maxWidth="lg" sx={{ py: 4 }}>
      {/* Header */}
      <Box sx={{ mb: 4 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 2 }}>
          <Box>
            <Typography variant="h4" sx={{ fontWeight: 700, mb: 1 }}>
              Portfolio Dashboard
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Professional-grade portfolio analytics - All metrics on one page
            </Typography>
          </Box>
          <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
            <Button
              variant="contained"
              startIcon={<Refresh />}
              onClick={handleAlpacaSync}
              disabled={isSyncing}
              sx={{
                backgroundColor: (theme) => theme.palette.primary.main,
                '&:hover': { backgroundColor: (theme) => theme.palette.primary.dark },
                '&:disabled': { opacity: 0.6 }
              }}
            >
              {isSyncing ? 'Syncing...' : 'Sync with Alpaca'}
            </Button>
            <ManualPositionsDialog />
            <ManualTradesDialog />
          </Box>
        </Box>

        {/* Sync Status Message */}
        {syncStatus && (
          <Card sx={{
            p: 2,
            mb: 2,
            backgroundColor: syncStatus.type === 'success'
              ? (theme) => theme.palette.success.light
              : (theme) => theme.palette.error.light,
            border: `1px solid ${syncStatus.type === 'success' ? '#4caf50' : '#f44336'}`
          }}>
            <Typography variant="body2" sx={{ color: syncStatus.type === 'success' ? '#2e7d32' : '#c62828' }}>
              {syncStatus.message}
            </Typography>
          </Card>
        )}
      </Box>

      {/* No Data State */}
      {!hasData && (
        <Card sx={{ p: 4, mb: 4 }}>
          <Typography align="center" color="text.secondary">
            No portfolio data available. Add holdings to see comprehensive metrics.
          </Typography>
        </Card>
      )}

      {hasData && (
        <>
          {/* ============ SECTION 1: EXECUTIVE SUMMARY & TOP HOLDINGS ============ */}
          <Box sx={{ mb: 4 }}>
            <Typography variant="h5" sx={{ fontWeight: 700, mb: 3, display: 'flex', alignItems: 'center', gap: 1 }}>
              <Assessment sx={{ color: 'primary.main' }} /> Executive Summary & Top Holdings
            </Typography>

            {/* KPI Cards - Show only metrics with real data */}
            <Grid container spacing={3} sx={{ mb: 4 }}>
              {/* Portfolio Value - Real data from Alpaca */}
              <Grid item xs={12} sm={6} md={3}>
                <StatCard
                  icon={TrendingUp}
                  label="Portfolio Value"
                  value={summary.portfolio_value != null ? `$${summary.portfolio_value.toLocaleString(undefined, {maximumFractionDigits: 2})}` : "N/A"}
                  unit=""
                  color="success"
                />
              </Grid>

              {/* Total P&L - Real data from calculations */}
              <Grid item xs={12} sm={6} md={3}>
                <StatCard
                  icon={Assessment}
                  label="Total P&L"
                  value={summary.total_pnl != null ? `$${summary.total_pnl.toLocaleString(undefined, {maximumFractionDigits: 2})}` : "N/A"}
                  unit=""
                  color={summary.total_pnl >= 0 ? "success" : "error"}
                />
              </Grid>

              {/* P&L % - Real data (return %) */}
              <Grid item xs={12} sm={6} md={3}>
                <StatCard
                  icon={ShowChart}
                  label="Return %"
                  value={summary.total_pnl_percent != null ? summary.total_pnl_percent.toFixed(2) : "N/A"}
                  unit="%"
                  color={summary.total_pnl_percent >= 0 ? "success" : "error"}
                />
              </Grid>

              {/* Holdings Count - Real data (position count) */}
              <Grid item xs={12} sm={6} md={3}>
                <StatCard
                  icon={Warning}
                  label="Holdings"
                  value={summary.holdings_count != null ? summary.holdings_count : "N/A"}
                  unit="positions"
                  color="info"
                />
              </Grid>
            </Grid>

            {/* All Holdings Pie Chart */}
            <Card sx={{ mb: 4 }}>
              <CardHeader title="Portfolio Holdings Distribution (All Positions)" />
              <CardContent>
                <ResponsiveContainer width="100%" height={400}>
                  <PieChart>
                    <Pie
                      data={positions
                        .filter(p => p.weight_percent !== null && p.weight_percent !== undefined && parseFloat(p.weight_percent) > 0)
                        .map(p => ({
                          name: p.symbol,
                          value: parseFloat(p.weight_percent),
                        }))}
                      cx="50%"
                      cy="50%"
                      labelLine={false}
                      label={({ name, value }) => value > 1 ? `${name}: ${value.toFixed(1)}%` : name}
                      outerRadius={110}
                      fill="#8884d8"
                      dataKey="value"
                    >
                      {/* Dynamic color palette for all positions */}
                      {positions.map((p, idx) => {
                        const colors = ['#1976d2', '#43a047', '#ffb300', '#8e24aa', '#e53935', '#00acc1', '#6a1b9a', '#0277bd', '#ef6c00', '#d32f2f', '#1e88e5', '#43a047', '#fb8c00', '#5e35b1', '#00838f'];
                        return <Cell key={`cell-${idx}`} fill={colors[idx % colors.length]} />;
                      })}
                    </Pie>
                    <RechartsTooltip formatter={(value) => `${value != null ? value.toFixed(2) : '0.00'}%`} />
                  </PieChart>
                </ResponsiveContainer>
                {positions.length > 5 && (
                  <div style={{ marginTop: 16, fontSize: '0.875rem', color: '#666' }}>
                    <p>Showing all {positions.length} positions • Positions &lt; 1% shown by symbol only</p>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Holdings Performance & Gains/Losses */}
            <Card sx={{ mb: 4 }}>
              <CardHeader
                title="Holdings Performance & Gains/Losses"
                subheader="Current P&L by position"
              />
              <CardContent>
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart data={positions.slice(0, 15).map((pos, idx) => ({
                    name: pos.symbol,
                    gain: pos.gain_loss_dollars !== null && pos.gain_loss_dollars !== undefined ? parseFloat(pos.gain_loss_dollars) : null,
                    value: pos.market_value_dollars !== null && pos.market_value_dollars !== undefined ? parseFloat(pos.market_value_dollars) : null,
                  }))} layout="vertical" margin={{ top: 5, right: 30, left: 80, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis type="number" />
                    <YAxis dataKey="name" type="category" width={75} />
                    <RechartsTooltip
                      formatter={(value) => `$${value?.toFixed(2) || '0.00'}`}
                      contentStyle={{ backgroundColor: '#fff', border: '1px solid #ccc' }}
                    />
                    <Legend />
                    <Bar dataKey="gain" fill="#43a047" name="Gain/Loss ($)" radius={[0, 8, 8, 0]} />
                    <Bar dataKey="value" fill="#1976d2" name="Position Value ($)" radius={[0, 8, 8, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          </Box>

          {/* Trading Signals Section */}
          {signals && signals.length > 0 && (
            <Card sx={{ mb: 4 }}>
              <CardHeader
                title="Trading Signals"
                subheader={`Latest signal recommendations - ${signals.length} signals`}
              />
              <CardContent>
                <Grid container spacing={2}>
                  {signals.slice(0, 10).map((signal, idx) => (
                    <Grid item xs={12} sm={6} md={4} lg={3} key={idx}>
                      <Box sx={{
                        p: 2,
                        backgroundColor: (theme) => theme.palette.mode === 'dark' ? '#1e1e1e' : '#f5f5f5',
                        borderRadius: 1,
                        border: '1px solid',
                        borderColor: (theme) => theme.palette.mode === 'dark' ? '#333' : '#ddd',
                      }}>
                        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
                          <Typography variant="h6" sx={{ fontWeight: 600 }}>
                            {signal.symbol || signal.ticker}
                          </Typography>
                        </Box>
                        {signal.score && (
                          <Typography variant="caption" color="text.secondary">
                            Score: {(signal.score * 100).toFixed(1)}%
                          </Typography>
                        )}
                        {signal.timestamp && (
                          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
                            {new Date(signal.timestamp).toLocaleDateString()}
                          </Typography>
                        )}
                      </Box>
                    </Grid>
                  ))}
                </Grid>
                {signals.length === 0 && (
                  <Typography variant="body2" color="text.secondary" align="center" sx={{ py: 2 }}>
                    No trading signals available at this time.
                  </Typography>
                )}
              </CardContent>
            </Card>
          )}

          {/* ============ SECTION 2: RETURNS OVERVIEW ============ */}
          <Box sx={{ mb: 4, mt: 6 }}>
            <Typography variant="h5" sx={{ fontWeight: 700, mb: 3, display: 'flex', alignItems: 'center', gap: 1 }}>
              <TrendingUp sx={{ color: 'success.main' }} /> Performance Metrics & Analysis
            </Typography>

            {/* Performance Metrics KPI Cards - Core Returns */}
            <Card sx={{ mb: 4 }}>
              <CardHeader title="Core Performance Metrics" subheader="Total returns across different timeframes" />
              <CardContent>
                <Grid container spacing={2}>
                  <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Total Return" value={summary.total_return != null ? summary.total_return.toFixed(2) : "N/A"} unit="%" /></Grid>
                  <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="1Y Return" value={summary.return_1y != null ? summary.return_1y.toFixed(2) : "N/A"} unit="%" /></Grid>
                  <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="3Y Return" value={summary.return_3y != null ? summary.return_3y.toFixed(2) : "N/A"} unit="%" /></Grid>
                  <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="YTD Return" value={summary.ytd_return != null ? summary.ytd_return.toFixed(2) : "N/A"} unit="%" /></Grid>
                  <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Portfolio Value" value={summary.portfolio_value != null ? `$${(summary.portfolio_value / 1000).toFixed(1)}` : "N/A"} unit="K" /></Grid>
                  <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Holdings Count" value={positions.length || "0"} unit="" /></Grid>
                </Grid>
              </CardContent>
            </Card>

            {/* Rolling Period Returns - Metrics + Chart Together */}
            <Card sx={{ mb: 4 }}>
              <CardHeader title="Rolling Period Returns" subheader="Returns across multiple time horizons" />
              <CardContent>
                {/* Metrics */}
                <Grid container spacing={2} sx={{ mb: 3 }}>
                  <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="1M" value={summary.return_1m != null ? summary.return_1m.toFixed(2) : "N/A"} unit="%" /></Grid>
                  <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="3M" value={summary.return_3m != null ? summary.return_3m.toFixed(2) : "N/A"} unit="%" /></Grid>
                  <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="6M" value={summary.return_6m != null ? summary.return_6m.toFixed(2) : "N/A"} unit="%" /></Grid>
                  <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="1Y Rolling" value={summary.return_rolling_1y != null ? summary.return_rolling_1y.toFixed(2) : "N/A"} unit="%" /></Grid>
                  <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="YTD" value={summary.ytd_return != null ? summary.ytd_return.toFixed(2) : "N/A"} unit="%" /></Grid>
                  <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Daily Volatility" value={summary.volatility_annualized != null ? (summary.volatility_annualized / Math.sqrt(252)).toFixed(3) : "N/A"} unit="%" /></Grid>
                </Grid>

                {/* Rolling Period Chart */}
                <ResponsiveContainer width="100%" height={320}>
                  <LineChart data={[
                    { period: '1M', return: summary.return_1m },
                    { period: '3M', return: summary.return_3m },
                    { period: '6M', return: summary.return_6m },
                    { period: '1Y', return: summary.return_rolling_1y },
                    { period: 'YTD', return: summary.ytd_return },
                  ]}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="period" />
                    <YAxis label={{ value: 'Return (%)', angle: -90, position: 'insideLeft' }} />
                    <RechartsTooltip formatter={(value) => `${value?.toFixed(2)}%`} />
                    <Legend />
                    <Line type="monotone" dataKey="return" stroke="#1976d2" strokeWidth={2.5} dot={{ fill: '#1976d2', r: 6 }} name="Period Return" />
                  </LineChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>

            {/* Cumulative Performance vs Benchmark */}
            <Card sx={{ mb: 4 }}>
              <CardHeader
                title="Cumulative Performance vs SPY"
                subheader="Portfolio growth compared to S&P 500 benchmark"
              />
              <CardContent>
                <ResponsiveContainer width="100%" height={350}>
                  <LineChart
                    data={performanceChartData.length > 0 ? performanceChartData : [
                      { date: 0, portfolio: 10000, spy: 10000 },
                      { date: 252, portfolio: 12000, spy: 11500 },
                    ]}
                  >
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="date" label={{ value: 'Trading Days', position: 'insideBottomRight', offset: -10 }} />
                    <YAxis label={{ value: 'Value ($)', angle: -90, position: 'insideLeft' }} />
                    <RechartsTooltip
                      formatter={(value) => `$${value?.toFixed(0) || '0'}`}
                      labelFormatter={(label) => `Day ${label}`}
                    />
                    <Legend />
                    <Line
                      type="monotone"
                      dataKey="portfolio"
                      stroke="#1976d2"
                      strokeWidth={2.5}
                      dot={false}
                      name="Portfolio"
                      isAnimationActive={false}
                    />
                    <Line
                      type="monotone"
                      dataKey="spy"
                      stroke="#43a047"
                      strokeWidth={2}
                      dot={false}
                      name="SPY Benchmark"
                      strokeDasharray="5 5"
                      isAnimationActive={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>

            {/* SPY BENCHMARK COMPARISON - Metrics + Chart */}
            <Card sx={{ mb: 4 }}>
              <CardHeader
                title="SPY Benchmark Comparison"
                subheader="How your portfolio compares to the S&P 500"
              />
              <CardContent>
                {/* Comparison Metrics */}
                <Grid container spacing={3} sx={{ mb: 3 }}>
                  <Grid item xs={12} sm={6} md={3}>
                    <Box sx={{ p: 2, backgroundColor: (theme) => theme.palette.background.default, borderRadius: 1 }}>
                      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
                        Portfolio Return
                      </Typography>
                      <Typography variant="h6" sx={{ fontWeight: 600, color: summary.total_return !== null && summary.total_return !== undefined ? (summary.total_return >= 0 ? 'success.main' : 'error.main') : 'text.secondary' }}>
                        {summary.total_return !== null && summary.total_return !== undefined ? `${summary.total_return.toFixed(2)}%` : "N/A"}
                      </Typography>
                    </Box>
                  </Grid>
                  <Grid item xs={12} sm={6} md={3}>
                    <Box sx={{ p: 2, backgroundColor: (theme) => theme.palette.background.default, borderRadius: 1 }}>
                      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
                        SPY Return
                      </Typography>
                      <Typography variant="h6" sx={{ fontWeight: 600, color: 'info.main' }}>
                        {benchmarkData.return !== null && benchmarkData.return !== undefined ? `${benchmarkData.return.toFixed(2)}%` : "N/A"}
                      </Typography>
                    </Box>
                  </Grid>
                  <Grid item xs={12} sm={6} md={3}>
                    <Box sx={{ p: 2, backgroundColor: (theme) => theme.palette.background.default, borderRadius: 1 }}>
                      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
                        Outperformance
                      </Typography>
                      {summary.total_return !== null && summary.total_return !== undefined && benchmarkData?.return !== null && benchmarkData?.return !== undefined ? (
                        <Typography variant="h6" sx={{ fontWeight: 600, color: (summary.total_return - benchmarkData.return) >= 0 ? 'success.main' : 'error.main' }}>
                          {(summary.total_return - benchmarkData.return).toFixed(2)}%
                        </Typography>
                      ) : (
                        <Typography variant="h6" sx={{ fontWeight: 600, color: 'text.secondary' }}>
                          N/A
                        </Typography>
                      )}
                    </Box>
                  </Grid>
                  <Grid item xs={12} sm={6} md={3}>
                    <Box sx={{ p: 2, backgroundColor: (theme) => theme.palette.background.default, borderRadius: 1 }}>
                      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
                        Correlation
                      </Typography>
                      <Typography variant="h6" sx={{ fontWeight: 600 }}>
                        {summary.correlation_with_spy !== null && summary.correlation_with_spy !== undefined ? summary.correlation_with_spy.toFixed(2) : "—"}
                      </Typography>
                    </Box>
                  </Grid>
                </Grid>

                {/* Risk vs Return Comparison Chart */}
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart
                    data={[
                      {
                        name: 'Portfolio',
                        return: summary.total_return,
                        risk: summary.volatility_annualized
                      },
                      {
                        name: 'SPY',
                        return: benchmarkData?.return,
                        risk: benchmarkData?.risk
                      },
                    ]}
                  >
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="name" />
                    <YAxis yAxisId="left" label={{ value: 'Return (%)', angle: -90, position: 'insideLeft' }} />
                    <YAxis yAxisId="right" orientation="right" label={{ value: 'Volatility (%)', angle: 90, position: 'insideRight' }} />
                    <RechartsTooltip />
                    <Legend />
                    <Bar yAxisId="left" dataKey="return" fill="#1976d2" name="Total Return %" radius={[8, 8, 0, 0]} />
                    <Bar yAxisId="right" dataKey="risk" fill="#ff9800" name="Volatility %" radius={[8, 8, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>

                <Typography variant="body2" sx={{ mt: 3, p: 2, backgroundColor: (theme) => theme.palette.mode === 'dark' ? 'rgba(25, 118, 210, 0.1)' : 'rgba(25, 118, 210, 0.05)', borderRadius: 1 }}>
                  <strong>Analysis:</strong> {
                    summary.correlation_with_spy > 0.8 ? '🔗 Your portfolio moves closely with the market (High correlation)' :
                    summary.correlation_with_spy > 0.5 ? '↔️ Moderate correlation with the market' :
                    '🔀 Low correlation - Good diversification from the broad market'
                  }. Your beta of {summary.beta?.toFixed(2) || '1.0'} means {
                    summary.beta > 1.2 ? 'your portfolio is MORE volatile than the market.' :
                    summary.beta < 0.8 ? 'your portfolio is LESS volatile than the market.' :
                    'your portfolio moves roughly with the market.'
                  }
                </Typography>
              </CardContent>
            </Card>

            {/* Return Attribution & Daily Performance - Metrics + Chart */}
            <Card sx={{ mb: 4 }}>
              <CardHeader title="Daily Performance Impact" subheader="Win rate, best/worst days, and daily volatility" />
              <CardContent>
                {/* Metrics */}
                <Grid container spacing={2} sx={{ mb: 3 }}>
                  <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Win Rate" value={summary.win_rate !== null && summary.win_rate !== undefined ? summary.win_rate.toFixed(1) : 'N/A'} unit="%" /></Grid>
                  <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Best Day" value={summary.best_day_gain !== null && summary.best_day_gain !== undefined ? summary.best_day_gain.toFixed(2) : 'N/A'} unit="%" /></Grid>
                  <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Worst Day" value={summary.worst_day_loss !== null && summary.worst_day_loss !== undefined ? summary.worst_day_loss.toFixed(2) : 'N/A'} unit="%" /></Grid>
                  <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Top 5 Days Impact" value={summary.top_5_days_contribution !== null && summary.top_5_days_contribution !== undefined ? summary.top_5_days_contribution.toFixed(2) : 'N/A'} unit="%" /></Grid>
                  <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Positive Days" value={summary.win_rate !== null && summary.win_rate !== undefined ? summary.win_rate.toFixed(1) : 'N/A'} unit="%" /></Grid>
                  <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Avg Daily Vol" value={summary.volatility_annualized !== null && summary.volatility_annualized !== undefined ? (summary.volatility_annualized / Math.sqrt(252)).toFixed(3) : 'N/A'} unit="%" /></Grid>
                </Grid>

                {/* Daily Performance Chart */}
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart data={[
                    ...(summary.win_rate !== null && summary.win_rate !== undefined ? [{ metric: 'Win Rate', value: summary.win_rate }] : []),
                    ...(summary.best_day_gain !== null && summary.best_day_gain !== undefined ? [{ metric: 'Best Day', value: summary.best_day_gain }] : []),
                    ...(summary.worst_day_loss !== null && summary.worst_day_loss !== undefined ? [{ metric: 'Worst Day', value: Math.abs(summary.worst_day_loss) }] : []),
                    ...(summary.top_5_days_contribution !== null && summary.top_5_days_contribution !== undefined ? [{ metric: 'Top 5 Days', value: summary.top_5_days_contribution }] : []),
                  ]}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="metric" />
                    <YAxis label={{ value: 'Return (%)', angle: -90, position: 'insideLeft' }} />
                    <RechartsTooltip formatter={(value) => `${value?.toFixed(2)}%`} />
                    <Bar dataKey="value" fill="#43a047" name="Value" radius={[8, 8, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>

            {/* Relative Performance vs Benchmark - Alpha, Beta, Information Ratio */}
            <Card sx={{ mb: 4 }}>
              <CardHeader title="Relative Performance Metrics" subheader="How you're tracking against SPY in detail" />
              <CardContent>
                <Grid container spacing={2}>
                  <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Tracking Error" value={summary.tracking_error !== null && summary.tracking_error !== undefined ? summary.tracking_error.toFixed(4) : 'N/A'} unit="" /></Grid>
                  <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Active Return" value={summary.active_return !== null && summary.active_return !== undefined ? summary.active_return.toFixed(2) : 'N/A'} unit="%" /></Grid>
                  <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Information Ratio" value={summary.information_ratio !== null && summary.information_ratio !== undefined ? summary.information_ratio.toFixed(2) : 'N/A'} unit="" /></Grid>
                  <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Rel Volatility" value={summary.relative_volatility !== null && summary.relative_volatility !== undefined ? summary.relative_volatility.toFixed(2) : 'N/A'} unit="" /></Grid>
                  <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Beta vs SPY" value={summary.beta !== null && summary.beta !== undefined ? summary.beta.toFixed(2) : 'N/A'} unit="" /></Grid>
                  <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Alpha" value={summary.alpha !== null && summary.alpha !== undefined ? summary.alpha.toFixed(2) : 'N/A'} unit="%" /></Grid>
                </Grid>
              </CardContent>
            </Card>
          </Box>

          {/* ============ SECTION 3: RISK METRICS & ANALYSIS ============ */}
          <Box sx={{ mb: 4, mt: 6 }}>
            <Typography variant="h5" sx={{ fontWeight: 700, mb: 3, display: 'flex', alignItems: 'center', gap: 1 }}>
              <Warning sx={{ color: 'error.main' }} /> Risk Metrics & Quality Indicators
            </Typography>

            {/* Volatility & Risk KPIs */}
            <Card sx={{ mb: 4 }}>
              <CardHeader title="Volatility & Risk Metrics" subheader="Core risk indicators for your portfolio" />
              <CardContent>
                <Grid container spacing={2} sx={{ mb: 3 }}>
                  <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Volatility" value={summary.volatility_annualized?.toFixed(2) || "—"} unit="%" /></Grid>
                  <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Downside Dev" value={summary.downside_deviation?.toFixed(2) || "—"} unit="%" /></Grid>
                  <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Beta vs SPY" value={summary.beta?.toFixed(2) || "—"} unit="" /></Grid>
                  <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Max Drawdown" value={summary.max_drawdown?.toFixed(2) || "—"} unit="%" /></Grid>
                  <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Return/Risk" value={summary.return_risk_ratio?.toFixed(2) || "—"} unit="" /></Grid>
                  <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Correlation SPY" value={summary.correlation_with_spy !== null && summary.correlation_with_spy !== undefined ? summary.correlation_with_spy.toFixed(2) : "—"} unit="" /></Grid>
                </Grid>
              </CardContent>
            </Card>

            {/* Risk-Adjusted Return Ratios - Metrics + Chart */}
            <Card sx={{ mb: 4 }}>
              <CardHeader title="Risk-Adjusted Return Ratios" subheader="Sharpe, Sortino, Calmar & Information ratios" />
              <CardContent>
                {/* Metrics */}
                <Grid container spacing={2} sx={{ mb: 3 }}>
                  <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Sharpe Ratio" value={summary.sharpe_ratio?.toFixed(3) || "—"} unit="" /></Grid>
                  <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Sortino Ratio" value={summary.sortino_ratio?.toFixed(3) || "—"} unit="" /></Grid>
                  <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Calmar Ratio" value={summary.calmar_ratio?.toFixed(3) || "—"} unit="" /></Grid>
                  <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Treynor Ratio" value={summary.treynor_ratio?.toFixed(3) || "—"} unit="%" /></Grid>
                  <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Information Ratio" value={summary.information_ratio?.toFixed(2) || "—"} unit="" /></Grid>
                  <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Alpha" value={summary.alpha?.toFixed(2) || "—"} unit="%" /></Grid>
                </Grid>

                {/* Risk-Adjusted Ratios Chart */}
                <ResponsiveContainer width="100%" height={320}>
                  <BarChart data={[
                    { metric: 'Sharpe', value: (summary.sharpe_ratio || 0) * 2 },
                    { metric: 'Sortino', value: (summary.sortino_ratio || 0) * 2 },
                    { metric: 'Calmar', value: (summary.calmar_ratio || 0) * 10 },
                    { metric: 'Info', value: (summary.information_ratio || 0) * 5 },
                  ]}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="metric" />
                    <YAxis label={{ value: 'Ratio Value (normalized)', angle: -90, position: 'insideLeft' }} />
                    <RechartsTooltip formatter={(value) => `${value?.toFixed(3)}`} />
                    <Bar dataKey="value" fill="#1976d2" name="Ratio" radius={[8, 8, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>

            {/* Drawdown Analysis - Metrics + Chart */}
            <Card sx={{ mb: 4 }}>
              <CardHeader title="Drawdown & Recovery" subheader="Portfolio drawdown depth and recovery time" />
              <CardContent>
                {/* Metrics */}
                <Grid container spacing={2} sx={{ mb: 3 }}>
                  <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Max Drawdown" value={summary.max_drawdown?.toFixed(2) || "0.00"} unit="%" /></Grid>
                  <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Current DD" value={summary.current_drawdown?.toFixed(2) || "0.00"} unit="%" /></Grid>
                  <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Avg Drawdown" value={summary.avg_drawdown?.toFixed(2) || "0.00"} unit="%" /></Grid>
                  <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="DD Duration" value={summary.drawdown_duration_days || "0"} unit="days" /></Grid>
                  <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Recovery Time" value={summary.max_recovery_days || "0"} unit="days" /></Grid>
                  <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Calmar Ratio" value={summary.calmar_ratio?.toFixed(3) || "0.000"} unit="" /></Grid>
                </Grid>

                {/* Drawdown Chart */}
                <ResponsiveContainer width="100%" height={300}>
                  <AreaChart data={[
                    { date: 'Current', drawdown: summary.current_drawdown || 0, maxDD: summary.max_drawdown || 0 },
                    { date: 'Avg DD', drawdown: summary.avg_drawdown || 0, maxDD: summary.max_drawdown || 0 },
                  ]}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="date" />
                    <YAxis label={{ value: 'Drawdown (%)', angle: -90, position: 'insideLeft' }} />
                    <RechartsTooltip formatter={(value) => `${value?.toFixed(2)}%`} />
                    <Legend />
                    <Area type="monotone" dataKey="drawdown" stackId="1" stroke="#ff9800" fill="#ff9800" opacity={0.6} name="Current Drawdown" />
                    <Area type="monotone" dataKey="maxDD" stackId="1" stroke="#f44336" fill="#f44336" opacity={0.6} name="Max Drawdown" />
                  </AreaChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>

            {/* Tail Risk & Distribution Analysis - Metrics + Chart */}
            <Card sx={{ mb: 4 }}>
              <CardHeader title="Tail Risk Analysis" subheader="VaR, CVaR, Skewness, and Kurtosis" />
              <CardContent>
                {/* Metrics */}
                <Grid container spacing={2} sx={{ mb: 3 }}>
                  <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="VaR 95%" value={summary.var_95?.toFixed(2) || "0.00"} unit="%" /></Grid>
                  <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="VaR 99%" value={summary.var_99?.toFixed(2) || "0.00"} unit="%" /></Grid>
                  <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="CVaR 95%" value={summary.cvar_95?.toFixed(2) || "0.00"} unit="%" /></Grid>
                  <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Skewness" value={summary.skewness?.toFixed(3) || "0.000"} unit="" /></Grid>
                  <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Kurtosis" value={summary.kurtosis?.toFixed(3) || "0.000"} unit="" /></Grid>
                  <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Semi-Skew" value={summary.semi_skewness?.toFixed(3) || "0.000"} unit="" /></Grid>
                </Grid>

                {/* Tail Risk Chart */}
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart data={[
                    { metric: 'Skewness', value: summary.skewness || 0 },
                    { metric: 'Kurtosis', value: (summary.kurtosis || 0) / 3 },
                    { metric: 'VaR 95%', value: summary.var_95 || 0 },
                    { metric: 'CVaR 95%', value: summary.cvar_95 || 0 },
                  ]}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="metric" />
                    <YAxis label={{ value: 'Value', angle: -90, position: 'insideLeft' }} />
                    <RechartsTooltip formatter={(value) => `${value?.toFixed(3)}`} />
                    <Bar dataKey="value" fill="#e53935" name="Value" radius={[8, 8, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>

            {/* Portfolio Risk Profile Radar */}
            <Card sx={{ mb: 4 }}>
              <CardHeader title="Portfolio Risk Profile (Holistic View)" subheader="Visual snapshot of all risk dimensions" />
              <CardContent>
                <ResponsiveContainer width="100%" height={350}>
                  <RadarChart data={[
                    ...(summary.volatility_annualized !== null && summary.volatility_annualized !== undefined ? [{ metric: 'Volatility', value: Math.min(summary.volatility_annualized, 100) }] : []),
                    ...(summary.max_drawdown !== null && summary.max_drawdown !== undefined ? [{ metric: 'Drawdown', value: Math.min(Math.abs(summary.max_drawdown), 100) }] : []),
                    ...(summary.skewness !== null && summary.skewness !== undefined ? [{ metric: 'Skewness', value: Math.min(Math.abs(summary.skewness * 20), 100) }] : []),
                    ...(summary.kurtosis !== null && summary.kurtosis !== undefined ? [{ metric: 'Kurtosis', value: Math.min(summary.kurtosis * 5, 100) }] : []),
                    ...(summary.portfolio_beta !== null && summary.portfolio_beta !== undefined ? [{ metric: 'Beta', value: Math.min(summary.portfolio_beta * 50, 100) }] : []),
                    ...(summary.diversification_score !== null && summary.diversification_score !== undefined ? [{ metric: 'Diversification', value: Math.min(summary.diversification_score / 10, 100) }] : []),
                  ]}>
                    <PolarGrid />
                    <PolarAngleAxis dataKey="metric" />
                    <PolarRadiusAxis angle={90} domain={[0, 100]} />
                    <Radar name="Risk Profile" dataKey="value" stroke="#ff9800" fill="#ff9800" fillOpacity={0.6} />
                    <RechartsTooltip formatter={(value) => `${value?.toFixed(1)}`} />
                  </RadarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          </Box>

          {/* ============ SECTION 4: ALLOCATION & DIVERSIFICATION ============ */}
          <Box sx={{ mb: 4, mt: 6 }}>
            <Typography variant="h5" sx={{ fontWeight: 700, mb: 3, display: 'flex', alignItems: 'center', gap: 1 }}>
              <AccountBalance sx={{ color: 'primary.main' }} /> Allocation & Diversification
            </Typography>

            {/* ---- Core Allocation Metrics ---- */}
            <Typography variant="h6" sx={{ fontWeight: 600, mb: 3, color: 'text.secondary' }}>
              Core Allocation Metrics
            </Typography>

            {/* Concentration & Diversification Metrics */}
            <Card sx={{ mb: 4 }}>
              <CardHeader title="Concentration & Diversification Metrics" />
              <CardContent>
                <Grid container spacing={2} sx={{ mb: 3 }}>
                  <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Top 1 Position" value={summary.top_1_weight != null ? summary.top_1_weight.toFixed(2) : "N/A"} unit="%" /></Grid>
                  <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Top 5 Positions" value={summary.top_5_weight != null ? summary.top_5_weight.toFixed(2) : "N/A"} unit="%" /></Grid>
                  <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Top 10 Positions" value={summary.top_10_weight != null ? summary.top_10_weight.toFixed(2) : "N/A"} unit="%" /></Grid>
                  <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Herfindahl Index" value={summary.herfindahl_index != null ? summary.herfindahl_index.toFixed(4) : "N/A"} unit="" /></Grid>
                  <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Effective N" value={summary.effective_n != null ? summary.effective_n.toFixed(2) : "N/A"} unit="" /></Grid>
                  <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Diversification Ratio" value={summary.diversification_ratio != null ? summary.diversification_ratio.toFixed(2) : "N/A"} unit="" /></Grid>
                </Grid>
              </CardContent>
            </Card>

            {/* ---- Holdings Distribution & Performance ---- */}
            <Typography variant="h6" sx={{ fontWeight: 600, mt: 4, mb: 3, color: 'text.secondary' }}>
              Holdings Distribution & Performance
            </Typography>

            {/* Holdings by Weight Distribution */}
            <Card sx={{ mb: 4 }}>
              <CardHeader title="Holdings by Weight Distribution" />
              <CardContent>
                <ResponsiveContainer width="100%" height={350}>
                  <BarChart
                    data={positions.map(p => ({
                      symbol: p.symbol,
                      weight: p.weight_percent !== null && p.weight_percent !== undefined ? parseFloat(p.weight_percent) : null,
                      value: p.market_value_dollars !== null && p.market_value_dollars !== undefined ? parseFloat(p.market_value_dollars) : null,
                    }))}
                    layout="vertical"
                    margin={{ top: 5, right: 30, left: 80, bottom: 5 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis type="number" />
                    <YAxis dataKey="symbol" type="category" width={70} />
                    <RechartsTooltip formatter={(value) => value?.toFixed(2)} />
                    <Legend />
                    <Bar dataKey="weight" fill="#1976d2" name="Weight %" radius={[0, 8, 8, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>

            {/* Market Value Heatmap */}
            <Card sx={{ mb: 4 }}>
              <CardHeader title="Position Market Values & Gains" />
              <CardContent>
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart
                    data={positions.map(p => ({
                      symbol: p.symbol,
                      value: p.market_value_dollars !== null && p.market_value_dollars !== undefined ? parseFloat(p.market_value_dollars) : null,
                      gain: p.gain_loss_dollars !== null && p.gain_loss_dollars !== undefined ? parseFloat(p.gain_loss_dollars) : null,
                    }))}
                  >
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="symbol" />
                    <YAxis yAxisId="left" label={{ value: 'Market Value ($)', angle: -90, position: 'insideLeft' }} />
                    <YAxis yAxisId="right" orientation="right" label={{ value: 'Gain/Loss ($)', angle: 90, position: 'insideRight' }} />
                    <RechartsTooltip formatter={(value) => `$${value?.toFixed(0)}`} />
                    <Legend />
                    <Bar yAxisId="left" dataKey="value" fill="#1976d2" name="Position Value ($)" radius={[8, 8, 0, 0]} />
                    <Bar yAxisId="right" dataKey="gain" fill="#43a047" name="Unrealized Gain/Loss ($)" radius={[8, 8, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>

            {/* Sector & Diversification */}
            <Card sx={{ mb: 4 }}>
              <CardHeader title="Sector & Industry Diversification" />
              <CardContent>
                <Grid container spacing={2} sx={{ mb: 3 }}>
                  <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Num Sectors" value={summary.num_sectors || "0"} unit="" /></Grid>
                  <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Num Industries" value={summary.num_industries || "0"} unit="" /></Grid>
                  <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Sector Concentration" value={summary.sector_concentration?.toFixed(2) || "0.00"} unit="%" /></Grid>
                  <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Avg Correlation" value={summary.avg_correlation?.toFixed(2) || "0.50"} unit="" /></Grid>
                  <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Top Sector" value={summary.top_sector || "N/A"} unit="" /></Grid>
                  <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Best Performer" value={summary.best_performer_sector || "N/A"} unit="" /></Grid>
                </Grid>

                {/* Sector Performance Analysis */}
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart
                    data={sectorData.length > 0 ? sectorData : [{ sector: 'No Data', weight: 0, return: 0 }]}
                  >
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="sector" />
                    <YAxis yAxisId="left" label={{ value: 'Weight (%)', angle: -90, position: 'insideLeft' }} />
                    <YAxis yAxisId="right" orientation="right" label={{ value: 'Avg Return (%)', angle: 90, position: 'insideRight' }} />
                    <RechartsTooltip />
                    <Legend />
                    <Bar yAxisId="left" dataKey="weight" fill="#1976d2" name="Portfolio Weight %" radius={[8, 8, 0, 0]} />
                    <Bar yAxisId="right" dataKey="return" fill="#43a047" name="Avg Sector Return %" radius={[8, 8, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>

            {/* ---- Position-Level Analysis ---- */}
            <Typography variant="h6" sx={{ fontWeight: 600, mt: 4, mb: 3, color: 'text.secondary' }}>
              Position-Level Analysis
            </Typography>

            {/* Volatility & Risk Contribution */}
            <Card sx={{ mb: 4 }}>
              <CardHeader title="Volatility & Risk Contribution by Position" />
              <CardContent>
                <ResponsiveContainer width="100%" height={300}>
                  <ComposedChart
                    data={positions.map(p => ({
                      symbol: p.symbol,
                      volatility: parseFloat(p.volatility_percent) || 0,
                      risk: parseFloat(p.risk_contribution_percent) || 0,
                      weight: parseFloat(p.weight_percent) || 0,
                    }))}
                  >
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="symbol" />
                    <YAxis yAxisId="left" label={{ value: 'Volatility (%)', angle: -90, position: 'insideLeft' }} />
                    <YAxis yAxisId="right" orientation="right" label={{ value: 'Risk Contrib (%) / Weight', angle: 90, position: 'insideRight' }} />
                    <RechartsTooltip />
                    <Legend />
                    <Bar yAxisId="left" dataKey="volatility" fill="#ff9800" name="Volatility %" radius={[8, 8, 0, 0]} />
                    <Bar yAxisId="right" dataKey="risk" fill="#e53935" name="Risk Contribution %" radius={[8, 8, 0, 0]} />
                  </ComposedChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>

            {/* Return Contribution Analysis */}
            <Card sx={{ mb: 4 }}>
              <CardHeader title="Return Contribution by Holding" />
              <CardContent>
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart
                    data={positions.map(p => ({
                      symbol: p.symbol,
                      return: parseFloat(p.return_contribution_percent) || 0,
                      beta: parseFloat(p.beta) || 0,
                    }))}
                  >
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="symbol" />
                    <YAxis yAxisId="left" label={{ value: 'Return Contrib (%)', angle: -90, position: 'insideLeft' }} />
                    <YAxis yAxisId="right" orientation="right" label={{ value: 'Beta', angle: 90, position: 'insideRight' }} />
                    <RechartsTooltip />
                    <Legend />
                    <Bar yAxisId="left" dataKey="return" fill="#43a047" name="Return Contribution %" radius={[8, 8, 0, 0]} />
                    <Bar yAxisId="right" dataKey="beta" fill="#1976d2" name="Beta" radius={[8, 8, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>

            {/* Position Correlation with Portfolio */}
            <Card sx={{ mb: 4 }}>
              <CardHeader title="Position Correlation with Portfolio" />
              <CardContent>
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart
                    data={positions
                      .filter(p => p.correlation_with_portfolio !== null && p.correlation_with_portfolio !== undefined &&
                                   p.weight_percent !== null && p.weight_percent !== undefined)
                      .map(p => ({
                        symbol: p.symbol,
                        correlation: parseFloat(p.correlation_with_portfolio),
                        weight: parseFloat(p.weight_percent),
                      }))}
                  >
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="symbol" />
                    <YAxis label={{ value: 'Correlation / Weight (%)', angle: -90, position: 'insideLeft' }} />
                    <RechartsTooltip formatter={(value) => value?.toFixed(2)} />
                    <Legend />
                    <Bar dataKey="correlation" fill="#9c27b0" name="Correlation with Portfolio" radius={[8, 8, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
                <Typography variant="caption" color="text.secondary" sx={{ mt: 2, display: 'block' }}>
                  Correlation &gt; 0.7: Strong positive correlation with portfolio movements | Correlation &lt; 0.5: Good diversifier
                </Typography>
              </CardContent>
            </Card>

            {/* Top Holdings Correlation Matrix */}
            <Card sx={{ mb: 4 }}>
              <CardHeader
                title="Top Holdings Correlation Matrix"
                subheader="Asset correlation structure (top 8 positions)"
              />
              <CardContent>
                <ResponsiveContainer width="100%" height={350}>
                  <ComposedChart
                    data={positions.slice(0, 8)
                      .filter(pos => pos.correlation_with_portfolio !== null && pos.correlation_with_portfolio !== undefined &&
                                     pos.volatility_percent !== null && pos.volatility_percent !== undefined &&
                                     pos.weight_percent !== null && pos.weight_percent !== undefined)
                      .map((pos, idx) => ({
                        symbol: pos.symbol,
                        correlation_market: parseFloat(pos.correlation_with_portfolio),
                        volatility: parseFloat(pos.volatility_percent),
                        weight: parseFloat(pos.weight_percent),
                      }))}
                    layout="vertical"
                    margin={{ top: 5, right: 30, left: 100, bottom: 5 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis type="number" />
                    <YAxis dataKey="symbol" type="category" width={90} />
                    <RechartsTooltip
                      contentStyle={{ backgroundColor: '#fff', border: '1px solid #ccc' }}
                      formatter={(value) => value?.toFixed(2) || '0'}
                    />
                    <Legend />
                    <Bar dataKey="correlation_market" fill="#1976d2" name="Market Correlation" radius={[0, 8, 8, 0]} />
                    <Bar dataKey="volatility" fill="#ff6f00" name="Volatility (Annualized %)" radius={[0, 8, 8, 0]} />
                  </ComposedChart>
                </ResponsiveContainer>
                <Typography variant="caption" color="text.secondary" sx={{ mt: 2, display: 'block' }}>
                  Shows how each holding correlates with the broader market and its individual volatility. Higher correlation = moves with market; Higher volatility = more price swings.
                </Typography>
              </CardContent>
            </Card>
          </Box>

          {/* ============ SECTION 5: PORTFOLIO EFFICIENCY & DETAILED BREAKDOWN ============ */}
          <Box sx={{ mb: 4, mt: 6 }}>
            <Typography variant="h5" sx={{ fontWeight: 700, mb: 3, display: 'flex', alignItems: 'center', gap: 1 }}>
              <ShowChart sx={{ color: 'primary.main' }} /> Portfolio Efficiency
            </Typography>

            {/* Portfolio Efficiency Metrics */}
            <Card sx={{ mb: 4 }}>
              <CardHeader title="Portfolio Efficiency Metrics" />
              <CardContent>
                <Grid container spacing={2}>
                  <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Return/Risk Ratio" value={summary.return_risk_ratio != null ? summary.return_risk_ratio.toFixed(2) : "N/A"} unit="" /></Grid>
                  <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Cash Drag" value={summary.cash_drag != null ? summary.cash_drag.toFixed(2) : "N/A"} unit="%" /></Grid>
                  <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Turnover Ratio" value={summary.turnover_ratio != null ? summary.turnover_ratio.toFixed(2) : "N/A"} unit="%" /></Grid>
                  <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Transaction Costs" value={summary.transaction_costs != null ? summary.transaction_costs.toFixed(2) : "N/A"} unit="bps" /></Grid>
                  <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Sector Momentum" value={summary.sector_momentum != null ? summary.sector_momentum.toFixed(2) : "N/A"} unit="%" /></Grid>
                  <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Risk-Free Rate" value={metadata.risk_free_rate != null ? metadata.risk_free_rate : "N/A"} unit="%" /></Grid>
                </Grid>
              </CardContent>
            </Card>

            {/* Holdings Table */}
            <Card sx={{ mb: 4 }}>
              <CardHeader
                title="Top Holdings Attribution"
                action={
                  <Button size="small" startIcon={<Refresh />} onClick={() => refetchMetrics()}>
                    Refresh
                  </Button>
                }
              />
              <CardContent sx={{ overflowX: "auto" }}>
                {positions.length === 0 ? (
                  <Typography color="text.secondary" align="center" sx={{ py: 4 }}>
                    No holdings data available.
                  </Typography>
                ) : (
                  <table style={{ width: "100%", borderCollapse: "collapse", minWidth: "700px" }}>
                    <thead>
                      <tr style={{ borderBottom: `2px solid ${theme.palette.divider}`, backgroundColor: theme.palette.background.default }}>
                        <th style={{ textAlign: "left", padding: "12px", fontWeight: 700 }}>Symbol</th>
                        <th style={{ textAlign: "right", padding: "12px", fontWeight: 700 }}>Weight %</th>
                        <th style={{ textAlign: "right", padding: "12px", fontWeight: 700 }}>Value $</th>
                        <th style={{ textAlign: "right", padding: "12px", fontWeight: 700 }}>Gain/Loss $</th>
                        <th style={{ textAlign: "right", padding: "12px", fontWeight: 700 }}>Return %</th>
                      </tr>
                    </thead>
                    <tbody>
                      {positions.map((pos, idx) => {
                        const weight = pos.weight_percent !== null && pos.weight_percent !== undefined ? parseFloat(pos.weight_percent).toFixed(2) : "N/A";
                        const value = pos.market_value_dollars !== null && pos.market_value_dollars !== undefined
                          ? `$${parseFloat(pos.market_value_dollars).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                          : "N/A";
                        const gainLoss = pos.gain_loss_dollars !== null && pos.gain_loss_dollars !== undefined
                          ? `$${parseFloat(pos.gain_loss_dollars).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                          : "N/A";
                        const gainLossColor = pos.gain_loss_dollars !== null && pos.gain_loss_dollars !== undefined
                          ? (parseFloat(pos.gain_loss_dollars) >= 0 ? theme.palette.success.main : theme.palette.error.main)
                          : "inherit";
                        const returnPct = pos.return_percent !== null && pos.return_percent !== undefined ? parseFloat(pos.return_percent).toFixed(2) : "N/A";
                        const returnColor = pos.return_percent !== null && pos.return_percent !== undefined
                          ? (parseFloat(pos.return_percent) >= 0 ? theme.palette.success.main : theme.palette.error.main)
                          : "inherit";
                        return (
                          <tr key={idx} style={{ borderBottom: `1px solid ${theme.palette.divider}` }}>
                            <td style={{ padding: "12px", fontWeight: 500 }}>{pos.symbol}</td>
                            <td style={{ textAlign: "right", padding: "12px" }}>{weight}%</td>
                            <td style={{ textAlign: "right", padding: "12px" }}>{value}</td>
                            <td style={{ textAlign: "right", padding: "12px", color: gainLossColor }}>
                              {gainLoss}
                            </td>
                            <td style={{ textAlign: "right", padding: "12px", color: returnColor, fontWeight: 600 }}>
                              {returnPct}%
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                )}
              </CardContent>
            </Card>
          </Box>

          {/* ============ METADATA FOOTER ============ */}
          <Card sx={{ backgroundColor: theme.palette.background.default }}>
            <CardContent>
              <Typography variant="caption" color="text.secondary">
                <strong>Calculation Basis:</strong> {metadata.calculation_basis ?? 'N/A'} •
                <strong> Benchmark:</strong> {metadata.benchmark ?? 'N/A'} •
                <strong> Risk-Free Rate:</strong> {metadata.risk_free_rate ?? 'N/A'} •
                <strong> Data Points:</strong> {metadata.data_points ?? 'N/A'} •
                <strong> Portfolio Value:</strong> {metadata.portfolio_value !== null && metadata.portfolio_value !== undefined ? `$${metadata.portfolio_value.toLocaleString()}` : 'N/A'}
              </Typography>
            </CardContent>
          </Card>
        </>
      )}
    </Container>
  );
}
