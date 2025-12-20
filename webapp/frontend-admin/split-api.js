#!/usr/bin/env node
/**
 * Split monolithic api.js into domain-specific modules
 * This script categorizes the 173 API functions and creates separate files
 */

const fs = require('fs');
const _path = require('path');

const apiFile = 'src/services/api.js';
const content = fs.readFileSync(apiFile, 'utf8');
const lines = content.split('\n');

// Extract helper functions and imports (first ~850 lines)
let _helperStart = 0;
let helperEnd = 0;
for (let i = 0; i < lines.length; i++) {
  if (lines[i].match(/^export const getMarketOverview/)) {
    helperEnd = i;
    break;
  }
}

const _helpers = lines.slice(0, helperEnd).join('\n');

// Categorize functions
const functionsByCategory = {
  market: [],
  stocks: [],
  portfolio: [],
  trading: [],
  dashboard: [],
  utils: []
};

let _currentFuncStart = helperEnd;
for (let i = helperEnd; i < lines.length; i++) {
  if (lines[i].match(/^export const (\w+)/)) {
    const match = lines[i].match(/^export const (\w+)/);
    const funcName = match[1];

    // Categorize
    let cat = 'utils';
    if (funcName.match(/^get(Portfolio|Risk|ApiKeys|Holding|Import|Benchmark|Factor|Performance|Analytics|Optimization|Sector|Industry)/)) cat = 'portfolio';
    else if (funcName.match(/^get(Market|Sector|Economic|Distribution|Seasonality|McClellan|Yield|Sentiment|Breadth|Correlation|Trends|Volatility|Internals|Indices|Commentary|Indicators)/)) cat = 'market';
    else if (funcName.match(/^get(Stock|Quote|History|Technical|Financial|Analyst|Earnings|Dividend|KeyMetrics|Price|Profile|Recommendations|Info|Metrics|Strength)/)) cat = 'stocks';
    else if (funcName.match(/^(get.*Signal|getBuySignals|getSellSignals|getTrading|placeOrder|getOrder|applyPortfolio|getTrade|subscribe)/)) cat = 'trading';
    else if (funcName.match(/^get(Dashboard|Summary|Alerts|Debug|Health|User|Symbols|WatchList|EarningsCalendar|FinancialHighlights|Diagnostic|DataValidation|DatabaseHealth)/)) cat = 'dashboard';

    functionsByCategory[cat].push({ name: funcName, line: i });
  }
}

console.log('Split Analysis:');
Object.entries(functionsByCategory).forEach(([cat, funcs]) => {
  if (funcs.length > 0) {
    console.log(`  ${cat}: ${funcs.length} functions`);
  }
});

console.log('\nTo implement split:');
console.log('1. Create: src/services/api/core.js (helpers, config, axios setup)');
console.log('2. Create: src/services/api/market.js (market APIs)');
console.log('3. Create: src/services/api/stocks.js (stock APIs)');
console.log('4. Create: src/services/api/portfolio.js (portfolio APIs)');
console.log('5. Create: src/services/api/trading.js (trading APIs)');
console.log('6. Create: src/services/api/dashboard.js (dashboard APIs)');
console.log('7. Create: src/services/api/utils.js (utility APIs)');
console.log('8. Update: src/services/api.js (re-export all from submodules)');
console.log('9. Update: All 29 importing files (keep imports the same, they work with re-exports)');
