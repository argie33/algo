import { BaseService } from '../../types';
import { Config } from '../../config';
import { Logger } from 'pino';

export interface HealthStatus {
  status: 'healthy' | 'degraded' | 'unhealthy';
  uptime: number;
  timestamp: number;
  version: string;
  environment: string;
  services: Record<string, ServiceHealthStatus>;
  metrics: HealthMetrics;
}

export interface ServiceHealthStatus {
  status: 'healthy' | 'degraded' | 'unhealthy';
  lastCheck: number;
  responseTime: number;
  errorRate: number;
  message?: string;
}

export interface HealthMetrics {
  memoryUsage: number;
  cpuUsage: number;
  activeConnections: number;
  queueSize: number;
  latency: {
    avg: number;
    p95: number;
    p99: number;
  };
}

/**
 * Health monitoring service for system status and diagnostics
 */
export class HealthService extends BaseService {
  private healthStatus: HealthStatus;
  private serviceChecks: Map<string, () => Promise<ServiceHealthStatus>> = new Map();
  private startTime: number;

  constructor(config: Config, logger: Logger) {
    super('HealthService', config, logger);
    
    this.startTime = Date.now();
    this.healthStatus = {
      status: 'healthy',
      uptime: 0,
      timestamp: Date.now(),
      version: '1.0.0',
      environment: config.environment,
      services: {},
      metrics: {
        memoryUsage: 0,
        cpuUsage: 0,
        activeConnections: 0,
        queueSize: 0,
        latency: {
          avg: 0,
          p95: 0,
          p99: 0
        }
      }
    };
    
    this.initializeHealthChecks();
  }

  async initialize(): Promise<void> {
    this.logger.info('Initializing Health Service...');
    
    try {
      await this.runAllHealthChecks();
      this.logger.info('Health Service initialized successfully');
    } catch (error) {
      this.logger.error({ error }, 'Failed to initialize Health Service');
      throw error;
    }
  }

  async start(): Promise<void> {
    if (this.isRunning) return;
    
    this.logger.info('Starting Health Service...');
    this.isRunning = true;
    
    // Start periodic health checks
    this.startPeriodicHealthChecks();
    
    this.logger.info('Health Service started successfully');
  }

  async stop(): Promise<void> {
    if (!this.isRunning) return;
    
    this.logger.info('Stopping Health Service...');
    this.isRunning = false;
    
    this.logger.info('Health Service stopped');
  }

  /**
   * Initialize health check functions for each service
   */
  private initializeHealthChecks(): void {
    // Database health check
    this.serviceChecks.set('database', async () => {
      const start = Date.now();
      try {
        // This would check database connectivity
        // For now, simulate a health check
        await new Promise(resolve => setTimeout(resolve, 10));
        
        return {
          status: 'healthy',
          lastCheck: Date.now(),
          responseTime: Date.now() - start,
          errorRate: 0,
          message: 'Database connection healthy'
        };
      } catch (error) {
        return {
          status: 'unhealthy',
          lastCheck: Date.now(),
          responseTime: Date.now() - start,
          errorRate: 1,
          message: `Database error: ${error}`
        };
      }
    });

    // Redis health check
    this.serviceChecks.set('redis', async () => {
      const start = Date.now();
      try {
        // This would check Redis connectivity
        await new Promise(resolve => setTimeout(resolve, 5));
        
        return {
          status: 'healthy',
          lastCheck: Date.now(),
          responseTime: Date.now() - start,
          errorRate: 0,
          message: 'Redis connection healthy'
        };
      } catch (error) {
        return {
          status: 'unhealthy',
          lastCheck: Date.now(),
          responseTime: Date.now() - start,
          errorRate: 1,
          message: `Redis error: ${error}`
        };
      }
    });

    // Market data health check
    this.serviceChecks.set('market_data', async () => {
      const start = Date.now();
      try {
        // This would check market data connection
        await new Promise(resolve => setTimeout(resolve, 15));
        
        return {
          status: 'healthy',
          lastCheck: Date.now(),
          responseTime: Date.now() - start,
          errorRate: 0,
          message: 'Market data feed healthy'
        };
      } catch (error) {
        return {
          status: 'unhealthy',
          lastCheck: Date.now(),
          responseTime: Date.now() - start,
          errorRate: 1,
          message: `Market data error: ${error}`
        };
      }
    });

    // Alpaca API health check
    this.serviceChecks.set('alpaca', async () => {
      const start = Date.now();
      try {
        // This would check Alpaca API connectivity
        await new Promise(resolve => setTimeout(resolve, 20));
        
        return {
          status: 'healthy',
          lastCheck: Date.now(),
          responseTime: Date.now() - start,
          errorRate: 0,
          message: 'Alpaca API healthy'
        };
      } catch (error) {
        return {
          status: 'unhealthy',
          lastCheck: Date.now(),
          responseTime: Date.now() - start,
          errorRate: 1,
          message: `Alpaca API error: ${error}`
        };
      }
    });
  }

  /**
   * Start periodic health checks
   */
  private startPeriodicHealthChecks(): void {
    const interval = this.config.monitoring.healthCheckInterval;
    
    setInterval(async () => {
      try {
        await this.runAllHealthChecks();
      } catch (error) {
        this.logger.error({ error }, 'Failed to run health checks');
      }
    }, interval);
  }

  /**
   * Run all health checks
   */
  private async runAllHealthChecks(): Promise<void> {
    const servicePromises = Array.from(this.serviceChecks.entries()).map(async ([name, checkFunction]) => {
      try {
        const result = await checkFunction();
        return [name, result] as [string, ServiceHealthStatus];
      } catch (error) {
        return [name, {
          status: 'unhealthy',
          lastCheck: Date.now(),
          responseTime: 0,
          errorRate: 1,
          message: `Health check failed: ${error}`
        }] as [string, ServiceHealthStatus];
      }
    });

    const serviceResults = await Promise.all(servicePromises);
    
    // Update service statuses
    this.healthStatus.services = Object.fromEntries(serviceResults);
    
    // Update overall health status
    this.updateOverallHealthStatus();
    
    // Update metrics
    this.updateHealthMetrics();
    
    // Update timestamp and uptime
    this.healthStatus.timestamp = Date.now();
    this.healthStatus.uptime = Date.now() - this.startTime;
  }

  /**
   * Update overall health status based on service statuses
   */
  private updateOverallHealthStatus(): void {
    const serviceStatuses = Object.values(this.healthStatus.services);
    
    if (serviceStatuses.length === 0) {
      this.healthStatus.status = 'unhealthy';
      return;
    }

    const unhealthyCount = serviceStatuses.filter(s => s.status === 'unhealthy').length;
    const degradedCount = serviceStatuses.filter(s => s.status === 'degraded').length;

    if (unhealthyCount > 0) {
      this.healthStatus.status = 'unhealthy';
    } else if (degradedCount > 0) {
      this.healthStatus.status = 'degraded';
    } else {
      this.healthStatus.status = 'healthy';
    }
  }

  /**
   * Update health metrics
   */
  private updateHealthMetrics(): void {
    const memUsage = process.memoryUsage();
    
    this.healthStatus.metrics = {
      memoryUsage: (memUsage.heapUsed / memUsage.heapTotal) * 100,
      cpuUsage: this.getCpuUsage(),
      activeConnections: this.getActiveConnections(),
      queueSize: this.getQueueSize(),
      latency: {
        avg: this.getAverageLatency(),
        p95: this.getP95Latency(),
        p99: this.getP99Latency()
      }
    };
  }

  /**
   * Get CPU usage percentage
   */
  private getCpuUsage(): number {
    // Simplified CPU usage calculation
    // In production, you'd use a proper CPU monitoring library
    const usage = process.cpuUsage();
    return ((usage.user + usage.system) / 1000000) % 100;
  }

  /**
   * Get active connections count
   */
  private getActiveConnections(): number {
    // This would get actual connection counts from database pools, etc.
    return 10; // Mock value
  }

  /**
   * Get current queue size
   */
  private getQueueSize(): number {
    // This would get actual queue sizes from order queue, signal queue, etc.
    return 0; // Mock value
  }

  /**
   * Get average latency
   */
  private getAverageLatency(): number {
    const serviceResponseTimes = Object.values(this.healthStatus.services)
      .map(s => s.responseTime)
      .filter(t => t > 0);
    
    if (serviceResponseTimes.length === 0) return 0;
    
    return serviceResponseTimes.reduce((sum, time) => sum + time, 0) / serviceResponseTimes.length;
  }

  /**
   * Get P95 latency
   */
  private getP95Latency(): number {
    // This would calculate from actual latency histogram
    return this.getAverageLatency() * 1.5; // Mock value
  }

  /**
   * Get P99 latency
   */
  private getP99Latency(): number {
    // This would calculate from actual latency histogram
    return this.getAverageLatency() * 2.0; // Mock value
  }

  /**
   * Get current health status
   */
  getStatus(): HealthStatus {
    return { ...this.healthStatus };
  }

  /**
   * Get simplified health check for load balancer
   */
  getSimpleHealthCheck(): { status: string; timestamp: number } {
    return {
      status: this.healthStatus.status,
      timestamp: this.healthStatus.timestamp
    };
  }

  /**
   * Check if system is healthy
   */
  isHealthy(): boolean {
    return this.healthStatus.status === 'healthy';
  }

  /**
   * Check if system is degraded
   */
  isDegraded(): boolean {
    return this.healthStatus.status === 'degraded';
  }

  /**
   * Check if system is unhealthy
   */
  isUnhealthy(): boolean {
    return this.healthStatus.status === 'unhealthy';
  }

  /**
   * Get service-specific health status
   */
  getServiceHealth(serviceName: string): ServiceHealthStatus | null {
    return this.healthStatus.services[serviceName] || null;
  }

  /**
   * Get system uptime in seconds
   */
  getUptime(): number {
    return Math.floor((Date.now() - this.startTime) / 1000);
  }

  /**
   * Get readiness status (for Kubernetes readiness probe)
   */
  getReadinessStatus(): { ready: boolean; message: string } {
    const criticalServices = ['database', 'redis', 'market_data'];
    const unhealthyCritical = criticalServices.filter(service => 
      this.healthStatus.services[service]?.status === 'unhealthy'
    );

    if (unhealthyCritical.length > 0) {
      return {
        ready: false,
        message: `Critical services unhealthy: ${unhealthyCritical.join(', ')}`
      };
    }

    return {
      ready: true,
      message: 'System ready'
    };
  }

  /**
   * Get liveness status (for Kubernetes liveness probe)
   */
  getLivenessStatus(): { alive: boolean; message: string } {
    // Simple liveness check - if the service is running, it's alive
    if (this.isRunning) {
      return {
        alive: true,
        message: 'System alive'
      };
    }

    return {
      alive: false,
      message: 'System not running'
    };
  }
}
