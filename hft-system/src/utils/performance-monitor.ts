/**
 * Ultra-High Performance Monitor for HFT System
 * 
 * Features:
 * - Real-time latency tracking
 * - Memory usage monitoring
 * - CPU usage tracking
 * - Throughput measurement
 * - Historical performance data
 * - Alert system for performance degradation
 */

import { CircularBuffer, NumericCircularBuffer } from './circular-buffer';
import { HighResTimer } from './high-res-timer';

export interface PerformanceMetrics {
  // Latency metrics (microseconds)
  latency: {
    current: number;
    min: number;
    max: number;
    avg: number;
    p50: number;
    p95: number;
    p99: number;
  };
  
  // Throughput metrics
  throughput: {
    current: number;    // operations per second
    avg: number;
    peak: number;
  };
  
  // Memory metrics (MB)
  memory: {
    used: number;
    total: number;
    utilization: number;
  };
  
  // CPU metrics (%)
  cpu: {
    usage: number;
    loadAverage: number[];
  };
  
  // System health
  health: {
    status: 'healthy' | 'warning' | 'critical';
    alerts: string[];
  };
}

export interface PerformanceAlert {
  severity: 'warning' | 'critical';
  message: string;
  timestamp: number;
  metric: string;
  value: number;
  threshold: number;
}

export class PerformanceMonitor {
  private timer: HighResTimer = new HighResTimer();
  
  // Performance buffers
  private latencyBuffer: NumericCircularBuffer = new NumericCircularBuffer(10000);
  private throughputBuffer: NumericCircularBuffer = new NumericCircularBuffer(1000);
  private memoryBuffer: NumericCircularBuffer = new NumericCircularBuffer(1000);
  private cpuBuffer: NumericCircularBuffer = new NumericCircularBuffer(1000);
  
  // Alert system
  private alerts: CircularBuffer<PerformanceAlert> = new CircularBuffer(100);
  private alertCallbacks: Set<(alert: PerformanceAlert) => void> = new Set();
  
  // Thresholds
  private thresholds = {
    latencyWarning: 1000,    // 1ms in microseconds
    latencyCritical: 5000,   // 5ms in microseconds
    memoryWarning: 80,       // 80% memory usage
    memoryCritical: 95,      // 95% memory usage
    cpuWarning: 80,          // 80% CPU usage
    cpuCritical: 95,         // 95% CPU usage
    throughputWarning: 1000, // operations per second
  };
  
  // Tracking state
  private operationCount: number = 0;
  private lastThroughputCheck: number = Date.now();
  private isMonitoring: boolean = false;
  private monitoringInterval: NodeJS.Timeout | null = null;
  
  constructor() {
    // Start monitoring system resources
    this.startSystemMonitoring();
  }
  
  /**
   * Start performance monitoring
   */
  start(): void {
    if (this.isMonitoring) return;
    
    this.isMonitoring = true;
    this.monitoringInterval = setInterval(() => {
      this.collectSystemMetrics();
    }, 1000); // Collect every second
  }
  
  /**
   * Stop performance monitoring
   */
  stop(): void {
    if (!this.isMonitoring) return;
    
    this.isMonitoring = false;
    if (this.monitoringInterval) {
      clearInterval(this.monitoringInterval);
      this.monitoringInterval = null;
    }
  }
  
  /**
   * Record operation latency
   */
  recordLatency(latencyMicros: number): void {
    this.latencyBuffer.push(latencyMicros);
    this.operationCount++;
    
    // Check for latency alerts
    if (latencyMicros > this.thresholds.latencyCritical) {
      this.addAlert('critical', `Critical latency: ${latencyMicros.toFixed(2)}μs`, 'latency', latencyMicros, this.thresholds.latencyCritical);
    } else if (latencyMicros > this.thresholds.latencyWarning) {
      this.addAlert('warning', `High latency: ${latencyMicros.toFixed(2)}μs`, 'latency', latencyMicros, this.thresholds.latencyWarning);
    }
  }
  
  /**
   * Record throughput measurement
   */
  recordThroughput(operations: number, timeWindowMs: number): void {
    const opsPerSecond = (operations / timeWindowMs) * 1000;
    this.throughputBuffer.push(opsPerSecond);
    
    if (opsPerSecond < this.thresholds.throughputWarning) {
      this.addAlert('warning', `Low throughput: ${opsPerSecond.toFixed(0)} ops/sec`, 'throughput', opsPerSecond, this.thresholds.throughputWarning);
    }
  }
  
  /**
   * Get current performance metrics
   */
  getMetrics(): PerformanceMetrics {
    const now = Date.now();
    const timeWindow = now - this.lastThroughputCheck;
    const currentThroughput = timeWindow > 0 ? (this.operationCount / timeWindow) * 1000 : 0;
    
    // Update throughput tracking
    if (timeWindow >= 1000) { // Every second
      this.recordThroughput(this.operationCount, timeWindow);
      this.operationCount = 0;
      this.lastThroughputCheck = now;
    }
    
    // Calculate latency statistics
    const latencyStats = this.calculateLatencyStats();
    
    // Get memory usage
    const memoryUsage = this.getMemoryUsage();
    
    // Get CPU usage
    const cpuUsage = this.getCPUUsage();
    
    // Determine system health
    const health = this.assessSystemHealth(latencyStats, memoryUsage, cpuUsage);
    
    return {
      latency: latencyStats,
      throughput: {
        current: currentThroughput,
        avg: this.throughputBuffer.average(),
        peak: this.throughputBuffer.max()
      },
      memory: memoryUsage,
      cpu: cpuUsage,
      health
    };
  }
  
  /**
   * Calculate latency statistics
   */
  private calculateLatencyStats() {
    if (this.latencyBuffer.size() === 0) {
      return {
        current: 0,
        min: 0,
        max: 0,
        avg: 0,
        p50: 0,
        p95: 0,
        p99: 0
      };
    }
    
    const latest = this.latencyBuffer.peek() ?? 0;
    
    return {
      current: latest,
      min: this.latencyBuffer.min(),
      max: this.latencyBuffer.max(),
      avg: this.latencyBuffer.average(),
      p50: this.latencyBuffer.percentile(50),
      p95: this.latencyBuffer.percentile(95),
      p99: this.latencyBuffer.percentile(99)
    };
  }
  
  /**
   * Get memory usage statistics
   */
  private getMemoryUsage() {
    const memUsage = process.memoryUsage();
    const totalMB = memUsage.heapTotal / 1024 / 1024;
    const usedMB = memUsage.heapUsed / 1024 / 1024;
    const utilization = (usedMB / totalMB) * 100;
    
    this.memoryBuffer.push(utilization);
    
    // Check for memory alerts
    if (utilization > this.thresholds.memoryCritical) {
      this.addAlert('critical', `Critical memory usage: ${utilization.toFixed(1)}%`, 'memory', utilization, this.thresholds.memoryCritical);
    } else if (utilization > this.thresholds.memoryWarning) {
      this.addAlert('warning', `High memory usage: ${utilization.toFixed(1)}%`, 'memory', utilization, this.thresholds.memoryWarning);
    }
    
    return {
      used: usedMB,
      total: totalMB,
      utilization
    };
  }
  
  /**
   * Get CPU usage statistics
   */
  private getCPUUsage() {
    // Simple CPU usage approximation
    const usage = process.cpuUsage();
    const totalUsage = (usage.user + usage.system) / 1000; // Convert to ms
    
    // Get load average (Unix-like systems)
    let loadAverage: number[] = [];
    try {
      loadAverage = require('os').loadavg();
    } catch (error) {
      loadAverage = [0, 0, 0];
    }
    
    const cpuPercent = Math.min(100, (totalUsage / 1000) * 100);
    this.cpuBuffer.push(cpuPercent);
    
    // Check for CPU alerts
    if (cpuPercent > this.thresholds.cpuCritical) {
      this.addAlert('critical', `Critical CPU usage: ${cpuPercent.toFixed(1)}%`, 'cpu', cpuPercent, this.thresholds.cpuCritical);
    } else if (cpuPercent > this.thresholds.cpuWarning) {
      this.addAlert('warning', `High CPU usage: ${cpuPercent.toFixed(1)}%`, 'cpu', cpuPercent, this.thresholds.cpuWarning);
    }
    
    return {
      usage: cpuPercent,
      loadAverage
    };
  }
  
  /**
   * Assess overall system health
   */
  private assessSystemHealth(latency: any, memory: any, cpu: any) {
    const recentAlerts = this.alerts.last(10);
    const criticalAlerts = recentAlerts.filter(alert => alert.severity === 'critical');
    const warningAlerts = recentAlerts.filter(alert => alert.severity === 'warning');
    
    let status: 'healthy' | 'warning' | 'critical';
    const alertMessages: string[] = [];
    
    if (criticalAlerts.length > 0) {
      status = 'critical';
      alertMessages.push(...criticalAlerts.map(alert => alert.message));
    } else if (warningAlerts.length > 0) {
      status = 'warning';
      alertMessages.push(...warningAlerts.map(alert => alert.message));
    } else {
      status = 'healthy';
    }
    
    return {
      status,
      alerts: alertMessages
    };
  }
  
  /**
   * Add performance alert
   */
  private addAlert(severity: 'warning' | 'critical', message: string, metric: string, value: number, threshold: number): void {
    const alert: PerformanceAlert = {
      severity,
      message,
      timestamp: Date.now(),
      metric,
      value,
      threshold
    };
    
    this.alerts.push(alert);
    
    // Notify alert callbacks
    for (const callback of this.alertCallbacks) {
      try {
        callback(alert);
      } catch (error) {
        console.error('Error in alert callback:', error);
      }
    }
  }
  
  /**
   * Add alert callback
   */
  onAlert(callback: (alert: PerformanceAlert) => void): void {
    this.alertCallbacks.add(callback);
  }
  
  /**
   * Remove alert callback
   */
  offAlert(callback: (alert: PerformanceAlert) => void): void {
    this.alertCallbacks.delete(callback);
  }
  
  /**
   * Get recent alerts
   */
  getRecentAlerts(count: number = 10): PerformanceAlert[] {
    return this.alerts.last(count);
  }
  
  /**
   * Start system monitoring
   */
  private startSystemMonitoring(): void {
    // Force garbage collection periodically to avoid GC pauses during trading
    if (global.gc) {
      setInterval(() => {
        global.gc();
      }, 30000); // Every 30 seconds
    }
  }
  
  /**
   * Collect system metrics
   */
  private collectSystemMetrics(): void {
    // This is called periodically to update system metrics
    // The actual metric collection happens in the individual methods
  }
  
  /**
   * Update performance thresholds
   */
  updateThresholds(newThresholds: Partial<typeof this.thresholds>): void {
    this.thresholds = { ...this.thresholds, ...newThresholds };
  }
  
  /**
   * Get performance summary
   */
  getSummary(): string {
    const metrics = this.getMetrics();
    
    return `
Performance Summary:
  Latency: ${metrics.latency.avg.toFixed(2)}μs avg, ${metrics.latency.p99.toFixed(2)}μs p99
  Throughput: ${metrics.throughput.current.toFixed(0)} ops/sec
  Memory: ${metrics.memory.utilization.toFixed(1)}% (${metrics.memory.used.toFixed(1)}MB/${metrics.memory.total.toFixed(1)}MB)
  CPU: ${metrics.cpu.usage.toFixed(1)}%
  Health: ${metrics.health.status.toUpperCase()}${metrics.health.alerts.length > 0 ? ` (${metrics.health.alerts.length} alerts)` : ''}
    `.trim();
  }
}
