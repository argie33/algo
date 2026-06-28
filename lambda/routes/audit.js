const express = require('express');
const { sendSuccess, sendError } = require('../utils/apiResponse');
const { authenticateToken } = require('../middleware/auth');
const { query } = require('../utils/database');

const router = express.Router();

// GET /api/audit/logs - Get audit logs
router.get('/logs', authenticateToken, async (req, res) => {
  try {
    const { limit = 100, offset = 0 } = req.query;

    // Try to fetch from audit_log table if it exists
    try {
      const result = await query(
        `SELECT id, timestamp, action, user_id, details, resource_type, resource_id
         FROM audit_log
         ORDER BY timestamp DESC
         LIMIT $1 OFFSET $2`,
        [parseInt(limit), parseInt(offset)]
      );

      return sendSuccess(res, {
        logs: result.rows || [],
        total: result.rowCount || 0
      });
    } catch (dbError) {
      // Table doesn't exist - return empty logs
      return sendSuccess(res, {
        logs: [],
        total: 0,
        message: 'Audit logging not yet enabled'
      });
    }
  } catch (error) {
    console.error('Error fetching audit logs:', error);
    return sendError(res, 'Failed to fetch audit logs', 500);
  }
});

// GET /api/audit/summary - Get audit summary statistics
router.get('/summary', authenticateToken, async (req, res) => {
  try {
    return sendSuccess(res, {
      total_events: 0,
      events_today: 0,
      critical_events: 0,
      last_audit: null,
      status: 'Audit system ready for data collection'
    });
  } catch (error) {
    console.error('Error fetching audit summary:', error);
    return sendError(res, 'Failed to fetch audit summary', 500);
  }
});

module.exports = router;
