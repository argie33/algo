import React, { useState } from "react";
import {
  Container,
  Typography,
  Box,
  Card,
  CardContent,
  Grid,
  TextField,
  Chip,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Alert,
  CircularProgress,
  Autocomplete,
  Divider,
} from "@mui/material";
import {
  TrendingUp,
  TrendingDown,
  TrendingFlat,
  SentimentSatisfiedAlt,
  ShowChart,
  Reddit,
  Newspaper,
  TrendingUpRounded,
} from "@mui/icons-material";
import { useQuery } from "@tanstack/react-query";
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip as RechartsTooltip, Legend, BarChart, Bar, XAxis, YAxis, CartesianGrid } from "recharts";

const API_BASE = window.CONFIG?.API_URL || "http://localhost:5001";

// Composite sentiment scoring algorithm
const calculateCompositeSentiment = (newsScore, analystScore, socialScore) => {
  // Weights: News 40%, Analyst 35%, Social 25%
  const weights = { news: 0.4, analyst: 0.35, social: 0.25 };

  let totalWeight = 0;
  let weightedSum = 0;

  if (newsScore !== null && newsScore !== undefined) {
    weightedSum += newsScore * weights.news;
    totalWeight += weights.news;
  }
  if (analystScore !== null && analystScore !== undefined) {
    weightedSum += analystScore * weights.analyst;
    totalWeight += weights.analyst;
  }
  if (socialScore !== null && socialScore !== undefined) {
    weightedSum += socialScore * weights.social;
    totalWeight += weights.social;
  }

  // Return normalized score or null if no data
  if (totalWeight === 0) return null;
  return weightedSum / totalWeight;
};

// Convert composite score to sentiment label
const getSentimentLabel = (score) => {
  if (score === null || score === undefined) return { label: "Unknown", color: "default", icon: <TrendingFlat /> };
  if (score > 0.3) return { label: "Bullish", color: "success", icon: <TrendingUp /> };
  if (score < -0.3) return { label: "Bearish", color: "error", icon: <TrendingDown /> };
  return { label: "Neutral", color: "warning", icon: <TrendingFlat /> };
};

function Sentiment() {
  const [selectedSymbol, setSelectedSymbol] = useState(null);

  // Fetch symbol list from sentiment data for autocomplete
  const { data: symbols } = useQuery({
    queryKey: ["symbols"],
    queryFn: async () => {
      const response = await fetch(`${API_BASE}/api/sentiment/stocks`);
      if (!response.ok) throw new Error("Failed to fetch symbols");
      const data = await response.json();
      // Extract unique symbols from sentiment data
      const stockData = data.data || [];
      const uniqueSymbols = [...new Set(stockData.map(d => d.symbol))].sort();
      return uniqueSymbols.map(symbol => ({ symbol, name: symbol }));
    },
    staleTime: 3600000, // 1 hour
  });

  // Fetch sentiment data for selected symbol
  const { data: sentimentData, isLoading, error } = useQuery({
    queryKey: ["symbolSentiment", selectedSymbol],
    queryFn: async () => {
      if (!selectedSymbol) return null;
      const response = await fetch(`${API_BASE}/api/sentiment/stocks?symbol=${selectedSymbol}`);
      if (!response.ok) throw new Error("Failed to fetch sentiment");
      return response.json();
    },
    enabled: !!selectedSymbol,
    refetchInterval: 300000,
  });

  // Parse sentiment data
  const stockData = sentimentData?.data || [];

  // Calculate composite scores for each data source
  const newsData = stockData.filter(d => d.source === "news" || !d.source);
  const socialData = stockData.filter(d => d.source === "reddit" || d.source === "social");
  const analystData = stockData.filter(d => d.source === "analyst");

  // Latest scores from each source
  const latestNews = newsData[0];
  const latestSocial = socialData[0];
  const latestAnalyst = analystData[0];

  // Calculate composite sentiment
  const compositeScore = calculateCompositeSentiment(
    latestNews?.sentiment_score,
    latestAnalyst?.sentiment_score,
    latestSocial?.sentiment_score
  );

  const compositeSentiment = getSentimentLabel(compositeScore);

  // Component breakdown data for pie chart
  const componentData = [
    { name: "News", value: latestNews?.sentiment_score || 0, weight: 40 },
    { name: "Analyst", value: latestAnalyst?.sentiment_score || 0, weight: 35 },
    { name: "Social", value: latestSocial?.sentiment_score || 0, weight: 25 },
  ].filter(d => d.value !== 0);

  const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042'];

  return (
    <Container maxWidth="xl" sx={{ py: 3 }}>
      <Box sx={{ mb: 3 }}>
        <Box display="flex" alignItems="center" gap={2}>
          <SentimentSatisfiedAlt sx={{ fontSize: 40, color: "primary.main" }} />
          <Typography variant="h4" component="h1">
            Symbol Sentiment Analysis
          </Typography>
        </Box>
        <Typography variant="subtitle1" color="textSecondary" sx={{ mt: 1 }}>
          Composite sentiment scores from news, analyst ratings, and social media
        </Typography>
      </Box>

      {/* Symbol Selector */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Autocomplete
            options={symbols || []}
            getOptionLabel={(option) => option.symbol || ""}
            value={selectedSymbol ? { symbol: selectedSymbol } : null}
            onChange={(_, newValue) => setSelectedSymbol(newValue?.symbol || null)}
            renderInput={(params) => (
              <TextField
                {...params}
                label="Select Symbol"
                placeholder="Search for a stock symbol (e.g., AAPL, GOOGL)"
              />
            )}
            renderOption={(props, option) => (
              <li {...props}>
                <Box>
                  <Typography variant="body1" fontWeight="600">{option.symbol}</Typography>
                  <Typography variant="caption" color="textSecondary">{option.name}</Typography>
                </Box>
              </li>
            )}
          />
        </CardContent>
      </Card>

      {!selectedSymbol ? (
        <Alert severity="info">Select a symbol to view sentiment analysis</Alert>
      ) : isLoading ? (
        <Box display="flex" justifyContent="center" py={4}>
          <CircularProgress />
        </Box>
      ) : error ? (
        <Alert severity="error">Failed to load sentiment data: {error.message}</Alert>
      ) : stockData.length === 0 ? (
        <Alert severity="warning">No sentiment data available for {selectedSymbol}</Alert>
      ) : (
        <>
          {/* Composite Sentiment Score */}
          <Grid container spacing={3} sx={{ mb: 3 }}>
            <Grid item xs={12} md={4}>
              <Card>
                <CardContent>
                  <Typography variant="h6" gutterBottom>Composite Sentiment</Typography>
                  <Box display="flex" alignItems="center" justifyContent="space-between" mb={2}>
                    <Typography variant="h3" fontWeight="bold">
                      {compositeScore !== null ? compositeScore.toFixed(2) : "N/A"}
                    </Typography>
                    <Chip
                      label={compositeSentiment.label}
                      color={compositeSentiment.color}
                      icon={compositeSentiment.icon}
                      size="large"
                    />
                  </Box>
                  <Divider sx={{ my: 2 }} />
                  <Typography variant="caption" color="textSecondary">
                    Weighted average of news (40%), analyst ratings (35%), and social sentiment (25%)
                  </Typography>
                </CardContent>
              </Card>
            </Grid>

            {/* Component Breakdown */}
            <Grid item xs={12} md={8}>
              <Card>
                <CardContent>
                  <Typography variant="h6" gutterBottom>Sentiment Component Breakdown</Typography>
                  <Grid container spacing={2}>
                    <Grid item xs={12} md={6}>
                      <ResponsiveContainer width="100%" height={200}>
                        <PieChart>
                          <Pie
                            data={componentData}
                            dataKey="weight"
                            nameKey="name"
                            cx="50%"
                            cy="50%"
                            outerRadius={70}
                            label={({ name, weight }) => `${name} (${weight}%)`}
                          >
                            {componentData.map((entry, index) => (
                              <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                            ))}
                          </Pie>
                          <RechartsTooltip />
                        </PieChart>
                      </ResponsiveContainer>
                    </Grid>
                    <Grid item xs={12} md={6}>
                      <Box>
                        <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
                          <Box display="flex" alignItems="center" gap={1}>
                            <Newspaper fontSize="small" />
                            <Typography variant="body2">News Sentiment</Typography>
                          </Box>
                          <Chip
                            label={latestNews?.sentiment_score?.toFixed(2) || "N/A"}
                            size="small"
                            color={latestNews?.sentiment_score > 0.2 ? "success" : latestNews?.sentiment_score < -0.2 ? "error" : "warning"}
                          />
                        </Box>
                        <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
                          <Box display="flex" alignItems="center" gap={1}>
                            <TrendingUpRounded fontSize="small" />
                            <Typography variant="body2">Analyst Ratings</Typography>
                          </Box>
                          <Chip
                            label={latestAnalyst?.sentiment_score?.toFixed(2) || "N/A"}
                            size="small"
                            color={latestAnalyst?.sentiment_score > 0.2 ? "success" : latestAnalyst?.sentiment_score < -0.2 ? "error" : "warning"}
                          />
                        </Box>
                        <Box display="flex" justifyContent="space-between" alignItems="center">
                          <Box display="flex" alignItems="center" gap={1}>
                            <Reddit fontSize="small" />
                            <Typography variant="body2">Social Media</Typography>
                          </Box>
                          <Chip
                            label={latestSocial?.sentiment_score?.toFixed(2) || "N/A"}
                            size="small"
                            color={latestSocial?.sentiment_score > 0.2 ? "success" : latestSocial?.sentiment_score < -0.2 ? "error" : "warning"}
                          />
                        </Box>
                      </Box>
                    </Grid>
                  </Grid>
                </CardContent>
              </Card>
            </Grid>
          </Grid>

          {/* Detailed Sentiment Data by Source */}
          <Grid container spacing={3}>
            {/* News Sentiment */}
            {newsData.length > 0 && (
              <Grid item xs={12} md={4}>
                <Card>
                  <CardContent>
                    <Box display="flex" alignItems="center" gap={1} mb={2}>
                      <Newspaper />
                      <Typography variant="h6">News Sentiment</Typography>
                    </Box>
                    <Box display="flex" justifyContent="space-between" mb={1}>
                      <Typography variant="body2">Score:</Typography>
                      <Typography variant="body2" fontWeight="600">
                        {latestNews.sentiment_score?.toFixed(2) || "N/A"}
                      </Typography>
                    </Box>
                    <Box display="flex" justifyContent="space-between" mb={1}>
                      <Typography variant="body2">Positive:</Typography>
                      <Chip label={latestNews.positive_mentions || 0} size="small" color="success" variant="outlined" />
                    </Box>
                    <Box display="flex" justifyContent="space-between" mb={1}>
                      <Typography variant="body2">Neutral:</Typography>
                      <Chip label={latestNews.neutral_mentions || 0} size="small" color="default" variant="outlined" />
                    </Box>
                    <Box display="flex" justifyContent="space-between" mb={1}>
                      <Typography variant="body2">Negative:</Typography>
                      <Chip label={latestNews.negative_mentions || 0} size="small" color="error" variant="outlined" />
                    </Box>
                    <Box display="flex" justifyContent="space-between">
                      <Typography variant="body2">Total Articles:</Typography>
                      <Typography variant="body2" fontWeight="600">{latestNews.total_mentions || 0}</Typography>
                    </Box>
                  </CardContent>
                </Card>
              </Grid>
            )}

            {/* Social Sentiment */}
            {socialData.length > 0 && (
              <Grid item xs={12} md={4}>
                <Card>
                  <CardContent>
                    <Box display="flex" alignItems="center" gap={1} mb={2}>
                      <Reddit />
                      <Typography variant="h6">Social Media</Typography>
                    </Box>
                    <Box display="flex" justifyContent="space-between" mb={1}>
                      <Typography variant="body2">Score:</Typography>
                      <Typography variant="body2" fontWeight="600">
                        {latestSocial.sentiment_score?.toFixed(2) || "N/A"}
                      </Typography>
                    </Box>
                    <Box display="flex" justifyContent="space-between" mb={1}>
                      <Typography variant="body2">Positive:</Typography>
                      <Chip label={latestSocial.positive_mentions || 0} size="small" color="success" variant="outlined" />
                    </Box>
                    <Box display="flex" justifyContent="space-between" mb={1}>
                      <Typography variant="body2">Neutral:</Typography>
                      <Chip label={latestSocial.neutral_mentions || 0} size="small" color="default" variant="outlined" />
                    </Box>
                    <Box display="flex" justifyContent="space-between" mb={1}>
                      <Typography variant="body2">Negative:</Typography>
                      <Chip label={latestSocial.negative_mentions || 0} size="small" color="error" variant="outlined" />
                    </Box>
                    <Box display="flex" justifyContent="space-between">
                      <Typography variant="body2">Total Mentions:</Typography>
                      <Typography variant="body2" fontWeight="600">{latestSocial.total_mentions || 0}</Typography>
                    </Box>
                  </CardContent>
                </Card>
              </Grid>
            )}

            {/* Analyst Sentiment */}
            {analystData.length > 0 && (
              <Grid item xs={12} md={4}>
                <Card>
                  <CardContent>
                    <Box display="flex" alignItems="center" gap={1} mb={2}>
                      <TrendingUpRounded />
                      <Typography variant="h6">Analyst Ratings</Typography>
                    </Box>
                    <Box display="flex" justifyContent="space-between" mb={1}>
                      <Typography variant="body2">Score:</Typography>
                      <Typography variant="body2" fontWeight="600">
                        {latestAnalyst.sentiment_score?.toFixed(2) || "N/A"}
                      </Typography>
                    </Box>
                    <Box display="flex" justifyContent="space-between" mb={1}>
                      <Typography variant="body2">Buy:</Typography>
                      <Chip label={latestAnalyst.positive_mentions || 0} size="small" color="success" variant="outlined" />
                    </Box>
                    <Box display="flex" justifyContent="space-between" mb={1}>
                      <Typography variant="body2">Hold:</Typography>
                      <Chip label={latestAnalyst.neutral_mentions || 0} size="small" color="default" variant="outlined" />
                    </Box>
                    <Box display="flex" justifyContent="space-between" mb={1}>
                      <Typography variant="body2">Sell:</Typography>
                      <Chip label={latestAnalyst.negative_mentions || 0} size="small" color="error" variant="outlined" />
                    </Box>
                    <Box display="flex" justifyContent="space-between">
                      <Typography variant="body2">Total Analysts:</Typography>
                      <Typography variant="body2" fontWeight="600">{latestAnalyst.total_mentions || 0}</Typography>
                    </Box>
                  </CardContent>
                </Card>
              </Grid>
            )}
          </Grid>

          {/* Historical Sentiment Table */}
          <Card sx={{ mt: 3 }}>
            <CardContent>
              <Typography variant="h6" mb={2}>Recent Sentiment Data</Typography>
              <TableContainer component={Paper} variant="outlined">
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Date</TableCell>
                      <TableCell>Source</TableCell>
                      <TableCell align="center">Score</TableCell>
                      <TableCell align="center">Positive</TableCell>
                      <TableCell align="center">Neutral</TableCell>
                      <TableCell align="center">Negative</TableCell>
                      <TableCell align="center">Total</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {stockData.slice(0, 20).map((row, index) => (
                      <TableRow key={index}>
                        <TableCell>{new Date(row.date).toLocaleDateString()}</TableCell>
                        <TableCell>
                          <Chip label={row.source || "Unknown"} size="small" variant="outlined" />
                        </TableCell>
                        <TableCell align="center">
                          <Chip
                            label={row.sentiment_score?.toFixed(2) || "N/A"}
                            size="small"
                            color={row.sentiment_score > 0.2 ? "success" : row.sentiment_score < -0.2 ? "error" : "warning"}
                          />
                        </TableCell>
                        <TableCell align="center">{row.positive_mentions || 0}</TableCell>
                        <TableCell align="center">{row.neutral_mentions || 0}</TableCell>
                        <TableCell align="center">{row.negative_mentions || 0}</TableCell>
                        <TableCell align="center">{row.total_mentions || 0}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </CardContent>
          </Card>
        </>
      )}
    </Container>
  );
}

export default Sentiment;
