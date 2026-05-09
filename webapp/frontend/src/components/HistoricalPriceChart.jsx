import React, { useState, useEffect } from "react";
import {
  Box,
  Paper,
  CircularProgress,
  Typography,
  Card,
  CardContent,
  CardHeader,
} from "@mui/material";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  BarChart,
  Bar,
} from "recharts";
import api from "../services/api";

/**
 * Historical Price Chart
 * Displays historical OHLCV data with interactive price and volume charts
 */
const HistoricalPriceChart = ({ symbol = "AAPL", days = 90 }) => {
  const [chartData, setChartData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const loadChartData = async () => {
      try {
        setLoading(true);
        setError(null);

        // Try to fetch chart data from API
        const response = await (api.getChartData?.(symbol, days) ||
          api.getStockPrices?.(symbol, days) ||
          Promise.resolve({ data: [] }));

        const data = response?.data || [];

        // Transform data for chart
        const transformed = data.map((row) => ({
          date: row.date || new Date().toISOString().split("T")[0],
          close: parseFloat(row.close || row.price || 0),
          open: parseFloat(row.open || row.price || 0),
          high: parseFloat(row.high || row.price || 0),
          low: parseFloat(row.low || row.price || 0),
          volume: parseInt(row.volume || 0),
        }));

        setChartData(transformed);
      } catch (err) {
        console.error("Error loading chart data:", err);
        setError(err.message || "Failed to load chart data");
      } finally {
        setLoading(false);
      }
    };

    loadChartData();
  }, [symbol, days]);

  if (loading) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", p: 4 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (error) {
    return (
      <Card sx={{ m: 2, bgcolor: "error.light" }}>
        <CardContent>
          <Typography color="error">Error: {error}</Typography>
        </CardContent>
      </Card>
    );
  }

  if (!chartData || chartData.length === 0) {
    return (
      <Card sx={{ m: 2 }}>
        <CardContent>
          <Typography>No data available for {symbol}</Typography>
        </CardContent>
      </Card>
    );
  }

  return (
    <Box sx={{ width: "100%" }}>
      {/* Price Chart */}
      <Paper sx={{ p: 2, mb: 3 }}>
        <Typography variant="h6" gutterBottom>
          {symbol} - Price History ({days} days)
        </Typography>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="date" />
            <YAxis />
            <Tooltip />
            <Legend />
            <Line
              type="monotone"
              dataKey="close"
              stroke="#8884d8"
              name="Close Price"
            />
            <Line
              type="monotone"
              dataKey="high"
              stroke="#82ca9d"
              name="High"
              opacity={0.5}
            />
            <Line
              type="monotone"
              dataKey="low"
              stroke="#ffc658"
              name="Low"
              opacity={0.5}
            />
          </LineChart>
        </ResponsiveContainer>
      </Paper>

      {/* Volume Chart */}
      <Paper sx={{ p: 2 }}>
        <Typography variant="h6" gutterBottom>
          Trading Volume
        </Typography>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="date" />
            <YAxis />
            <Tooltip />
            <Bar dataKey="volume" fill="#8884d8" name="Volume" />
          </BarChart>
        </ResponsiveContainer>
      </Paper>
    </Box>
  );
};

export default HistoricalPriceChart;
