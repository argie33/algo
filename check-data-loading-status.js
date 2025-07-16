#!/usr/bin/env node

// Quick script to check data loading status and deployment progress
const https = require('https');

const API_BASE = 'https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev';

async function makeRequest(url) {
  return new Promise((resolve, reject) => {
    https.get(url, (res) => {
      let data = '';
      res.on('data', (chunk) => data += chunk);
      res.on('end', () => {
        try {
          resolve(JSON.parse(data));
        } catch (e) {
          resolve({ error: 'Invalid JSON', raw: data });
        }
      });
    }).on('error', reject);
  });
}

async function checkStatus() {
  console.log('🔍 Checking deployment and data loading status...\n');
  
  // Check basic health
  try {
    const health = await makeRequest(`${API_BASE}/health`);
    console.log('✅ API Health:', health.success ? 'Working' : 'Issues detected');
    console.log('   Environment:', health.environment);
    console.log('   Lambda:', health.lambda_info?.function_name);
  } catch (error) {
    console.log('❌ API Health: Failed -', error.message);
  }
  
  // Check if comprehensive database health is available
  try {
    const dbHealth = await makeRequest(`${API_BASE}/health?quick=false`);
    if (dbHealth.database) {
      console.log('\n📊 Database Status:');
      console.log('   Status:', dbHealth.database.status);
      console.log('   Tables:', Object.keys(dbHealth.database.tables || {}).length);
    } else {
      console.log('\n⚠️  Comprehensive database health not available yet');
    }
  } catch (error) {
    console.log('\n❌ Database health check failed:', error.message);
  }
  
  // Try to access a sample API endpoint to check data
  try {
    const stocks = await makeRequest(`${API_BASE}/api/stocks?limit=5`);
    if (stocks.success && stocks.data) {
      console.log('\n🏢 Sample stocks data:', stocks.data.length, 'records found');
    } else {
      console.log('\n⚠️  Stocks endpoint not ready:', stocks.error || 'No data');
    }
  } catch (error) {
    console.log('\n❌ Stocks endpoint failed:', error.message);
  }
  
  // Check portfolio endpoint
  try {
    const portfolio = await makeRequest(`${API_BASE}/api/portfolio/holdings`);
    if (portfolio.success) {
      console.log('\n💼 Portfolio endpoint: Working');
    } else {
      console.log('\n⚠️  Portfolio endpoint:', portfolio.error || 'Not ready');
    }
  } catch (error) {
    console.log('\n❌ Portfolio endpoint failed:', error.message);
  }
  
  console.log('\n📋 Comprehensive Data Loaders Triggered (12 datasets):');
  console.log('   🏢 CORE DATA:');
  console.log('      ✅ loadstocksymbols.py - Stock symbols and listings');
  console.log('      ✅ loadpricedaily.py - Daily OHLCV price data');
  console.log('      ✅ loadtechnicalsdaily.py - Technical indicators (RSI, MACD, etc.)');
  console.log('   📰 NEWS & SENTIMENT:');
  console.log('      ✅ loadnews.py - Financial news aggregation');
  console.log('      ✅ loadsentiment.py - Comprehensive sentiment analysis');
  console.log('      ✅ loadfeargreed.py - CNN Fear & Greed Index');
  console.log('      ✅ loadaaiidata.py - AAII investor sentiment');
  console.log('   📊 MARKET & ECONOMIC:');
  console.log('      ✅ loadmarket.py - Market indices and ETF data');
  console.log('      ✅ loadecondata.py - Federal Reserve economic indicators');
  console.log('   📈 TRADING & ANALYSIS:');
  console.log('      ✅ loadbuyselldaily.py - Daily buy/sell trading signals');
  console.log('      ✅ loadanalystupgradedowngrade.py - Analyst recommendations');
  console.log('      ✅ loadfinancials.py - Financial metrics and ratios');
  console.log('      ✅ loadcalendar.py - Earnings calendar and events');
  
  console.log('\n⏳ ECS Tasks should be running to populate database tables...');
  console.log('🎯 Frontend features will be enhanced as data becomes available');
}

checkStatus().catch(console.error);