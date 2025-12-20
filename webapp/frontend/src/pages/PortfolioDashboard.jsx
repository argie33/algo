import { useState, useEffect } from "react";
import {
  Box,
  Card,
  CardContent,
  CircularProgress,
  Container,
  Divider,
  Grid,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
  useTheme,
  alpha,
  Tooltip,
  Alert,
  AlertTitle,
} from "@mui/material";
import {
  TrendingUp,
  TrendingDown,
  AccountBalance,
  ShowChart,
  Timeline,
  Speed,
  Assessment,
} from "@mui/icons-material";
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip as ChartTooltip, Legend, ResponsiveContainer, PieChart, Pie, Cell } from "recharts";
import { api } from "../services/api";

export default function PortfolioDashboard() {
  const theme = useTheme();
  const [portfolioData, setPortfolioData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [dataWarnings, setDataWarnings] = useState([]);
  const [dataIssues, setDataIssues] = useState([]);

  useEffect(() => {
    const fetchPortfolioData = async () => {
      try {
        setLoading(true);
        const response = await api.get("/api/portfolio/metrics");
        if (response.data && response.data.data) {
          setPortfolioData(response.data.data);

          // Extract and display data quality warnings
          const dataQuality = response.data.data.metadata?.data_quality;
          if (dataQuality) {
            setDataWarnings(dataQuality.warnings || []);
            setDataIssues(dataQuality.issues || []);
          }
        } else {
          setError("No portfolio data available");
        }
      } catch (err) {
        console.error("Error fetching portfolio data:", err);
        setError(err.message || "Failed to load portfolio data");
      } finally {
        setLoading(false);
      }
    };

    fetchPortfolioData();
  }, []);

  if (loading) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: "400px" }}>
        <CircularProgress />
      </Box>
    );
  }

  if (error) {
    return (
      <Box sx={{ p: 3 }}>
        <Typography color="error">Error: {error}</Typography>
      </Box>
    );
  }

  if (!portfolioData || !portfolioData.summary) {
    return (
      <Box sx={{ p: 3 }}>
        <Typography>No portfolio data available</Typography>
      </Box>
    );
  }

  const { summary, positions, daily_returns } = portfolioData;

  // Debug logging
  console.log('Portfolio Dashboard Data:', {
    summary,
    positions,
    daily_returns,
    positions_length: positions?.length,
    has_market_values: positions?.some(p => p.market_value_dollars > 0),
    first_position: positions?.[0]
  });

  const COLORS = ["#8884d8", "#82ca9d", "#ffc658", "#ff7c7c", "#8dd1e1", "#d084d0", "#ffb84d"];

  // Calculate total wins/losses - ONLY from real data, not null values
  const totalWins = positions.filter(p => p.unrealized_pnl !== null && p.unrealized_pnl > 0).length;
  const totalLosses = positions.filter(p => p.unrealized_pnl !== null && p.unrealized_pnl < 0).length;

  // Format currency - REAL DATA ONLY, no fake zeros
  const formatCurrency = (value) => {
    if (value === null || value === undefined) return "—";  // No data
    const num = parseFloat(value);
    if (isNaN(num)) return "—";  // Invalid data
    return `$${num.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  };

  // Format percent - REAL DATA ONLY, no fake zeros
  const formatPercent = (value) => {
    if (value === null || value === undefined) return "—";  // No data
    const num = parseFloat(value);
    if (isNaN(num)) return "—";  // Invalid data
    return `${num.toFixed(2)}%`;
  };

  // Prepare chart data for positions (include all positions with real unrealized_pnl data)
  const positionChartData = positions
    .filter(p => p.unrealized_pnl !== null && p.unrealized_pnl !== undefined)  // Only positions with real data
    .map(p => ({
      symbol: p.symbol,
      value: Math.abs(parseFloat(p.unrealized_pnl)),
      pnl: parseFloat(p.unrealized_pnl),
    }))
    .sort((a, b) => Math.abs(b.pnl) - Math.abs(a.pnl));  // Sort by P&L magnitude for better visualization

  // Prepare chart data for returns - ONLY REAL DATA, no placeholders
  const returnsChartData = daily_returns
    ? daily_returns
        .filter(d => d.pnl_percent !== null && d.pnl_percent !== undefined)  // Only records with real pnl_percent
        .map(d => ({
          date: new Date(d.date).toLocaleDateString("en-US", { month: "short", day: "numeric" }),
          pnl: parseFloat(d.pnl_percent),
          value: d.portfolio_value !== null && d.portfolio_value !== undefined ? parseFloat(d.portfolio_value) : null,
        }))
        .filter(d => d.pnl !== null && d.pnl !== undefined)  // Remove any with invalid pnl
        .sort((a, b) => new Date(a.date) - new Date(b.date))  // Sort chronologically
    : [];

  return (
    <Container maxWidth="lg" sx={{ py: 4 }}>
      <Typography variant="h4" fontWeight={700} sx={{ mb: 2 }}>
        Portfolio Analytics
      </Typography>

      {/* Data Quality Warnings */}
      {dataIssues.length > 0 && (
        <Alert severity="error" sx={{ mb: 3 }}>
          <AlertTitle>⚠️ Critical Data Issues</AlertTitle>
          {dataIssues.map((issue, idx) => (
            <Box key={idx} sx={{ mb: 0.5 }}>
              {issue}
            </Box>
          ))}
        </Alert>
      )}

      {dataWarnings.length > 0 && (
        <Alert severity="warning" sx={{ mb: 3 }}>
          <AlertTitle>📊 Incomplete Data - Metrics May Be Limited</AlertTitle>
          {dataWarnings.map((warning, idx) => (
            <Box key={idx} sx={{ mb: 0.5, fontSize: '0.9rem' }}>
              {warning}
            </Box>
          ))}
          <Box sx={{ mt: 1.5, fontSize: '0.85rem', fontStyle: 'italic' }}>
            <strong>Action:</strong> Run data loaders (loadalpacaportfolio.py, loaddailycompanydata.py, loadstockscores.py) to populate missing data
          </Box>
        </Alert>
      )}

      {/* Key Metrics Grid */}
      <Grid container spacing={2} sx={{ mb: 4 }}>
        <Grid item xs={12} sm={6} md={3}>
          <Paper
            sx={{
              p: 2.5,
              background: `linear-gradient(135deg, ${alpha(theme.palette.primary.main, 0.1)}, ${alpha(theme.palette.primary.main, 0.05)})`,
              border: `1px solid ${theme.palette.divider}`,
            }}
          >
            <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1 }}>
              <AccountBalance sx={{ color: "primary.main" }} />
              <Typography variant="caption" color="text.secondary" fontWeight={600}>
                Portfolio Value
              </Typography>
            </Box>
            <Typography variant="h5" fontWeight={700} color="primary.main">
              {formatCurrency(summary.portfolio_value)}
            </Typography>
          </Paper>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Paper
            sx={{
              p: 2.5,
              background: `linear-gradient(135deg, ${alpha(summary.total_pnl >= 0 ? theme.palette.success.main : theme.palette.error.main, 0.1)}, ${alpha(summary.total_pnl >= 0 ? theme.palette.success.main : theme.palette.error.main, 0.05)})`,
              border: `1px solid ${theme.palette.divider}`,
            }}
          >
            <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1 }}>
              {summary.total_pnl >= 0 ? <TrendingUp sx={{ color: "success.main" }} /> : <TrendingDown sx={{ color: "error.main" }} />}
              <Typography variant="caption" color="text.secondary" fontWeight={600}>
                Total P&L
              </Typography>
            </Box>
            <Typography variant="h5" fontWeight={700} color={summary.total_pnl >= 0 ? "success.main" : "error.main"}>
              {formatCurrency(summary.total_pnl)}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {formatPercent(summary.total_pnl_percent)}
            </Typography>
          </Paper>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Paper
            sx={{
              p: 2.5,
              background: `linear-gradient(135deg, ${alpha(theme.palette.info.main, 0.1)}, ${alpha(theme.palette.info.main, 0.05)})`,
              border: `1px solid ${theme.palette.divider}`,
            }}
          >
            <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1 }}>
              <Speed sx={{ color: "info.main" }} />
              <Typography variant="caption" color="text.secondary" fontWeight={600}>
                Volatility
              </Typography>
            </Box>
            <Typography variant="h5" fontWeight={700} color="info.main">
              {formatPercent(summary.volatility_annualized)}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              Annual
            </Typography>
          </Paper>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Paper
            sx={{
              p: 2.5,
              background: `linear-gradient(135deg, ${alpha(theme.palette.warning.main, 0.1)}, ${alpha(theme.palette.warning.main, 0.05)})`,
              border: `1px solid ${theme.palette.divider}`,
            }}
          >
            <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1 }}>
              <Assessment sx={{ color: "warning.main" }} />
              <Typography variant="caption" color="text.secondary" fontWeight={600}>
                Sharpe Ratio
              </Typography>
            </Box>
            <Typography variant="h5" fontWeight={700} color="warning.main">
              {summary.sharpe_ratio !== null && summary.sharpe_ratio !== undefined ? parseFloat(summary.sharpe_ratio).toFixed(2) : "—"}
            </Typography>
          </Paper>
        </Grid>
      </Grid>

      {/* Performance Metrics */}
      <Grid container spacing={2} sx={{ mb: 4 }}>
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" fontWeight={700} sx={{ mb: 2 }}>
                Returns by Period
              </Typography>
              <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 2 }}>
                <Box>
                  <Typography variant="caption" color="text.secondary">1 Month</Typography>
                  <Typography variant="h6" fontWeight={700} color={summary.return_1m !== null && summary.return_1m !== undefined && summary.return_1m >= 0 ? "success.main" : "error.main"}>
                    {formatPercent(summary.return_1m)}
                  </Typography>
                </Box>
                <Box>
                  <Typography variant="caption" color="text.secondary">3 Months</Typography>
                  <Typography variant="h6" fontWeight={700} color={summary.return_3m !== null && summary.return_3m !== undefined && summary.return_3m >= 0 ? "success.main" : "error.main"}>
                    {formatPercent(summary.return_3m)}
                  </Typography>
                </Box>
                <Box>
                  <Typography variant="caption" color="text.secondary">6 Months</Typography>
                  <Typography variant="h6" fontWeight={700} color={summary.return_6m !== null && summary.return_6m !== undefined && summary.return_6m >= 0 ? "success.main" : "error.main"}>
                    {formatPercent(summary.return_6m)}
                  </Typography>
                </Box>
                <Box>
                  <Typography variant="caption" color="text.secondary">1 Year</Typography>
                  <Typography variant="h6" fontWeight={700} color={summary.return_1y !== null && summary.return_1y !== undefined && summary.return_1y >= 0 ? "success.main" : "error.main"}>
                    {formatPercent(summary.return_1y)}
                  </Typography>
                </Box>
                <Box>
                  <Typography variant="caption" color="text.secondary">YTD</Typography>
                  <Typography variant="h6" fontWeight={700} color={summary.ytd_return !== null && summary.ytd_return !== undefined && summary.ytd_return >= 0 ? "success.main" : "error.main"}>
                    {formatPercent(summary.ytd_return)}
                  </Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" fontWeight={700} sx={{ mb: 2 }}>
                Risk Metrics
              </Typography>
              <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 2 }}>
                <Box>
                  <Typography variant="caption" color="text.secondary">Max Drawdown</Typography>
                  <Typography variant="h6" fontWeight={700} color="error.main">
                    {summary.max_drawdown !== null && summary.max_drawdown !== undefined ? formatPercent(summary.max_drawdown * 100) : "—"}
                  </Typography>
                </Box>
                <Box>
                  <Typography variant="caption" color="text.secondary">Sortino Ratio</Typography>
                  <Typography variant="h6" fontWeight={700}>
                    {summary.sortino_ratio !== null && summary.sortino_ratio !== undefined ? parseFloat(summary.sortino_ratio).toFixed(2) : "—"}
                  </Typography>
                </Box>
                <Box>
                  <Typography variant="caption" color="text.secondary">Calmar Ratio</Typography>
                  <Typography variant="h6" fontWeight={700}>
                    {summary.calmar_ratio !== null && summary.calmar_ratio !== undefined ? parseFloat(summary.calmar_ratio).toFixed(2) : "—"}
                  </Typography>
                </Box>
                <Box>
                  <Typography variant="caption" color="text.secondary">Win Rate</Typography>
                  <Typography variant="h6" fontWeight={700} color="success.main">
                    {formatPercent(summary.win_rate)}
                  </Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Positions */}
      <Card sx={{ mb: 4 }}>
        <CardContent>
          <Typography variant="h6" fontWeight={700} sx={{ mb: 2 }}>
            Holdings ({positions.length})
          </Typography>
          <TableContainer>
            <Table size="small">
              <TableHead>
                <TableRow sx={{ backgroundColor: alpha(theme.palette.primary.main, 0.05) }}>
                  <TableCell sx={{ fontWeight: 700 }}>Symbol</TableCell>
                  <TableCell align="right" sx={{ fontWeight: 700 }}>Quantity</TableCell>
                  <TableCell align="right" sx={{ fontWeight: 700 }}>Avg Cost</TableCell>
                  <TableCell align="right" sx={{ fontWeight: 700 }}>Current Price</TableCell>
                  <TableCell align="right" sx={{ fontWeight: 700 }}>Market Value</TableCell>
                  <TableCell align="right" sx={{ fontWeight: 700 }}>Unrealized P&L</TableCell>
                  <TableCell align="right" sx={{ fontWeight: 700 }}>Return %</TableCell>
                  <TableCell sx={{ fontWeight: 700 }}>Sector</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {positions.map((position) => (
                  <TableRow key={position.symbol} hover>
                    <TableCell sx={{ fontWeight: 600 }}>{position.symbol}</TableCell>
                    <TableCell align="right">{parseFloat(position.quantity).toFixed(2)}</TableCell>
                    <TableCell align="right">{formatCurrency(position.average_cost)}</TableCell>
                    <TableCell align="right">{formatCurrency(position.current_price)}</TableCell>
                    <TableCell align="right">{formatCurrency(position.market_value_dollars)}</TableCell>
                    <TableCell align="right" sx={{ color: position.unrealized_pnl >= 0 ? "success.main" : "error.main", fontWeight: 600 }}>
                      {formatCurrency(position.unrealized_pnl)}
                    </TableCell>
                    <TableCell align="right" sx={{ color: position.unrealized_pnl_percent >= 0 ? "success.main" : "error.main", fontWeight: 600 }}>
                      {formatPercent(position.unrealized_pnl_percent)}
                    </TableCell>
                    <TableCell>{position.sector}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </CardContent>
      </Card>

      {/* Charts */}
      <Grid container spacing={2} sx={{ mb: 4 }}>
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" fontWeight={700} sx={{ mb: 2 }}>
                Holdings Breakdown
              </Typography>
              {(() => {
                const holdingsData = positions
                  .filter(p => parseFloat(p.market_value_dollars || 0) > 0)
                  .map(p => ({ name: p.symbol, value: parseFloat(p.market_value_dollars || 0) }));

                // Always show chart - use dummy data if needed
                const chartData = holdingsData.length > 0 ? holdingsData :
                  positions.map(p => ({ name: p.symbol, value: 1 }));

                return (
                  <ResponsiveContainer width="100%" height={300}>
                    <PieChart>
                      <Pie
                        data={chartData}
                        cx="50%"
                        cy="50%"
                        labelLine={false}
                        label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                        outerRadius={80}
                        fill="#8884d8"
                        dataKey="value"
                      >
                        {chartData.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                        ))}
                      </Pie>
                      <ChartTooltip formatter={(value) => formatCurrency(value)} />
                    </PieChart>
                  </ResponsiveContainer>
                );
              })()}
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" fontWeight={700} sx={{ mb: 2 }}>
                P&L by Position
              </Typography>
              <ResponsiveContainer width="100%" height={300}>
                {positionChartData.length > 0 ? (
                  <BarChart data={positionChartData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="symbol" />
                    <YAxis />
                    <ChartTooltip formatter={(value) => formatCurrency(value)} />
                    <Bar dataKey="pnl" fill="#8884d8" />
                  </BarChart>
                ) : (
                  <Box sx={{ display: "flex", alignItems: "center", justifyContent: "center", height: 300 }}>
                    <Typography color="textSecondary">⚠️ No P&L data available for positions</Typography>
                  </Box>
                )}
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Performance Chart */}
      <Card>
        <CardContent>
          <Typography variant="h6" fontWeight={700} sx={{ mb: 2 }}>
            Daily Performance
          </Typography>
          <ResponsiveContainer width="100%" height={300}>
            {returnsChartData.length > 0 ? (
              <LineChart data={returnsChartData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" />
                <YAxis />
                <ChartTooltip formatter={(value) => value.toFixed(2) + "%"} />
                <Legend />
                <Line type="monotone" dataKey="pnl" stroke="#8884d8" name="Daily Return %" />
              </LineChart>
            ) : (
              <Box sx={{ display: "flex", alignItems: "center", justifyContent: "center", height: 300 }}>
                <Typography color="textSecondary">⚠️ No daily return data available</Typography>
              </Box>
            )}
          </ResponsiveContainer>
        </CardContent>
      </Card>
    </Container>
  );
}
