const express = require('express');
const { query } = require('../utils/database');

const router = express.Router();

// Debug endpoint to check table structure
router.get('/debug/tables', async (req, res) => {
  try {
    console.log('Financials debug endpoint called');
    
    const tables = ['balance_sheet', 'ttm_income_stmt', 'ttm_cashflow', 'quarterly_balance_sheet', 'quarterly_income_stmt', 'quarterly_cashflow'];
    const results = {};
    
    for (const table of tables) {
      try {
        // Check if table exists
        const tableExistsQuery = `
          SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = '${table}'
          );
        `;
        
        const tableExists = await query(tableExistsQuery);
        
        if (tableExists.rows[0].exists) {
          // Get column information
          const columnsQuery = `
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns 
            WHERE table_name = '${table}' 
            AND table_schema = 'public'
            ORDER BY ordinal_position
          `;
          
          const columnsResult = await query(columnsQuery);
          
          // Count total records
          const countQuery = `SELECT COUNT(*) as total FROM ${table}`;
          const countResult = await query(countQuery);
          
          // Get sample records (first 2 rows)
          const sampleQuery = `SELECT * FROM ${table} LIMIT 2`;
          const sampleResult = await query(sampleQuery);
          
          results[table] = {
            exists: true,
            totalRecords: parseInt(countResult.rows[0].total),
            columns: columnsResult.rows,
            sampleData: sampleResult.rows
          };
        } else {
          results[table] = {
            exists: false,
            message: `${table} table does not exist`
          };
        }
        
      } catch (error) {
        results[table] = {
          exists: false,
          error: error.message
        };
      }
    }
    
    res.json({
      status: 'ok',
      tables: results,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Error in financials debug:', error);
    res.status(500).json({ 
      error: 'Debug check failed', 
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Get financial statements for a ticker
router.get('/:ticker/balance-sheet', async (req, res) => {
  try {
    const { ticker } = req.params;
    const { period = 'annual' } = req.query;
    
    console.log(`Balance sheet request for ${ticker}, period: ${period}`);
      // Query the balance_sheet table with all key metrics
    const balanceSheetQuery = `
      SELECT 
        ticker,
        period_end,
        total_assets,
        total_liabilities_net_minority_interest as total_liabilities,
        stockholders_equity,
        cash_and_cash_equivalents,
        current_assets,
        current_liabilities,
        long_term_debt,
        working_capital,
        retained_earnings,
        common_stock_equity,
        tangible_book_value,
        net_debt,
        invested_capital
      FROM balance_sheet
      WHERE UPPER(ticker) = UPPER($1)
      ORDER BY period_end DESC
      LIMIT 10
    `;
    
    const result = await query(balanceSheetQuery, [ticker.toUpperCase()]);
      // Transform data to match frontend expectations (same structure as income statement)
    const transformedData = result.rows.map(row => ({
      symbol: row.ticker,
      date: row.period_end,
      items: {
        'Total Assets': parseFloat(row.total_assets || 0),
        'Total Liabilities': parseFloat(row.total_liabilities || 0),
        'Stockholders Equity': parseFloat(row.stockholders_equity || 0),
        'Cash and Cash Equivalents': parseFloat(row.cash_and_cash_equivalents || 0),
        'Current Assets': parseFloat(row.current_assets || 0),
        'Current Liabilities': parseFloat(row.current_liabilities || 0),
        'Long Term Debt': parseFloat(row.long_term_debt || 0),
        'Working Capital': parseFloat(row.working_capital || 0),
        'Retained Earnings': parseFloat(row.retained_earnings || 0),
        'Common Stock Equity': parseFloat(row.common_stock_equity || 0),
        'Tangible Book Value': parseFloat(row.tangible_book_value || 0),
        'Net Debt': parseFloat(row.net_debt || 0),
        'Invested Capital': parseFloat(row.invested_capital || 0)
      }
    }));
    
    res.json({
      success: true,
      data: transformedData,
      metadata: {
        ticker: ticker.toUpperCase(),
        period,
        count: transformedData.length,
        timestamp: new Date().toISOString()
      }
    });
    
  } catch (error) {
    console.error('Balance sheet fetch error:', error.message);
    console.error('Stack:', error.stack);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch balance sheet data',
      message: error.message,
      details: 'Check if balance_sheet table exists and contains data for this ticker'
    });
  }
});

// Get income statement for a ticker
router.get('/:ticker/income-statement', async (req, res) => {
  try {
    const { ticker } = req.params;
    const { period = 'ttm' } = req.query;
    
    console.log(`Income statement request for ${ticker}, period: ${period}`);
    
    // Query the normalized ttm_income_stmt table
    const incomeQuery = `
      SELECT 
        symbol,
        date,
        item_name,
        value
      FROM ttm_income_stmt
      WHERE UPPER(symbol) = UPPER($1)
      ORDER BY date DESC, item_name
      LIMIT 200
    `;
    
    const result = await query(incomeQuery, [ticker.toUpperCase()]);
    
    // Transform the normalized data into a structured format
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
      groupedData[dateKey].items[row.item_name] = parseFloat(row.value || 0);
    });
    
    // Convert to array and add common financial metrics
    const transformedData = Object.values(groupedData).map(period => ({
      symbol: period.symbol,
      date: period.date,
      revenue: period.items['Total Revenue'] || period.items['Revenue'] || 0,
      costOfRevenue: period.items['Cost Of Revenue'] || 0,
      grossProfit: period.items['Gross Profit'] || 0,
      operatingIncome: period.items['Operating Income'] || 0,
      netIncome: period.items['Net Income'] || 0,
      ebit: period.items['EBIT'] || 0,
      items: period.items // Include all raw items for debugging
    }));
      res.json({
      success: true,
      data: transformedData,
      metadata: {
        ticker: ticker.toUpperCase(),
        period: 'ttm',
        count: transformedData.length,
        timestamp: new Date().toISOString()
      }
    });
    
  } catch (error) {
    console.error('Income statement fetch error:', error.message);
    console.error('Stack:', error.stack);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch income statement data',
      message: error.message,
      details: 'Check if ttm_income_stmt table exists and contains data for this ticker'
    });
  }
});

// Get cash flow statement for a ticker
router.get('/:ticker/cash-flow', async (req, res) => {
  try {
    const { ticker } = req.params;
    const { period = 'ttm' } = req.query; // Only ttm is available
    
    console.log(`Cash flow request for ${ticker}, period: ${period}`);
    
    // Query the normalized ttm_cashflow table
    const cashFlowQuery = `
      SELECT 
        symbol,
        date,
        item_name,
        value
      FROM ttm_cashflow
      WHERE UPPER(symbol) = UPPER($1)
      ORDER BY date DESC, item_name
      LIMIT 200
    `;
    
    const result = await query(cashFlowQuery, [ticker.toUpperCase()]);
    
    // Transform the normalized data into a structured format
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
      groupedData[dateKey].items[row.item_name] = parseFloat(row.value || 0);
    });
    
    // Convert to array and add common cash flow metrics
    const transformedData = Object.values(groupedData).map(period => ({
      symbol: period.symbol,
      date: period.date,
      operatingCashFlow: period.items['Operating Cash Flow'] || period.items['Cash Flow From Operating Activities'] || 0,
      investingCashFlow: period.items['Investing Cash Flow'] || period.items['Cash Flow From Investing Activities'] || 0,
      financingCashFlow: period.items['Financing Cash Flow'] || period.items['Cash Flow From Financing Activities'] || 0,
      freeCashFlow: period.items['Free Cash Flow'] || 0,
      capitalExpenditures: period.items['Capital Expenditures'] || 0,
      items: period.items // Include all raw items for debugging
    }));
      res.json({
      success: true,
      data: transformedData,
      metadata: {
        ticker: ticker.toUpperCase(),
        period: 'ttm',
        count: transformedData.length,
        timestamp: new Date().toISOString()
      }
    });
    
  } catch (error) {
    console.error('Cash flow fetch error:', error.message);
    console.error('Stack:', error.stack);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch cash flow data',
      message: error.message,
      details: 'Check if ttm_cashflow table exists and contains data for this ticker'
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
