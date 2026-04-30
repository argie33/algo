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
import {
  LineChart as RechartsLineChart,
  Line as RechartLine,
  XAxis as RechartXAxis,
  YAxis as RechartYAxis,
  CartesianGrid as RechartCartesianGrid,
  Tooltip as RechartTooltip,
  Legend as RechartLegend,
  ResponsiveContainer as RechartResponsiveContainer
} from 'recharts';

const BacktestResults = () => {
  const [runs, setRuns] = useState([]);
  const [selectedRun, setSelectedRun] = useState(null);
  const [runDetail, setRunDetail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filters, setFilters] = useState({
    strategy_name: '',
    limit: 50,
    offset: 0,
    sort_by: 'run_timestamp',
    order: 'DESC'
  });
  const [pagination, setPagination] = useState({
    total: 0,
    page: 1,
    totalPages: 1
  });

  useEffect(() => {
    fetchRuns();
  }, [filters]);

  const fetchRuns = async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams();
      if (filters.strategy_name) params.append('strategy_name', filters.strategy_name);
      params.append('limit', filters.limit);
      params.append('offset', filters.offset);
      params.append('sort_by', filters.sort_by);
      params.append('order', filters.order);

      const response = await axios.get(`/api/research/backtests?${params}`);
      setRuns(response.data.items || []);
      setPagination(response.data.pagination);
      setError(null);
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to load backtest runs');
      setRuns([]);
    } finally {
      setLoading(false);
    }
  };

  const fetchRunDetail = async (runId) => {
    try {
      const response = await axios.get(`/api/research/backtests/${runId}`);
      setRunDetail(response.data);
      setSelectedRun(runId);
    } catch (err) {
      setError('Failed to load run details');
    }
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

  const formatDate = (dateStr) => {
    return new Date(dateStr).toLocaleDateString();
  };

  const KPICard = ({ label, value, decimals = 2 }) => (
    <Card>
      <CardContent>
        <Typography color="textSecondary" gutterBottom>
          {label}
        </Typography>
        <Typography variant="h6">
          {typeof value === 'number' ? value.toFixed(decimals) : value || 'N/A'}
        </Typography>
      </CardContent>
    </Card>
  );

  return (
    <Container maxWidth="lg" sx={{ py: 4 }}>
      <Typography variant="h4" gutterBottom>
        Backtest Results
      </Typography>

      <Paper sx={{ p: 2, mb: 3 }}>
        <Grid container spacing={2}>
          <Grid item xs={12} sm={6} md={4}>
            <TextField
              size="small"
              label="Strategy"
              value={filters.strategy_name}
              onChange={(e) => handleFilterChange('strategy_name', e.target.value)}
              fullWidth
              select
              SelectProps={{ native: true }}
            >
              <option value="">All Strategies</option>
              <option value="swing">Swing Breakout</option>
              <option value="range">Range Trading</option>
              <option value="mean_reversion">Mean Reversion</option>
            </TextField>
          </Grid>
          <Grid item xs={12} sm={6} md={4}>
            <TextField
              size="small"
              label="Sort By"
              value={filters.sort_by}
              onChange={(e) => handleFilterChange('sort_by', e.target.value)}
              fullWidth
              select
              SelectProps={{ native: true }}
            >
              <option value="run_timestamp">Date</option>
              <option value="win_rate">Win Rate</option>
              <option value="expectancy_per_trade">Expectancy</option>
              <option value="sharpe">Sharpe Ratio</option>
              <option value="total_signals">Signals</option>
            </TextField>
          </Grid>
          <Grid item xs={12} sm={6} md={4}>
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
      ) : !selectedRun ? (
        <>
          <TableContainer component={Paper}>
            <Table>
              <TableHead sx={{ backgroundColor: '#f5f5f5' }}>
                <TableRow>
                  <TableCell><strong>Run Name</strong></TableCell>
                  <TableCell><strong>Strategy</strong></TableCell>
                  <TableCell><strong>Date Range</strong></TableCell>
                  <TableCell><strong>Signals</strong></TableCell>
                  <TableCell><strong>Win %</strong></TableCell>
                  <TableCell><strong>Expectancy</strong></TableCell>
                  <TableCell><strong>Max DD %</strong></TableCell>
                  <TableCell><strong>Sharpe</strong></TableCell>
                  <TableCell><strong>Return %</strong></TableCell>
                  <TableCell><strong>Action</strong></TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {runs.map((run) => (
                  <TableRow key={run.run_id}>
                    <TableCell>{run.run_name}</TableCell>
                    <TableCell>{run.strategy_name}</TableCell>
                    <TableCell>
                      {formatDate(run.date_start)} to {formatDate(run.date_end)}
                    </TableCell>
                    <TableCell>{run.total_signals}</TableCell>
                    <TableCell>
                      <Chip
                        label={`${run.win_rate?.toFixed(1)}%`}
                        size="small"
                        color={run.win_rate >= 50 ? 'success' : 'warning'}
                        variant="outlined"
                      />
                    </TableCell>
                    <TableCell>{run.expectancy_per_trade?.toFixed(3)}</TableCell>
                    <TableCell>{run.max_drawdown_pct?.toFixed(1)}%</TableCell>
                    <TableCell>{run.sharpe?.toFixed(2)}</TableCell>
                    <TableCell>
                      <Chip
                        label={`${run.total_return_pct?.toFixed(1)}%`}
                        size="small"
                        color={run.total_return_pct >= 0 ? 'success' : 'error'}
                        variant="outlined"
                      />
                    </TableCell>
                    <TableCell>
                      <Button
                        size="small"
                        variant="outlined"
                        onClick={() => fetchRunDetail(run.run_id)}
                      >
                        View
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>

          <Box sx={{ mt: 3, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Typography>
              Page {pagination.page} of {pagination.totalPages} | Total: {pagination.total} runs
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
      ) : runDetail ? (
        <>
          <Button variant="outlined" onClick={() => { setSelectedRun(null); setRunDetail(null); }} sx={{ mb: 2 }}>
            Back to Runs
          </Button>

          <Paper sx={{ p: 3, mb: 3 }}>
            <Grid container spacing={2}>
              <Grid item xs={12}>
                <Typography variant="h5">{runDetail.run.run_name}</Typography>
                <Typography variant="body2" color="textSecondary">
                  {runDetail.run.strategy_name} | {formatDate(runDetail.run.date_start)} to {formatDate(runDetail.run.date_end)}
                </Typography>
              </Grid>

              <Grid item xs={12} sm={6} md={3}>
                <KPICard label="Total Signals" value={runDetail.run.total_signals} decimals={0} />
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <KPICard label="Win Rate" value={runDetail.run.win_rate} decimals={1} />
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <KPICard label="Expectancy" value={runDetail.run.expectancy_per_trade} decimals={3} />
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <KPICard label="Sharpe Ratio" value={runDetail.run.sharpe} decimals={2} />
              </Grid>

              <Grid item xs={12} sm={6} md={3}>
                <KPICard label="Profit Factor" value={runDetail.run.profit_factor} decimals={2} />
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <KPICard label="Max Drawdown" value={runDetail.run.max_drawdown_pct} decimals={1} />
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <KPICard label="Avg Win" value={runDetail.run.avg_win_pct} decimals={2} />
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <KPICard label="Avg Loss" value={runDetail.run.avg_loss_pct} decimals={2} />
              </Grid>

              {runDetail.run.notes && (
                <Grid item xs={12}>
                  <Card>
                    <CardContent>
                      <Typography color="textSecondary" gutterBottom>
                        Notes
                      </Typography>
                      <Typography>{runDetail.run.notes}</Typography>
                    </CardContent>
                  </Card>
                </Grid>
              )}
            </Grid>
          </Paper>

          {runDetail.run.equity_curve && (
            <Paper sx={{ p: 3, mb: 3 }}>
              <Typography variant="h6" gutterBottom>
                Equity Curve
              </Typography>
              <RechartResponsiveContainer width="100%" height={300}>
                <RechartsLineChart data={runDetail.run.equity_curve}>
                  <RechartCartesianGrid strokeDasharray="3 3" />
                  <RechartXAxis dataKey="date" />
                  <RechartYAxis />
                  <RechartTooltip />
                  <RechartLegend />
                  <RechartLine type="monotone" dataKey="equity" stroke="#8884d8" />
                </RechartsLineChart>
              </RechartResponsiveContainer>
            </Paper>
          )}

          <Paper sx={{ p: 3 }}>
            <Typography variant="h6" gutterBottom>
              Trades ({runDetail.trade_pagination.total})
            </Typography>
            <TableContainer>
              <Table size="small">
                <TableHead sx={{ backgroundColor: '#f5f5f5' }}>
                  <TableRow>
                    <TableCell>Symbol</TableCell>
                    <TableCell>Entry Date</TableCell>
                    <TableCell>Exit Date</TableCell>
                    <TableCell>Entry Price</TableCell>
                    <TableCell>Exit Price</TableCell>
                    <TableCell>Return %</TableCell>
                    <TableCell>Outcome</TableCell>
                    <TableCell>Days</TableCell>
                    <TableCell>MFE %</TableCell>
                    <TableCell>MAE %</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {runDetail.trades.map((trade) => (
                    <TableRow key={trade.trade_id}>
                      <TableCell>{trade.symbol}</TableCell>
                      <TableCell>{formatDate(trade.signal_date)}</TableCell>
                      <TableCell>{formatDate(trade.exit_date)}</TableCell>
                      <TableCell>${trade.entry_price?.toFixed(2)}</TableCell>
                      <TableCell>${trade.exit_price?.toFixed(2)}</TableCell>
                      <TableCell>
                        <Chip
                          label={`${trade.return_pct?.toFixed(2)}%`}
                          size="small"
                          color={trade.return_pct >= 0 ? 'success' : 'error'}
                          variant="outlined"
                        />
                      </TableCell>
                      <TableCell>{trade.outcome}</TableCell>
                      <TableCell>{trade.days_held}</TableCell>
                      <TableCell>{trade.mfe_pct?.toFixed(1)}%</TableCell>
                      <TableCell>{trade.mae_pct?.toFixed(1)}%</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </Paper>
        </>
      ) : null}
    </Container>
  );
};

export default BacktestResults;
