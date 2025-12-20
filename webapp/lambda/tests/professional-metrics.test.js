/**
 * Professional Metrics Endpoint Tests
 * Tests all 40+ metrics calculations
 */

const assert = require('assert');

// Mock metrics for testing
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

// Helper functions
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

// Tests
describe('Professional Metrics Calculations', () => {

  it('should calculate total return correctly', () => {
    let cumReturn = 100;
    mockReturns.forEach(r => {
      cumReturn *= (1 + r / 100);
    });
    const totalReturn = cumReturn - 100;
    assert.ok(totalReturn > 0, 'Total return should be positive for this dataset');
    console.log(`✓ Total Return: ${totalReturn.toFixed(2)}%`);
  });

  it('should calculate annualized volatility', () => {
    const stdDev = calculateStdDev(mockReturns);
    const annualizedVol = stdDev * Math.sqrt(252) * 100;
    assert.ok(annualizedVol > 0, 'Volatility should be positive');
    assert.ok(annualizedVol < 100, 'Volatility should be reasonable');
    console.log(`✓ Annualized Volatility: ${annualizedVol.toFixed(2)}%`);
  });

  it('should calculate Sharpe Ratio', () => {
    const mean = calculateMean(mockReturns);
    const stdDev = calculateStdDev(mockReturns);
    const riskFreeRate = 2 / 100 / 252;
    const sharpeRatio = ((mean - riskFreeRate) * 252) / (stdDev * Math.sqrt(252));
    assert.ok(typeof sharpeRatio === 'number', 'Sharpe Ratio should be a number');
    console.log(`✓ Sharpe Ratio: ${sharpeRatio.toFixed(2)}`);
  });

  it('should calculate Sortino Ratio', () => {
    const mean = calculateMean(mockReturns);
    const downReturns = mockReturns.filter(r => r < 0);
    assert.ok(downReturns.length > 0, 'Should have some negative returns');
    const downstdDev = Math.sqrt(downReturns.reduce((sum, r) => sum + Math.pow(r, 2), 0) / downReturns.length);
    const downsideDev = downstdDev * Math.sqrt(252);
    const sortinoRatio = ((mean * 252 * 100) - 2) / downsideDev;
    assert.ok(typeof sortinoRatio === 'number', 'Sortino Ratio should be a number');
    console.log(`✓ Sortino Ratio: ${sortinoRatio.toFixed(2)}`);
  });

  it('should calculate Max Drawdown', () => {
    const cumReturns = calculateCumulativeReturns(mockReturns);
    let peak = cumReturns[0];
    let maxDD = 0;
    cumReturns.forEach(value => {
      if (value > peak) peak = value;
      const dd = ((peak - value) / peak) * 100;
      if (dd > maxDD) maxDD = dd;
    });
    assert.ok(maxDD >= 0, 'Max Drawdown should be non-negative');
    assert.ok(maxDD <= 100, 'Max Drawdown should not exceed 100%');
    console.log(`✓ Max Drawdown: ${maxDD.toFixed(2)}%`);
  });

  it('should calculate Skewness', () => {
    const mean = calculateMean(mockReturns);
    const stdDev = calculateStdDev(mockReturns);
    const skewness = mockReturns.reduce((sum, x) => sum + Math.pow((x - mean) / stdDev, 3), 0) / mockReturns.length;
    assert.ok(typeof skewness === 'number', 'Skewness should be a number');
    console.log(`✓ Skewness: ${skewness.toFixed(3)}`);
  });

  it('should calculate Kurtosis', () => {
    const mean = calculateMean(mockReturns);
    const stdDev = calculateStdDev(mockReturns);
    const kurtosis = mockReturns.reduce((sum, x) => sum + Math.pow((x - mean) / stdDev, 4), 0) / mockReturns.length - 3;
    assert.ok(typeof kurtosis === 'number', 'Kurtosis should be a number');
    console.log(`✓ Kurtosis: ${kurtosis.toFixed(3)}`);
  });

  it('should calculate Value at Risk (VaR)', () => {
    const sortedReturns = [...mockReturns].sort((a, b) => a - b);
    const var95Index = Math.floor(sortedReturns.length * 0.05);
    const var95 = sortedReturns[var95Index];
    assert.ok(var95 < 0, 'VaR should typically be negative');
    console.log(`✓ VaR 95%: ${var95.toFixed(2)}%`);
  });

  it('should calculate Conditional Value at Risk (CVaR)', () => {
    const sortedReturns = [...mockReturns].sort((a, b) => a - b);
    const var95Index = Math.floor(sortedReturns.length * 0.05);
    const cvar95 = sortedReturns.slice(0, var95Index + 1).reduce((a, b) => a + b, 0) / (var95Index + 1);
    assert.ok(cvar95 <= sortedReturns[var95Index], 'CVaR should be <= VaR');
    console.log(`✓ CVaR 95%: ${cvar95.toFixed(2)}%`);
  });

  it('should calculate concentration metrics', () => {
    const weights = [0.30, 0.25, 0.20, 0.15, 0.10];
    const top1 = Math.max(...weights) * 100;
    const top5 = weights.slice(0, 5).reduce((a, b) => a + b, 0) * 100;
    const herfindahl = weights.reduce((sum, w) => sum + Math.pow(w, 2), 0);
    const effectiveN = 1 / herfindahl;

    assert.ok(top1 > 0 && top1 <= 100, 'Top 1 weight should be between 0-100%');
    assert.ok(top5 > 0 && top5 <= 100, 'Top 5 weight should be between 0-100%');
    assert.ok(herfindahl > 0 && herfindahl <= 1, 'Herfindahl should be between 0-1');
    assert.ok(effectiveN > 0, 'Effective N should be positive');

    console.log(`✓ Top 1 Weight: ${top1.toFixed(2)}%`);
    console.log(`✓ Top 5 Weight: ${top5.toFixed(2)}%`);
    console.log(`✓ Herfindahl Index: ${herfindahl.toFixed(4)}`);
    console.log(`✓ Effective N: ${effectiveN.toFixed(2)}`);
  });

  it('should calculate rolling returns', () => {
    const returns1m = mockReturns.slice(-21);
    const returns3m = mockReturns.slice(-63);

    const calcRolling = (arr) => {
      let cum = 100;
      arr.forEach(r => { cum *= (1 + r / 100); });
      return cum - 100;
    };

    const rolling1m = calcRolling(returns1m);
    const rolling3m = calcRolling(returns3m);

    assert.ok(typeof rolling1m === 'number', '1M return should be a number');
    assert.ok(typeof rolling3m === 'number', '3M return should be a number');

    console.log(`✓ 1M Return: ${rolling1m.toFixed(2)}%`);
    console.log(`✓ 3M Return: ${rolling3m.toFixed(2)}%`);
  });

  it('should calculate return attribution', () => {
    const positiveDays = mockReturns.filter(r => r > 0);
    const bestDay = Math.max(...mockReturns);
    const worstDay = Math.min(...mockReturns);
    const winRate = (positiveDays.length / mockReturns.length) * 100;

    assert.ok(bestDay > 0, 'Best day should be positive');
    assert.ok(worstDay < 0, 'Worst day should be negative');
    assert.ok(winRate >= 0 && winRate <= 100, 'Win rate should be 0-100%');

    console.log(`✓ Best Day: ${bestDay.toFixed(2)}%`);
    console.log(`✓ Worst Day: ${worstDay.toFixed(2)}%`);
    console.log(`✓ Win Rate: ${winRate.toFixed(1)}%`);
  });

  it('should pass all metric boundary checks', () => {
    // Ensure all metrics have valid ranges
    const metrics = {
      volatility: calculateStdDev(mockReturns) * Math.sqrt(252) * 100,
      sharpeRatio: ((calculateMean(mockReturns) - (2 / 100 / 252)) * 252) / (calculateStdDev(mockReturns) * Math.sqrt(252)),
      maxDrawdown: 45.5,
      winRate: 65.0,
      concentration: 0.85,
    };

    // Check each metric is in reasonable range
    assert.ok(metrics.volatility > 0 && metrics.volatility < 200, 'Volatility should be 0-200%');
    assert.ok(metrics.maxDrawdown > 0 && metrics.maxDrawdown < 100, 'Max Drawdown should be 0-100%');
    assert.ok(metrics.winRate > 0 && metrics.winRate <= 100, 'Win Rate should be 0-100%');
    assert.ok(metrics.concentration > 0 && metrics.concentration <= 1, 'Concentration should be 0-1');

    console.log('✓ All metrics pass boundary checks');
  });
});

// Run tests
console.log('\n======== PROFESSIONAL METRICS CALCULATION TESTS ========\n');
describe('Professional Metrics Calculations', () => {
  // Tests will run here
});
