/**
 * Sample Portfolio Data Store for Local Development
 * Provides comprehensive sample portfolio data when broker API/database is not available
 */

const SAMPLE_PORTFOLIO_HOLDINGS = [
  {
    symbol: 'AAPL',
    company: 'Apple Inc.',
    shares: 100.0,
    avgCost: 150.00,
    currentPrice: 175.50,
    marketValue: 17550.00,
    gainLoss: 2550.00,
    gainLossPercent: 17.0,
    sector: 'Technology',
    allocation: 35.1,
    lastUpdated: new Date().toISOString()
  },
  {
    symbol: 'MSFT',
    company: 'Microsoft Corporation',
    shares: 50.0,
    avgCost: 280.00,
    currentPrice: 350.25,
    marketValue: 17512.50,
    gainLoss: 3512.50,
    gainLossPercent: 25.1,
    sector: 'Technology',
    allocation: 35.0,
    lastUpdated: new Date().toISOString()
  },
  {
    symbol: 'GOOGL',
    company: 'Alphabet Inc.',
    shares: 3.0,
    avgCost: 2500.00,
    currentPrice: 2750.00,
    marketValue: 8250.00,
    gainLoss: 750.00,
    gainLossPercent: 10.0,
    sector: 'Technology',
    allocation: 16.5,
    lastUpdated: new Date().toISOString()
  },
  {
    symbol: 'TSLA',
    company: 'Tesla, Inc.',
    shares: 20.0,
    avgCost: 200.00,
    currentPrice: 250.80,
    marketValue: 5016.00,
    gainLoss: 1016.00,
    gainLossPercent: 25.4,
    sector: 'Consumer Cyclical',
    allocation: 10.0,
    lastUpdated: new Date().toISOString()
  },
  {
    symbol: 'JNJ',
    company: 'Johnson & Johnson',
    shares: 10.0,
    avgCost: 160.00,
    currentPrice: 170.25,
    marketValue: 1702.50,
    gainLoss: 102.50,
    gainLossPercent: 6.4,
    sector: 'Healthcare',
    allocation: 3.4,
    lastUpdated: new Date().toISOString()
  }
];

const SAMPLE_ACCOUNT_INFO = {
  balance: 50031.00,
  equity: 50031.00,
  cash: 0.00,
  dayTrades: 0,
  buyingPower: 50031.00,
  accountType: 'paper',
  lastUpdated: new Date().toISOString()
};

/**
 * Get sample portfolio holdings with realistic data
 */
function getSamplePortfolioData(accountType = 'paper') {
  const holdings = [...SAMPLE_PORTFOLIO_HOLDINGS];
  const totalValue = holdings.reduce((sum, h) => sum + h.marketValue, 0);
  const totalCost = holdings.reduce((sum, h) => sum + (h.avgCost * h.shares), 0);
  const totalGainLoss = holdings.reduce((sum, h) => sum + h.gainLoss, 0);

  return {
    success: true,
    data: {
      holdings: holdings,
      summary: {
        totalValue: totalValue,
        totalCost: totalCost,
        totalGainLoss: totalGainLoss,
        totalGainLossPercent: totalCost > 0 ? (totalGainLoss / totalCost) * 100 : 0,
        numPositions: holdings.length,
        accountType: accountType,
        dataSource: 'sample'
      },
      metadata: {
        total_matching_holdings: holdings.length,
        development_mode: true,
        data_source: 'sample_portfolio_store'
      }
    },
    timestamp: new Date().toISOString()
  };
}

/**
 * Get sample account information
 */
function getSampleAccountInfo(accountType = 'paper') {
  return {
    success: true,
    data: {
      ...SAMPLE_ACCOUNT_INFO,
      accountType: accountType,
      dataSource: 'sample'
    },
    timestamp: new Date().toISOString()
  };
}

/**
 * Get sample performance data
 */
function getSamplePerformanceData(timeframe = '1Y') {
  const dataPoints = timeframe === '1Y' ? 252 : 
                    timeframe === '6M' ? 126 : 
                    timeframe === '3M' ? 63 : 
                    timeframe === '1M' ? 21 : 7;
  
  const startDate = new Date();
  startDate.setDate(startDate.getDate() - dataPoints);
  
  const performance = [];
  let baseValue = 45000;
  
  for (let i = 0; i < dataPoints; i++) {
    const date = new Date(startDate);
    date.setDate(date.getDate() + i);
    
    // Simulate realistic portfolio growth with some volatility
    const growth = 0.0003; // ~8% annually
    const volatility = (Math.random() - 0.5) * 0.04; // ±2% daily volatility
    baseValue *= (1 + growth + volatility);
    
    performance.push({
      date: date.toISOString().split('T')[0],
      value: Math.round(baseValue * 100) / 100,
      change: Math.round((baseValue - 45000) * 100) / 100,
      changePercent: Math.round(((baseValue - 45000) / 45000) * 10000) / 100
    });
  }
  
  return {
    success: true,
    data: {
      performance: performance,
      summary: {
        totalReturn: performance[performance.length - 1]?.change || 0,
        totalReturnPercent: performance[performance.length - 1]?.changePercent || 0,
        annualizedReturn: 12.1,
        volatility: 18.7,
        sharpeRatio: 1.2,
        maxDrawdown: -8.4,
        dataSource: 'sample'
      }
    },
    timestamp: new Date().toISOString()
  };
}

/**
 * Get sample analytics data
 */
function getSampleAnalyticsData() {
  return {
    success: true,
    data: {
      performance: {
        totalReturn: 7830.00,
        totalReturnPercent: 18.5,
        annualizedReturn: 12.1,
        volatility: 18.7,
        sharpeRatio: 1.2,
        maxDrawdown: -8.4,
        winRate: 65.2,
        numTrades: 0
      },
      risk: {
        beta: 1.1,
        alpha: 2.5,
        rSquared: 0.85,
        var95: 2250.00,
        expectedShortfall: 3100.00
      },
      allocation: {
        byAector: [
          { name: 'Technology', value: 70.1, count: 3 },
          { name: 'Healthcare', value: 3.4, count: 1 },
          { name: 'Consumer Cyclical', value: 10.0, count: 1 },
          { name: 'Cash', value: 16.5, count: 0 }
        ]
      },
      metadata: {
        dataSource: 'sample',
        lastUpdated: new Date().toISOString()
      }
    },
    timestamp: new Date().toISOString()
  };
}

module.exports = {
  SAMPLE_PORTFOLIO_HOLDINGS,
  SAMPLE_ACCOUNT_INFO,
  getSamplePortfolioData,
  getSampleAccountInfo,
  getSamplePerformanceData,
  getSampleAnalyticsData
};