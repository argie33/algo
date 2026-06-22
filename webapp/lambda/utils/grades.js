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
      logger.error("Invalid grade query result structure");
      return [];
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
    logger.error("Error fetching swing grades from database", {
      error: error.message,
      stack: error.stack,
    });
    return [];
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
    return {
      letter: "D",
      pass_gates: false,
      fail_reason: "Grade configuration unavailable",
    };
  }

  const scoreVal = parseFloat(score) || 0;

  // Find grade where: min_score <= score < max_score
  const gradeInfo = grades.find(
    (g) => scoreVal >= g.min_score && scoreVal < g.max_score
  );

  if (!gradeInfo) {
    // Fallback: return lowest grade if score is out of range
    const lowestGrade = grades.reduce((lowest, g) =>
      g.min_score < lowest.min_score ? g : lowest
    );
    return {
      letter: lowestGrade.letter,
      pass_gates: lowestGrade.pass_gates,
      fail_reason: lowestGrade.fail_reason,
    };
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
