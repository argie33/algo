import { BaseService, Order, Trade, Signal, RiskBreach } from '../../types';
import { Config } from '../../config';
import { Logger } from 'pino';

export interface ComplianceRule {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
  severity: 'info' | 'warning' | 'error' | 'critical';
  checkFunction: (data: any) => boolean;
}

export interface ComplianceViolation {
  id: string;
  ruleId: string;
  ruleName: string;
  severity: string;
  message: string;
  data: any;
  timestamp: number;
  resolved: boolean;
}

/**
 * Compliance monitoring and regulatory compliance service
 */
export class ComplianceService extends BaseService {
  private rules: Map<string, ComplianceRule> = new Map();
  private violations: ComplianceViolation[] = [];
  private auditLog: any[] = [];

  constructor(config: Config, logger: Logger) {
    super('ComplianceService', config, logger);
    this.initializeRules();
  }

  async initialize(): Promise<void> {
    this.logger.info('Initializing Compliance Service...');
    
    try {
      // Initialize compliance monitoring
      this.startComplianceMonitoring();
      
      this.logger.info({ ruleCount: this.rules.size }, 'Compliance Service initialized successfully');
      
    } catch (error) {
      this.logger.error({ error }, 'Failed to initialize Compliance Service');
      throw error;
    }
  }

  async start(): Promise<void> {
    if (this.isRunning) return;
    
    this.logger.info('Starting Compliance Service...');
    this.isRunning = true;
    
    this.logger.info('Compliance Service started successfully');
  }

  async stop(): Promise<void> {
    if (!this.isRunning) return;
    
    this.logger.info('Stopping Compliance Service...');
    this.isRunning = false;
    
    this.logger.info('Compliance Service stopped');
  }

  /**
   * Initialize compliance rules
   */
  private initializeRules(): void {
    // Position size limits
    this.addRule({
      id: 'position_size_limit',
      name: 'Position Size Limit',
      description: 'Ensure individual position sizes do not exceed limits',
      enabled: true,
      severity: 'error',
      checkFunction: (data: any) => {
        const { symbol, quantity, maxSize } = data;
        return Math.abs(quantity) <= maxSize;
      }
    });

    // Daily trading volume limits
    this.addRule({
      id: 'daily_volume_limit',
      name: 'Daily Volume Limit',
      description: 'Monitor daily trading volume limits',
      enabled: true,
      severity: 'warning',
      checkFunction: (data: any) => {
        const { dailyVolume, limit } = data;
        return dailyVolume <= limit;
      }
    });

    // Market hours compliance
    this.addRule({
      id: 'market_hours',
      name: 'Market Hours Compliance',
      description: 'Ensure trading only occurs during market hours',
      enabled: true,
      severity: 'critical',
      checkFunction: (data: any) => {
        return data.isMarketOpen;
      }
    });

    // Best execution compliance
    this.addRule({
      id: 'best_execution',
      name: 'Best Execution',
      description: 'Monitor execution quality for best execution compliance',
      enabled: true,
      severity: 'warning',
      checkFunction: (data: any) => {
        const { executionPrice, benchmark, tolerance } = data;
        const deviation = Math.abs(executionPrice - benchmark) / benchmark;
        return deviation <= tolerance;
      }
    });

    // Risk limits compliance
    this.addRule({
      id: 'risk_limits',
      name: 'Risk Limits Compliance',
      description: 'Ensure all risk limits are respected',
      enabled: true,
      severity: 'critical',
      checkFunction: (data: any) => {
        const { currentRisk, riskLimit } = data;
        return currentRisk <= riskLimit;
      }
    });

    this.logger.info('Compliance rules initialized');
  }

  /**
   * Add a compliance rule
   */
  private addRule(rule: ComplianceRule): void {
    this.rules.set(rule.id, rule);
  }

  /**
   * Check order compliance
   */
  async checkOrderCompliance(order: Order): Promise<ComplianceViolation[]> {
    const violations: ComplianceViolation[] = [];

    try {
      // Check position size limits
      const symbolConfig = this.config.getSymbolConfig(order.symbol);
      if (symbolConfig) {
        const positionSizeCheck = await this.checkRule('position_size_limit', {
          symbol: order.symbol,
          quantity: order.quantity,
          maxSize: symbolConfig.maxPositionSize
        });
        
        if (positionSizeCheck) {
          violations.push(positionSizeCheck);
        }
      }

      // Check market hours
      const marketHoursCheck = await this.checkRule('market_hours', {
        isMarketOpen: this.config.isMarketOpen()
      });
      
      if (marketHoursCheck) {
        violations.push(marketHoursCheck);
      }

      // Log compliance check
      this.auditLog.push({
        type: 'order_compliance_check',
        orderId: order.id,
        symbol: order.symbol,
        violations: violations.length,
        timestamp: Date.now()
      });

      return violations;

    } catch (error) {
      this.logger.error({ error, order }, 'Failed to check order compliance');
      return [];
    }
  }

  /**
   * Check trade compliance
   */
  async checkTradeCompliance(trade: Trade): Promise<ComplianceViolation[]> {
    const violations: ComplianceViolation[] = [];

    try {
      // Check best execution
      const benchmarkPrice = await this.getBenchmarkPrice(trade.symbol);
      if (benchmarkPrice) {
        const bestExecutionCheck = await this.checkRule('best_execution', {
          executionPrice: trade.price,
          benchmark: benchmarkPrice,
          tolerance: 0.001 // 0.1% tolerance
        });
        
        if (bestExecutionCheck) {
          violations.push(bestExecutionCheck);
        }
      }

      // Log compliance check
      this.auditLog.push({
        type: 'trade_compliance_check',
        symbol: trade.symbol,
        price: trade.price,
        violations: violations.length,
        timestamp: Date.now()
      });

      return violations;

    } catch (error) {
      this.logger.error({ error, trade }, 'Failed to check trade compliance');
      return [];
    }
  }

  /**
   * Check signal compliance
   */
  async checkSignalCompliance(signal: Signal): Promise<ComplianceViolation[]> {
    const violations: ComplianceViolation[] = [];

    try {
      // Add signal-specific compliance checks here
      // For example: signal quality, source validation, etc.

      // Log compliance check
      this.auditLog.push({
        type: 'signal_compliance_check',
        signalId: signal.id,
        symbol: signal.symbol,
        source: signal.source,
        violations: violations.length,
        timestamp: Date.now()
      });

      return violations;

    } catch (error) {
      this.logger.error({ error, signal }, 'Failed to check signal compliance');
      return [];
    }
  }

  /**
   * Check risk compliance
   */
  async checkRiskCompliance(riskBreach: RiskBreach): Promise<ComplianceViolation[]> {
    const violations: ComplianceViolation[] = [];

    try {
      // Check if risk breach violates compliance
      const riskLimitCheck = await this.checkRule('risk_limits', {
        currentRisk: riskBreach.currentValue,
        riskLimit: riskBreach.limitValue
      });
      
      if (riskLimitCheck) {
        violations.push(riskLimitCheck);
      }

      // Log compliance check
      this.auditLog.push({
        type: 'risk_compliance_check',
        breachType: riskBreach.type,
        severity: riskBreach.severity,
        violations: violations.length,
        timestamp: Date.now()
      });

      return violations;

    } catch (error) {
      this.logger.error({ error, riskBreach }, 'Failed to check risk compliance');
      return [];
    }
  }

  /**
   * Check a specific compliance rule
   */
  private async checkRule(ruleId: string, data: any): Promise<ComplianceViolation | null> {
    const rule = this.rules.get(ruleId);
    if (!rule || !rule.enabled) {
      return null;
    }

    try {
      const passed = rule.checkFunction(data);
      
      if (!passed) {
        const violation: ComplianceViolation = {
          id: this.generateViolationId(),
          ruleId: rule.id,
          ruleName: rule.name,
          severity: rule.severity,
          message: `Compliance violation: ${rule.description}`,
          data,
          timestamp: Date.now(),
          resolved: false
        };

        this.violations.push(violation);
        
        this.logger.warn({ violation }, 'Compliance violation detected');
        
        // Emit violation event
        this.emit('complianceViolation', violation);
        
        return violation;
      }

      return null;

    } catch (error) {
      this.logger.error({ error, ruleId, data }, 'Failed to check compliance rule');
      return null;
    }
  }

  /**
   * Start compliance monitoring
   */
  private startComplianceMonitoring(): void {
    // Periodic compliance checks
    setInterval(() => {
      this.performPeriodicChecks();
    }, 60000); // Every minute

    // Audit log cleanup
    setInterval(() => {
      this.cleanupAuditLog();
    }, 3600000); // Every hour
  }

  /**
   * Perform periodic compliance checks
   */
  private async performPeriodicChecks(): Promise<void> {
    try {
      // Check daily volume limits
      const dailyVolumeCheck = await this.checkRule('daily_volume_limit', {
        dailyVolume: await this.getDailyTradingVolume(),
        limit: 1000000 // $1M daily limit
      });

      if (dailyVolumeCheck) {
        this.logger.warn('Daily volume limit compliance violation');
      }

    } catch (error) {
      this.logger.error({ error }, 'Failed to perform periodic compliance checks');
    }
  }

  /**
   * Generate unique violation ID
   */
  private generateViolationId(): string {
    return `violation_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }

  /**
   * Get benchmark price for best execution check
   */
  private async getBenchmarkPrice(symbol: string): Promise<number | null> {
    // This would typically get NBBO or other benchmark prices
    // For now, return null (no benchmark available)
    return null;
  }

  /**
   * Get daily trading volume
   */
  private async getDailyTradingVolume(): Promise<number> {
    // This would calculate actual daily trading volume
    // For now, return mock value
    return 0;
  }

  /**
   * Cleanup old audit log entries
   */
  private cleanupAuditLog(): void {
    const cutoffTime = Date.now() - (7 * 24 * 60 * 60 * 1000); // 7 days
    const initialLength = this.auditLog.length;
    
    this.auditLog = this.auditLog.filter(entry => entry.timestamp > cutoffTime);
    
    const cleaned = initialLength - this.auditLog.length;
    if (cleaned > 0) {
      this.logger.info({ cleaned }, 'Cleaned up old audit log entries');
    }
  }

  /**
   * Get compliance violations
   */
  getViolations(resolved: boolean = false): ComplianceViolation[] {
    return this.violations.filter(v => v.resolved === resolved);
  }

  /**
   * Resolve compliance violation
   */
  resolveViolation(violationId: string): boolean {
    const violation = this.violations.find(v => v.id === violationId);
    if (violation) {
      violation.resolved = true;
      this.logger.info({ violationId }, 'Compliance violation resolved');
      return true;
    }
    return false;
  }

  /**
   * Get compliance summary
   */
  getComplianceSummary(): any {
    const totalViolations = this.violations.length;
    const unresolvedViolations = this.violations.filter(v => !v.resolved).length;
    const violationsBySeverity = this.violations.reduce((acc, v) => {
      acc[v.severity] = (acc[v.severity] || 0) + 1;
      return acc;
    }, {} as Record<string, number>);

    return {
      totalViolations,
      unresolvedViolations,
      violationsBySeverity,
      auditLogEntries: this.auditLog.length,
      rulesEnabled: Array.from(this.rules.values()).filter(r => r.enabled).length,
      lastCheck: Date.now()
    };
  }

  /**
   * Get audit log
   */
  getAuditLog(limit: number = 100): any[] {
    return this.auditLog
      .sort((a, b) => b.timestamp - a.timestamp)
      .slice(0, limit);
  }

  /**
   * Enable/disable compliance rule
   */
  setRuleEnabled(ruleId: string, enabled: boolean): boolean {
    const rule = this.rules.get(ruleId);
    if (rule) {
      rule.enabled = enabled;
      this.logger.info({ ruleId, enabled }, 'Compliance rule updated');
      return true;
    }
    return false;
  }
}
