// Check risk metrics and portfolio values
const r1 = await fetch('http://localhost:3001/api/algo/risk-metrics');
const j1 = await r1.json();
console.log('=== RISK METRICS ===');
console.log(JSON.stringify(j1.data, null, 2));

const r2 = await fetch('http://localhost:3001/api/algo/portfolio');
const j2 = await r2.json();
console.log('\n=== PORTFOLIO ===');
console.log(JSON.stringify(j2.data, null, 2));

const r3 = await fetch('http://localhost:3001/api/algo/positions');
const j3 = await r3.json();
console.log('\n=== POSITIONS SUMMARY ===');
const positions = j3.data?.items || [];
console.log('Count:', positions.length);
positions.forEach(p => {
  console.log(`  ${p.symbol}: qty=${p.quantity}, price=$${p.current_price}, value=$${p.position_value}, pnl_pct=${p.unrealized_pnl_pct}%`);
});

const r4 = await fetch('http://localhost:3001/api/algo/circuit-breakers');
const j4 = await r4.json();
console.log('\n=== CIRCUIT BREAKERS ===');
j4.data?.breakers?.forEach(b => {
  const icon = b.triggered ? '❌' : '✅';
  console.log(`  ${icon} ${b.label}: current=${b.current} vs threshold=${b.threshold}${b.unit}`);
});

const r5 = await fetch('http://localhost:3001/api/algo/performance');
const j5 = await r5.json();
console.log('\n=== PERFORMANCE ===');
const perf = j5.data;
console.log(`  Trades: total=${perf?.total_trades}, wins=${perf?.winning_trades}, losses=${perf?.losing_trades}`);
console.log(`  Win rate: ${perf?.win_rate_pct}%`);
console.log(`  PnL: $${perf?.total_pnl_dollars} (${perf?.total_pnl_pct}%)`);
console.log(`  Sharpe: ${perf?.sharpe_ratio}`);
console.log(`  Profit factor: ${perf?.profit_factor}`);
console.log(`  Total return: ${perf?.total_return_pct}%`);

// Check holding period distribution
const r6 = await fetch('http://localhost:3001/api/algo/holding-period-distribution');
const j6 = await r6.json();
console.log('\n=== HOLDING PERIOD DISTRIBUTION ===');
console.log(JSON.stringify(j6.data || j6, null, 2));

// Check sentiment
const r7 = await fetch('http://localhost:3001/api/algo/sentiment');
const j7 = await r7.json();
console.log('\n=== SENTIMENT ===');
console.log(JSON.stringify(j7.data, null, 2));
