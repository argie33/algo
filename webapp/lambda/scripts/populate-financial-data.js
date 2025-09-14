/**
 * Database Population Script for Financial Data
 * 
 * This script creates missing tables and populates them with test data
 * for local development and testing purposes.
 */

const { Pool } = require('pg');
require('dotenv').config();

const pool = new Pool({
  host: process.env.DB_HOST || 'localhost',
  user: process.env.DB_USER || 'postgres',
  password: process.env.DB_PASSWORD || 'password',
  database: process.env.DB_NAME || 'stocks',
  port: process.env.DB_PORT || 5432,
});

async function createCashFlowTable() {
  const query = `
    CREATE TABLE IF NOT EXISTS annual_cash_flow (
      id SERIAL PRIMARY KEY,
      symbol VARCHAR(10) NOT NULL,
      fiscal_year INTEGER NOT NULL,
      operating_cash_flow NUMERIC(20,2),
      investing_cash_flow NUMERIC(20,2),
      financing_cash_flow NUMERIC(20,2),
      net_cash_flow NUMERIC(20,2),
      capital_expenditures NUMERIC(20,2),
      free_cash_flow NUMERIC(20,2),
      dividends_paid NUMERIC(20,2),
      stock_repurchases NUMERIC(20,2),
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(symbol, fiscal_year)
    );
    
    CREATE INDEX IF NOT EXISTS idx_annual_cash_flow_symbol_year ON annual_cash_flow(symbol, fiscal_year);
  `;
  
  await pool.query(query);
  console.log('✅ Created annual_cash_flow table');
}

async function addPriceToSalesColumn() {
  const query = `
    ALTER TABLE key_metrics 
    ADD COLUMN IF NOT EXISTS price_to_sales_ttm NUMERIC(5,2);
  `;
  
  await pool.query(query);
  console.log('✅ Added price_to_sales_ttm column to key_metrics table');
}

async function populateBalanceSheetData() {
  const testData = [
    {
      symbol: 'AAPL',
      fiscal_year: 2023,
      total_assets: 352755000000,
      current_assets: 143566000000,
      total_liabilities: 290020000000,
      current_liabilities: 133973000000,
      total_equity: 62146000000,
      retained_earnings: -3068000000,
      cash_and_equivalents: 29965000000,
      total_debt: 123930000000,
      working_capital: 9593000000
    },
    {
      symbol: 'AAPL',
      fiscal_year: 2022,
      total_assets: 352755000000,
      current_assets: 135405000000,
      total_liabilities: 302083000000,
      current_liabilities: 153982000000,
      total_equity: 50672000000,
      retained_earnings: -3454000000,
      cash_and_equivalents: 23646000000,
      total_debt: 120069000000,
      working_capital: -18577000000
    },
    {
      symbol: 'AAPL',
      fiscal_year: 2021,
      total_assets: 351002000000,
      current_assets: 134836000000,
      total_liabilities: 287912000000,
      current_liabilities: 125481000000,
      total_equity: 63090000000,
      retained_earnings: 5562000000,
      cash_and_equivalents: 34940000000,
      total_debt: 124719000000,
      working_capital: 9355000000
    }
  ];

  for (const data of testData) {
    const query = `
      INSERT INTO annual_balance_sheet (
        symbol, fiscal_year, total_assets, current_assets, total_liabilities,
        current_liabilities, total_equity, retained_earnings, cash_and_equivalents,
        total_debt, working_capital
      ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
      ON CONFLICT (symbol, fiscal_year) DO UPDATE SET
        total_assets = EXCLUDED.total_assets,
        current_assets = EXCLUDED.current_assets,
        total_liabilities = EXCLUDED.total_liabilities,
        current_liabilities = EXCLUDED.current_liabilities,
        total_equity = EXCLUDED.total_equity,
        retained_earnings = EXCLUDED.retained_earnings,
        cash_and_equivalents = EXCLUDED.cash_and_equivalents,
        total_debt = EXCLUDED.total_debt,
        working_capital = EXCLUDED.working_capital,
        updated_at = CURRENT_TIMESTAMP
    `;
    
    await pool.query(query, [
      data.symbol, data.fiscal_year, data.total_assets, data.current_assets,
      data.total_liabilities, data.current_liabilities, data.total_equity,
      data.retained_earnings, data.cash_and_equivalents, data.total_debt,
      data.working_capital
    ]);
  }
  
  console.log('✅ Populated balance sheet data for AAPL (3 years)');
}

async function populateCashFlowData() {
  const testData = [
    {
      symbol: 'AAPL',
      fiscal_year: 2023,
      operating_cash_flow: 110543000000,
      investing_cash_flow: -10200000000,
      financing_cash_flow: -108488000000,
      net_cash_flow: -8145000000,
      capital_expenditures: -10959000000,
      free_cash_flow: 99584000000,
      dividends_paid: -14996000000,
      stock_repurchases: -77550000000
    },
    {
      symbol: 'AAPL',
      fiscal_year: 2022,
      operating_cash_flow: 122151000000,
      investing_cash_flow: -22354000000,
      financing_cash_flow: -110749000000,
      net_cash_flow: -10952000000,
      capital_expenditures: -11085000000,
      free_cash_flow: 111066000000,
      dividends_paid: -14841000000,
      stock_repurchases: -89402000000
    },
    {
      symbol: 'AAPL',
      fiscal_year: 2021,
      operating_cash_flow: 104038000000,
      investing_cash_flow: -14545000000,
      financing_cash_flow: -93353000000,
      net_cash_flow: -3860000000,
      capital_expenditures: -11085000000,
      free_cash_flow: 92953000000,
      dividends_paid: -14467000000,
      stock_repurchases: -85971000000
    }
  ];

  for (const data of testData) {
    const query = `
      INSERT INTO annual_cash_flow (
        symbol, fiscal_year, operating_cash_flow, investing_cash_flow,
        financing_cash_flow, net_cash_flow, capital_expenditures,
        free_cash_flow, dividends_paid, stock_repurchases
      ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
      ON CONFLICT (symbol, fiscal_year) DO UPDATE SET
        operating_cash_flow = EXCLUDED.operating_cash_flow,
        investing_cash_flow = EXCLUDED.investing_cash_flow,
        financing_cash_flow = EXCLUDED.financing_cash_flow,
        net_cash_flow = EXCLUDED.net_cash_flow,
        capital_expenditures = EXCLUDED.capital_expenditures,
        free_cash_flow = EXCLUDED.free_cash_flow,
        dividends_paid = EXCLUDED.dividends_paid,
        stock_repurchases = EXCLUDED.stock_repurchases,
        updated_at = CURRENT_TIMESTAMP
    `;
    
    await pool.query(query, [
      data.symbol, data.fiscal_year, data.operating_cash_flow, data.investing_cash_flow,
      data.financing_cash_flow, data.net_cash_flow, data.capital_expenditures,
      data.free_cash_flow, data.dividends_paid, data.stock_repurchases
    ]);
  }
  
  console.log('✅ Populated cash flow data for AAPL (3 years)');
}

async function populateKeyMetricsData() {
  const testData = [
    {
      ticker: 'AAPL',
      trailing_pe: 29.55,
      forward_pe: 24.12,
      dividend_yield: 0.0043,
      peg_ratio: 2.31,
      price_to_book: 45.73,
      price_to_sales_ttm: 7.65
    }
  ];

  for (const data of testData) {
    const query = `
      INSERT INTO key_metrics (
        ticker, trailing_pe, forward_pe, dividend_yield, peg_ratio, price_to_book, price_to_sales_ttm
      ) VALUES ($1, $2, $3, $4, $5, $6, $7)
      ON CONFLICT (ticker) DO UPDATE SET
        trailing_pe = EXCLUDED.trailing_pe,
        forward_pe = EXCLUDED.forward_pe,
        dividend_yield = EXCLUDED.dividend_yield,
        peg_ratio = EXCLUDED.peg_ratio,
        price_to_book = EXCLUDED.price_to_book,
        price_to_sales_ttm = EXCLUDED.price_to_sales_ttm
    `;
    
    await pool.query(query, [
      data.ticker, data.trailing_pe, data.forward_pe, data.dividend_yield,
      data.peg_ratio, data.price_to_book, data.price_to_sales_ttm
    ]);
  }
  
  console.log('✅ Populated key metrics data for AAPL');
}

async function main() {
  try {
    console.log('🚀 Starting financial data population...');
    
    // Create missing table and columns
    await createCashFlowTable();
    await addPriceToSalesColumn();
    
    // Populate test data
    await populateBalanceSheetData();
    await populateCashFlowData();
    await populateKeyMetricsData();
    
    console.log('✅ All financial data populated successfully!');
    console.log('📊 Data available for AAPL across all 4 financial tabs');
    
  } catch (error) {
    console.error('❌ Error populating financial data:', error);
    process.exit(1);
  } finally {
    await pool.end();
  }
}

if (require.main === module) {
  main();
}

module.exports = { main };