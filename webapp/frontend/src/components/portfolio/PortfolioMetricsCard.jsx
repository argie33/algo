import React from 'react';
import { 
  ArrowTrendingUpIcon, 
  ArrowTrendingDownIcon,
  ChartBarIcon,
  InformationCircleIcon
} from '@heroicons/react/24/outline';

const PortfolioMetricsCard = ({ 
  title, 
  value, 
  change, 
  changePercent, 
  icon: Icon, 
  gradient, 
  description,
  trend = 'neutral',
  size = 'default'
}) => {
  const gradients = {
    blue: 'from-blue-500 to-blue-600',
    green: 'from-green-500 to-green-600',
    purple: 'from-purple-500 to-purple-600',
    orange: 'from-orange-500 to-orange-600',
    red: 'from-red-500 to-red-600',
    indigo: 'from-indigo-500 to-indigo-600'
  };

  const sizes = {
    sm: 'p-4',
    default: 'p-6',
    lg: 'p-8'
  };

  const isPositive = change >= 0;
  const TrendIcon = isPositive ? ArrowTrendingUpIcon : ArrowTrendingDownIcon;

  return (
    <div className={`bg-gradient-to-r ${gradients[gradient] || gradients.blue} rounded-xl shadow-lg hover:shadow-xl transition-all duration-300 transform hover:-translate-y-1`}>
      <div className={`${sizes[size]} text-white`}>
        <div className="flex items-start justify-between">
          <div className="flex-1">
            <div className="flex items-center space-x-2 mb-2">
              <p className="text-white/80 text-sm font-medium">{title}</p>
              {description && (
                <div className="group relative">
                  <InformationCircleIcon className="h-4 w-4 text-white/60 hover:text-white/90 cursor-help" />
                  <div className="absolute bottom-full left-1/2 transform -translate-x-1/2 mb-2 hidden group-hover:block">
                    <div className="bg-gray-900 text-white text-xs rounded-lg px-3 py-2 max-w-xs">
                      {description}
                      <div className="absolute top-full left-1/2 transform -translate-x-1/2">
                        <div className="border-4 border-transparent border-t-gray-900"></div>
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
            
            <div className="space-y-2">
              <p className="text-2xl lg:text-3xl font-bold tracking-tight">
                {typeof value === 'number' ? value.toLocaleString() : value}
              </p>
              
              {change !== undefined && (
                <div className="flex items-center space-x-2">
                  <div className={`flex items-center space-x-1 px-2 py-1 rounded-full text-xs font-medium ${
                    isPositive ? 'bg-white/20 text-white' : 'bg-black/20 text-white'
                  }`}>
                    <TrendIcon className="h-3 w-3" />
                    <span>
                      {isPositive ? '+' : ''}{typeof change === 'number' ? change.toLocaleString() : change}
                    </span>
                    {changePercent && (
                      <span>({isPositive ? '+' : ''}{changePercent}%)</span>
                    )}
                  </div>
                  <span className="text-white/70 text-xs">today</span>
                </div>
              )}
            </div>
          </div>
          
          {Icon && (
            <div className="ml-4">
              <div className="p-3 bg-white/20 rounded-lg backdrop-blur-sm">
                <Icon className="h-8 w-8 text-white" />
              </div>
            </div>
          )}
        </div>
        
        {/* Optional sparkline or mini chart area */}
        <div className="mt-4 flex items-center justify-between">
          <div className="flex space-x-1">
            {[...Array(7)].map((_, i) => (
              <div 
                key={i}
                className="w-1 bg-white/30 rounded-full"
                style={{ 
                  height: `${Math.random() * 20 + 8}px`,
                  opacity: 0.4 + (Math.random() * 0.6)
                }}
              />
            ))}
          </div>
          
          {trend !== 'neutral' && (
            <div className={`text-xs font-medium px-2 py-1 rounded-full ${
              trend === 'up' ? 'bg-green-400/30 text-green-100' :
              trend === 'down' ? 'bg-red-400/30 text-red-100' :
              'bg-yellow-400/30 text-yellow-100'
            }`}>
              {trend === 'up' ? '↗ Trending Up' : 
               trend === 'down' ? '↘ Trending Down' : 
               '→ Stable'}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default PortfolioMetricsCard;