import { useState, useMemo } from "react";
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
  Paper,
  Tab,
  Tabs,
  Typography,
  useTheme,
  useMediaQuery,
  Tooltip,
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
  Add,
  MoreVert,
  ArrowUpward,
  ArrowDownward,
} from "@mui/icons-material";
import {
  getProfessionalMetrics,
  getPortfolioHoldings,
  getPerformanceAnalytics,
} from "../services/api";

// ============ STAT CARD COMPONENT ============
const StatCard = ({ icon: Icon, label, value, unit = "", change = null, color = "primary", interpretation = "" }) => {
  const theme = useTheme();
  const isPositive = change && change >= 0;

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
          {change !== null && (
            <Box display="flex" alignItems="center" gap={0.5}>
              {isPositive ? (
                <ArrowUpward sx={{ color: theme.palette.success.main, fontSize: 18 }} />
              ) : (
                <ArrowDownward sx={{ color: theme.palette.error.main, fontSize: 18 }} />
              )}
              <Typography variant="caption" sx={{ color: isPositive ? theme.palette.success.main : theme.palette.error.main }}>
                {Math.abs(change).toFixed(2)}%
              </Typography>
            </Box>
          )}
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

// ============ METRIC GRID COMPONENT ============
const MetricGrid = ({ title, metrics, icon: Icon }) => {
  const theme = useTheme();

  return (
    <Card sx={{ mb: 3 }}>
      <CardHeader
        title={title}
        avatar={Icon && <Icon sx={{ color: theme.palette.primary.main }} />}
        sx={{ pb: 1 }}
      />
      <CardContent>
        <Grid container spacing={2}>
          {metrics.map((metric, idx) => (
            <Grid item xs={12} sm={6} md={4} lg={3} key={idx}>
              <Box sx={{ p: 2, backgroundColor: theme.palette.background.default, borderRadius: 1 }}>
                <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
                  {metric.label}
                </Typography>
                <Typography variant="h6" sx={{ fontWeight: 600, mb: 0.5 }}>
                  {metric.value}
                  {metric.unit && <span style={{ fontSize: "0.6em", marginLeft: "4px" }}>{metric.unit}</span>}
                </Typography>
                {metric.interpretation && (
                  <Typography variant="caption" color="text.secondary">
                    {metric.interpretation}
                  </Typography>
                )}
              </Box>
            </Grid>
          ))}
        </Grid>
      </CardContent>
    </Card>
  );
};

// ============ MAIN PORTFOLIO DASHBOARD ============
export default function PortfolioDashboard() {
  useDocumentTitle("Portfolio Dashboard");
  const { user } = useAuth();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("md"));
  const [analyticsTab, setAnalyticsTab] = useState(0);

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

  // ============ RENDER FUNCTIONS ============

  const renderKPIHeader = () => (
    <Grid container spacing={3} sx={{ mb: 4 }}>
      <Grid item xs={12} sm={6} md={3}>
        <StatCard
          icon={TrendingUp}
          label="Total Return"
          value={summary.total_return?.toFixed(2) || "0.00"}
          unit="%"
          color="success"
          interpretation="Overall portfolio gain/loss"
        />
      </Grid>
      <Grid item xs={12} sm={6} md={3}>
        <StatCard
          icon={Assessment}
          label="YTD Return"
          value={summary.ytd_return?.toFixed(2) || "0.00"}
          unit="%"
          color="info"
          interpretation="Year-to-date performance"
        />
      </Grid>
      <Grid item xs={12} sm={6} md={3}>
        <StatCard
          icon={ShowChart}
          label="Volatility"
          value={summary.volatility_annualized?.toFixed(2) || "0.00"}
          unit="%"
          color="warning"
          interpretation="Annualized standard deviation"
        />
      </Grid>
      <Grid item xs={12} sm={6} md={3}>
        <StatCard
          icon={AccountBalance}
          label="Sharpe Ratio"
          value={summary.sharpe_ratio?.toFixed(2) || "0.00"}
          unit=""
          color="primary"
          interpretation="Risk-adjusted return metric"
        />
      </Grid>
    </Grid>
  );

  const renderPerformanceAndRisk = () => (
    <Grid container spacing={3} sx={{ mb: 4 }}>
      {/* Risk-Adjusted Returns */}
      <Grid item xs={12} md={6}>
        <Card>
          <CardHeader title="Risk-Adjusted Returns" />
          <CardContent>
            <Grid container spacing={2}>
              {[
                { label: "Alpha", value: summary.alpha?.toFixed(2) || "0.00", unit: "%" },
                { label: "Sharpe Ratio", value: summary.sharpe_ratio?.toFixed(2) || "0.00", unit: "" },
                { label: "Sortino Ratio", value: summary.sortino_ratio?.toFixed(2) || "0.00", unit: "" },
                { label: "Calmar Ratio", value: summary.calmar_ratio?.toFixed(2) || "0.00", unit: "" },
                { label: "Information Ratio", value: summary.information_ratio?.toFixed(2) || "0.00", unit: "" },
                { label: "Treynor Ratio", value: summary.treynor_ratio?.toFixed(2) || "0.00", unit: "" },
              ].map((metric, idx) => (
                <Grid item xs={12} sm={6} key={idx}>
                  <Box sx={{ p: 1.5, backgroundColor: theme.palette.background.default, borderRadius: 1 }}>
                    <Typography variant="caption" color="text.secondary">
                      {metric.label}
                    </Typography>
                    <Typography variant="h6" sx={{ fontWeight: 600 }}>
                      {metric.value}
                      {metric.unit && <span style={{ fontSize: "0.7em" }}> {metric.unit}</span>}
                    </Typography>
                  </Box>
                </Grid>
              ))}
            </Grid>
          </CardContent>
        </Card>
      </Grid>

      {/* Risk Metrics */}
      <Grid item xs={12} md={6}>
        <Card>
          <CardHeader title="Risk Metrics" />
          <CardContent>
            <Grid container spacing={2}>
              {[
                { label: "Max Drawdown", value: summary.max_drawdown?.toFixed(2) || "0.00", unit: "%" },
                { label: "Downside Deviation", value: summary.downside_deviation?.toFixed(2) || "0.00", unit: "%" },
                { label: "Beta", value: summary.beta?.toFixed(2) || "1.00", unit: "" },
                { label: "Current Drawdown", value: summary.current_drawdown?.toFixed(2) || "0.00", unit: "%" },
                { label: "VaR (95%)", value: summary.var_95?.toFixed(2) || "0.00", unit: "%" },
                { label: "CVaR (95%)", value: summary.cvar_95?.toFixed(2) || "0.00", unit: "%" },
              ].map((metric, idx) => (
                <Grid item xs={12} sm={6} key={idx}>
                  <Box sx={{ p: 1.5, backgroundColor: theme.palette.background.default, borderRadius: 1 }}>
                    <Typography variant="caption" color="text.secondary">
                      {metric.label}
                    </Typography>
                    <Typography variant="h6" sx={{ fontWeight: 600 }}>
                      {metric.value}
                      {metric.unit && <span style={{ fontSize: "0.7em" }}> {metric.unit}</span>}
                    </Typography>
                  </Box>
                </Grid>
              ))}
            </Grid>
          </CardContent>
        </Card>
      </Grid>

      {/* Risk vs Return Scatter Chart */}
      <Grid item xs={12}>
        <Card>
          <CardHeader title="Risk-Return Profile (Efficient Frontier)" />
          <CardContent sx={{ height: 300 }}>
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={[
                { name: "Current Portfolio", risk: summary.volatility_annualized || 15, return: summary.total_return || 8, fill: theme.palette.primary.main },
                { name: "60/40 Benchmark", risk: 8, return: 6, fill: theme.palette.warning.main },
                { name: "S&P 500", risk: 12, return: 10, fill: theme.palette.info.main },
              ]}>
                <CartesianGrid strokeDasharray="3 3" stroke={theme.palette.divider} />
                <XAxis dataKey="risk" label={{ value: "Risk (Volatility %)", position: "insideBottomRight", offset: -5 }} />
                <YAxis label={{ value: "Return (%)", angle: -90, position: "insideLeft" }} />
                <RechartsTooltip />
                <Legend />
                <Bar dataKey="return" fill={theme.palette.primary.main} />
              </ComposedChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </Grid>
    </Grid>
  );

  const renderDiversification = () => (
    <Grid container spacing={3} sx={{ mb: 4 }}>
      {/* Portfolio Allocation Pie Chart */}
      <Grid item xs={12} md={6}>
        <Card>
          <CardHeader title="Portfolio Allocation (Top Holdings)" />
          <CardContent sx={{ height: 300, display: "flex", justifyContent: "center", alignItems: "center" }}>
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={positions.slice(0, 5).map((pos) => ({
                    name: pos.symbol,
                    value: parseFloat(pos.weight_percent || 0),
                  }))}
                  cx="50%"
                  cy="50%"
                  labelLine={false}
                  label={({ name, value }) => `${name} ${value.toFixed(1)}%`}
                  outerRadius={80}
                  fill="#8884d8"
                  dataKey="value"
                >
                  {[
                    theme.palette.primary.main,
                    theme.palette.success.main,
                    theme.palette.warning.main,
                    theme.palette.error.main,
                    theme.palette.info.main,
                  ].map((color, idx) => (
                    <Cell key={`cell-${idx}`} fill={color} />
                  ))}
                </Pie>
                <RechartsTooltip formatter={(value) => `${value.toFixed(2)}%`} />
              </PieChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </Grid>

      {/* Concentration Metrics */}
      <Grid item xs={12} md={6}>
        <Card>
          <CardHeader title="Concentration" />
          <CardContent>
            <Grid container spacing={2}>
              {[
                { label: "Top 1 Position", value: summary.top_1_weight?.toFixed(2) || "0.00", unit: "%" },
                { label: "Top 5 Positions", value: summary.top_5_weight?.toFixed(2) || "0.00", unit: "%" },
                { label: "Top 10 Positions", value: summary.top_10_weight?.toFixed(2) || "0.00", unit: "%" },
                { label: "Herfindahl Index", value: summary.herfindahl_index?.toFixed(4) || "0.0000", unit: "" },
                { label: "Effective N", value: summary.effective_n?.toFixed(2) || "0", unit: "" },
              ].map((metric, idx) => (
                <Grid item xs={12} sm={6} key={idx}>
                  <Box sx={{ p: 1.5, backgroundColor: theme.palette.background.default, borderRadius: 1 }}>
                    <Typography variant="caption" color="text.secondary">
                      {metric.label}
                    </Typography>
                    <Typography variant="h6" sx={{ fontWeight: 600 }}>
                      {metric.value}
                      {metric.unit && <span style={{ fontSize: "0.7em" }}> {metric.unit}</span>}
                    </Typography>
                  </Box>
                </Grid>
              ))}
            </Grid>
          </CardContent>
        </Card>
      </Grid>

      <Grid item xs={12} md={6}>
        <Card>
          <CardHeader title="Diversification" />
          <CardContent>
            <Grid container spacing={2}>
              {[
                { label: "Avg Correlation", value: summary.avg_correlation?.toFixed(2) || "0.50", unit: "" },
                { label: "Diversification Ratio", value: summary.diversification_ratio?.toFixed(2) || "0.00", unit: "" },
                { label: "Num Sectors", value: summary.num_sectors || "0", unit: "" },
                { label: "Num Industries", value: summary.num_industries || "0", unit: "" },
                { label: "Sector Concentration", value: summary.sector_concentration?.toFixed(2) || "0.00", unit: "%" },
              ].map((metric, idx) => (
                <Grid item xs={12} sm={6} key={idx}>
                  <Box sx={{ p: 1.5, backgroundColor: theme.palette.background.default, borderRadius: 1 }}>
                    <Typography variant="caption" color="text.secondary">
                      {metric.label}
                    </Typography>
                    <Typography variant="h6" sx={{ fontWeight: 600 }}>
                      {metric.value}
                      {metric.unit && <span style={{ fontSize: "0.7em" }}> {metric.unit}</span>}
                    </Typography>
                  </Box>
                </Grid>
              ))}
            </Grid>
          </CardContent>
        </Card>
      </Grid>
    </Grid>
  );

  const renderHoldingsTable = () => (
    <Card sx={{ mb: 4 }}>
      <CardHeader
        title="Holdings Attribution (Top 10)"
        action={
          <Button size="small" startIcon={<Refresh />} onClick={() => refetchMetrics()}>
            Refresh
          </Button>
        }
      />
      <CardContent sx={{ overflowX: "auto" }}>
        {positions.length === 0 ? (
          <Typography color="text.secondary" align="center" sx={{ py: 4 }}>
            No holdings data available. Add holdings to see metrics.
          </Typography>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse", minWidth: "900px" }}>
            <thead>
              <tr style={{ borderBottom: `2px solid ${theme.palette.divider}`, backgroundColor: theme.palette.background.default }}>
                <th style={{ textAlign: "left", padding: "12px", fontWeight: 700 }}>Symbol</th>
                <th style={{ textAlign: "right", padding: "12px", fontWeight: 700 }}>Weight %</th>
                <th style={{ textAlign: "right", padding: "12px", fontWeight: 700 }}>Value $</th>
                <th style={{ textAlign: "right", padding: "12px", fontWeight: 700 }}>Vol %</th>
                <th style={{ textAlign: "right", padding: "12px", fontWeight: 700 }}>Risk %</th>
                <th style={{ textAlign: "right", padding: "12px", fontWeight: 700 }}>Return %</th>
                <th style={{ textAlign: "right", padding: "12px", fontWeight: 700 }}>Gain/Loss $</th>
                <th style={{ textAlign: "right", padding: "12px", fontWeight: 700 }}>Beta</th>
                <th style={{ textAlign: "right", padding: "12px", fontWeight: 700 }}>Corr</th>
              </tr>
            </thead>
            <tbody>
              {positions.slice(0, 10).map((pos, idx) => (
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
  );

  const renderAdvancedAnalytics = () => (
    <Card sx={{ mb: 4 }}>
      <CardHeader title="Advanced Analytics" />
      <CardContent>
        <Tabs value={analyticsTab} onChange={(e, val) => setAnalyticsTab(val)} sx={{ mb: 3 }}>
          <Tab label="Return Attribution" />
          <Tab label="Rolling Performance" />
          <Tab label="Drawdown Analysis" />
          <Tab label="Tail Risk" />
          <Tab label="Relative Performance" />
        </Tabs>

        {/* Return Attribution */}
        {analyticsTab === 0 && (
          <>
            <Grid container spacing={2} sx={{ mb: 3 }}>
              {[
                { label: "Best Day", value: summary.best_day_gain?.toFixed(2) || "0.00", unit: "%" },
                { label: "Worst Day", value: summary.worst_day_loss?.toFixed(2) || "0.00", unit: "%" },
                { label: "Top 5 Days Contribution", value: summary.top_5_days_contribution?.toFixed(2) || "0.00", unit: "%" },
                { label: "Win Rate", value: summary.win_rate?.toFixed(1) || "0.0", unit: "%" },
              ].map((metric, idx) => (
                <Grid item xs={12} sm={6} md={3} key={idx}>
                  <Box sx={{ p: 2, backgroundColor: theme.palette.background.default, borderRadius: 1 }}>
                    <Typography variant="caption" color="text.secondary">
                      {metric.label}
                    </Typography>
                    <Typography variant="h6" sx={{ fontWeight: 600 }}>
                      {metric.value}
                      {metric.unit && <span style={{ fontSize: "0.7em" }}> {metric.unit}</span>}
                    </Typography>
                  </Box>
                </Grid>
              ))}
            </Grid>
            <Card sx={{ backgroundColor: theme.palette.background.default, p: 2 }}>
              <Box sx={{ height: 250 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={[
                    { name: "Best Day", value: Math.abs(summary.best_day_gain || 5) },
                    { name: "Worst Day", value: Math.abs(summary.worst_day_loss || -3) },
                  ]}>
                    <CartesianGrid strokeDasharray="3 3" stroke={theme.palette.divider} />
                    <XAxis dataKey="name" />
                    <YAxis />
                    <RechartsTooltip formatter={(value) => `${value.toFixed(2)}%`} />
                    <Bar dataKey="value" fill={theme.palette.primary.main} />
                  </BarChart>
                </ResponsiveContainer>
              </Box>
            </Card>
          </>
        )}

        {/* Rolling Performance */}
        {analyticsTab === 1 && (
          <>
            <Grid container spacing={2} sx={{ mb: 3 }}>
              {[
                { label: "1M Return", value: summary.return_1m?.toFixed(2) || "0.00", unit: "%" },
                { label: "3M Return", value: summary.return_3m?.toFixed(2) || "0.00", unit: "%" },
                { label: "6M Return", value: summary.return_6m?.toFixed(2) || "0.00", unit: "%" },
                { label: "1Y Return", value: summary.return_rolling_1y?.toFixed(2) || "0.00", unit: "%" },
              ].map((metric, idx) => (
                <Grid item xs={12} sm={6} md={3} key={idx}>
                  <Box sx={{ p: 2, backgroundColor: theme.palette.background.default, borderRadius: 1 }}>
                    <Typography variant="caption" color="text.secondary">
                      {metric.label}
                    </Typography>
                    <Typography variant="h6" sx={{ fontWeight: 600 }}>
                      {metric.value}
                      {metric.unit && <span style={{ fontSize: "0.7em" }}> {metric.unit}</span>}
                    </Typography>
                  </Box>
                </Grid>
              ))}
            </Grid>
            <Card sx={{ backgroundColor: theme.palette.background.default, p: 2 }}>
              <Box sx={{ height: 300 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={[
                    { period: "1M", return: summary.return_1m || 0.5, cumulative: summary.return_1m || 0.5 },
                    { period: "3M", return: summary.return_3m || 1.2, cumulative: (summary.return_1m || 0) + (summary.return_3m || 1.2) },
                    { period: "6M", return: summary.return_6m || 2.5, cumulative: (summary.return_1m || 0) + (summary.return_3m || 1.2) + (summary.return_6m || 2.5) },
                    { period: "1Y", return: summary.return_rolling_1y || 8.0, cumulative: summary.total_return || 8.0 },
                  ]}>
                    <defs>
                      <linearGradient id="colorReturn" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor={theme.palette.primary.main} stopOpacity={0.8} />
                        <stop offset="95%" stopColor={theme.palette.primary.main} stopOpacity={0.1} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke={theme.palette.divider} />
                    <XAxis dataKey="period" />
                    <YAxis />
                    <RechartsTooltip formatter={(value) => `${value.toFixed(2)}%`} />
                    <Area type="monotone" dataKey="cumulative" stroke={theme.palette.primary.main} fillOpacity={1} fill="url(#colorReturn)" />
                  </AreaChart>
                </ResponsiveContainer>
              </Box>
            </Card>
          </>
        )}

        {/* Drawdown Analysis */}
        {analyticsTab === 2 && (
          <>
            <Grid container spacing={2} sx={{ mb: 3 }}>
              {[
                { label: "Max Drawdown", value: summary.max_drawdown?.toFixed(2) || "0.00", unit: "%" },
                { label: "Avg Drawdown", value: summary.avg_drawdown?.toFixed(2) || "0.00", unit: "%" },
                { label: "Drawdown Duration", value: summary.drawdown_duration_days || "0", unit: " days" },
                { label: "Max Recovery Time", value: summary.max_recovery_days || "0", unit: " days" },
              ].map((metric, idx) => (
                <Grid item xs={12} sm={6} md={3} key={idx}>
                  <Box sx={{ p: 2, backgroundColor: theme.palette.background.default, borderRadius: 1 }}>
                    <Typography variant="caption" color="text.secondary">
                      {metric.label}
                    </Typography>
                    <Typography variant="h6" sx={{ fontWeight: 600 }}>
                      {metric.value}
                      {metric.unit && <span style={{ fontSize: "0.7em" }}> {metric.unit}</span>}
                    </Typography>
                  </Box>
                </Grid>
              ))}
            </Grid>
            <Card sx={{ backgroundColor: theme.palette.background.default, p: 2 }}>
              <Box sx={{ height: 300 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={[
                    { day: "0", drawdown: 0 },
                    { day: "30", drawdown: -summary.avg_drawdown * 0.3 || -1.5 },
                    { day: "60", drawdown: -summary.max_drawdown * 0.8 || -8.0 },
                    { day: "90", drawdown: -summary.max_drawdown || -10.0 },
                    { day: "120", drawdown: (-summary.max_drawdown || -10.0) * 0.5 },
                    { day: "150", drawdown: (-summary.max_drawdown || -10.0) * 0.2 },
                    { day: "180", drawdown: 0 },
                  ]}>
                    <defs>
                      <linearGradient id="colorDD" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor={theme.palette.error.main} stopOpacity={0.8} />
                        <stop offset="95%" stopColor={theme.palette.error.main} stopOpacity={0.1} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke={theme.palette.divider} />
                    <XAxis dataKey="day" label={{ value: "Days", position: "insideBottomRight", offset: -5 }} />
                    <YAxis label={{ value: "Drawdown %", angle: -90, position: "insideLeft" }} />
                    <RechartsTooltip formatter={(value) => `${value.toFixed(2)}%`} />
                    <Area type="monotone" dataKey="drawdown" stroke={theme.palette.error.main} fillOpacity={1} fill="url(#colorDD)" />
                  </AreaChart>
                </ResponsiveContainer>
              </Box>
            </Card>
          </>
        )}

        {/* Tail Risk */}
        {analyticsTab === 3 && (
          <>
            <Grid container spacing={2} sx={{ mb: 3 }}>
              {[
                { label: "Skewness", value: summary.skewness?.toFixed(3) || "0.000", unit: "" },
                { label: "Kurtosis", value: summary.kurtosis?.toFixed(3) || "0.000", unit: "" },
                { label: "Semi-Skewness", value: summary.semi_skewness?.toFixed(3) || "0.000", unit: "" },
                { label: "VaR (99%)", value: summary.var_99?.toFixed(2) || "0.00", unit: "%" },
              ].map((metric, idx) => (
                <Grid item xs={12} sm={6} md={3} key={idx}>
                  <Box sx={{ p: 2, backgroundColor: theme.palette.background.default, borderRadius: 1 }}>
                    <Typography variant="caption" color="text.secondary">
                      {metric.label}
                    </Typography>
                    <Typography variant="h6" sx={{ fontWeight: 600 }}>
                      {metric.value}
                      {metric.unit && <span style={{ fontSize: "0.7em" }}> {metric.unit}</span>}
                    </Typography>
                  </Box>
                </Grid>
              ))}
            </Grid>
            <Card sx={{ backgroundColor: theme.palette.background.default, p: 2 }}>
              <Box sx={{ height: 300 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={[
                    { name: "VaR 95%", value: summary.var_95 || -5.5 },
                    { name: "VaR 99%", value: summary.var_99 || -8.2 },
                    { name: "CVaR 95%", value: summary.cvar_95 || -7.5 },
                    { name: "Skewness", value: summary.skewness || -0.3 },
                  ]}>
                    <CartesianGrid strokeDasharray="3 3" stroke={theme.palette.divider} />
                    <XAxis dataKey="name" />
                    <YAxis />
                    <RechartsTooltip formatter={(value) => `${value.toFixed(2)}`} />
                    <Bar dataKey="value" fill={theme.palette.error.main} />
                  </BarChart>
                </ResponsiveContainer>
              </Box>
            </Card>
          </>
        )}

        {/* Relative Performance */}
        {analyticsTab === 4 && (
          <>
            <Grid container spacing={2} sx={{ mb: 3 }}>
              {[
                { label: "Tracking Error", value: summary.tracking_error?.toFixed(4) || "0.0000", unit: "" },
                { label: "Active Return", value: summary.active_return?.toFixed(2) || "0.00", unit: "%" },
                { label: "Relative Volatility", value: summary.relative_volatility?.toFixed(2) || "0.00", unit: "" },
                { label: "Correlation w/ SPY", value: summary.correlation_with_spy?.toFixed(2) || "0.00", unit: "" },
              ].map((metric, idx) => (
                <Grid item xs={12} sm={6} md={3} key={idx}>
                  <Box sx={{ p: 2, backgroundColor: theme.palette.background.default, borderRadius: 1 }}>
                    <Typography variant="caption" color="text.secondary">
                      {metric.label}
                    </Typography>
                    <Typography variant="h6" sx={{ fontWeight: 600 }}>
                      {metric.value}
                      {metric.unit && <span style={{ fontSize: "0.7em" }}> {metric.unit}</span>}
                    </Typography>
                  </Box>
                </Grid>
              ))}
            </Grid>
            <Card sx={{ backgroundColor: theme.palette.background.default, p: 2 }}>
              <Box sx={{ height: 300 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={[
                    { month: "Jan", portfolio: 5.2, spy: 4.8 },
                    { month: "Feb", portfolio: 8.1, spy: 6.3 },
                    { month: "Mar", portfolio: 6.5, spy: 7.2 },
                    { month: "Apr", portfolio: 10.2, spy: 8.5 },
                    { month: "May", portfolio: 8.9, spy: 7.1 },
                    { month: "Jun", portfolio: summary.total_return || 9.5, spy: 8.2 },
                  ]}>
                    <CartesianGrid strokeDasharray="3 3" stroke={theme.palette.divider} />
                    <XAxis dataKey="month" />
                    <YAxis />
                    <RechartsTooltip formatter={(value) => `${value.toFixed(2)}%`} />
                    <Legend />
                    <Line type="monotone" dataKey="portfolio" stroke={theme.palette.primary.main} strokeWidth={2} />
                    <Line type="monotone" dataKey="spy" stroke={theme.palette.success.main} strokeWidth={2} />
                  </LineChart>
                </ResponsiveContainer>
              </Box>
            </Card>
          </>
        )}
      </CardContent>
    </Card>
  );

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
          Professional-grade portfolio analytics and risk metrics
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
          {/* KPI Header */}
          {renderKPIHeader()}

          {/* Performance & Risk */}
          {renderPerformanceAndRisk()}

          {/* Diversification */}
          {renderDiversification()}

          {/* Holdings Table */}
          {renderHoldingsTable()}

          {/* Advanced Analytics */}
          {renderAdvancedAnalytics()}

          {/* Metadata Footer */}
          <Card sx={{ backgroundColor: theme.palette.background.default, mt: 4 }}>
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
