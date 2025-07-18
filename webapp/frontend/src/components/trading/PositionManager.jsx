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
      return { status: 'WINNING', color: '#4caf50', icon: <TrendingUp /> };
    } else if (metrics.unrealizedGainPct <= -7) {
      return { status: 'STOP LOSS', color: '#f44336', icon: <Warning /> };
    } else if (metrics.unrealizedGainPct > 0) {
      return { status: 'PROFITABLE', color: '#2196f3', icon: <TrendingUp /> };
    } else {
      return { status: 'UNDERWATER', color: '#ff9800', icon: <TrendingDown /> };
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
      <div className="bg-white shadow-md rounded-lg">
        <div className="bg-white shadow-md rounded-lg"Header 
          title="Active Positions"
          subheader="Manage your swing trading positions with O'Neill exit zones"
          action={
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
              label={`${positions.length} Active`}
              color="primary"
              size="small"
            />
          }
        />
        <div className="bg-white shadow-md rounded-lg"Content>
          {positions.length === 0 ? (
            <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="info">
              No active positions. Look for buy signals to enter new positions.
            </div>
          ) : (
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer component={Paper} variant="outlined">
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leHead>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Symbol</td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Entry</td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Current</td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Gain/Loss</td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Exit Progress</td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Status</td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Days Held</td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Actions</td>
                  </tr>
                </thead>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
                  {positions.map((position) => {
                    const metrics = calculatePositionMetrics(position);
                    const status = getPositionStatus(position);
                    const exitProgress = getExitProgress(position);
                    
                    return (
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow key={position.id} hover>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                          <div  sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                            <div  variant="subtitle2" fontWeight={600}>
                              {position.symbol}
                            </div>
                            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                              label={`${position.shares} shares`}
                              size="small"
                              variant="outlined"
                            />
                          </div>
                        </td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                          <div  variant="body2">
                            {formatCurrency(position.entry_price)}
                          </div>
                          <div  variant="caption" color="text.secondary">
                            {new Date(position.entry_date).toLocaleDateString()}
                          </div>
                        </td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                          <div  variant="body2" fontWeight={600}>
                            {formatCurrency(position.current_price)}
                          </div>
                        </td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                          <div  sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                            <div  
                              variant="body2" 
                              fontWeight={600}
                              color={metrics.unrealizedGainPct >= 0 ? 'success.main' : 'error.main'}
                            >
                              {metrics.unrealizedGainPct >= 0 ? '+' : ''}{metrics.unrealizedGainPct.toFixed(2)}%
                            </div>
                            <div  variant="caption" color="text.secondary">
                              ({formatCurrency(metrics.unrealizedGain)})
                            </div>
                          </div>
                        </td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                          <div  sx={{ width: 120 }}>
                            <div  sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                              <div  variant="caption">Exit Progress</div>
                              <div  variant="caption" fontWeight={600}>
                                {exitProgress}%
                              </div>
                            </div>
                            <div className="w-full bg-gray-200 rounded-full h-2" 
                              variant="determinate" 
                              value={exitProgress}
                              sx={{ 
                                height: 6, 
                                borderRadius: 3,
                                backgroundColor: '#1976d21A'
                              }}
                            />
                          </div>
                        </td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                            icon={status.icon}
                            label={status.status}
                            size="small"
                            sx={{
                              backgroundColor: status.color + '1A',
                              color: status.color,
                              border: `1px solid ${status.color + '4D'}`,
                              '& .MuiChip-icon': {
                                color: status.color
                              }
                            }}
                          />
                        </td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                          <div  variant="body2">
                            {metrics.daysHeld} days
                          </div>
                        </td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                          <div className="flex flex-col space-y-2" direction="row" spacing={1} justifyContent="flex-end">
                            <div  title="View Details">
                              <button className="p-2 rounded-full hover:bg-gray-100" 
                                size="small"
                                onClick={() => setSelectedPosition(position)}
                              >
                                <ShowChart />
                              </button>
                            </div>
                            <div  title="Exit Position">
                              <button className="p-2 rounded-full hover:bg-gray-100" 
                                size="small"
                                color="primary"
                                onClick={() => {
                                  setSelectedPosition(position);
                                  setExitDialog(true);
                                }}
                              >
                                <ExitToApp />
                              </button>
                            </div>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {/* Portfolio Summary */}
          <div  sx={{ mt: 3, p: 2, backgroundColor: '#1976d20D', borderRadius: 1 }}>
            <div className="grid" container spacing={3}>
              <div className="grid" item xs={12} sm={3}>
                <div  variant="caption" color="text.secondary">Total Value</div>
                <div  variant="h6" fontWeight={600}>
                  {formatCurrency(positions.reduce((sum, p) => sum + (p.shares * p.current_price), 0))}
                </div>
              </div>
              <div className="grid" item xs={12} sm={3}>
                <div  variant="caption" color="text.secondary">Total Cost Basis</div>
                <div  variant="h6" fontWeight={600}>
                  {formatCurrency(positions.reduce((sum, p) => sum + (p.shares * p.entry_price), 0))}
                </div>
              </div>
              <div className="grid" item xs={12} sm={3}>
                <div  variant="caption" color="text.secondary">Unrealized Gain</div>
                <div  
                  variant="h6" 
                  fontWeight={600}
                  color={positions.reduce((sum, p) => sum + ((p.shares * p.current_price) - (p.shares * p.entry_price)), 0) >= 0 ? 'success.main' : 'error.main'}
                >
                  {formatCurrency(positions.reduce((sum, p) => sum + ((p.shares * p.current_price) - (p.shares * p.entry_price)), 0))}
                </div>
              </div>
              <div className="grid" item xs={12} sm={3}>
                <div  variant="caption" color="text.secondary">Win Rate</div>
                <div  variant="h6" fontWeight={600}>
                  {positions.length > 0 
                    ? `${((positions.filter(p => p.current_price > p.entry_price).length / positions.length) * 100).toFixed(0)}%`
                    : '0%'
                  }
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Position Details Dialog */}
      {selectedPosition && !exitDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50" 
          open={Boolean(selectedPosition) && !exitDialog} 
          onClose={() => setSelectedPosition(null)}
          maxWidth="md"
          fullWidth
        >
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Title>
            <div  sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div  variant="h6">{selectedPosition.symbol} Position Details</div>
              <button className="p-2 rounded-full hover:bg-gray-100" onClick={() => setSelectedPosition(null)}>
                <Close />
              </button>
            </div>
          </h2>
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Content dividers>
            <ExitZoneVisualizer 
              signal={selectedPosition}
              currentPrice={selectedPosition.current_price}
              entryPrice={selectedPosition.entry_price}
            />
          </div>
        </div>
      )}

      {/* Exit Position Dialog */}
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50" 
        open={exitDialog} 
        onClose={() => setExitDialog(false)}
        maxWidth="sm"
        fullWidth
      >
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Title>Exit Position - {selectedPosition?.symbol}</h2>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Content dividers>
          <div className="flex flex-col space-y-2" spacing={3}>
            <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="info">
              Following O'Neill's methodology, consider taking partial profits at key levels.
            </div>

            <div className="mb-4" fullWidth>
              <label className="block text-sm font-medium text-gray-700 mb-1">Exit Zone</label>
              <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={exitZone}
                onChange={(e) => setExitZone(e.target.value)}
                label="Exit Zone"
              >
                <option  value="zone1">Zone 1 - 20% Profit Target</option>
                <option  value="zone2">Zone 2 - 25% Profit Target</option>
                <option  value="zone3">Zone 3 - 21 EMA Breach</option>
                <option  value="zone4">Zone 4 - 50 SMA Breach</option>
                <option  value="stoploss">Stop Loss - 7% Loss</option>
                <option  value="custom">Custom Exit</option>
              </select>
            </div>

            <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
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
              <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
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
              <div  sx={{ p: 2, backgroundColor: '#9e9e9e1A', borderRadius: 1 }}>
                <div  variant="body2" gutterBottom>
                  Exit Summary:
                </div>
                <div  variant="body2">
                  Shares to sell: {Math.floor(selectedPosition.shares * (exitPercentage / 100))}
                </div>
                <div  variant="body2">
                  Exit price: {formatCurrency(customExitPrice || selectedPosition.current_price)}
                </div>
                <div  variant="body2" fontWeight={600}>
                  Proceeds: {formatCurrency(
                    Math.floor(selectedPosition.shares * (exitPercentage / 100)) * 
                    (customExitPrice || selectedPosition.current_price)
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Actions>
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" onClick={() => setExitDialog(false)}>Cancel</button>
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" 
            onClick={handleExitPosition} 
            variant="contained" 
            color="primary"
            disabled={!exitZone}
          >
            Execute Exit
          </button>
        </div>
      </div>
    </>
  );
};

export default PositionManager;