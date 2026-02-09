import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Box,
  Card,
  CardContent,
  CardHeader,
  Chip,
  Container,
  Grid,
  Typography,
  CircularProgress,
  Alert,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  LinearProgress,
  Paper,
  Button,
  Tabs,
  Tab,
  TextField,
  MenuItem,
  Select,
  FormControl,
  InputLabel,
} from "@mui/material";
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ScatterChart,
  Scatter,
  ComposedChart,
  Area,
  AreaChart,
  Heatmap,
} from "recharts";
import {
  TrendingUp,
  TrendingDown,
  Info,
  Download,
  BoltTwoTone,
  SignalCellularAlt,
  WarningAmber,
} from "@mui/icons-material";
import api from "../services/api";
import { getChangeColor } from "../utils/formatters";

const COLORS = ["#0088FE", "#00C49F", "#FFBB28", "#FF8042", "#8884D8", "#82CA9D"];

function TabPanel(props) {
  const { children, value, index, ...other } = props;
  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`tabpanel-${index}`}
      aria-labelledby={`tab-${index}`}
      {...other}
    >
      {value === index && <Box sx={{ pt: 3 }}>{children}</Box>}
    </div>
  );
}

export default function CommoditiesAnalysis() {
  const [selectedCommodity, setSelectedCommodity] = useState("GC=F");
  const [activeTab, setActiveTab] = useState(0);
  const [filterCategory, setFilterCategory] = useState("all");
  const [searchText, setSearchText] = useState("");

  // Fetch all data with caching
  const categoriesQuery = useQuery({
    queryKey: ["commodities-categories"],
    queryFn: async () => {
      const response = await api.get("/api/commodities/categories");
      return response.data.data;
    },
    staleTime: 5 * 60 * 1000,
  });

  const pricesQuery = useQuery({
    queryKey: ["commodities-prices"],
    queryFn: async () => {
      const response = await api.get("/api/commodities/prices?limit=100");
      return response.data.data;
    },
    staleTime: 2 * 60 * 1000,
  });

  const summaryQuery = useQuery({
    queryKey: ["commodities-summary"],
    queryFn: async () => {
      const response = await api.get("/api/commodities/market-summary");
      return response.data.data;
    },
    staleTime: 2 * 60 * 1000,
  });

  const correlationsQuery = useQuery({
    queryKey: ["commodities-correlations"],
    queryFn: async () => {
      const response = await api.get("/api/commodities/correlations?minCorrelation=0.5");
      return response.data.data.correlations;
    },
    staleTime: 30 * 60 * 1000,
  });

  const cotQuery = useQuery({
    queryKey: ["commodities-cot", selectedCommodity],
    queryFn: async () => {
      try {
        const response = await api.get(`/api/commodities/cot/${selectedCommodity}`);
        return response.data.data;
      } catch {
        return null;
      }
    },
    staleTime: 24 * 60 * 60 * 1000,
  });

  const seasonalityQuery = useQuery({
    queryKey: ["commodities-seasonality", selectedCommodity],
    queryFn: async () => {
      try {
        const response = await api.get(`/api/commodities/seasonality/${selectedCommodity}`);
        return response.data.data;
      } catch {
        return null;
      }
    },
    staleTime: 7 * 24 * 60 * 60 * 1000,
  });

  const isLoading =
    categoriesQuery.isLoading ||
    pricesQuery.isLoading ||
    summaryQuery.isLoading ||
    correlationsQuery.isLoading;

  // ============ DATA PROCESSING ============

  // Smart Trading Signals
  const tradingSignals = useMemo(() => {
    if (!pricesQuery.data || !seasonalityQuery.data) return [];

    const currentMonth = new Date().getMonth() + 1;
    const seasonalData = seasonalityQuery.data.seasonality?.find(
      (s) => s.month === currentMonth
    );

    const signals = [];

    if (seasonalData && parseFloat(seasonalData.winRate) > 60) {
      signals.push({
        type: "seasonal",
        strength: "strong",
        message: `${selectedCommodity}: Strong seasonal pattern for ${seasonalData.monthName} (${seasonalData.winRate}% win rate)`,
        action: "BUY",
        score: parseFloat(seasonalData.winRate),
      });
    }

    if (cotQuery.data?.analysis?.commercialSentiment === "bullish") {
      signals.push({
        type: "cot",
        strength: "strong",
        message: `${selectedCommodity}: Commercial hedgers are bullish (Pros know)`,
        action: "BUY",
        score: 75,
      });
    }

    const commodity = pricesQuery.data.find(
      (c) => c.symbol === selectedCommodity
    );
    if (commodity && parseFloat(commodity.changePercent) > 2) {
      signals.push({
        type: "momentum",
        strength: "moderate",
        message: `${selectedCommodity}: Strong upward momentum (+${commodity.changePercent}%)`,
        action: "BUY",
        score: 60,
      });
    }

    return signals.sort((a, b) => b.score - a.score);
  }, [selectedCommodity, pricesQuery.data, seasonalityQuery.data, cotQuery.data]);

  // Risk Analysis
  const riskMetrics = useMemo(() => {
    if (!pricesQuery.data || !correlationsQuery.data) return {};

    const commodity = pricesQuery.data.find((c) => c.symbol === selectedCommodity);
    if (!commodity) return {};

    const highCorrelations = correlationsQuery.data.filter(
      (c) =>
        (c.symbol1 === selectedCommodity || c.symbol2 === selectedCommodity) &&
        parseFloat(c.coefficient) > 0.7
    );

    const volatility = parseFloat(seasonalityQuery.data?.seasonality?.[0]?.volatility || 0) * 100;
    const diversificationScore =
      100 - Math.min(100, highCorrelations.length * 20);

    return {
      volatility: volatility.toFixed(2),
      diversificationScore,
      hedgeOpportunities: highCorrelations.length,
      riskLevel:
        volatility > 2 ? "HIGH" : volatility > 1 ? "MEDIUM" : "LOW",
      priceRange52w: `${commodity.low52w} - ${commodity.high52w}`,
      distanceFromHigh: (
        ((commodity.high52w - commodity.price) / commodity.high52w) *
        100
      ).toFixed(1),
    };
  }, [selectedCommodity, pricesQuery.data, correlationsQuery.data, seasonalityQuery.data]);

  // Top Opportunities
  const topOpportunities = useMemo(() => {
    if (!pricesQuery.data) return [];

    return pricesQuery.data
      .filter(
        (c) => filterCategory === "all" || c.category === filterCategory
      )
      .map((c) => {
        const distanceFromHigh = (
          ((c.high52w - c.price) / c.high52w) *
          100
        ).toFixed(1);
        const volumeScore = c.volume / 1000000; // millions

        return {
          ...c,
          opportunity:
            parseFloat(distanceFromHigh) > 20 && volumeScore > 10 ? "STRONG" : "MODERATE",
          volumeScore,
          distanceFromHigh,
        };
      })
      .sort((a, b) => {
        if (a.opportunity !== b.opportunity)
          return a.opportunity === "STRONG" ? -1 : 1;
        return b.volumeScore - a.volumeScore;
      })
      .slice(0, 15);
  }, [pricesQuery.data, filterCategory]);

  // Sector Momentum
  const sectorMomentum = useMemo(() => {
    if (!summaryQuery.data?.sectors) return [];

    return summaryQuery.data.sectors.map((sector) => ({
      name: sector.name,
      change: parseFloat(sector.change1d) || 0,
      trend: sector.trend === "up" ? "📈" : "📉",
      momentum: sector.trend === "up" ? "Bullish" : "Bearish",
    }));
  }, [summaryQuery.data]);

  // Correlation Analysis
  const correlationPairs = useMemo(() => {
    if (!correlationsQuery.data) return [];

    return correlationsQuery.data
      .map((c) => ({
        ...c,
        coefficient: parseFloat(c.coefficient),
      }))
      .sort((a, b) => b.coefficient - a.coefficient);
  }, [correlationsQuery.data]);

  // Seasonality Chart Data
  const seasonalityData = seasonalityQuery.data?.seasonality || [];

  // COT History
  const cotHistoryData = cotQuery.data?.cotHistory?.slice(-12) || [];

  const cotSymbols = ["GC=F", "SI=F", "CL=F", "NG=F", "HG=F", "ZC=F", "ZS=F"];

  // ============ RENDER ============

  return (
    <Container maxWidth="xl" sx={{ py: 3 }}>
      {/* HEADER */}
      <Box sx={{ mb: 4, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <Box>
          <Typography variant="h4" component="h1" sx={{ fontWeight: 700, mb: 1 }}>
            🚀 Professional Commodities Trading Platform
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Real-time data, AI signals, risk analysis & portfolio optimization
          </Typography>
        </Box>
        <Button
          variant="outlined"
          startIcon={<Download />}
          onClick={() => {
            const data = JSON.stringify(
              {
                prices: pricesQuery.data,
                correlations: correlationsQuery.data,
                tradingSignals,
                riskMetrics,
              },
              null,
              2
            );
            const element = document.createElement("a");
            element.setAttribute(
              "href",
              "data:text/plain;charset=utf-8," + encodeURIComponent(data)
            );
            element.setAttribute("download", "commodities-analysis.json");
            element.style.display = "none";
            document.body.appendChild(element);
            element.click();
            document.body.removeChild(element);
          }}
        >
          Export Data
        </Button>
      </Box>

      {isLoading && (
        <Box sx={{ display: "flex", justifyContent: "center", py: 8 }}>
          <CircularProgress />
        </Box>
      )}

      {!isLoading && (
        <>
          {/* TAB NAVIGATION */}
          <Box sx={{ borderBottom: 1, borderColor: "divider", mb: 3 }}>
            <Tabs value={activeTab} onChange={(e, v) => setActiveTab(v)}>
              <Tab
                label="🎯 Executive Dashboard"
                id="tab-0"
                aria-controls="tabpanel-0"
                icon={<BoltTwoTone />}
                iconPosition="start"
              />
              <Tab
                label="📊 Market Analysis"
                id="tab-1"
                aria-controls="tabpanel-1"
                icon={<SignalCellularAlt />}
                iconPosition="start"
              />
              <Tab
                label="⚠️ Risk & Hedging"
                id="tab-2"
                aria-controls="tabpanel-2"
                icon={<WarningAmber />}
                iconPosition="start"
              />
              <Tab
                label="💡 Trading Signals"
                id="tab-3"
                aria-controls="tabpanel-3"
              />
              <Tab
                label="📈 Detailed Analysis"
                id="tab-4"
                aria-controls="tabpanel-4"
              />
            </Tabs>
          </Box>

          {/* TAB 0: EXECUTIVE DASHBOARD */}
          <TabPanel value={activeTab} index={0}>
            {/* KPI Cards */}
            {summaryQuery.data && (
              <>
                <Grid container spacing={2} sx={{ mb: 4 }}>
                  <Grid item xs={12} sm={6} md={3}>
                    <Paper elevation={2} sx={{ p: 2 }}>
                      <Typography color="textSecondary" variant="subtitle2" sx={{ mb: 1 }}>
                        Active Contracts
                      </Typography>
                      <Typography variant="h5" sx={{ fontWeight: 700 }}>
                        {summaryQuery.data.overview?.activeContracts || 0}
                      </Typography>
                      <Typography variant="caption" color="success.main">
                        ↑ All markets open
                      </Typography>
                    </Paper>
                  </Grid>
                  <Grid item xs={12} sm={6} md={3}>
                    <Paper elevation={2} sx={{ p: 2 }}>
                      <Typography color="textSecondary" variant="subtitle2" sx={{ mb: 1 }}>
                        Total Volume
                      </Typography>
                      <Typography variant="h5" sx={{ fontWeight: 700 }}>
                        {(summaryQuery.data.overview?.totalVolume / 1e6).toFixed(1)}M
                      </Typography>
                      <Typography variant="caption" color="info.main">
                        24h contracts traded
                      </Typography>
                    </Paper>
                  </Grid>
                  <Grid item xs={12} sm={6} md={3}>
                    <Paper elevation={2} sx={{ p: 2, backgroundColor: "success.light" }}>
                      <Typography color="textSecondary" variant="subtitle2" sx={{ mb: 1 }}>
                        Top Gainer
                      </Typography>
                      {summaryQuery.data.topGainers?.[0] && (
                        <>
                          <Typography variant="body2" sx={{ fontWeight: 600, mb: 1 }}>
                            {summaryQuery.data.topGainers[0].name}
                          </Typography>
                          <Chip
                            icon={<TrendingUp />}
                            label={`+${summaryQuery.data.topGainers[0].change}%`}
                            color="success"
                            size="small"
                          />
                        </>
                      )}
                    </Paper>
                  </Grid>
                  <Grid item xs={12} sm={6} md={3}>
                    <Paper elevation={2} sx={{ p: 2, backgroundColor: "error.light" }}>
                      <Typography color="textSecondary" variant="subtitle2" sx={{ mb: 1 }}>
                        Top Loser
                      </Typography>
                      {summaryQuery.data.topLosers?.[0] && (
                        <>
                          <Typography variant="body2" sx={{ fontWeight: 600, mb: 1 }}>
                            {summaryQuery.data.topLosers[0].name}
                          </Typography>
                          <Chip
                            icon={<TrendingDown />}
                            label={`${summaryQuery.data.topLosers[0].change}%`}
                            color="error"
                            size="small"
                          />
                        </>
                      )}
                    </Paper>
                  </Grid>
                </Grid>

                {/* Sector Momentum */}
                <Card elevation={2} sx={{ mb: 4 }}>
                  <CardHeader title="📊 Sector Momentum" />
                  <CardContent>
                    <Grid container spacing={2}>
                      {sectorMomentum.map((sector) => (
                        <Grid item xs={12} sm={6} md={4} key={sector.name}>
                          <Box sx={{ p: 2, border: "1px solid #ddd", borderRadius: 1 }}>
                            <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
                              <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
                                {sector.name}
                              </Typography>
                              <Typography
                                variant="body2"
                                sx={{
                                  color: sector.change > 0 ? "success.main" : "error.main",
                                  fontWeight: 600,
                                }}
                              >
                                {sector.trend} {sector.change > 0 ? "+" : ""}
                                {sector.change.toFixed(2)}%
                              </Typography>
                            </Box>
                            <LinearProgress
                              variant="determinate"
                              value={Math.min(Math.max(50 + sector.change * 5, 0), 100)}
                              sx={{
                                backgroundColor: "#e0e0e0",
                                "& .MuiLinearProgress-bar": {
                                  backgroundColor:
                                    sector.change > 0 ? "#4caf50" : "#f44336",
                                },
                              }}
                            />
                            <Typography
                              variant="caption"
                              sx={{ mt: 1, display: "block", color: "text.secondary" }}
                            >
                              {sector.momentum}
                            </Typography>
                          </Box>
                        </Grid>
                      ))}
                    </Grid>
                  </CardContent>
                </Card>

                {/* Category Performance */}
                <Grid container spacing={3} sx={{ mb: 4 }}>
                  <Grid item xs={12} md={6}>
                    <Card elevation={2}>
                      <CardHeader title="📈 Category Performance (1D)" />
                      <CardContent>
                        <ResponsiveContainer width="100%" height={300}>
                          <BarChart
                            data={categoriesQuery.data?.map((cat) => ({
                              name: cat.name,
                              change: parseFloat(cat.avgChange1d),
                            })) || []}
                          >
                            <CartesianGrid strokeDasharray="3 3" />
                            <XAxis dataKey="name" angle={-45} textAnchor="end" height={80} />
                            <YAxis />
                            <Tooltip formatter={(value) => `${value.toFixed(2)}%`} />
                            <Bar dataKey="change" fill="#8884d8" radius={[8, 8, 0, 0]} />
                          </BarChart>
                        </ResponsiveContainer>
                      </CardContent>
                    </Card>
                  </Grid>

                  <Grid item xs={12} md={6}>
                    <Card elevation={2}>
                      <CardHeader title="🥧 Commodity Distribution" />
                      <CardContent>
                        <ResponsiveContainer width="100%" height={300}>
                          <PieChart>
                            <Pie
                              data={
                                categoriesQuery.data?.map((cat) => ({
                                  name: cat.name,
                                  value: cat.commodityCount,
                                })) || []
                              }
                              dataKey="value"
                              nameKey="name"
                              cx="50%"
                              cy="50%"
                              outerRadius={80}
                              label
                            >
                              {categoriesQuery.data?.map((entry, index) => (
                                <Cell
                                  key={`cell-${index}`}
                                  fill={COLORS[index % COLORS.length]}
                                />
                              ))}
                            </Pie>
                            <Tooltip />
                            <Legend />
                          </PieChart>
                        </ResponsiveContainer>
                      </CardContent>
                    </Card>
                  </Grid>
                </Grid>
              </>
            )}
          </TabPanel>

          {/* TAB 1: MARKET ANALYSIS */}
          <TabPanel value={activeTab} index={1}>
            {/* Top Opportunities */}
            <Card elevation={2} sx={{ mb: 4 }}>
              <CardHeader
                title="🎯 Smart Opportunity Scanner"
                subheader="AI-identified trading opportunities based on volume, price, and seasonality"
              />
              <CardContent>
                <Box sx={{ mb: 3, display: "flex", gap: 2 }}>
                  <FormControl sx={{ minWidth: 120 }}>
                    <InputLabel>Category</InputLabel>
                    <Select
                      value={filterCategory}
                      label="Category"
                      onChange={(e) => setFilterCategory(e.target.value)}
                    >
                      <MenuItem value="all">All Categories</MenuItem>
                      <MenuItem value="agriculture">Agriculture</MenuItem>
                      <MenuItem value="energy">Energy</MenuItem>
                      <MenuItem value="metals">Metals</MenuItem>
                      <MenuItem value="forex">Forex</MenuItem>
                      <MenuItem value="livestock">Livestock</MenuItem>
                    </Select>
                  </FormControl>
                  <TextField
                    placeholder="Search commodities..."
                    value={searchText}
                    onChange={(e) => setSearchText(e.target.value)}
                    size="small"
                    sx={{ flex: 1 }}
                  />
                </Box>

                <TableContainer>
                  <Table>
                    <TableHead sx={{ backgroundColor: "#f5f5f5" }}>
                      <TableRow>
                        <TableCell sx={{ fontWeight: 600 }}>Commodity</TableCell>
                        <TableCell align="right" sx={{ fontWeight: 600 }}>
                          Current Price
                        </TableCell>
                        <TableCell align="right" sx={{ fontWeight: 600 }}>
                          1D Change
                        </TableCell>
                        <TableCell align="right" sx={{ fontWeight: 600 }}>
                          Volume
                        </TableCell>
                        <TableCell align="right" sx={{ fontWeight: 600 }}>
                          52W Range
                        </TableCell>
                        <TableCell align="center" sx={{ fontWeight: 600 }}>
                          Opportunity
                        </TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {topOpportunities.map((opp) => (
                        <TableRow key={opp.symbol}>
                          <TableCell sx={{ fontWeight: 500 }}>
                            {opp.name}
                            <Typography variant="caption" display="block" color="text.secondary">
                              {opp.symbol}
                            </Typography>
                          </TableCell>
                          <TableCell align="right">
                            ${opp.price.toFixed(2)}
                          </TableCell>
                          <TableCell
                            align="right"
                            sx={{
                              color: getChangeColor(opp.changePercent),
                              fontWeight: 600,
                            }}
                          >
                            {opp.changePercent}%
                          </TableCell>
                          <TableCell align="right">
                            {(opp.volume / 1000000).toFixed(2)}M
                          </TableCell>
                          <TableCell align="right">
                            <Typography variant="caption">
                              ${opp.low52w.toFixed(2)} - ${opp.high52w.toFixed(2)}
                            </Typography>
                            <Typography variant="caption" display="block" color="text.secondary">
                              {opp.distanceFromHigh}% from high
                            </Typography>
                          </TableCell>
                          <TableCell align="center">
                            <Chip
                              label={opp.opportunity}
                              color={opp.opportunity === "STRONG" ? "success" : "default"}
                              size="small"
                              variant={opp.opportunity === "STRONG" ? "filled" : "outlined"}
                            />
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              </CardContent>
            </Card>

            {/* Correlation Heatmap */}
            <Card elevation={2} sx={{ mb: 4 }}>
              <CardHeader
                title="🔗 Correlation Analysis"
                subheader="Price correlation matrix for portfolio diversification"
              />
              <CardContent>
                <TableContainer>
                  <Table size="small">
                    <TableHead sx={{ backgroundColor: "#f5f5f5" }}>
                      <TableRow>
                        <TableCell sx={{ fontWeight: 600 }}>Pair</TableCell>
                        <TableCell align="right" sx={{ fontWeight: 600 }}>
                          Correlation
                        </TableCell>
                        <TableCell align="center" sx={{ fontWeight: 600 }}>
                          Strength
                        </TableCell>
                        <TableCell sx={{ fontWeight: 600 }}>Implication</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {correlationPairs.slice(0, 12).map((pair, idx) => (
                        <TableRow key={idx}>
                          <TableCell sx={{ fontWeight: 500 }}>
                            {pair.name1} ↔ {pair.name2}
                          </TableCell>
                          <TableCell align="right">
                            <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                              <LinearProgress
                                variant="determinate"
                                value={pair.coefficient * 100}
                                sx={{ flex: 1, width: 100 }}
                              />
                              <Typography variant="body2" sx={{ fontWeight: 600, minWidth: 50 }}>
                                {pair.coefficient.toFixed(2)}
                              </Typography>
                            </Box>
                          </TableCell>
                          <TableCell align="center">
                            <Chip label={pair.strength} size="small" />
                          </TableCell>
                          <TableCell variant="body2">
                            {pair.coefficient > 0.7
                              ? "Move together - low diversification"
                              : pair.coefficient > 0.5
                              ? "Moderate correlation - some diversification"
                              : "Low correlation - good hedge"}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              </CardContent>
            </Card>
          </TabPanel>

          {/* TAB 2: RISK & HEDGING */}
          <TabPanel value={activeTab} index={2}>
            <Grid container spacing={3}>
              {/* Commodity Selector */}
              <Grid item xs={12}>
                <Card elevation={2}>
                  <CardHeader title="Select Commodity for Analysis" />
                  <CardContent>
                    <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
                      {cotSymbols.map((symbol) => (
                        <Chip
                          key={symbol}
                          label={symbol}
                          onClick={() => setSelectedCommodity(symbol)}
                          color={selectedCommodity === symbol ? "primary" : "default"}
                          variant={
                            selectedCommodity === symbol ? "filled" : "outlined"
                          }
                        />
                      ))}
                    </Box>
                  </CardContent>
                </Card>
              </Grid>

              {/* Risk Metrics Cards */}
              <Grid item xs={12} sm={6} md={3}>
                <Paper elevation={2} sx={{ p: 2 }}>
                  <Typography color="textSecondary" variant="subtitle2" sx={{ mb: 1 }}>
                    Volatility
                  </Typography>
                  <Typography variant="h5" sx={{ fontWeight: 700, mb: 1 }}>
                    {riskMetrics.volatility}%
                  </Typography>
                  <Chip
                    label={riskMetrics.riskLevel}
                    color={
                      riskMetrics.riskLevel === "HIGH"
                        ? "error"
                        : riskMetrics.riskLevel === "MEDIUM"
                        ? "warning"
                        : "success"
                    }
                    size="small"
                  />
                </Paper>
              </Grid>

              <Grid item xs={12} sm={6} md={3}>
                <Paper elevation={2} sx={{ p: 2 }}>
                  <Typography color="textSecondary" variant="subtitle2" sx={{ mb: 1 }}>
                    Diversification Score
                  </Typography>
                  <Typography variant="h5" sx={{ fontWeight: 700, mb: 1 }}>
                    {riskMetrics.diversificationScore}
                  </Typography>
                  <Typography variant="caption" color="info.main">
                    ↑ Higher is better
                  </Typography>
                </Paper>
              </Grid>

              <Grid item xs={12} sm={6} md={3}>
                <Paper elevation={2} sx={{ p: 2 }}>
                  <Typography color="textSecondary" variant="subtitle2" sx={{ mb: 1 }}>
                    Hedge Opportunities
                  </Typography>
                  <Typography variant="h5" sx={{ fontWeight: 700, mb: 1 }}>
                    {riskMetrics.hedgeOpportunities}
                  </Typography>
                  <Typography variant="caption" color="success.main">
                    Available pairs
                  </Typography>
                </Paper>
              </Grid>

              <Grid item xs={12} sm={6} md={3}>
                <Paper elevation={2} sx={{ p: 2 }}>
                  <Typography color="textSecondary" variant="subtitle2" sx={{ mb: 1 }}>
                    Distance from 52W High
                  </Typography>
                  <Typography variant="h5" sx={{ fontWeight: 700, mb: 1 }}>
                    {riskMetrics.distanceFromHigh}%
                  </Typography>
                  <Typography variant="caption">
                    {riskMetrics.distanceFromHigh > 20
                      ? "💡 Potential value"
                      : "⚠️ Near highs"}
                  </Typography>
                </Paper>
              </Grid>

              {/* COT Analysis */}
              {cotQuery.data && (
                <>
                  <Grid item xs={12}>
                    <Card elevation={2}>
                      <CardHeader title="👥 Commitment of Traders Analysis" />
                      <CardContent>
                        <Grid container spacing={2} sx={{ mb: 3 }}>
                          <Grid item xs={12} sm={6} md={3}>
                            <Box
                              sx={{
                                p: 2,
                                border: "1px solid #ddd",
                                borderRadius: 1,
                                textAlign: "center",
                              }}
                            >
                              <Typography variant="caption" color="textSecondary">
                                Commercial Sentiment
                              </Typography>
                              <Chip
                                label={cotQuery.data.analysis?.commercialSentiment}
                                color={
                                  cotQuery.data.analysis?.commercialSentiment === "bullish"
                                    ? "success"
                                    : "error"
                                }
                                sx={{ mt: 1 }}
                              />
                              <Typography variant="caption" display="block" sx={{ mt: 1 }}>
                                Professional hedgers
                              </Typography>
                            </Box>
                          </Grid>

                          <Grid item xs={12} sm={6} md={3}>
                            <Box
                              sx={{
                                p: 2,
                                border: "1px solid #ddd",
                                borderRadius: 1,
                                textAlign: "center",
                              }}
                            >
                              <Typography variant="caption" color="textSecondary">
                                Speculator Sentiment
                              </Typography>
                              <Chip
                                label={cotQuery.data.analysis?.speculatorSentiment}
                                color={
                                  cotQuery.data.analysis?.speculatorSentiment === "bullish"
                                    ? "success"
                                    : "error"
                                }
                                sx={{ mt: 1 }}
                              />
                              <Typography variant="caption" display="block" sx={{ mt: 1 }}>
                                Traders & funds
                              </Typography>
                            </Box>
                          </Grid>

                          <Grid item xs={12} sm={6} md={3}>
                            <Box
                              sx={{
                                p: 2,
                                border: "1px solid #ddd",
                                borderRadius: 1,
                                textAlign: "center",
                              }}
                            >
                              <Typography variant="caption" color="textSecondary">
                                Divergence Signal
                              </Typography>
                              <Chip
                                label={cotQuery.data.analysis?.divergence}
                                color={
                                  cotQuery.data.analysis?.divergence === "divergent"
                                    ? "error"
                                    : "success"
                                }
                                sx={{ mt: 1 }}
                              />
                              <Typography variant="caption" display="block" sx={{ mt: 1 }}>
                                {cotQuery.data.analysis?.divergence === "aligned"
                                  ? "Agreement = confidence"
                                  : "Disagreement = caution"}
                              </Typography>
                            </Box>
                          </Grid>

                          <Grid item xs={12} sm={6} md={3}>
                            <Box
                              sx={{
                                p: 2,
                                border: "1px solid #ddd",
                                borderRadius: 1,
                                textAlign: "center",
                              }}
                            >
                              <Typography variant="caption" color="textSecondary">
                                Latest Report
                              </Typography>
                              <Typography variant="body2" sx={{ fontWeight: 600, mt: 1 }}>
                                {new Date(cotQuery.data.latestReportDate).toLocaleDateString()}
                              </Typography>
                              <Typography variant="caption" color="text.secondary">
                                CFTC Data
                              </Typography>
                            </Box>
                          </Grid>
                        </Grid>

                        {cotHistoryData.length > 0 && (
                          <Box sx={{ mt: 3 }}>
                            <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                              12-Week Positioning Trend
                            </Typography>
                            <ResponsiveContainer width="100%" height={300}>
                              <LineChart data={cotHistoryData}>
                                <CartesianGrid strokeDasharray="3 3" />
                                <XAxis
                                  dataKey="reportDate"
                                  angle={-45}
                                  textAnchor="end"
                                  height={80}
                                  tick={{ fontSize: 12 }}
                                />
                                <YAxis />
                                <Tooltip />
                                <Legend />
                                <Line
                                  type="monotone"
                                  dataKey="commercial.net"
                                  stroke="#8884d8"
                                  name="Commercial Net"
                                  strokeWidth={2}
                                />
                                <Line
                                  type="monotone"
                                  dataKey="nonCommercial.net"
                                  stroke="#82ca9d"
                                  name="Speculator Net"
                                  strokeWidth={2}
                                />
                              </LineChart>
                            </ResponsiveContainer>
                          </Box>
                        )}
                      </CardContent>
                    </Card>
                  </Grid>
                </>
              )}
            </Grid>
          </TabPanel>

          {/* TAB 3: TRADING SIGNALS */}
          <TabPanel value={activeTab} index={3}>
            <Card elevation={2}>
              <CardHeader
                title="🎯 AI-Generated Trading Signals"
                subheader="Based on seasonality, COT, momentum, and technical indicators"
              />
              <CardContent>
                {tradingSignals.length > 0 ? (
                  <Grid container spacing={2}>
                    {tradingSignals.map((signal, idx) => (
                      <Grid item xs={12} key={idx}>
                        <Paper
                          sx={{
                            p: 2,
                            border: `2px solid ${
                              signal.strength === "strong" ? "#4caf50" : "#ff9800"
                            }`,
                            backgroundColor:
                              signal.strength === "strong"
                                ? "#e8f5e9"
                                : "#fff3e0",
                          }}
                        >
                          <Box
                            sx={{
                              display: "flex",
                              justifyContent: "space-between",
                              alignItems: "flex-start",
                              mb: 1,
                            }}
                          >
                            <Box>
                              <Chip
                                label={signal.action}
                                color={signal.action === "BUY" ? "success" : "error"}
                                size="small"
                                sx={{ mb: 1 }}
                              />
                              <Typography variant="body1" sx={{ fontWeight: 600 }}>
                                {signal.message}
                              </Typography>
                            </Box>
                            <Box sx={{ textAlign: "right" }}>
                              <Typography variant="h5" sx={{ fontWeight: 700 }}>
                                {signal.score}/100
                              </Typography>
                              <Chip
                                label={signal.strength}
                                variant="outlined"
                                size="small"
                              />
                            </Box>
                          </Box>
                          <LinearProgress
                            variant="determinate"
                            value={signal.score}
                            sx={{ mt: 2 }}
                          />
                          <Typography
                            variant="caption"
                            color="text.secondary"
                            sx={{ mt: 1, display: "block" }}
                          >
                            Type: {signal.type} | Strength: {signal.strength}
                          </Typography>
                        </Paper>
                      </Grid>
                    ))}
                  </Grid>
                ) : (
                  <Alert severity="info">
                    No strong trading signals at this time. Monitor for seasonal patterns and
                    COT positioning changes.
                  </Alert>
                )}
              </CardContent>
            </Card>
          </TabPanel>

          {/* TAB 4: DETAILED ANALYSIS */}
          <TabPanel value={activeTab} index={4}>
            <Grid container spacing={3}>
              {/* Seasonality */}
              <Grid item xs={12}>
                <Card elevation={2}>
                  <CardHeader title="📅 Monthly Seasonal Patterns" />
                  <CardContent>
                    {seasonalityData.length > 0 ? (
                      <>
                        <ResponsiveContainer width="100%" height={300}>
                          <LineChart data={seasonalityData}>
                            <CartesianGrid strokeDasharray="3 3" />
                            <XAxis
                              dataKey="monthName"
                              angle={-45}
                              textAnchor="end"
                              height={80}
                            />
                            <YAxis yAxisId="left" />
                            <YAxis yAxisId="right" orientation="right" />
                            <Tooltip />
                            <Legend />
                            <Line
                              yAxisId="left"
                              type="monotone"
                              dataKey="winRate"
                              stroke="#8884d8"
                              name="Win Rate %"
                            />
                            <Line
                              yAxisId="right"
                              type="monotone"
                              dataKey="avgReturn"
                              stroke="#82ca9d"
                              name="Avg Return %"
                            />
                          </LineChart>
                        </ResponsiveContainer>

                        <Table size="small" sx={{ mt: 3 }}>
                          <TableHead sx={{ backgroundColor: "#f5f5f5" }}>
                            <TableRow>
                              <TableCell sx={{ fontWeight: 600 }}>Month</TableCell>
                              <TableCell align="right" sx={{ fontWeight: 600 }}>
                                Avg Return
                              </TableCell>
                              <TableCell align="right" sx={{ fontWeight: 600 }}>
                                Win Rate
                              </TableCell>
                              <TableCell align="right" sx={{ fontWeight: 600 }}>
                                Volatility
                              </TableCell>
                              <TableCell align="right" sx={{ fontWeight: 600 }}>
                                Data Points
                              </TableCell>
                            </TableRow>
                          </TableHead>
                          <TableBody>
                            {seasonalityData.map((item) => (
                              <TableRow key={item.month}>
                                <TableCell sx={{ fontWeight: 500 }}>
                                  {item.monthName}
                                </TableCell>
                                <TableCell
                                  align="right"
                                  sx={{
                                    color: getChangeColor(item.avgReturn),
                                    fontWeight: 600,
                                  }}
                                >
                                  {item.avgReturn}%
                                </TableCell>
                                <TableCell align="right">
                                  <Box
                                    sx={{
                                      display: "flex",
                                      alignItems: "center",
                                      justifyContent: "flex-end",
                                      gap: 1,
                                    }}
                                  >
                                    {item.winRate}%
                                    <LinearProgress
                                      variant="determinate"
                                      value={Math.min(parseFloat(item.winRate), 100)}
                                      sx={{
                                        width: 60,
                                        height: 6,
                                        borderRadius: 3,
                                      }}
                                    />
                                  </Box>
                                </TableCell>
                                <TableCell align="right">{item.volatility}</TableCell>
                                <TableCell align="right">{item.yearsData} years</TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      </>
                    ) : (
                      <Alert severity="info">
                        No seasonality data available for this commodity
                      </Alert>
                    )}
                  </CardContent>
                </Card>
              </Grid>

              {/* All Prices */}
              <Grid item xs={12}>
                <Card elevation={2}>
                  <CardHeader title="💰 Complete Commodity Prices" />
                  <CardContent>
                    <TableContainer sx={{ maxHeight: 600 }}>
                      <Table stickyHeader>
                        <TableHead sx={{ backgroundColor: "#f5f5f5" }}>
                          <TableRow>
                            <TableCell sx={{ fontWeight: 600 }}>Commodity</TableCell>
                            <TableCell align="right" sx={{ fontWeight: 600 }}>
                              Price
                            </TableCell>
                            <TableCell align="right" sx={{ fontWeight: 600 }}>
                              1D Change
                            </TableCell>
                            <TableCell align="right" sx={{ fontWeight: 600 }}>
                              Volume
                            </TableCell>
                            <TableCell align="right" sx={{ fontWeight: 600 }}>
                              52W High/Low
                            </TableCell>
                            <TableCell sx={{ fontWeight: 600 }}>Category</TableCell>
                          </TableRow>
                        </TableHead>
                        <TableBody>
                          {pricesQuery.data?.map((commodity) => (
                            <TableRow key={commodity.symbol}>
                              <TableCell sx={{ fontWeight: 500 }}>
                                {commodity.name}
                                <Typography variant="caption" display="block" color="text.secondary">
                                  {commodity.symbol}
                                </Typography>
                              </TableCell>
                              <TableCell align="right">
                                ${commodity.price.toFixed(2)}
                              </TableCell>
                              <TableCell
                                align="right"
                                sx={{
                                  color: getChangeColor(commodity.changePercent),
                                  fontWeight: 600,
                                }}
                              >
                                {commodity.change > 0 ? "+" : ""}
                                {commodity.changePercent}%
                              </TableCell>
                              <TableCell align="right">
                                {(commodity.volume / 1000000).toFixed(2)}M
                              </TableCell>
                              <TableCell align="right">
                                <Typography variant="caption">
                                  ${commodity.high52w.toFixed(2)}
                                </Typography>
                                <Typography variant="caption" display="block" color="text.secondary">
                                  / ${commodity.low52w.toFixed(2)}
                                </Typography>
                              </TableCell>
                              <TableCell>
                                <Chip
                                  label={commodity.category}
                                  size="small"
                                  variant="outlined"
                                />
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </TableContainer>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>
          </TabPanel>
        </>
      )}
    </Container>
  );
}
