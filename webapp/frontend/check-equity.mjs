const r = await fetch('http://localhost:3001/api/algo/equity-curve?limit=5');
const json = await r.json();
console.log('Full response keys:', Object.keys(json));
console.log('Items count:', json.items?.length);
if (json.items?.length > 0) {
  console.log('First item keys:', Object.keys(json.items[0]));
  console.log('First item:', JSON.stringify(json.items[0], null, 2));
}
// Also check positions items
const r2 = await fetch('http://localhost:3001/api/algo/positions');
const j2 = await r2.json();
const data2 = j2.data || j2;
console.log('\n=== POSITIONS ===');
if (data2.items?.length > 0) {
  console.log('Position keys:', Object.keys(data2.items[0]));
}

// Check trades
const r3 = await fetch('http://localhost:3001/api/algo/trades?limit=3');
const j3 = await r3.json();
const data3 = j3.data || j3;
console.log('\n=== TRADES ===');
if (data3.items?.length > 0) {
  console.log('Trade keys:', Object.keys(data3.items[0]));
}

// Check performance-analytics
const r4 = await fetch('http://localhost:3001/api/algo/performance-analytics');
const j4 = await r4.json();
const data4 = j4.data || j4;
console.log('\n=== PERFORMANCE ANALYTICS ===');
console.log(JSON.stringify(data4, null, 2).substring(0, 1000));

// Check risk-metrics
const r5 = await fetch('http://localhost:3001/api/algo/risk-metrics');
const j5 = await r5.json();
const data5 = j5.data || j5;
console.log('\n=== RISK METRICS ===');
console.log(JSON.stringify(data5, null, 2).substring(0, 1000));
