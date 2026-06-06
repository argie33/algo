/**
 * Notifications API Routes
 *
 * Endpoints:
 * - GET /api/algo/notifications - Get user notifications with filtering
 * - PATCH /api/algo/notifications/:id/read - Mark notification as read
 * - DELETE /api/algo/notifications/:id - Delete notification
 */

const express = require('express');
const { getPool } = require('../utils/database');
const { authenticateToken } = require('../middleware/auth');
const { sendSuccess, sendError } = require('../utils/apiResponse');
const logger = require('../utils/logger');

const router = express.Router();

/**
 * GET /api/algo/notifications
 * Get notifications with optional filtering
 * Query params: kind, severity, unread, include_seen, limit
 */
router.get('/', authenticateToken, async (req, res) => {
  try {
    const pool = getPool();
    const { kind, severity, unread, include_seen, limit = 50 } = req.query;
    const user_id = req.user?.id || 'system';

    // Build dynamic query based on filters
    let query = `
      SELECT
        id,
        kind,
        severity,
        title,
        message,
        seen,
        created_at,
        updated_at,
        metadata
      FROM algo_notifications
      WHERE user_id = $1
    `;
    const params = [user_id];
    let paramCount = 1;

    // Apply filters
    if (kind && kind !== 'all') {
      paramCount++;
      query += ` AND kind = $${paramCount}`;
      params.push(kind);
    }

    if (severity && severity !== 'all') {
      paramCount++;
      query += ` AND severity = $${paramCount}`;
      params.push(severity);
    }

    if (unread === 'true') {
      query += ` AND seen = false`;
    }

    // Only include unseen unless explicitly requested
    if (include_seen !== '1') {
      query += ` AND seen = false`;
    }

    query += ` ORDER BY created_at DESC LIMIT $${paramCount + 1}`;
    params.push(parseInt(limit) || 50);

    const result = await pool.query(query, params);

    const items = result.rows.map(row => ({
      id: row.id,
      kind: row.kind,
      severity: row.severity,
      title: row.title,
      message: row.message,
      seen: row.seen,
      created_at: row.created_at,
      updated_at: row.updated_at,
      metadata: row.metadata || {}
    }));

    const unreadCount = items.filter(n => !n.seen).length;

    return sendSuccess(res, {
      items,
      unread_count: unreadCount,
      total_count: items.length
    });
  } catch (error) {
    logger.error('Failed to fetch notifications', error);
    return sendError(res, 500, 'Failed to fetch notifications');
  }
});

/**
 * PATCH /api/algo/notifications/:id/read
 * Mark a notification as read
 */
router.patch('/:id/read', authenticateToken, async (req, res) => {
  try {
    const pool = getPool();
    const { id } = req.params;
    const user_id = req.user?.id || 'system';

    const result = await pool.query(
      `UPDATE algo_notifications
       SET seen = true, updated_at = NOW()
       WHERE id = $1 AND user_id = $2
       RETURNING id, seen, updated_at`,
      [id, user_id]
    );

    if (result.rows.length === 0) {
      return sendError(res, 404, 'Notification not found');
    }

    return sendSuccess(res, {
      id: result.rows[0].id,
      seen: result.rows[0].seen,
      updated_at: result.rows[0].updated_at
    });
  } catch (error) {
    logger.error('Failed to mark notification as read', error);
    return sendError(res, 500, 'Failed to update notification');
  }
});

/**
 * DELETE /api/algo/notifications/:id
 * Delete a notification
 */
router.delete('/:id', authenticateToken, async (req, res) => {
  try {
    const pool = getPool();
    const { id } = req.params;
    const user_id = req.user?.id || 'system';

    const result = await pool.query(
      `DELETE FROM algo_notifications
       WHERE id = $1 AND user_id = $2
       RETURNING id`,
      [id, user_id]
    );

    if (result.rows.length === 0) {
      return sendError(res, 404, 'Notification not found');
    }

    return sendSuccess(res, { deleted_id: result.rows[0].id });
  } catch (error) {
    logger.error('Failed to delete notification', error);
    return sendError(res, 500, 'Failed to delete notification');
  }
});

module.exports = router;
