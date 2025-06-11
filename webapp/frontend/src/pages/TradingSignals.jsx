import React from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Grid,
  Card,
  CardContent,
  Typography,
  Box,
  Chip,
  LinearProgress,
  Alert,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tabs,
  Tab
} from '@mui/material'
import {
  TrendingUp,
  TrendingDown,
  Timeline,
  SignalCellularAlt
} from '@mui/icons-material'

import { getBuySignals, getSellSignals } from '../services/api'
import { formatCurrency, formatPercentage, getChangeColor } from '../utils/formatters'

function TabPanel(props) {
  const { children, value, index, ...other } = props

  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`trading-tabpanel-${index}`}
      aria-labelledby={`trading-tab-${index}`}
      {...other}
    >
      {value === index && (
        <Box sx={{ p: 3 }}>
          {children}
        </Box>
      )}
    </div>
  )
}

function TradingSignals() {
  const [tabValue, setTabValue] = React.useState(0)

  const { 
    data: buySignals, 
    isLoading: buyLoading, 
    error: buyError 
  } = useQuery({
    queryKey: ['buySignals'],
    queryFn: getBuySignals,
    refetchInterval: 5 * 60 * 1000 // Refetch every 5 minutes
  })

  const { 
    data: sellSignals, 
    isLoading: sellLoading, 
    error: sellError 
  } = useQuery({
    queryKey: ['sellSignals'],
    queryFn: getSellSignals,
    refetchInterval: 5 * 60 * 1000 // Refetch every 5 minutes
  })

  const handleTabChange = (event, newValue) => {
    setTabValue(newValue)
  }

  const renderSignalsTable = (signals, type) => {
    if (!signals || signals.length === 0) {
      return (
        <Alert severity="info">
          No {type} signals available at this time.
        </Alert>
      )
    }

    return (
      <TableContainer component={Paper}>
        <Table>
          <TableHead>
            <TableRow>
              <TableCell>Symbol</TableCell>
              <TableCell>Company</TableCell>
              <TableCell align="right">Price</TableCell>
              <TableCell align="right">Change</TableCell>
              <TableCell align="right">Signal Strength</TableCell>
              <TableCell>Timeframe</TableCell>
              <TableCell>Generated</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {signals.map((signal, index) => (
              <TableRow key={index}>
                <TableCell>
                  <Typography variant="subtitle2" fontWeight="bold">
                    {signal.symbol}
                  </Typography>
                </TableCell>
                <TableCell>{signal.company_name || 'N/A'}</TableCell>
                <TableCell align="right">
                  {formatCurrency(signal.current_price)}
                </TableCell>
                <TableCell align="right">
                  <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end' }}>
                    {signal.price_change > 0 ? <TrendingUp color="success" /> : <TrendingDown color="error" />}
                    <Typography 
                      variant="body2" 
                      color={getChangeColor(signal.price_change)}
                      sx={{ ml: 0.5 }}
                    >
                      {formatPercentage(signal.price_change)}
                    </Typography>
                  </Box>
                </TableCell>
                <TableCell align="right">
                  <Chip 
                    label={`${signal.signal_strength}%`}
                    color={signal.signal_strength > 75 ? 'success' : signal.signal_strength > 50 ? 'warning' : 'default'}
                    size="small"
                  />
                </TableCell>
                <TableCell>
                  <Chip 
                    label={signal.timeframe || 'Daily'}
                    variant="outlined"
                    size="small"
                  />
                </TableCell>
                <TableCell>
                  <Typography variant="caption">
                    {new Date(signal.created_at).toLocaleString()}
                  </Typography>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    )
  }

  if (buyError || sellError) {
    return (
      <Alert severity="error">
        Error loading trading signals: {buyError?.message || sellError?.message}
      </Alert>
    )
  }

  return (
    <Box sx={{ width: '100%' }}>
      <Typography variant="h4" gutterBottom sx={{ display: 'flex', alignItems: 'center' }}>
        <Timeline sx={{ mr: 2 }} />
        Trading Signals
      </Typography>
      
      <Grid container spacing={3} sx={{ mb: 3 }}>
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                <TrendingUp color="success" sx={{ mr: 1 }} />
                <Typography variant="h6">Buy Signals</Typography>
              </Box>
              <Typography variant="h3" color="success.main">
                {buySignals?.length || 0}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Active buy opportunities
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                <TrendingDown color="error" sx={{ mr: 1 }} />
                <Typography variant="h6">Sell Signals</Typography>
              </Box>
              <Typography variant="h3" color="error.main">
                {sellSignals?.length || 0}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Active sell recommendations
              </Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      <Paper sx={{ width: '100%' }}>
        <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
          <Tabs value={tabValue} onChange={handleTabChange}>
            <Tab 
              label={
                <Box sx={{ display: 'flex', alignItems: 'center' }}>
                  <TrendingUp sx={{ mr: 1 }} />
                  Buy Signals ({buySignals?.length || 0})
                </Box>
              } 
            />
            <Tab 
              label={
                <Box sx={{ display: 'flex', alignItems: 'center' }}>
                  <TrendingDown sx={{ mr: 1 }} />
                  Sell Signals ({sellSignals?.length || 0})
                </Box>
              } 
            />
          </Tabs>
        </Box>
        
        <TabPanel value={tabValue} index={0}>
          {buyLoading ? (
            <LinearProgress />
          ) : (
            renderSignalsTable(buySignals, 'buy')
          )}
        </TabPanel>
        
        <TabPanel value={tabValue} index={1}>
          {sellLoading ? (
            <LinearProgress />
          ) : (
            renderSignalsTable(sellSignals, 'sell')
          )}
        </TabPanel>
      </Paper>
    </Box>
  )
}

export default TradingSignals