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

const MeanReversionSignals = () => {
  const [signals, setSignals] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [expandedRows, setExpandedRows] = useState(new Set());
  const [filters, setFilters] = useState({
    symbol: '',
    min_confluence: 0,
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
      if (filters.symbol) params.append('symbol', filters.symbol);
      params.append('min_confluence', filters.min_confluence);
      params.append('days', filters.days);
      params.append('limit', filters.limit);
      params.append('offset', filters.offset);

      const response = await axios.get(`/api/signals/mean-reversion?${params}`);
      setSignals(response.data.items || []);
      setPagination(response.data.pagination);
      setError(null);
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to load mean reversion signals');
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

  const getConfluenceColor = (score) => {
    if (score >= 4) return '#4caf50';
    if (score >= 2) return '#ff9800';
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
            label={signal.confluence_score}
            size="small"
            style={{ backgroundColor: getConfluenceColor(signal.confluence_score), color: 'white' }}
          />
        </TableCell>
        <TableCell>{signal.rsi_2?.toFixed(1)}</TableCell>
        <TableCell>{signal.pct_above_200sma?.toFixed(1)}%</TableCell>
        <TableCell>${signal.entry_price?.toFixed(2)}</TableCell>
        <TableCell>${signal.stop_level?.toFixed(2)}</TableCell>
        <TableCell>${signal.target_estimate?.toFixed(2)}</TableCell>
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
                        RSI(2)
                      </Typography>
                      <Typography variant="h6">
                        {signal.rsi_2?.toFixed(1)}
                      </Typography>
                      <Typography color="textSecondary" variant="caption">
                        Extreme Oversold: &lt;10
                      </Typography>
                    </CardContent>
                  </Card>
                </Grid>
                <Grid item xs={12} sm={6} md={3}>
                  <Card>
                    <CardContent>
                      <Typography color="textSecondary" gutterBottom>
                        RSI(14)
                      </Typography>
                      <Typography variant="h6">
                        {signal.rsi_14?.toFixed(1)}
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
                        {signal.td_buy_setup_complete && ' ✓'}
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
                        Position & Levels
                      </Typography>
                      <Typography variant="body2">
                        <strong>% above 200 SMA:</strong> {signal.pct_above_200sma?.toFixed(1)}%
                        <br />
                        <strong>Risk:</strong> {signal.risk_pct?.toFixed(1)}%
                        <br />
                        <strong>R:R Ratio:</strong> {signal.risk_reward_ratio?.toFixed(2)}
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
                        <strong>ATR:</strong> ${signal.atr?.toFixed(2)}
                        <br />
                        <strong>5-day SMA:</strong> ${signal.sma_5?.toFixed(2)}
                        <br />
                        <strong>Exit signal:</strong> Close above 5-day SMA
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
        Mean Reversion Signals (Connors RSI&lt;10)
      </Typography>

      <Paper sx={{ p: 2, mb: 3 }}>
        <Grid container spacing={2}>
          <Grid item xs={12} sm={6} md={4}>
            <TextField
              size="small"
              label="Symbol"
              value={filters.symbol}
              onChange={(e) => handleFilterChange('symbol', e.target.value)}
              fullWidth
            />
          </Grid>
          <Grid item xs={12} sm={6} md={4}>
            <TextField
              size="small"
              label="Min Confluence Score"
              type="number"
              value={filters.min_confluence}
              onChange={(e) => handleFilterChange('min_confluence', e.target.value)}
              fullWidth
              inputProps={{ min: 0, max: 5 }}
            />
          </Grid>
          <Grid item xs={12} sm={6} md={4}>
            <TextField
              size="small"
              label="Days"
              type="number"
              value={filters.days}
              onChange={(e) => handleFilterChange('days', e.target.value)}
              fullWidth
            />
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
                  <TableCell><strong>Confluence</strong></TableCell>
                  <TableCell><strong>RSI(2)</strong></TableCell>
                  <TableCell><strong>% Above 200SMA</strong></TableCell>
                  <TableCell><strong>Entry</strong></TableCell>
                  <TableCell><strong>Stop</strong></TableCell>
                  <TableCell><strong>Target</strong></TableCell>
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

export default MeanReversionSignals;
