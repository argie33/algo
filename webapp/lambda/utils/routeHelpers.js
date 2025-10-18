/**
 * Consolidated route helper functions
 * Eliminates duplication across route files
 */

const { query } = require("./database");

/**
 * Check if a table exists in the database
 * Used by: stocks, market, portfolio, alerts, price, trading, earnings, screener, etc.
 */
async function tableExists(tableName) {
  try {
    const tableCheckQuery = `
      SELECT EXISTS (
        SELECT FROM information_schema.tables
        WHERE table_name = $1
      );
    `;
    const result = await query(tableCheckQuery, [tableName]);
    if (!result || !result.rows || result.rows.length === 0) {
      console.warn('Query returned invalid result:', result);
      return null;
    }
    return result.rows[0].exists;
  } catch (error) {
    console.warn(`Error checking table existence for ${tableName}:`, error);
    return false;
  }
}

/**
 * Consistent error response for missing tables
 */
function tableNotFoundResponse(tableName) {
  return {
    success: true,
    data: [],
    message: `${tableName} data not yet loaded`,
    total: 0,
    timestamp: new Date().toISOString(),
  };
}

/**
 * Consistent error response for empty results
 */
function emptyResultResponse(message = "No data available") {
  return {
    success: true,
    data: [],
    message,
    total: 0,
  };
}

module.exports = {
  tableExists,
  tableNotFoundResponse,
  emptyResultResponse,
};
