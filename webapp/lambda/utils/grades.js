const { getPool } = require("./database");
const logger = require("./logger");

// In-memory cache with expiration (5 minutes)
let gradesCache = null;
let gradesCacheExpiry = null;
const CACHE_TTL = 5 * 60 * 1000; // 5 minutes

/**
 * Fetch active swing score grades from database
 * Includes caching to reduce database queries
 */
async function getSwingGrades() {
  const now = Date.now();

  // Return cached grades if still valid
  if (gradesCache && gradesCacheExpiry && now < gradesCacheExpiry) {
    return gradesCache;
  }

  try {
    const pool = getPool();
    const result = await pool.query(`
      SELECT
        grade_id,
        grade_letter,
        min_score,
        max_score,
        description,
        pass_gates,
        fail_reason
      FROM swing_score_grades
      WHERE is_active = TRUE
      ORDER BY min_score DESC
    `);

    if (!result || !result.rows) {
      const error = new Error("Invalid swing grades query result structure - database may be unavailable");
      logger.error("Critical error in getSwingGrades", {
        error: error.message,
        hasResult: !!result,
        hasRows: !!result?.rows,
      });
      throw error;
    }

    const grades = result.rows.map((g) => ({
      grade_id: g.grade_id,
      letter: g.grade_letter,
      min_score: g.min_score,
      max_score: g.max_score,
      description: g.description,
      pass_gates: g.pass_gates,
      fail_reason: g.fail_reason,
    }));

    // Cache the result
    gradesCache = grades;
    gradesCacheExpiry = now + CACHE_TTL;

    return grades;
  } catch (error) {
    const gradesError = new Error(`Failed to load swing score grades (grading will be unsafe): ${error.message}`);
    gradesError.originalError = error;
    logger.error("CRITICAL: Swing score grades unavailable", {
      error: gradesError.message,
      originalError: error.message,
      stack: error.stack,
    });
    throw gradesError;
  }
}

/**
 * Assign a grade letter based on swing score
 * @param {number} score - The swing score value
 * @param {Array} grades - Array of grade definitions from database
 * @returns {Object} Grade information including letter, pass_gates, and fail_reason
 */
function getGradeForScore(score, grades) {
  if (!grades || grades.length === 0) {
    throw new Error(
      "CRITICAL: Grade configuration unavailable. " +
      "Cannot determine signal grades without grade tier definitions. " +
      "Verify signal_grade_tiers table is loaded and contains active grade definitions."
    );
  }

  // CRITICAL: Score is required for grading. 0 is a valid value, but missing is an error.
  if (score === null || score === undefined) {
    console.error("CRITICAL: Score missing. Cannot determine grade.");
    return {
      letter: "?",
      pass_gates: false,
      fail_reason: "Score unavailable",
    };
  }

  const scoreVal = parseFloat(score);
  if (isNaN(scoreVal)) {
    console.error(`CRITICAL: Score invalid (NaN). Value: ${score}`);
    return {
      letter: "?",
      pass_gates: false,
      fail_reason: "Score is invalid",
    };
  }

  // Find grade where: min_score <= score < max_score
  const gradeInfo = grades.find(
    (g) => scoreVal >= g.min_score && scoreVal < g.max_score
  );

  if (!gradeInfo) {
    const gradeRanges = grades
      .map(g => `${g.letter}=[${g.min_score},${g.max_score})`)
      .join(", ");
    throw new Error(
      `CRITICAL: Score ${scoreVal} falls outside all defined grade ranges. ` +
      `Valid ranges: ${gradeRanges}. ` +
      `Score is out of bounds and cannot be safely graded. ` +
      `Verify signal_quality_scores data integrity and grade tier definitions.`
    );
  }

  return {
    letter: gradeInfo.letter,
    pass_gates: gradeInfo.pass_gates,
    fail_reason: gradeInfo.fail_reason || null,
  };
}

/**
 * Clear the grade cache (useful for testing or after updates)
 */
function clearGradeCache() {
  gradesCache = null;
  gradesCacheExpiry = null;
}

module.exports = {
  getSwingGrades,
  getGradeForScore,
  clearGradeCache,
};
