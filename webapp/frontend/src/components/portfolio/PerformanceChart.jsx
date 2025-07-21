import React, { useState, useMemo } from 'react';
import {
  LineChart,
  Line,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  Brush
} from 'recharts';
import {
  ChartBarIcon,
  AdjustmentsHorizontalIcon,
  EyeIcon,
  EyeSlashIcon,
  ArrowTrendingUpIcon,
  ArrowTrendingDownIcon
} from '@heroicons/react/24/outline';

const PerformanceChart = ({ 
  data, 
  height = 400, 
  showBenchmark = true, 
  showBrush = true,
  timeframes = ['1D', '1W', '1M', '3M', '6M', '1Y', 'YTD', 'ALL'],
  benchmarks = [
    { key: 'sp500', name: 'S&P 500', color: '#10B981' },
    { key: 'nasdaq', name: 'NASDAQ', color: '#F59E0B' },
    { key: 'dow', name: 'Dow Jones', color: '#8B5CF6' }
  ]
}) => {
  const [selectedTimeframe, setSelectedTimeframe] = useState('1M');
  const [chartType, setChartType] = useState('line'); // line, area
  const [selectedBenchmarks, setSelectedBenchmarks] = useState(['sp500']);
  const [showGrid, setShowGrid] = useState(true);
  const [showTooltip, setShowTooltip] = useState(true);

  // Filter data based on timeframe
  const filteredData = useMemo(() => {
    if (!data || selectedTimeframe === 'ALL') return data;
    
    const now = new Date();
    let startDate = new Date();
    
    switch (selectedTimeframe) {
      case '1D':
        startDate.setDate(now.getDate() - 1);
        break;
      case '1W':
        startDate.setDate(now.getDate() - 7);
        break;
      case '1M':
        startDate.setMonth(now.getMonth() - 1);
        break;
      case '3M':
        startDate.setMonth(now.getMonth() - 3);
        break;
      case '6M':
        startDate.setMonth(now.getMonth() - 6);
        break;
      case '1Y':
        startDate.setFullYear(now.getFullYear() - 1);
        break;
      case 'YTD':
        startDate = new Date(now.getFullYear(), 0, 1);
        break;
      default:
        return data;
    }
    
    return data.filter(item => new Date(item.date) >= startDate);
  }, [data, selectedTimeframe]);

  // Calculate performance metrics
  const metrics = useMemo(() => {
    if (!filteredData || filteredData.length < 2) return null;
    
    const firstValue = filteredData[0].value;
    const lastValue = filteredData[filteredData.length - 1].value;
    const totalReturn = ((lastValue - firstValue) / firstValue) * 100;
    
    let maxValue = firstValue;
    let maxDrawdown = 0;
    
    filteredData.forEach(item => {
      if (item.value > maxValue) {
        maxValue = item.value;
      }
      const drawdown = ((item.value - maxValue) / maxValue) * 100;
      if (drawdown < maxDrawdown) {
        maxDrawdown = drawdown;
      }
    });

    // Calculate volatility (simplified)
    const returns = filteredData.slice(1).map((item, i) => 
      ((item.value - filteredData[i].value) / filteredData[i].value) * 100
    );
    const avgReturn = returns.reduce((sum, ret) => sum + ret, 0) / returns.length;
    const variance = returns.reduce((sum, ret) => sum + Math.pow(ret - avgReturn, 2), 0) / returns.length;
    const volatility = Math.sqrt(variance) * Math.sqrt(252); // Annualized

    return {
      totalReturn: totalReturn.toFixed(2),
      maxDrawdown: maxDrawdown.toFixed(2),
      volatility: volatility.toFixed(2),
      sharpeRatio: (totalReturn / volatility).toFixed(2)
    };
  }, [filteredData]);

  const toggleBenchmark = (benchmarkKey) => {
    setSelectedBenchmarks(prev => 
      prev.includes(benchmarkKey)
        ? prev.filter(key => key !== benchmarkKey)
        : [...prev, benchmarkKey]
    );
  };

  const CustomTooltip = ({ active, payload, label }) => {
    if (!active || !payload || !payload.length) return null;

    return (
      <div className="bg-white border border-gray-200 rounded-lg shadow-lg p-4 min-w-48">
        <p className="font-medium text-gray-900 mb-2">
          {new Date(label).toLocaleDateString()}
        </p>
        {payload.map((entry) => (
          <div key={entry.dataKey} className="flex items-center justify-between py-1">
            <div className="flex items-center space-x-2">
              <div 
                className="w-3 h-3 rounded-full"
                style={{ backgroundColor: entry.color }}
              />
              <span className="text-sm text-gray-600">
                {entry.dataKey === 'value' ? 'Portfolio' : entry.name || entry.dataKey}
              </span>
            </div>
            <span className="font-medium text-gray-900">
              ${Number(entry.value).toLocaleString()}
            </span>
          </div>
        ))}
      </div>
    );
  };

  const renderChart = () => {
    const ChartComponent = chartType === 'area' ? AreaChart : LineChart;
    const DataComponent = chartType === 'area' ? Area : Line;

    return (
      <ResponsiveContainer width="100%" height={height}>
        <ChartComponent data={filteredData} margin={{ top: 20, right: 30, left: 20, bottom: 20 }}>
          {showGrid && <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />}
          <XAxis 
            dataKey="date" 
            stroke="#6b7280"
            fontSize={12}
            tickFormatter={(value) => new Date(value).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
          />
          <YAxis 
            stroke="#6b7280"
            fontSize={12}
            tickFormatter={(value) => `$${(value / 1000).toFixed(0)}k`}
          />
          {showTooltip && <Tooltip content={<CustomTooltip />} />}
          
          {/* Portfolio Line/Area */}
          <DataComponent
            type="monotone"
            dataKey="value"
            stroke="#3B82F6"
            strokeWidth={3}
            fill={chartType === 'area' ? 'url(#portfolioGradient)' : undefined}
            dot={false}
            activeDot={chartType === 'line' ? { r: 6, fill: '#3B82F6' } : undefined}
          />
          
          {/* Benchmark Lines */}
          {showBenchmark && selectedBenchmarks.map(benchmarkKey => {
            const benchmark = benchmarks.find(b => b.key === benchmarkKey);
            if (!benchmark) return null;
            
            return (
              <Line
                key={benchmarkKey}
                type="monotone"
                dataKey={benchmarkKey}
                stroke={benchmark.color}
                strokeWidth={2}
                strokeDasharray="5 5"
                dot={false}
                name={benchmark.name}
              />
            );
          })}
          
          {chartType === 'area' && (
            <defs>
              <linearGradient id="portfolioGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#3B82F6" stopOpacity={0.3}/>
                <stop offset="95%" stopColor="#3B82F6" stopOpacity={0}/>
              </linearGradient>
            </defs>
          )}
          
          {showBrush && (
            <Brush 
              dataKey="date" 
              height={30} 
              stroke="#3B82F6"
              tickFormatter={(value) => new Date(value).toLocaleDateString('en-US', { month: 'short' })}
            />
          )}
        </ChartComponent>
      </ResponsiveContainer>
    );
  };

  return (
    <div className="bg-white rounded-lg border border-gray-200 shadow-sm">
      {/* Header */}
      <div className="p-6 border-b border-gray-200">
        <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between space-y-4 lg:space-y-0">
          <div>
            <h3 className="text-lg font-semibold text-gray-900">Portfolio Performance</h3>
            <p className="text-sm text-gray-500">Track your portfolio performance over time</p>
          </div>
          
          {/* Controls */}
          <div className="flex flex-wrap items-center gap-4">
            {/* Timeframe Selector */}
            <div className="flex items-center space-x-1 bg-gray-100 rounded-lg p-1">
              {timeframes.map(tf => (
                <button
                  key={tf}
                  onClick={() => setSelectedTimeframe(tf)}
                  className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${
                    selectedTimeframe === tf
                      ? 'bg-white text-blue-600 shadow-sm'
                      : 'text-gray-600 hover:text-gray-900'
                  }`}
                >
                  {tf}
                </button>
              ))}
            </div>
            
            {/* Chart Type Toggle */}
            <div className="flex items-center space-x-1 bg-gray-100 rounded-lg p-1">
              <button
                onClick={() => setChartType('line')}
                className={`p-2 rounded-md transition-colors ${
                  chartType === 'line' ? 'bg-white text-blue-600 shadow-sm' : 'text-gray-600 hover:text-gray-900'
                }`}
                title="Line Chart"
              >
                <ChartBarIcon className="h-4 w-4" />
              </button>
              <button
                onClick={() => setChartType('area')}
                className={`p-2 rounded-md transition-colors ${
                  chartType === 'area' ? 'bg-white text-blue-600 shadow-sm' : 'text-gray-600 hover:text-gray-900'
                }`}
                title="Area Chart"
              >
                <AdjustmentsHorizontalIcon className="h-4 w-4" />
              </button>
            </div>
            
            {/* View Options */}
            <div className="flex items-center space-x-2">
              <button
                onClick={() => setShowGrid(!showGrid)}
                className={`p-2 rounded-md transition-colors ${
                  showGrid ? 'text-blue-600 bg-blue-50' : 'text-gray-400 hover:text-gray-600'
                }`}
                title="Toggle Grid"
              >
                <EyeIcon className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>
        
        {/* Performance Metrics */}
        {metrics && (
          <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="text-center p-3 bg-blue-50 rounded-lg">
              <div className={`text-lg font-bold ${parseFloat(metrics.totalReturn) >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                {parseFloat(metrics.totalReturn) >= 0 ? '+' : ''}{metrics.totalReturn}%
              </div>
              <div className="text-xs text-gray-600">Total Return</div>
            </div>
            <div className="text-center p-3 bg-gray-50 rounded-lg">
              <div className="text-lg font-bold text-gray-900">{metrics.volatility}%</div>
              <div className="text-xs text-gray-600">Volatility</div>
            </div>
            <div className="text-center p-3 bg-red-50 rounded-lg">
              <div className="text-lg font-bold text-red-600">{metrics.maxDrawdown}%</div>
              <div className="text-xs text-gray-600">Max Drawdown</div>
            </div>
            <div className="text-center p-3 bg-green-50 rounded-lg">
              <div className="text-lg font-bold text-green-600">{metrics.sharpeRatio}</div>
              <div className="text-xs text-gray-600">Sharpe Ratio</div>
            </div>
          </div>
        )}
        
        {/* Benchmark Controls */}
        {showBenchmark && (
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium text-gray-700">Compare to:</span>
            {benchmarks.map(benchmark => (
              <button
                key={benchmark.key}
                onClick={() => toggleBenchmark(benchmark.key)}
                className={`inline-flex items-center px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                  selectedBenchmarks.includes(benchmark.key)
                    ? 'text-white shadow-sm'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                }`}
                style={{
                  backgroundColor: selectedBenchmarks.includes(benchmark.key) ? benchmark.color : undefined
                }}
              >
                <div 
                  className="w-2 h-2 rounded-full mr-2"
                  style={{ backgroundColor: benchmark.color }}
                />
                {benchmark.name}
              </button>
            ))}
          </div>
        )}
      </div>
      
      {/* Chart */}
      <div className="p-6">
        {filteredData && filteredData.length > 0 ? (
          renderChart()
        ) : (
          <div className="flex items-center justify-center h-64 text-gray-500">
            <div className="text-center">
              <ChartBarIcon className="h-12 w-12 mx-auto mb-4 text-gray-300" />
              <p>No performance data available</p>
              <p className="text-sm">Performance data will appear once you have holdings</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default PerformanceChart;