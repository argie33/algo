const { query } = require('./database');
const apiKeyService = require('./apiKeyService');
const AlpacaService = require('./alpacaService');

class WatchlistAlerts {
  constructor() {
    this.alertTypes = {
      PRICE_ABOVE: 'price_above',
      PRICE_BELOW: 'price_below',
      PRICE_CHANGE_PERCENT: 'price_change_percent',
      VOLUME_SPIKE: 'volume_spike',
      RSI_OVERBOUGHT: 'rsi_overbought',
      RSI_OVERSOLD: 'rsi_oversold',
      MACD_SIGNAL: 'macd_signal',
      MOVING_AVERAGE_CROSS: 'moving_average_cross',
      BREAKOUT: 'breakout',
      EARNINGS_DATE: 'earnings_date'
    };
    
    this.alertsQueue = [];
    this.processedAlerts = new Set();
    this.isProcessing = false;
  }

  // Create a new alert
  async createAlert(userId, alertConfig) {
    try {
      const {
        symbol,
        alertType,
        condition,
        targetValue,
        isActive = true,
        expiryDate = null,
        message = null
      } = alertConfig;

      // Validate alert configuration
      if (!symbol || !alertType || !condition || targetValue === undefined) {
        throw new Error('Missing required alert parameters');
      }

      if (!Object.values(this.alertTypes).includes(alertType)) {
        throw new Error('Invalid alert type');
      }

      // Insert alert into database
      const result = await query(`
        INSERT INTO watchlist_alerts (
          user_id, symbol, alert_type, condition, target_value, 
          is_active, expiry_date, message, created_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
        RETURNING *
      `, [userId, symbol, alertType, condition, targetValue, isActive, expiryDate, message]);

      return result.rows[0];
    } catch (error) {
      console.error('Error creating alert:', error);
      throw error;
    }
  }

  // Get user's alerts
  async getUserAlerts(userId, filters = {}) {
    try {
      let whereClause = 'WHERE user_id = $1';
      const params = [userId];
      let paramIndex = 2;

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

      if (filters.alertType) {
        whereClause += ` AND alert_type = $${paramIndex}`;
        params.push(filters.alertType);
        paramIndex++;
      }

      const result = await query(`
        SELECT 
          wa.*,
          sse.company_name,
          sse.sector,
          (
            SELECT COUNT(*) FROM alert_notifications an 
            WHERE an.alert_id = wa.id
          ) as notification_count,
          (
            SELECT MAX(created_at) FROM alert_notifications an 
            WHERE an.alert_id = wa.id
          ) as last_triggered
        FROM watchlist_alerts wa
        LEFT JOIN stock_symbols_enhanced sse ON wa.symbol = sse.symbol
        ${whereClause}
        ORDER BY wa.created_at DESC
      `, params);

      return result.rows;
    } catch (error) {
      console.error('Error fetching user alerts:', error);
      throw error;
    }
  }

  // Update alert
  async updateAlert(alertId, userId, updates) {
    try {
      const {
        isActive,
        targetValue,
        expiryDate,
        message
      } = updates;

      const result = await query(`
        UPDATE watchlist_alerts 
        SET 
          is_active = COALESCE($3, is_active),
          target_value = COALESCE($4, target_value),
          expiry_date = COALESCE($5, expiry_date),
          message = COALESCE($6, message),
          updated_at = NOW()
        WHERE id = $1 AND user_id = $2
        RETURNING *
      `, [alertId, userId, isActive, targetValue, expiryDate, message]);

      if (result.rows.length === 0) {
        throw new Error('Alert not found or access denied');
      }

      return result.rows[0];
    } catch (error) {
      console.error('Error updating alert:', error);
      throw error;
    }
  }

  // Delete alert
  async deleteAlert(alertId, userId) {
    try {
      const result = await query(`
        DELETE FROM watchlist_alerts 
        WHERE id = $1 AND user_id = $2
        RETURNING *
      `, [alertId, userId]);

      if (result.rows.length === 0) {
        throw new Error('Alert not found or access denied');
      }

      return result.rows[0];
    } catch (error) {
      console.error('Error deleting alert:', error);
      throw error;
    }
  }

  // Process all active alerts
  async processAlerts() {
    if (this.isProcessing) {
      console.log('Alert processing already in progress');
      return;
    }

    this.isProcessing = true;
    
    try {
      console.log('Starting alert processing...');
      
      // Get all active alerts
      const alerts = await this.getActiveAlerts();
      
      if (alerts.length === 0) {
        console.log('No active alerts to process');
        return;
      }

      console.log(`Processing ${alerts.length} active alerts`);
      
      // Group alerts by symbol to minimize API calls
      const alertsBySymbol = this.groupAlertsBySymbol(alerts);
      
      // Process each symbol's alerts
      for (const [symbol, symbolAlerts] of Object.entries(alertsBySymbol)) {
        try {
          await this.processSymbolAlerts(symbol, symbolAlerts);
        } catch (error) {
          console.error(`Error processing alerts for ${symbol}:`, error);
        }
      }

      console.log('Alert processing completed');
    } catch (error) {
      console.error('Error in alert processing:', error);
    } finally {
      this.isProcessing = false;
    }
  }

  // Get all active alerts
  async getActiveAlerts() {
    try {
      const result = await query(`
        SELECT 
          wa.*,
          sse.company_name,
          u.email,
          u.phone,
          unp.email_notifications,
          unp.push_notifications,
          unp.price_alerts
        FROM watchlist_alerts wa
        JOIN users u ON wa.user_id = u.id
        JOIN stock_symbols_enhanced sse ON wa.symbol = sse.symbol
        LEFT JOIN user_notification_preferences unp ON wa.user_id = unp.user_id
        WHERE wa.is_active = true
        AND (wa.expiry_date IS NULL OR wa.expiry_date > NOW())
        ORDER BY wa.symbol, wa.created_at
      `);

      return result.rows;
    } catch (error) {
      console.error('Error fetching active alerts:', error);
      return [];
    }
  }

  // Group alerts by symbol
  groupAlertsBySymbol(alerts) {
    const grouped = {};
    
    for (const alert of alerts) {
      if (!grouped[alert.symbol]) {
        grouped[alert.symbol] = [];
      }
      grouped[alert.symbol].push(alert);
    }
    
    return grouped;
  }

  // Process alerts for a specific symbol
  async processSymbolAlerts(symbol, alerts) {
    try {
      // Get current market data
      const marketData = await this.getMarketData(symbol);
      
      if (!marketData) {
        console.log(`No market data available for ${symbol}`);
        return;
      }

      // Get technical data
      const technicalData = await this.getTechnicalData(symbol);
      
      // Process each alert
      for (const alert of alerts) {
        try {
          const shouldTrigger = await this.checkAlertCondition(alert, marketData, technicalData);
          
          if (shouldTrigger) {
            await this.triggerAlert(alert, marketData);
          }
        } catch (error) {
          console.error(`Error processing alert ${alert.id}:`, error);
        }
      }
    } catch (error) {
      console.error(`Error processing symbol alerts for ${symbol}:`, error);
    }
  }

  // Check if alert condition is met
  async checkAlertCondition(alert, marketData, technicalData) {
    const { alert_type, condition, target_value } = alert;
    const currentPrice = marketData.close || marketData.price;
    
    switch (alert_type) {
      case this.alertTypes.PRICE_ABOVE:
        return currentPrice > target_value;
      
      case this.alertTypes.PRICE_BELOW:
        return currentPrice < target_value;
      
      case this.alertTypes.PRICE_CHANGE_PERCENT:
        const changePercent = ((currentPrice - marketData.previous_close) / marketData.previous_close) * 100;
        return condition === 'greater' ? changePercent > target_value : changePercent < target_value;
      
      case this.alertTypes.VOLUME_SPIKE:
        const volumeRatio = marketData.volume / marketData.average_volume;
        return volumeRatio > target_value;
      
      case this.alertTypes.RSI_OVERBOUGHT:
        return technicalData?.rsi > target_value;
      
      case this.alertTypes.RSI_OVERSOLD:
        return technicalData?.rsi < target_value;
      
      case this.alertTypes.MACD_SIGNAL:
        if (!technicalData?.macd || !technicalData?.macd_signal) return false;
        return condition === 'bullish' ? 
          technicalData.macd > technicalData.macd_signal : 
          technicalData.macd < technicalData.macd_signal;
      
      case this.alertTypes.MOVING_AVERAGE_CROSS:
        if (!technicalData?.sma_20 || !technicalData?.sma_50) return false;
        return condition === 'golden' ? 
          technicalData.sma_20 > technicalData.sma_50 : 
          technicalData.sma_20 < technicalData.sma_50;
      
      case this.alertTypes.BREAKOUT:
        const range = target_value; // breakout range percentage
        const highBreakout = currentPrice > marketData.high_52w * (1 - range/100);
        const lowBreakout = currentPrice < marketData.low_52w * (1 + range/100);
        return condition === 'upward' ? highBreakout : lowBreakout;
      
      default:
        return false;
    }
  }

  // Trigger an alert
  async triggerAlert(alert, marketData) {
    try {
      // Check if alert was already triggered recently (prevent spam)
      const recentTrigger = await this.checkRecentTrigger(alert.id);
      if (recentTrigger) {
        console.log(`Alert ${alert.id} was triggered recently, skipping`);
        return;
      }

      // Create notification record
      const notification = await this.createNotification(alert, marketData);
      
      // Send notifications based on user preferences
      if (alert.email_notifications && alert.email) {
        await this.sendEmailNotification(alert, marketData, notification);
      }
      
      if (alert.push_notifications) {
        await this.sendPushNotification(alert, marketData, notification);
      }

      // Update alert trigger count
      await this.updateAlertTriggerCount(alert.id);
      
      console.log(`Alert ${alert.id} triggered for ${alert.symbol}`);
    } catch (error) {
      console.error(`Error triggering alert ${alert.id}:`, error);
    }
  }

  // Check if alert was triggered recently
  async checkRecentTrigger(alertId, windowMinutes = 60) {
    try {
      const result = await query(`
        SELECT COUNT(*) as count
        FROM alert_notifications
        WHERE alert_id = $1
        AND created_at > NOW() - INTERVAL '${windowMinutes} minutes'
      `, [alertId]);

      return parseInt(result.rows[0].count) > 0;
    } catch (error) {
      console.error('Error checking recent trigger:', error);
      return false;
    }
  }

  // Create notification record
  async createNotification(alert, marketData) {
    try {
      const result = await query(`
        INSERT INTO alert_notifications (
          alert_id, user_id, symbol, alert_type, 
          trigger_value, market_data, created_at
        ) VALUES ($1, $2, $3, $4, $5, $6, NOW())
        RETURNING *
      `, [
        alert.id,
        alert.user_id,
        alert.symbol,
        alert.alert_type,
        marketData.close || marketData.price,
        JSON.stringify(marketData)
      ]);

      return result.rows[0];
    } catch (error) {
      console.error('Error creating notification:', error);
      throw error;
    }
  }

  // Send email notification
  async sendEmailNotification(alert, marketData, notification) {
    try {
      // This would integrate with an email service like SendGrid, SES, etc.
      // For now, just log the notification
      console.log('Email notification would be sent:', {
        to: alert.email,
        subject: `Price Alert: ${alert.symbol} - ${alert.alert_type}`,
        body: this.formatAlertMessage(alert, marketData)
      });
    } catch (error) {
      console.error('Error sending email notification:', error);
    }
  }

  // Send push notification
  async sendPushNotification(alert, marketData, notification) {
    try {
      // This would integrate with a push notification service
      // For now, just log the notification
      console.log('Push notification would be sent:', {
        userId: alert.user_id,
        title: `${alert.symbol} Alert`,
        body: this.formatAlertMessage(alert, marketData),
        data: {
          alertId: alert.id,
          symbol: alert.symbol,
          alertType: alert.alert_type,
          price: marketData.close || marketData.price
        }
      });
    } catch (error) {
      console.error('Error sending push notification:', error);
    }
  }

  // Format alert message
  formatAlertMessage(alert, marketData) {
    const price = marketData.close || marketData.price;
    const symbol = alert.symbol;
    const companyName = alert.company_name || symbol;
    
    switch (alert.alert_type) {
      case this.alertTypes.PRICE_ABOVE:
        return `${companyName} (${symbol}) is now above $${alert.target_value}. Current price: $${price.toFixed(2)}`;
      
      case this.alertTypes.PRICE_BELOW:
        return `${companyName} (${symbol}) is now below $${alert.target_value}. Current price: $${price.toFixed(2)}`;
      
      case this.alertTypes.PRICE_CHANGE_PERCENT:
        const changePercent = ((price - marketData.previous_close) / marketData.previous_close) * 100;
        return `${companyName} (${symbol}) has moved ${changePercent.toFixed(2)}% today. Current price: $${price.toFixed(2)}`;
      
      case this.alertTypes.VOLUME_SPIKE:
        return `${companyName} (${symbol}) has unusual volume activity. Current price: $${price.toFixed(2)}`;
      
      case this.alertTypes.RSI_OVERBOUGHT:
        return `${companyName} (${symbol}) RSI is overbought. Current price: $${price.toFixed(2)}`;
      
      case this.alertTypes.RSI_OVERSOLD:
        return `${companyName} (${symbol}) RSI is oversold. Current price: $${price.toFixed(2)}`;
      
      default:
        return `${companyName} (${symbol}) alert triggered. Current price: $${price.toFixed(2)}`;
    }
  }

  // Update alert trigger count
  async updateAlertTriggerCount(alertId) {
    try {
      await query(`
        UPDATE watchlist_alerts 
        SET trigger_count = trigger_count + 1,
            last_triggered = NOW()
        WHERE id = $1
      `, [alertId]);
    } catch (error) {
      console.error('Error updating alert trigger count:', error);
    }
  }

  // Get market data for symbol
  async getMarketData(symbol) {
    try {
      // Try to get from database first
      const result = await query(`
        SELECT 
          symbol, date, open, high, low, close, volume,
          LAG(close) OVER (ORDER BY date) as previous_close
        FROM stock_data
        WHERE symbol = $1
        ORDER BY date DESC
        LIMIT 1
      `, [symbol]);

      if (result.rows.length > 0) {
        return result.rows[0];
      }

      // If no database data, try to get from API
      // This would require user API keys - for now return null
      return null;
    } catch (error) {
      console.error('Error fetching market data:', error);
      return null;
    }
  }

  // Get technical data for symbol
  async getTechnicalData(symbol) {
    try {
      const result = await query(`
        SELECT *
        FROM technical_data_daily
        WHERE symbol = $1
        ORDER BY date DESC
        LIMIT 1
      `, [symbol]);

      return result.rows[0] || null;
    } catch (error) {
      console.error('Error fetching technical data:', error);
      return null;
    }
  }

  // Get alert notifications for user
  async getAlertNotifications(userId, limit = 50) {
    try {
      const result = await query(`
        SELECT 
          an.*,
          wa.symbol,
          wa.alert_type,
          wa.message,
          sse.company_name
        FROM alert_notifications an
        JOIN watchlist_alerts wa ON an.alert_id = wa.id
        JOIN stock_symbols_enhanced sse ON wa.symbol = sse.symbol
        WHERE an.user_id = $1
        ORDER BY an.created_at DESC
        LIMIT $2
      `, [userId, limit]);

      return result.rows;
    } catch (error) {
      console.error('Error fetching alert notifications:', error);
      throw error;
    }
  }

  // Mark notification as read
  async markNotificationAsRead(notificationId, userId) {
    try {
      const result = await query(`
        UPDATE alert_notifications 
        SET is_read = true, read_at = NOW()
        WHERE id = $1 AND user_id = $2
        RETURNING *
      `, [notificationId, userId]);

      return result.rows[0];
    } catch (error) {
      console.error('Error marking notification as read:', error);
      throw error;
    }
  }

  // Start alert processing interval
  startAlertProcessing(intervalMinutes = 5) {
    console.log(`Starting alert processing with ${intervalMinutes} minute interval`);
    
    // Initial processing
    this.processAlerts();
    
    // Set up interval
    setInterval(() => {
      this.processAlerts();
    }, intervalMinutes * 60 * 1000);
  }
}

module.exports = WatchlistAlerts;