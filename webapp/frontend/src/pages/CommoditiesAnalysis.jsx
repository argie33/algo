import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Container,
  Grid,
  Card,
  CardContent,
  Typography,
  Select,
  MenuItem,
  Box,
  Alert,
  CircularProgress,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Chip
} from "@mui/material";
import {
  TrendingUp,
  TrendingDown,
  Info
} from "@mui/icons-material";
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  Legend,
  ComposedChart,
  Area
} from "recharts";
import api from "../services/api";
import {
  formatPercentage,
  formatPercentageChange,
  getChangeColor,
} from "../utils/formatters";

export default function CommoditiesAnalysis() {
  const [selectedCategory, setSelectedCategory] = useState("all");
  const [selectedCommodity, setSelectedCommodity] = useState(null);

  // Fetch categories
  const { data: categories, isLoading: categoriesLoading } = useQuery({
    queryKey: ["commodities-categories"],
    queryFn: async () => {
      const response = await api.get("/api/commodities/categories");
      return response?.data?.data || [];
    },
    staleTime: 5 * 60 * 1000,
  });

  // Fetch prices with category filter
  const { data: prices, isLoading: pricesLoading } = useQuery({
    queryKey: ["commodities-prices", selectedCategory],
    queryFn: async () => {
      const url = selectedCategory === "all"
        ? "/api/commodities/prices"
        : `/api/commodities/prices?category=${selectedCategory}`;
      const response = await api.get(url);
      return response?.data?.data || [];
    },
    enabled: true,
    staleTime: 2 * 60 * 1000,
  });

  // Fetch market summary
  const { data: marketSummary, isLoading: summaryLoading } = useQuery({
    queryKey: ["commodities-market-summary"],
    queryFn: async () => {
      const response = await api.get("/api/commodities/market-summary");
      return response?.data?.data;
    },
    staleTime: 2 * 60 * 1000,
  });

  // Fetch COT data for selected commodity
  const { data: cotData, isLoading: cotLoading } = useQuery({
    queryKey: ["commodities-cot", selectedCommodity],
    queryFn: async () => {
      const response = await api.get(`/api/commodities/cot/${selectedCommodity}`);
      return response?.data?.data;
    },
    enabled: !!selectedCommodity,
    staleTime: 5 * 60 * 1000,
  });

  // Fetch seasonality data for selected commodity
  const { data: seasonalityData, isLoading: seasonalityLoading } = useQuery({
    queryKey: ["commodities-seasonality", selectedCommodity],
    queryFn: async () => {
      const response = await api.get(`/api/commodities/seasonality/${selectedCommodity}`);
      return response?.data?.data;
    },
    enabled: !!selectedCommodity,
    staleTime: 24 * 60 * 60 * 1000, // 24 hours
  });

  // Fetch correlations
  const { data: correlationsData } = useQuery({
    queryKey: ["commodities-correlations"],
    queryFn: async () => {
      const response = await api.get("/api/commodities/correlations?min_correlation=0.5");
      return response?.data?.data;
    },
    staleTime: 24 * 60 * 60 * 1000,
  });

  if (categoriesLoading || pricesLoading || summaryLoading) {
    return (
      <Container maxWidth="xl" sx={{ py: 4, textAlign: "center" }}>
        <CircularProgress />
      </Container>
    );
  }

  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      <Typography variant="h4" gutterBottom sx={{ mb: 4, fontWeight: 600 }}>
        Commodities Analysis
      </Typography>

      {/* Market Summary Cards */}
      <Grid container spacing={3} sx={{ mb: 4 }}>
        <Grid item xs={12} sm={6} md={3}>
          <SummaryCard
            title="Active Contracts"
            value={marketSummary?.overview?.activeContracts || 0}
            icon="📊"
          />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <SummaryCard
            title="Total Volume"
            value={marketSummary?.overview?.totalVolume?.toLocaleString() || 0}
            icon="📈"
          />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <SummaryCard
            title="Top Gainer"
            value={marketSummary?.topGainers?.[0]?.name}
            subtitle={`+${marketSummary?.topGainers?.[0]?.change}%`}
            icon="📈"
            color="success"
          />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <SummaryCard
            title="Top Loser"
            value={marketSummary?.topLosers?.[0]?.name}
            subtitle={`${marketSummary?.topLosers?.[0]?.change}%`}
            icon="📉"
            color="error"
          />
        </Grid>
      </Grid>

      {/* Category Performance */}
      <Card sx={{ mb: 4 }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Category Performance
          </Typography>
          <Grid container spacing={2}>
            {marketSummary?.sectors?.map((sector) => (
              <Grid item xs={12} sm={6} md={4} key={sector.category}>
                <Card variant="outlined">
                  <CardContent sx={{ py: 2 }}>
                    <Typography variant="subtitle2" color="text.secondary">
                      {sector.name}
                    </Typography>
                    <Box sx={{ display: "flex", alignItems: "center", gap: 1, mt: 1 }}>
                      <Typography
                        variant="h6"
                        color={sector.trend === "up" ? "success.main" : "error.main"}
                      >
                        {sector.change1d}%
                      </Typography>
                      {sector.trend === "up" ? (
                        <TrendingUp sx={{ color: "success.main" }} />
                      ) : (
                        <TrendingDown sx={{ color: "error.main" }} />
                      )}
                    </Box>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        </CardContent>
      </Card>

      {/* Commodity Selector and Prices */}
      <Card sx={{ mb: 4 }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Commodity Prices
          </Typography>

          <Box sx={{ mb: 3 }}>
            <Typography variant="subtitle2" sx={{ mb: 1 }}>
              Filter by Category
            </Typography>
            <Select
              value={selectedCategory}
              onChange={(e) => setSelectedCategory(e.target.value)}
              fullWidth
            >
              <MenuItem value="all">All Categories</MenuItem>
              {categories?.map((cat) => (
                <MenuItem key={cat.category} value={cat.category}>
                  {cat.name} ({cat.commodityCount})
                </MenuItem>
              ))}
            </Select>
          </Box>

          {/* Prices Table */}
          <TableContainer component={Paper} variant="outlined">
            <Table size="small">
              <TableHead>
                <TableRow sx={{ backgroundColor: "#f5f5f5" }}>
                  <TableCell>Symbol</TableCell>
                  <TableCell>Name</TableCell>
                  <TableCell>Category</TableCell>
                  <TableCell align="right">Price</TableCell>
                  <TableCell align="right">Change (24h)</TableCell>
                  <TableCell align="right">52W High</TableCell>
                  <TableCell align="right">52W Low</TableCell>
                  <TableCell align="center">Action</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {prices?.map((price) => (
                  <TableRow key={price.symbol} hover>
                    <TableCell sx={{ fontWeight: 600 }}>{price.symbol}</TableCell>
                    <TableCell>{price.name}</TableCell>
                    <TableCell>
                      <Chip
                        label={price.category}
                        size="small"
                        variant="outlined"
                      />
                    </TableCell>
                    <TableCell align="right">
                      {price.price ? `$${price.price.toFixed(2)}` : "—"}
                    </TableCell>
                    <TableCell
                      align="right"
                      sx={{ color: getChangeColor(price.changePercent) }}
                    >
                      {price.changePercent !== null && price.changePercent !== undefined
                        ? `${price.changePercent >= 0 ? "+" : ""}${price.changePercent}%`
                        : "—"}
                    </TableCell>
                    <TableCell align="right">
                      {price.high52w ? `$${price.high52w.toFixed(2)}` : "—"}
                    </TableCell>
                    <TableCell align="right">
                      {price.low52w ? `$${price.low52w.toFixed(2)}` : "—"}
                    </TableCell>
                    <TableCell align="center">
                      <Select
                        size="small"
                        value={selectedCommodity === price.symbol ? price.symbol : ""}
                        onChange={(e) => setSelectedCommodity(e.target.value || null)}
                        sx={{ minWidth: 60 }}
                      >
                        <MenuItem value="">View</MenuItem>
                        <MenuItem value={price.symbol}>Analysis</MenuItem>
                      </Select>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </CardContent>
      </Card>

      {/* COT Analysis Section */}
      {selectedCommodity && cotLoading && (
        <Box sx={{ textAlign: "center", py: 4 }}>
          <CircularProgress />
        </Box>
      )}

      {selectedCommodity && cotData && !cotLoading && (
        <COTAnalysisSection cotData={cotData} />
      )}

      {/* Seasonality Section */}
      {selectedCommodity && seasonalityLoading && (
        <Box sx={{ textAlign: "center", py: 4 }}>
          <CircularProgress />
        </Box>
      )}

      {selectedCommodity && seasonalityData && !seasonalityLoading && (
        <SeasonalitySection seasonalityData={seasonalityData} />
      )}

      {/* Correlations Section */}
      {correlationsData && correlationsData.correlations.length > 0 && (
        <CorrelationsSection correlations={correlationsData.correlations} />
      )}
    </Container>
  );
}

// Summary Card Component
function SummaryCard({ title, value, subtitle, icon = "📊", color = "primary" }) {
  return (
    <Card>
      <CardContent>
        <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
          <Box>
            <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 0.5 }}>
              {title}
            </Typography>
            <Typography variant="h5" sx={{ fontWeight: 600 }}>
              {value}
            </Typography>
            {subtitle && (
              <Typography variant="caption" color="text.secondary">
                {subtitle}
              </Typography>
            )}
          </Box>
          <Typography variant="h4">{icon}</Typography>
        </Box>
      </CardContent>
    </Card>
  );
}

// COT Analysis Component
function COTAnalysisSection({ cotData }) {
  const { cotHistory, analysis, commodityName } = cotData;

  const chartData = cotHistory.map(record => ({
    date: new Date(record.reportDate).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric"
    }),
    commercialNet: record.commercial.net,
    speculatorNet: record.nonCommercial.net,
    openInterest: record.openInterest / 1000, // Scale for chart readability
  }));

  return (
    <Card sx={{ mb: 4 }}>
      <CardContent>
        <Typography variant="h6" gutterBottom>
          Commitment of Traders (COT) - {commodityName}
        </Typography>

        {/* Educational Info */}
        <Alert severity="info" sx={{ mb: 3 }}>
          <Typography variant="body2">
            <strong>COT Analysis Explained:</strong> Commercial traders (producers/consumers) hedge
            their exposure, while non-commercial traders are speculators. Extreme commercial positioning
            often precedes market reversals.
          </Typography>
        </Alert>

        {/* Sentiment Cards */}
        <Grid container spacing={2} sx={{ mb: 3 }}>
          <Grid item xs={12} md={6}>
            <SentimentCard
              title="Commercial Hedgers (Smart Money)"
              sentiment={analysis.commercialSentiment}
              netPosition={analysis.latestCommercialNet}
              description="Producers/consumers hedging operational exposure"
            />
          </Grid>

          <Grid item xs={12} md={6}>
            <SentimentCard
              title="Non-Commercial Speculators"
              sentiment={analysis.speculatorSentiment}
              netPosition={analysis.latestSpeculatorNet}
              description="Hedge funds and traders taking directional positions"
            />
          </Grid>
        </Grid>

        {/* Divergence Alert */}
        {analysis.divergence === "divergent" && (
          <Alert severity="warning" sx={{ mb: 3 }}>
            <Box sx={{ display: "flex", gap: 1, alignItems: "flex-start" }}>
              <Info sx={{ mt: 0.5, flexShrink: 0 }} />
              <Box>
                <strong>Divergence Detected:</strong> Commercial hedgers and speculators have opposing
                views on direction. Historically, commercials are more accurate - consider their position
                as a contrarian indicator for speculators.
              </Box>
            </Box>
          </Alert>
        )}

        {/* COT Chart */}
        <Typography variant="subtitle2" sx={{ mb: 2 }}>
          Positioning History (52 Weeks)
        </Typography>
        <Box sx={{ height: 400 }}>
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 12 }}
                interval={Math.floor(chartData.length / 6)}
              />
              <YAxis yAxisId="left" tick={{ fontSize: 12 }} />
              <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 12 }} />
              <Tooltip
                contentStyle={{
                  backgroundColor: "rgba(255, 255, 255, 0.95)",
                  border: "1px solid #ccc",
                  borderRadius: "4px"
                }}
              />
              <Legend />
              <Line
                yAxisId="left"
                type="monotone"
                dataKey="commercialNet"
                stroke="#2E7D32"
                strokeWidth={2}
                name="Commercial Net"
                dot={false}
              />
              <Line
                yAxisId="left"
                type="monotone"
                dataKey="speculatorNet"
                stroke="#D32F2F"
                strokeWidth={2}
                name="Speculator Net"
                dot={false}
              />
              <Area
                yAxisId="right"
                type="monotone"
                dataKey="openInterest"
                fill="#1976D2"
                stroke="#1976D2"
                fillOpacity={0.2}
                name="Open Interest (K)"
              />
            </ComposedChart>
          </ResponsiveContainer>
        </Box>

        <Typography variant="caption" color="text.secondary" sx={{ mt: 2, display: "block" }}>
          Chart shows net positioning over the last 52 weeks. Divergence between commercial and
          speculator positioning can signal potential market moves.
        </Typography>
      </CardContent>
    </Card>
  );
}

// Sentiment Card Component
function SentimentCard({ title, sentiment, netPosition, description }) {
  const sentimentColor = {
    bullish: "success",
    bearish: "error",
    neutral: "warning"
  }[sentiment] || "default";

  const sentimentIcon = {
    bullish: "📈",
    bearish: "📉",
    neutral: "➡️"
  }[sentiment] || "";

  return (
    <Card variant="outlined">
      <CardContent>
        <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 1 }}>
          {title}
        </Typography>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1 }}>
          <Typography variant="h3" sx={{ fontSize: 32 }}>
            {sentimentIcon}
          </Typography>
          <Box>
            <Typography
              variant="h5"
              sx={{
                color: sentimentColor === "success" ? "success.main" : sentimentColor === "error" ? "error.main" : "warning.main",
                fontWeight: 600,
                textTransform: "uppercase",
                letterSpacing: 1
              }}
            >
              {sentiment}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Net: {netPosition?.toLocaleString() || "—"}
            </Typography>
          </Box>
        </Box>
        <Typography variant="caption" color="text.secondary">
          {description}
        </Typography>
      </CardContent>
    </Card>
  );
}

// Seasonality Component
function SeasonalitySection({ seasonalityData }) {
  const { seasonality, commodityName } = seasonalityData;

  // Data for bar chart
  const chartData = seasonality.map(m => ({
    month: m.monthName.substring(0, 3),
    return: parseFloat(m.avgReturn) * 100, // Convert to percentage
    winRate: parseFloat(m.winRate),
    volatility: parseFloat(m.volatility) * 100 // Convert to percentage
  }));

  return (
    <Card sx={{ mb: 4 }}>
      <CardContent>
        <Typography variant="h6" gutterBottom>
          Seasonal Patterns - {commodityName}
        </Typography>

        <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
          Historical average returns and win rates by month across all years of available data.
        </Typography>

        <Grid container spacing={3}>
          <Grid item xs={12} md={6}>
            <Typography variant="subtitle2" sx={{ mb: 2 }}>
              Average Monthly Returns
            </Typography>
            <Box sx={{ height: 300 }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="month" />
                  <YAxis />
                  <Tooltip formatter={(value) => `${value.toFixed(2)}%`} />
                  <Bar dataKey="return" fill="#1976D2" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </Box>
          </Grid>

          <Grid item xs={12} md={6}>
            <Typography variant="subtitle2" sx={{ mb: 2 }}>
              Win Rate by Month
            </Typography>
            <Box sx={{ height: 300 }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="month" />
                  <YAxis domain={[0, 100]} label={{ value: "Win %", angle: -90, position: "insideLeft" }} />
                  <Tooltip formatter={(value) => `${value.toFixed(1)}%`} />
                  <Bar dataKey="winRate" fill="#2E7D32" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </Box>
          </Grid>
        </Grid>

        <Typography variant="body2" color="text.secondary" sx={{ mt: 3 }}>
          Use seasonal patterns to identify favorable trading months, but always combine with other
          technical and fundamental analysis for comprehensive trading decisions.
        </Typography>
      </CardContent>
    </Card>
  );
}

// Correlations Component
function CorrelationsSection({ correlations }) {
  return (
    <Card>
      <CardContent>
        <Typography variant="h6" gutterBottom>
          Commodity Correlations (90-Day)
        </Typography>

        <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
          Pairs with correlation ≥ 0.50. Positive correlation means prices move together; negative
          means they move inversely.
        </Typography>

        <TableContainer component={Paper} variant="outlined">
          <Table size="small">
            <TableHead>
              <TableRow sx={{ backgroundColor: "#f5f5f5" }}>
                <TableCell>Commodity Pair</TableCell>
                <TableCell align="right">Correlation</TableCell>
                <TableCell>Strength</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {correlations?.slice(0, 10).map((corr, idx) => (
                <TableRow key={idx}>
                  <TableCell>
                    {corr.name1} ↔ {corr.name2}
                  </TableCell>
                  <TableCell align="right">
                    <Typography
                      sx={{
                        color: corr.coefficient > 0 ? "success.main" : "error.main",
                        fontWeight: 600
                      }}
                    >
                      {corr.coefficient}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <Chip
                      label={corr.strength}
                      size="small"
                      variant={corr.strength === "strong" ? "filled" : "outlined"}
                      color={corr.strength === "strong" ? "primary" : "default"}
                    />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      </CardContent>
    </Card>
  );
}
