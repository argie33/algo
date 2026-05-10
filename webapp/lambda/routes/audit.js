/**
 * Audit Logs Endpoint
 * Provides access to audit trails for trades, config changes, and safeguard activations
 */

const express = require("express");
const { query } = require("../utils/database");
const { sendSuccess, sendError } = require('../utils/apiResponse');
const { authenticateToken, requireAdmin } = require('../middleware/auth');
const router = express.Router();

// Protect all audit endpoints with auth + admin role
router.use(authenticateToken, requireAdmin);

// GET /api/audit/trades - Trading audit log
router.get("/trades", async (req, res) => {
  try {
    const limit = Math.min(parseInt(req.query.limit) || 100, 1000);
    const offset = parseInt(req.query.offset) || 0;
    const symbol = req.query.symbol ? req.query.symbol.toUpperCase() : null;

    let sql = "SELECT * FROM algo_audit_log";
    const params = [];

    if (symbol) {
      sql += " WHERE symbol = $1";
      params.push(symbol);
    }

    sql += " ORDER BY created_at DESC LIMIT $" + (params.length + 1) + " OFFSET $" + (params.length + 2);
    params.push(limit, offset);

    const result = await query(sql, params);

    // Get total count
    let countSql = "SELECT COUNT(*) as total FROM algo_audit_log";
    if (symbol) {
      countSql += " WHERE symbol = $1";
    }

    const countResult = await query(
      countSql,
      symbol ? [symbol] : []
    );

    return sendSuccess(res, {
      data: result.rows,
      pagination: {
        limit,
        offset,
        total: parseInt(countResult.rows[0]?.total || 0)
      }
    });
  } catch (err) {
    console.error("Error fetching trade audit logs:", err);
    return sendError(res, "Failed to fetch trade audit logs", 500, err.message);
  }
});

// GET /api/audit/config - Config change audit log
router.get("/config", async (req, res) => {
  try {
    const limit = Math.min(parseInt(req.query.limit) || 100, 1000);
    const offset = parseInt(req.query.offset) || 0;

    const result = await query(
      "SELECT * FROM algo_config_audit ORDER BY changed_at DESC LIMIT $1 OFFSET $2",
      [limit, offset]
    );

    const countResult = await query("SELECT COUNT(*) as total FROM algo_config_audit");

    return sendSuccess(res, {
      data: result.rows,
      pagination: {
        limit,
        offset,
        total: parseInt(countResult.rows[0]?.total || 0)
      }
    });
  } catch (err) {
    console.error("Error fetching config audit logs:", err);
    return sendError(res, "Failed to fetch config audit logs", 500, err.message);
  }
});

// GET /api/audit/safeguards - Safeguard activation log
router.get("/safeguards", async (req, res) => {
  try {
    const limit = Math.min(parseInt(req.query.limit) || 100, 1000);
    const offset = parseInt(req.query.offset) || 0;
    const symbol = req.query.symbol ? req.query.symbol.toUpperCase() : null;

    let sql = "SELECT * FROM safeguard_audit_log";
    const params = [];

    if (symbol) {
      sql += " WHERE symbol = $1";
      params.push(symbol);
    }

    sql += " ORDER BY timestamp DESC LIMIT $" + (params.length + 1) + " OFFSET $" + (params.length + 2);
    params.push(limit, offset);

    const result = await query(sql, params);

    const countSql = symbol
      ? "SELECT COUNT(*) as total FROM safeguard_audit_log WHERE symbol = $1"
      : "SELECT COUNT(*) as total FROM safeguard_audit_log";

    const countResult = await query(
      countSql,
      symbol ? [symbol] : []
    );

    return sendSuccess(res, {
      data: result.rows,
      pagination: {
        limit,
        offset,
        total: parseInt(countResult.rows[0]?.total || 0)
      }
    });
  } catch (err) {
    console.error("Error fetching safeguard audit logs:", err);
    return sendError(res, "Failed to fetch safeguard audit logs", 500, err.message);
  }
});

// GET /api/audit/summary - Audit summary stats
router.get("/summary", async (req, res) => {
  try {
    const result = await query(`
      SELECT
        (SELECT COUNT(*) FROM algo_audit_log) as trade_actions,
        (SELECT COUNT(*) FROM algo_config_audit) as config_changes,
        (SELECT COUNT(*) FROM safeguard_audit_log) as safeguard_activations,
        (SELECT MAX(created_at) FROM algo_audit_log) as last_trade_action,
        (SELECT MAX(changed_at) FROM algo_config_audit) as last_config_change,
        (SELECT MAX(timestamp) FROM safeguard_audit_log) as last_safeguard
    `);

    return sendSuccess(res, result.rows[0]);
  } catch (err) {
    console.error("Error fetching audit summary:", err);
    return sendError(res, "Failed to fetch audit summary", 500, err.message);
  }
});

module.exports = router;
