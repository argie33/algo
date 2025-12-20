/**
 * Data safety helpers - reusable across mocks and production
 * Ensures consistent handling of null/undefined/invalid values
 */

/**
 * Safe float conversion - returns null if value is null/undefined, otherwise parses
 * @param {any} value - The value to parse
 * @returns {number|null} - Parsed float or null
 */
function safeFloat(value) {
  if (value === null || value === undefined) {
    return null;
  }
  const parsed = parseFloat(value);
  return isNaN(parsed) ? null : parsed;
}

/**
 * Safe integer conversion - returns null if value is null/undefined, otherwise parses
 * @param {any} value - The value to parse
 * @returns {number|null} - Parsed integer or null
 */
function safeInt(value) {
  if (value === null || value === undefined) {
    return null;
  }
  const parsed = parseInt(value);
  return isNaN(parsed) ? null : parsed;
}

/**
 * Safe fixed decimal - returns null if value is null/undefined, otherwise formats
 * @param {any} value - The value to format
 * @param {number} decimals - Number of decimal places
 * @returns {string|null} - Formatted decimal or null
 */
function safeFixed(value, decimals = 2) {
  const num = safeFloat(value);
  return num === null ? null : num.toFixed(decimals);
}

module.exports = {
  safeFloat,
  safeInt,
  safeFixed,
};
