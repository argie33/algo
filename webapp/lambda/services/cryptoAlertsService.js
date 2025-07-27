/**
 * Crypto Alerts Service
 * 
 * Comprehensive cryptocurrency alerts management with real-time monitoring,
 * multiple notification channels, and intelligent price tracking
 */

const { query } = require('../utils/database');
const enhancedCryptoDataService = require('./enhancedCryptoDataService');
const { StructuredLogger } = require('../utils/structuredLogger');
const logger = new StructuredLogger('crypto-alerts');

class CryptoAlertsService {
  constructor() {
    this.logger = logger;
    this.alertCheckInterval = null;
    this.isMonitoring = false;
    this.priceCache = new Map();
    this.lastCheckTime = null;
    
    console.log('🚨 Crypto Alerts Service initialized');
  }

  /**
   * Create a new price alert
   */
  async createAlert(userId, alertData) {
    try {
      const {
        symbol,
        alertType,
        targetValue,
        notificationMethods = ['email'],
        message = '',
        isActive = true
      } = alertData;

      // Validate alert type
      const validTypes = ['price_above', 'price_below', 'percent_change'];
      if (!validTypes.includes(alertType)) {
        throw new Error(`Invalid alert type. Must be one of: ${validTypes.join(', ')}`);
      }

      // Get current price for context
      const currentPrice = await this.getCurrentPrice(symbol);

      const insertQuery = `
        INSERT INTO crypto_alerts (
          user_id, symbol, alert_type, target_value, current_value,
          notification_methods, message, is_active, created_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, CURRENT_TIMESTAMP)
        RETURNING *
      `;

      const result = await query(insertQuery, [
        userId,
        symbol.toUpperCase(),
        alertType,
        targetValue,
        currentPrice,
        notificationMethods,
        message,
        isActive
      ]);

      this.logger.info('Alert created', {
        user_id: userId,
        symbol: symbol,
        alert_type: alertType,
        target_value: targetValue,
        alert_id: result.rows[0].id
      });

      return {
        success: true,
        data: result.rows[0]
      };

    } catch (error) {
      this.logger.error('Failed to create alert', error, { user_id: userId, symbol: alertData.symbol });
      throw new Error(`Alert creation failed: ${error.message}`);
    }
  }

  /**
   * Get user's alerts
   */
  async getUserAlerts(userId, options = {}) {
    try {
      const {
        activeOnly = false,
        symbol = null,
        limit = 50,
        offset = 0
      } = options;

      let whereClause = 'WHERE user_id = $1';
      let params = [userId];
      let paramCount = 1;

      if (activeOnly) {
        whereClause += ` AND is_active = true`;
      }

      if (symbol) {
        paramCount++;
        whereClause += ` AND symbol = $${paramCount}`;
        params.push(symbol.toUpperCase());
      }

      const alertsQuery = `
        SELECT 
          a.*,
          ca.name as asset_name,
          ca.coingecko_id
        FROM crypto_alerts a
        LEFT JOIN crypto_assets ca ON a.symbol = ca.symbol
        ${whereClause}
        ORDER BY a.created_at DESC
        LIMIT $${paramCount + 1} OFFSET $${paramCount + 2}
      `;

      params.push(limit, offset);

      const result = await query(alertsQuery, params);
      
      // Enrich alerts with current prices and status
      const enrichedAlerts = await Promise.all(
        result.rows.map(async (alert) => {
          const currentPrice = await this.getCurrentPrice(alert.symbol);
          const alertStatus = this.calculateAlertStatus(alert, currentPrice);
          
          return {
            ...alert,
            current_price: currentPrice,
            status: alertStatus,
            distance_to_target: this.calculateDistanceToTarget(alert, currentPrice),
            formatted_target: this.formatPrice(alert.target_value),
            formatted_current: this.formatPrice(currentPrice)
          };
        })
      );

      return {
        success: true,
        data: enrichedAlerts,
        metadata: {
          total_alerts: enrichedAlerts.length,
          active_alerts: enrichedAlerts.filter(a => a.is_active).length,
          triggered_alerts: enrichedAlerts.filter(a => a.condition_met).length
        }
      };

    } catch (error) {
      this.logger.error('Failed to get user alerts', error, { user_id: userId });
      throw new Error(`Failed to get alerts: ${error.message}`);
    }
  }

  /**
   * Update an alert
   */
  async updateAlert(userId, alertId, updateData) {
    try {
      const {
        targetValue,
        notificationMethods,
        message,
        isActive
      } = updateData;

      // Build dynamic update query
      const updates = [];
      const params = [];
      let paramCount = 0;

      if (targetValue !== undefined) {
        paramCount++;
        updates.push(`target_value = $${paramCount}`);
        params.push(targetValue);
      }

      if (notificationMethods !== undefined) {
        paramCount++;
        updates.push(`notification_methods = $${paramCount}`);
        params.push(notificationMethods);
      }

      if (message !== undefined) {
        paramCount++;
        updates.push(`message = $${paramCount}`);
        params.push(message);
      }

      if (isActive !== undefined) {
        paramCount++;
        updates.push(`is_active = $${paramCount}`);
        params.push(isActive);
      }

      if (updates.length === 0) {
        throw new Error('No valid update fields provided');
      }

      // Add updated_at timestamp
      paramCount++;
      updates.push(`updated_at = $${paramCount}`);
      params.push(new Date());

      // Add WHERE conditions
      paramCount++;
      params.push(alertId);
      paramCount++;
      params.push(userId);

      const updateQuery = `
        UPDATE crypto_alerts 
        SET ${updates.join(', ')}
        WHERE id = $${paramCount - 1} AND user_id = $${paramCount}
        RETURNING *
      `;

      const result = await query(updateQuery, params);

      if (result.rowCount === 0) {
        throw new Error('Alert not found or does not belong to user');
      }

      this.logger.info('Alert updated', {
        user_id: userId,
        alert_id: alertId,
        updated_fields: Object.keys(updateData)
      });

      return {
        success: true,
        data: result.rows[0]
      };

    } catch (error) {
      this.logger.error('Failed to update alert', error, { user_id: userId, alert_id: alertId });
      throw new Error(`Alert update failed: ${error.message}`);
    }
  }

  /**
   * Delete an alert
   */
  async deleteAlert(userId, alertId) {
    try {
      const deleteQuery = `
        DELETE FROM crypto_alerts 
        WHERE id = $1 AND user_id = $2
        RETURNING *
      `;

      const result = await query(deleteQuery, [alertId, userId]);

      if (result.rowCount === 0) {
        throw new Error('Alert not found or does not belong to user');
      }

      this.logger.info('Alert deleted', {
        user_id: userId,
        alert_id: alertId,
        symbol: result.rows[0].symbol
      });

      return {
        success: true,
        data: result.rows[0]
      };

    } catch (error) {
      this.logger.error('Failed to delete alert', error, { user_id: userId, alert_id: alertId });
      throw new Error(`Alert deletion failed: ${error.message}`);
    }
  }

  /**
   * Start monitoring alerts (runs periodically)
   */
  async startMonitoring(intervalMinutes = 5) {
    if (this.isMonitoring) {
      this.logger.info('Alert monitoring already running');
      return;
    }

    this.isMonitoring = true;
    const intervalMs = intervalMinutes * 60 * 1000;

    this.logger.info('Starting crypto alerts monitoring', { interval_minutes: intervalMinutes });

    // Run initial check
    await this.checkAllAlerts();

    // Set up periodic checking
    this.alertCheckInterval = setInterval(async () => {
      try {
        await this.checkAllAlerts();
      } catch (error) {
        this.logger.error('Error in alert monitoring cycle', error);
      }
    }, intervalMs);
  }

  /**
   * Stop monitoring alerts
   */
  stopMonitoring() {
    if (this.alertCheckInterval) {
      clearInterval(this.alertCheckInterval);
      this.alertCheckInterval = null;
    }
    this.isMonitoring = false;
    this.logger.info('Alert monitoring stopped');
  }

  /**
   * Check all active alerts and trigger notifications
   */
  async checkAllAlerts() {
    try {
      this.lastCheckTime = new Date();
      this.logger.info('Checking all active alerts');

      // Get all active alerts
      const activeAlertsQuery = `
        SELECT * FROM crypto_alerts 
        WHERE is_active = true 
          AND condition_met = false
        ORDER BY symbol, user_id
      `;

      const result = await query(activeAlertsQuery);
      const activeAlerts = result.rows;

      if (activeAlerts.length === 0) {
        this.logger.info('No active alerts to check');
        return;
      }

      // Group alerts by symbol to minimize API calls
      const alertsBySymbol = this.groupAlertsBySymbol(activeAlerts);
      const symbols = Object.keys(alertsBySymbol);

      this.logger.info('Checking alerts for symbols', { 
        symbols: symbols, 
        total_alerts: activeAlerts.length 
      });

      // Get current prices for all symbols
      const currentPrices = await this.getCurrentPrices(symbols);

      // Check each alert
      const triggeredAlerts = [];
      for (const [symbol, alerts] of Object.entries(alertsBySymbol)) {
        const currentPrice = currentPrices[symbol.toLowerCase()] || 0;
        
        for (const alert of alerts) {
          const isTriggered = await this.checkSingleAlert(alert, currentPrice);
          if (isTriggered) {
            triggeredAlerts.push({ ...alert, current_price: currentPrice });
          }
        }
      }

      if (triggeredAlerts.length > 0) {
        this.logger.info('Alerts triggered', { 
          count: triggeredAlerts.length,
          alerts: triggeredAlerts.map(a => ({ id: a.id, symbol: a.symbol, type: a.alert_type }))
        });

        // Send notifications for triggered alerts
        await this.processTriggeredAlerts(triggeredAlerts);
      }

    } catch (error) {
      this.logger.error('Failed to check alerts', error);
    }
  }

  /**
   * Check a single alert against current price
   */
  async checkSingleAlert(alert, currentPrice) {
    try {
      let isTriggered = false;

      switch (alert.alert_type) {
        case 'price_above':
          isTriggered = currentPrice >= alert.target_value;
          break;
        case 'price_below':
          isTriggered = currentPrice <= alert.target_value;
          break;
        case 'percent_change':
          // Calculate percentage change from when alert was created
          const percentChange = ((currentPrice - alert.current_value) / alert.current_value) * 100;
          isTriggered = Math.abs(percentChange) >= Math.abs(alert.target_value);
          break;
        default:
          this.logger.warn('Unknown alert type', { alert_id: alert.id, type: alert.alert_type });
          return false;
      }

      if (isTriggered) {
        // Update alert status in database
        await this.markAlertTriggered(alert.id, currentPrice);
        return true;
      }

      // Update current price for tracking
      await this.updateAlertCurrentPrice(alert.id, currentPrice);
      return false;

    } catch (error) {
      this.logger.error('Failed to check single alert', error, { alert_id: alert.id });
      return false;
    }
  }

  /**
   * Mark alert as triggered and update database
   */
  async markAlertTriggered(alertId, currentPrice) {
    try {
      const updateQuery = `
        UPDATE crypto_alerts 
        SET 
          condition_met = true,
          current_value = $1,
          triggered_at = CURRENT_TIMESTAMP,
          updated_at = CURRENT_TIMESTAMP
        WHERE id = $2
      `;

      await query(updateQuery, [currentPrice, alertId]);
      
    } catch (error) {
      this.logger.error('Failed to mark alert as triggered', error, { alert_id: alertId });
    }
  }

  /**
   * Update alert's current price for tracking
   */
  async updateAlertCurrentPrice(alertId, currentPrice) {
    try {
      const updateQuery = `
        UPDATE crypto_alerts 
        SET current_value = $1, updated_at = CURRENT_TIMESTAMP
        WHERE id = $2
      `;

      await query(updateQuery, [currentPrice, alertId]);
      
    } catch (error) {
      this.logger.error('Failed to update alert current price', error, { alert_id: alertId });
    }
  }

  /**
   * Process triggered alerts and send notifications
   */
  async processTriggeredAlerts(triggeredAlerts) {
    for (const alert of triggeredAlerts) {
      try {
        await this.sendAlertNotification(alert);
      } catch (error) {
        this.logger.error('Failed to send notification for alert', error, { alert_id: alert.id });
      }
    }
  }

  /**
   * Send notification for triggered alert
   */
  async sendAlertNotification(alert) {
    try {
      const notificationData = {
        userId: alert.user_id,
        alertId: alert.id,
        symbol: alert.symbol,
        alertType: alert.alert_type,
        targetValue: alert.target_value,
        currentPrice: alert.current_price,
        message: alert.message || this.generateDefaultMessage(alert),
        methods: alert.notification_methods || ['email']
      };

      // For now, just log the notification (in production, implement actual notifications)
      this.logger.info('Alert notification triggered', notificationData);

      // Mark notification as sent
      await query(
        'UPDATE crypto_alerts SET notification_sent = true WHERE id = $1',
        [alert.id]
      );

      // TODO: Implement actual notification sending (email, push, SMS, etc.)
      // await this.emailService.sendAlertEmail(notificationData);
      // await this.pushService.sendPushNotification(notificationData);

    } catch (error) {
      this.logger.error('Failed to send alert notification', error, { alert_id: alert.id });
    }
  }

  /**
   * Helper methods
   */
  async getCurrentPrice(symbol) {
    try {
      // Check cache first
      const cached = this.priceCache.get(symbol.toLowerCase());
      if (cached && Date.now() - cached.timestamp < 60000) { // 1 minute cache
        return cached.price;
      }

      // Get from crypto data service
      const prices = await enhancedCryptoDataService.getRealTimePrices([symbol.toLowerCase()]);
      if (prices.success && prices.data.length > 0) {
        const price = prices.data[0].current_price;
        this.priceCache.set(symbol.toLowerCase(), { price, timestamp: Date.now() });
        return price;
      }

      return 0;
    } catch (error) {
      this.logger.error('Failed to get current price', error, { symbol });
      return 0;
    }
  }

  async getCurrentPrices(symbols) {
    try {
      const prices = {};
      const lowerCaseSymbols = symbols.map(s => s.toLowerCase());
      
      const priceData = await enhancedCryptoDataService.getRealTimePrices(lowerCaseSymbols);
      
      if (priceData.success) {
        priceData.data.forEach(coin => {
          prices[coin.symbol.toLowerCase()] = coin.current_price;
          // Update cache
          this.priceCache.set(coin.symbol.toLowerCase(), { 
            price: coin.current_price, 
            timestamp: Date.now() 
          });
        });
      }

      return prices;
    } catch (error) {
      this.logger.error('Failed to get current prices', error, { symbols });
      return {};
    }
  }

  groupAlertsBySymbol(alerts) {
    return alerts.reduce((groups, alert) => {
      const symbol = alert.symbol.toUpperCase();
      if (!groups[symbol]) {
        groups[symbol] = [];
      }
      groups[symbol].push(alert);
      return groups;
    }, {});
  }

  calculateAlertStatus(alert, currentPrice) {
    if (alert.condition_met) return 'triggered';
    if (!alert.is_active) return 'inactive';

    const distance = this.calculateDistanceToTarget(alert, currentPrice);
    if (distance <= 5) return 'close'; // Within 5% of target
    if (distance <= 15) return 'approaching'; // Within 15% of target
    return 'watching';
  }

  calculateDistanceToTarget(alert, currentPrice) {
    if (alert.alert_type === 'percent_change') {
      const percentChange = ((currentPrice - alert.current_value) / alert.current_value) * 100;
      return Math.abs(Math.abs(percentChange) - Math.abs(alert.target_value));
    } else {
      return Math.abs((currentPrice - alert.target_value) / alert.target_value) * 100;
    }
  }

  formatPrice(price) {
    if (price >= 1) {
      return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD',
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
      }).format(price);
    } else {
      return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD',
        minimumFractionDigits: 4,
        maximumFractionDigits: 6
      }).format(price);
    }
  }

  generateDefaultMessage(alert) {
    const symbol = alert.symbol.toUpperCase();
    const target = this.formatPrice(alert.target_value);
    
    switch (alert.alert_type) {
      case 'price_above':
        return `${symbol} has reached ${target} or higher`;
      case 'price_below':
        return `${symbol} has dropped to ${target} or lower`;
      case 'percent_change':
        return `${symbol} has changed by ${alert.target_value}% or more`;
      default:
        return `${symbol} alert triggered`;
    }
  }

  /**
   * Get alert statistics for user
   */
  async getAlertStats(userId) {
    try {
      const statsQuery = `
        SELECT 
          COUNT(*) as total_alerts,
          COUNT(*) FILTER (WHERE is_active = true) as active_alerts,
          COUNT(*) FILTER (WHERE condition_met = true) as triggered_alerts,
          COUNT(*) FILTER (WHERE is_active = true AND condition_met = false) as pending_alerts,
          COUNT(DISTINCT symbol) as watched_symbols
        FROM crypto_alerts 
        WHERE user_id = $1
      `;

      const result = await query(statsQuery, [userId]);
      return {
        success: true,
        data: result.rows[0]
      };

    } catch (error) {
      this.logger.error('Failed to get alert stats', error, { user_id: userId });
      throw new Error(`Failed to get alert statistics: ${error.message}`);
    }
  }
}

// Export singleton instance
module.exports = new CryptoAlertsService();