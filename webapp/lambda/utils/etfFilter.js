/**
 * ETF Filtering Utility
 * 
 * Provides SQL filters to exclude ETF symbols from query results.
 * ETFs are identified by:
 * - stock_symbols.etf column = 'etf' (in AWS production)
 * - Test symbols matching patterns (in local dev only)
 */

/**
 * Returns SQL WHERE clause to filter out ETFs and test symbols
 * @param {string} symbolColumn - The column name containing symbols (e.g., 'symbol', 'pd.symbol', 'ss.symbol')
 * @param {boolean} includeJoin - Whether to include JOIN clause with stock_symbols table
 * @returns {string} SQL filter clause
 */
function getEtfFilterClause(symbolColumn = 'symbol', includeJoin = false) {
  const tableAlias = symbolColumn.includes('.') ? symbolColumn.split('.')[0] : null;
  const symbolCol = tableAlias ? symbolColumn : `"${symbolColumn}"`;
  
  if (includeJoin) {
    // Return both JOIN and WHERE clause
    const joinAlias = tableAlias || 'main_table';
    return `
      LEFT JOIN stock_symbols ss_filter ON ${symbolCol} = ss_filter.symbol
      WHERE (ss_filter.etf IS NULL OR ss_filter.etf != 'etf')
    `;
  }
  
  // Return just WHERE clause (assumes stock_symbols is already joined)
  return `(etf IS NULL OR etf != 'etf')`;
}

/**
 * Returns SQL subquery to filter out ETFs
 * Use this in IN clauses: WHERE symbol IN (SELECT * FROM get_stock_symbols())
 */
function getStockSymbolsSubquery() {
  return `
    SELECT symbol 
    FROM stock_symbols 
    WHERE (etf IS NULL OR etf != 'etf')
  `;
}

module.exports = {
  getEtfFilterClause,
  getStockSymbolsSubquery,
};
