#!/usr/bin/env node

const axios = require('axios');
const fs = require('fs');

const BASE_URL = 'http://localhost:3001/api';

// Define all API endpoints to test
const API_ENDPOINTS = {
  'Health': '/health',
  'Auth Status': '/auth/status',
  'Market Overview': '/market/overview',
  'Market Sectors': '/market/sectors',
  'Market Indices': '/market/indices',
  'Market Movers': '/market/movers',
  'Dashboard Summary': '/dashboard/summary',
  'Dashboard Metrics': '/dashboard/metrics',
  'Portfolio Summary': '/portfolio',
  'Portfolio Holdings': '/portfolio/holdings',
  'Portfolio Performance': '/portfolio/performance',
  'Stocks List': '/stocks',
  'Stocks Popular': '/stocks/popular',
  'Stock Detail AAPL': '/stocks/AAPL',
  'Stock Detail MSFT': '/stocks/MSFT',
  'Stock Price AAPL': '/stocks/AAPL/price',
  'Stock Financials AAPL': '/stocks/AAPL/financials',
  'Stock Technical AAPL': '/stocks/AAPL/technical',
  'Screener Default': '/screener',
  'Screener Results': '/screener/results',
  'Analytics Portfolio': '/analytics/portfolio',
  'Analytics Performance': '/analytics/performance',
  'Technical Indicators': '/technical/indicators',
  'Technical Analysis': '/technical/analysis',
  'Sentiment Analysis': '/sentiment/analysis',
  'Sentiment Summary': '/sentiment/summary',
  'News Latest': '/news/latest',
  'News Stock AAPL': '/news/AAPL',
  'Calendar Earnings': '/calendar/earnings',
  'Calendar Events': '/calendar/events',
  'Scores Overview': '/scores',
  'Scores Stock AAPL': '/scores/AAPL',
  'Metrics Market': '/metrics/market',
  'Metrics Performance': '/metrics/performance',
  'Risk Analysis': '/risk/analysis',
  'Risk Portfolio': '/risk/portfolio',
  'Settings User': '/settings',
  'Settings Preferences': '/settings/preferences',
  'Sectors Overview': '/sectors',
  'Sectors Performance': '/sectors/performance',
  'Signals Trading': '/signals/trading',
  'Signals Buy': '/signals/buy',
  'Signals Sell': '/signals/sell',
  'Backtest Results': '/backtest/results',
  'Financial Statements': '/financials/statements',
  'Financial Ratios': '/financials/ratios',
  'Trading Positions': '/trading/positions',
  'Trading History': '/trading/history',
  'Price Data AAPL': '/price/AAPL',
  'Price Historical AAPL': '/price/AAPL/historical',
  'Performance Metrics': '/performance/metrics',
  'Performance Summary': '/performance/summary',
  'Watchlist Default': '/watchlist',
  'Data Sources': '/data/sources',
  'Data Status': '/data/status',
  'Economic Indicators': '/economic/indicators',
  'Economic Data': '/economic/data',
  'Commodities Prices': '/commodities/prices',
  'Commodities Overview': '/commodities',
  'ETF List': '/etf',
  'ETF Popular': '/etf/popular',
  'Insider Trading': '/insider/trading',
  'Insider Activity': '/insider/activity',
  'Dividend Calendar': '/dividend/calendar',
  'Dividend History': '/dividend/history',
  'Live Data Stream': '/live-data/stream',
  'Live Data Quotes': '/live-data/quotes',
  'Orders Active': '/orders/active',
  'Orders History': '/orders/history',
  'Analysts Recommendations': '/analysts/recommendations',
  'Analysts Upgrades': '/analysts/upgrades',
  'Earnings Estimates': '/earnings/estimates',
  'Earnings History': '/earnings/history',
  'Positioning Data': '/positioning/data',
  'Strategy Builder': '/strategyBuilder/strategies',
  'Diagnostics System': '/diagnostics/system',
  'Diagnostics Performance': '/diagnostics/performance'
};

async function testEndpoint(name, endpoint) {
  try {
    const startTime = Date.now();
    const response = await axios.get(`${BASE_URL}${endpoint}`, {
      timeout: 10000,
      headers: {
        'Accept': 'application/json',
        'User-Agent': 'API-Test-Client/1.0'
      }
    });
    const endTime = Date.now();
    const responseTime = endTime - startTime;

    return {
      name,
      endpoint,
      status: 'SUCCESS',
      statusCode: response.status,
      responseTime: `${responseTime}ms`,
      dataSize: JSON.stringify(response.data).length,
      hasData: response.data && (Array.isArray(response.data) ? response.data.length > 0 : Object.keys(response.data).length > 0),
      dataStructure: Array.isArray(response.data) ? 'Array' : typeof response.data,
      preview: JSON.stringify(response.data).substring(0, 200) + '...'
    };
  } catch (error) {
    return {
      name,
      endpoint,
      status: 'ERROR',
      statusCode: error.response?.status || 'N/A',
      responseTime: 'N/A',
      error: error.response?.data?.message || error.message,
      errorType: error.code || 'Unknown'
    };
  }
}

async function runAllTests() {
  console.log('🚀 Starting comprehensive API testing...\n');

  const results = [];
  let successCount = 0;
  let errorCount = 0;

  const endpoints = Object.entries(API_ENDPOINTS);

  for (let i = 0; i < endpoints.length; i++) {
    const [name, endpoint] = endpoints[i];
    console.log(`Testing ${i + 1}/${endpoints.length}: ${name} (${endpoint})`);

    const result = await testEndpoint(name, endpoint);
    results.push(result);

    if (result.status === 'SUCCESS') {
      successCount++;
      console.log(`✅ ${result.statusCode} - ${result.responseTime} - ${result.hasData ? 'Has Data' : 'No Data'}`);
    } else {
      errorCount++;
      console.log(`❌ ${result.statusCode} - ${result.error}`);
    }

    // Small delay to prevent overwhelming the server
    await new Promise(resolve => setTimeout(resolve, 100));
  }

  // Generate summary report
  const summary = {
    totalTests: endpoints.length,
    successful: successCount,
    failed: errorCount,
    successRate: ((successCount / endpoints.length) * 100).toFixed(1) + '%',
    timestamp: new Date().toISOString(),
    results: results
  };

  // Save detailed results to file
  fs.writeFileSync('api_test_results.json', JSON.stringify(summary, null, 2));

  console.log('\n📊 TEST SUMMARY:');
  console.log(`Total Endpoints: ${summary.totalTests}`);
  console.log(`Successful: ${summary.successful}`);
  console.log(`Failed: ${summary.failed}`);
  console.log(`Success Rate: ${summary.successRate}`);

  console.log('\n🔍 DETAILED RESULTS:');
  results.forEach(result => {
    if (result.status === 'SUCCESS') {
      console.log(`✅ ${result.name}: ${result.statusCode} (${result.responseTime}) - ${result.hasData ? 'Data Available' : 'No Data'}`);
    } else {
      console.log(`❌ ${result.name}: ${result.statusCode} - ${result.error}`);
    }
  });

  console.log('\n📄 Full results saved to: api_test_results.json');

  return summary;
}

// Run the tests
runAllTests().catch(console.error);