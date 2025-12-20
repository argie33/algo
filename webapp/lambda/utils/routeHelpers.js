/**
 * Route helper utilities
 * Database utilities only - NO response formatters (see RULES.md for API response pattern)
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

module.exports = {
  tableExists,
};
