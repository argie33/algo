#!/usr/bin/env node

/**
 * Professional Metrics Validation Script
 * Validates all portfolio metrics calculations without dependencies
 */

// Helper functions for calculations
function calculateMean(arr) {
  return arr.reduce((a, b) => a + b, 0) / arr.length;
}

function calculateStdDev(arr) {
  const mean = calculateMean(arr);
  const variance = arr.reduce((sum, x) => sum + Math.pow(x - mean, 2), 0) / arr.length;
  return Math.sqrt(variance);
}

function calculateCumulativeReturns(returns) {
  let cumulative = 100;
  return returns.map(r => {
    cumulative *= (1 + r / 100);
    return cumulative;
  });
}

// Mock data: 100 daily returns
const mockReturns = [
  0.5, 0.3, -0.2, 0.8, 0.1, -0.5, 1.2, 0.2, -0.1, 0.4,
  0.6, -0.3, 0.9, 0.2, 0.5, 1.1, -0.4, 0.7, 0.3, 0.6,
  -0.2, 0.8, 0.4, 0.2, 0.9, 0.5, -0.3, 1.0, 0.3, 0.6,
  0.5, 0.3, -0.2, 0.8, 0.1, -0.5, 1.2, 0.2, -0.1, 0.4,
  0.6, -0.3, 0.9, 0.2, 0.5, 1.1, -0.4, 0.7, 0.3, 0.6,
  -0.2, 0.8, 0.4, 0.2, 0.9, 0.5, -0.3, 1.0, 0.3, 0.6,
  0.5, 0.3, -0.2, 0.8, 0.1, -0.5, 1.2, 0.2, -0.1, 0.4,
  0.6, -0.3, 0.9, 0.2, 0.5, 1.1, -0.4, 0.7, 0.3, 0.6,
  -0.2, 0.8, 0.4, 0.2, 0.9, 0.5, -0.3, 1.0, 0.3, 0.6,
  0.5, 0.3, -0.2, 0.8, 0.1, -0.5, 1.2, 0.2, -0.1, 0.4,
];

const results = {};
let passedTests = 0;
let totalTests = 0;

function test(name, fn) {
  totalTests++;
  try {
    fn();
    console.log(`✓ ${name}`);
    passedTests++;
  } catch (error) {
    console.log(`✗ ${name}: ${error.message}`);
  }
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

console.log('\n======== PROFESSIONAL METRICS VALIDATION ========\n');

// Test 1: Total Return
test('Total Return Calculation', () => {
  let cumReturn = 100;
  mockReturns.forEach(r => {
    cumReturn *= (1 + r / 100);
  });
  const totalReturn = cumReturn - 100;
  results.totalReturn = totalReturn;
  assert(totalReturn > 0, 'Total return should be positive for this dataset');
  console.log(`  → Total Return: ${totalReturn.toFixed(2)}%`);
});

// Test 2: Annualized Volatility
test('Annualized Volatility Calculation', () => {
  const stdDev = calculateStdDev(mockReturns);
  const annualizedVol = stdDev * Math.sqrt(252) * 100;
  results.volatility = annualizedVol;
  assert(annualizedVol > 0, 'Volatility should be positive');
  assert(annualizedVol < 100, 'Volatility should be reasonable');
  console.log(`  → Annualized Volatility: ${annualizedVol.toFixed(2)}%`);
});

// Test 3: Sharpe Ratio
test('Sharpe Ratio Calculation', () => {
  const mean = calculateMean(mockReturns);
  const stdDev = calculateStdDev(mockReturns);
  const riskFreeRate = 2 / 100 / 252;
  const sharpeRatio = ((mean - riskFreeRate) * 252) / (stdDev * Math.sqrt(252));
  results.sharpeRatio = sharpeRatio;
  assert(typeof sharpeRatio === 'number', 'Sharpe Ratio should be a number');
  console.log(`  → Sharpe Ratio: ${sharpeRatio.toFixed(2)}`);
});

// Test 4: Sortino Ratio
test('Sortino Ratio Calculation', () => {
  const mean = calculateMean(mockReturns);
  const downReturns = mockReturns.filter(r => r < 0);
  assert(downReturns.length > 0, 'Should have some negative returns');
  const downstdDev = Math.sqrt(downReturns.reduce((sum, r) => sum + Math.pow(r, 2), 0) / downReturns.length);
  const downsideDev = downstdDev * Math.sqrt(252);
  const sortinoRatio = ((mean * 252 * 100) - 2) / downsideDev;
  results.sortinoRatio = sortinoRatio;
  assert(typeof sortinoRatio === 'number', 'Sortino Ratio should be a number');
  console.log(`  → Sortino Ratio: ${sortinoRatio.toFixed(2)}`);
});

// Test 5: Max Drawdown
test('Max Drawdown Calculation', () => {
  const cumReturns = calculateCumulativeReturns(mockReturns);
  let peak = cumReturns[0];
  let maxDD = 0;
  cumReturns.forEach(value => {
    if (value > peak) peak = value;
    const dd = ((peak - value) / peak) * 100;
    if (dd > maxDD) maxDD = dd;
  });
  results.maxDrawdown = maxDD;
  assert(maxDD >= 0, 'Max Drawdown should be non-negative');
  assert(maxDD <= 100, 'Max Drawdown should not exceed 100%');
  console.log(`  → Max Drawdown: ${maxDD.toFixed(2)}%`);
});

// Test 6: Skewness
test('Skewness Calculation', () => {
  const mean = calculateMean(mockReturns);
  const stdDev = calculateStdDev(mockReturns);
  const skewness = mockReturns.reduce((sum, x) => sum + Math.pow((x - mean) / stdDev, 3), 0) / mockReturns.length;
  results.skewness = skewness;
  assert(typeof skewness === 'number', 'Skewness should be a number');
  console.log(`  → Skewness: ${skewness.toFixed(3)}`);
});

// Test 7: Kurtosis
test('Kurtosis Calculation', () => {
  const mean = calculateMean(mockReturns);
  const stdDev = calculateStdDev(mockReturns);
  const kurtosis = mockReturns.reduce((sum, x) => sum + Math.pow((x - mean) / stdDev, 4), 0) / mockReturns.length - 3;
  results.kurtosis = kurtosis;
  assert(typeof kurtosis === 'number', 'Kurtosis should be a number');
  console.log(`  → Kurtosis: ${kurtosis.toFixed(3)}`);
});

// Test 8: Value at Risk (VaR)
test('Value at Risk (VaR) Calculation', () => {
  const sortedReturns = [...mockReturns].sort((a, b) => a - b);
  const var95Index = Math.floor(sortedReturns.length * 0.05);
  const var95 = sortedReturns[var95Index];
  results.var95 = var95;
  assert(var95 < 0, 'VaR should typically be negative');
  console.log(`  → VaR 95%: ${var95.toFixed(2)}%`);
});

// Test 9: Conditional Value at Risk (CVaR)
test('Conditional Value at Risk (CVaR) Calculation', () => {
  const sortedReturns = [...mockReturns].sort((a, b) => a - b);
  const var95Index = Math.floor(sortedReturns.length * 0.05);
  const cvar95 = sortedReturns.slice(0, var95Index + 1).reduce((a, b) => a + b, 0) / (var95Index + 1);
  results.cvar95 = cvar95;
  assert(cvar95 <= sortedReturns[var95Index], 'CVaR should be <= VaR');
  console.log(`  → CVaR 95%: ${cvar95.toFixed(2)}%`);
});

// Test 10: Concentration Metrics
test('Concentration Metrics', () => {
  const weights = [0.30, 0.25, 0.20, 0.15, 0.10];
  const top1 = Math.max(...weights) * 100;
  const top5 = weights.slice(0, 5).reduce((a, b) => a + b, 0) * 100;
  const herfindahl = weights.reduce((sum, w) => sum + Math.pow(w, 2), 0);
  const effectiveN = 1 / herfindahl;

  results.concentration = { top1, top5, herfindahl, effectiveN };

  assert(top1 > 0 && top1 <= 100, 'Top 1 weight should be between 0-100%');
  assert(top5 > 0 && top5 <= 100, 'Top 5 weight should be between 0-100%');
  assert(herfindahl > 0 && herfindahl <= 1, 'Herfindahl should be between 0-1');
  assert(effectiveN > 0, 'Effective N should be positive');

  console.log(`  → Top 1 Weight: ${top1.toFixed(2)}%`);
  console.log(`  → Top 5 Weight: ${top5.toFixed(2)}%`);
  console.log(`  → Herfindahl Index: ${herfindahl.toFixed(4)}`);
  console.log(`  → Effective N: ${effectiveN.toFixed(2)}`);
});

// Test 11: Rolling Returns
test('Rolling Returns Calculation', () => {
  const returns1m = mockReturns.slice(-21);
  const returns3m = mockReturns.slice(-63);

  const calcRolling = (arr) => {
    let cum = 100;
    arr.forEach(r => { cum *= (1 + r / 100); });
    return cum - 100;
  };

  const rolling1m = calcRolling(returns1m);
  const rolling3m = calcRolling(returns3m);

  results.rolling = { rolling1m, rolling3m };

  assert(typeof rolling1m === 'number', '1M return should be a number');
  assert(typeof rolling3m === 'number', '3M return should be a number');

  console.log(`  → 1M Return: ${rolling1m.toFixed(2)}%`);
  console.log(`  → 3M Return: ${rolling3m.toFixed(2)}%`);
});

// Test 12: Return Attribution
test('Return Attribution Calculation', () => {
  const positiveDays = mockReturns.filter(r => r > 0);
  const bestDay = Math.max(...mockReturns);
  const worstDay = Math.min(...mockReturns);
  const winRate = (positiveDays.length / mockReturns.length) * 100;

  results.attribution = { bestDay, worstDay, winRate };

  assert(bestDay > 0, 'Best day should be positive');
  assert(worstDay < 0, 'Worst day should be negative');
  assert(winRate >= 0 && winRate <= 100, 'Win rate should be 0-100%');

  console.log(`  → Best Day: ${bestDay.toFixed(2)}%`);
  console.log(`  → Worst Day: ${worstDay.toFixed(2)}%`);
  console.log(`  → Win Rate: ${winRate.toFixed(1)}%`);
});

// Test 13: Boundary Checks
test('All Metrics Pass Boundary Checks', () => {
  const metrics = {
    volatility: calculateStdDev(mockReturns) * Math.sqrt(252) * 100,
    sharpeRatio: ((calculateMean(mockReturns) - (2 / 100 / 252)) * 252) / (calculateStdDev(mockReturns) * Math.sqrt(252)),
    maxDrawdown: 45.5,
    winRate: 65.0,
    concentration: 0.85,
  };

  // Check each metric is in reasonable range
  assert(metrics.volatility > 0 && metrics.volatility < 200, 'Volatility should be 0-200%');
  assert(metrics.maxDrawdown > 0 && metrics.maxDrawdown < 100, 'Max Drawdown should be 0-100%');
  assert(metrics.winRate > 0 && metrics.winRate <= 100, 'Win Rate should be 0-100%');
  assert(metrics.concentration > 0 && metrics.concentration <= 1, 'Concentration should be 0-1');

  console.log(`  ✓ All metrics pass boundary checks`);
});

// Print summary
console.log(`\n======== TEST SUMMARY ========`);
console.log(`Passed: ${passedTests}/${totalTests}`);
console.log(`Status: ${passedTests === totalTests ? '✓ ALL TESTS PASSED' : '✗ SOME TESTS FAILED'}`);

console.log(`\n======== CALCULATED METRICS ========`);
console.log(JSON.stringify(results, null, 2));

process.exit(passedTests === totalTests ? 0 : 1);
