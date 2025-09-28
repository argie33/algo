const request = require('supertest');

const app = require('./server');

async function testStrategyBacktest() {
  console.log(`Testing AI strategy backtest`);
  const response = await request(app)
    .post("/api/strategies/run-ai-strategy")
    .set("Authorization", "Bearer dev-bypass-token")
    .send({
      strategy: {
        name: "Test Strategy",
        code: "function onTick(data) { return 'HOLD'; }",
        symbols: ["AAPL"],
      },
      symbols: ["AAPL"],
      config: {
        startDate: "2023-01-01",
        endDate: "2023-12-31",
        initialCapital: 100000,
      },
    });

  console.log(`  Status: ${response.status}`);
  console.log(`  Body: ${JSON.stringify(response.body, null, 2)}`);
}

testStrategyBacktest().then(() => {
  console.log('Debug test complete');
  process.exit(0);
}).catch(err => {
  console.error('Debug test failed:', err);
  process.exit(1);
});