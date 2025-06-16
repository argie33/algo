import { EventEmitter } from 'events';
import { LatencyMetrics, PerformanceMetrics } from '../types';

export interface SystemMetrics {
  uptime: number;
  memory_usage: number;
  cpu_usage: number;
  heap_used: number;
  heap_total: number;
  external: number;
  gc_runs: number;
  active_handles: number;
  active_requests: number;
}

export interface TradingMetrics {
  orders_per_second: number;
  signals_per_second: number;
  trades_per_second: number;
  error_rate: number;
  latency: LatencyMetrics;
  performance: PerformanceMetrics;
}

/**
 * Centralized metrics collection and reporting
 */
export class MetricsCollector extends EventEmitter {
  private metrics: Map<string, number> = new Map();
  private histograms: Map<string, number[]> = new Map();
  private counters: Map<string, number> = new Map();
  private timers: Map<string, number> = new Map();
  private intervals: NodeJS.Timeout[] = [];
  private isRunning: boolean = false;
  
  private readonly maxHistogramSize = 1000;
  private readonly metricsInterval = 1000; // 1 second

  async start(): Promise<void> {
    if (this.isRunning) return;
    
    this.isRunning = true;
    
    // Start system metrics collection
    const systemInterval = setInterval(() => {
      this.collectSystemMetrics();
    }, this.metricsInterval);
    
    this.intervals.push(systemInterval);
    
    // Start metrics reporting
    const reportInterval = setInterval(() => {
      this.reportMetrics();
    }, this.metricsInterval * 5); // Report every 5 seconds
    
    this.intervals.push(reportInterval);
  }

  async stop(): Promise<void> {
    if (!this.isRunning) return;
    
    this.isRunning = false;
    
    // Clear all intervals
    this.intervals.forEach(interval => {
      clearInterval(interval);
    });
    this.intervals = [];
  }

  /**
   * Record a simple metric value
   */
  recordMetric(name: string, value: number): void {
    this.metrics.set(name, value);
  }

  /**
   * Increment a counter
   */
  incrementCounter(name: string, delta: number = 1): void {
    const current = this.counters.get(name) || 0;
    this.counters.set(name, current + delta);
  }

  /**
   * Record a value in a histogram
   */
  recordHistogram(name: string, value: number): void {
    let histogram = this.histograms.get(name);
    if (!histogram) {
      histogram = [];
      this.histograms.set(name, histogram);
    }
    
    histogram.push(value);
    
    // Keep histogram size manageable
    if (histogram.length > this.maxHistogramSize) {
      histogram.shift();
    }
  }

  /**
   * Start a timer
   */
  startTimer(name: string): void {
    this.timers.set(name, Date.now());
  }

  /**
   * End a timer and record the duration
   */
  endTimer(name: string): number {
    const startTime = this.timers.get(name);
    if (!startTime) {
      return 0;
    }
    
    const duration = Date.now() - startTime;
    this.timers.delete(name);
    this.recordHistogram(`${name}_duration`, duration);
    
    return duration;
  }

  /**
   * Record latency measurement
   */
  recordLatency(type: string, latency: number): void {
    this.recordHistogram(`latency_${type}`, latency);
    this.recordMetric(`latency_${type}_current`, latency);
  }

  /**
   * Get current metrics
   */
  getMetrics(): any {
    const systemMetrics = this.getSystemMetrics();
    const tradingMetrics = this.getTradingMetrics();
    const latencyStats = this.getLatencyStats();
    
    return {
      timestamp: Date.now(),
      system: systemMetrics,
      trading: tradingMetrics,
      latency: latencyStats,
      counters: Object.fromEntries(this.counters),
      metrics: Object.fromEntries(this.metrics)
    };
  }

  /**
   * Get system metrics
   */
  private getSystemMetrics(): SystemMetrics {
    const memUsage = process.memoryUsage();
    
    return {
      uptime: process.uptime(),
      memory_usage: (memUsage.rss / 1024 / 1024), // MB
      cpu_usage: this.getCpuUsage(),
      heap_used: (memUsage.heapUsed / 1024 / 1024), // MB
      heap_total: (memUsage.heapTotal / 1024 / 1024), // MB
      external: (memUsage.external / 1024 / 1024), // MB
      gc_runs: this.getGcRuns(),
      active_handles: (process as any)._getActiveHandles().length,
      active_requests: (process as any)._getActiveRequests().length
    };
  }

  /**
   * Get trading-specific metrics
   */
  private getTradingMetrics(): Partial<TradingMetrics> {
    const ordersPerSecond = this.calculateRate('orders_placed');
    const signalsPerSecond = this.calculateRate('signals_generated');
    const tradesPerSecond = this.calculateRate('trades_executed');
    const errorRate = this.calculateErrorRate();
    
    return {
      orders_per_second: ordersPerSecond,
      signals_per_second: signalsPerSecond,
      trades_per_second: tradesPerSecond,
      error_rate: errorRate
    };
  }

  /**
   * Get latency statistics
   */
  private getLatencyStats(): any {
    const stats: any = {};
    
    this.histograms.forEach((values, name) => {
      if (name.includes('latency')) {
        stats[name] = this.calculateHistogramStats(values);
      }
    });
    
    return stats;
  }

  /**
   * Calculate rate per second for a counter
   */
  private calculateRate(counterName: string): number {
    const count = this.counters.get(counterName) || 0;
    const intervalSeconds = this.metricsInterval / 1000;
    return count / intervalSeconds;
  }

  /**
   * Calculate error rate
   */
  private calculateErrorRate(): number {
    const errors = this.counters.get('errors') || 0;
    const total = this.counters.get('total_operations') || 1;
    return errors / total;
  }

  /**
   * Calculate statistics for a histogram
   */
  private calculateHistogramStats(values: number[]): any {
    if (values.length === 0) {
      return { count: 0 };
    }
    
    const sorted = [...values].sort((a, b) => a - b);
    const count = sorted.length;
    const sum = sorted.reduce((a, b) => a + b, 0);
    const mean = sum / count;
    
    return {
      count,
      min: sorted[0],
      max: sorted[count - 1],
      mean,
      median: sorted[Math.floor(count / 2)],
      p95: sorted[Math.floor(count * 0.95)],
      p99: sorted[Math.floor(count * 0.99)]
    };
  }

  /**
   * Collect system metrics
   */
  private collectSystemMetrics(): void {
    const metrics = this.getSystemMetrics();
    
    Object.entries(metrics).forEach(([key, value]) => {
      this.recordMetric(`system_${key}`, value);
    });
  }

  /**
   * Get CPU usage (simplified)
   */
  private getCpuUsage(): number {
    // This is a simplified CPU usage calculation
    // In production, you'd want to use a proper CPU monitoring library
    const usage = process.cpuUsage();
    return (usage.user + usage.system) / 1000000; // Convert to seconds
  }

  /**
   * Get GC runs count (simplified)
   */
  private getGcRuns(): number {
    // This would require enabling GC monitoring
    // For now, return 0
    return 0;
  }

  /**
   * Report metrics to monitoring systems
   */
  private reportMetrics(): void {
    const metrics = this.getMetrics();
    
    // Emit metrics event for other components to consume
    this.emit('metrics', metrics);
    
    // TODO: Send to CloudWatch, Prometheus, etc.
    // This would be implemented based on the monitoring infrastructure
  }

  /**
   * Reset counters (called periodically to prevent overflow)
   */
  resetCounters(): void {
    this.counters.clear();
  }

  /**
   * Get counter value
   */
  getCounter(name: string): number {
    return this.counters.get(name) || 0;
  }

  /**
   * Get metric value
   */
  getMetric(name: string): number | undefined {
    return this.metrics.get(name);
  }
}
