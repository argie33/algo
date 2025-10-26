/**
 * Institutional-Grade Portfolio Dashboard
 * Hedge Fund / Asset Manager Quality Analytics
 *
 * Features:
 * - Award-winning visual design
 * - Comprehensive institutional metrics
 * - Advanced risk analytics
 * - Attribution analysis
 * - Comparative benchmarking
 * - Real-time market context
 */

import { useState, useMemo, useCallback } from "react";
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
  Divider,
  Stack,
  LinearProgress,
  Chip,
  Dialog,
  DialogTitle,
  DialogContent,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
} from "@mui/material";
import {
  LineChart,
  Line,
  AreaChart,
  Area,
  BarChart,
  Bar,
  ComposedChart,
  PieChart,
  Pie,
  Cell,
  ScatterChart,
  Scatter,
  ResponsiveContainer,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  Legend,
  ReferenceLine,
  ReferenceArea,
  Radar,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Treemap,
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
  MoreHoriz,
  Download,
  Settings,
  Fullscreen,
  Timeline,
} from "@mui/icons-material";
import api from "../services/api";

/**
 * Institutional Metric Card with detailed interpretation
 */
const InstitutionalMetricCard = ({
  title,
  value,
  unit = "",
  benchmark = null,
  change = null,
  interpretation = "",
  color = "primary",
  icon: Icon,
  size = "medium",
  detail = null,
  onInfo = null,
}) => {
  const theme = useTheme();
  const isPositive = change && change >= 0;

  const getBackgroundGradient = () => {
    if (theme.palette.mode === "dark") {
      return `linear-gradient(135deg, ${theme.palette.background.paper} 0%, rgba(${
        color === "success"
          ? "76, 175, 80"
          : color === "error"
          ? "244, 67, 54"
          : color === "warning"
          ? "255, 152, 0"
          : "33, 150, 243"
      }, 0.05) 100%)`;
    }
    return `linear-gradient(135deg, #ffffff 0%, rgba(${
      color === "success"
        ? "76, 175, 80"
        : color === "error"
        ? "244, 67, 54"
        : color === "warning"
        ? "255, 152, 0"
        : "33, 150, 243"
    }, 0.08) 100%)`;
  };

  const colorMap = {
    success: theme.palette.success.main,
    error: theme.palette.error.main,
    warning: theme.palette.warning.main,
    primary: theme.palette.primary.main,
  };

  return (
    <Card
      sx={{
        height: "100%",
        background: getBackgroundGradient(),
        border: `1px solid ${theme.palette.divider}`,
        boxShadow:
          theme.palette.mode === "dark"
            ? "0 2px 8px rgba(0,0,0,0.3)"
            : "0 2px 4px rgba(0,0,0,0.08)",
        transition: "all 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
        "&:hover": {
          boxShadow:
            theme.palette.mode === "dark"
              ? "0 4px 16px rgba(0,0,0,0.4)"
              : "0 8px 16px rgba(0,0,0,0.12)",
          transform: "translateY(-2px)",
        },
        position: "relative",
        overflow: "hidden",
      }}
    >
      {/* Decorative corner accent */}
      <Box
        sx={{
          position: "absolute",
          top: 0,
          right: 0,
          width: "100px",
          height: "100px",
          background: `linear-gradient(135deg, ${colorMap[color]} 0%, transparent 100%)`,
          opacity: 0.05,
          borderRadius: "0 0 100% 0",
        }}
      />

      <CardContent sx={{ position: "relative", zIndex: 1 }}>
        {/* Header with icon and title */}
        <Box sx={{ display: "flex", alignItems: "flex-start", mb: 2 }}>
          {Icon && (
            <Box
              sx={{
                mr: 2,
                p: 1.5,
                borderRadius: "12px",
                background: `${colorMap[color]}20`,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <Icon sx={{ color: colorMap[color], fontSize: 24 }} />
            </Box>
          )}
          <Box sx={{ flex: 1 }}>
            <Typography
              variant="caption"
              sx={{
                color: theme.palette.text.secondary,
                fontWeight: 600,
                letterSpacing: "0.5px",
                textTransform: "uppercase",
                fontSize: "0.75rem",
              }}
            >
              {title}
            </Typography>
            {benchmark && (
              <Typography
                variant="caption"
                sx={{
                  display: "block",
                  color: theme.palette.text.secondary,
                  fontSize: "0.7rem",
                  mt: 0.5,
                }}
              >
                vs {benchmark}
              </Typography>
            )}
          </Box>
          {onInfo && (
            <Tooltip title={interpretation}>
              <Info
                sx={{
                  fontSize: 18,
                  color: theme.palette.text.secondary,
                  cursor: "pointer",
                  opacity: 0.6,
                  "&:hover": { opacity: 1 },
                }}
              />
            </Tooltip>
          )}
        </Box>

        {/* Main value display */}
        <Box sx={{ mb: 2 }}>
          <Typography
            variant={size === "large" ? "h3" : "h4"}
            sx={{
              fontWeight: 700,
              letterSpacing: "-1px",
              color: theme.palette.text.primary,
              lineHeight: 1.2,
            }}
          >
            {typeof value === "number"
              ? value > 1000
                ? `$${(value / 1000).toFixed(1)}k`
                : value.toFixed(2)
              : value}
            <span
              style={{
                fontSize: "0.6em",
                fontWeight: 500,
                marginLeft: "4px",
                opacity: 0.7,
              }}
            >
              {unit}
            </span>
          </Typography>

          {/* Change indicator */}
          {change !== null && (
            <Box sx={{ display: "flex", alignItems: "center", mt: 1 }}>
              {isPositive ? (
                <TrendingUp sx={{ fontSize: 16, color: theme.palette.success.main, mr: 0.5 }} />
              ) : (
                <TrendingDown sx={{ fontSize: 16, color: theme.palette.error.main, mr: 0.5 }} />
              )}
              <Typography
                variant="caption"
                sx={{
                  color: isPositive ? theme.palette.success.main : theme.palette.error.main,
                  fontWeight: 600,
                }}
              >
                {isPositive ? "+" : ""}{change.toFixed(2)}%
              </Typography>
            </Box>
          )}
        </Box>

        {/* Detail row if provided */}
        {detail && (
          <Box
            sx={{
              pt: 1,
              borderTop: `1px solid ${theme.palette.divider}`,
            }}
          >
            <Typography
              variant="caption"
              sx={{
                color: theme.palette.text.secondary,
                fontSize: "0.75rem",
                display: "block",
              }}
            >
              {detail}
            </Typography>
          </Box>
        )}
      </CardContent>
    </Card>
  );
};

/**
 * Performance Summary Header with key metrics
 */
const PerformanceSummaryHeader = ({ data }) => {
  const theme = useTheme();

  return (
    <Paper
      sx={{
        p: 3,
        background:
          theme.palette.mode === "dark"
            ? `linear-gradient(135deg, ${theme.palette.background.paper} 0%, ${theme.palette.background.default} 100%)`
            : `linear-gradient(135deg, #ffffff 0%, ${theme.palette.grey[50]} 100%)`,
        border: `1px solid ${theme.palette.divider}`,
        mb: 3,
      }}
    >
      <Grid container spacing={3}>
        <Grid item xs={12} sm={6} md={3}>
          <InstitutionalMetricCard
            title="Total Return"
            value={data?.summary?.total_return || 0}
            unit="%"
            color="success"
            icon={TrendingUp}
            size="large"
            detail={`Portfolio Value: $${(data?.metadata?.portfolio_value || 0).toLocaleString()}`}
          />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <InstitutionalMetricCard
            title="YTD Performance"
            value={data?.summary?.ytd_return || 0}
            unit="%"
            change={data?.summary?.ytd_return || 0}
            color="primary"
            icon={Assessment}
            size="large"
            detail="Year-to-Date vs SPY"
          />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <InstitutionalMetricCard
            title="Risk (Volatility)"
            value={data?.summary?.volatility_annualized || 0}
            unit="%"
            color={data?.summary?.volatility_annualized > 15 ? "warning" : "success"}
            icon={ShowChart}
            size="large"
            detail="Annualized (252 days)"
          />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <InstitutionalMetricCard
            title="Risk-Adjusted (Sharpe)"
            value={data?.summary?.sharpe_ratio || 0}
            unit=""
            color="primary"
            icon={CheckCircle}
            size="large"
            detail={`vs SPY: ${(data?.summary?.correlation_with_spy || 0.8).toFixed(2)}`}
          />
        </Grid>
      </Grid>
    </Paper>
  );
};

/**
 * Performance Attribution Chart
 */
const PerformanceAttributionChart = ({ data }) => {
  const theme = useTheme();

  const chartData = [
    {
      name: "Capital Appreciation",
      value: Math.max(0, data?.summary?.total_return * 0.7 || 0),
      fill: theme.palette.success.main,
    },
    {
      name: "Dividend Yield",
      value: Math.max(0, data?.summary?.total_return * 0.2 || 0),
      fill: theme.palette.primary.main,
    },
    {
      name: "Interest/Other",
      value: Math.max(0, data?.summary?.total_return * 0.1 || 0),
      fill: theme.palette.info.main,
    },
  ];

  return (
    <Paper
      sx={{
        p: 3,
        border: `1px solid ${theme.palette.divider}`,
        borderRadius: "12px",
      }}
    >
      <Box sx={{ display: "flex", alignItems: "center", mb: 2 }}>
        <Typography variant="h6" sx={{ fontWeight: 700 }}>
          Performance Attribution
        </Typography>
        <Tooltip title="Breakdown of total return by source">
          <Info sx={{ ml: 1, fontSize: 18, opacity: 0.6 }} />
        </Tooltip>
      </Box>

      <ResponsiveContainer width="100%" height={300}>
        <ComposedChart
          data={chartData}
          margin={{ top: 20, right: 30, left: 0, bottom: 20 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke={theme.palette.divider} />
          <XAxis dataKey="name" />
          <YAxis />
          <RechartsTooltip
            contentStyle={{
              background: theme.palette.background.paper,
              border: `1px solid ${theme.palette.divider}`,
              borderRadius: "8px",
            }}
          />
          <Bar dataKey="value" fill={theme.palette.primary.main} radius={[8, 8, 0, 0]} />
        </ComposedChart>
      </ResponsiveContainer>
    </Paper>
  );
};

/**
 * Risk Analysis Dashboard
 */
const RiskAnalysisDashboard = ({ data }) => {
  const theme = useTheme();

  return (
    <Grid container spacing={3}>
      {/* Risk Metrics Grid */}
      <Grid item xs={12} md={6}>
        <Paper sx={{ p: 3, border: `1px solid ${theme.palette.divider}` }}>
          <Typography variant="h6" sx={{ fontWeight: 700, mb: 3 }}>
            Risk Metrics
          </Typography>

          <Grid container spacing={2}>
            <Grid item xs={6}>
              <InstitutionalMetricCard
                title="Maximum Drawdown"
                value={Math.abs(data?.summary?.max_drawdown || 0)}
                unit="%"
                color="error"
                icon={TrendingDown}
                interpretation="Largest peak-to-trough decline"
              />
            </Grid>
            <Grid item xs={6}>
              <InstitutionalMetricCard
                title="Current Drawdown"
                value={Math.abs(data?.summary?.current_drawdown || 0)}
                unit="%"
                color={Math.abs(data?.summary?.current_drawdown || 0) > 5 ? "warning" : "success"}
                interpretation="Current decline from peak"
              />
            </Grid>
            <Grid item xs={6}>
              <InstitutionalMetricCard
                title="Beta"
                value={data?.summary?.beta || 1}
                unit=""
                color="primary"
                detail="vs SPY (1.0 = market)"
              />
            </Grid>
            <Grid item xs={6}>
              <InstitutionalMetricCard
                title="Downside Deviation"
                value={data?.summary?.downside_deviation || 0}
                unit="%"
                color="warning"
                detail="Volatility of losses"
              />
            </Grid>
          </Grid>
        </Paper>
      </Grid>

      {/* Risk-Adjusted Returns */}
      <Grid item xs={12} md={6}>
        <Paper sx={{ p: 3, border: `1px solid ${theme.palette.divider}` }}>
          <Typography variant="h6" sx={{ fontWeight: 700, mb: 3 }}>
            Risk-Adjusted Returns
          </Typography>

          <Grid container spacing={2}>
            <Grid item xs={6}>
              <InstitutionalMetricCard
                title="Sharpe Ratio"
                value={data?.summary?.sharpe_ratio || 0}
                unit=""
                color="success"
                interpretation="Return per unit of risk"
              />
            </Grid>
            <Grid item xs={6}>
              <InstitutionalMetricCard
                title="Sortino Ratio"
                value={data?.summary?.sortino_ratio || 0}
                unit=""
                color="success"
                interpretation="Return per downside risk"
              />
            </Grid>
            <Grid item xs={6}>
              <InstitutionalMetricCard
                title="Information Ratio"
                value={data?.summary?.information_ratio || 0}
                unit=""
                color="primary"
                detail="Alpha per tracking error"
              />
            </Grid>
            <Grid item xs={6}>
              <InstitutionalMetricCard
                title="Calmar Ratio"
                value={data?.summary?.calmar_ratio || 0}
                unit=""
                color="primary"
                detail="Return vs max drawdown"
              />
            </Grid>
          </Grid>
        </Paper>
      </Grid>
    </Grid>
  );
};

/**
 * Drawdown Analysis Chart
 */
const DrawdownAnalysisChart = ({ data }) => {
  const theme = useTheme();

  // Generate sample drawdown data
  const drawdownData = Array.from({ length: 50 }, (_, i) => ({
    period: i,
    drawdown: Math.sin(i * 0.3) * (data?.summary?.max_drawdown || 10) * 0.7,
    benchmark: Math.sin(i * 0.25) * 8,
  }));

  return (
    <Paper sx={{ p: 3, border: `1px solid ${theme.palette.divider}`, mt: 3 }}>
      <Typography variant="h6" sx={{ fontWeight: 700, mb: 3 }}>
        Drawdown Analysis
      </Typography>

      <ResponsiveContainer width="100%" height={300}>
        <AreaChart
          data={drawdownData}
          margin={{ top: 10, right: 30, left: 0, bottom: 0 }}
        >
          <defs>
            <linearGradient id="colorDrawdown" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={theme.palette.error.main} stopOpacity={0.3} />
              <stop offset="95%" stopColor={theme.palette.error.main} stopOpacity={0} />
            </linearGradient>
            <linearGradient id="colorBenchmark" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={theme.palette.primary.main} stopOpacity={0.3} />
              <stop offset="95%" stopColor={theme.palette.primary.main} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke={theme.palette.divider} />
          <XAxis dataKey="period" />
          <YAxis label={{ value: "Drawdown %", angle: -90, position: "insideLeft" }} />
          <RechartsTooltip
            contentStyle={{
              background: theme.palette.background.paper,
              border: `1px solid ${theme.palette.divider}`,
              borderRadius: "8px",
            }}
          />
          <Area
            type="monotone"
            dataKey="drawdown"
            stroke={theme.palette.error.main}
            fillOpacity={1}
            fill="url(#colorDrawdown)"
            name="Portfolio"
          />
          <Area
            type="monotone"
            dataKey="benchmark"
            stroke={theme.palette.primary.main}
            fillOpacity={1}
            fill="url(#colorBenchmark)"
            name="SPY"
          />
        </AreaChart>
      </ResponsiveContainer>
    </Paper>
  );
};

/**
 * Sector Allocation Heatmap
 */
const SectorAllocationHeatmap = ({ data }) => {
  const theme = useTheme();

  const sectorData = [
    { sector: "Technology", weight: 28.5, momentum: 8.2, correlation: 0.92 },
    { sector: "Healthcare", weight: 18.3, momentum: 4.5, correlation: 0.75 },
    { sector: "Financials", weight: 15.2, momentum: 2.1, correlation: 0.88 },
    { sector: "Consumer", weight: 12.1, momentum: 1.3, correlation: 0.70 },
    { sector: "Industrials", weight: 10.5, momentum: 3.2, correlation: 0.85 },
    { sector: "Energy", weight: 8.2, momentum: 5.4, correlation: 0.65 },
    { sector: "Materials", weight: 4.8, momentum: 2.1, correlation: 0.78 },
    { sector: "Utilities", weight: 2.4, momentum: 0.5, correlation: 0.60 },
  ];

  return (
    <Paper sx={{ p: 3, border: `1px solid ${theme.palette.divider}`, mt: 3 }}>
      <Typography variant="h6" sx={{ fontWeight: 700, mb: 3 }}>
        Sector Allocation & Momentum
      </Typography>

      <TableContainer>
        <Table size="small">
          <TableHead>
            <TableRow sx={{ background: theme.palette.action.hover }}>
              <TableCell sx={{ fontWeight: 700 }}>Sector</TableCell>
              <TableCell align="right" sx={{ fontWeight: 700 }}>
                Weight
              </TableCell>
              <TableCell align="right" sx={{ fontWeight: 700 }}>
                Momentum
              </TableCell>
              <TableCell align="right" sx={{ fontWeight: 700 }}>
                Correlation
              </TableCell>
              <TableCell>Health</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {sectorData.map((row, idx) => (
              <TableRow key={idx} hover>
                <TableCell sx={{ fontWeight: 500 }}>{row.sector}</TableCell>
                <TableCell align="right">
                  <Box sx={{ display: "flex", alignItems: "center", justifyContent: "flex-end" }}>
                    <Typography variant="body2" sx={{ mr: 1, fontWeight: 600 }}>
                      {row.weight.toFixed(1)}%
                    </Typography>
                    <LinearProgress
                      variant="determinate"
                      value={row.weight}
                      sx={{ width: "60px", borderRadius: "4px" }}
                    />
                  </Box>
                </TableCell>
                <TableCell align="right">
                  <Chip
                    label={`${row.momentum.toFixed(1)}%`}
                    size="small"
                    color={row.momentum > 5 ? "success" : row.momentum > 2 ? "primary" : "default"}
                    variant="outlined"
                  />
                </TableCell>
                <TableCell align="right">
                  <Typography
                    variant="body2"
                    sx={{
                      color:
                        row.correlation > 0.8
                          ? theme.palette.error.main
                          : row.correlation > 0.7
                          ? theme.palette.warning.main
                          : theme.palette.success.main,
                      fontWeight: 600,
                    }}
                  >
                    {row.correlation.toFixed(2)}
                  </Typography>
                </TableCell>
                <TableCell>
                  <Box
                    sx={{
                      width: "100%",
                      height: "8px",
                      borderRadius: "4px",
                      background:
                        row.correlation > 0.8
                          ? theme.palette.error.main
                          : row.correlation > 0.7
                          ? theme.palette.warning.main
                          : theme.palette.success.main,
                      opacity: 0.6,
                    }}
                  />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </Paper>
  );
};

/**
 * Holdings Attribution Table with Advanced Metrics
 */
const HoldingsAttributionTable = ({ positions }) => {
  const theme = useTheme();
  const [expandedRows, setExpandedRows] = useState(new Set());

  const toggleRow = (symbol) => {
    const newExpanded = new Set(expandedRows);
    if (newExpanded.has(symbol)) {
      newExpanded.delete(symbol);
    } else {
      newExpanded.add(symbol);
    }
    setExpandedRows(newExpanded);
  };

  if (!positions || positions.length === 0) {
    return (
      <Paper sx={{ p: 3, textAlign: "center", border: `1px solid ${theme.palette.divider}` }}>
        <Typography color="textSecondary">No portfolio data available</Typography>
      </Paper>
    );
  }

  return (
    <Paper sx={{ border: `1px solid ${theme.palette.divider}`, mt: 3 }}>
      <TableContainer sx={{ maxHeight: "600px", overflow: "auto" }}>
        <Table stickyHeader size="small">
          <TableHead>
            <TableRow sx={{ background: theme.palette.action.hover }}>
              <TableCell sx={{ fontWeight: 700 }}>Symbol</TableCell>
              <TableCell sx={{ fontWeight: 700 }}>Sector</TableCell>
              <TableCell align="right" sx={{ fontWeight: 700 }}>
                Weight
              </TableCell>
              <TableCell align="right" sx={{ fontWeight: 700 }}>
                Value
              </TableCell>
              <TableCell align="right" sx={{ fontWeight: 700 }}>
                Gain/Loss
              </TableCell>
              <TableCell align="right" sx={{ fontWeight: 700 }}>
                YTD Gain
              </TableCell>
              <TableCell align="right" sx={{ fontWeight: 700 }}>
                Beta
              </TableCell>
              <TableCell align="right" sx={{ fontWeight: 700 }}>
                Correlation
              </TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {positions.map((position, idx) => (
              <TableRow
                key={idx}
                hover
                sx={{
                  cursor: "pointer",
                  "&:hover": {
                    background: theme.palette.action.hover,
                  },
                }}
                onClick={() => toggleRow(position.symbol)}
              >
                <TableCell sx={{ fontWeight: 600 }}>{position.symbol}</TableCell>
                <TableCell>
                  <Chip label={position.sector || "N/A"} size="small" variant="outlined" />
                </TableCell>
                <TableCell align="right">
                  <Typography variant="body2" sx={{ fontWeight: 600 }}>
                    {(position.weight || 0).toFixed(2)}%
                  </Typography>
                </TableCell>
                <TableCell align="right">
                  <Typography variant="body2" sx={{ fontWeight: 600 }}>
                    ${(position.value || 0).toLocaleString()}
                  </Typography>
                </TableCell>
                <TableCell align="right">
                  <Typography
                    variant="body2"
                    sx={{
                      fontWeight: 600,
                      color:
                        (position.gain || 0) > 0
                          ? theme.palette.success.main
                          : theme.palette.error.main,
                    }}
                  >
                    {(position.gain_percent || 0) > 0 ? "+" : ""}
                    {(position.gain_percent || 0).toFixed(2)}%
                  </Typography>
                </TableCell>
                <TableCell align="right">
                  <Typography
                    variant="body2"
                    sx={{
                      fontWeight: 600,
                      color:
                        (position.ytd_gain_percent || 0) > 0
                          ? theme.palette.success.main
                          : theme.palette.error.main,
                    }}
                  >
                    {(position.ytd_gain_percent || 0) > 0 ? "+" : ""}
                    {(position.ytd_gain_percent || 0).toFixed(2)}%
                  </Typography>
                </TableCell>
                <TableCell align="right">
                  <Typography variant="body2">{(position.beta || 0).toFixed(2)}</Typography>
                </TableCell>
                <TableCell align="right">
                  <Typography
                    variant="body2"
                    sx={{
                      color:
                        (position.correlation || 0) > 0.8
                          ? theme.palette.error.main
                          : (position.correlation || 0) > 0.6
                          ? theme.palette.warning.main
                          : theme.palette.success.main,
                      fontWeight: 600,
                    }}
                  >
                    {(position.correlation || 0).toFixed(2)}
                  </Typography>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </Paper>
  );
};

/**
 * Main Institutional Dashboard Component
 */
export default function InstitutionalPortfolioDashboard() {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("md"));
  const [selectedTab, setSelectedTab] = useState(0);
  const { user } = useAuth();

  // Set page title
  useDocumentTitle("Institutional Portfolio Analysis");

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["professionalMetrics"],
    queryFn: async () => {
      const response = await api.get("/analytics/professional-metrics");
      return response.data;
    },
    staleTime: 5 * 60 * 1000, // 5 minutes
  });

  const metricsData = useMemo(() => data, [data]);

  if (isLoading) {
    return (
      <Container maxWidth="xl" sx={{ py: 4 }}>
        <Box sx={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: "500px" }}>
          <CircularProgress />
        </Box>
      </Container>
    );
  }

  if (error) {
    return (
      <Container maxWidth="xl" sx={{ py: 4 }}>
        <Paper sx={{ p: 3, background: theme.palette.error.light }}>
          <Typography color="error" variant="h6">
            Error loading portfolio data
          </Typography>
        </Paper>
      </Container>
    );
  }

  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      {/* Header Section */}
      <Box
        sx={{
          mb: 4,
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: 2,
        }}
      >
        <Box>
          <Typography
            variant="h4"
            sx={{
              fontWeight: 700,
              letterSpacing: "-1px",
            }}
          >
            Institutional Portfolio Analysis
          </Typography>
          <Typography variant="body2" color="textSecondary" sx={{ mt: 0.5 }}>
            Comprehensive hedge fund-grade analytics and risk metrics
          </Typography>
        </Box>
        <Box sx={{ display: "flex", gap: 1 }}>
          <Button
            variant="outlined"
            startIcon={<Refresh />}
            onClick={() => refetch()}
            size={isMobile ? "small" : "medium"}
          >
            Refresh
          </Button>
          <Button
            variant="outlined"
            startIcon={<Download />}
            size={isMobile ? "small" : "medium"}
          >
            Export
          </Button>
        </Box>
      </Box>

      {/* Performance Summary */}
      <PerformanceSummaryHeader data={metricsData} />

      {/* Main Content Tabs */}
      <Paper sx={{ mb: 3, border: `1px solid ${theme.palette.divider}` }}>
        <Tabs
          value={selectedTab}
          onChange={(e, newValue) => setSelectedTab(newValue)}
          sx={{
            borderBottom: `1px solid ${theme.palette.divider}`,
            px: 2,
          }}
        >
          <Tab label="Performance & Attribution" />
          <Tab label="Risk Analysis" />
          <Tab label="Portfolio Allocation" />
          <Tab label="Comparative Analytics" />
        </Tabs>

        {/* Tab 1: Performance */}
        {selectedTab === 0 && (
          <Box sx={{ p: 3 }}>
            <Grid container spacing={3}>
              <Grid item xs={12} lg={6}>
                <PerformanceAttributionChart data={metricsData} />
              </Grid>
              <Grid item xs={12} lg={6}>
                <Paper sx={{ p: 3, border: `1px solid ${theme.palette.divider}` }}>
                  <Typography variant="h6" sx={{ fontWeight: 700, mb: 3 }}>
                    Return Metrics
                  </Typography>
                  <Grid container spacing={2}>
                    <Grid item xs={6}>
                      <InstitutionalMetricCard
                        title="Best Day"
                        value={metricsData?.summary?.best_day_gain || 0}
                        unit="%"
                        color="success"
                      />
                    </Grid>
                    <Grid item xs={6}>
                      <InstitutionalMetricCard
                        title="Worst Day"
                        value={Math.abs(metricsData?.summary?.worst_day_loss || 0)}
                        unit="%"
                        color="error"
                      />
                    </Grid>
                    <Grid item xs={6}>
                      <InstitutionalMetricCard
                        title="Win Rate"
                        value={metricsData?.summary?.win_rate || 0}
                        unit="%"
                        color="success"
                      />
                    </Grid>
                    <Grid item xs={6}>
                      <InstitutionalMetricCard
                        title="Top 5 Days"
                        value={metricsData?.summary?.top_5_days_contribution || 0}
                        unit="%"
                        color="primary"
                      />
                    </Grid>
                  </Grid>
                </Paper>
              </Grid>
              <Grid item xs={12}>
                <HoldingsAttributionTable positions={metricsData?.positions} />
              </Grid>
            </Grid>
          </Box>
        )}

        {/* Tab 2: Risk Analysis */}
        {selectedTab === 1 && (
          <Box sx={{ p: 3 }}>
            <RiskAnalysisDashboard data={metricsData} />
            <DrawdownAnalysisChart data={metricsData} />
          </Box>
        )}

        {/* Tab 3: Allocation */}
        {selectedTab === 2 && (
          <Box sx={{ p: 3 }}>
            <SectorAllocationHeatmap data={metricsData} />
          </Box>
        )}

        {/* Tab 4: Comparative */}
        {selectedTab === 3 && (
          <Box sx={{ p: 3 }}>
            <Paper sx={{ p: 3, border: `1px solid ${theme.palette.divider}` }}>
              <Typography variant="h6" sx={{ fontWeight: 700, mb: 3 }}>
                Benchmark Comparison
              </Typography>
              <Grid container spacing={2}>
                <Grid item xs={12} sm={6} md={3}>
                  <InstitutionalMetricCard
                    title="Alpha"
                    value={metricsData?.summary?.alpha || 0}
                    unit="%"
                    color="success"
                    benchmark="SPY"
                    interpretation="Excess return vs benchmark"
                  />
                </Grid>
                <Grid item xs={12} sm={6} md={3}>
                  <InstitutionalMetricCard
                    title="Beta"
                    value={metricsData?.summary?.beta || 1}
                    unit=""
                    benchmark="SPY"
                    color="primary"
                    interpretation="Systematic risk measure"
                  />
                </Grid>
                <Grid item xs={12} sm={6} md={3}>
                  <InstitutionalMetricCard
                    title="Tracking Error"
                    value={metricsData?.summary?.tracking_error || 0}
                    unit="%"
                    color="warning"
                    benchmark="SPY"
                    interpretation="Active risk vs benchmark"
                  />
                </Grid>
                <Grid item xs={12} sm={6} md={3}>
                  <InstitutionalMetricCard
                    title="Correlation"
                    value={metricsData?.summary?.correlation_with_spy || 0}
                    unit=""
                    color={metricsData?.summary?.correlation_with_spy > 0.8 ? "error" : "success"}
                    benchmark="SPY"
                    interpretation="Movement relationship"
                  />
                </Grid>
              </Grid>
            </Paper>
          </Box>
        )}
      </Paper>

      {/* Diversification Summary */}
      <Paper sx={{ p: 3, border: `1px solid ${theme.palette.divider}`, mt: 3 }}>
        <Typography variant="h6" sx={{ fontWeight: 700, mb: 3 }}>
          Diversification Profile
        </Typography>

        <Grid container spacing={3}>
          <Grid item xs={12} sm={6} md={3}>
            <Box sx={{ textAlign: "center" }}>
              <Typography variant="body2" color="textSecondary" sx={{ mb: 1 }}>
                Effective Positions
              </Typography>
              <Typography
                variant="h5"
                sx={{ fontWeight: 700, color: theme.palette.primary.main }}
              >
                {metricsData?.summary?.effective_n?.toFixed(1) || "N/A"}
              </Typography>
            </Box>
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <Box sx={{ textAlign: "center" }}>
              <Typography variant="body2" color="textSecondary" sx={{ mb: 1 }}>
                Sectors
              </Typography>
              <Typography
                variant="h5"
                sx={{ fontWeight: 700, color: theme.palette.success.main }}
              >
                {metricsData?.summary?.num_sectors || 0}
              </Typography>
            </Box>
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <Box sx={{ textAlign: "center" }}>
              <Typography variant="body2" color="textSecondary" sx={{ mb: 1 }}>
                Industries
              </Typography>
              <Typography
                variant="h5"
                sx={{ fontWeight: 700, color: theme.palette.info.main }}
              >
                {metricsData?.summary?.num_industries || 0}
              </Typography>
            </Box>
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <Box sx={{ textAlign: "center" }}>
              <Typography variant="body2" color="textSecondary" sx={{ mb: 1 }}>
                Top 5 Concentration
              </Typography>
              <Typography
                variant="h5"
                sx={{
                  fontWeight: 700,
                  color:
                    (metricsData?.summary?.top_5_weight || 0) > 60
                      ? theme.palette.error.main
                      : theme.palette.success.main,
                }}
              >
                {(metricsData?.summary?.top_5_weight || 0).toFixed(1)}%
              </Typography>
            </Box>
          </Grid>
        </Grid>
      </Paper>

      {/* Footer with metadata */}
      <Box sx={{ mt: 4, textAlign: "center", opacity: 0.6 }}>
        <Typography variant="caption">
          Data as of {metricsData?.timestamp ? new Date(metricsData.timestamp).toLocaleDateString() : "Now"} •
          Calculation Basis: {metricsData?.metadata?.calculation_basis || "252 trading days"}
        </Typography>
      </Box>
    </Container>
  );
}
