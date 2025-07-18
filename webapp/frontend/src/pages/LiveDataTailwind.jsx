import React, { useState, useEffect } from 'react';
import { Switch } from '@headlessui/react';
import {
  PlayIcon,
  StopIcon,
  Cog6ToothIcon,
  ChartBarIcon,
  ArrowRefreshIcon,
  TrendingUpIcon,
  TrendingDownIcon,
  SignalIcon,
  ExclamationTriangleIcon,
  CheckCircleIcon,
  InformationCircleIcon
} from '@heroicons/react/24/outline';

const LiveDataTailwind = () => {
  const [isStreaming, setIsStreaming] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState('disconnected');
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);

  // Mock data for demonstration
  const mockData = [
    { symbol: 'AAPL', price: 175.43, change: 2.1, changePercent: 1.21 },
    { symbol: 'GOOGL', price: 2421.33, change: -15.20, changePercent: -0.62 },
    { symbol: 'MSFT', price: 377.85, change: 4.75, changePercent: 1.27 },
    { symbol: 'TSLA', price: 248.42, change: -8.33, changePercent: -3.24 }
  ];

  useEffect(() => {
    // Simulate connection status
    if (isStreaming) {
      setConnectionStatus('connected');
      setData(mockData);
    } else {
      setConnectionStatus('disconnected');
      setData([]);
    }
  }, [isStreaming]);

  const toggleStreaming = () => {
    setLoading(true);
    setTimeout(() => {
      setIsStreaming(!isStreaming);
      setLoading(false);
    }, 1000);
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'connected': return 'bg-success text-success-800';
      case 'connecting': return 'bg-warning text-yellow-800';
      default: return 'bg-error text-error-800';
    }
  };

  const getChangeIcon = (change) => {
    return change >= 0 ? 
      <TrendingUpIcon className="h-6 w-6 text-green-600" /> : 
      <TrendingDownIcon className="h-6 w-6 text-red-600" />;
  };

  const getChangeColor = (change) => {
    return change >= 0 ? 'text-green-600' : 'text-red-600';
  };

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">
          Live Market Data
        </h1>
        <p className="text-gray-600">
          Real-time market data streaming with live price updates and market analytics.
        </p>
      </div>

      {/* Connection Status */}
      <div className="card mb-6">
        <div className="flex justify-between items-center">
          <div>
            <h2 className="text-lg font-semibold text-gray-900 mb-2">Connection Status</h2>
            <div className="flex items-center space-x-2">
              <span className={`px-3 py-1 rounded-full text-sm font-medium ${getStatusColor(connectionStatus)}`}>
                {connectionStatus.toUpperCase()}
              </span>
              {isStreaming && (
                <span className="px-3 py-1 rounded-full text-sm font-medium bg-success text-success-800">
                  LIVE
                </span>
              )}
            </div>
          </div>
          
          <div className="flex space-x-2">
            <button
              onClick={toggleStreaming}
              disabled={loading}
              className={`inline-flex items-center px-4 py-2 rounded-lg font-medium transition-colors ${
                isStreaming 
                  ? 'bg-red-600 hover:bg-red-700 text-white' 
                  : 'btn-primary'
              } ${loading ? 'opacity-50 cursor-not-allowed' : ''}`}
            >
              {loading ? (
                <div className="animate-spin h-4 w-4 mr-2 border-2 border-white border-t-transparent rounded-full"></div>
              ) : (
                <>
                  {isStreaming ? (
                    <StopIcon className="h-4 w-4 mr-2" />
                  ) : (
                    <PlayIcon className="h-4 w-4 mr-2" />
                  )}
                </>
              )}
              {loading ? 'Connecting...' : (isStreaming ? 'Stop Stream' : 'Start Stream')}
            </button>
            
            <button className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors">
              <ArrowRefreshIcon className="h-5 w-5" />
            </button>
            
            <button className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors">
              <Cog6ToothIcon className="h-5 w-5" />
            </button>
          </div>
        </div>
      </div>

      {/* Market Data Grid */}
      {isStreaming ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6 mb-6">
          {data.map((stock) => (
            <div key={stock.symbol} className="card">
              <div className="space-y-4">
                <div className="flex justify-between items-center">
                  <h3 className="text-lg font-semibold text-gray-900">
                    {stock.symbol}
                  </h3>
                  {getChangeIcon(stock.change)}
                </div>
                
                <div className="text-2xl font-bold text-gray-900">
                  ${stock.price.toFixed(2)}
                </div>
                
                <div className="flex items-center space-x-2">
                  <span className={`text-sm font-medium ${getChangeColor(stock.change)}`}>
                    {stock.change >= 0 ? '+' : ''}${stock.change.toFixed(2)}
                  </span>
                  <span className={`text-sm font-medium ${getChangeColor(stock.change)}`}>
                    ({stock.changePercent >= 0 ? '+' : ''}{stock.changePercent.toFixed(2)}%)
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="card text-center py-12 mb-6">
          <ChartBarIcon className="h-16 w-16 text-gray-400 mx-auto mb-4" />
          <h3 className="text-lg font-semibold text-gray-900 mb-2">
            Live data streaming is stopped
          </h3>
          <p className="text-gray-600 mb-4">
            Click "Start Stream" to begin receiving real-time market data
          </p>
          <button 
            onClick={toggleStreaming}
            className="btn-primary inline-flex items-center"
          >
            <PlayIcon className="h-4 w-4 mr-2" />
            Start Live Stream
          </button>
        </div>
      )}

      {/* Quick Stats */}
      <div className="card">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">
          Stream Statistics
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
          <div>
            <p className="text-sm text-gray-600 mb-1">Active Connections</p>
            <p className="text-xl font-semibold text-gray-900">
              {isStreaming ? '1' : '0'}
            </p>
          </div>
          <div>
            <p className="text-sm text-gray-600 mb-1">Data Points</p>
            <p className="text-xl font-semibold text-gray-900">
              {data.length}
            </p>
          </div>
          <div>
            <p className="text-sm text-gray-600 mb-1">Update Rate</p>
            <p className="text-xl font-semibold text-gray-900">
              {isStreaming ? '1s' : '0s'}
            </p>
          </div>
          <div>
            <p className="text-sm text-gray-600 mb-1">Status</p>
            <p className={`text-xl font-semibold ${getChangeColor(isStreaming ? 1 : -1)}`}>
              {isStreaming ? 'LIVE' : 'STOPPED'}
            </p>
          </div>
        </div>
      </div>

      {/* Info Alert */}
      <div className="mt-6 bg-blue-50 border border-blue-200 rounded-lg p-4">
        <div className="flex">
          <InformationCircleIcon className="h-5 w-5 text-blue-600 mr-3 mt-0.5 flex-shrink-0" />
          <p className="text-sm text-blue-800">
            This is a TailwindCSS version of the Live Data page that eliminates MUI dependencies. 
            Real-time streaming capabilities include WebSocket connections, multiple data sources, 
            and advanced charting features.
          </p>
        </div>
      </div>
    </div>
  );
};

export default LiveDataTailwind;