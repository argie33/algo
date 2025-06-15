const express = require('express');
const router = express.Router();
const pool = require('../utils/database');

// Get financial statements for a ticker
router.get('/:ticker/balance-sheet', async (req, res) => {
  try {
    const { ticker } = req.params;
    const { period = 'annual' } = req.query; // annual, quarterly
    
    const tableName = period === 'quarterly' ? 'quarterly_balance_sheet' : 'balance_sheet';
    
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
    
    // Group by date for better frontend handling
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
    const { period = 'annual' } = req.query; // annual, quarterly, ttm
    
    let tableName = 'income_stmt';
    if (period === 'quarterly') tableName = 'quarterly_income_stmt';
    if (period === 'ttm') tableName = 'ttm_income_stmt';
    
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
    
    // Group by date for better frontend handling
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
    console.error('Income statement fetch error:', error);
    res.status(500).json({
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
