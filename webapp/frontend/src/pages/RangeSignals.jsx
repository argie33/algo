import React, { useEffect, useState } from 'react';
import {
  Container,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  CircularProgress,
  Alert,
  Box,
  TextField,
  Button,
  Grid,
  Card,
  CardContent,
  Typography,
  Collapse,
  IconButton,
  Chip
} from '@mui/material';
import { KeyboardArrowDown, KeyboardArrowUp } from '@mui/icons-material';
import axios from 'axios';

const RangeSignals = () => {
  const [signals, setSignals] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [expandedRows, setExpandedRows] = useState(new Set());
  const [filters, setFilters] = useState({
    signal: '',
    signal_type: '',
    symbol: '',
    days: 30,
    limit: 50,
    offset: 0
  });
  const [pagination, setPagination] = useState({
    total: 0,
    page: 1,
    totalPages: 1
  });

  useEffect(() => {
    fetchSignals();
  }, [filters]);

  const fetchSignals = async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams();
      if (filters.signal) params.append('signal', filters.signal);
      if (filters.signal_type) params.append('signal_type', filters.signal_type);
      if (filters.symbol) params.append('symbol', filters.symbol);
      params.append('days', filters.days);
      params.append('limit', filters.limit);
      params.append('offset', filters.offset);

      const response = await axios.get(`/api/signals/range?${params}`);
      setSignals(response.data.items || []);
      setPagination(response.data.pagination);
      setError(null);
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to load range signals');
      setSignals([]);
    } finally {
      setLoading(false);
    }
  };

  const handleExpandClick = (id) => {
    const newExpanded = new Set(expandedRows);
    if (newExpanded.has(id)) {
      newExpanded.delete(id);
    } else {
      newExpanded.add(id);
    }
    setExpandedRows(newExpanded);
  };

  const handleFilterChange = (key, value) => {
    setFilters(prev => ({
      ...prev,
      [key]: value,
      offset: 0
    }));
  };

  const handlePageChange = (newOffset) => {
    setFilters(prev => ({
      ...prev,
      offset: newOffset
    }));
  };

  const getSignalColor = (signal) => {
    if (signal === 'BUY') return '#4caf50';
    if (signal === 'SELL') return '#f44336';
    return '#9e9e9e';
  };

  const ExpandableRow = ({ signal }) => (
    <React.Fragment>
      <TableRow>
        <TableCell>
          <IconButton
            size="small"
            onClick={() => handleExpandClick(signal.id)}
          >
            {expandedRows.has(signal.id) ? <KeyboardArrowUp /> : <KeyboardArrowDown />}
          </IconButton>
        </TableCell>
        <TableCell>{signal.symbol}</TableCell>
        <TableCell>{new Date(signal.date).toLocaleDateString()}</TableCell>
        <TableCell>
          <Chip
            label={signal.signal}
            size="small"
            style={{ backgroundColor: getSignalColor(signal.signal), color: 'white' }}
          />
        </TableCell>
        <TableCell>{signal.signal_type}</TableCell>
        <TableCell>{signal.range_position?.toFixed(1)}%</TableCell>
        <TableCell>${signal.range_high?.toFixed(2)}</TableCell>
        <TableCell>${signal.range_low?.toFixed(2)}</TableCell>
        <TableCell>${signal.entry_price?.toFixed(2)}</TableCell>
        <TableCell>{signal.risk_reward_ratio?.toFixed(2)}</TableCell>
      </TableRow>
      <TableRow>
        <TableCell colSpan={10} style={{ paddingBottom: 0, paddingTop: 0 }}>
          <Collapse in={expandedRows.has(signal.id)} timeout="auto" unmountOnExit>
            <Box sx={{ margin: 2 }}>
              <Grid container spacing={2}>
                <Grid item xs={12} sm={6} md={3}>
                  <Card>
                    <CardContent>
                      <Typography color="textSecondary" gutterBottom>
                        Range Age
                      </Typography>
                      <Typography variant="h6">
                        {signal.range_age_days} days
                      </Typography>
                    </CardContent>
                  </Card>
                </Grid>
                <Grid item xs={12} sm={6} md={3}>
                  <Card>
                    <CardContent>
                      <Typography color="textSecondary" gutterBottom>
                        Range Strength
                      </Typography>
                      <Typography variant="h6">
                        {signal.range_strength} touches
                      </Typography>
                    </CardContent>
                  </Card>
                </Grid>
                <Grid item xs={12} sm={6} md={3}>
                  <Card>
                    <CardContent>
                      <Typography color="textSecondary" gutterBottom>
                        TD Buy Setup
                      </Typography>
                      <Typography variant="h6">
                        {signal.td_buy_setup_count}/9
                      </Typography>
                    </CardContent>
                  </Card>
                </Grid>
                <Grid item xs={12} sm={6} md={3}>
                  <Card>
                    <CardContent>
                      <Typography color="textSecondary" gutterBottom>
                        TD Pressure
                      </Typography>
                      <Typography variant="h6">
                        {signal.td_pressure?.toFixed(0)}
                      </Typography>
                    </CardContent>
                  </Card>
                </Grid>
                <Grid item xs={12} sm={6}>
                  <Card>
                    <CardContent>
                      <Typography color="textSecondary" gutterBottom>
                        Trade Levels
                      </Typography>
                      <Typography variant="body2">
                        Stop: ${signal.stop_level?.toFixed(2)} | Target 1: ${signal.target_1?.toFixed(2)} | Target 2: ${signal.target_2?.toFixed(2)}
                      </Typography>
                    </CardContent>
                  </Card>
                </Grid>
                <Grid item xs={12} sm={6}>
                  <Card>
                    <CardContent>
                      <Typography color="textSecondary" gutterBottom>
                        Technicals
                      </Typography>
                      <Typography variant="body2">
                        RSI: {signal.rsi?.toFixed(1)} | ADX: {signal.adx?.toFixed(1)} | ATR: ${signal.atr?.toFixed(2)}
                      </Typography>
                    </CardContent>
                  </Card>
                </Grid>
              </Grid>
            </Box>
          </Collapse>
        </TableCell>
      </TableRow>
    </React.Fragment>
  );

  return (
    <Container maxWidth="lg" sx={{ py: 4 }}>
      <Typography variant="h4" gutterBottom>
        Range Trading Signals
      </Typography>

      <Paper sx={{ p: 2, mb: 3 }}>
        <Grid container spacing={2}>
          <Grid item xs={12} sm={6} md={3}>
            <TextField
              size="small"
              label="Symbol"
              value={filters.symbol}
              onChange={(e) => handleFilterChange('symbol', e.target.value)}
              fullWidth
            />
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <TextField
              size="small"
              label="Signal Type"
              value={filters.signal_type}
              onChange={(e) => handleFilterChange('signal_type', e.target.value)}
              fullWidth
              select
              SelectProps={{ native: true }}
            >
              <option value="">All</option>
              <option value="RANGE_BOUNCE_LOW">Long (Support)</option>
              <option value="RANGE_BOUNCE_HIGH">Short (Resistance)</option>
              <option value="RANGE_BREAKOUT_UP">Breakout Up</option>
              <option value="RANGE_BREAKDOWN">Breakdown</option>
            </TextField>
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <TextField
              size="small"
              label="Days"
              type="number"
              value={filters.days}
              onChange={(e) => handleFilterChange('days', e.target.value)}
              fullWidth
            />
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <Button variant="contained" fullWidth onClick={() => setFilters(filters)}>
              Apply Filters
            </Button>
          </Grid>
        </Grid>
      </Paper>

      {error && <Alert severity="error">{error}</Alert>}

      {loading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
          <CircularProgress />
        </Box>
      ) : (
        <>
          <TableContainer component={Paper}>
            <Table>
              <TableHead sx={{ backgroundColor: '#f5f5f5' }}>
                <TableRow>
                  <TableCell width="5%" />
                  <TableCell><strong>Symbol</strong></TableCell>
                  <TableCell><strong>Date</strong></TableCell>
                  <TableCell><strong>Signal</strong></TableCell>
                  <TableCell><strong>Type</strong></TableCell>
                  <TableCell><strong>Position %</strong></TableCell>
                  <TableCell><strong>Range High</strong></TableCell>
                  <TableCell><strong>Range Low</strong></TableCell>
                  <TableCell><strong>Entry</strong></TableCell>
                  <TableCell><strong>R:R</strong></TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {signals.map((signal) => (
                  <ExpandableRow key={signal.id} signal={signal} />
                ))}
              </TableBody>
            </Table>
          </TableContainer>

          <Box sx={{ mt: 3, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Typography>
              Page {pagination.page} of {pagination.totalPages} | Total: {pagination.total} signals
            </Typography>
            <Box>
              <Button
                disabled={!pagination.hasPrev}
                onClick={() => handlePageChange(filters.offset - filters.limit)}
              >
                Previous
              </Button>
              <Button
                disabled={!pagination.hasNext}
                onClick={() => handlePageChange(filters.offset + filters.limit)}
              >
                Next
              </Button>
            </Box>
          </Box>
        </>
      )}
    </Container>
  );
};

export default RangeSignals;
