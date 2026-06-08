/**
 * Audit Logs Endpoint
 * Provides access to audit trails for trades, config changes, and safeguard activations
 */

const express = require("express");
const { query } = require("../utils/database");
const { sendSuccess, sendError } = require('../utils/apiResponse');
const logger = require('../utils/logger');
const { authenticateToken, requireAdmin } = require('../middleware/auth');
const paginationConfig = require("../config/pagination");
const { validateQueryResult, validateAndCoerceRows, extractCount } = require('../utils/responseValidation');
const router = express.Router();

// Protect all audit endpoints with auth + admin role
router.use(authenticateToken, requireAdmin);

// GET /api/audit - Audit API root
router.get("/", (req, res) => {
  return sendSuccess(res, {
    message: "Audit API - available endpoints: /trades, /config-changes, /safeguard-activations"
  });
});

// GET /api/audit/trades - Trading audit log
router.get("/trades", async (req, res) => {
  try {
    const { limit, offset } = paginationConfig.sanitize(req.query.limit, req.query.offset, 'audit');
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

    // Validate result structure
    validateQueryResult(result, { requireRows: false });

    // Get total count
    let countSql = "SELECT COUNT(*) as total FROM algo_audit_log";
    if (symbol) {
      countSql += " WHERE symbol = $1";
    }

    const countResult = await query(
      countSql,
      symbol ? [symbol] : []
    );

    // Validate count result
    validateQueryResult(countResult, { minRows: 1, maxRows: 1 });
    const total = extractCount(countResult, 'total');

    // Validate and coerce row types
    const validated = validateAndCoerceRows(result, {
      id: { type: 'int', required: true },
      action_type: { type: 'string', required: true },
      symbol: { type: 'string', required: false },
      action_date: { type: 'date', required: false },
      details: { type: 'string', required: false },
      actor: { type: 'string', required: false },
      status: { type: 'string', required: false },
      error_message: { type: 'string', required: false },
      created_at: { type: 'date', required: false }
    });

    return sendSuccess(res, {
      items: validated,
      pagination: {
        limit,
        offset,
        total
      }
    });
  } catch (err) {
    logger.error("Error fetching trade audit logs:", { error: err.message });
    return sendError(res, "Failed to fetch trade audit logs", 500, err.message);
  }
});

// GET /api/audit/config - Config change audit log
router.get("/config", async (req, res) => {
  try {
    const { limit, offset } = paginationConfig.sanitize(req.query.limit, req.query.offset, 'audit');

    const result = await query(
      "SELECT * FROM algo_config_audit ORDER BY changed_at DESC LIMIT $1 OFFSET $2",
      [limit, offset]
    );

    // Validate result structure
    validateQueryResult(result, { requireRows: false });

    const countResult = await query("SELECT COUNT(*) as total FROM algo_config_audit");

    // Validate count result
    validateQueryResult(countResult, { minRows: 1, maxRows: 1 });
    const total = extractCount(countResult, 'total');

    // Validate and coerce row types
    const validated = validateAndCoerceRows(result, {
      id: { type: 'int', required: true },
      key: { type: 'string', required: true },
      old_value: { type: 'string', required: false },
      new_value: { type: 'string', required: false },
      changed_by: { type: 'string', required: false },
      changed_at: { type: 'date', required: false },
      reason: { type: 'string', required: false }
    });

    return sendSuccess(res, {
      items: validated,
      pagination: {
        limit,
        offset,
        total
      }
    });
  } catch (err) {
    logger.error("Error fetching config audit logs:", { error: err.message });
    return sendError(res, "Failed to fetch config audit logs", 500, err.message);
  }
});

// GET /api/audit/safeguards - Safeguard activation log
router.get("/safeguards", async (req, res) => {
  try {
    const { limit, offset } = paginationConfig.sanitize(req.query.limit, req.query.offset, 'audit');
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

    // Validate result structure
    validateQueryResult(result, { requireRows: false });

    const countSql = symbol
      ? "SELECT COUNT(*) as total FROM safeguard_audit_log WHERE symbol = $1"
      : "SELECT COUNT(*) as total FROM safeguard_audit_log";

    const countResult = await query(
      countSql,
      symbol ? [symbol] : []
    );

    // Validate count result
    validateQueryResult(countResult, { minRows: 1, maxRows: 1 });
    const total = extractCount(countResult, 'total');

    // Validate and coerce row types
    const validated = validateAndCoerceRows(result, {
      id: { type: 'int', required: true },
      safeguard_name: { type: 'string', required: true },
      symbol: { type: 'string', required: false },
      triggered: { type: 'bool', required: true },
      reason: { type: 'string', required: false },
      impact: { type: 'string', required: false },
      timestamp: { type: 'date', required: true }
    });

    return sendSuccess(res, {
      items: validated,
      pagination: {
        limit,
        offset,
        total
      }
    });
  } catch (err) {
    logger.error("Error fetching safeguard audit logs:", { error: err.message });
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

    // Validate result structure
    validateQueryResult(result, { minRows: 1, maxRows: 1 });

    // Validate and coerce row types
    const validated = validateAndCoerceRows(result, {
      trade_actions: { type: 'int', required: false, defaultValue: 0 },
      config_changes: { type: 'int', required: false, defaultValue: 0 },
      safeguard_activations: { type: 'int', required: false, defaultValue: 0 },
      last_trade_action: { type: 'date', required: false },
      last_config_change: { type: 'date', required: false },
      last_safeguard: { type: 'date', required: false }
    });

    return sendSuccess(res, validated[0]);
  } catch (err) {
    logger.error("Error fetching audit summary:", { error: err.message });
    return sendError(res, "Failed to fetch audit summary", 500, err.message);
  }
});

module.exports = router;
