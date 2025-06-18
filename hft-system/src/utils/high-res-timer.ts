/**
 * High-Resolution Timer for Ultra-Low Latency Measurements
 * 
 * Features:
 * - Nanosecond precision using process.hrtime.bigint()
 * - Optimized for frequent timing measurements
 * - Minimal memory allocation
 * - Cross-platform compatibility
 */

export class HighResTimer {
  private startTime: bigint = 0n;
  
  /**
   * Get current high-resolution timestamp in nanoseconds
   */
  now(): bigint {
    return process.hrtime.bigint();
  }
  
  /**
   * Get current timestamp in microseconds
   */
  nowMicros(): number {
    return Number(process.hrtime.bigint()) / 1000;
  }
  
  /**
   * Get current timestamp in milliseconds with sub-millisecond precision
   */
  nowMillis(): number {
    return Number(process.hrtime.bigint()) / 1_000_000;
  }
  
  /**
   * Start timing operation
   */
  start(): bigint {
    this.startTime = this.now();
    return this.startTime;
  }
  
  /**
   * Get elapsed time in nanoseconds
   */
  elapsed(startTime?: bigint): number {
    const start = startTime || this.startTime;
    return Number(this.now() - start);
  }
  
  /**
   * Get elapsed time in microseconds
   */
  elapsedMicros(startTime?: bigint): number {
    return this.elapsed(startTime) / 1000;
  }
  
  /**
   * Get elapsed time in milliseconds
   */
  elapsedMillis(startTime?: bigint): number {
    return this.elapsed(startTime) / 1_000_000;
  }
  
  /**
   * Time a function execution
   */
  time<T>(fn: () => T): { result: T; timeNanos: number; timeMicros: number } {
    const start = this.now();
    const result = fn();
    const timeNanos = this.elapsed(start);
    
    return {
      result,
      timeNanos,
      timeMicros: timeNanos / 1000
    };
  }
  
  /**
   * Time an async function execution
   */
  async timeAsync<T>(fn: () => Promise<T>): Promise<{ result: T; timeNanos: number; timeMicros: number }> {
    const start = this.now();
    const result = await fn();
    const timeNanos = this.elapsed(start);
    
    return {
      result,
      timeNanos,
      timeMicros: timeNanos / 1000
    };
  }
  
  /**
   * Create a benchmark function
   */
  benchmark(name: string, iterations: number, fn: () => void): {
    name: string;
    iterations: number;
    totalTimeNanos: number;
    avgTimeNanos: number;
    avgTimeMicros: number;
    opsPerSecond: number;
  } {
    const start = this.now();
    
    for (let i = 0; i < iterations; i++) {
      fn();
    }
    
    const totalTimeNanos = this.elapsed(start);
    const avgTimeNanos = totalTimeNanos / iterations;
    
    return {
      name,
      iterations,
      totalTimeNanos,
      avgTimeNanos,
      avgTimeMicros: avgTimeNanos / 1000,
      opsPerSecond: (iterations / totalTimeNanos) * 1_000_000_000
    };
  }
  
  /**
   * Sleep for specified microseconds (high precision)
   */
  async sleepMicros(microseconds: number): Promise<void> {
    const start = this.now();
    const targetNanos = microseconds * 1000;
    
    return new Promise((resolve) => {
      const checkTime = () => {
        if (this.elapsed(start) >= targetNanos) {
          resolve();
        } else {
          setImmediate(checkTime);
        }
      };
      checkTime();
    });
  }
  
  /**
   * Measure latency statistics over multiple samples
   */
  measureLatency(samples: number, fn: () => void): {
    samples: number;
    minNanos: number;
    maxNanos: number;
    avgNanos: number;
    medianNanos: number;
    p95Nanos: number;
    p99Nanos: number;
    minMicros: number;
    maxMicros: number;
    avgMicros: number;
    medianMicros: number;
    p95Micros: number;
    p99Micros: number;
  } {    const measurements: number[] = [];
    
    // Warm up
    for (let i = 0; i < 10; i++) {
      fn();
    }
    
    // Actual measurements
    for (let i = 0; i < samples; i++) {
      const start = this.now();
      fn();
      const elapsed = this.elapsed(start);
      measurements.push(elapsed);
    }
    
    // Sort for percentiles
    measurements.sort((a, b) => a - b);
    
    const min = measurements[0] ?? 0;
    const max = measurements[measurements.length - 1] ?? 0;
    const avg = measurements.reduce((a, b) => a + b, 0) / measurements.length;
    const median = measurements[Math.floor(measurements.length / 2)] ?? 0;
    const p95 = measurements[Math.floor(measurements.length * 0.95)] ?? 0;
    const p99 = measurements[Math.floor(measurements.length * 0.99)] ?? 0;
    
    return {
      samples,
      minNanos: min,
      maxNanos: max,
      avgNanos: avg,
      medianNanos: median,
      p95Nanos: p95,
      p99Nanos: p99,
      minMicros: min / 1000,
      maxMicros: max / 1000,
      avgMicros: avg / 1000,
      medianMicros: median / 1000,
      p95Micros: p95 / 1000,
      p99Micros: p99 / 1000
    };
  }
}

// Singleton instance for convenience
export const timer = new HighResTimer();
