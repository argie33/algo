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
  LinearProgress,
} from "@mui/material";
import {
  TrendingUp,
  TrendingDown,
  TrendingFlat,
  SentimentSatisfiedAlt,
} from "@mui/icons-material";
import { useQuery } from "@tanstack/react-query";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from "recharts";

const API_BASE = window.CONFIG?.API_URL || "http://localhost:5001";

function Sentiment() {
  const [symbolFilter, setSymbolFilter] = useState("");

  // Fetch market-wide AAII sentiment data
  const { data: aaii, isLoading: aaiLoading, error: aaiError } = useQuery({
    queryKey: ["marketSentiment"],
    queryFn: async () => {
      const response = await fetch(`${API_BASE}/api/sentiment/market`);
      if (!response.ok) throw new Error("Failed to fetch market sentiment");
      return response.json();
    },
    refetchInterval: 300000,
  });

  // Fetch stock-specific sentiment data
  const { data: stockSentiment, isLoading: stockLoading, error: stockError } = useQuery({
    queryKey: ["stockSentiment", symbolFilter],
    queryFn: async () => {
      const url = symbolFilter
        ? `${API_BASE}/api/sentiment/stocks?symbol=${symbolFilter.toUpperCase()}`
        : `${API_BASE}/api/sentiment/stocks`;
      const response = await fetch(url);
      if (!response.ok) throw new Error("Failed to fetch stock sentiment");
      return response.json();
    },
    refetchInterval: 300000,
  });

  const marketData = aaii?.data || [];
  const stockData = stockSentiment?.data || [];
  const latestMarket = marketData[0] || { bullish: 0, neutral: 0, bearish: 0 };

  // Calculate sentiment signal
  const getSentimentSignal = (bullish, bearish) => {
    const diff = bullish - bearish;
    if (diff > 10) return { label: "Bullish", color: "success", icon: <TrendingUp /> };
    if (diff < -10) return { label: "Bearish", color: "error", icon: <TrendingDown /> };
    return { label: "Neutral", color: "warning", icon: <TrendingFlat /> };
  };

  const signal = getSentimentSignal(latestMarket.bullish, latestMarket.bearish);

  return (
    <Container maxWidth="xl" sx={{ py: 3 }}>
      <Box sx={{ mb: 3 }}>
        <Box display="flex" alignItems="center" gap={2}>
          <SentimentSatisfiedAlt sx={{ fontSize: 40, color: "primary.main" }} />
          <Typography variant="h4" component="h1">
            Sentiment Analysis
          </Typography>
        </Box>
        <Typography variant="subtitle1" color="textSecondary" sx={{ mt: 1 }}>
          Market and stock sentiment indicators from multiple sources
        </Typography>
      </Box>

      {/* Market Sentiment Overview */}
      <Grid container spacing={3} sx={{ mb: 3 }}>
        <Grid item xs={12} md={4}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center" justifyContent="space-between" mb={2}>
                <Typography variant="h6">Market Sentiment</Typography>
                <Chip label={signal.label} color={signal.color} icon={signal.icon} />
              </Box>
              {aaiLoading ? (
                <CircularProgress />
              ) : aaiError ? (
                <Alert severity="error">Failed to load market sentiment</Alert>
              ) : (
                <Box>
                  <Box mb={2}>
                    <Box display="flex" justifyContent="space-between" mb={1}>
                      <Typography variant="body2" color="textSecondary">
                        Bullish
                      </Typography>
                      <Typography variant="body2" fontWeight="bold" color="success.main">
                        {latestMarket.bullish}%
                      </Typography>
                    </Box>
                    <LinearProgress
                      variant="determinate"
                      value={latestMarket.bullish}
                      color="success"
                      sx={{ height: 8, borderRadius: 1 }}
                    />
                  </Box>
                  <Box mb={2}>
                    <Box display="flex" justifyContent="space-between" mb={1}>
                      <Typography variant="body2" color="textSecondary">
                        Neutral
                      </Typography>
                      <Typography variant="body2" fontWeight="bold" color="warning.main">
                        {latestMarket.neutral}%
                      </Typography>
                    </Box>
                    <LinearProgress
                      variant="determinate"
                      value={latestMarket.neutral}
                      color="warning"
                      sx={{ height: 8, borderRadius: 1 }}
                    />
                  </Box>
                  <Box>
                    <Box display="flex" justifyContent="space-between" mb={1}>
                      <Typography variant="body2" color="textSecondary">
                        Bearish
                      </Typography>
                      <Typography variant="body2" fontWeight="bold" color="error.main">
                        {latestMarket.bearish}%
                      </Typography>
                    </Box>
                    <LinearProgress
                      variant="determinate"
                      value={latestMarket.bearish}
                      color="error"
                      sx={{ height: 8, borderRadius: 1 }}
                    />
                  </Box>
                </Box>
              )}
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={8}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Market Sentiment Trend
              </Typography>
              {aaiLoading ? (
                <CircularProgress />
              ) : marketData.length > 0 ? (
                <ResponsiveContainer width="100%" height={250}>
                  <LineChart data={marketData.slice(0, 30).reverse()}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="date" tick={{ fontSize: 12 }} />
                    <YAxis />
                    <Tooltip />
                    <Legend />
                    <Line type="monotone" dataKey="bullish" stroke="#4caf50" name="Bullish %" />
                    <Line type="monotone" dataKey="neutral" stroke="#ff9800" name="Neutral %" />
                    <Line type="monotone" dataKey="bearish" stroke="#f44336" name="Bearish %" />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <Alert severity="info">No market sentiment data available</Alert>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Stock Sentiment */}
      <Card>
        <CardContent>
          <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
            <Typography variant="h6">Stock Sentiment</Typography>
            <TextField
              label="Filter by Symbol"
              variant="outlined"
              size="small"
              value={symbolFilter}
              onChange={(e) => setSymbolFilter(e.target.value)}
              placeholder="e.g., AAPL"
              sx={{ width: 200 }}
            />
          </Box>

          {stockLoading ? (
            <Box display="flex" justifyContent="center" py={4}>
              <CircularProgress />
            </Box>
          ) : stockError ? (
            <Alert severity="error">Failed to load stock sentiment data</Alert>
          ) : stockData.length === 0 ? (
            <Alert severity="info">No stock sentiment data available</Alert>
          ) : (
            <TableContainer component={Paper} variant="outlined">
              <Table>
                <TableHead>
                  <TableRow>
                    <TableCell>Symbol</TableCell>
                    <TableCell>Date</TableCell>
                    <TableCell align="center">Sentiment Score</TableCell>
                    <TableCell align="center">Positive</TableCell>
                    <TableCell align="center">Neutral</TableCell>
                    <TableCell align="center">Negative</TableCell>
                    <TableCell align="center">Total Mentions</TableCell>
                    <TableCell>Source</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {stockData.map((row, index) => {
                    const scoreColor =
                      row.sentiment_score > 0.2 ? "success" : row.sentiment_score < -0.2 ? "error" : "warning";
                    return (
                      <TableRow key={index}>
                        <TableCell>
                          <Typography fontWeight="bold">{row.symbol}</Typography>
                        </TableCell>
                        <TableCell>{new Date(row.date).toLocaleDateString()}</TableCell>
                        <TableCell align="center">
                          <Chip
                            label={row.sentiment_score?.toFixed(2) || "N/A"}
                            color={scoreColor}
                            size="small"
                          />
                        </TableCell>
                        <TableCell align="center">
                          <Chip
                            label={row.positive_mentions || 0}
                            color="success"
                            size="small"
                            variant="outlined"
                          />
                        </TableCell>
                        <TableCell align="center">
                          <Chip
                            label={row.neutral_mentions || 0}
                            color="default"
                            size="small"
                            variant="outlined"
                          />
                        </TableCell>
                        <TableCell align="center">
                          <Chip
                            label={row.negative_mentions || 0}
                            color="error"
                            size="small"
                            variant="outlined"
                          />
                        </TableCell>
                        <TableCell align="center">{row.total_mentions || 0}</TableCell>
                        <TableCell>{row.source || "Unknown"}</TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </CardContent>
      </Card>
    </Container>
  );
}

export default Sentiment;
