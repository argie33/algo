import React, { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import api from "../services/api";
import {
  Box,
  Container,
  Typography,
  Grid,
  Card,
  CardContent,
  Alert,
  CircularProgress,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Chip,
  TablePagination,
} from "@mui/material";
import {
  TrendingUp,
  TrendingDown,
  ShowChart,
  Schedule,
} from "@mui/icons-material";
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";

function EarningsCalendar() {
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(25);

  // Fetch S&P 500 earnings trend data
  const {
    data: sp500TrendData,
    isLoading: sp500Loading,
    error: sp500Error,
  } = useQuery({
    queryKey: ["sp500EarningsTrend"],
    queryFn: async () => {
      const response = await api.get('/api/earnings/sp500-trend');
      return response.data;
    },
    staleTime: 1000 * 60 * 60,
  });

  // Fetch sector earnings trend
  const {
    data: sectorTrendData,
    isLoading: sectorTrendLoading,
    error: sectorTrendError,
  } = useQuery({
    queryKey: ["sectorEarningsTrend"],
    queryFn: async () => {
      const response = await api.get('/api/earnings/sector-trend');
      return response.data;
    },
    staleTime: 1000 * 60 * 60,
  });

  // Fetch upcoming earnings
  const {
    data: upcomingData,
    isLoading: upcomingLoading,
    error: upcomingError,
  } = useQuery({
    queryKey: ["upcomingEarnings", page, rowsPerPage],
    queryFn: async () => {
      const response = await api.get(`/api/earnings/calendar?period=upcoming&limit=50`);
      return response.data?.items || [];
    },
  });

  // Fetch past earnings
  const {
    data: pastData,
    isLoading: pastLoading,
    error: pastError,
  } = useQuery({
    queryKey: ["pastEarnings"],
    queryFn: async () => {
      const response = await api.get('/api/earnings/calendar?period=past&limit=50');
      return response.data?.items || [];
    },
  });

  const handleChangePage = (event, newPage) => {
    setPage(newPage);
  };

  const handleChangeRowsPerPage = (event) => {
    setRowsPerPage(parseInt(event.target.value, 10));
    setPage(0);
  };

  if (sp500Loading || sectorTrendLoading) {
    return (
      <Container maxWidth="xl" sx={{ py: 4 }}>
        <Box display="flex" justifyContent="center" alignItems="center" minHeight="400px">
          <CircularProgress />
        </Box>
      </Container>
    );
  }

  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      <Typography variant="h4" gutterBottom sx={{ fontWeight: 600, mb: 4 }}>
        📊 Earnings Calendar
      </Typography>

      {/* S&P 500 Earnings Trend */}
      <Card sx={{ mb: 4 }}>
        <CardContent>
          <Box display="flex" alignItems="center" gap={1} mb={3}>
            <ShowChart color="primary" />
            <Typography variant="h6">S&P 500 Earnings Trend</Typography>
          </Box>

          {sp500Error && (
            <Alert severity="error" sx={{ mb: 2 }}>
              Failed to load S&P 500 earnings data.
            </Alert>
          )}

          {sp500TrendData ? (
            <Grid container spacing={3}>
              <Grid item xs={12} md={6}>
                <Box>
                  <Typography variant="body2" color="text.secondary" gutterBottom>
                    Stocks Reporting (Last 3 Months)
                  </Typography>
                  <Typography variant="h4" fontWeight="bold" color="primary">
                    {sp500TrendData.stocks_reporting || 0} stocks
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {sp500TrendData.note || 'From S&P 500 earnings reports'}
                  </Typography>
                </Box>
              </Grid>
            </Grid>
          ) : (
            <Alert severity="info">No S&P 500 earnings data available</Alert>
          )}
        </CardContent>
      </Card>

      {/* Sector Earnings Trend */}
      {sectorTrendData?.timeSeries && sectorTrendData.timeSeries.length > 0 && (
        <Card sx={{ mb: 4 }}>
          <CardContent>
            <Box display="flex" alignItems="center" gap={1} mb={3}>
              <ShowChart color="primary" />
              <Typography variant="h6">Sector Earnings Growth</Typography>
            </Box>

            <Box sx={{ width: '100%', height: 400 }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={sectorTrendData.timeSeries}
                  margin={{ top: 20, right: 30, left: 0, bottom: 60 }}
                >
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis
                    dataKey="quarter"
                    angle={-45}
                    textAnchor="end"
                    height={100}
                    tick={{ fontSize: 12 }}
                  />
                  <YAxis label={{ value: 'EPS ($)', angle: -90, position: 'insideLeft' }} />
                  <Tooltip
                    formatter={(value) => typeof value === 'number' ? `$${value.toFixed(2)}` : value}
                  />
                  <Legend />
                  {/* Display all sectors as bars */}
                  {sectorTrendData.timeSeries.length > 0 &&
                    Object.keys(sectorTrendData.timeSeries[0])
                      .filter(key => key !== 'quarter')
                      .slice(0, 8)
                      .map((sector, idx) => (
                        <Bar
                          key={sector}
                          dataKey={sector}
                          fill={['#2196F3', '#4CAF50', '#FF9800', '#9C27B0', '#FF5722', '#607D8B', '#8BC34A', '#E91E63'][idx]}
                          stackId="a"
                        />
                      ))
                  }
                </BarChart>
              </ResponsiveContainer>
            </Box>

            {sectorTrendData.bestGrowth && (
              <Box sx={{ mt: 3, p: 2, bgcolor: '#f5f5f5', borderRadius: 1 }}>
                <Typography variant="body2" color="text.secondary" gutterBottom>
                  Best Performing Sector
                </Typography>
                <Typography variant="h6" color="success.main">
                  {sectorTrendData.bestGrowth.name}: {sectorTrendData.bestGrowth.growth?.toFixed(1)}% growth
                </Typography>
              </Box>
            )}
          </CardContent>
        </Card>
      )}

      {/* Upcoming Earnings */}
      <Card sx={{ mb: 4 }}>
        <CardContent>
          <Box display="flex" alignItems="center" gap={1} mb={3}>
            <Schedule color="primary" />
            <Typography variant="h6">Upcoming Earnings</Typography>
          </Box>

          {upcomingLoading ? (
            <CircularProgress />
          ) : upcomingError ? (
            <Alert severity="error">Failed to load upcoming earnings</Alert>
          ) : upcomingData && upcomingData.length > 0 ? (
            <TableContainer component={Paper}>
              <Table>
                <TableHead>
                  <TableRow sx={{ backgroundColor: '#f5f5f5' }}>
                    <TableCell sx={{ fontWeight: 'bold' }}>Symbol</TableCell>
                    <TableCell sx={{ fontWeight: 'bold' }}>Quarter</TableCell>
                    <TableCell align="right" sx={{ fontWeight: 'bold' }}>EPS Estimate</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {upcomingData.map((item, idx) => (
                    <TableRow key={idx} sx={{ '&:hover': { backgroundColor: '#f9f9f9' } }}>
                      <TableCell sx={{ fontWeight: '500' }}>{item.symbol}</TableCell>
                      <TableCell>{item.quarter || item.fiscal_quarter || '—'}</TableCell>
                      <TableCell align="right">${(item.eps_estimate || 0).toFixed(2)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          ) : (
            <Alert severity="info">No upcoming earnings data available</Alert>
          )}
        </CardContent>
      </Card>

      {/* Past Earnings */}
      <Card>
        <CardContent>
          <Box display="flex" alignItems="center" gap={1} mb={3}>
            <TrendingUp color="primary" />
            <Typography variant="h6">Recent Earnings</Typography>
          </Box>

          {pastLoading ? (
            <CircularProgress />
          ) : pastError ? (
            <Alert severity="error">Failed to load past earnings</Alert>
          ) : pastData && pastData.length > 0 ? (
            <TableContainer component={Paper}>
              <Table>
                <TableHead>
                  <TableRow sx={{ backgroundColor: '#f5f5f5' }}>
                    <TableCell sx={{ fontWeight: 'bold' }}>Symbol</TableCell>
                    <TableCell sx={{ fontWeight: 'bold' }}>Quarter</TableCell>
                    <TableCell align="right" sx={{ fontWeight: 'bold' }}>Actual EPS</TableCell>
                    <TableCell align="right" sx={{ fontWeight: 'bold' }}>Estimated EPS</TableCell>
                    <TableCell align="right" sx={{ fontWeight: 'bold' }}>Surprise %</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {pastData.map((item, idx) => {
                    const surprise = item.eps_surprise_pct || 0;
                    const surpriseColor = surprise > 0 ? 'success.main' : surprise < 0 ? 'error.main' : 'grey.500';
                    return (
                      <TableRow key={idx} sx={{ '&:hover': { backgroundColor: '#f9f9f9' } }}>
                        <TableCell sx={{ fontWeight: '500' }}>{item.symbol}</TableCell>
                        <TableCell>{item.quarter || item.fiscal_quarter || '—'}</TableCell>
                        <TableCell align="right">${(item.eps_actual || 0).toFixed(2)}</TableCell>
                        <TableCell align="right">${(item.eps_estimate || 0).toFixed(2)}</TableCell>
                        <TableCell align="right">
                          <Chip
                            label={`${surprise.toFixed(1)}%`}
                            size="small"
                            color={surprise > 0 ? 'success' : surprise < 0 ? 'error' : 'default'}
                          />
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </TableContainer>
          ) : (
            <Alert severity="info">No past earnings data available</Alert>
          )}
        </CardContent>
      </Card>
    </Container>
  );
}

export default EarningsCalendar;
