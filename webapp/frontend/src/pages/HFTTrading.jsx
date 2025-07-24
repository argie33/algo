/**
 * HFT Trading Dashboard - Award-Winning High Frequency Trading Interface
 * Real-time monitoring, strategy management, and performance analytics
 */

import React, { useState, useEffect, useRef } from 'react';
import { 
  Chart as ChartJS, 
  CategoryScale, 
  LinearScale, 
  PointElement, 
  LineElement, 
  Title, 
  Tooltip, 
  Legend,
  Filler 
} from 'chart.js';
import { Line } from 'react-chartjs-2';
import hftEngine from '../services/hftEngine.js';
import liveDataService from '../services/liveDataService.js';

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler
);

const HFTTrading = () => {
  // State management
  const [isEngineRunning, setIsEngineRunning] = useState(false);
  const [metrics, setMetrics] = useState({
    totalTrades: 0,
    profitableTrades: 0,
    totalPnL: 0,
    winRate: 0,
    dailyPnL: 0,
    openPositions: 0,
    signalsGenerated: 0,
    avgExecutionTime: 0,
    uptime: 0
  });
  const [strategies, setStrategies] = useState([]);
  const [positions, setPositions] = useState([]);
  const [recentTrades, setRecentTrades] = useState([]);
  const [performanceData, setPerformanceData] = useState({ labels: [], data: [] });
  const [selectedStrategy, setSelectedStrategy] = useState('scalping');
  const [strategyParams, setStrategyParams] = useState({});
  const [connectionStatus, setConnectionStatus] = useState('disconnected');
  const [marketData, setMarketData] = useState(new Map());
  
  // Refs for real-time updates
  const metricsIntervalRef = useRef();
  const performanceHistoryRef = useRef([]);
  
  // Initialize component
  useEffect(() => {
    loadInitialData();
    setupRealtimeUpdates();
    
    return () => {
      clearInterval(metricsIntervalRef.current);
    };
  }, []);

  const loadInitialData = async () => {
    try {
      // Load strategies
      const strategiesData = hftEngine.getStrategies();
      setStrategies(strategiesData);
      
      // Load initial metrics
      const metricsData = hftEngine.getMetrics();
      setMetrics(metricsData);
      setIsEngineRunning(metricsData.isRunning);
      
      // Set initial strategy params
      if (strategiesData.length > 0) {
        setStrategyParams(strategiesData[0].params || {});
      }
      
      // Check connection status
      setConnectionStatus(liveDataService.getConnectionStatus().toLowerCase());
      
    } catch (error) {
      console.error('Failed to load initial data:', error);
    }
  };

  const setupRealtimeUpdates = () => {
    // Update metrics every second
    metricsIntervalRef.current = setInterval(() => {
      const currentMetrics = hftEngine.getMetrics();
      setMetrics(currentMetrics);
      setPositions(currentMetrics.activePositions || []);
      
      // Update performance chart data
      updatePerformanceChart(currentMetrics);
    }, 1000);
    
    // Listen to live data service events
    liveDataService.on('connected', () => setConnectionStatus('connected'));
    liveDataService.on('disconnected', () => setConnectionStatus('disconnected'));
    liveDataService.on('marketData', handleMarketData);
  };

  const handleMarketData = (data) => {
    setMarketData(prev => new Map(prev.set(data.symbol, data.data)));
  };

  const updatePerformanceChart = (currentMetrics) => {
    const now = new Date();
    const timeLabel = now.toLocaleTimeString();
    
    performanceHistoryRef.current.push({
      time: timeLabel,
      pnl: currentMetrics.totalPnL || 0,
      timestamp: now.getTime()
    });
    
    // Keep only last 50 data points
    if (performanceHistoryRef.current.length > 50) {
      performanceHistoryRef.current.shift();
    }
    
    setPerformanceData({
      labels: performanceHistoryRef.current.map(d => d.time),
      data: performanceHistoryRef.current.map(d => d.pnl)
    });
  };

  const handleStartEngine = async () => {
    try {
      const result = await hftEngine.start([selectedStrategy]);
      if (result.success) {
        setIsEngineRunning(true);
        console.log('✅ HFT Engine started successfully');
      } else {
        console.error('❌ Failed to start HFT Engine:', result.error);
      }
    } catch (error) {
      console.error('❌ Error starting HFT Engine:', error);
    }
  };

  const handleStopEngine = async () => {
    try {
      const result = await hftEngine.stop();
      if (result.success) {
        setIsEngineRunning(false);
        console.log('✅ HFT Engine stopped successfully');
      } else {
        console.error('❌ Failed to stop HFT Engine:', result.error);
      }
    } catch (error) {
      console.error('❌ Error stopping HFT Engine:', error);
    }
  };

  const handleStrategyUpdate = () => {
    const result = hftEngine.updateStrategy(selectedStrategy, {
      params: strategyParams,
      enabled: true
    });
    
    if (result.success) {
      console.log('✅ Strategy updated successfully');
      setStrategies(hftEngine.getStrategies());
    }
  };

  // Chart configuration
  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        display: false
      },
      title: {
        display: true,
        text: 'Real-Time P&L Performance',
        color: '#ffffff',
        font: { size: 14 }
      }
    },
    scales: {
      x: {
        grid: { color: '#374151' },
        ticks: { color: '#9ca3af' }
      },
      y: {
        grid: { color: '#374151' },
        ticks: { 
          color: '#9ca3af',
          callback: (value) => `$${value.toFixed(2)}`
        }
      }
    },
    elements: {
      line: {
        tension: 0.4
      }
    },
    animation: {
      duration: 0 // Disable animation for real-time updates
    }
  };

  const chartData = {
    labels: performanceData.labels,
    datasets: [
      {
        label: 'P&L',
        data: performanceData.data,
        borderColor: performanceData.data.length > 0 && performanceData.data[performanceData.data.length - 1] >= 0 
          ? '#10b981' : '#ef4444',
        backgroundColor: performanceData.data.length > 0 && performanceData.data[performanceData.data.length - 1] >= 0 
          ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.1)',
        fill: true,
        borderWidth: 2,
        pointRadius: 1,
        pointHoverRadius: 4
      }
    ]
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'connected': return 'text-green-400';
      case 'connecting': return 'text-yellow-400';
      default: return 'text-red-400';
    }
  };

  const formatCurrency = (value) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2
    }).format(value);
  };

  const formatPercentage = (value) => {
    return `${value.toFixed(1)}%`;
  };

  const formatTime = (ms) => {
    const seconds = Math.floor(ms / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);
    
    if (hours > 0) {
      return `${hours}h ${minutes % 60}m`;
    } else if (minutes > 0) {
      return `${minutes}m ${seconds % 60}s`;
    } else {
      return `${seconds}s`;
    }
  };

  return (
    <div className="min-h-screen bg-gray-900 text-white p-6">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-3xl font-bold bg-gradient-to-r from-blue-400 to-purple-500 bg-clip-text text-transparent">
              HFT Trading Dashboard
            </h1>
            <p className="text-gray-400 mt-1">High Frequency Trading • Real-time Strategy Execution</p>
          </div>
          
          <div className="flex items-center space-x-4">
            <div className="flex items-center space-x-2">
              <div className={`w-3 h-3 rounded-full ${connectionStatus === 'connected' ? 'bg-green-400' : 'bg-red-400'} animate-pulse`}></div>
              <span className={`text-sm ${getStatusColor(connectionStatus)}`}>
                {connectionStatus.toUpperCase()}
              </span>
            </div>
            
            {isEngineRunning ? (
              <button
                onClick={handleStopEngine}
                className="bg-red-600 hover:bg-red-700 px-6 py-2 rounded-lg font-semibold transition-colors"
              >
                🛑 Stop Engine
              </button>
            ) : (
              <button
                onClick={handleStartEngine}
                className="bg-green-600 hover:bg-green-700 px-6 py-2 rounded-lg font-semibold transition-colors"
                disabled={connectionStatus !== 'connected'}
              >
                🚀 Start Engine
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Key Metrics Dashboard */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4 mb-8">
        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
          <div className="text-2xl font-bold text-blue-400">{formatCurrency(metrics.totalPnL)}</div>
          <div className="text-sm text-gray-400">Total P&L</div>
        </div>
        
        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
          <div className="text-2xl font-bold text-green-400">{formatCurrency(metrics.dailyPnL)}</div>
          <div className="text-sm text-gray-400">Daily P&L</div>
        </div>
        
        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
          <div className="text-2xl font-bold text-purple-400">{metrics.totalTrades}</div>
          <div className="text-sm text-gray-400">Total Trades</div>
        </div>
        
        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
          <div className="text-2xl font-bold text-yellow-400">{formatPercentage(metrics.winRate || 0)}</div>
          <div className="text-sm text-gray-400">Win Rate</div>
        </div>
        
        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
          <div className="text-2xl font-bold text-orange-400">{metrics.openPositions}</div>
          <div className="text-sm text-gray-400">Open Positions</div>
        </div>
        
        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
          <div className="text-2xl font-bold text-cyan-400">{metrics.avgExecutionTime?.toFixed(0) || 0}ms</div>
          <div className="text-sm text-gray-400">Avg Execution</div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
        {/* Performance Chart */}
        <div className="lg:col-span-2 bg-gray-800 rounded-lg p-6 border border-gray-700">
          <div className="h-80">
            <Line data={chartData} options={chartOptions} />
          </div>
        </div>

        {/* Strategy Controls */}
        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <h3 className="text-xl font-semibold mb-4 text-white">Strategy Configuration</h3>
          
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">Active Strategy</label>
              <select
                value={selectedStrategy}
                onChange={(e) => setSelectedStrategy(e.target.value)}
                className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white"
              >
                {strategies.map((strategy) => (
                  <option key={strategy.name} value={strategy.name}>
                    {strategy.name.charAt(0).toUpperCase() + strategy.name.slice(1)}
                  </option>
                ))}
              </select>
            </div>

            {selectedStrategy === 'scalping' && (
              <div className="space-y-3">
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-1">Min Spread (%)</label>
                  <input
                    type="number"
                    step="0.001"
                    value={strategyParams.minSpread || 0.001}
                    onChange={(e) => setStrategyParams(prev => ({ ...prev, minSpread: parseFloat(e.target.value) }))}
                    className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white"
                  />
                </div>
                
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-1">Max Spread (%)</label>
                  <input
                    type="number"
                    step="0.001"
                    value={strategyParams.maxSpread || 0.005}
                    onChange={(e) => setStrategyParams(prev => ({ ...prev, maxSpread: parseFloat(e.target.value) }))}
                    className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white"
                  />
                </div>
                
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-1">Volume Threshold</label>
                  <input
                    type="number"
                    value={strategyParams.volume_threshold || 1000}
                    onChange={(e) => setStrategyParams(prev => ({ ...prev, volume_threshold: parseInt(e.target.value) }))}
                    className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white"
                  />
                </div>
              </div>
            )}

            <button
              onClick={handleStrategyUpdate}
              className="w-full bg-blue-600 hover:bg-blue-700 py-2 px-4 rounded-lg font-semibold transition-colors"
            >
              Update Strategy
            </button>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Active Positions */}
        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <h3 className="text-xl font-semibold mb-4 text-white">Active Positions</h3>
          
          {positions.length > 0 ? (
            <div className="space-y-3">
              {positions.map((position, index) => (
                <div key={index} className="bg-gray-700 rounded-lg p-4 border border-gray-600">
                  <div className="flex justify-between items-start mb-2">
                    <div>
                      <div className="font-semibold text-white">{position.symbol}</div>
                      <div className="text-sm text-gray-400">{position.strategy}</div>
                    </div>
                    <div className="text-right">
                      <div className="font-semibold text-green-400">{position.type}</div>
                      <div className="text-sm text-gray-400">{position.quantity} units</div>
                    </div>
                  </div>
                  
                  <div className="grid grid-cols-2 gap-4 text-sm">
                    <div>
                      <span className="text-gray-400">Entry:</span>
                      <span className="text-white ml-2">{formatCurrency(position.avgPrice)}</span>
                    </div>
                    <div>
                      <span className="text-gray-400">Current:</span>
                      <span className="text-white ml-2">
                        {formatCurrency(marketData.get(position.symbol)?.price || position.avgPrice)}
                      </span>
                    </div>
                    {position.stopLoss && (
                      <div>
                        <span className="text-gray-400">Stop Loss:</span>
                        <span className="text-red-400 ml-2">{formatCurrency(position.stopLoss)}</span>
                      </div>
                    )}
                    {position.takeProfit && (
                      <div>
                        <span className="text-gray-400">Take Profit:</span>
                        <span className="text-green-400 ml-2">{formatCurrency(position.takeProfit)}</span>
                      </div>
                    )}
                  </div>
                  
                  <div className="mt-3 text-xs text-gray-400">
                    Opened: {new Date(position.openTime).toLocaleTimeString()}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center text-gray-400 py-8">
              No active positions
            </div>
          )}
        </div>

        {/* System Status */}
        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <h3 className="text-xl font-semibold mb-4 text-white">System Status</h3>
          
          <div className="space-y-4">
            <div className="flex justify-between items-center py-2 border-b border-gray-700">
              <span className="text-gray-400">Engine Status</span>
              <span className={`font-semibold ${isEngineRunning ? 'text-green-400' : 'text-red-400'}`}>
                {isEngineRunning ? '🟢 RUNNING' : '🔴 STOPPED'}
              </span>
            </div>
            
            <div className="flex justify-between items-center py-2 border-b border-gray-700">
              <span className="text-gray-400">Uptime</span>
              <span className="text-white">{formatTime(metrics.uptime || 0)}</span>
            </div>
            
            <div className="flex justify-between items-center py-2 border-b border-gray-700">
              <span className="text-gray-400">Signals Generated</span>
              <span className="text-white">{metrics.signalsGenerated}</span>
            </div>
            
            <div className="flex justify-between items-center py-2 border-b border-gray-700">
              <span className="text-gray-400">Orders Executed</span>
              <span className="text-white">{metrics.ordersExecuted || 0}</span>
            </div>
            
            <div className="flex justify-between items-center py-2 border-b border-gray-700">
              <span className="text-gray-400">Connection Quality</span>
              <span className="text-green-400">
                {connectionStatus === 'connected' ? 'EXCELLENT' : 'POOR'}
              </span>
            </div>
          </div>

          {/* Risk Metrics */}
          <div className="mt-6">
            <h4 className="text-lg font-semibold mb-3 text-gray-300">Risk Management</h4>
            
            <div className="space-y-3">
              <div>
                <div className="flex justify-between text-sm mb-1">
                  <span className="text-gray-400">Daily Loss Limit</span>
                  <span className="text-white">
                    {formatCurrency(Math.abs(metrics.dailyPnL || 0))} / {formatCurrency(500)}
                  </span>
                </div>
                <div className="w-full bg-gray-700 rounded-full h-2">
                  <div 
                    className="bg-red-400 h-2 rounded-full transition-all duration-300"
                    style={{ width: `${Math.min(100, (Math.abs(metrics.dailyPnL || 0) / 500) * 100)}%` }}
                  ></div>
                </div>
              </div>
              
              <div>
                <div className="flex justify-between text-sm mb-1">
                  <span className="text-gray-400">Open Positions</span>
                  <span className="text-white">{metrics.openPositions} / 5</span>
                </div>
                <div className="w-full bg-gray-700 rounded-full h-2">
                  <div 
                    className="bg-blue-400 h-2 rounded-full transition-all duration-300"
                    style={{ width: `${Math.min(100, (metrics.openPositions / 5) * 100)}%` }}
                  ></div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default HFTTrading;