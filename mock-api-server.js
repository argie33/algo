#!/usr/bin/env node
/**
 * Mock API Server for Economic Dashboard Testing
 * Serves mock economic data without needing database setup
 */

const http = require('http');
const random = (min, max) => Math.random() * (max - min) + min;

function generateMockData() {
  return {
    success: true,
    data: {
      gdpGrowth: 5234.5,
      unemployment: 3.8,
      inflation: 306.7,
      employment: {
        payroll_change: 156300,
        unemployment_rate: 3.8
      },
      yieldCurve: {
        spread2y10y: 0.85,
        spread3m10y: 1.20,
        isInverted: false,
        interpretation: "Normal yield curve indicates healthy economic conditions",
        historicalAccuracy: 65,
        averageLeadTime: 0
      },
      indicators: [
        // LEI INDICATORS (11)
        {
          name: "Unemployment Rate",
          category: "LEI",
          value: "3.8%",
          rawValue: 3.8,
          unit: "%",
          change: -0.15,
          trend: "down",
          signal: "Positive",
          description: "Percentage of labor force actively seeking employment",
          strength: 96,
          importance: "high",
          date: new Date(Date.now() - 5*24*60*60*1000).toISOString().split('T')[0],
          history: Array.from({length: 30}, (_, i) => ({
            date: new Date(Date.now() - i*24*60*60*1000).toISOString().split('T')[0],
            value: 3.8 + random(-0.3, 0.3)
          }))
        },
        {
          name: "Inflation (CPI)",
          category: "LEI",
          value: "306.7",
          rawValue: 306.7,
          unit: "Index",
          change: 0.32,
          trend: "up",
          signal: "Neutral",
          description: "Consumer Price Index measuring inflation",
          strength: 45,
          importance: "high",
          date: new Date(Date.now() - 10*24*60*60*1000).toISOString().split('T')[0],
          history: Array.from({length: 30}, (_, i) => ({
            date: new Date(Date.now() - i*24*60*60*1000).toISOString().split('T')[0],
            value: 306.7 - i*0.1
          }))
        },
        {
          name: "Fed Funds Rate",
          category: "LEI",
          value: "5.33%",
          rawValue: 5.33,
          unit: "%",
          change: 0.00,
          trend: "stable",
          signal: "Neutral",
          description: "Federal Reserve target interest rate",
          strength: 45,
          importance: "high",
          date: new Date(Date.now() - 3*24*60*60*1000).toISOString().split('T')[0],
          history: Array.from({length: 30}, (_, i) => ({
            date: new Date(Date.now() - i*24*60*60*1000).toISOString().split('T')[0],
            value: 5.33 + random(-0.05, 0.05)
          }))
        },
        {
          name: "GDP Growth",
          category: "LEI",
          value: "5.2T",
          rawValue: 5234.5,
          unit: "Billions",
          change: 2.15,
          trend: "up",
          signal: "Positive",
          description: "Real Gross Domestic Product",
          strength: 78,
          importance: "high",
          date: new Date(Date.now() - 60*24*60*60*1000).toISOString().split('T')[0],
          history: Array.from({length: 30}, (_, i) => ({
            date: new Date(Date.now() - i*7*24*60*60*1000).toISOString().split('T')[0],
            value: 5100 + i*5
          }))
        },
        {
          name: "Payroll Employment",
          category: "LEI",
          value: "156.3M",
          rawValue: 156300,
          unit: "Thousands",
          change: 0.45,
          trend: "up",
          signal: "Positive",
          description: "Total nonfarm payroll employment",
          strength: 85,
          importance: "high",
          date: new Date(Date.now() - 5*24*60*60*1000).toISOString().split('T')[0],
          history: Array.from({length: 30}, (_, i) => ({
            date: new Date(Date.now() - i*24*60*60*1000).toISOString().split('T')[0],
            value: 156200 + i*2
          }))
        },
        {
          name: "Housing Starts",
          category: "LEI",
          value: "1382K",
          rawValue: 1382,
          unit: "Thousands",
          change: -1.23,
          trend: "down",
          signal: "Neutral",
          description: "Number of new residential construction projects started",
          strength: 72,
          importance: "medium",
          date: new Date(Date.now() - 15*24*60*60*1000).toISOString().split('T')[0],
          history: Array.from({length: 30}, (_, i) => ({
            date: new Date(Date.now() - i*7*24*60*60*1000).toISOString().split('T')[0],
            value: 1382 - i*5
          }))
        },
        {
          name: "Initial Jobless Claims",
          category: "LEI",
          value: "220K",
          rawValue: 220,
          unit: "Thousands",
          change: 2.27,
          trend: "up",
          signal: "Positive",
          description: "Weekly unemployment insurance claims",
          strength: 85,
          importance: "medium",
          date: new Date(Date.now() - 3*24*60*60*1000).toISOString().split('T')[0],
          history: Array.from({length: 30}, (_, i) => ({
            date: new Date(Date.now() - i*24*60*60*1000).toISOString().split('T')[0],
            value: 220 + random(-20, 20)
          }))
        },
        {
          name: "Business Loans",
          category: "LEI",
          value: "2.1B",
          rawValue: 2100000,
          unit: "Billions",
          change: 1.85,
          trend: "up",
          signal: "Positive",
          description: "Commercial and industrial loans outstanding",
          strength: 68,
          importance: "medium",
          date: new Date(Date.now() - 30*24*60*60*1000).toISOString().split('T')[0],
          history: Array.from({length: 30}, (_, i) => ({
            date: new Date(Date.now() - i*7*24*60*60*1000).toISOString().split('T')[0],
            value: 2050000 + i*10000
          }))
        },
        {
          name: "S&P 500 Index",
          category: "LEI",
          value: "5789",
          rawValue: 5789,
          unit: "Index",
          change: 8.45,
          trend: "up",
          signal: "Positive",
          description: "S&P 500 stock market index - leading indicator of economic activity",
          strength: 95,
          importance: "high",
          date: new Date(Date.now() - 1*24*60*60*1000).toISOString().split('T')[0],
          history: Array.from({length: 30}, (_, i) => ({
            date: new Date(Date.now() - i*24*60*60*1000).toISOString().split('T')[0],
            value: 5650 + i*4.5
          }))
        },
        {
          name: "Market Volatility (VIX)",
          category: "LEI",
          value: "13.2",
          rawValue: 13.2,
          unit: "Index",
          change: -5.13,
          trend: "down",
          signal: "Positive",
          description: "CBOE Volatility Index - fear gauge and market sentiment",
          strength: 92,
          importance: "high",
          date: new Date(Date.now() - 1*24*60*60*1000).toISOString().split('T')[0],
          history: Array.from({length: 30}, (_, i) => ({
            date: new Date(Date.now() - i*24*60*60*1000).toISOString().split('T')[0],
            value: 13.2 + random(-2, 2)
          }))
        },
        {
          name: "Yield Curve (2Y-10Y Spread)",
          category: "LEI",
          value: "0.85 %",
          rawValue: 0.85,
          unit: "%",
          change: 5.88,
          trend: "up",
          signal: "Positive",
          description: "Difference between 10-year and 2-year Treasury yields - recession predictor",
          strength: 72,
          importance: "high",
          date: new Date(Date.now() - 1*24*60*60*1000).toISOString().split('T')[0],
          history: Array.from({length: 30}, (_, i) => ({
            date: new Date(Date.now() - i*24*60*60*1000).toISOString().split('T')[0],
            value: 0.85 - i*0.01
          }))
        },
        // LAGGING INDICATORS (7)
        {
          name: "Average Duration of Unemployment",
          category: "LAGGING",
          value: "22.5 weeks",
          rawValue: 22.5,
          unit: "Weeks",
          change: -1.76,
          trend: "down",
          signal: "Positive",
          description: "Average number of weeks unemployed workers have been looking for work",
          strength: 92,
          importance: "high",
          date: new Date(Date.now() - 5*24*60*60*1000).toISOString().split('T')[0],
          history: Array.from({length: 30}, (_, i) => ({
            date: new Date(Date.now() - i*24*60*60*1000).toISOString().split('T')[0],
            value: 22.5 + i*0.1
          }))
        },
        {
          name: "Prime Lending Rate",
          category: "LAGGING",
          value: "8.50%",
          rawValue: 8.50,
          unit: "%",
          change: 0.00,
          trend: "stable",
          signal: "Neutral",
          description: "Bank prime lending rate used as a basis for other loan rates",
          strength: 50,
          importance: "medium",
          date: new Date(Date.now() - 7*24*60*60*1000).toISOString().split('T')[0],
          history: Array.from({length: 30}, (_, i) => ({
            date: new Date(Date.now() - i*24*60*60*1000).toISOString().split('T')[0],
            value: 8.50
          }))
        },
        {
          name: "Money Market Instruments Rate",
          category: "LAGGING",
          value: "5.35%",
          rawValue: 5.35,
          unit: "%",
          change: -0.45,
          trend: "down",
          signal: "Positive",
          description: "Interest rate on money market instruments",
          strength: 70,
          importance: "medium",
          date: new Date(Date.now() - 7*24*60*60*1000).toISOString().split('T')[0],
          history: Array.from({length: 30}, (_, i) => ({
            date: new Date(Date.now() - i*24*60*60*1000).toISOString().split('T')[0],
            value: 5.35 + random(-0.1, 0.1)
          }))
        },
        {
          name: "Inventory-Sales Ratio",
          category: "LAGGING",
          value: "1.31",
          rawValue: 1.31,
          unit: "Ratio",
          change: 0.76,
          trend: "up",
          signal: "Neutral",
          description: "Ratio of business inventories to sales",
          strength: 55,
          importance: "medium",
          date: new Date(Date.now() - 30*24*60*60*1000).toISOString().split('T')[0],
          history: Array.from({length: 30}, (_, i) => ({
            date: new Date(Date.now() - i*7*24*60*60*1000).toISOString().split('T')[0],
            value: 1.31 - i*0.02
          }))
        },
        {
          name: "Total Nonfarm Payroll (Lagging)",
          category: "LAGGING",
          value: "156.5M",
          rawValue: 156500,
          unit: "Thousands",
          change: 0.32,
          trend: "up",
          signal: "Positive",
          description: "Total seasonally adjusted nonfarm payroll employment",
          strength: 88,
          importance: "high",
          date: new Date(Date.now() - 5*24*60*60*1000).toISOString().split('T')[0],
          history: Array.from({length: 30}, (_, i) => ({
            date: new Date(Date.now() - i*24*60*60*1000).toISOString().split('T')[0],
            value: 156400 + i*1.5
          }))
        },
        {
          name: "Imports of Goods and Services",
          category: "LAGGING",
          value: "418.2B",
          rawValue: 418200,
          unit: "Billions",
          change: 2.45,
          trend: "up",
          signal: "Neutral",
          description: "Real imports of goods and services",
          strength: 60,
          importance: "medium",
          date: new Date(Date.now() - 30*24*60*60*1000).toISOString().split('T')[0],
          history: Array.from({length: 30}, (_, i) => ({
            date: new Date(Date.now() - i*7*24*60*60*1000).toISOString().split('T')[0],
            value: 418200 - i*2000
          }))
        },
        {
          name: "Labor Share of Income",
          category: "LAGGING",
          value: "56.8%",
          rawValue: 56.8,
          unit: "%",
          change: -0.32,
          trend: "down",
          signal: "Positive",
          description: "Labor share of income in the business sector",
          strength: 62,
          importance: "medium",
          date: new Date(Date.now() - 60*24*60*60*1000).toISOString().split('T')[0],
          history: Array.from({length: 30}, (_, i) => ({
            date: new Date(Date.now() - i*7*24*60*60*1000).toISOString().split('T')[0],
            value: 56.8 + i*0.05
          }))
        },
        // COINCIDENT INDICATORS (3)
        {
          name: "Consumer Sentiment (University of Michigan)",
          category: "COINCIDENT",
          value: "82.5",
          rawValue: 82.5,
          unit: "Index",
          change: 3.14,
          trend: "up",
          signal: "Positive",
          description: "Consumer sentiment index measuring economic expectations",
          strength: 88,
          importance: "high",
          date: new Date(Date.now() - 10*24*60*60*1000).toISOString().split('T')[0],
          history: Array.from({length: 30}, (_, i) => ({
            date: new Date(Date.now() - i*24*60*60*1000).toISOString().split('T')[0],
            value: 82.5 - i*0.15
          }))
        },
        {
          name: "Retail Sales",
          category: "COINCIDENT",
          value: "734.5B",
          rawValue: 734500,
          unit: "Billions",
          change: 1.23,
          trend: "up",
          signal: "Positive",
          description: "Real retail sales excluding gasoline",
          strength: 85,
          importance: "high",
          date: new Date(Date.now() - 15*24*60*60*1000).toISOString().split('T')[0],
          history: Array.from({length: 30}, (_, i) => ({
            date: new Date(Date.now() - i*7*24*60*60*1000).toISOString().split('T')[0],
            value: 734500 + i*1500
          }))
        },
        {
          name: "Employment-to-Population Ratio",
          category: "COINCIDENT",
          value: "62.8%",
          rawValue: 62.8,
          unit: "%",
          change: 0.15,
          trend: "up",
          signal: "Positive",
          description: "Percentage of population aged 16+ that is employed",
          strength: 91,
          importance: "high",
          date: new Date(Date.now() - 5*24*60*60*1000).toISOString().split('T')[0],
          history: Array.from({length: 30}, (_, i) => ({
            date: new Date(Date.now() - i*24*60*60*1000).toISOString().split('T')[0],
            value: 62.8 - i*0.02
          }))
        },
        // SECONDARY INDICATORS (4)
        {
          name: "Consumer Sentiment",
          category: "SECONDARY",
          value: "82.5",
          rawValue: 82.5,
          unit: "Index",
          change: 3.14,
          trend: "up",
          signal: "Positive",
          description: "Consumer confidence and spending expectations",
          strength: 88,
          importance: "high",
          date: new Date(Date.now() - 10*24*60*60*1000).toISOString().split('T')[0],
          history: Array.from({length: 30}, (_, i) => ({
            date: new Date(Date.now() - i*24*60*60*1000).toISOString().split('T')[0],
            value: 82.5 - i*0.15
          }))
        },
        {
          name: "Payroll Employment",
          category: "SECONDARY",
          value: "156.3M",
          rawValue: 156300,
          unit: "Thousands",
          change: 0.45,
          trend: "up",
          signal: "Positive",
          description: "Total nonfarm payroll employment",
          strength: 85,
          importance: "high",
          date: new Date(Date.now() - 5*24*60*60*1000).toISOString().split('T')[0],
          history: Array.from({length: 30}, (_, i) => ({
            date: new Date(Date.now() - i*24*60*60*1000).toISOString().split('T')[0],
            value: 156200 + i*2
          }))
        },
        {
          name: "Industrial Production",
          category: "SECONDARY",
          value: "107.4",
          rawValue: 107.4,
          unit: "Index",
          change: 1.42,
          trend: "up",
          signal: "Positive",
          description: "Measure of real output for all manufacturing, mining, and utilities facilities",
          strength: 82,
          importance: "medium",
          date: new Date(Date.now() - 20*24*60*60*1000).toISOString().split('T')[0],
          history: Array.from({length: 30}, (_, i) => ({
            date: new Date(Date.now() - i*24*60*60*1000).toISOString().split('T')[0],
            value: 107.4 - i*0.15
          }))
        },
        {
          name: "Federal Funds Rate",
          category: "SECONDARY",
          value: "5.33%",
          rawValue: 5.33,
          unit: "%",
          change: 0.00,
          trend: "stable",
          signal: "Neutral",
          description: "Federal Reserve target interest rate policy",
          strength: 45,
          importance: "high",
          date: new Date(Date.now() - 3*24*60*60*1000).toISOString().split('T')[0],
          history: Array.from({length: 30}, (_, i) => ({
            date: new Date(Date.now() - i*24*60*60*1000).toISOString().split('T')[0],
            value: 5.33 + random(-0.05, 0.05)
          }))
        }
      ],
      creditSpreads: {
        highYield: {
          oas: 385,
          signal: "Neutral",
          historicalContext: "Elevated but manageable"
        },
        investmentGrade: {
          oas: 105,
          signal: "Positive",
          historicalContext: "Tight spreads indicate confidence"
        },
        financialConditionsIndex: {
          value: -0.45,
          level: "Accommodative"
        }
      },
      upcomingEvents: [
        {
          date: new Date(Date.now() + 5*24*60*60*1000).toISOString().split('T')[0],
          event: "FOMC Interest Rate Decision",
          importance: "High",
          forecast_value: "5.25-5.50%",
          previous_value: "5.25-5.50%"
        },
        {
          date: new Date(Date.now() + 10*24*60*60*1000).toISOString().split('T')[0],
          event: "Nonfarm Payrolls",
          importance: "High",
          forecast_value: "180K",
          previous_value: "227K"
        },
        {
          date: new Date(Date.now() + 15*24*60*60*1000).toISOString().split('T')[0],
          event: "Consumer Price Index",
          importance: "High",
          forecast_value: "2.6% Y/Y",
          previous_value: "2.6% Y/Y"
        }
      ]
    }
  };
}

const server = http.createServer((req, res) => {
  // Enable CORS
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  res.setHeader('Content-Type', 'application/json');

  if (req.method === 'OPTIONS') {
    res.writeHead(200);
    res.end();
    return;
  }

  if (req.url === '/api/market/leading-indicators' && req.method === 'GET') {
    const data = generateMockData();
    res.writeHead(200);
    res.end(JSON.stringify(data));
  } else if (req.url === '/health' && req.method === 'GET') {
    res.writeHead(200);
    res.end(JSON.stringify({ status: 'ok', message: 'Mock API server running' }));
  } else {
    res.writeHead(404);
    res.end(JSON.stringify({ error: 'Not found' }));
  }
});

const PORT = 3002;
server.listen(PORT, () => {
  console.log(`\n✅ Mock API Server running at http://localhost:${PORT}`);
  console.log(`📊 Economic data endpoint: http://localhost:${PORT}/api/market/leading-indicators`);
  console.log(`🏥 Health check: http://localhost:${PORT}/health\n`);
});

process.on('SIGINT', () => {
  console.log('\n👋 Shutting down mock API server...');
  process.exit(0);
});
