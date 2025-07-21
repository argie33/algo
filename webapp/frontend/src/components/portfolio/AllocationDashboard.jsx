import React, { useState } from 'react';
import {
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Treemap,
  RadialBarChart,
  RadialBar
} from 'recharts';
import {
  AdjustmentsHorizontalIcon,
  ChartPieIcon,
  Squares2X2Icon,
  ArrowPathIcon,
  ExclamationTriangleIcon
} from '@heroicons/react/24/outline';

const AllocationDashboard = ({ allocation, targetAllocation, onRebalance }) => {
  const [viewType, setViewType] = useState('pie'); // pie, bar, treemap, radial
  const [selectedCategory, setSelectedCategory] = useState('sectors');
  const [showTargets, setShowTargets] = useState(false);

  const categories = {
    sectors: { data: allocation.sectors, title: 'Sector Allocation' },
    assetTypes: { data: allocation.assetTypes, title: 'Asset Type Allocation' },
    marketCap: { data: allocation.marketCap, title: 'Market Cap Allocation' },
    geography: { data: allocation.geography || [], title: 'Geographic Allocation' },
    style: { data: allocation.style, title: 'Investment Style' }
  };

  const currentData = categories[selectedCategory]?.data || [];

  // Calculate concentration risk
  const concentrationRisk = currentData.reduce((max, item) => Math.max(max, item.value), 0);
  const riskLevel = concentrationRisk > 40 ? 'high' : concentrationRisk > 25 ? 'medium' : 'low';

  const RADIAN = Math.PI / 180;
  const renderCustomizedLabel = ({ cx, cy, midAngle, innerRadius, outerRadius, percent, name }) => {
    if (percent < 0.05) return null; // Don't show labels for slices < 5%
    
    const radius = innerRadius + (outerRadius - innerRadius) * 0.5;
    const x = cx + radius * Math.cos(-midAngle * RADIAN);
    const y = cy + radius * Math.sin(-midAngle * RADIAN);

    return (
      <text 
        x={x} 
        y={y} 
        fill="white" 
        textAnchor={x > cx ? 'start' : 'end'} 
        dominantBaseline="central"
        className="text-xs font-medium"
      >
        {`${(percent * 100).toFixed(0)}%`}
      </text>
    );
  };

  const CustomTooltip = ({ active, payload, label }) => {
    if (!active || !payload || !payload.length) return null;

    const data = payload[0].payload;
    return (
      <div className="bg-white border border-gray-200 rounded-lg shadow-lg p-4">
        <p className="font-medium text-gray-900">{data.name}</p>
        <p className="text-sm text-gray-600">
          Allocation: <span className="font-medium">{data.value}%</span>
        </p>
        {showTargets && targetAllocation && (
          <p className="text-sm text-gray-600">
            Target: <span className="font-medium">{data.target || 'N/A'}%</span>
          </p>
        )}
      </div>
    );
  };

  const renderChart = () => {
    if (!currentData || currentData.length === 0) {
      return (
        <div className="flex items-center justify-center h-64 text-gray-500">
          <div className="text-center">
            <ChartPieIcon className="h-12 w-12 mx-auto mb-4 text-gray-300" />
            <p>No allocation data available</p>
          </div>
        </div>
      );
    }

    switch (viewType) {
      case 'pie':
        return (
          <ResponsiveContainer width="100%" height={300}>
            <PieChart>
              <Pie
                data={currentData}
                cx="50%"
                cy="50%"
                labelLine={false}
                label={renderCustomizedLabel}
                outerRadius={100}
                fill="#8884d8"
                dataKey="value"
              >
                {currentData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.color} />
                ))}
              </Pie>
              <Tooltip content={<CustomTooltip />} />
            </PieChart>
          </ResponsiveContainer>
        );

      case 'bar':
        return (
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={currentData} margin={{ top: 20, right: 30, left: 20, bottom: 20 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis 
                dataKey="name" 
                angle={-45}
                textAnchor="end"
                height={80}
                fontSize={12}
              />
              <YAxis tickFormatter={(value) => `${value}%`} />
              <Tooltip content={<CustomTooltip />} />
              <Bar dataKey="value" fill="#3B82F6" radius={[4, 4, 0, 0]}>
                {currentData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.color} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        );

      case 'treemap':
        return (
          <ResponsiveContainer width="100%" height={300}>
            <Treemap
              data={currentData}
              dataKey="value"
              aspectRatio={4/3}
              stroke="#fff"
              strokeWidth={2}
              content={({ root, depth, x, y, width, height, index, payload, colors, rank, name, value }) => (
                <g>
                  <rect
                    x={x}
                    y={y}
                    width={width}
                    height={height}
                    style={{
                      fill: payload.color,
                      stroke: '#fff',
                      strokeWidth: 2,
                    }}
                  />
                  {width > 60 && height > 40 && (
                    <>
                      <text
                        x={x + width / 2}
                        y={y + height / 2 - 10}
                        textAnchor="middle"
                        fill="#fff"
                        className="text-sm font-medium"
                      >
                        {name}
                      </text>
                      <text
                        x={x + width / 2}
                        y={y + height / 2 + 10}
                        textAnchor="middle"
                        fill="#fff"
                        className="text-xs"
                      >
                        {value}%
                      </text>
                    </>
                  )}
                </g>
              )}
            />
          </ResponsiveContainer>
        );

      case 'radial':
        return (
          <ResponsiveContainer width="100%" height={300}>
            <RadialBarChart cx="50%" cy="50%" innerRadius="20%" outerRadius="80%" data={currentData}>
              <RadialBar
                dataKey="value"
                cornerRadius={10}
                fill="#3B82F6"
              >
                {currentData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.color} />
                ))}
              </RadialBar>
              <Tooltip content={<CustomTooltip />} />
            </RadialBarChart>
          </ResponsiveContainer>
        );

      default:
        return null;
    }
  };

  const getRebalanceRecommendations = () => {
    if (!targetAllocation || !currentData) return [];
    
    return currentData.map(item => {
      const target = targetAllocation[selectedCategory]?.find(t => t.name === item.name);
      if (!target) return null;
      
      const difference = item.value - target.value;
      if (Math.abs(difference) < 2) return null; // Ignore small differences
      
      return {
        name: item.name,
        current: item.value,
        target: target.value,
        difference: difference,
        action: difference > 0 ? 'Reduce' : 'Increase',
        amount: Math.abs(difference)
      };
    }).filter(Boolean);
  };

  const rebalanceRecs = getRebalanceRecommendations();

  return (
    <div className="space-y-6">
      {/* Header and Controls */}
      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between space-y-4 lg:space-y-0">
          <div>
            <h3 className="text-lg font-semibold text-gray-900">Portfolio Allocation</h3>
            <p className="text-sm text-gray-500">Analyze your portfolio distribution across different categories</p>
          </div>
          
          <div className="flex flex-wrap items-center gap-4">
            {/* Category Selector */}
            <select
              value={selectedCategory}
              onChange={(e) => setSelectedCategory(e.target.value)}
              className="border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            >
              <option value="sectors">Sectors</option>
              <option value="assetTypes">Asset Types</option>
              <option value="marketCap">Market Cap</option>
              <option value="geography">Geography</option>
              <option value="style">Investment Style</option>
            </select>
            
            {/* View Type Selector */}
            <div className="flex items-center space-x-1 bg-gray-100 rounded-lg p-1">
              {[
                { type: 'pie', icon: ChartPieIcon, title: 'Pie Chart' },
                { type: 'bar', icon: AdjustmentsHorizontalIcon, title: 'Bar Chart' },
                { type: 'treemap', icon: Squares2X2Icon, title: 'Treemap' },
                { type: 'radial', icon: ArrowPathIcon, title: 'Radial Chart' }
              ].map(({ type, icon: Icon, title }) => (
                <button
                  key={type}
                  onClick={() => setViewType(type)}
                  className={`p-2 rounded-md transition-colors ${
                    viewType === type ? 'bg-white text-blue-600 shadow-sm' : 'text-gray-600 hover:text-gray-900'
                  }`}
                  title={title}
                >
                  <Icon className="h-4 w-4" />
                </button>
              ))}
            </div>
            
            {/* Show Targets Toggle */}
            {targetAllocation && (
              <label className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  checked={showTargets}
                  onChange={(e) => setShowTargets(e.target.checked)}
                  className="rounded text-blue-600 focus:ring-blue-500"
                />
                <span className="text-sm text-gray-700">Show targets</span>
              </label>
            )}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Main Chart */}
        <div className="lg:col-span-2">
          <div className="bg-white rounded-lg border border-gray-200 p-6">
            <h4 className="text-lg font-medium text-gray-900 mb-4">
              {categories[selectedCategory]?.title}
            </h4>
            {renderChart()}
          </div>
        </div>

        {/* Allocation Details */}
        <div className="space-y-6">
          {/* Concentration Risk */}
          <div className="bg-white rounded-lg border border-gray-200 p-6">
            <div className="flex items-center space-x-2 mb-4">
              <ExclamationTriangleIcon className={`h-5 w-5 ${
                riskLevel === 'high' ? 'text-red-500' :
                riskLevel === 'medium' ? 'text-yellow-500' :
                'text-green-500'
              }`} />
              <h4 className="text-lg font-medium text-gray-900">Concentration Risk</h4>
            </div>
            
            <div className="text-center">
              <div className={`text-3xl font-bold mb-2 ${
                riskLevel === 'high' ? 'text-red-600' :
                riskLevel === 'medium' ? 'text-yellow-600' :
                'text-green-600'
              }`}>
                {concentrationRisk.toFixed(1)}%
              </div>
              <p className="text-sm text-gray-600">
                Largest allocation in {categories[selectedCategory]?.title.toLowerCase()}
              </p>
              
              <div className={`mt-4 px-3 py-2 rounded-full text-xs font-medium ${
                riskLevel === 'high' ? 'bg-red-100 text-red-800' :
                riskLevel === 'medium' ? 'bg-yellow-100 text-yellow-800' :
                'bg-green-100 text-green-800'
              }`}>
                {riskLevel === 'high' ? 'High Risk' :
                 riskLevel === 'medium' ? 'Medium Risk' :
                 'Low Risk'}
              </div>
            </div>
          </div>

          {/* Allocation Breakdown */}
          <div className="bg-white rounded-lg border border-gray-200 p-6">
            <h4 className="text-lg font-medium text-gray-900 mb-4">Breakdown</h4>
            <div className="space-y-3">
              {currentData.map((item, index) => (
                <div key={index} className="flex items-center justify-between">
                  <div className="flex items-center space-x-3">
                    <div 
                      className="w-4 h-4 rounded-full"
                      style={{ backgroundColor: item.color }}
                    />
                    <span className="text-sm font-medium text-gray-900">{item.name}</span>
                  </div>
                  <div className="text-right">
                    <div className="text-sm font-medium text-gray-900">{item.value}%</div>
                    {showTargets && targetAllocation && (
                      <div className="text-xs text-gray-500">
                        Target: {item.target || 'N/A'}%
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Rebalancing Recommendations */}
          {rebalanceRecs.length > 0 && (
            <div className="bg-white rounded-lg border border-gray-200 p-6">
              <div className="flex items-center justify-between mb-4">
                <h4 className="text-lg font-medium text-gray-900">Rebalancing</h4>
                <button
                  onClick={onRebalance}
                  className="text-sm text-blue-600 hover:text-blue-800 font-medium"
                >
                  Execute
                </button>
              </div>
              
              <div className="space-y-3">
                {rebalanceRecs.map((rec, index) => (
                  <div key={index} className="p-3 bg-gray-50 rounded-lg">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-sm font-medium text-gray-900">{rec.name}</span>
                      <span className={`text-xs font-medium px-2 py-1 rounded-full ${
                        rec.action === 'Reduce' ? 'bg-red-100 text-red-800' : 'bg-green-100 text-green-800'
                      }`}>
                        {rec.action}
                      </span>
                    </div>
                    <div className="text-xs text-gray-600">
                      {rec.current}% → {rec.target}% ({rec.difference > 0 ? '-' : '+'}{rec.amount.toFixed(1)}%)
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default AllocationDashboard;