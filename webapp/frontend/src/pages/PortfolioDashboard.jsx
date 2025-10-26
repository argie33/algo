import { useMemo } from "react";
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
  getPortfolioHoldings,
  getPerformanceAnalytics,
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

  // Fetch professional metrics
  const { data: metricsData, isLoading: metricsLoading, refetch: refetchMetrics } = useQuery({
    queryKey: ["professionalMetrics"],
    queryFn: () => getProfessionalMetrics(),
    staleTime: 60000,
  });

  const { data: holdingsData, isLoading: holdingsLoading } = useQuery({
    queryKey: ["portfolioHoldings"],
    queryFn: () => getPortfolioHoldings(),
    staleTime: 120000,
  });

  const { data: performanceData, isLoading: perfLoading } = useQuery({
    queryKey: ["performanceAnalytics"],
    queryFn: () => getPerformanceAnalytics("1y", "SPY"),
    staleTime: 60000,
  });

  // Extract metrics
  const summary = metricsData?.data?.summary || {};
  const positions = metricsData?.data?.positions || [];
  const metadata = metricsData?.data?.metadata || {};

  // Prepare chart data
  const performanceChartData = useMemo(() => {
    return performanceData?.data?.daily_returns?.slice(-252).map((val, idx) => ({
      date: idx,
      return: val,
      cumulative: val,
    })) || [];
  }, [performanceData]);

  // ============ MAIN RENDER ============
  if (metricsLoading || holdingsLoading) {
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
        <Typography variant="h4" sx={{ fontWeight: 700, mb: 1 }}>
          Portfolio Dashboard
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Professional-grade portfolio analytics - All metrics on one page
        </Typography>
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
          {/* ============ KPI HEADER ============ */}
          <Grid container spacing={3} sx={{ mb: 4 }}>
            <Grid item xs={12} sm={6} md={3}>
              <StatCard
                icon={TrendingUp}
                label="Total Return"
                value={summary.total_return?.toFixed(2) || "0.00"}
                unit="%"
                color="success"
              />
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <StatCard
                icon={Assessment}
                label="Sharpe Ratio"
                value={summary.sharpe_ratio?.toFixed(2) || "0.00"}
                unit=""
                color="primary"
              />
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <StatCard
                icon={ShowChart}
                label="Volatility"
                value={summary.volatility_annualized?.toFixed(2) || "0.00"}
                unit="%"
                color="warning"
              />
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <StatCard
                icon={Warning}
                label="Max Drawdown"
                value={summary.max_drawdown?.toFixed(2) || "0.00"}
                unit="%"
                color="error"
              />
            </Grid>
          </Grid>

          {/* ============ PORTFOLIO ALLOCATION PIE CHART ============ */}
          <Card sx={{ mb: 4 }}>
            <CardHeader title="Portfolio Allocation - Top Holdings" />
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

          {/* ============ RISK vs RETURN SCATTER ============ */}
          <Card sx={{ mb: 4 }}>
            <CardHeader title="Risk-Return Profile (Efficient Frontier)" />
            <CardContent>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={[
                  { name: 'Portfolio', return: summary.total_return || 0, risk: summary.volatility_annualized || 0 },
                  { name: 'SPY Benchmark', return: 10, risk: 15 },
                ]}>
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
                  { label: 'SPY', return: 10 },
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
          <Card sx={{ mb: 4 }}>
            <CardHeader title="Risk-Adjusted Return Metrics" />
            <CardContent>
              <Grid container spacing={2}>
                <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Sharpe Ratio" value={summary.sharpe_ratio?.toFixed(3) || "0.000"} unit="" /></Grid>
                <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Sortino Ratio" value={summary.sortino_ratio?.toFixed(3) || "0.000"} unit="" /></Grid>
                <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Calmar Ratio" value={summary.calmar_ratio?.toFixed(3) || "0.000"} unit="" /></Grid>
                <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Treynor Ratio" value={summary.treynor_ratio?.toFixed(3) || "0.000"} unit="%" /></Grid>
                <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Information Ratio" value={summary.information_ratio?.toFixed(2) || "0.00"} unit="" /></Grid>
                <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Alpha" value={summary.alpha?.toFixed(2) || "0.00"} unit="%" /></Grid>
              </Grid>
            </CardContent>
          </Card>

          {/* ============ VOLATILITY & RISK ============ */}
          <Card sx={{ mb: 4 }}>
            <CardHeader title="Volatility & Risk Metrics" />
            <CardContent>
              <Grid container spacing={2}>
                <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Volatility" value={summary.volatility_annualized?.toFixed(2) || "0.00"} unit="%" /></Grid>
                <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Downside Deviation" value={summary.downside_deviation?.toFixed(2) || "0.00"} unit="%" /></Grid>
                <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Beta" value={summary.beta?.toFixed(2) || "1.00"} unit="" /></Grid>
                <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Return/Risk Ratio" value={summary.return_risk_ratio?.toFixed(2) || "0.00"} unit="" /></Grid>
                <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Treynor Ratio" value={summary.treynor_ratio?.toFixed(2) || "0.00"} unit="%" /></Grid>
                <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Max Drawdown" value={summary.max_drawdown?.toFixed(2) || "0.00"} unit="%" /></Grid>
              </Grid>
            </CardContent>
          </Card>

          {/* ============ VALUE AT RISK & TAIL RISK ============ */}
          <Card sx={{ mb: 4 }}>
            <CardHeader title="Value-at-Risk & Tail Risk Analysis" />
            <CardContent>
              <Grid container spacing={2}>
                <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="VaR 95%" value={summary.var_95?.toFixed(2) || "0.00"} unit="%" /></Grid>
                <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="VaR 99%" value={summary.var_99?.toFixed(2) || "0.00"} unit="%" /></Grid>
                <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="CVaR 95%" value={summary.cvar_95?.toFixed(2) || "0.00"} unit="%" /></Grid>
                <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Skewness" value={summary.skewness?.toFixed(3) || "0.000"} unit="" /></Grid>
                <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Kurtosis" value={summary.kurtosis?.toFixed(3) || "0.000"} unit="" /></Grid>
                <Grid item xs={12} sm={6} md={3} lg={2}><MetricBox label="Semi-Skewness" value={summary.semi_skewness?.toFixed(3) || "0.000"} unit="" /></Grid>
              </Grid>
            </CardContent>
          </Card>

          {/* ============ DRAWDOWN ANALYSIS ============ */}
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
                <table style={{ width: "100%", borderCollapse: "collapse", minWidth: "900px" }}>
                  <thead>
                    <tr style={{ borderBottom: `2px solid ${theme.palette.divider}`, backgroundColor: theme.palette.background.default }}>
                      <th style={{ textAlign: "left", padding: "12px", fontWeight: 700 }}>Symbol</th>
                      <th style={{ textAlign: "right", padding: "12px", fontWeight: 700 }}>Weight %</th>
                      <th style={{ textAlign: "right", padding: "12px", fontWeight: 700 }}>Value $</th>
                      <th style={{ textAlign: "right", padding: "12px", fontWeight: 700 }}>Volatility %</th>
                      <th style={{ textAlign: "right", padding: "12px", fontWeight: 700 }}>Risk %</th>
                      <th style={{ textAlign: "right", padding: "12px", fontWeight: 700 }}>Return %</th>
                      <th style={{ textAlign: "right", padding: "12px", fontWeight: 700 }}>Gain/Loss $</th>
                      <th style={{ textAlign: "right", padding: "12px", fontWeight: 700 }}>Beta</th>
                      <th style={{ textAlign: "right", padding: "12px", fontWeight: 700 }}>Correlation</th>
                    </tr>
                  </thead>
                  <tbody>
                    {positions.map((pos, idx) => (
                      <tr key={idx} style={{ borderBottom: `1px solid ${theme.palette.divider}` }}>
                        <td style={{ padding: "12px", fontWeight: 500 }}>{pos.symbol}</td>
                        <td style={{ textAlign: "right", padding: "12px" }}>{parseFloat(pos.weight_percent || 0).toFixed(2)}%</td>
                        <td style={{ textAlign: "right", padding: "12px" }}>${parseFloat(pos.market_value_dollars || 0).toLocaleString()}</td>
                        <td style={{ textAlign: "right", padding: "12px" }}>{parseFloat(pos.volatility_percent || 0).toFixed(2)}%</td>
                        <td style={{ textAlign: "right", padding: "12px" }}>{parseFloat(pos.risk_contribution_percent || 0).toFixed(2)}%</td>
                        <td style={{ textAlign: "right", padding: "12px", color: parseFloat(pos.return_contribution_percent || 0) >= 0 ? theme.palette.success.main : theme.palette.error.main }}>
                          {parseFloat(pos.return_contribution_percent || 0).toFixed(2)}%
                        </td>
                        <td style={{ textAlign: "right", padding: "12px", color: parseFloat(pos.gain_loss_dollars || 0) >= 0 ? theme.palette.success.main : theme.palette.error.main }}>
                          ${parseFloat(pos.gain_loss_dollars || 0).toLocaleString()}
                        </td>
                        <td style={{ textAlign: "right", padding: "12px" }}>{parseFloat(pos.beta || 1).toFixed(2)}</td>
                        <td style={{ textAlign: "right", padding: "12px" }}>{parseFloat(pos.correlation_with_portfolio || 0).toFixed(2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </CardContent>
          </Card>

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
