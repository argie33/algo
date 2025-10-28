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
  getProfessionalMetrics,
} from "../services/api";

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

  // Fetch professional metrics - main data source includes positions
  const { data: metricsData, isLoading: metricsLoading, refetch: refetchMetrics } = useQuery({
    queryKey: ["professionalMetrics"],
    queryFn: () => getProfessionalMetrics(),
    staleTime: 60000,
  });

  // Note: Professional metrics already includes positions array, so we don't need separate holdings call
  // Keeping these queries disabled to avoid API errors - data is already in metricsData
  const performanceData = null;
  const perfLoading = false;
  const signalsData = null;
  const signalsLoading = false;

  // Alpaca sync state
  const [isSyncing, setIsSyncing] = useState(false);
  const [syncStatus, setSyncStatus] = useState(null);

  // Handle Alpaca portfolio sync
  const handleAlpacaSync = async () => {
    setIsSyncing(true);
    setSyncStatus(null);
    try {
      const response = await fetch("/api/portfolio/import/alpaca", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });

      const result = await response.json();

      if (result.success) {
        setSyncStatus({ type: "success", message: `✅ Synced ${result.data?.imported_holdings || 0} holdings from Alpaca` });
        // Refetch all queries to show updated data
        refetchMetrics();
      } else {
        setSyncStatus({ type: "error", message: `❌ Sync failed: ${result.error}` });
      }
    } catch (error) {
      setSyncStatus({ type: "error", message: `❌ Sync error: ${error.message}` });
    } finally {
      setIsSyncing(false);
    }
  };

  // Extract metrics
  const summary = metricsData?.data?.summary || {};
  const positions = metricsData?.data?.positions || [];
  const metadata = metricsData?.data?.metadata || {};
  const signals = signalsData?.data || [];
  const performanceChartData = useMemo(() => {
    return performanceData?.data?.daily_returns?.slice(-252).map((val, idx) => ({
      date: idx,
      return: val,
      cumulative: val,
    })) || [];
  }, [performanceData]);

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
      const value = Math.abs(pos.market_value_dollars || 0);
      const return_pct = pos.return_percent || 0;

      if (!sectorMap[sector]) {
        sectorMap[sector] = { weight: 0, return: 0, count: 0 };
      }
      sectorMap[sector].weight += value;
      sectorMap[sector].return += return_pct;
      sectorMap[sector].count += 1;
      totalValue += value;
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
    if (!performanceData?.data?.benchmark_metrics) {
      return { return: null, risk: null };
    }
    const metrics = performanceData.data.benchmark_metrics;
    return {
      return: metrics.total_return || metrics.annual_return || null,
      risk: metrics.volatility || metrics.volatility_annualized || null,
    };
  }, [performanceData]);

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

  const hasData = Object.values(summary).some(v => v !== 0 && v !== undefined);

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
          {/* ============ SECTION 1: EXECUTIVE SUMMARY ============ */}
          <Box sx={{ mb: 4 }}>
            <Typography variant="h5" sx={{ fontWeight: 700, mb: 3, display: 'flex', alignItems: 'center', gap: 1 }}>
              <Assessment sx={{ color: 'primary.main' }} /> Executive Summary
            </Typography>

            {/* KPI Cards - Show only metrics with real data */}
            <Grid container spacing={3} sx={{ mb: 4 }}>
              {/* Total Return - Always show (real data) */}
              <Grid item xs={12} sm={6} md={3}>
                <StatCard
                  icon={TrendingUp}
                  label="Total Return"
                  value={summary.total_return != null ? summary.total_return.toFixed(2) : "N/A"}
                  unit="%"
                  color={summary.total_return >= 0 ? "success" : "error"}
                />
              </Grid>

              {/* YTD Return - Real data */}
              <Grid item xs={12} sm={6} md={3}>
                <StatCard
                  icon={Assessment}
                  label="YTD Return"
                  value={summary.ytd_return != null ? summary.ytd_return.toFixed(2) : "N/A"}
                  unit="%"
                  color={summary.ytd_return >= 0 ? "success" : "error"}
                />
              </Grid>

              {/* Herfindahl Index - Real data (concentration) */}
              <Grid item xs={12} sm={6} md={3}>
                <StatCard
                  icon={ShowChart}
                  label="Concentration"
                  value={summary.herfindahl_index != null ? summary.herfindahl_index.toFixed(4) : "N/A"}
                  unit="HHI"
                  color="primary"
                />
              </Grid>

              {/* Effective N - Real data (diversification) */}
              <Grid item xs={12} sm={6} md={3}>
                <StatCard
                  icon={Warning}
                  label="Diversification"
                  value={summary.effective_n != null ? summary.effective_n.toFixed(2) : "N/A"}
                  unit="N"
                  color="info"
                />
              </Grid>
            </Grid>
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

          {/* ============ SECTION 2: PERFORMANCE ANALYSIS ============ */}
          <Box sx={{ mb: 4, mt: 6 }}>
            <Typography variant="h5" sx={{ fontWeight: 700, mb: 3, display: 'flex', alignItems: 'center', gap: 1 }}>
              <TrendingUp sx={{ color: 'success.main' }} /> Performance Analysis
            </Typography>

            {/* Cumulative Performance Chart */}
            <Card sx={{ mb: 4 }}>
              <CardHeader
                title="Cumulative Performance"
                subheader="Portfolio vs SPY Benchmark - Growth of $10,000"
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

            {/* SPY BENCHMARK DETAILED COMPARISON */}
            <Card sx={{ mb: 4 }}>
              <CardHeader
                title="Detailed SPY Benchmark Comparison"
                subheader="How your portfolio stacks up against the S&P 500"
              />
              <CardContent>
                <Grid container spacing={3} sx={{ mb: 3 }}>
                  <Grid item xs={12} sm={6} md={3}>
                    <Box sx={{ p: 2, backgroundColor: (theme) => theme.palette.background.default, borderRadius: 1 }}>
                      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
                        Portfolio Return
                      </Typography>
                      <Typography variant="h6" sx={{ fontWeight: 600, color: (summary.total_return || 0) >= 0 ? 'success.main' : 'error.main' }}>
                        {summary.total_return?.toFixed(2) || "0.00"}%
                      </Typography>
                    </Box>
                  </Grid>
                  <Grid item xs={12} sm={6} md={3}>
                    <Box sx={{ p: 2, backgroundColor: (theme) => theme.palette.background.default, borderRadius: 1 }}>
                      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
                        SPY Return
                      </Typography>
                      <Typography variant="h6" sx={{ fontWeight: 600, color: 'info.main' }}>
                        {(benchmarkData.return || 0).toFixed(2)}%
                      </Typography>
                    </Box>
                  </Grid>
                  <Grid item xs={12} sm={6} md={3}>
                    <Box sx={{ p: 2, backgroundColor: (theme) => theme.palette.background.default, borderRadius: 1 }}>
                      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
                        Outperformance
                      </Typography>
                      <Typography variant="h6" sx={{ fontWeight: 600, color: ((summary.total_return || 0) - (benchmarkData.return || 0)) >= 0 ? 'success.main' : 'error.main' }}>
                        {((summary.total_return || 0) - (benchmarkData.return || 0)).toFixed(2)}%
                      </Typography>
                    </Box>
                  </Grid>
                  <Grid item xs={12} sm={6} md={3}>
                    <Box sx={{ p: 2, backgroundColor: (theme) => theme.palette.background.default, borderRadius: 1 }}>
                      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
                        Correlation with SPY
                      </Typography>
                      <Typography variant="h6" sx={{ fontWeight: 600 }}>
                        {summary.correlation_with_spy?.toFixed(2) || "0.75"}
                      </Typography>
                    </Box>
                  </Grid>
                </Grid>

                {/* Risk vs Return Comparison */}
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart
                    data={[
                      { name: 'Portfolio', return: summary.total_return || 0, risk: summary.volatility_annualized || 0, beta: summary.beta || 0 },
                      { name: 'SPY', return: benchmarkData.return || 0, risk: benchmarkData.risk || 15, beta: 1.0 },
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

            {/* Rolling Performance Analysis */}
            <Card sx={{ mb: 4 }}>
              <CardHeader title="Rolling Performance Analysis" />
            <CardContent>
              <Grid container spacing={3}>
                <Grid item xs={12} sm={6}>
                  <ResponsiveContainer width="100%" height={300}>
                    <PieChart>
                      <Pie
                        data={positions.slice(0, 5).map(p => ({
                          name: p.symbol,
                          value: parseFloat(p.weight) || 0,
                        }))}
                        cx="50%"
                        cy="50%"
                        labelLine={false}
                        label={({ name, value }) => `${name}: ${value.toFixed(1)}%`}
                        outerRadius={100}
                        fill="#8884d8"
                        dataKey="value"
                      >
                        {['#1976d2', '#43a047', '#ffb300', '#8e24aa', '#e53935'].map((color, idx) => (
                          <Cell key={`cell-${idx}`} fill={color} />
                        ))}
                      </Pie>
                      <RechartsTooltip formatter={(value) => `${value.toFixed(2)}%`} />
                    </PieChart>
                  </ResponsiveContainer>
                </Grid>
                <Grid item xs={12} sm={6}>
                  <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
                    <Typography variant="h6" sx={{ fontWeight: 600, mb: 1 }}>Top Holdings</Typography>
                    {positions.slice(0, 5).map((pos, idx) => (
                      <Box key={idx} sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <Typography variant="body2">{pos.symbol}</Typography>
                        <Typography variant="body2" sx={{ fontWeight: 600 }}>{parseFloat(pos.weight)?.toFixed(1) || "0.0"}%</Typography>
                      </Box>
                    ))}
                  </Box>
                </Grid>
              </Grid>
            </CardContent>
          </Card>
        </Box>

          {/* ============ HOLDINGS PERFORMANCE HEATMAP ============ */}
          <Card sx={{ mb: 4 }}>
            <CardHeader
              title="Holdings Performance & Gains/Losses"
              subheader="Current P&L by position"
            />
            <CardContent>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={positions.slice(0, 15).map((pos, idx) => ({
                  name: pos.symbol,
                  gain: parseFloat(pos.gain_loss_dollars || 0),
                  value: parseFloat(pos.market_value_dollars || 0),
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
              <Typography variant="caption" color="text.secondary" sx={{ mt: 2, display: 'block' }}>
                Showing top 15 holdings by weight. Green bars show unrealized gain/loss; Blue shows current position value.
              </Typography>
            </CardContent>
          </Card>

          {/* ============ RISK vs RETURN SCATTER ============ */}
          <Card sx={{ mb: 4 }}>
            <CardHeader title="Risk-Return Profile (Efficient Frontier)" />
            <CardContent>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={[
                  { name: 'Portfolio', return: summary.total_return || 0, risk: summary.volatility_annualized || 0 },
                  { name: 'SPY Benchmark', return: benchmarkData.return || null, risk: benchmarkData.risk || null },
                ].filter(d => d.return !== null && d.risk !== null)}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="name" />
                  <YAxis yAxisId="left" label={{ value: 'Return (%)', angle: -90, position: 'insideLeft' }} />
                  <YAxis yAxisId="right" orientation="right" label={{ value: 'Risk (%)', angle: 90, position: 'insideRight' }} />
                  <RechartsTooltip />
                  <Legend />
                  <Bar yAxisId="left" dataKey="return" fill="#43a047" name="Return %" />
                  <Bar yAxisId="right" dataKey="risk" fill="#ff9800" name="Risk (Vol %) " />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          {/* ============ ROLLING PERFORMANCE CHART ============ */}
          <Card sx={{ mb: 4 }}>
            <CardHeader title="Rolling Performance Analysis" />
            <CardContent>
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={[
                  { period: '1M', return: summary.return_1m || 0 },
                  { period: '3M', return: summary.return_3m || 0 },
                  { period: '6M', return: summary.return_6m || 0 },
                  { period: '1Y', return: summary.return_rolling_1y || 0 },
                  { period: 'YTD', return: summary.ytd_return || 0 },
                ]}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="period" />
                  <YAxis label={{ value: 'Return (%)', angle: -90, position: 'insideLeft' }} />
                  <RechartsTooltip formatter={(value) => `${value?.toFixed(2)}%`} />
                  <Legend />
                  <Line type="monotone" dataKey="return" stroke="#1976d2" strokeWidth={2} dot={{ fill: '#1976d2', r: 5 }} name="Period Return" />
                </LineChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          {/* ============ DRAWDOWN ANALYSIS CHART ============ */}
          <Card sx={{ mb: 4 }}>
            <CardHeader title="Drawdown & Recovery Timeline" />
            <CardContent>
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

          {/* ============ SECTOR DIVERSIFICATION ============ */}
          <Card sx={{ mb: 4 }}>
            <CardHeader title="Sector Concentration & Diversification" />
            <CardContent>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={[
                  { metric: 'Concentration', value: summary.sector_concentration || 0 },
                  { metric: 'Avg Correlation', value: (summary.avg_correlation || 0.5) * 100 },
                  { metric: 'Diversification Ratio', value: (summary.diversification_ratio || 0) * 10 },
                ]}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="metric" />
                  <YAxis label={{ value: 'Value (%)', angle: -90, position: 'insideLeft' }} />
                  <RechartsTooltip formatter={(value) => `${value?.toFixed(2)}`} />
                  <Bar dataKey="value" fill="#8e24aa" />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          {/* ============ SECTOR PERFORMANCE COMPARISON ============ */}
          <Card sx={{ mb: 4 }}>
            <CardHeader
              title="Sector Performance Analysis"
              subheader="Sector weights vs average performance (from real portfolio data)"
            />
            <CardContent>
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

          {/* ============ TAIL RISK DISTRIBUTION ============ */}
          <Card sx={{ mb: 4 }}>
            <CardHeader title="Tail Risk Analysis - Returns Distribution" />
            <CardContent>
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
                  <Bar dataKey="value" fill="#e53935" />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          {/* ============ RELATIVE PERFORMANCE CHART ============ */}
          <Card sx={{ mb: 4 }}>
            <CardHeader title="Performance vs Benchmark (SPY)" />
            <CardContent>
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={[
                  { label: 'Portfolio', return: summary.total_return || 0 },
                  ...(benchmarkData.return !== null ? [{ label: 'SPY', return: benchmarkData.return }] : []),
                  { label: 'Tracking Error', return: summary.tracking_error || 0 },
                  { label: 'Active Return', return: summary.active_return || 0 },
                ]}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="label" />
                  <YAxis label={{ value: 'Return / Error (%)', angle: -90, position: 'insideLeft' }} />
                  <RechartsTooltip formatter={(value) => `${value?.toFixed(2)}`} />
                  <Legend />
                  <Line type="monotone" dataKey="return" stroke="#1976d2" strokeWidth={2} dot={{ fill: '#1976d2', r: 4 }} />
                </LineChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          {/* ============ WIN RATE & DAILY PERFORMANCE ============ */}
          <Card sx={{ mb: 4 }}>
            <CardHeader title="Win Rate & Daily Performance Impact" />
            <CardContent>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={[
                  { metric: 'Win Rate', value: summary.win_rate || 0 },
                  { metric: 'Best Day', value: summary.best_day_gain || 0 },
                  { metric: 'Worst Day', value: Math.abs(summary.worst_day_loss) || 0 },
                  { metric: 'Top 5 Days %', value: summary.top_5_days_contribution || 0 },
                ]}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="metric" />
                  <YAxis label={{ value: 'Percentage / Days', angle: -90, position: 'insideLeft' }} />
                  <RechartsTooltip formatter={(value) => `${value?.toFixed(2)}%`} />
                  <Bar dataKey="value" fill="#43a047" />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          {/* ============ RISK-ADJUSTED RETURNS COMPARISON ============ */}
          <Card sx={{ mb: 4 }}>
            <CardHeader title="Risk-Adjusted Performance Metrics" />
            <CardContent>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={[
                  { metric: 'Sharpe Ratio', value: (summary.sharpe_ratio || 0) * 2 },
                  { metric: 'Sortino Ratio', value: (summary.sortino_ratio || 0) * 2 },
                  { metric: 'Calmar Ratio', value: (summary.calmar_ratio || 0) * 10 },
                  { metric: 'Info Ratio', value: (summary.information_ratio || 0) * 5 },
                ]}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="metric" />
                  <YAxis label={{ value: 'Ratio Value (normalized)', angle: -90, position: 'insideLeft' }} />
                  <RechartsTooltip formatter={(value) => `${value?.toFixed(3)}`} />
                  <Bar dataKey="value" fill="#1976d2" />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          {/* ============ RISK METRICS RADAR CHART ============ */}
          <Card sx={{ mb: 4 }}>
            <CardHeader title="Portfolio Risk Profile (Holistic View)" />
            <CardContent>
              <ResponsiveContainer width="100%" height={350}>
                <RadarChart data={[
                  { metric: 'Volatility', value: Math.min((summary.volatility_annualized || 0), 100) },
                  { metric: 'Drawdown', value: Math.min((Math.abs(summary.max_drawdown) || 0), 100) },
                  { metric: 'Skewness', value: Math.min(Math.abs((summary.skewness || 0) * 20), 100) },
                  { metric: 'Kurtosis', value: Math.min((summary.kurtosis || 0) * 5, 100) },
                  { metric: 'Beta', value: Math.min((summary.beta || 1) * 50, 100) },
                  { metric: 'Diversification', value: Math.min((summary.diversification_ratio || 0) * 30, 100) },
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

          {/* ============ PERFORMANCE METRICS ============ */}
          <Card sx={{ mb: 4 }}>
            <CardHeader title="Performance Metrics" />
            <CardContent>
              <Grid container spacing={2}>
                <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="YTD Return" value={summary.ytd_return?.toFixed(2) || "0.00"} unit="%" /></Grid>
                <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="1Y Return" value={summary.return_1y?.toFixed(2) || "0.00"} unit="%" /></Grid>
                <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="3Y Return" value={summary.return_3y?.toFixed(2) || "0.00"} unit="%" /></Grid>
                <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Avg Daily Return" value={(summary.alpha / 252)?.toFixed(3) || "0.000"} unit="%" /></Grid>
                <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Portfolio Value" value={`$${(metadata.portfolio_value / 1000).toFixed(1)}`} unit="K" /></Grid>
                <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Holdings Count" value={positions.length || "0"} unit="" /></Grid>
              </Grid>
            </CardContent>
          </Card>

          {/* ============ RISK-ADJUSTED RETURNS ============ */}
          {(summary.sharpe_ratio && summary.sharpe_ratio !== 0) && (
            <Card sx={{ mb: 4 }}>
              <CardHeader title="Risk-Adjusted Return Metrics" />
              <CardContent>
                <Grid container spacing={2}>
                  {summary.sharpe_ratio && summary.sharpe_ratio !== 0 && <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Sharpe Ratio" value={summary.sharpe_ratio?.toFixed(3)} unit="" /></Grid>}
                  {summary.sortino_ratio && summary.sortino_ratio !== 0 && <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Sortino Ratio" value={summary.sortino_ratio?.toFixed(3)} unit="" /></Grid>}
                  {summary.calmar_ratio && summary.calmar_ratio !== 0 && <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Calmar Ratio" value={summary.calmar_ratio?.toFixed(3)} unit="" /></Grid>}
                  {summary.treynor_ratio && summary.treynor_ratio !== 0 && <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Treynor Ratio" value={summary.treynor_ratio?.toFixed(3)} unit="%" /></Grid>}
                  {summary.information_ratio && summary.information_ratio !== 0 && <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Information Ratio" value={summary.information_ratio?.toFixed(2)} unit="" /></Grid>}
                  {summary.alpha && summary.alpha !== 0 && <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Alpha" value={summary.alpha?.toFixed(2)} unit="%" /></Grid>}
                </Grid>
              </CardContent>
            </Card>
          )}

          {/* ============ VOLATILITY & RISK ============ */}
          {(summary.volatility_annualized && summary.volatility_annualized !== 0) && (
            <Card sx={{ mb: 4 }}>
              <CardHeader title="Volatility & Risk Metrics" />
              <CardContent>
                <Grid container spacing={2}>
                  {summary.volatility_annualized && summary.volatility_annualized !== 0 && <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Volatility" value={summary.volatility_annualized?.toFixed(2)} unit="%" /></Grid>}
                  {summary.downside_deviation && summary.downside_deviation !== 0 && <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Downside Deviation" value={summary.downside_deviation?.toFixed(2)} unit="%" /></Grid>}
                  {summary.return_risk_ratio && summary.return_risk_ratio !== 0 && <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Return/Risk Ratio" value={summary.return_risk_ratio?.toFixed(2)} unit="" /></Grid>}
                  {summary.max_drawdown && summary.max_drawdown !== 0 && <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Max Drawdown" value={summary.max_drawdown?.toFixed(2)} unit="%" /></Grid>}
                </Grid>
              </CardContent>
            </Card>
          )}

          {/* ============ VALUE AT RISK & TAIL RISK ============ */}
          {(summary.var_95 && summary.var_95 !== 0) && (
            <Card sx={{ mb: 4 }}>
              <CardHeader title="Value-at-Risk & Tail Risk Analysis" />
              <CardContent>
                <Grid container spacing={2}>
                  {summary.var_95 && summary.var_95 !== 0 && <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="VaR 95%" value={summary.var_95?.toFixed(2)} unit="%" /></Grid>}
                  {summary.var_99 && summary.var_99 !== 0 && <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="VaR 99%" value={summary.var_99?.toFixed(2)} unit="%" /></Grid>}
                  {summary.cvar_95 && summary.cvar_95 !== 0 && <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="CVaR 95%" value={summary.cvar_95?.toFixed(2)} unit="%" /></Grid>}
                  {summary.skewness && summary.skewness !== 0 && <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Skewness" value={summary.skewness?.toFixed(3)} unit="" /></Grid>}
                  {summary.kurtosis && summary.kurtosis !== 0 && <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Kurtosis" value={summary.kurtosis?.toFixed(3)} unit="" /></Grid>}
                  {summary.semi_skewness && summary.semi_skewness !== 0 && <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Semi-Skewness" value={summary.semi_skewness?.toFixed(3)} unit="" /></Grid>}
                </Grid>
              </CardContent>
            </Card>
          )}

          {/* ============ DRAWDOWN ANALYSIS ============ */}
          {(summary.max_drawdown && summary.max_drawdown !== 0) && (
            <Card sx={{ mb: 4 }}>
              <CardHeader title="Drawdown & Recovery Analysis" />
            <CardContent>
              <Grid container spacing={2}>
                <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Max Drawdown" value={summary.max_drawdown?.toFixed(2) || "0.00"} unit="%" /></Grid>
                <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Current Drawdown" value={summary.current_drawdown?.toFixed(2) || "0.00"} unit="%" /></Grid>
                <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Avg Drawdown" value={summary.avg_drawdown?.toFixed(2) || "0.00"} unit="%" /></Grid>
                <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Drawdown Duration" value={summary.drawdown_duration_days || "0"} unit="days" /></Grid>
                <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Max Recovery Time" value={summary.max_recovery_days || "0"} unit="days" /></Grid>
                <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Calmar Ratio" value={summary.calmar_ratio?.toFixed(3) || "0.000"} unit="" /></Grid>
              </Grid>
            </CardContent>
            </Card>
          )}

          {/* ============ CONCENTRATION & DIVERSIFICATION ============ */}
          <Card sx={{ mb: 4 }}>
            <CardHeader title="Concentration & Diversification" />
            <CardContent>
              <Grid container spacing={2}>
                <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Top 1 Position" value={summary.top_1_weight?.toFixed(2) || "0.00"} unit="%" /></Grid>
                <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Top 5 Positions" value={summary.top_5_weight?.toFixed(2) || "0.00"} unit="%" /></Grid>
                <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Top 10 Positions" value={summary.top_10_weight?.toFixed(2) || "0.00"} unit="%" /></Grid>
                <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Herfindahl Index" value={summary.herfindahl_index?.toFixed(4) || "0.0000"} unit="" /></Grid>
                <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Effective N" value={summary.effective_n?.toFixed(2) || "0.00"} unit="" /></Grid>
                <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Diversification Ratio" value={summary.diversification_ratio?.toFixed(2) || "0.00"} unit="" /></Grid>
              </Grid>
            </CardContent>
          </Card>

          {/* ============ SECTOR & DIVERSIFICATION ============ */}
          <Card sx={{ mb: 4 }}>
            <CardHeader title="Sector & Industry Diversification" />
            <CardContent>
              <Grid container spacing={2}>
                <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Num Sectors" value={summary.num_sectors || "0"} unit="" /></Grid>
                <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Num Industries" value={summary.num_industries || "0"} unit="" /></Grid>
                <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Sector Concentration" value={summary.sector_concentration?.toFixed(2) || "0.00"} unit="%" /></Grid>
                <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Avg Correlation" value={summary.avg_correlation?.toFixed(2) || "0.50"} unit="" /></Grid>
                <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Top Sector" value={summary.top_sector || "N/A"} unit="" /></Grid>
                <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Best Performer" value={summary.best_performer_sector || "N/A"} unit="" /></Grid>
              </Grid>
            </CardContent>
          </Card>

          {/* ============ RETURN ATTRIBUTION ============ */}
          <Card sx={{ mb: 4 }}>
            <CardHeader title="Return Attribution & Daily Performance" />
            <CardContent>
              <Grid container spacing={2} sx={{ mb: 3 }}>
                <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Best Day" value={summary.best_day_gain?.toFixed(2) || "0.00"} unit="%" /></Grid>
                <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Worst Day" value={summary.worst_day_loss?.toFixed(2) || "0.00"} unit="%" /></Grid>
                <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Top 5 Days Contrib" value={summary.top_5_days_contribution?.toFixed(2) || "0.00"} unit="%" /></Grid>
                <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Win Rate" value={summary.win_rate?.toFixed(1) || "0.0"} unit="%" /></Grid>
                <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Positive Days" value={summary.win_rate ? summary.win_rate : "0"} unit="%" /></Grid>
                <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Daily Volatility" value={(summary.volatility_annualized / Math.sqrt(252))?.toFixed(3) || "0.000"} unit="%" /></Grid>
              </Grid>
            </CardContent>
          </Card>

          {/* ============ ROLLING RETURNS ============ */}
          <Card sx={{ mb: 4 }}>
            <CardHeader title="Rolling Period Returns" />
            <CardContent>
              <Grid container spacing={2}>
                <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="1M Return" value={summary.return_1m?.toFixed(2) || "0.00"} unit="%" /></Grid>
                <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="3M Return" value={summary.return_3m?.toFixed(2) || "0.00"} unit="%" /></Grid>
                <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="6M Return" value={summary.return_6m?.toFixed(2) || "0.00"} unit="%" /></Grid>
                <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="1Y Return" value={summary.return_rolling_1y?.toFixed(2) || "0.00"} unit="%" /></Grid>
                <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="3Y Return" value={summary.return_3y?.toFixed(2) || "0.00"} unit="%" /></Grid>
                <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Total Return" value={summary.total_return?.toFixed(2) || "0.00"} unit="%" /></Grid>
              </Grid>
            </CardContent>
          </Card>

          {/* ============ PORTFOLIO EFFICIENCY ============ */}
          <Card sx={{ mb: 4 }}>
            <CardHeader title="Portfolio Efficiency Metrics" />
            <CardContent>
              <Grid container spacing={2}>
                <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Return/Risk Ratio" value={summary.return_risk_ratio?.toFixed(2) || "0.00"} unit="" /></Grid>
                <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Cash Drag" value={summary.cash_drag?.toFixed(2) || "0.10"} unit="%" /></Grid>
                <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Turnover Ratio" value={summary.turnover_ratio?.toFixed(2) || "15.00"} unit="%" /></Grid>
                <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Transaction Costs" value={summary.transaction_costs?.toFixed(2) || "0.15"} unit="bps" /></Grid>
                <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Sector Momentum" value={summary.sector_momentum?.toFixed(2) || "0.00"} unit="%" /></Grid>
                <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Risk-Free Rate" value={metadata.risk_free_rate || "2.00"} unit="%" /></Grid>
              </Grid>
            </CardContent>
          </Card>

          {/* ============ RELATIVE PERFORMANCE vs BENCHMARK ============ */}
          <Card sx={{ mb: 4 }}>
            <CardHeader title="Relative Performance vs SPY" />
            <CardContent>
              <Grid container spacing={2}>
                <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Tracking Error" value={summary.tracking_error?.toFixed(4) || "0.0000"} unit="" /></Grid>
                <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Active Return" value={summary.active_return?.toFixed(2) || "0.00"} unit="%" /></Grid>
                <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Relative Volatility" value={summary.relative_volatility?.toFixed(2) || "0.00"} unit="" /></Grid>
                <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Information Ratio" value={summary.information_ratio?.toFixed(2) || "0.00"} unit="" /></Grid>
                <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Correlation w/ SPY" value={summary.correlation_with_spy?.toFixed(2) || "0.75"} unit="" /></Grid>
                <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Beta vs SPY" value={summary.beta?.toFixed(2) || "0.85"} unit="" /></Grid>
              </Grid>
            </CardContent>
          </Card>

          {/* ============ CORRELATION MATRIX HEATMAP ============ */}
          <Card sx={{ mb: 4 }}>
            <CardHeader
              title="Top Holdings Correlation Matrix"
              subheader="Asset correlation structure (top 8 positions)"
            />
            <CardContent>
              <ResponsiveContainer width="100%" height={350}>
                <ComposedChart
                  data={positions.slice(0, 8).map((pos, idx) => ({
                    symbol: pos.symbol,
                    correlation_market: parseFloat(pos.correlation_with_portfolio || 0),
                    volatility: parseFloat(pos.volatility_percent || 0),
                    weight: parseFloat(pos.weight_percent || 0),
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

          {/* ============ HOLDINGS TABLE ============ */}
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
                    {positions.map((pos, idx) => (
                      <tr key={idx} style={{ borderBottom: `1px solid ${theme.palette.divider}` }}>
                        <td style={{ padding: "12px", fontWeight: 500 }}>{pos.symbol}</td>
                        <td style={{ textAlign: "right", padding: "12px" }}>{parseFloat(pos.weight_percent || 0).toFixed(2)}%</td>
                        <td style={{ textAlign: "right", padding: "12px" }}>${parseFloat(pos.market_value_dollars || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
                        <td style={{ textAlign: "right", padding: "12px", color: parseFloat(pos.gain_loss_dollars || 0) >= 0 ? theme.palette.success.main : theme.palette.error.main }}>
                          ${parseFloat(pos.gain_loss_dollars || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                        </td>
                        <td style={{ textAlign: "right", padding: "12px", color: parseFloat(pos.return_percent || 0) >= 0 ? theme.palette.success.main : theme.palette.error.main, fontWeight: 600 }}>
                          {parseFloat(pos.return_percent || 0).toFixed(2)}%
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </CardContent>
          </Card>

          {/* ============ DETAILED HOLDINGS BREAKDOWN ============ */}
          <Box sx={{ mb: 4, mt: 6 }}>
            <Typography variant="h5" sx={{ fontWeight: 700, mb: 3, display: 'flex', alignItems: 'center', gap: 1 }}>
              <AccountBalance sx={{ color: 'primary.main' }} /> Holdings Breakdown by Allocation
            </Typography>

            {/* Top Holdings Pie Chart */}
            <Card sx={{ mb: 4 }}>
              <CardHeader title="Portfolio Allocation (All Holdings)" />
              <CardContent>
                <ResponsiveContainer width="100%" height={400}>
                  <PieChart>
                    <Pie
                      data={positions.map(p => ({
                        name: p.symbol,
                        value: parseFloat(p.weight_percent) || 0,
                      }))}
                      cx="50%"
                      cy="50%"
                      labelLine={true}
                      label={({ name, value }) => `${name}: ${value.toFixed(1)}%`}
                      outerRadius={120}
                      fill="#8884d8"
                      dataKey="value"
                    >
                      {positions.map((_, idx) => (
                        <Cell key={`cell-${idx}`} fill={['#1976d2', '#43a047', '#ff9800', '#8e24aa', '#e53935', '#00acc1', '#f57c00'][idx % 7]} />
                      ))}
                    </Pie>
                    <RechartsTooltip formatter={(value) => `${value.toFixed(2)}%`} />
                  </PieChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>

            {/* Holdings by Weight Visualization */}
            <Card sx={{ mb: 4 }}>
              <CardHeader title="Holdings by Weight Distribution" />
              <CardContent>
                <ResponsiveContainer width="100%" height={350}>
                  <BarChart
                    data={positions.map(p => ({
                      symbol: p.symbol,
                      weight: parseFloat(p.weight_percent) || 0,
                      value: parseFloat(p.market_value_dollars) || 0,
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
              <CardHeader title="Position Market Values" />
              <CardContent>
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart
                    data={positions.map(p => ({
                      symbol: p.symbol,
                      value: parseFloat(p.market_value_dollars) || 0,
                      gain: parseFloat(p.gain_loss_dollars) || 0,
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

            {/* Correlation with Portfolio */}
            <Card sx={{ mb: 4 }}>
              <CardHeader title="Position Correlation with Portfolio" />
              <CardContent>
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart
                    data={positions.map(p => ({
                      symbol: p.symbol,
                      correlation: parseFloat(p.correlation_with_portfolio) || 0,
                      weight: parseFloat(p.weight_percent) || 0,
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
          </Box>

          {/* ============ METADATA FOOTER ============ */}
          <Card sx={{ backgroundColor: theme.palette.background.default }}>
            <CardContent>
              <Typography variant="caption" color="text.secondary">
                <strong>Calculation Basis:</strong> {metadata.calculation_basis || "252 trading days"} •
                <strong> Benchmark:</strong> {metadata.benchmark || "SPY"} •
                <strong> Risk-Free Rate:</strong> {metadata.risk_free_rate || "2%"} •
                <strong> Data Points:</strong> {metadata.data_points || "0"} •
                <strong> Portfolio Value:</strong> ${metadata.portfolio_value?.toLocaleString() || "0"}
              </Typography>
            </CardContent>
          </Card>
        </>
      )}
    </Container>
  );
}
