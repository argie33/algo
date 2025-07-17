const { query } = require('./database');
const { createLogger } = require('./structuredLogger');

class PortfolioAlerts {
  constructor() {
    this.logger = createLogger('financial-platform', 'portfolio-alerts');
    this.correlationId = this.generateCorrelationId();
    
    this.alertTypes = {
      ALLOCATION_DRIFT: 'allocation_drift',
      POSITION_GAIN_LOSS: 'position_gain_loss',
      PORTFOLIO_VALUE_CHANGE: 'portfolio_value_change',
      SECTOR_CONCENTRATION: 'sector_concentration',
      POSITION_SIZE_CHANGE: 'position_size_change',
      DIVIDEND_PAYMENT: 'dividend_payment',
      EARNINGS_ANNOUNCEMENT: 'earnings_announcement',
      BETA_CHANGE: 'beta_change',
      REBALANCE_NEEDED: 'rebalance_needed'
    };
    
    this.alertSeverity = {
      LOW: 'low',
      MEDIUM: 'medium',
      HIGH: 'high',
      CRITICAL: 'critical'
    };
  }

  generateCorrelationId() {
    return `portfolio-alerts-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  }

  /**
   * Create a portfolio alert
   */
  async createPortfolioAlert(userId, alertConfig) {
    try {
      const {
        alertType,
        symbol = null,
        threshold,
        condition,
        isActive = true,
        notificationPreferences = {},
        expiryDate = null,
        message = null
      } = alertConfig;

      // Validate alert configuration
      if (!alertType || !threshold || !condition) {
        throw new Error('Missing required alert parameters');
      }

      if (!Object.values(this.alertTypes).includes(alertType)) {
        throw new Error('Invalid alert type');
      }

      // Insert alert into database
      const result = await query(`
        INSERT INTO portfolio_alerts (
          user_id, alert_type, symbol, threshold, condition, 
          is_active, notification_preferences, expiry_date, 
          message, created_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW())
        RETURNING *
      `, [
        userId, alertType, symbol, threshold, condition,
        isActive, JSON.stringify(notificationPreferences), 
        expiryDate, message
      ]);

      this.logger.info('Portfolio alert created', {
        alertId: result.rows[0].id,
        userId,
        alertType,
        symbol,
        correlationId: this.correlationId
      });

      return result.rows[0];
    } catch (error) {
      this.logger.error('Error creating portfolio alert', {
        userId,
        alertType: alertConfig.alertType,
        error: error.message,
        correlationId: this.correlationId
      });
      throw error;
    }
  }

  /**
   * Get user's portfolio alerts
   */
  async getUserPortfolioAlerts(userId, filters = {}) {
    try {
      let whereClause = 'WHERE user_id = $1';
      const params = [userId];
      let paramIndex = 2;

      if (filters.alertType) {
        whereClause += ` AND alert_type = $${paramIndex}`;
        params.push(filters.alertType);
        paramIndex++;
      }

      if (filters.symbol) {
        whereClause += ` AND symbol = $${paramIndex}`;
        params.push(filters.symbol);
        paramIndex++;
      }

      if (filters.isActive !== undefined) {
        whereClause += ` AND is_active = $${paramIndex}`;
        params.push(filters.isActive);
        paramIndex++;
      }

      const result = await query(`
        SELECT 
          pa.*,
          (
            SELECT COUNT(*) FROM portfolio_alert_notifications pan 
            WHERE pan.alert_id = pa.id
          ) as notification_count,
          (
            SELECT MAX(created_at) FROM portfolio_alert_notifications pan 
            WHERE pan.alert_id = pa.id
          ) as last_triggered
        FROM portfolio_alerts pa
        ${whereClause}
        ORDER BY pa.created_at DESC
      `, params);

      return result.rows;
    } catch (error) {
      this.logger.error('Error fetching user portfolio alerts', {
        userId,
        filters,
        error: error.message,
        correlationId: this.correlationId
      });
      throw error;
    }
  }

  /**
   * Process portfolio alerts for a user
   */
  async processUserPortfolioAlerts(userId) {
    try {
      this.logger.info('Processing portfolio alerts for user', {
        userId,
        correlationId: this.correlationId
      });

      // Get user's active alerts
      const alerts = await this.getUserPortfolioAlerts(userId, { isActive: true });

      if (alerts.length === 0) {
        return { processedCount: 0, triggeredCount: 0 };
      }

      // Get current portfolio data
      const portfolioData = await this.getPortfolioData(userId);
      
      if (!portfolioData) {
        this.logger.warn('No portfolio data found for user', {
          userId,
          correlationId: this.correlationId
        });
        return { processedCount: 0, triggeredCount: 0 };
      }

      let triggeredCount = 0;

      // Process each alert
      for (const alert of alerts) {
        try {
          const shouldTrigger = await this.checkAlertCondition(alert, portfolioData);
          
          if (shouldTrigger) {
            await this.triggerPortfolioAlert(alert, portfolioData);
            triggeredCount++;
          }
        } catch (error) {
          this.logger.error('Error processing portfolio alert', {
            alertId: alert.id,
            userId,
            error: error.message,
            correlationId: this.correlationId
          });
        }
      }

      return { processedCount: alerts.length, triggeredCount };
    } catch (error) {
      this.logger.error('Error processing user portfolio alerts', {
        userId,
        error: error.message,
        correlationId: this.correlationId
      });
      throw error;
    }
  }

  /**
   * Check if alert condition is met
   */
  async checkAlertCondition(alert, portfolioData) {
    const { alert_type, condition, threshold, symbol } = alert;

    switch (alert_type) {
      case this.alertTypes.ALLOCATION_DRIFT:
        return this.checkAllocationDrift(portfolioData, threshold, condition);
      
      case this.alertTypes.POSITION_GAIN_LOSS:
        return this.checkPositionGainLoss(portfolioData, symbol, threshold, condition);
      
      case this.alertTypes.PORTFOLIO_VALUE_CHANGE:
        return this.checkPortfolioValueChange(portfolioData, threshold, condition);
      
      case this.alertTypes.SECTOR_CONCENTRATION:
        return this.checkSectorConcentration(portfolioData, threshold, condition);
      
      case this.alertTypes.POSITION_SIZE_CHANGE:
        return this.checkPositionSizeChange(portfolioData, symbol, threshold, condition);
      
      case this.alertTypes.BETA_CHANGE:
        return this.checkBetaChange(portfolioData, threshold, condition);
      
      case this.alertTypes.REBALANCE_NEEDED:
        return this.checkRebalanceNeeded(portfolioData, threshold);
      
      default:
        return false;
    }
  }

  /**
   * Check allocation drift
   */
  checkAllocationDrift(portfolioData, threshold, condition) {
    const { holdings, targetAllocation } = portfolioData;
    
    if (!targetAllocation) return false;

    const currentAllocation = this.calculateCurrentAllocation(holdings);
    
    for (const [symbol, targetPercent] of Object.entries(targetAllocation)) {
      const currentPercent = currentAllocation[symbol] || 0;
      const drift = Math.abs(currentPercent - targetPercent);
      
      if (drift > threshold) {
        return true;
      }
    }
    
    return false;
  }

  /**
   * Check position gain/loss
   */
  checkPositionGainLoss(portfolioData, symbol, threshold, condition) {
    const { holdings } = portfolioData;
    const position = holdings.find(h => h.symbol === symbol);
    
    if (!position) return false;

    const gainLossPercent = parseFloat(position.gain_loss_percent || 0);
    
    switch (condition) {
      case 'above':
        return gainLossPercent > threshold;
      case 'below':
        return gainLossPercent < threshold;
      case 'absolute_above':
        return Math.abs(gainLossPercent) > threshold;
      default:
        return false;
    }
  }

  /**
   * Check portfolio value change
   */
  checkPortfolioValueChange(portfolioData, threshold, condition) {
    const { summary, previousSummary } = portfolioData;
    
    if (!previousSummary) return false;

    const currentValue = parseFloat(summary.totalValue || 0);
    const previousValue = parseFloat(previousSummary.totalValue || 0);
    
    if (previousValue === 0) return false;

    const changePercent = ((currentValue - previousValue) / previousValue) * 100;
    
    switch (condition) {
      case 'increase_above':
        return changePercent > threshold;
      case 'decrease_below':
        return changePercent < -threshold;
      case 'change_above':
        return Math.abs(changePercent) > threshold;
      default:
        return false;
    }
  }

  /**
   * Check sector concentration
   */
  checkSectorConcentration(portfolioData, threshold, condition) {
    const { holdings } = portfolioData;
    const sectorAllocation = {};
    const totalValue = holdings.reduce((sum, h) => sum + parseFloat(h.market_value || 0), 0);
    
    if (totalValue === 0) return false;

    // Calculate sector allocations
    holdings.forEach(holding => {
      const sector = holding.sector || 'Other';
      const value = parseFloat(holding.market_value || 0);
      sectorAllocation[sector] = (sectorAllocation[sector] || 0) + value;
    });

    // Check if any sector exceeds threshold
    for (const [sector, value] of Object.entries(sectorAllocation)) {
      const percentage = (value / totalValue) * 100;
      if (percentage > threshold) {
        return true;
      }
    }
    
    return false;
  }

  /**
   * Check position size change
   */
  checkPositionSizeChange(portfolioData, symbol, threshold, condition) {
    const { holdings } = portfolioData;
    const position = holdings.find(h => h.symbol === symbol);
    
    if (!position) return false;

    const totalValue = holdings.reduce((sum, h) => sum + parseFloat(h.market_value || 0), 0);
    const positionPercent = totalValue > 0 ? (parseFloat(position.market_value || 0) / totalValue) * 100 : 0;
    
    switch (condition) {
      case 'above':
        return positionPercent > threshold;
      case 'below':
        return positionPercent < threshold;
      default:
        return false;
    }
  }

  /**
   * Check beta change
   */
  checkBetaChange(portfolioData, threshold, condition) {
    const { holdings } = portfolioData;
    const totalValue = holdings.reduce((sum, h) => sum + parseFloat(h.market_value || 0), 0);
    
    if (totalValue === 0) return false;

    // Calculate weighted portfolio beta
    const portfolioBeta = holdings.reduce((sum, h) => {
      const allocation = parseFloat(h.market_value || 0) / totalValue;
      const beta = parseFloat(h.beta || 1);
      return sum + (allocation * beta);
    }, 0);

    switch (condition) {
      case 'above':
        return portfolioBeta > threshold;
      case 'below':
        return portfolioBeta < threshold;
      default:
        return false;
    }
  }

  /**
   * Check if rebalancing is needed
   */
  checkRebalanceNeeded(portfolioData, threshold) {
    // This is a simplified check - in practice, you'd want more sophisticated logic
    const { holdings } = portfolioData;
    const totalValue = holdings.reduce((sum, h) => sum + parseFloat(h.market_value || 0), 0);
    
    if (totalValue === 0) return false;

    // Check for concentration risk
    const topPosition = holdings.reduce((max, h) => {
      const value = parseFloat(h.market_value || 0);
      return value > max ? value : max;
    }, 0);

    const topPositionPercent = (topPosition / totalValue) * 100;
    
    return topPositionPercent > threshold;
  }

  /**
   * Calculate current allocation
   */
  calculateCurrentAllocation(holdings) {
    const totalValue = holdings.reduce((sum, h) => sum + parseFloat(h.market_value || 0), 0);
    const allocation = {};
    
    holdings.forEach(holding => {
      const symbol = holding.symbol;
      const value = parseFloat(holding.market_value || 0);
      allocation[symbol] = totalValue > 0 ? (value / totalValue) * 100 : 0;
    });
    
    return allocation;
  }

  /**
   * Get portfolio data for alert processing
   */
  async getPortfolioData(userId) {
    try {
      // Get current holdings
      const holdingsResult = await query(`
        SELECT 
          h.symbol,
          h.shares,
          h.avg_cost,
          h.current_price,
          h.market_value,
          h.gain_loss,
          h.gain_loss_percent,
          h.sector,
          h.industry,
          h.beta,
          h.last_updated
        FROM portfolio_holdings h
        WHERE h.user_id = $1 AND h.shares > 0
        ORDER BY h.market_value DESC
      `, [userId]);

      const holdings = holdingsResult.rows;

      // Get portfolio summary
      const summaryResult = await query(`
        SELECT 
          SUM(market_value) as total_value,
          SUM(gain_loss) as total_gain_loss,
          COUNT(*) as positions_count
        FROM portfolio_holdings
        WHERE user_id = $1 AND shares > 0
      `, [userId]);

      const summary = summaryResult.rows[0];

      // Get previous day's summary for comparison
      const previousSummaryResult = await query(`
        SELECT 
          total_value,
          total_gain_loss,
          positions_count,
          snapshot_date
        FROM portfolio_snapshots
        WHERE user_id = $1 
        AND snapshot_date < CURRENT_DATE
        ORDER BY snapshot_date DESC
        LIMIT 1
      `, [userId]);

      const previousSummary = previousSummaryResult.rows[0] || null;

      return {
        holdings,
        summary,
        previousSummary,
        targetAllocation: null // This would come from user's target allocation settings
      };
    } catch (error) {
      this.logger.error('Error fetching portfolio data', {
        userId,
        error: error.message,
        correlationId: this.correlationId
      });
      return null;
    }
  }

  /**
   * Trigger portfolio alert
   */
  async triggerPortfolioAlert(alert, portfolioData) {
    try {
      // Check if alert was triggered recently
      const recentTrigger = await this.checkRecentTrigger(alert.id);
      if (recentTrigger) {
        return;
      }

      // Create notification record
      const notification = await this.createPortfolioNotification(alert, portfolioData);
      
      // Update alert trigger count
      await this.updateAlertTriggerCount(alert.id);
      
      this.logger.info('Portfolio alert triggered', {
        alertId: alert.id,
        userId: alert.user_id,
        alertType: alert.alert_type,
        symbol: alert.symbol,
        correlationId: this.correlationId
      });

      return notification;
    } catch (error) {
      this.logger.error('Error triggering portfolio alert', {
        alertId: alert.id,
        error: error.message,
        correlationId: this.correlationId
      });
      throw error;
    }
  }

  /**
   * Check recent trigger
   */
  async checkRecentTrigger(alertId, windowMinutes = 240) { // 4 hours default
    try {
      const result = await query(`
        SELECT COUNT(*) as count
        FROM portfolio_alert_notifications
        WHERE alert_id = $1
        AND created_at > NOW() - INTERVAL '${windowMinutes} minutes'
      `, [alertId]);

      return parseInt(result.rows[0].count) > 0;
    } catch (error) {
      this.logger.error('Error checking recent trigger', {
        alertId,
        error: error.message,
        correlationId: this.correlationId
      });
      return false;
    }
  }

  /**
   * Create portfolio notification
   */
  async createPortfolioNotification(alert, portfolioData) {
    try {
      const severity = this.calculateAlertSeverity(alert, portfolioData);
      const message = this.formatAlertMessage(alert, portfolioData);

      const result = await query(`
        INSERT INTO portfolio_alert_notifications (
          alert_id, user_id, alert_type, symbol, 
          severity, message, portfolio_data, created_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())
        RETURNING *
      `, [
        alert.id,
        alert.user_id,
        alert.alert_type,
        alert.symbol,
        severity,
        message,
        JSON.stringify(portfolioData.summary)
      ]);

      return result.rows[0];
    } catch (error) {
      this.logger.error('Error creating portfolio notification', {
        alertId: alert.id,
        error: error.message,
        correlationId: this.correlationId
      });
      throw error;
    }
  }

  /**
   * Calculate alert severity
   */
  calculateAlertSeverity(alert, portfolioData) {
    const { alert_type, threshold } = alert;

    switch (alert_type) {
      case this.alertTypes.ALLOCATION_DRIFT:
        return threshold > 10 ? this.alertSeverity.HIGH : this.alertSeverity.MEDIUM;
      
      case this.alertTypes.POSITION_GAIN_LOSS:
        return Math.abs(threshold) > 20 ? this.alertSeverity.HIGH : this.alertSeverity.MEDIUM;
      
      case this.alertTypes.PORTFOLIO_VALUE_CHANGE:
        return Math.abs(threshold) > 15 ? this.alertSeverity.HIGH : this.alertSeverity.MEDIUM;
      
      case this.alertTypes.SECTOR_CONCENTRATION:
        return threshold > 40 ? this.alertSeverity.HIGH : this.alertSeverity.MEDIUM;
      
      case this.alertTypes.REBALANCE_NEEDED:
        return this.alertSeverity.HIGH;
      
      default:
        return this.alertSeverity.MEDIUM;
    }
  }

  /**
   * Format alert message
   */
  formatAlertMessage(alert, portfolioData) {
    const { alert_type, symbol, threshold, condition } = alert;
    const { summary } = portfolioData;

    switch (alert_type) {
      case this.alertTypes.ALLOCATION_DRIFT:
        return `Portfolio allocation has drifted beyond ${threshold}% threshold. Consider rebalancing.`;
      
      case this.alertTypes.POSITION_GAIN_LOSS:
        return `Position ${symbol} has ${condition} ${threshold}% gain/loss threshold.`;
      
      case this.alertTypes.PORTFOLIO_VALUE_CHANGE:
        return `Portfolio value has changed by more than ${threshold}%. Current value: $${parseFloat(summary.total_value || 0).toFixed(2)}`;
      
      case this.alertTypes.SECTOR_CONCENTRATION:
        return `Sector concentration exceeds ${threshold}% threshold. Consider diversification.`;
      
      case this.alertTypes.POSITION_SIZE_CHANGE:
        return `Position ${symbol} size has changed beyond ${threshold}% threshold.`;
      
      case this.alertTypes.BETA_CHANGE:
        return `Portfolio beta has ${condition} ${threshold} threshold. Current risk level may need adjustment.`;
      
      case this.alertTypes.REBALANCE_NEEDED:
        return `Portfolio rebalancing recommended. Top position exceeds ${threshold}% concentration.`;
      
      default:
        return `Portfolio alert triggered for ${alert_type}.`;
    }
  }

  /**
   * Update alert trigger count
   */
  async updateAlertTriggerCount(alertId) {
    try {
      await query(`
        UPDATE portfolio_alerts 
        SET trigger_count = trigger_count + 1,
            last_triggered = NOW()
        WHERE id = $1
      `, [alertId]);
    } catch (error) {
      this.logger.error('Error updating alert trigger count', {
        alertId,
        error: error.message,
        correlationId: this.correlationId
      });
    }
  }

  /**
   * Get portfolio alert notifications
   */
  async getPortfolioAlertNotifications(userId, limit = 50) {
    try {
      const result = await query(`
        SELECT 
          pan.*,
          pa.alert_type,
          pa.symbol,
          pa.message as alert_message
        FROM portfolio_alert_notifications pan
        JOIN portfolio_alerts pa ON pan.alert_id = pa.id
        WHERE pan.user_id = $1
        ORDER BY pan.created_at DESC
        LIMIT $2
      `, [userId, limit]);

      return result.rows;
    } catch (error) {
      this.logger.error('Error fetching portfolio alert notifications', {
        userId,
        error: error.message,
        correlationId: this.correlationId
      });
      throw error;
    }
  }

  /**
   * Update alert
   */
  async updatePortfolioAlert(alertId, userId, updates) {
    try {
      const {
        threshold,
        condition,
        isActive,
        notificationPreferences,
        expiryDate,
        message
      } = updates;

      const result = await query(`
        UPDATE portfolio_alerts 
        SET 
          threshold = COALESCE($3, threshold),
          condition = COALESCE($4, condition),
          is_active = COALESCE($5, is_active),
          notification_preferences = COALESCE($6, notification_preferences),
          expiry_date = COALESCE($7, expiry_date),
          message = COALESCE($8, message),
          updated_at = NOW()
        WHERE id = $1 AND user_id = $2
        RETURNING *
      `, [alertId, userId, threshold, condition, isActive, 
          notificationPreferences ? JSON.stringify(notificationPreferences) : null,
          expiryDate, message]);

      if (result.rows.length === 0) {
        throw new Error('Portfolio alert not found or access denied');
      }

      return result.rows[0];
    } catch (error) {
      this.logger.error('Error updating portfolio alert', {
        alertId,
        userId,
        error: error.message,
        correlationId: this.correlationId
      });
      throw error;
    }
  }

  /**
   * Delete portfolio alert
   */
  async deletePortfolioAlert(alertId, userId) {
    try {
      const result = await query(`
        DELETE FROM portfolio_alerts 
        WHERE id = $1 AND user_id = $2
        RETURNING *
      `, [alertId, userId]);

      if (result.rows.length === 0) {
        throw new Error('Portfolio alert not found or access denied');
      }

      return result.rows[0];
    } catch (error) {
      this.logger.error('Error deleting portfolio alert', {
        alertId,
        userId,
        error: error.message,
        correlationId: this.correlationId
      });
      throw error;
    }
  }
}

module.exports = PortfolioAlerts;