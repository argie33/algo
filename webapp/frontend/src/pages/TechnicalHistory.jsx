import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { getTechnicalData } from '../services/api';
import {
  Container, Typography, Box, Table, TableHead, TableRow, TableCell, TableBody, TablePagination, Paper, TextField, Button, CircularProgress, Alert, Divider
} from '@mui/material';

function TechnicalHistory() {
  const { symbol } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(25);
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [total, setTotal] = useState(0);

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

  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      <Button variant="outlined" onClick={() => navigate(-1)} sx={{ mb: 2 }}>Back</Button>
      <Typography variant="h4" gutterBottom>Technical History for {symbol}</Typography>
      <Divider sx={{ mb: 2 }} />
      <Box display="flex" gap={2} mb={2}>
        <TextField label="Date From" type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} size="small" InputLabelProps={{ shrink: true }} />
        <TextField label="Date To" type="date" value={dateTo} onChange={e => setDateTo(e.target.value)} size="small" InputLabelProps={{ shrink: true }} />
        <Button variant="contained" onClick={() => { setPage(0); fetchData(); }}>Apply</Button>
      </Box>
      {loading ? (
        <Box display="flex" alignItems="center" justifyContent="center" minHeight={120}><CircularProgress /></Box>
      ) : error ? (
        <Alert severity="error">{error}</Alert>
      ) : (
        <Paper>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Date</TableCell>
                <TableCell>RSI</TableCell>
                <TableCell>MACD</TableCell>
                <TableCell>MACD Signal</TableCell>
                <TableCell>MACD Hist</TableCell>
                <TableCell>ADX</TableCell>
                <TableCell>ATR</TableCell>
                <TableCell>MFI</TableCell>
                <TableCell>ROC</TableCell>
                <TableCell>MOM</TableCell>
                <TableCell>BB Upper</TableCell>
                <TableCell>BB Middle</TableCell>
                <TableCell>BB Lower</TableCell>
                <TableCell>SMA 10</TableCell>
                <TableCell>SMA 20</TableCell>
                <TableCell>SMA 50</TableCell>
                <TableCell>SMA 150</TableCell>
                <TableCell>SMA 200</TableCell>
                <TableCell>EMA 4</TableCell>
                <TableCell>EMA 9</TableCell>
                <TableCell>EMA 21</TableCell>
                <TableCell>A/D</TableCell>
                <TableCell>CMF</TableCell>
                <TableCell>TD Seq</TableCell>
                <TableCell>TD Combo</TableCell>
                <TableCell>MW</TableCell>
                <TableCell>DM</TableCell>
                <TableCell>Pivot H</TableCell>
                <TableCell>Pivot L</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {data.map((row, i) => (
                <TableRow key={row.date + '-' + i}>
                  <TableCell>{row.date}</TableCell>
                  <TableCell>{row.rsi}</TableCell>
                  <TableCell>{row.macd}</TableCell>
                  <TableCell>{row.macd_signal}</TableCell>
                  <TableCell>{row.macd_hist}</TableCell>
                  <TableCell>{row.adx}</TableCell>
                  <TableCell>{row.atr}</TableCell>
                  <TableCell>{row.mfi}</TableCell>
                  <TableCell>{row.roc}</TableCell>
                  <TableCell>{row.mom}</TableCell>
                  <TableCell>{row.bbands_upper}</TableCell>
                  <TableCell>{row.bbands_middle}</TableCell>
                  <TableCell>{row.bbands_lower}</TableCell>
                  <TableCell>{row.sma_10}</TableCell>
                  <TableCell>{row.sma_20}</TableCell>
                  <TableCell>{row.sma_50}</TableCell>
                  <TableCell>{row.sma_150}</TableCell>
                  <TableCell>{row.sma_200}</TableCell>
                  <TableCell>{row.ema_4}</TableCell>
                  <TableCell>{row.ema_9}</TableCell>
                  <TableCell>{row.ema_21}</TableCell>
                  <TableCell>{row.ad}</TableCell>
                  <TableCell>{row.cmf}</TableCell>
                  <TableCell>{row.td_sequential}</TableCell>
                  <TableCell>{row.td_combo}</TableCell>
                  <TableCell>{row.marketwatch}</TableCell>
                  <TableCell>{row.dm}</TableCell>
                  <TableCell>{row.pivot_high}</TableCell>
                  <TableCell>{row.pivot_low}</TableCell>
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
        </Paper>
      )}
    </Container>
  );
}

export default TechnicalHistory;
