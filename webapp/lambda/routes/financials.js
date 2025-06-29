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
    
    // Determine table name based on period
    let tableName = 'annual_balance_sheet';
    if (period === 'quarterly') {
      tableName = 'quarterly_balance_sheet';
    }
    
    // Query the normalized balance sheet table
    const balanceSheetQuery = `
      SELECT 
        symbol,
        date,
        item_name,
        value
      FROM ${tableName}
      WHERE UPPER(symbol) = UPPER($1)
      ORDER BY date DESC, item_name
      LIMIT 200
    `;
    
    const result = await query(balanceSheetQuery, [ticker.toUpperCase()]);
    
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
    
    // Convert to array and add common balance sheet metrics
    const transformedData = Object.values(groupedData).map(period => ({
      symbol: period.symbol,
      date: period.date,
      totalAssets: period.items['Total Assets'] || 0,
      totalLiabilities: period.items['Total Liabilities Net Minority Interest'] || 0,
      stockholdersEquity: period.items['Total Equity Gross Minority Interest'] || 0,
      cashAndCashEquivalents: period.items['Cash And Cash Equivalents'] || 0,
      currentAssets: period.items['Total Current Assets'] || 0,
      currentLiabilities: period.items['Total Current Liabilities'] || 0,
      longTermDebt: period.items['Long Term Debt'] || 0,
      workingCapital: period.items['Working Capital'] || 0,
      retainedEarnings: period.items['Retained Earnings'] || 0,
      commonStockEquity: period.items['Common Stock'] || 0,
      tangibleBookValue: period.items['Tangible Book Value'] || 0,
      netDebt: period.items['Net Debt'] || 0,
      investedCapital: period.items['Invested Capital'] || 0,
      items: period.items // Include all raw items for debugging
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
      details: 'Check if balance sheet table exists and contains data for this ticker'
    });
  }
});

// Get income statement for a ticker
router.get('/:ticker/income-statement', async (req, res) => {
  try {
    const { ticker } = req.params;
    const { period = 'annual' } = req.query;
    
    console.log(`Income statement request for ${ticker}, period: ${period}`);
    
    // Determine table name based on period
    let tableName = 'annual_income_statement';
    if (period === 'quarterly') {
      tableName = 'quarterly_income_statement';
    } else if (period === 'ttm') {
      tableName = 'ttm_income_stmt';
    }
    
    // Query the normalized income statement table
    const incomeQuery = `
      SELECT 
        symbol,
        date,
        item_name,
        value
      FROM ${tableName}
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
      ebitda: period.items['EBITDA'] || 0,
      items: period.items // Include all raw items for debugging
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
    console.error('Income statement fetch error:', error.message);
    console.error('Stack:', error.stack);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch income statement data',
      message: error.message,
      details: 'Check if income statement table exists and contains data for this ticker'
    });
  }
});

// Get cash flow statement for a ticker
router.get('/:ticker/cash-flow', async (req, res) => {
  try {
    const { ticker } = req.params;
    const { period = 'annual' } = req.query;
    
    console.log(`Cash flow request for ${ticker}, period: ${period}`);
    
    // Determine table name based on period
    let tableName = 'annual_cash_flow';
    if (period === 'quarterly') {
      tableName = 'quarterly_cash_flow';
    } else if (period === 'ttm') {
      tableName = 'ttm_cashflow';
    }
    
    // Query the normalized cash flow table
    const cashFlowQuery = `
      SELECT 
        symbol,
        date,
        item_name,
        value
      FROM ${tableName}
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
      capitalExpenditures: period.items['Capital Expenditure'] || period.items['Capital Expenditures'] || 0,
      netIncome: period.items['Net Income'] || 0,
      items: period.items // Include all raw items for debugging
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
    console.error('Cash flow fetch error:', error.message);
    console.error('Stack:', error.stack);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch cash flow data',
      message: error.message,
      details: 'Check if cash flow table exists and contains data for this ticker'
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

// Get key metrics for a ticker (comprehensive financial ratios and metrics)
router.get('/:ticker/key-metrics', async (req, res) => {
  try {
    const { ticker } = req.params;
    
    console.log(`Key metrics request for ${ticker}`);
    
    // Query the key_metrics table from loadinfo
    const keyMetricsQuery = `
      SELECT 
        ticker,
        -- Valuation ratios
        trailing_pe,
        forward_pe,
        price_to_sales_ttm,
        price_to_book,
        book_value,
        peg_ratio,
        
        -- Enterprise metrics
        enterprise_value,
        ev_to_revenue,
        ev_to_ebitda,
        
        -- Financial results
        total_revenue,
        net_income,
        ebitda,
        gross_profit,
        
        -- Earnings per share
        eps_trailing,
        eps_forward,
        eps_current_year,
        price_eps_current_year,
        
        -- Growth metrics
        earnings_q_growth_pct,
        revenue_growth_pct,
        earnings_growth_pct,
        
        -- Cash & debt
        total_cash,
        cash_per_share,
        operating_cashflow,
        free_cashflow,
        total_debt,
        debt_to_equity,
        
        -- Liquidity ratios
        quick_ratio,
        current_ratio,
        
        -- Profitability margins
        profit_margin_pct,
        gross_margin_pct,
        ebitda_margin_pct,
        operating_margin_pct,
        
        -- Return metrics
        return_on_assets_pct,
        return_on_equity_pct,
        
        -- Dividend information
        dividend_rate,
        dividend_yield,
        five_year_avg_dividend_yield,
        payout_ratio
        
      FROM key_metrics
      WHERE UPPER(ticker) = UPPER($1)
    `;
    
    const result = await query(keyMetricsQuery, [ticker.toUpperCase()]);
    
    if (result.rows.length === 0) {
      return res.json({
        success: false,
        error: 'No key metrics data found',
        data: null,
        metadata: {
          ticker: ticker.toUpperCase(),
          message: 'Key metrics data not available for this ticker'
        }
      });
    }
    
    const metrics = result.rows[0];
    
    // Organize metrics into logical categories for better presentation
    const organizedMetrics = {
      valuation: {
        title: 'Valuation Ratios',
        icon: 'TrendingUp',
        metrics: {
          'P/E Ratio (Trailing)': metrics.trailing_pe,
          'P/E Ratio (Forward)': metrics.forward_pe,
          'Price/Sales (TTM)': metrics.price_to_sales_ttm,
          'Price/Book': metrics.price_to_book,
          'PEG Ratio': metrics.peg_ratio,
          'Book Value': metrics.book_value
        }
      },
      
      enterprise: {
        title: 'Enterprise Metrics',
        icon: 'BusinessCenter',
        metrics: {
          'Enterprise Value': metrics.enterprise_value,
          'EV/Revenue': metrics.ev_to_revenue,
          'EV/EBITDA': metrics.ev_to_ebitda
        }
      },
      
      financial_performance: {
        title: 'Financial Performance',
        icon: 'Assessment',
        metrics: {
          'Total Revenue': metrics.total_revenue,
          'Net Income': metrics.net_income,
          'EBITDA': metrics.ebitda,
          'Gross Profit': metrics.gross_profit
        }
      },
      
      earnings: {
        title: 'Earnings Per Share',
        icon: 'MonetizationOn',
        metrics: {
          'EPS (Trailing)': metrics.eps_trailing,
          'EPS (Forward)': metrics.eps_forward,
          'EPS (Current Year)': metrics.eps_current_year,
          'Price/EPS Current Year': metrics.price_eps_current_year
        }
      },
      
      growth: {
        title: 'Growth Metrics',
        icon: 'ShowChart',
        metrics: {
          'Earnings Growth (Quarterly)': metrics.earnings_q_growth_pct,
          'Revenue Growth': metrics.revenue_growth_pct,
          'Earnings Growth': metrics.earnings_growth_pct
        }
      },
      
      cash_and_debt: {
        title: 'Cash & Debt',
        icon: 'AccountBalance',
        metrics: {
          'Total Cash': metrics.total_cash,
          'Cash per Share': metrics.cash_per_share,
          'Operating Cash Flow': metrics.operating_cashflow,
          'Free Cash Flow': metrics.free_cashflow,
          'Total Debt': metrics.total_debt,
          'Debt to Equity': metrics.debt_to_equity
        }
      },
      
      liquidity: {
        title: 'Liquidity Ratios',
        icon: 'WaterDrop',
        metrics: {
          'Quick Ratio': metrics.quick_ratio,
          'Current Ratio': metrics.current_ratio
        }
      },
      
      profitability: {
        title: 'Profitability Margins',
        icon: 'Percent',
        metrics: {
          'Profit Margin': metrics.profit_margin_pct,
          'Gross Margin': metrics.gross_margin_pct,
          'EBITDA Margin': metrics.ebitda_margin_pct,
          'Operating Margin': metrics.operating_margin_pct
        }
      },
      
      returns: {
        title: 'Return Metrics',
        icon: 'TrendingUp',
        metrics: {
          'Return on Assets': metrics.return_on_assets_pct,
          'Return on Equity': metrics.return_on_equity_pct
        }
      },
      
      dividends: {
        title: 'Dividend Information',
        icon: 'Savings',
        metrics: {
          'Dividend Rate': metrics.dividend_rate,
          'Dividend Yield': metrics.dividend_yield,
          '5-Year Avg Dividend Yield': metrics.five_year_avg_dividend_yield,
          'Payout Ratio': metrics.payout_ratio
        }
      }
    };
    
    // Calculate data quality score
    const totalFields = Object.values(organizedMetrics).reduce((sum, category) => {
      return sum + Object.keys(category.metrics).length;
    }, 0);
    
    const populatedFields = Object.values(organizedMetrics).reduce((sum, category) => {
      return sum + Object.values(category.metrics).filter(value => value !== null && value !== undefined).length;
    }, 0);
    
    const dataQuality = totalFields > 0 ? (populatedFields / totalFields * 100).toFixed(1) : 0;
    
    res.json({
      success: true,
      data: organizedMetrics,
      metadata: {
        ticker: ticker.toUpperCase(),
        dataQuality: `${dataQuality}%`,
        totalMetrics: totalFields,
        populatedMetrics: populatedFields,
        lastUpdated: new Date().toISOString(),
        source: 'key_metrics table via loadinfo'
      }
    });
    
  } catch (error) {
    console.error('Key metrics fetch error:', error.message);
    console.error('Stack:', error.stack);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch key metrics data',
      message: error.message,
      details: 'Check if key_metrics table exists and contains data for this ticker'
    });
  }
});

// Get financial data for a specific symbol
router.get('/data/:symbol', async (req, res) => {
  const { symbol } = req.params;
  console.log(`💰 [FINANCIALS] Fetching financial data for ${symbol}`);
  
  try {
    // Get comprehensive financial data
    const dataQuery = `
      SELECT 
        symbol,
        date,
        item_name,
        value,
        statement_type
      FROM (
        SELECT symbol, date, item_name, value, 'balance_sheet' as statement_type
        FROM annual_balance_sheet 
        WHERE symbol = $1
        UNION ALL
        SELECT symbol, date, item_name, value, 'income_statement' as statement_type
        FROM annual_income_statement 
        WHERE symbol = $1
        UNION ALL
        SELECT symbol, date, item_name, value, 'cash_flow' as statement_type
        FROM annual_cash_flow 
        WHERE symbol = $1
      ) combined_data
      ORDER BY date DESC, statement_type, item_name
      LIMIT 100
    `;

    const result = await query(dataQuery, [symbol.toUpperCase()]);

    if (result.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: `No financial data found for symbol ${symbol}`
      });
    }

    // Group by statement type
    const groupedData = {
      balance_sheet: [],
      income_statement: [],
      cash_flow: []
    };

    result.rows.forEach(row => {
      groupedData[row.statement_type].push({
        date: row.date,
        item_name: row.item_name,
        value: parseFloat(row.value || 0)
      });
    });

    res.json({
      success: true,
      data: groupedData,
      symbol: symbol.toUpperCase(),
      count: result.rows.length
    });
  } catch (error) {
    console.error(`❌ [FINANCIALS] Error fetching financial data for ${symbol}:`, error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch financial data',
      details: error.message
    });
  }
});

// Get earnings data for a specific symbol
router.get('/earnings/:symbol', async (req, res) => {
  const { symbol } = req.params;
  console.log(`📊 [FINANCIALS] Fetching earnings data for ${symbol}`);
  
  try {
    // Get earnings history
    const earningsQuery = `
      SELECT 
        symbol,
        report_date,
        actual_eps,
        estimated_eps,
        surprise_percent,
        revenue_actual,
        revenue_estimated,
        revenue_surprise_percent
      FROM earnings_history
      WHERE symbol = $1
      ORDER BY report_date DESC
      LIMIT 20
    `;

    const result = await query(earningsQuery, [symbol.toUpperCase()]);

    if (result.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: `No earnings data found for symbol ${symbol}`
      });
    }

    res.json({
      success: true,
      data: result.rows,
      count: result.rows.length,
      symbol: symbol.toUpperCase()
    });
  } catch (error) {
    console.error(`❌ [FINANCIALS] Error fetching earnings data for ${symbol}:`, error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch earnings data',
      details: error.message
    });
  }
});

// Get cash flow for a specific symbol (alias for existing endpoint)
router.get('/cash-flow/:symbol', async (req, res) => {
  const { symbol } = req.params;
  console.log(`💵 [FINANCIALS] Fetching cash flow for ${symbol}`);
  
  try {
    // Use the existing cash flow endpoint logic
    const cashFlowQuery = `
      SELECT 
        symbol,
        date,
        item_name,
        value
      FROM annual_cash_flow
      WHERE UPPER(symbol) = UPPER($1)
      ORDER BY date DESC, item_name
      LIMIT 100
    `;
    
    const result = await query(cashFlowQuery, [symbol.toUpperCase()]);
    
    if (result.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: `No cash flow data found for symbol ${symbol}`
      });
    }

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

    res.json({
      success: true,
      data: Object.values(groupedData),
      count: Object.keys(groupedData).length,
      symbol: symbol.toUpperCase()
    });
  } catch (error) {
    console.error(`❌ [FINANCIALS] Error fetching cash flow for ${symbol}:`, error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch cash flow data',
      details: error.message
    });
  }
});

module.exports = router;
