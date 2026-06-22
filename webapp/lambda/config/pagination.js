/**
 * Pagination Configuration
 * Centralized limits to prevent DoS attacks and ensure consistency
 */

module.exports = {
  // Default limit when not specified
  DEFAULT_LIMIT: 50,

  // Maximum allowed limit (prevents resource exhaustion)
  MAX_LIMIT: 5000,

  // Limits for specific endpoint types
  LIMITS: {
    default: { default: 50, max: 5000 },
    audit: { default: 100, max: 10000 }, // audit logs can be large
    trades: { default: 100, max: 5000 },
    signals: { default: 50, max: 1000 },
    prices: { default: 100, max: 5000 },
    performance: { default: 30, max: 1000 },
    equity_curve: { default: 100, max: 1000 },
    rejection_funnel: { default: 50, max: 10000 }, // can be very large
    market: { default: 50, max: 1000 },
    economic: { default: 50, max: 500 },
    commodities: { default: 25, max: 500 },
  },

  /**
   * Sanitize and validate limit/offset parameters
   * @param {string|number} limit - User-provided limit
   * @param {string|number} offset - User-provided offset
   * @param {string} type - Endpoint type (for type-specific limits)
   * @returns {Object} {limit, offset} - Sanitized values
   */
  sanitize(limit, offset, type = "default") {
    const config = this.LIMITS[type] || this.LIMITS.default;

    // Parse and validate limit
    let limitNum = parseInt(limit) || config.default;
    limitNum = Math.max(1, Math.min(limitNum, config.max));

    // Parse and validate offset
    let offsetNum = Math.max(0, parseInt(offset) || 0);

    return { limit: limitNum, offset: offsetNum };
  },

  /**
   * Calculate page info from limit/offset
   * @param {number} total - Total number of records
   * @param {number} limit - Records per page
   * @param {number} offset - Offset
   * @returns {Object} Pagination metadata
   */
  getPaginationInfo(total, limit, offset) {
    const page = Math.floor(offset / limit) + 1;
    const totalPages = Math.ceil(total / limit);

    return {
      total,
      limit,
      offset,
      page,
      totalPages,
      hasNext: offset + limit < total,
      hasPrev: offset > 0,
    };
  },
};
