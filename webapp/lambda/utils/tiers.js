const { getPool } = require("./database");
const logger = require("./logger");

// In-memory cache with expiration (5 minutes)
let tiersCache = null;
let tiersCacheExpiry = null;
const CACHE_TTL = 5 * 60 * 1000; // 5 minutes

/**
 * Fetch active market exposure tiers from database
 * Includes caching to reduce database queries
 */
async function getActiveTiers() {
  const now = Date.now();

  // Return cached tiers if still valid
  if (tiersCache && tiersCacheExpiry && now < tiersCacheExpiry) {
    return tiersCache;
  }

  try {
    const pool = getPool();
    const result = await pool.query(`
      SELECT
        tier_id,
        tier_name as name,
        min_exposure_pct as min_pct,
        max_exposure_pct as max_pct,
        risk_multiplier,
        max_new_positions,
        min_swing_score,
        min_swing_grade,
        tighten_winners_at_r,
        force_partial_at_r,
        halt_new_entries,
        force_exit_negative_r,
        display_color as color,
        tier_description as description
      FROM market_exposure_tiers
      WHERE is_active = TRUE
      ORDER BY display_order ASC
    `);

    if (!result || !result.rows) {
      const error = new Error("Invalid tier query result structure - database may be unavailable");
      logger.error("Critical error in getActiveTiers", {
        error: error.message,
        hasResult: !!result,
        hasRows: !!result?.rows,
      });
      throw error;
    }

    // Normalize field names for backward compatibility
    const tiers = result.rows.map((tier) => ({
      tier_id: tier.tier_id,
      name: tier.name,
      min_pct: parseFloat(tier.min_pct),
      max_pct: parseFloat(tier.max_pct),
      min: parseFloat(tier.min_pct), // Legacy field name for /markets endpoint
      max: parseFloat(tier.max_pct), // Legacy field name for /markets endpoint
      risk_mult: parseFloat(tier.risk_multiplier), // Legacy field name
      risk_multiplier: parseFloat(tier.risk_multiplier),
      max_new: tier.max_new_positions, // Legacy field name
      max_new_positions: tier.max_new_positions,
      min_grade: tier.min_swing_grade, // Legacy field name
      min_swing_grade: tier.min_swing_grade,
      min_swing_score: tier.min_swing_score,
      tighten_winners_at_r: tier.tighten_winners_at_r,
      force_partial_at_r: tier.force_partial_at_r,
      halt: tier.halt_new_entries, // Legacy field name
      halt_new_entries: tier.halt_new_entries,
      force_exit_negative_r: tier.force_exit_negative_r,
      color: tier.color,
      description: tier.description,
    }));

    // Cache the result
    tiersCache = tiers;
    tiersCacheExpiry = now + CACHE_TTL;

    return tiers;
  } catch (error) {
    const tiersError = new Error(`Failed to load market exposure tiers (tier policy decisions will be unsafe): ${error.message}`);
    tiersError.originalError = error;
    logger.error("CRITICAL: Market exposure tiers unavailable", {
      error: tiersError.message,
      originalError: error.message,
      stack: error.stack,
    });
    throw tiersError;
  }
}

/**
 * Find the active tier based on exposure percentage
 * @param {number} exposurePct - Market exposure percentage (0-100)
 * @param {Array} tiers - Array of tier definitions
 * @returns {Object} The matching tier or first tier as fallback
 */
function getActiveTier(exposurePct, tiers) {
  if (!tiers || tiers.length === 0) {
    return null;
  }

  const exposure = parseFloat(exposurePct) || 0;

  // Find tier where: min <= exposure <= max
  // Use min_pct/max_pct fields (database field names)
  const activeTier = tiers.find((t) => {
    const minVal = t.min_pct !== undefined ? t.min_pct : t.min;
    const maxVal = t.max_pct !== undefined ? t.max_pct : t.max;
    return exposure >= minVal && exposure <= maxVal;
  });

  return activeTier || tiers[0];
}

/**
 * Clear the tier cache (useful for testing or after updates)
 */
function clearTierCache() {
  tiersCache = null;
  tiersCacheExpiry = null;
}

module.exports = {
  getActiveTiers,
  getActiveTier,
  clearTierCache,
};
