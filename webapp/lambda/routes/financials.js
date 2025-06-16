const express = require('express');
const router = express.Router();
const pool = require('../utils/database');

// Debug endpoint to check financial table status
router.get('/debug', async (req, res) => {
  try {
    console.log('Financial debug endpoint called');
    
    const tables = ['balance_sheet', 'income_stmt', 'cash_flow', 'ttm_income_stmt'];
    const tableInfo = {};
    
    for (const tableName of tables) {
      try {
        // Check if table exists
        const tableExistsQuery = `
          SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = $1
          );
        `;
        const tableExists = await pool.query(tableExistsQuery, [tableName]);
        
        if (tableExists.rows[0].exists) {
          // Get table structure
          const structureQuery = `
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = $1 
            ORDER BY ordinal_position;
          `;
          const structure = await pool.query(structureQuery, [tableName]);
          
          // Count records
          const countQuery = `SELECT COUNT(*) as total FROM ${tableName}`;
          const countResult = await pool.query(countQuery);
          
          // Get sample data
          const sampleQuery = `SELECT * FROM ${tableName} LIMIT 3`;
          const sampleResult = await pool.query(sampleQuery);
          
          tableInfo[tableName] = {
            exists: true,
            structure: structure.rows,
            totalRecords: parseInt(countResult.rows[0].total),
            sampleData: sampleResult.rows
          };
        } else {
          tableInfo[tableName] = { exists: false };
        }
      } catch (error) {
        tableInfo[tableName] = { exists: false, error: error.message };
      }
    }
    
    res.json({
      tables: tableInfo,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Financial debug error:', error);
    res.status(500).json({
      error: 'Failed to debug financial tables',
      message: error.message
    });
  }
});

// Get financial statements for a ticker
router.get('/:ticker/balance-sheet', async (req, res) => {
  try {
    const { ticker } = req.params;
    const { period = 'annual' } = req.query; // annual, quarterly
    
    // First try to get data from balance_sheet table
    let query = `
      SELECT *
      FROM balance_sheet
      WHERE UPPER(ticker) = UPPER($1)
      ORDER BY period_end DESC
      LIMIT 20
    `;
    
    let result;
    try {
      result = await pool.query(query, [ticker.toUpperCase()]);
      console.log(`Balance sheet query result for ${ticker}:`, result.rows.length, 'rows');
    } catch (error) {
      console.log('Balance sheet table query failed, trying alternative approach:', error.message);
      
      // Fallback: if balance_sheet table doesn't exist or has no data, return empty result
      result = { rows: [] };
    }
    
    res.json({
      success: true,
      data: result.rows,
      metadata: {
        ticker: ticker.toUpperCase(),
        period,
        count: result.rows.length,
        timestamp: new Date().toISOString()
      }
    });
    
  } catch (error) {
    console.error('Balance sheet fetch error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch balance sheet data',
      message: error.message
    });
  }
});

// Get income statement for a ticker
router.get('/:ticker/income-statement', async (req, res) => {
  try {
    const { ticker } = req.params;
    const { period = 'ttm' } = req.query;
    
    // Query the normalized ttm_income_stmt table
    const query = `
      SELECT 
        symbol,
        date,
        item_name,
        value
      FROM ttm_income_stmt
      WHERE UPPER(symbol) = UPPER($1)
      ORDER BY date DESC, item_name ASC
      LIMIT 500
    `;
    
    const result = await pool.query(query, [ticker.toUpperCase()]);
    
    // Transform the normalized data into grouped format
    const groupedData = {};
    result.rows.forEach(row => {
      const dateKey = row.date;
      if (!groupedData[dateKey]) {
        groupedData[dateKey] = {
          symbol: row.symbol,
          date: row.date,
          items: {}
        };
      }
      groupedData[dateKey].items[row.item_name] = row.value;
    });
    
    // Convert to array format
    const data = Object.values(groupedData);
    
    res.json({
      success: true,
      data: data,
      metadata: {
        ticker: ticker.toUpperCase(),
        period,
        count: data.length,
        timestamp: new Date().toISOString()
      }
    });
    
  } catch (error) {
    console.error('Income statement fetch error:', error);    res.status(500).json({
      success: false,
      error: 'Failed to fetch income statement data',
      message: error.message
    });
  }
});

// Get cash flow statement for a ticker
router.get('/:ticker/cash-flow', async (req, res) => {
  try {
    const { ticker } = req.params;
    const { period = 'annual' } = req.query; // annual, quarterly, ttm
      let tableName = 'cash_flow';
    if (period === 'quarterly') tableName = 'quarterly_cashflow';
    if (period === 'ttm') tableName = 'ttm_cashflow';
    
    const query = `
      SELECT 
        symbol,
        date,
        item_name,
        value,
        fetched_at
      FROM ${tableName}
      WHERE UPPER(symbol) = UPPER($1)
      ORDER BY date DESC, item_name
    `;
    
    const result = await pool.query(query, [ticker]);
      // Group by date for better frontend handling
    const groupedData = {};
    result.rows.forEach(row => {
      const dateKey = row.date.toISOString().split('T')[0];
      if (!groupedData[dateKey]) {
        groupedData[dateKey] = {
          symbol: row.symbol,
          date: dateKey,
          items: {},
          fetched_at: row.fetched_at
        };
      }
      groupedData[dateKey].items[row.item_name] = row.value;
    });
    
    const statements = Object.values(groupedData).sort((a, b) => new Date(b.date) - new Date(a.date));
    
    res.json({
      success: true,
      data: statements,
      metadata: {
        ticker: ticker.toUpperCase(),
        period,
        count: statements.length,
        timestamp: new Date().toISOString()
      }
    });
    
  } catch (error) {
    console.error('Cash flow fetch error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch cash flow data',
      message: error.message
    });
  }
});

// Get all financial statements for a ticker (combined)
router.get('/:ticker/financials', async (req, res) => {
  try {
    const { ticker } = req.params;
    const { period = 'annual' } = req.query;
    
    // Get all three statements in parallel
    const [balanceSheet, incomeStatement, cashFlow] = await Promise.all([
      getFinancialStatement(ticker, 'balance_sheet', period),
      getFinancialStatement(ticker, 'income_stmt', period),
      getFinancialStatement(ticker, 'cash_flow', period)
    ]);
    
    res.json({
      success: true,
      data: {
        balance_sheet: balanceSheet,
        income_statement: incomeStatement,
        cash_flow: cashFlow
      },
      metadata: {
        ticker: ticker.toUpperCase(),
        period,
        timestamp: new Date().toISOString()
      }
    });
    
  } catch (error) {
    console.error('Financial statements fetch error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch financial statements',
      message: error.message
    });
  }
});

// Helper function to get financial statement data
async function getFinancialStatement(ticker, type, period) {
  let tableName = type;
  if (period === 'quarterly' && type !== 'balance_sheet') {
    tableName = `quarterly_${type}`;
  } else if (period === 'ttm' && type !== 'balance_sheet') {
    tableName = `ttm_${type}`;
  } else if (period === 'quarterly' && type === 'balance_sheet') {
    tableName = 'quarterly_balance_sheet';
  }
  
  const query = `
    SELECT 
      date,
      item_name,
      value,
      fetched_at
    FROM ${tableName}
    WHERE UPPER(symbol) = UPPER($1)
    ORDER BY date DESC, item_name
  `;
  
  const result = await pool.query(query, [ticker]);
  
  // Group by date
  const groupedData = {};
  result.rows.forEach(row => {
    const dateKey = row.date.toISOString().split('T')[0];
    if (!groupedData[dateKey]) {
      groupedData[dateKey] = {
        date: dateKey,
        items: {},
        fetched_at: row.fetched_at
      };
    }
    groupedData[dateKey].items[row.item_name] = row.value;
  });
  
  return Object.values(groupedData).sort((a, b) => new Date(b.date) - new Date(a.date));
}

// Health check
router.get('/ping', (req, res) => {
  res.json({ success: true, service: 'financials', timestamp: new Date().toISOString() });
});

module.exports = router;
