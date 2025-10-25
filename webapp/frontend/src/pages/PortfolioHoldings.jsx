import { useState, useEffect, useMemo, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "../contexts/AuthContext";
import { useDocumentTitle } from "../hooks/useDocumentTitle";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CardHeader,
  CircularProgress,
  Container,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  Grid,
  IconButton,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TablePagination,
  TableRow,
  TableSortLabel,
  Tabs,
  Tab,
  TextField,
  Typography,
} from "@mui/material";
import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartChartTooltip,
  Legend,
  BarChart,
  Bar,
  AreaChart,
  Area,
} from "recharts";
import { Add, Delete, Edit, FilterList, Refresh, CloudDownload, ShowChart, Assessment, TrendingUp, TrendingDown, AccountBalance, Timeline, Warning, CheckCircle, Error as ErrorIcon, Info, BarChart as BarChartIcon } from "@mui/icons-material";
import {
  getPortfolioHoldings,
  addHolding,
  updateHolding,
  deleteHolding,
  getStockPrices,
  importPortfolioFromBroker,
  getPerformanceAnalytics,
  getRiskAnalytics,
  getCorrelationAnalytics,
  getAllocationAnalytics,
  getVolatilityAnalytics,
  getTrendsAnalytics,
  getPortfolioSectorIndustryAnalysis,
  getProfessionalMetrics,
} from "../services/api";

// Advanced Analytics Component with tabs
const AdvancedAnalyticsContent = ({ timeframe }) => {
  const [benchmark, setBenchmark] = useState("SPY");
  const [analyticsTab, setAnalyticsTab] = useState(0);

  // Convert timeframe format (1Y -> 1y, 3M -> 3m)
  const apiTimeframe = timeframe?.toLowerCase() || "1y";

  const { data: performanceData, isLoading: perfLoading } = useQuery({
    queryKey: ["performanceAnalytics", apiTimeframe, benchmark],
    queryFn: () => getPerformanceAnalytics(apiTimeframe, benchmark),
    staleTime: 60000,
  });

  const { data: riskData, isLoading: riskLoading } = useQuery({
    queryKey: ["riskAnalytics", apiTimeframe],
    queryFn: () => getRiskAnalytics(apiTimeframe),
    staleTime: 60000,
  });

  const { data: allocationData, isLoading: allocLoading } = useQuery({
    queryKey: ["allocationAnalytics"],
    queryFn: () => getAllocationAnalytics(),
    staleTime: 120000,
  });

  const { data: correlationData, isLoading: corrLoading } = useQuery({
    queryKey: ["correlationAnalytics", apiTimeframe],
    queryFn: () => getCorrelationAnalytics(apiTimeframe),
    staleTime: 300000,
  });

  const { data: volatilityData, isLoading: volLoading } = useQuery({
    queryKey: ["volatilityAnalytics", apiTimeframe],
    queryFn: () => getVolatilityAnalytics(apiTimeframe),
    staleTime: 60000,
  });

  const { data: trendsData, isLoading: trendsLoading } = useQuery({
    queryKey: ["trendsAnalytics", apiTimeframe],
    queryFn: () => getTrendsAnalytics(apiTimeframe),
    staleTime: 60000,
  });

  const { data: sectorIndustryData, isLoading: sectorIndustryLoading } = useQuery({
    queryKey: ["portfolioSectorIndustryAnalysis"],
    queryFn: () => getPortfolioSectorIndustryAnalysis(),
    staleTime: 120000,
  });

  const { data: professionalMetricsData, isLoading: profMetricsLoading } = useQuery({
    queryKey: ["professionalMetrics", apiTimeframe, benchmark],
    queryFn: () => getProfessionalMetrics(apiTimeframe, benchmark),
    staleTime: 60000,
  });

  const isLoading = perfLoading || riskLoading || allocLoading || corrLoading || volLoading || trendsLoading;

  if (isLoading) {
    return (
      <Box display="flex" justifyContent="center" p={4}>
        <CircularProgress />
      </Box>
    );
  }

  const renderPerformanceTab = () => (
    <Grid container spacing={3}>
      {/* Performance Summary */}
      <Grid item xs={12}>
        <Grid container spacing={2}>
          <Grid item xs={12} sm={6} md={3}>
            <Card>
              <CardContent>
                <Box display="flex" alignItems="center" gap={2}>
                  <TrendingUp color="primary" />
                  <Box>
                    <Typography variant="h6">
                      {performanceData?.data?.returns ? `${(performanceData.data.returns * 100).toFixed(2)}%` : "N/A"}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">Total Return</Typography>
                  </Box>
                </Box>
              </CardContent>
            </Card>
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <Card>
              <CardContent>
                <Box display="flex" alignItems="center" gap={2}>
                  <ShowChart color="secondary" />
                  <Box>
                    <Typography variant="h6">
                      {performanceData?.data?.volatility ? `${(performanceData.data.volatility * 100).toFixed(2)}%` : "N/A"}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">Volatility</Typography>
                  </Box>
                </Box>
              </CardContent>
            </Card>
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <Card>
              <CardContent>
                <Box display="flex" alignItems="center" gap={2}>
                  <Timeline />
                  <Box>
                    <Typography variant="h6">
                      {performanceData?.data?.sharpe_ratio ? performanceData.data.sharpe_ratio.toFixed(2) : "N/A"}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">Sharpe Ratio</Typography>
                  </Box>
                </Box>
              </CardContent>
            </Card>
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <Card>
              <CardContent>
                <Box display="flex" alignItems="center" gap={2}>
                  <AccountBalance />
                  <Box>
                    <Typography variant="h6">
                      {performanceData?.data?.portfolio_metrics?.total_value ? `$${parseFloat(performanceData.data.portfolio_metrics.total_value).toLocaleString()}` : "N/A"}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">Portfolio Value</Typography>
                  </Box>
                </Box>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      </Grid>

      {/* Performance Chart */}
      <Grid item xs={12} lg={8}>
        <Card>
          <CardHeader title="Performance vs Benchmark" />
          <CardContent>
            <ResponsiveContainer width="100%" height={400}>
              <LineChart data={performanceData?.data?.performance_timeline || []}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" tickFormatter={(value) => new Date(value).toLocaleDateString()} />
                <YAxis tickFormatter={(value) => `${value}%`} />
                <RechartChartTooltip formatter={(value, name) => [`${(parseFloat(value) || 0).toFixed(2)}%`, name]} labelFormatter={(value) => new Date(value).toLocaleDateString()} />
                <Legend />
                <Line type="monotone" dataKey="pnl_percent" stroke="#8884d8" strokeWidth={2} name="Portfolio" />
                <Line type="monotone" dataKey="benchmark_return" stroke="#82ca9d" strokeWidth={2} name={`${benchmark} Benchmark`} data={performanceData?.data?.benchmark_comparison?.data || []} />
              </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </Grid>

      {/* Risk Analysis */}
      <Grid item xs={12} lg={4}>
        <Card>
          <CardHeader title="Risk Metrics" />
          <CardContent>
            <Box mb={2}>
              <Typography variant="body2" color="text.secondary">Portfolio Volatility</Typography>
              <Typography variant="h6">{riskData?.data?.risk?.portfolio_metrics?.portfolio_volatility || "N/A"}%</Typography>
            </Box>
            <Box mb={2}>
              <Typography variant="body2" color="text.secondary">Max Drawdown</Typography>
              <Typography variant="h6">{riskData?.data?.risk?.portfolio_metrics?.max_drawdown || "N/A"}%</Typography>
            </Box>
            <Box>
              <Typography variant="body2" color="text.secondary">Value at Risk (95%)</Typography>
              <Typography variant="h6">{riskData?.data?.risk?.portfolio_metrics?.value_at_risk_95 || "N/A"}%</Typography>
            </Box>
          </CardContent>
        </Card>
      </Grid>

      {/* Sector Allocation */}
      <Grid item xs={12} md={6}>
        <Card>
          <CardHeader title="Sector Allocation" />
          <CardContent>
            <ResponsiveContainer width="100%" height={300}>
              <PieChart>
                <Pie data={allocationData?.data?.sectors || []} dataKey="percentage" cx="50%" cy="50%" outerRadius={100} fill="#8884d8" label={({ name, percentage }) => `${name}: ${percentage}%`}>
                  {(allocationData?.data?.sectors || []).map((_, index) => (
                    <Cell key={`cell-${index}`} fill={`hsl(${index * 45}, 70%, 60%)`} />
                  ))}
                </Pie>
                <RechartsTooltip />
              </PieChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </Grid>

      {/* Top Holdings */}
      <Grid item xs={12} md={6}>
        <Card>
          <CardHeader title="Top Holdings" />
          <CardContent>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={(allocationData?.data?.assets || []).slice(0, 10)}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="symbol" />
                <YAxis tickFormatter={(value) => `${value}%`} />
                <RechartChartTooltip formatter={(value) => [`${value}%`, "Weight"]} />
                <Bar dataKey="percentage" fill="#8884d8" />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </Grid>
    </Grid>
  );

  const renderRiskTab = () => (
    <Grid container spacing={3}>
      <Grid item xs={12}>
        <Card>
          <CardHeader title="Risk Metrics" />
          <CardContent>
            <Grid container spacing={3}>
              <Grid item xs={12} md={6}>
                <Box mb={2}>
                  <Typography variant="body2" color="text.secondary">Portfolio Volatility</Typography>
                  <Typography variant="h6">{riskData?.data?.risk?.portfolio_metrics?.portfolio_volatility || "N/A"}%</Typography>
                </Box>
                <Box mb={2}>
                  <Typography variant="body2" color="text.secondary">Max Drawdown</Typography>
                  <Typography variant="h6">{riskData?.data?.risk?.portfolio_metrics?.max_drawdown || "N/A"}%</Typography>
                </Box>
                <Box>
                  <Typography variant="body2" color="text.secondary">Value at Risk (95%)</Typography>
                  <Typography variant="h6">{riskData?.data?.risk?.portfolio_metrics?.value_at_risk_95 || "N/A"}%</Typography>
                </Box>
              </Grid>
              <Grid item xs={12} md={6}>
                <Box mb={2}>
                  <Typography variant="body2" color="text.secondary">Concentration Risk</Typography>
                  <Typography variant="h6">{riskData?.data?.risk?.portfolio_metrics?.concentration_risk || "N/A"}</Typography>
                </Box>
                <Box>
                  <Typography variant="body2" color="text.secondary">Overall Risk Level</Typography>
                  <Box display="flex" alignItems="center" gap={1} mt={1}>
                    {riskData?.data?.risk?.risk_assessment?.overall_risk === "Low" ? <CheckCircle color="success" /> :
                     riskData?.data?.risk?.risk_assessment?.overall_risk === "Medium" ? <Warning color="warning" /> :
                     riskData?.data?.risk?.risk_assessment?.overall_risk === "High" ? <ErrorIcon color="error" /> : null}
                    <Typography variant="h6">{riskData?.data?.risk?.risk_assessment?.overall_risk || "Unknown"}</Typography>
                  </Box>
                </Box>
              </Grid>
            </Grid>
          </CardContent>
        </Card>
      </Grid>
    </Grid>
  );

  const renderCorrelationTab = () => (
    <Grid container spacing={3}>
      <Grid item xs={12}>
        <Card>
          <CardHeader title="Correlation Analysis" />
          <CardContent>
            <Grid container spacing={3}>
              <Grid item xs={12} md={4}>
                <Box textAlign="center" p={2}>
                  <Typography variant="h4" color="primary">{correlationData?.data?.correlations?.insights?.diversification_score || "N/A"}</Typography>
                  <Typography variant="body2" color="text.secondary">Diversification Score</Typography>
                </Box>
              </Grid>
              <Grid item xs={12} md={4}>
                <Box textAlign="center" p={2}>
                  <Typography variant="h6">{correlationData?.data?.correlations?.insights?.average_correlation || "N/A"}</Typography>
                  <Typography variant="body2" color="text.secondary">Average Correlation</Typography>
                </Box>
              </Grid>
              <Grid item xs={12} md={4}>
                <Box textAlign="center" p={2}>
                  <Typography variant="h6">{correlationData?.data?.correlations?.assets_analyzed || "N/A"}</Typography>
                  <Typography variant="body2" color="text.secondary">Assets Analyzed</Typography>
                </Box>
              </Grid>
            </Grid>
          </CardContent>
        </Card>
      </Grid>
    </Grid>
  );

  const renderVolatilityTab = () => (
    <Grid container spacing={3}>
      <Grid item xs={12} md={6}>
        <Card>
          <CardHeader title="Volatility Analysis" />
          <CardContent>
            <Box textAlign="center" p={2}>
              <Typography variant="h5">{volatilityData?.data?.volatility?.annualized_volatility || "N/A"}%</Typography>
              <Typography variant="body2" color="text.secondary">Annualized Volatility</Typography>
              <Box mt={2}>
                {volatilityData?.data?.volatility?.risk_level === "Low" ? <CheckCircle color="success" /> :
                 volatilityData?.data?.volatility?.risk_level === "Medium" ? <Warning color="warning" /> :
                 volatilityData?.data?.volatility?.risk_level === "High" ? <ErrorIcon color="error" /> : null}
                <Typography variant="body2" color="text.secondary" mt={1}>{volatilityData?.data?.volatility?.risk_level || "Unknown"} Risk</Typography>
              </Box>
            </Box>
          </CardContent>
        </Card>
      </Grid>
      <Grid item xs={12} md={6}>
        <Card>
          <CardHeader title="Trend Analysis" />
          <CardContent>
            <Box textAlign="center" p={2}>
              <Typography variant="h6">{trendsData?.data?.trends?.trend_direction || "Unknown"}</Typography>
              <Typography variant="body2" color="text.secondary">Trend Direction</Typography>
              <Box mt={2}>
                <Typography variant="h6">{trendsData?.data?.trends?.trend_strength || "Unknown"}</Typography>
                <Typography variant="body2" color="text.secondary">Trend Strength</Typography>
              </Box>
            </Box>
          </CardContent>
        </Card>
      </Grid>
    </Grid>
  );

  const renderSectorIndustryTab = () => {
    if (sectorIndustryLoading) {
      return (
        <Box display="flex" justifyContent="center" p={4}>
          <CircularProgress />
        </Box>
      );
    }

    const summary = sectorIndustryData?.data?.summary || {};
    const sectors = sectorIndustryData?.data?.sectors || [];
    const industries = sectorIndustryData?.data?.industries || [];

    // Check if we have any portfolio data
    const hasData = sectors.length > 0 || industries.length > 0 || (summary.total_value && parseFloat(summary.total_value) > 0);

    return (
      <Grid container spacing={3}>
        {!hasData && (
          <Grid item xs={12}>
            <Card>
              <CardContent>
                <Typography color="textSecondary" align="center">
                  No portfolio holdings data available. Add holdings to your portfolio to see sector and industry analysis.
                </Typography>
              </CardContent>
            </Card>
          </Grid>
        )}
        {/* Diversification Summary */}
        <Grid item xs={12}>
          <Grid container spacing={2}>
            <Grid item xs={12} sm={6} md={3}>
              <Card>
                <CardContent>
                  <Box display="flex" alignItems="center" gap={2}>
                    <Assessment color="primary" />
                    <Box>
                      <Typography variant="h6">{summary.diversification_score || "N/A"}</Typography>
                      <Typography variant="body2" color="text.secondary">Diversification Score</Typography>
                    </Box>
                  </Box>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <Card>
                <CardContent>
                  <Box display="flex" alignItems="center" gap={2}>
                    <ShowChart color="secondary" />
                    <Box>
                      <Typography variant="h6">{summary.top_3_concentration || "N/A"}%</Typography>
                      <Typography variant="body2" color="text.secondary">Top 3 Concentration</Typography>
                    </Box>
                  </Box>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <Card>
                <CardContent>
                  <Box display="flex" alignItems="center" gap={2}>
                    <TrendingUp color="info" />
                    <Box>
                      <Typography variant="h6">{summary.sector_count || "0"}</Typography>
                      <Typography variant="body2" color="text.secondary">Sectors</Typography>
                    </Box>
                  </Box>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <Card>
                <CardContent>
                  <Box display="flex" alignItems="center" gap={2}>
                    <AccountBalance color="success" />
                    <Box>
                      <Typography variant="h6">{summary.industry_count || "0"}</Typography>
                      <Typography variant="body2" color="text.secondary">Industries</Typography>
                    </Box>
                  </Box>
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        </Grid>

        {/* Sector Allocation Chart */}
        <Grid item xs={12} lg={6}>
          <Card>
            <CardHeader title="Sector Allocation" />
            <CardContent>
              <ResponsiveContainer width="100%" height={350}>
                <BarChart data={sectors}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="name" angle={-45} textAnchor="end" height={80} />
                  <YAxis tickFormatter={(value) => `${value}%`} />
                  <RechartChartTooltip formatter={(value) => [`${value}%`, "Allocation"]} />
                  <Bar dataKey="allocation" fill="#8884d8" />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </Grid>

        {/* Sector Performance */}
        <Grid item xs={12} lg={6}>
          <Card>
            <CardHeader title="Sector Performance (Weighted)" />
            <CardContent>
              <ResponsiveContainer width="100%" height={350}>
                <BarChart data={sectors}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="name" angle={-45} textAnchor="end" height={80} />
                  <YAxis tickFormatter={(value) => `${value}%`} />
                  <RechartChartTooltip formatter={(value) => [`${value}%`, "Return"]} />
                  <Bar dataKey="gain_loss_percent" fill="#82ca9d" />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </Grid>

        {/* Industry Breakdown (Top 10) */}
        <Grid item xs={12}>
          <Card>
            <CardHeader title="Top Industries Breakdown" />
            <CardContent>
              <Box sx={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse" }}>
                  <thead>
                    <tr style={{ borderBottom: "2px solid #ddd" }}>
                      <th style={{ textAlign: "left", padding: "12px", fontWeight: 600 }}>Industry</th>
                      <th style={{ textAlign: "left", padding: "12px", fontWeight: 600 }}>Sector</th>
                      <th style={{ textAlign: "right", padding: "12px", fontWeight: 600 }}>Allocation</th>
                      <th style={{ textAlign: "right", padding: "12px", fontWeight: 600 }}>Value</th>
                      <th style={{ textAlign: "right", padding: "12px", fontWeight: 600 }}>Gain/Loss</th>
                      <th style={{ textAlign: "right", padding: "12px", fontWeight: 600 }}>Return %</th>
                      <th style={{ textAlign: "center", padding: "12px", fontWeight: 600 }}>Holdings</th>
                    </tr>
                  </thead>
                  <tbody>
                    {industries.slice(0, 10).map((industry, idx) => (
                      <tr key={idx} style={{ borderBottom: "1px solid #eee" }}>
                        <td style={{ padding: "12px" }}>{industry.name}</td>
                        <td style={{ padding: "12px" }}>{industry.sector}</td>
                        <td style={{ textAlign: "right", padding: "12px" }}>{parseFloat(industry.allocation).toFixed(2)}%</td>
                        <td style={{ textAlign: "right", padding: "12px", fontWeight: 500 }}>${parseFloat(industry.market_value).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
                        <td style={{ textAlign: "right", padding: "12px", color: parseFloat(industry.gain_loss) >= 0 ? "#4caf50" : "#f44336", fontWeight: 500 }}>
                          ${parseFloat(industry.gain_loss).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                        </td>
                        <td style={{ textAlign: "right", padding: "12px", color: parseFloat(industry.gain_loss_percent) >= 0 ? "#4caf50" : "#f44336", fontWeight: 500 }}>
                          {parseFloat(industry.gain_loss_percent).toFixed(2)}%
                        </td>
                        <td style={{ textAlign: "center", padding: "12px" }}>{industry.holdings_count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    );
  };

  const renderProfessionalMetricsTab = () => {
    if (profMetricsLoading) {
      return (
        <Box display="flex" justifyContent="center" p={4}>
          <CircularProgress />
        </Box>
      );
    }

    const summary = professionalMetricsData?.data?.summary || {};
    const positions = professionalMetricsData?.data?.positions || [];
    const metadata = professionalMetricsData?.data?.metadata || {};

    // Check if we have any metrics calculated
    const hasData = Object.values(summary).some(v => v !== 0 && v !== undefined);

    return (
      <Grid container spacing={3}>
        {!hasData && (
          <Grid item xs={12}>
            <Card>
              <CardContent>
                <Typography color="textSecondary" align="center">
                  No portfolio data available to calculate professional metrics. Add holdings to your portfolio to see advanced metrics.
                </Typography>
              </CardContent>
            </Card>
          </Grid>
        )}

        {/* Risk-Adjusted Returns Metrics */}
        <Grid item xs={12}>
          <Typography variant="h6" gutterBottom>Risk-Adjusted Returns</Typography>
          <Grid container spacing={2}>
            <Grid item xs={12} sm={6} md={3}>
              <Card>
                <CardContent>
                  <Box display="flex" alignItems="center" gap={2}>
                    <TrendingUp color="primary" />
                    <Box>
                      <Typography variant="h6">{summary.alpha?.toFixed(2) || "0.00"}%</Typography>
                      <Typography variant="body2" color="text.secondary">Alpha (Excess Return)</Typography>
                    </Box>
                  </Box>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <Card>
                <CardContent>
                  <Box display="flex" alignItems="center" gap={2}>
                    <Assessment color="success" />
                    <Box>
                      <Typography variant="h6">{summary.sortino_ratio?.toFixed(2) || "0.00"}</Typography>
                      <Typography variant="body2" color="text.secondary">Sortino Ratio</Typography>
                    </Box>
                  </Box>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <Card>
                <CardContent>
                  <Box display="flex" alignItems="center" gap={2}>
                    <ShowChart color="info" />
                    <Box>
                      <Typography variant="h6">{summary.information_ratio?.toFixed(2) || "0.00"}</Typography>
                      <Typography variant="body2" color="text.secondary">Information Ratio</Typography>
                    </Box>
                  </Box>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <Card>
                <CardContent>
                  <Box display="flex" alignItems="center" gap={2}>
                    <AccountBalance color="warning" />
                    <Box>
                      <Typography variant="h6">{summary.calmar_ratio?.toFixed(2) || "0.00"}</Typography>
                      <Typography variant="body2" color="text.secondary">Calmar Ratio</Typography>
                    </Box>
                  </Box>
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        </Grid>

        {/* Downside Risk Metrics */}
        <Grid item xs={12}>
          <Typography variant="h6" gutterBottom>Downside Risk Analysis</Typography>
          <Grid container spacing={2}>
            <Grid item xs={12} sm={6} md={3}>
              <Card>
                <CardContent>
                  <Box display="flex" alignItems="center" gap={2}>
                    <TrendingDown color="error" />
                    <Box>
                      <Typography variant="h6">{summary.downside_deviation?.toFixed(2) || "0.00"}%</Typography>
                      <Typography variant="body2" color="text.secondary">Downside Deviation</Typography>
                    </Box>
                  </Box>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <Card>
                <CardContent>
                  <Box display="flex" alignItems="center" gap={2}>
                    <Warning color="warning" />
                    <Box>
                      <Typography variant="h6">{summary.drawdown_analysis?.max_drawdown?.toFixed(2) || "0.00"}%</Typography>
                      <Typography variant="body2" color="text.secondary">Max Drawdown</Typography>
                    </Box>
                  </Box>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <Card>
                <CardContent>
                  <Box display="flex" alignItems="center" gap={2}>
                    <Info color="info" />
                    <Box>
                      <Typography variant="h6">{summary.risk_metrics?.var_95?.toFixed(2) || "0.00"}%</Typography>
                      <Typography variant="body2" color="text.secondary">VaR (95% Confidence)</Typography>
                    </Box>
                  </Box>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <Card>
                <CardContent>
                  <Box display="flex" alignItems="center" gap={2}>
                    <BarChartIcon color="secondary" />
                    <Box>
                      <Typography variant="h6">{summary.risk_metrics?.cvar_95?.toFixed(2) || "0.00"}%</Typography>
                      <Typography variant="body2" color="text.secondary">CVaR (Expected Shortfall)</Typography>
                    </Box>
                  </Box>
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        </Grid>

        {/* Tail Risk Metrics */}
        <Grid item xs={12}>
          <Typography variant="h6" gutterBottom>Tail Risk & Distribution</Typography>
          <Grid container spacing={2}>
            <Grid item xs={12} sm={6}>
              <Card>
                <CardContent>
                  <Box display="flex" alignItems="center" gap={2}>
                    <Assessment color="primary" />
                    <Box>
                      <Typography variant="h6">{summary.risk_metrics?.skewness?.toFixed(3) || "0.000"}</Typography>
                      <Typography variant="body2" color="text.secondary">Skewness (Distribution Shape)</Typography>
                      <Typography variant="caption" color="text.secondary">
                        {summary.risk_metrics?.skewness > 0.5 ? "Right-skewed (good)" : summary.risk_metrics?.skewness < -0.5 ? "Left-skewed (risky)" : "Neutral"}
                      </Typography>
                    </Box>
                  </Box>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} sm={6}>
              <Card>
                <CardContent>
                  <Box display="flex" alignItems="center" gap={2}>
                    <ShowChart color="secondary" />
                    <Box>
                      <Typography variant="h6">{summary.risk_metrics?.kurtosis?.toFixed(3) || "0.000"}</Typography>
                      <Typography variant="body2" color="text.secondary">Kurtosis (Fat Tails Risk)</Typography>
                      <Typography variant="caption" color="text.secondary">
                        {summary.risk_metrics?.kurtosis > 3.5 ? "High tail risk" : "Normal tail risk"}
                      </Typography>
                    </Box>
                  </Box>
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        </Grid>

        {/* Position-Level Attribution */}
        {positions.length > 0 && (
          <Grid item xs={12}>
            <Card>
              <CardHeader title="Position-Level Metrics (Top 10)" />
              <CardContent>
                <Box sx={{ overflowX: "auto" }}>
                  <table style={{ width: "100%", borderCollapse: "collapse" }}>
                    <thead>
                      <tr style={{ borderBottom: "2px solid #ddd" }}>
                        <th style={{ textAlign: "left", padding: "12px", fontWeight: 600 }}>Symbol</th>
                        <th style={{ textAlign: "right", padding: "12px", fontWeight: 600 }}>Weight %</th>
                        <th style={{ textAlign: "right", padding: "12px", fontWeight: 600 }}>Value $</th>
                        <th style={{ textAlign: "right", padding: "12px", fontWeight: 600 }}>Risk Contrib %</th>
                        <th style={{ textAlign: "right", padding: "12px", fontWeight: 600 }}>Return Contrib %</th>
                        <th style={{ textAlign: "right", padding: "12px", fontWeight: 600 }}>Volatility %</th>
                      </tr>
                    </thead>
                    <tbody>
                      {positions.slice(0, 10).map((pos, idx) => (
                        <tr key={idx} style={{ borderBottom: "1px solid #eee" }}>
                          <td style={{ padding: "12px", fontWeight: 500 }}>{pos.symbol}</td>
                          <td style={{ textAlign: "right", padding: "12px" }}>{parseFloat(pos.weight || 0).toFixed(2)}%</td>
                          <td style={{ textAlign: "right", padding: "12px" }}>${parseFloat(pos.value || 0).toLocaleString("en-US", { minimumFractionDigits: 2 })}</td>
                          <td style={{ textAlign: "right", padding: "12px" }}>{parseFloat(pos.risk_contribution || 0).toFixed(2)}%</td>
                          <td style={{ textAlign: "right", padding: "12px", color: parseFloat(pos.return_contribution || 0) >= 0 ? "#4caf50" : "#f44336" }}>{parseFloat(pos.return_contribution || 0).toFixed(2)}%</td>
                          <td style={{ textAlign: "right", padding: "12px" }}>{parseFloat(pos.volatility || 0).toFixed(2)}%</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </Box>
              </CardContent>
            </Card>
          </Grid>
        )}

        {/* Metadata */}
        <Grid item xs={12}>
          <Card sx={{ bgcolor: "#f5f5f5" }}>
            <CardContent>
              <Typography variant="body2" color="text.secondary">
                <strong>Calculation Basis:</strong> {metadata.calculation_basis || "N/A"} •
                <strong> Benchmark:</strong> {metadata.benchmark || "SPY"} •
                <strong> Risk-Free Rate:</strong> {metadata.risk_free_rate || "2%"} •
                <strong> Data Points:</strong> {metadata.data_points || "0"}
              </Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    );
  };

  return (
    <Box>
      <Paper sx={{ mb: 2 }}>
        <Tabs value={analyticsTab} onChange={(_, v) => setAnalyticsTab(v)} variant="scrollable" scrollButtons="auto">
          <Tab label="Performance" />
          <Tab label="Risk Analysis" />
          <Tab label="Asset Allocation" />
          <Tab label="Correlation" />
          <Tab label="Volatility & Trends" />
          <Tab label="Sector & Industry" />
          <Tab label="Professional Metrics" />
        </Tabs>
      </Paper>
      <Box mt={2}>
        {analyticsTab === 0 && renderPerformanceTab()}
        {analyticsTab === 1 && renderRiskTab()}
        {analyticsTab === 2 && (
          <Grid container spacing={3}>
            <Grid item xs={12} md={6}>
              <Card>
                <CardHeader title="Sector Allocation" />
                <CardContent>
                  <ResponsiveContainer width="100%" height={300}>
                    <PieChart>
                      <Pie data={allocationData?.data?.sectors || []} dataKey="percentage" cx="50%" cy="50%" outerRadius={100} fill="#8884d8" label={({ name, percentage }) => `${name}: ${percentage}%`}>
                        {(allocationData?.data?.sectors || []).map((_, index) => (
                          <Cell key={`cell-${index}`} fill={`hsl(${index * 45}, 70%, 60%)`} />
                        ))}
                      </Pie>
                      <RechartsTooltip />
                    </PieChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} md={6}>
              <Card>
                <CardHeader title="Top Holdings" />
                <CardContent>
                  <ResponsiveContainer width="100%" height={300}>
                    <BarChart data={(allocationData?.data?.assets || []).slice(0, 10)}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="symbol" />
                      <YAxis tickFormatter={(value) => `${value}%`} />
                      <RechartChartTooltip formatter={(value) => [`${value}%`, "Weight"]} />
                      <Bar dataKey="percentage" fill="#8884d8" />
                    </BarChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        )}
        {analyticsTab === 3 && renderCorrelationTab()}
        {analyticsTab === 4 && renderVolatilityTab()}
        {analyticsTab === 5 && renderSectorIndustryTab()}
        {analyticsTab === 6 && renderProfessionalMetricsTab()}
      </Box>
    </Box>
  );
};

const PortfolioHoldings = () => {
  const { user, tokens } = useAuth();

  useDocumentTitle("Portfolio Holdings");

  // State management
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Portfolio data
  const [holdings, setHoldings] = useState([]);
  const [portfolioSummary, setPortfolioSummary] = useState(null);

  // UI state
  const [orderBy, setOrderBy] = useState("marketValue");
  const [order, setOrder] = useState("desc");
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(25);
  const [timeframe, setTimeframe] = useState("1Y");

  // Dialogs
  const [addHoldingDialog, setAddHoldingDialog] = useState(false);
  const [editHoldingDialog, setEditHoldingDialog] = useState(false);
  const [importDialog, setImportDialog] = useState(false);
  const [selectedHolding, setSelectedHolding] = useState(null);
  const [selectedBroker, setSelectedBroker] = useState("");

  // Form state
  const [holdingForm, setHoldingForm] = useState({
    symbol: "",
    shares: "",
    avgCost: "",
  });

  // Load portfolio data
  const loadPortfolioData = useCallback(async () => {
    if (
      (!user?.userId && !user?.id) ||
      (!tokens?.accessToken && !tokens?.access)
    ) {
      setError("Authentication required");
      setLoading(false);
      return;
    }

    try {
      setLoading(true);
      setError(null);

      // Load holdings
      const userId = user.userId || user.id;
      const holdingsResponse = await getPortfolioHoldings(userId);
      if (holdingsResponse?.data?.holdings) {
        setHoldings(holdingsResponse.data.holdings);
        setPortfolioSummary(holdingsResponse.data.summary);

        // Load current stock prices for holdings
        const symbols = holdingsResponse.data.holdings.map(h => h.symbol);
        if (symbols.length > 0) {
          try {
            await getStockPrices(symbols);
          } catch (priceError) {
            console.warn("Failed to fetch current stock prices:", priceError);
            // Don't fail the entire load for price errors
          }
        }
      } else {
        throw new Error("No portfolio holdings found");
      }
    } catch (err) {
      if (import.meta.env && import.meta.env.DEV)
        console.error("Portfolio data loading error:", err);
      setError(err.message || "Failed to load portfolio data");
    } finally {
      setLoading(false);
    }
  }, [user?.userId, user?.id, tokens?.accessToken, tokens?.access]);

  // Load data on component mount and when timeframe changes
  useEffect(() => {
    loadPortfolioData();
  }, [loadPortfolioData]);

  // Handle holding operations
  const handleAddHolding = async () => {
    try {
      const response = await addHolding({
        userId: user.userId || user.id,
        symbol: holdingForm.symbol.toUpperCase(),
        shares: parseFloat(holdingForm.shares),
        avgCost: parseFloat(holdingForm.avgCost),
      });

      if (response.success) {
        setAddHoldingDialog(false);
        setHoldingForm({ symbol: "", shares: "", avgCost: "" });
        loadPortfolioData(); // Reload data
      } else {
        throw new Error(response.message || "Failed to add holding");
      }
    } catch (err) {
      setError(err.message);
    }
  };

  const handleUpdateHolding = async () => {
    try {
      const response = await updateHolding(selectedHolding.symbol, {
        userId: user.userId || user.id,
        shares: parseFloat(holdingForm.shares),
        avgCost: parseFloat(holdingForm.avgCost),
      });

      if (response.success) {
        setEditHoldingDialog(false);
        setSelectedHolding(null);
        setHoldingForm({ symbol: "", shares: "", avgCost: "" });
        loadPortfolioData(); // Reload data
      } else {
        throw new Error(response.message || "Failed to update holding");
      }
    } catch (err) {
      setError(err.message);
    }
  };

  const handleDeleteHolding = async (symbol) => {
    if (!window.confirm(`Are you sure you want to delete ${symbol}?`)) return;

    try {
      const userId = user.userId || user.id;
      const response = await deleteHolding(symbol, userId);
      if (response.success) {
        loadPortfolioData(); // Reload data
      } else {
        throw new Error(response.message || "Failed to delete holding");
      }
    } catch (err) {
      setError(err.message);
    }
  };

  const handleImportPortfolio = async () => {
    if (!selectedBroker) {
      setError("Please select a broker");
      return;
    }

    try {
      setLoading(true);
      setError(null);
      const response = await importPortfolioFromBroker(selectedBroker);
      if (response.success) {
        setImportDialog(false);
        setSelectedBroker("");
        loadPortfolioData(); // Reload data to show imported positions
      } else {
        throw new Error(response.message || "Failed to import portfolio");
      }
    } catch (err) {
      setError(err.message || "Failed to import portfolio. Please check your API credentials and try again.");
    } finally {
      setLoading(false);
    }
  };

  // Sorting and pagination
  const sortedHoldings = useMemo(() => {
    if (!holdings?.length) return [];

    return [...holdings].sort((a, b) => {
      let aVal = a[orderBy];
      let bVal = b[orderBy];

      if (typeof aVal === "string") {
        aVal = aVal.toLowerCase();
        bVal = bVal.toLowerCase();
      }

      if (order === "desc") {
        return bVal > aVal ? 1 : -1;
      }
      return aVal > bVal ? 1 : -1;
    });
  }, [holdings, orderBy, order]);

  const paginatedHoldings = useMemo(() => {
    const startIndex = page * rowsPerPage;
    return sortedHoldings.slice(startIndex, startIndex + rowsPerPage);
  }, [sortedHoldings, page, rowsPerPage]);

  // Chart data preparation
  const allocationChartData = useMemo(() => {
    if (!holdings?.length) return [];
    return holdings.map((holding) => ({
      symbol: holding.symbol,
      value: holding.marketValue || 0,
      allocation: holding.allocation || 0,
    }));
  }, [holdings]);

  const sectorChartData = useMemo(() => {
    if (!holdings?.length) return [];
    const sectorTotals = holdings.reduce((acc, holding) => {
      const sector = holding.sector || "Unknown";
      acc[sector] = (acc[sector] || 0) + (holding.marketValue || 0);
      return acc;
    }, {});

    return Object.entries(sectorTotals).map(([sector, value]) => ({
      sector,
      value,
      allocation: portfolioSummary?.totalValue
        ? (value / portfolioSummary.totalValue) * 100
        : 0,
    }));
  }, [holdings, portfolioSummary]);

  if (loading && !holdings.length) {
    return (
      <Container maxWidth="xl" sx={{ mt: 4, mb: 4 }} data-testid="portfolio-page">
        <Box
          display="flex"
          justifyContent="center"
          alignItems="center"
          minHeight="400px"
        >
          <CircularProgress size={60} />
          <Typography variant="h6" sx={{ ml: 2 }}>
            Loading portfolio data...
          </Typography>
        </Box>
      </Container>
    );
  }

  return (
    <Container maxWidth="xl" sx={{ mt: 4, mb: 4 }} data-testid="portfolio-page">
      <Grid container spacing={3}>
        {/* Header */}
        <Grid item xs={12}>
          <Paper sx={{ p: 3, mb: 3 }}>
            <Box
              display="flex"
              justifyContent="space-between"
              alignItems="center"
            >
              <Typography variant="h4" gutterBottom>
                Portfolio Holdings & Analysis
              </Typography>
              <Box display="flex" gap={2}>
                <FormControl size="small">
                  <InputLabel>Timeframe</InputLabel>
                  <Select
                    value={timeframe}
                    onChange={(e) => setTimeframe(e.target.value)}
                    label="Timeframe"
                  >
                    <MenuItem value="1M">1 Month</MenuItem>
                    <MenuItem value="3M">3 Months</MenuItem>
                    <MenuItem value="6M">6 Months</MenuItem>
                    <MenuItem value="1Y">1 Year</MenuItem>
                    <MenuItem value="2Y">2 Years</MenuItem>
                  </Select>
                </FormControl>
                <Button
                  variant="outlined"
                  startIcon={<Refresh />}
                  onClick={loadPortfolioData}
                  disabled={loading}
                  aria-label="refresh"
                >
                  Refresh
                </Button>
                <Button
                  variant="outlined"
                  startIcon={<CloudDownload />}
                  onClick={() => setImportDialog(true)}
                  disabled={loading}
                  data-testid="import-portfolio-button"
                >
                  Import Portfolio
                </Button>
                <Button
                  variant="contained"
                  startIcon={<Add />}
                  onClick={() => setAddHoldingDialog(true)}
                >
                  Add Holding
                </Button>
              </Box>
            </Box>

            {/* Portfolio Summary */}
            {portfolioSummary && (
              <Grid container spacing={2} sx={{ mt: 2 }}>
                <Grid item xs={12} sm={6} md={3}>
                  <Card>
                    <CardContent>
                      <Typography color="textSecondary" gutterBottom>
                        Total Value
                      </Typography>
                      <Typography variant="h5">
                        ${portfolioSummary.totalValue?.toLocaleString() || "0"}
                      </Typography>
                    </CardContent>
                  </Card>
                </Grid>
                <Grid item xs={12} sm={6} md={3}>
                  <Card>
                    <CardContent>
                      <Typography color="textSecondary" gutterBottom>
                        Total Gain/Loss
                      </Typography>
                      <Typography
                        variant="h5"
                        color={
                          portfolioSummary.totalGainLoss >= 0
                            ? "success.main"
                            : "error.main"
                        }
                      >
                        $
                        {portfolioSummary.totalGainLoss?.toLocaleString() ||
                          "0"}
                      </Typography>
                    </CardContent>
                  </Card>
                </Grid>
                <Grid item xs={12} sm={6} md={3}>
                  <Card>
                    <CardContent>
                      <Typography color="textSecondary" gutterBottom>
                        Total Return %
                      </Typography>
                      <Typography
                        variant="h5"
                        color={
                          portfolioSummary.totalGainLossPercent >= 0
                            ? "success.main"
                            : "error.main"
                        }
                      >
                        {portfolioSummary.totalGainLossPercent?.toFixed(2) ||
                          "0.00"}
                        %
                      </Typography>
                    </CardContent>
                  </Card>
                </Grid>
                <Grid item xs={12} sm={6} md={3}>
                  <Card>
                    <CardContent>
                      <Typography color="textSecondary" gutterBottom>
                        Holdings Count
                      </Typography>
                      <Typography variant="h5">
                        {holdings?.length || 0}
                      </Typography>
                    </CardContent>
                  </Card>
                </Grid>
              </Grid>
            )}
          </Paper>
        </Grid>

        {/* Error Display */}
        {error && (
          <Grid item xs={12}>
            <Alert
              severity="error"
              onClose={() => setError(null)}
              sx={{ mb: 2 }}
            >
              {error}
            </Alert>
          </Grid>
        )}

        {/* Portfolio Holdings */}
        <Grid item xs={12}>
            <Paper sx={{ p: 3 }}>
            <Box
              display="flex"
              justifyContent="space-between"
              alignItems="center"
              mb={2}
            >
              <Typography variant="h6">Portfolio Holdings</Typography>
              <Box display="flex" gap={1}>
                <IconButton size="small">
                  <FilterList />
                </IconButton>
              </Box>
            </Box>

            {/* Holdings Table */}
            <TableContainer>
              <Table>
                <TableHead>
                  <TableRow>
                    <TableCell>
                      <TableSortLabel
                        active={orderBy === "symbol"}
                        direction={order}
                        onClick={() => {
                          setOrder(
                            orderBy === "symbol" && order === "asc"
                              ? "desc"
                              : "asc"
                          );
                          setOrderBy("symbol");
                        }}
                      >
                        Symbol
                      </TableSortLabel>
                    </TableCell>
                    <TableCell>Company</TableCell>
                    <TableCell align="right">
                      <TableSortLabel
                        active={orderBy === "shares"}
                        direction={order}
                        onClick={() => {
                          setOrder(
                            orderBy === "shares" && order === "asc"
                              ? "desc"
                              : "asc"
                          );
                          setOrderBy("shares");
                        }}
                      >
                        Shares
                      </TableSortLabel>
                    </TableCell>
                    <TableCell align="right">Avg Cost</TableCell>
                    <TableCell align="right">Current Price</TableCell>
                    <TableCell align="right">
                      <TableSortLabel
                        active={orderBy === "marketValue"}
                        direction={order}
                        onClick={() => {
                          setOrder(
                            orderBy === "marketValue" && order === "asc"
                              ? "desc"
                              : "asc"
                          );
                          setOrderBy("marketValue");
                        }}
                      >
                        Market Value
                      </TableSortLabel>
                    </TableCell>
                    <TableCell align="right">Gain/Loss</TableCell>
                    <TableCell align="right">Gain/Loss %</TableCell>
                    <TableCell align="right">Allocation</TableCell>
                    <TableCell align="center">Actions</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {paginatedHoldings.map((holding, index) => (
                    <TableRow
                      key={`${holding.symbol}-${holding.id || index}`}
                      hover
                    >
                      <TableCell>
                        <Typography variant="body2" fontWeight="bold">
                          {holding.symbol}
                        </Typography>
                      </TableCell>
                      <TableCell>
                        <Typography variant="body2">
                          {holding.company || "N/A"}
                        </Typography>
                      </TableCell>
                      <TableCell align="right">
                        {holding.shares?.toLocaleString() || 0}
                      </TableCell>
                      <TableCell align="right">
                        ${holding.avgCost?.toFixed(2) || "0.00"}
                      </TableCell>
                      <TableCell align="right">
                        ${holding.currentPrice?.toFixed(2) || "0.00"}
                      </TableCell>
                      <TableCell align="right">
                        ${holding.marketValue?.toLocaleString() || "0"}
                      </TableCell>
                      <TableCell
                        align="right"
                        sx={{
                          color:
                            holding.gainLoss >= 0
                              ? "success.main"
                              : "error.main",
                        }}
                      >
                        ${holding.gainLoss?.toLocaleString() || "0"}
                      </TableCell>
                      <TableCell
                        align="right"
                        sx={{
                          color:
                            holding.gainLossPercent >= 0
                              ? "success.main"
                              : "error.main",
                        }}
                      >
                        {holding.gainLossPercent?.toFixed(2) || "0.00"}%
                      </TableCell>
                      <TableCell align="right">
                        {holding.allocation?.toFixed(1) || "0.0"}%
                      </TableCell>
                      <TableCell align="center">
                        <IconButton
                          size="small"
                          aria-label="edit"
                          onClick={() => {
                            setSelectedHolding(holding);
                            setHoldingForm({
                              symbol: holding.symbol,
                              shares: holding.shares.toString(),
                              avgCost: holding.avgCost.toString(),
                            });
                            setEditHoldingDialog(true);
                          }}
                        >
                          <Edit />
                        </IconButton>
                        <IconButton
                          size="small"
                          aria-label="delete"
                          onClick={() => handleDeleteHolding(holding.symbol)}
                          color="error"
                        >
                          <Delete />
                        </IconButton>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>

            <TablePagination
              rowsPerPageOptions={[10, 25, 50]}
              component="div"
              count={sortedHoldings.length}
              rowsPerPage={rowsPerPage}
              page={page}
              onPageChange={(e, newPage) => setPage(newPage)}
              onRowsPerPageChange={(e) => {
                setRowsPerPage(parseInt(e.target.value, 10));
                setPage(0);
              }}
            />

            {/* Allocation Charts */}
            <Grid container spacing={3} sx={{ mt: 3 }}>
              <Grid item xs={12} md={6}>
                <Card>
                  <CardHeader title="Holdings Allocation" />
                  <CardContent>
                    <ResponsiveContainer width="100%" height={300}>
                      <PieChart>
                        <Pie
                          data={allocationChartData}
                          dataKey="value"
                          cx="50%"
                          cy="50%"
                          outerRadius={100}
                          fill="#8884d8"
                        >
                          {allocationChartData.map((entry, index) => (
                            <Cell
                              key={`cell-${index}`}
                              fill={`hsl(${index * 45}, 70%, 60%)`}
                            />
                          ))}
                        </Pie>
                        <RechartsTooltip
                          formatter={(value) => [
                            `$${value.toLocaleString()}`,
                            "Value",
                          ]}
                        />
                      </PieChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>
              </Grid>
              <Grid item xs={12} md={6}>
                <Card>
                  <CardHeader title="Sector Allocation" />
                  <CardContent>
                    <ResponsiveContainer width="100%" height={300}>
                      <PieChart>
                        <Pie
                          data={sectorChartData}
                          dataKey="value"
                          cx="50%"
                          cy="50%"
                          outerRadius={100}
                          fill="#82ca9d"
                        >
                          {sectorChartData.map((entry, index) => (
                            <Cell
                              key={`cell-${index}`}
                              fill={`hsl(${index * 60}, 70%, 60%)`}
                            />
                          ))}
                        </Pie>
                        <RechartsTooltip
                          formatter={(value) => [
                            `$${value.toLocaleString()}`,
                            "Value",
                          ]}
                        />
                      </PieChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>
          </Paper>
        </Grid>

        {/* Advanced Analytics */}
        <Grid item xs={12}>
          <AdvancedAnalyticsContent timeframe={timeframe} />
        </Grid>
      </Grid>

      {/* Add Holding Dialog */}
      <Dialog
        open={addHoldingDialog}
        onClose={() => setAddHoldingDialog(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Add New Holding</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            margin="dense"
            label="Symbol"
            fullWidth
            variant="outlined"
            value={holdingForm.symbol}
            onChange={(e) =>
              setHoldingForm({
                ...holdingForm,
                symbol: e.target.value.toUpperCase(),
              })
            }
            sx={{ mb: 2 }}
          />
          <TextField
            margin="dense"
            label="Shares"
            type="number"
            fullWidth
            variant="outlined"
            value={holdingForm.shares}
            onChange={(e) =>
              setHoldingForm({ ...holdingForm, shares: e.target.value })
            }
            sx={{ mb: 2 }}
          />
          <TextField
            margin="dense"
            label="Average Cost"
            type="number"
            fullWidth
            variant="outlined"
            value={holdingForm.avgCost}
            onChange={(e) =>
              setHoldingForm({ ...holdingForm, avgCost: e.target.value })
            }
            step="0.01"
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAddHoldingDialog(false)}>Cancel</Button>
          <Button onClick={handleAddHolding} variant="contained">
            Add Holding
          </Button>
        </DialogActions>
      </Dialog>

      {/* Edit Holding Dialog */}
      <Dialog
        open={editHoldingDialog}
        onClose={() => setEditHoldingDialog(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Edit Holding: {selectedHolding?.symbol}</DialogTitle>
        <DialogContent>
          <TextField
            margin="dense"
            label="Shares"
            type="number"
            fullWidth
            variant="outlined"
            value={holdingForm.shares}
            onChange={(e) =>
              setHoldingForm({ ...holdingForm, shares: e.target.value })
            }
            sx={{ mb: 2 }}
          />
          <TextField
            margin="dense"
            label="Average Cost"
            type="number"
            fullWidth
            variant="outlined"
            value={holdingForm.avgCost}
            onChange={(e) =>
              setHoldingForm({ ...holdingForm, avgCost: e.target.value })
            }
            step="0.01"
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditHoldingDialog(false)}>Cancel</Button>
          <Button onClick={handleUpdateHolding} variant="contained">
            Update Holding
          </Button>
        </DialogActions>
      </Dialog>

      {/* Import Portfolio Dialog */}
      <Dialog
        open={importDialog}
        onClose={() => setImportDialog(false)}
        maxWidth="sm"
        fullWidth
        data-testid="import-portfolio-dialog"
      >
        <DialogTitle>Import Portfolio from Broker</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Import your portfolio positions from your connected broker account.
            Make sure you have configured your API keys in the Settings page.
          </Typography>
          <FormControl fullWidth sx={{ mt: 2 }}>
            <InputLabel>Select Broker</InputLabel>
            <Select
              value={selectedBroker}
              onChange={(e) => setSelectedBroker(e.target.value)}
              label="Select Broker"
              data-testid="broker-select"
            >
              <MenuItem value="alpaca">Alpaca</MenuItem>
            </Select>
          </FormControl>
          {error && (
            <Alert severity="error" sx={{ mt: 2 }}>
              {error}
            </Alert>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setImportDialog(false)}>Cancel</Button>
          <Button
            onClick={handleImportPortfolio}
            variant="contained"
            disabled={!selectedBroker || loading}
            data-testid="import-confirm-button"
          >
            {loading ? "Importing..." : "Import Portfolio"}
          </Button>
        </DialogActions>
      </Dialog>
    </Container>
  );
};

export default PortfolioHoldings;
