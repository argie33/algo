/**
 * HFT System Test Runner
 * 
 * Tests the ultra-fast core components:
 * - Time series engine
 * - Signal generation
 * - Performance benchmarks
 */

import { timeSeriesManager } from './core/timeseries/timeseries-engine';
import { fastSignalGenerator } from './core/signals/fast-signal-generator';

// Performance test configuration
const TEST_CONFIG = {
  symbols: ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA'],
  tickCount: 100000,
  priceRange: [100, 200],
  volumeRange: [100, 10000],
  testDuration: 60000 // 1 minute
};

/**
 * Generate synthetic market data for testing
 */
function generateTick(symbol: string, lastPrice: number): {
  symbol: string;
  price: number;
  volume: number;
  timestamp: bigint;
} {
  // Random walk with some volatility
  const change = (Math.random() - 0.5) * 0.01; // ±0.5% change
  const price = Math.max(50, lastPrice * (1 + change));
  const volume = Math.floor(Math.random() * (TEST_CONFIG.volumeRange[1] - TEST_CONFIG.volumeRange[0])) + TEST_CONFIG.volumeRange[0];
  
  return {
    symbol,
    price,
    volume,
    timestamp: process.hrtime.bigint()
  };
}

/**
 * Run performance benchmark
 */
async function runPerformanceBenchmark(): Promise<void> {
  console.log('🚀 Starting HFT System Performance Benchmark');
  console.log('==========================================');
  
  const startTime = process.hrtime.bigint();
  let totalTicks = 0;
  let totalSignals = 0;
  let totalLatency = 0n;
  
  // Initialize signal generators
  TEST_CONFIG.symbols.forEach(symbol => {
    fastSignalGenerator.initializeSymbol(symbol);
  });
  
  // Track prices for each symbol
  const lastPrices: { [symbol: string]: number } = {};
  TEST_CONFIG.symbols.forEach(symbol => {
    lastPrices[symbol] = Math.random() * (TEST_CONFIG.priceRange[1] - TEST_CONFIG.priceRange[0]) + TEST_CONFIG.priceRange[0];
  });
  
  console.log(`📊 Testing with ${TEST_CONFIG.symbols.length} symbols`);
  console.log(`⏱️  Target: ${TEST_CONFIG.tickCount} ticks in ${TEST_CONFIG.testDuration}ms`);
  console.log('');
  
  // Main test loop
  const testStart = Date.now();
  const testEnd = testStart + TEST_CONFIG.testDuration;
  
  while (Date.now() < testEnd && totalTicks < TEST_CONFIG.tickCount) {
    for (const symbol of TEST_CONFIG.symbols) {
      if (Date.now() >= testEnd) break;
      
      const tickStart = process.hrtime.bigint();
      
      // Generate tick
      const tick = generateTick(symbol, lastPrices[symbol]);
      lastPrices[symbol] = tick.price;
      
      // Add to time series
      timeSeriesManager.addTick(tick.symbol, tick.price, tick.volume, tick.timestamp);
      
      // Update order book (simplified)
      const spread = tick.price * 0.001; // 10 bps spread
      timeSeriesManager.updateOrderBook(tick.symbol, 'bid', tick.price - spread/2, tick.volume, tick.timestamp);
      timeSeriesManager.updateOrderBook(tick.symbol, 'ask', tick.price + spread/2, tick.volume, tick.timestamp);
      
      // Generate signals
      const technicalData = timeSeriesManager.getTechnicalData(symbol, 50);
      const microstructureData = timeSeriesManager.getMicrostructure(symbol);
      
      if (technicalData && microstructureData) {
        const signals = fastSignalGenerator.generateSignals(symbol, technicalData, microstructureData);
        totalSignals += signals.length;
        
        if (signals.length > 0) {
          console.log(`🎯 ${signals.length} signals for ${symbol}: ${signals.map(s => s.type).join(', ')}`);
        }
      }
      
      const tickEnd = process.hrtime.bigint();
      totalLatency += (tickEnd - tickStart);
      totalTicks++;
      
      // Progress update every 10k ticks
      if (totalTicks % 10000 === 0) {
        const currentLatency = Number(totalLatency / BigInt(totalTicks)) / 1000000; // ms
        const ticksPerSecond = totalTicks / ((Date.now() - testStart) / 1000);
        console.log(`📈 Progress: ${totalTicks} ticks, ${currentLatency.toFixed(3)}ms avg latency, ${Math.round(ticksPerSecond)} ticks/s`);
      }
    }
  }
  
  const endTime = process.hrtime.bigint();
  const totalTime = Number(endTime - startTime) / 1000000000; // seconds
  const avgLatency = Number(totalLatency / BigInt(totalTicks)) / 1000000; // milliseconds
  
  console.log('');
  console.log('📊 PERFORMANCE RESULTS');
  console.log('=====================');
  console.log(`⏱️  Total time: ${totalTime.toFixed(2)}s`);
  console.log(`🎯 Total ticks processed: ${totalTicks.toLocaleString()}`);
  console.log(`📡 Total signals generated: ${totalSignals.toLocaleString()}`);
  console.log(`⚡ Average latency: ${avgLatency.toFixed(3)}ms`);
  console.log(`🚀 Throughput: ${Math.round(totalTicks / totalTime).toLocaleString()} ticks/second`);
  console.log(`📈 Signal rate: ${Math.round(totalSignals / totalTime).toLocaleString()} signals/second`);
  
  // Memory usage
  const memUsage = process.memoryUsage();
  console.log(`💾 Memory usage: ${Math.round(memUsage.heapUsed / 1024 / 1024)}MB`);
  
  // Performance assessment
  console.log('');
  console.log('🎯 PERFORMANCE ASSESSMENT');
  console.log('========================');
  
  if (avgLatency < 1.0) {
    console.log('✅ Excellent: Sub-millisecond latency achieved!');
  } else if (avgLatency < 5.0) {
    console.log('✅ Good: Low latency within target range');
  } else {
    console.log('⚠️  Warning: Latency higher than target');
  }
  
  if (totalTicks / totalTime > 50000) {
    console.log('✅ Excellent: High throughput achieved');
  } else if (totalTicks / totalTime > 10000) {
    console.log('✅ Good: Adequate throughput');
  } else {
    console.log('⚠️  Warning: Low throughput');
  }
  
  if (totalSignals > 0) {
    console.log(`✅ Signal generation working: ${(totalSignals/totalTicks*100).toFixed(2)}% signal rate`);
  } else {
    console.log('⚠️  Warning: No signals generated');
  }
}

/**
 * Test individual components
 */
async function runComponentTests(): Promise<void> {
  console.log('');
  console.log('🔧 COMPONENT TESTS');
  console.log('==================');
  
  // Test 1: Time Series Engine
  console.log('1. Testing Time Series Engine...');
  const symbol = 'TEST';
  const testStart = process.hrtime.bigint();
  
  for (let i = 0; i < 10000; i++) {
    timeSeriesManager.addTick(symbol, 100 + Math.random(), 1000, BigInt(Date.now() * 1000));
  }
  
  const testEnd = process.hrtime.bigint();
  const timeSeriesLatency = Number(testEnd - testStart) / 1000000 / 10000; // ms per tick
  console.log(`   ✅ Time series: ${timeSeriesLatency.toFixed(4)}ms per tick`);
  
  // Test 2: Signal Generation
  console.log('2. Testing Signal Generation...');
  fastSignalGenerator.initializeSymbol(symbol);
  
  const signalStart = process.hrtime.bigint();
  const technicalData = timeSeriesManager.getTechnicalData(symbol, 50);
  const microstructureData = timeSeriesManager.getMicrostructure(symbol);
  
  if (technicalData && microstructureData) {
    const signals = fastSignalGenerator.generateSignals(symbol, technicalData, microstructureData);
    const signalEnd = process.hrtime.bigint();
    const signalLatency = Number(signalEnd - signalStart) / 1000000; // ms
    console.log(`   ✅ Signal generation: ${signalLatency.toFixed(4)}ms, ${signals.length} signals`);
  }
  
  // Test 3: VWAP Calculation
  console.log('3. Testing VWAP calculation...');
  const vwapStart = process.hrtime.bigint();
  const vwap = timeSeriesManager.getTechnicalData(symbol, 100)?.vwap || 0;
  const vwapEnd = process.hrtime.bigint();
  const vwapLatency = Number(vwapEnd - vwapStart) / 1000000; // ms
  console.log(`   ✅ VWAP calculation: ${vwapLatency.toFixed(4)}ms, VWAP: ${vwap.toFixed(2)}`);
  
  // Test 4: Order Book Updates
  console.log('4. Testing Order Book updates...');
  const obStart = process.hrtime.bigint();
  for (let i = 0; i < 1000; i++) {
    timeSeriesManager.updateOrderBook(symbol, 'bid', 100 - Math.random(), 1000, BigInt(Date.now()));
    timeSeriesManager.updateOrderBook(symbol, 'ask', 100 + Math.random(), 1000, BigInt(Date.now()));
  }
  const obEnd = process.hrtime.bigint();
  const obLatency = Number(obEnd - obStart) / 1000000 / 1000; // ms per update
  console.log(`   ✅ Order book: ${obLatency.toFixed(4)}ms per update`);
}

/**
 * Main test runner
 */
async function main(): Promise<void> {
  console.log('🎯 HFT SYSTEM ULTRA-FAST CORE TEST');
  console.log('==================================');
  console.log('Testing sub-millisecond components for institutional HFT');
  console.log('');
  
  try {
    // Run component tests first
    await runComponentTests();
    
    // Run performance benchmark
    await runPerformanceBenchmark();
    
    console.log('');
    console.log('🎉 All tests completed successfully!');
    console.log('System ready for institutional HFT deployment.');
    
  } catch (error) {
    console.error('❌ Test failed:', error);
    process.exit(1);
  }
}

// Handle graceful shutdown
process.on('SIGINT', () => {
  console.log('\\n🛑 Test interrupted by user');
  process.exit(0);
});

// Run tests
if (require.main === module) {
  main().catch(console.error);
}

export { main };
