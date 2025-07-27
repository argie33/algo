/**
 * Crypto Alerts Routes
 * 
 * API endpoints for cryptocurrency price alerts management
 */

const express = require('express');
const router = express.Router();
const cryptoAlertsService = require('../services/cryptoAlertsService');
const cryptoErrorHandler = require('../utils/cryptoErrorHandler');
const { StructuredLogger } = require('../utils/structuredLogger');

const logger = new StructuredLogger('crypto-alerts-routes');

// GET /crypto-alerts/:userId - Get user's alerts
router.get('/:userId', async (req, res) => {
  try {
    const { userId } = req.params;
    const {
      activeOnly = false,
      symbol = null,
      limit = 50,
      offset = 0
    } = req.query;

    logger.info('Fetching user crypto alerts', {
      user_id: userId,
      active_only: activeOnly,
      symbol: symbol,
      limit: parseInt(limit)
    });

    const alerts = await cryptoAlertsService.getUserAlerts(userId, {
      activeOnly: activeOnly === 'true',
      symbol: symbol,
      limit: parseInt(limit),
      offset: parseInt(offset)
    });

    res.json(alerts);

  } catch (error) {
    logger.error('Failed to fetch user alerts', error, { user_id: req.params.userId });
    
    const errorResponse = cryptoErrorHandler.handleError(error, {
      endpoint: '/crypto-alerts/:userId',
      dataType: 'alerts',
      userId: req.params.userId
    });
    
    res.status(500).json({
      success: false,
      error: errorResponse
    });
  }
});

// POST /crypto-alerts/:userId - Create new alert
router.post('/:userId', async (req, res) => {
  try {
    const { userId } = req.params;
    const alertData = req.body;

    // Validate required fields
    const { symbol, alertType, targetValue } = alertData;
    if (!symbol || !alertType || targetValue === undefined) {
      return res.status(400).json({
        success: false,
        error: 'Missing required fields: symbol, alertType, targetValue'
      });
    }

    logger.info('Creating crypto alert', {
      user_id: userId,
      symbol: symbol,
      alert_type: alertType,
      target_value: targetValue
    });

    const result = await cryptoAlertsService.createAlert(userId, alertData);

    res.status(201).json(result);

  } catch (error) {
    logger.error('Failed to create alert', error, { user_id: req.params.userId });
    
    const errorResponse = cryptoErrorHandler.handleError(error, {
      endpoint: '/crypto-alerts/:userId',
      dataType: 'alert_creation'
    });
    
    res.status(500).json({
      success: false,
      error: errorResponse
    });
  }
});

// PUT /crypto-alerts/:userId/:alertId - Update alert
router.put('/:userId/:alertId', async (req, res) => {
  try {
    const { userId, alertId } = req.params;
    const updateData = req.body;

    logger.info('Updating crypto alert', {
      user_id: userId,
      alert_id: alertId,
      update_fields: Object.keys(updateData)
    });

    const result = await cryptoAlertsService.updateAlert(userId, parseInt(alertId), updateData);

    res.json(result);

  } catch (error) {
    logger.error('Failed to update alert', error, {
      user_id: req.params.userId,
      alert_id: req.params.alertId
    });
    
    const errorResponse = cryptoErrorHandler.handleError(error, {
      endpoint: '/crypto-alerts/:userId/:alertId',
      dataType: 'alert_update'
    });
    
    res.status(500).json({
      success: false,
      error: errorResponse
    });
  }
});

// DELETE /crypto-alerts/:userId/:alertId - Delete alert
router.delete('/:userId/:alertId', async (req, res) => {
  try {
    const { userId, alertId } = req.params;

    logger.info('Deleting crypto alert', {
      user_id: userId,
      alert_id: alertId
    });

    const result = await cryptoAlertsService.deleteAlert(userId, parseInt(alertId));

    res.json(result);

  } catch (error) {
    logger.error('Failed to delete alert', error, {
      user_id: req.params.userId,
      alert_id: req.params.alertId
    });
    
    const errorResponse = cryptoErrorHandler.handleError(error, {
      endpoint: '/crypto-alerts/:userId/:alertId',
      dataType: 'alert_deletion'
    });
    
    res.status(500).json({
      success: false,
      error: errorResponse
    });
  }
});

// GET /crypto-alerts/:userId/stats - Get alert statistics
router.get('/:userId/stats', async (req, res) => {
  try {
    const { userId } = req.params;

    logger.info('Fetching alert statistics', { user_id: userId });

    const stats = await cryptoAlertsService.getAlertStats(userId);

    res.json(stats);

  } catch (error) {
    logger.error('Failed to fetch alert statistics', error, { user_id: req.params.userId });
    
    const errorResponse = cryptoErrorHandler.handleError(error, {
      endpoint: '/crypto-alerts/:userId/stats',
      dataType: 'alert_statistics'
    });
    
    res.status(500).json({
      success: false,
      error: errorResponse
    });
  }
});

// POST /crypto-alerts/monitoring/start - Start alert monitoring (admin endpoint)
router.post('/monitoring/start', async (req, res) => {
  try {
    const { intervalMinutes = 5 } = req.body;

    logger.info('Starting alert monitoring', { interval_minutes: intervalMinutes });

    await cryptoAlertsService.startMonitoring(intervalMinutes);

    res.json({
      success: true,
      message: 'Alert monitoring started',
      interval_minutes: intervalMinutes
    });

  } catch (error) {
    logger.error('Failed to start alert monitoring', error);
    
    res.status(500).json({
      success: false,
      error: 'Failed to start alert monitoring'
    });
  }
});

// POST /crypto-alerts/monitoring/stop - Stop alert monitoring (admin endpoint)
router.post('/monitoring/stop', async (req, res) => {
  try {
    logger.info('Stopping alert monitoring');

    cryptoAlertsService.stopMonitoring();

    res.json({
      success: true,
      message: 'Alert monitoring stopped'
    });

  } catch (error) {
    logger.error('Failed to stop alert monitoring', error);
    
    res.status(500).json({
      success: false,
      error: 'Failed to stop alert monitoring'
    });
  }
});

// GET /crypto-alerts/monitoring/status - Get monitoring status
router.get('/monitoring/status', async (req, res) => {
  try {
    const status = {
      isMonitoring: cryptoAlertsService.isMonitoring,
      lastCheckTime: cryptoAlertsService.lastCheckTime,
      timestamp: new Date().toISOString()
    };

    res.json({
      success: true,
      data: status
    });

  } catch (error) {
    logger.error('Failed to get monitoring status', error);
    
    res.status(500).json({
      success: false,
      error: 'Failed to get monitoring status'
    });
  }
});

// POST /crypto-alerts/monitoring/check - Manually trigger alert check (admin endpoint)
router.post('/monitoring/check', async (req, res) => {
  try {
    logger.info('Manually triggering alert check');

    await cryptoAlertsService.checkAllAlerts();

    res.json({
      success: true,
      message: 'Alert check completed',
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    logger.error('Failed to trigger alert check', error);
    
    res.status(500).json({
      success: false,
      error: 'Failed to trigger alert check'
    });
  }
});

module.exports = router;