import React, { useState, useEffect } from 'react'
import {
  Box,
  Typography,
  Grid,
  Card,
  CardContent,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Chip,
  CircularProgress,
  Alert,
  TextField,
  Button
} from '@mui/material'
import { apiService } from '../services/api'

function TechnicalAnalysis() {
  const [timeframe, setTimeframe] = useState('daily')
  const [technicalData, setTechnicalData] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [symbolFilter, setSymbolFilter] = useState('')

  useEffect(() => {
    fetchTechnicalData()
  }, [timeframe])

  const fetchTechnicalData = async () => {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams({
        limit: '50',
        ...(symbolFilter && { symbol: symbolFilter })
      })
      const response = await fetch(`${process.env.REACT_APP_API_URL || ''}/technical/${timeframe}?${params}`)
      if (!response.ok) throw new Error('Failed to fetch technical data')
      const data = await response.json()
      setTechnicalData(data.data || [])
    } catch (err) {
      setError('Failed to fetch technical data')
      console.error('Error fetching technical data:', err)
    } finally {
      setLoading(false)
    }
  }

  const getRSIColor = (rsi) => {
    if (rsi > 70) return 'error'
    if (rsi < 30) return 'success'
    return 'default'
  }

  const getRSILabel = (rsi) => {
    if (rsi > 70) return 'Overbought'
    if (rsi < 30) return 'Oversold'
    return 'Neutral'
  }

  const getMACDSignal = (macd, signal) => {
    if (macd > signal) return { label: 'Bullish', color: 'success' }
    return { label: 'Bearish', color: 'error' }
  }

  const getADXStrength = (adx) => {
    if (adx > 50) return { label: 'Very Strong', color: 'success' }
    if (adx > 25) return { label: 'Strong', color: 'info' }
    if (adx > 20) return { label: 'Trending', color: 'warning' }
    return { label: 'Weak', color: 'default' }
  }

  const handleSymbolSearch = () => {
    fetchTechnicalData()
  }

  return (
    <Box>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Typography variant="h4" gutterBottom>
          Technical Analysis
        </Typography>
        
        <Box display="flex" gap={2} alignItems="center">
          <TextField
            label="Symbol"
            variant="outlined"
            size="small"
            value={symbolFilter}
            onChange={(e) => setSymbolFilter(e.target.value.toUpperCase())}
            placeholder="e.g., AAPL"
          />
          <Button variant="contained" onClick={handleSymbolSearch}>
            Search
          </Button>
          <FormControl sx={{ minWidth: 120 }}>
            <InputLabel>Timeframe</InputLabel>
            <Select
              value={timeframe}
              label="Timeframe"
              onChange={(e) => setTimeframe(e.target.value)}
            >
              <MenuItem value="daily">Daily</MenuItem>
              <MenuItem value="weekly">Weekly</MenuItem>
              <MenuItem value="monthly">Monthly</MenuItem>
            </Select>
          </FormControl>
        </Box>
      </Box>

      {loading && (
        <Box display="flex" justifyContent="center" p={4}>
          <CircularProgress />
        </Box>
      )}
      
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {!loading && !error && (
        <Grid container spacing={3}>
          <Grid item xs={12}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Technical Indicators - {timeframe.charAt(0).toUpperCase() + timeframe.slice(1)}
                </Typography>
                
                {technicalData.length === 0 ? (
                  <Alert severity="info">No technical data found</Alert>
                ) : (
                  <TableContainer component={Paper} sx={{ mt: 2 }}>
                    <Table>
                      <TableHead>
                        <TableRow>
                          <TableCell>Symbol</TableCell>
                          <TableCell>Date</TableCell>
                          <TableCell>RSI (14)</TableCell>
                          <TableCell>MACD</TableCell>
                          <TableCell>ADX</TableCell>
                          <TableCell>MFI</TableCell>
                          <TableCell>SMA 20</TableCell>
                          <TableCell>SMA 50</TableCell>
                          <TableCell>BB Upper</TableCell>
                          <TableCell>BB Lower</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {technicalData.map((row, index) => (
                          <TableRow key={index}>
                            <TableCell>
                              <Typography fontWeight="bold">{row.symbol}</Typography>
                            </TableCell>
                            <TableCell>
                              {new Date(row.date).toLocaleDateString()}
                            </TableCell>
                            <TableCell>
                              <Box display="flex" alignItems="center" gap={1}>
                                <Typography>{row.rsi?.toFixed(2) || 'N/A'}</Typography>
                                {row.rsi && (
                                  <Chip 
                                    label={getRSILabel(row.rsi)} 
                                    color={getRSIColor(row.rsi)} 
                                    size="small" 
                                  />
                                )}
                              </Box>
                            </TableCell>
                            <TableCell>
                              <Box>
                                <Typography variant="body2">
                                  {row.macd?.toFixed(4) || 'N/A'}
                                </Typography>
                                {row.macd && row.macd_signal && (
                                  <Chip 
                                    label={getMACDSignal(row.macd, row.macd_signal).label}
                                    color={getMACDSignal(row.macd, row.macd_signal).color}
                                    size="small"
                                  />
                                )}
                              </Box>
                            </TableCell>
                            <TableCell>
                              <Box display="flex" alignItems="center" gap={1}>
                                <Typography>{row.adx?.toFixed(2) || 'N/A'}</Typography>
                                {row.adx && (
                                  <Chip 
                                    label={getADXStrength(row.adx).label}
                                    color={getADXStrength(row.adx).color}
                                    size="small"
                                  />
                                )}
                              </Box>
                            </TableCell>
                            <TableCell>{row.mfi?.toFixed(2) || 'N/A'}</TableCell>
                            <TableCell>${row.sma_20?.toFixed(2) || 'N/A'}</TableCell>
                            <TableCell>${row.sma_50?.toFixed(2) || 'N/A'}</TableCell>
                            <TableCell>${row.bbands_upper?.toFixed(2) || 'N/A'}</TableCell>
                            <TableCell>${row.bbands_lower?.toFixed(2) || 'N/A'}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </TableContainer>
                )}
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      )}
    </Box>
  )
}

export default TechnicalAnalysis
