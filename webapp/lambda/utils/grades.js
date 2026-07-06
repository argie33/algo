const logger = require("./logger");

/**
 * SWING SCORE MIGRATION: Grades module deprecated
 * Signal quality scoring has been migrated from swing_trader_scores to composite_score.
 * The swing_score_grades table has been removed (migration 1003).
 * Signal quality is now determined by signal_quality_score from algo_signals table.
 */

/**
 * DEPRECATED: Swing score grades no longer exist.
 * This function stub remains for backward compatibility only.
 * Use signal_quality_score from algo_signals table instead.
 */
async function getSwingGrades() {
  throw new Error(
    "DEPRECATED: Swing score grades have been removed (migration 1003). " +
      "Use signal_quality_score from algo_signals table instead."
  );
}

/**
 * DEPRECATED: Swing score grading function.
 * Grade assignment was based on swing_trader_scores table which has been removed.
 * This function stub remains for backward compatibility only.
 */
function getGradeForScore(_score, _grades) {
  throw new Error(
    "DEPRECATED: Swing score grading has been removed (migration 1003). " +
      "Use signal_quality_score from algo_signals table instead."
  );
}

/**
 * DEPRECATED: Grade cache clearing no longer applicable.
 */
function clearGradeCache() {
  logger.warn("clearGradeCache called but swing_score_grades table has been removed");
}

module.exports = {
  getSwingGrades,
  getGradeForScore,
  clearGradeCache,
};
