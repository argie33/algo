const express = require('express');
const { query } = require('../utils/database');

const router = express.Router();

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
    
    // Transform data to match frontend expectations
    const transformedData = result.rows.map(row => ({
      symbol: row.ticker,
      date: row.period_end,
      totalAssets: parseFloat(row.total_assets || 0),
      totalLiabilities: parseFloat(row.total_liabilities || 0),
      stockholdersEquity: parseFloat(row.stockholders_equity || 0),
      cash: parseFloat(row.cash_and_cash_equivalents || 0),
      currentAssets: parseFloat(row.current_assets || 0),
      currentLiabilities: parseFloat(row.current_liabilities || 0),
      longTermDebt: parseFloat(row.long_term_debt || 0),
      workingCapital: parseFloat(row.working_capital || 0),
      retainedEarnings: parseFloat(row.retained_earnings || 0),
      commonStockEquity: parseFloat(row.common_stock_equity || 0),
      tangibleBookValue: parseFloat(row.tangible_book_value || 0),
      netDebt: parseFloat(row.net_debt || 0),
      investedCapital: parseFloat(row.invested_capital || 0)
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
    const { period = 'ttm' } = req.query; // Force ttm since it's the only available table
    
    console.log(`Income statement request for ${ticker}, period: ${period}`);
    
    // Only ttm_income_stmt table is available
    const incomeQuery = `
      SELECT 
        symbol,
        period_ending,
        revenue,
        cost_of_revenue,
        gross_profit,
        research_development,
        selling_general_administrative,
        total_operating_expenses,
        operating_income,
        total_other_income_expense_net,
        ebit,
        interest_expense,
        income_before_tax,
        income_tax_expense,
        net_income
      FROM ttm_income_stmt
      WHERE UPPER(symbol) = UPPER($1)
      ORDER BY period_ending DESC
      LIMIT 10
    `;
    
    const result = await query(incomeQuery, [ticker.toUpperCase()]);
    
    // Transform data to match frontend expectations
    const transformedData = result.rows.map(row => ({
      symbol: row.symbol,
      date: row.period_ending,
      revenue: parseFloat(row.revenue || 0),
      costOfRevenue: parseFloat(row.cost_of_revenue || 0),
      grossProfit: parseFloat(row.gross_profit || 0),
      researchDevelopment: parseFloat(row.research_development || 0),
      sellingGeneralAdmin: parseFloat(row.selling_general_administrative || 0),
      totalOperatingExpenses: parseFloat(row.total_operating_expenses || 0),
      operatingIncome: parseFloat(row.operating_income || 0),
      otherIncomeExpense: parseFloat(row.total_other_income_expense_net || 0),
      ebit: parseFloat(row.ebit || 0),
      interestExpense: parseFloat(row.interest_expense || 0),
      incomeBeforeTax: parseFloat(row.income_before_tax || 0),
      incomeTaxExpense: parseFloat(row.income_tax_expense || 0),
      netIncome: parseFloat(row.net_income || 0)
    }));
    
    res.json({
      success: true,
      data: transformedData,
      metadata: {
        ticker: ticker.toUpperCase(),
        period: 'ttm',
        count: result.rows.length,
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
