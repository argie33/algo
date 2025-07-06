import React, { useState } from 'react';
import {
  Box,
  Card,
  CardContent,
  CardHeader,
  Typography,
  Grid,
  Chip,
  Button,
  IconButton,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Alert,
  Tooltip,
  LinearProgress,
  Stack,
  Divider,
  useTheme,
  alpha
} from '@mui/material';
import {
  TrendingUp,
  TrendingDown,
  Add,
  Remove,
  Edit,
  Close,
  CheckCircle,
  Warning,
  Info,
  ShowChart,
  AttachMoney,
  Calculate,
  ExitToApp
} from '@mui/icons-material';
import { formatCurrency } from '../../utils/formatters';
import ExitZoneVisualizer from './ExitZoneVisualizer';

const PositionManager = ({ positions = [], onUpdatePosition, onClosePosition }) => {
  const theme = useTheme();
  const [selectedPosition, setSelectedPosition] = useState(null);
  const [exitDialog, setExitDialog] = useState(false);
  const [exitZone, setExitZone] = useState('');
  const [exitPercentage, setExitPercentage] = useState(25);
  const [customExitPrice, setCustomExitPrice] = useState('');

  const calculatePositionMetrics = (position) => {
    const currentValue = position.shares * position.current_price;
    const costBasis = position.shares * position.entry_price;
    const unrealizedGain = currentValue - costBasis;
    const unrealizedGainPct = (unrealizedGain / costBasis) * 100;
    const daysHeld = Math.floor((new Date() - new Date(position.entry_date)) / (1000 * 60 * 60 * 24));
    
    return {
      currentValue,
      costBasis,
      unrealizedGain,
      unrealizedGainPct,
      daysHeld
    };
  };

  const getPositionStatus = (position) => {
    const metrics = calculatePositionMetrics(position);
    
    if (metrics.unrealizedGainPct >= 20) {
      return { status: 'WINNING', color: theme.palette.success.main, icon: <TrendingUp /> };
    } else if (metrics.unrealizedGainPct <= -7) {
      return { status: 'STOP LOSS', color: theme.palette.error.main, icon: <Warning /> };
    } else if (metrics.unrealizedGainPct > 0) {
      return { status: 'PROFITABLE', color: theme.palette.info.main, icon: <TrendingUp /> };
    } else {
      return { status: 'UNDERWATER', color: theme.palette.warning.main, icon: <TrendingDown /> };
    }
  };

  const handleExitPosition = () => {
    if (!selectedPosition || !exitZone) return;

    const exitData = {
      positionId: selectedPosition.id,
      exitZone: exitZone,
      exitPercentage: exitPercentage,
      exitPrice: customExitPrice || selectedPosition.current_price,
      exitDate: new Date().toISOString()
    };

    onClosePosition(exitData);
    setExitDialog(false);
    setSelectedPosition(null);
    setExitZone('');
    setExitPercentage(25);
    setCustomExitPrice('');
  };

  const getExitProgress = (position) => {
    let progress = 0;
    if (position.exit_1_completed) progress += 25;
    if (position.exit_2_completed) progress += 25;
    if (position.exit_3_completed) progress += 25;
    if (position.exit_4_completed) progress += 25;
    return progress;
  };

  return (
    <>
      <Card>
        <CardHeader 
          title="Active Positions"
          subheader="Manage your swing trading positions with O'Neill exit zones"
          action={
            <Chip 
              label={`${positions.length} Active`}
              color="primary"
              size="small"
            />
          }
        />
        <CardContent>
          {positions.length === 0 ? (
            <Alert severity="info">
              No active positions. Look for buy signals to enter new positions.
            </Alert>
          ) : (
            <TableContainer component={Paper} variant="outlined">
              <Table>
                <TableHead>
                  <TableRow>
                    <TableCell>Symbol</TableCell>
                    <TableCell>Entry</TableCell>
                    <TableCell>Current</TableCell>
                    <TableCell>Gain/Loss</TableCell>
                    <TableCell>Exit Progress</TableCell>
                    <TableCell>Status</TableCell>
                    <TableCell>Days Held</TableCell>
                    <TableCell align="right">Actions</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {positions.map((position) => {
                    const metrics = calculatePositionMetrics(position);
                    const status = getPositionStatus(position);
                    const exitProgress = getExitProgress(position);
                    
                    return (
                      <TableRow key={position.id} hover>
                        <TableCell>
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                            <Typography variant="subtitle2" fontWeight={600}>
                              {position.symbol}
                            </Typography>
                            <Chip 
                              label={`${position.shares} shares`}
                              size="small"
                              variant="outlined"
                            />
                          </Box>
                        </TableCell>
                        <TableCell>
                          <Typography variant="body2">
                            {formatCurrency(position.entry_price)}
                          </Typography>
                          <Typography variant="caption" color="text.secondary">
                            {new Date(position.entry_date).toLocaleDateString()}
                          </Typography>
                        </TableCell>
                        <TableCell>
                          <Typography variant="body2" fontWeight={600}>
                            {formatCurrency(position.current_price)}
                          </Typography>
                        </TableCell>
                        <TableCell>
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                            <Typography 
                              variant="body2" 
                              fontWeight={600}
                              color={metrics.unrealizedGainPct >= 0 ? 'success.main' : 'error.main'}
                            >
                              {metrics.unrealizedGainPct >= 0 ? '+' : ''}{metrics.unrealizedGainPct.toFixed(2)}%
                            </Typography>
                            <Typography variant="caption" color="text.secondary">
                              ({formatCurrency(metrics.unrealizedGain)})
                            </Typography>
                          </Box>
                        </TableCell>
                        <TableCell>
                          <Box sx={{ width: 120 }}>
                            <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                              <Typography variant="caption">Exit Progress</Typography>
                              <Typography variant="caption" fontWeight={600}>
                                {exitProgress}%
                              </Typography>
                            </Box>
                            <LinearProgress 
                              variant="determinate" 
                              value={exitProgress}
                              sx={{ 
                                height: 6, 
                                borderRadius: 3,
                                backgroundColor: alpha(theme.palette.primary.main, 0.1)
                              }}
                            />
                          </Box>
                        </TableCell>
                        <TableCell>
                          <Chip
                            icon={status.icon}
                            label={status.status}
                            size="small"
                            sx={{
                              backgroundColor: alpha(status.color, 0.1),
                              color: status.color,
                              border: `1px solid ${alpha(status.color, 0.3)}`,
                              '& .MuiChip-icon': {
                                color: status.color
                              }
                            }}
                          />
                        </TableCell>
                        <TableCell>
                          <Typography variant="body2">
                            {metrics.daysHeld} days
                          </Typography>
                        </TableCell>
                        <TableCell align="right">
                          <Stack direction="row" spacing={1} justifyContent="flex-end">
                            <Tooltip title="View Details">
                              <IconButton 
                                size="small"
                                onClick={() => setSelectedPosition(position)}
                              >
                                <ShowChart />
                              </IconButton>
                            </Tooltip>
                            <Tooltip title="Exit Position">
                              <IconButton 
                                size="small"
                                color="primary"
                                onClick={() => {
                                  setSelectedPosition(position);
                                  setExitDialog(true);
                                }}
                              >
                                <ExitToApp />
                              </IconButton>
                            </Tooltip>
                          </Stack>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </TableContainer>
          )}

          {/* Portfolio Summary */}
          <Box sx={{ mt: 3, p: 2, backgroundColor: alpha(theme.palette.primary.main, 0.05), borderRadius: 1 }}>
            <Grid container spacing={3}>
              <Grid item xs={12} sm={3}>
                <Typography variant="caption" color="text.secondary">Total Value</Typography>
                <Typography variant="h6" fontWeight={600}>
                  {formatCurrency(positions.reduce((sum, p) => sum + (p.shares * p.current_price), 0))}
                </Typography>
              </Grid>
              <Grid item xs={12} sm={3}>
                <Typography variant="caption" color="text.secondary">Total Cost Basis</Typography>
                <Typography variant="h6" fontWeight={600}>
                  {formatCurrency(positions.reduce((sum, p) => sum + (p.shares * p.entry_price), 0))}
                </Typography>
              </Grid>
              <Grid item xs={12} sm={3}>
                <Typography variant="caption" color="text.secondary">Unrealized Gain</Typography>
                <Typography 
                  variant="h6" 
                  fontWeight={600}
                  color={positions.reduce((sum, p) => sum + ((p.shares * p.current_price) - (p.shares * p.entry_price)), 0) >= 0 ? 'success.main' : 'error.main'}
                >
                  {formatCurrency(positions.reduce((sum, p) => sum + ((p.shares * p.current_price) - (p.shares * p.entry_price)), 0))}
                </Typography>
              </Grid>
              <Grid item xs={12} sm={3}>
                <Typography variant="caption" color="text.secondary">Win Rate</Typography>
                <Typography variant="h6" fontWeight={600}>
                  {positions.length > 0 
                    ? `${((positions.filter(p => p.current_price > p.entry_price).length / positions.length) * 100).toFixed(0)}%`
                    : '0%'
                  }
                </Typography>
              </Grid>
            </Grid>
          </Box>
        </CardContent>
      </Card>

      {/* Position Details Dialog */}
      {selectedPosition && !exitDialog && (
        <Dialog 
          open={Boolean(selectedPosition) && !exitDialog} 
          onClose={() => setSelectedPosition(null)}
          maxWidth="md"
          fullWidth
        >
          <DialogTitle>
            <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <Typography variant="h6">{selectedPosition.symbol} Position Details</Typography>
              <IconButton onClick={() => setSelectedPosition(null)}>
                <Close />
              </IconButton>
            </Box>
          </DialogTitle>
          <DialogContent dividers>
            <ExitZoneVisualizer 
              signal={selectedPosition}
              currentPrice={selectedPosition.current_price}
              entryPrice={selectedPosition.entry_price}
            />
          </DialogContent>
        </Dialog>
      )}

      {/* Exit Position Dialog */}
      <Dialog 
        open={exitDialog} 
        onClose={() => setExitDialog(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Exit Position - {selectedPosition?.symbol}</DialogTitle>
        <DialogContent dividers>
          <Stack spacing={3}>
            <Alert severity="info">
              Following O'Neill's methodology, consider taking partial profits at key levels.
            </Alert>

            <FormControl fullWidth>
              <InputLabel>Exit Zone</InputLabel>
              <Select
                value={exitZone}
                onChange={(e) => setExitZone(e.target.value)}
                label="Exit Zone"
              >
                <MenuItem value="zone1">Zone 1 - 20% Profit Target</MenuItem>
                <MenuItem value="zone2">Zone 2 - 25% Profit Target</MenuItem>
                <MenuItem value="zone3">Zone 3 - 21 EMA Breach</MenuItem>
                <MenuItem value="zone4">Zone 4 - 50 SMA Breach</MenuItem>
                <MenuItem value="stoploss">Stop Loss - 7% Loss</MenuItem>
                <MenuItem value="custom">Custom Exit</MenuItem>
              </Select>
            </FormControl>

            <TextField
              label="Percentage to Sell"
              type="number"
              value={exitPercentage}
              onChange={(e) => setExitPercentage(Number(e.target.value))}
              InputProps={{
                endAdornment: '%',
                inputProps: { min: 1, max: 100 }
              }}
              fullWidth
            />

            {exitZone === 'custom' && (
              <TextField
                label="Exit Price"
                type="number"
                value={customExitPrice}
                onChange={(e) => setCustomExitPrice(e.target.value)}
                InputProps={{
                  startAdornment: '$',
                  inputProps: { step: 0.01 }
                }}
                fullWidth
              />
            )}

            {selectedPosition && (
              <Box sx={{ p: 2, backgroundColor: alpha(theme.palette.grey[500], 0.1), borderRadius: 1 }}>
                <Typography variant="body2" gutterBottom>
                  Exit Summary:
                </Typography>
                <Typography variant="body2">
                  Shares to sell: {Math.floor(selectedPosition.shares * (exitPercentage / 100))}
                </Typography>
                <Typography variant="body2">
                  Exit price: {formatCurrency(customExitPrice || selectedPosition.current_price)}
                </Typography>
                <Typography variant="body2" fontWeight={600}>
                  Proceeds: {formatCurrency(
                    Math.floor(selectedPosition.shares * (exitPercentage / 100)) * 
                    (customExitPrice || selectedPosition.current_price)
                  )}
                </Typography>
              </Box>
            )}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setExitDialog(false)}>Cancel</Button>
          <Button 
            onClick={handleExitPosition} 
            variant="contained" 
            color="primary"
            disabled={!exitZone}
          >
            Execute Exit
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
};

export default PositionManager;