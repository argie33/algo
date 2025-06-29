import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { getTechnicalData } from '../services/api';
import {
  Container, Typography, Box, Card, CardContent, Divider, Button, Paper, Table, TableHead, TableRow, TableCell, TableBody, TablePagination, TextField, CircularProgress, Alert, Chip
} from '@mui/material';
import { TrendingUp, TrendingDown, ShowChart, InfoOutlined } from '@mui/icons-material';
import { formatNumber, formatDate, getTechStatus } from '../utils/formatters';
import { useTheme } from '@mui/material/styles';

function TechnicalHistory() {
  const { symbol } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(5); // Reduced from 25 for faster load
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [total, setTotal] = useState(0);
  const theme = useTheme();

  // --- Summary/overview ---
  const latest = data && data.length > 0 ? data[0] : null;
  const summaryIndicators = [
    { id: 'rsi', label: 'RSI' },
    { id: 'macd', label: 'MACD' },
    { id: 'pivot_high', label: 'Pivot H' },
    { id: 'pivot_low', label: 'Pivot L' },
    { id: 'pivot_high_triggered', label: 'Pivot H Triggered' },
    { id: 'pivot_low_triggered', label: 'Pivot L Triggered' }
  ];

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const params = {
        symbol,
        limit: rowsPerPage,
        page: page + 1,
        startDate: dateFrom,
        endDate: dateTo
      };
      const result = await getTechnicalData('daily', params);
      setData(result.data || []);
      setTotal(result.pagination?.total || 0);
    } catch (e) {
      setError(e.message || 'Failed to load history');
    }
    setLoading(false);
  };

  useEffect(() => {
    fetchData();
    // eslint-disable-next-line
  }, [symbol, page, rowsPerPage, dateFrom, dateTo]);

  const handlePageChange = (event, newPage) => setPage(newPage);
  const handleRowsPerPageChange = (event) => {
    setRowsPerPage(parseInt(event.target.value, 10));
    setPage(0);
  };

  // Add a Load More button for progressive loading
  const handleLoadMore = () => {
    setRowsPerPage(prev => prev + 10);
  };

  // --- Table columns (match TechnicalAnalysis) ---
  const columns = [
    { id: 'date', label: 'Date', format: formatDate },
    { id: 'rsi', label: 'RSI' },
    { id: 'macd', label: 'MACD' },
    { id: 'macd_signal', label: 'MACD Signal' },
    { id: 'macd_hist', label: 'MACD Hist' },
    { id: 'adx', label: 'ADX' },
    { id: 'atr', label: 'ATR' },
    { id: 'mfi', label: 'MFI' },
    { id: 'roc', label: 'ROC' },
    { id: 'mom', label: 'MOM' },
    { id: 'bbands_upper', label: 'BB Upper' },
    { id: 'bbands_middle', label: 'BB Middle' },
    { id: 'bbands_lower', label: 'BB Lower' },
    { id: 'sma_10', label: 'SMA 10' },
    { id: 'sma_20', label: 'SMA 20' },
    { id: 'sma_50', label: 'SMA 50' },
    { id: 'sma_150', label: 'SMA 150' },
    { id: 'sma_200', label: 'SMA 200' },
    { id: 'ema_4', label: 'EMA 4' },
    { id: 'ema_9', label: 'EMA 9' },
    { id: 'ema_21', label: 'EMA 21' },
    { id: 'ad', label: 'A/D' },
    { id: 'cmf', label: 'CMF' },
    { id: 'td_sequential', label: 'TD Seq' },
    { id: 'td_combo', label: 'TD Combo' },
    { id: 'marketwatch', label: 'MW' },
    { id: 'dm', label: 'DM' },
    { id: 'pivot_high', label: 'Pivot H' },
    { id: 'pivot_low', label: 'Pivot L' },
    { id: 'pivot_high_triggered', label: 'Pivot H Triggered' },
    { id: 'pivot_low_triggered', label: 'Pivot L Triggered' }
  ];

  // Helper to ensure only valid MUI Chip color values are used for the color prop
  const getMuiChipColor = (color) => {
    const validColors = ['default','primary','secondary','error','info','success','warning'];
    if (!color) return 'default';
    // Remove any .main or similar suffixes
    const cleaned = String(color).replace('.main','').toLowerCase();
    return validColors.includes(cleaned) ? cleaned : 'default';
  };

  // Helper to get themed color for indicators
  const getIndicatorColor = (color) => {
    if (!color) return undefined;
    const cleaned = color.replace('.main','');
    const validColors = ['primary','secondary','error','info','success','warning'];
    if (validColors.includes(cleaned) && theme.palette[cleaned]) {
      return theme.palette[cleaned].main;
    }
    return undefined;
  };

  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      <Button variant="outlined" onClick={() => navigate(-1)} sx={{ mb: 2 }}>Back</Button>
      <Typography variant="h4" gutterBottom>Technical History for {symbol}</Typography>
      <Divider sx={{ mb: 2 }} />
      {/* --- Summary/Overview --- */}
      {latest && (
        <Card sx={{ mb: 3, background: 'linear-gradient(90deg, #f5f7fa 0%, #c3cfe2 100%)', boxShadow: 2 }}>
          <CardContent>
            <Typography variant="h6" gutterBottom>Latest Technicals ({formatDate(latest.date)})</Typography>
            <Box display="flex" gap={3} flexWrap="wrap">
              {summaryIndicators.map(({ id, label }) => (
                <Box key={id} minWidth={120} display="flex" alignItems="center" gap={1}>
                  {getTechStatus(id, latest[id]).icon}
                  <Typography variant="subtitle2" color={getIndicatorColor(getTechStatus(id, latest[id]).color)} fontWeight="bold">
                    {label}:
                  </Typography>
                  <Typography variant="h6" color={getIndicatorColor(getTechStatus(id, latest[id]).color)} fontWeight="bold">
                    {latest[id] !== undefined && latest[id] !== null ? formatNumber(latest[id]) : 'N/A'}
                  </Typography>
                  {getTechStatus(id, latest[id]).label && (
                    <Chip 
                      label={getTechStatus(id, latest[id]).label} 
                      size="small" 
                      sx={{ ml: 1 }} 
                      color={getMuiChipColor(getTechStatus(id, latest[id]).color)}
                    />
                  )}
                </Box>
              ))}
            </Box>
          </CardContent>
        </Card>
      )}
      {/* --- Date filter --- */}
      <Box display="flex" gap={2} mb={2}>
        <TextField label="Date From" type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} size="small" InputLabelProps={{ shrink: true }} />
        <TextField label="Date To" type="date" value={dateTo} onChange={e => setDateTo(e.target.value)} size="small" InputLabelProps={{ shrink: true }} />
        <Button variant="contained" onClick={() => { setPage(0); fetchData(); }}>Apply</Button>
      </Box>
      {/* --- Main Table --- */}
      {loading ? (
        <Box display="flex" alignItems="center" justifyContent="center" minHeight={120}><CircularProgress /></Box>
      ) : error ? (
        <Alert severity="error">{error}</Alert>
      ) : (
        <Paper sx={{ width: '100%', overflowX: 'auto', boxShadow: 2, maxWidth: '100vw' }}>
          <Table size="small" stickyHeader sx={{ minWidth: 1200 }}>
            <TableHead>
              <TableRow>
                {columns.map(col => (
                  <TableCell key={col.id} sx={{ fontWeight: 700, background: '#f5f7fa', position: 'sticky', top: 0, zIndex: 1 }}>
                    {col.label}
                  </TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {(Array.isArray(data) ? data : []).map((row, i) => (
                <TableRow key={row.date + '-' + i} hover sx={{ '&:hover': { background: '#f0f4ff' } }}>
                  {columns.map(col => (
                    <TableCell key={col.id} align={typeof row[col.id] === 'number' ? 'right' : 'left'} sx={{ whiteSpace: 'nowrap', maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', color: getIndicatorColor(getTechStatus(col.id, row[col.id]).color) }}>
                      <Box display="flex" alignItems="center" gap={1}>
                        {getTechStatus(col.id, row[col.id]).icon}
                        <Typography variant="body2" fontWeight="bold">
                          {col.format ? col.format(row[col.id]) : (row[col.id] !== undefined && row[col.id] !== null ? formatNumber(row[col.id]) : 'N/A')}
                        </Typography>
                        {getTechStatus(col.id, row[col.id]).label && (
                          <Chip 
                            label={getTechStatus(col.id, row[col.id]).label} 
                            size="small" 
                            sx={{ ml: 0.5 }} 
                            color={getMuiChipColor(getTechStatus(col.id, row[col.id]).color)}
                          />
                        )}
                      </Box>
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <TablePagination
            component="div"
            count={total}
            page={page}
            onPageChange={handlePageChange}
            rowsPerPage={rowsPerPage}
            onRowsPerPageChange={handleRowsPerPageChange}
            rowsPerPageOptions={[10, 25, 50, 100]}
          />
          <Box display="flex" justifyContent="center" mt={2}>
            {data.length < total && (
              <Button variant="contained" onClick={handleLoadMore} disabled={loading}>
                {loading ? 'Loading...' : 'Load More'}
              </Button>
            )}
          </Box>
        </Paper>
      )}
    </Container>
  );
}

export default TechnicalHistory;
