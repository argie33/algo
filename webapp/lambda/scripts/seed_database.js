/* eslint-disable no-process-exit */

/**
 * Database Seeding Script
 * Populates local database with comprehensive mock data for all endpoints
 */

const { query, initializeDatabase } = require("../utils/database");

// Mock data generators
const generateStockData = () => {
  const symbols = [
    "AAPL",
    "MSFT",
    "GOOGL",
    "AMZN",
    "TSLA",
    "META",
    "NVDA",
    "NFLX",
    "CRM",
    "QQQ",
    "SPY",
    "VTI",
  ];
  const sectors = [
    "Technology",
    "Consumer Cyclical",
    "Communication Services",
    "Healthcare",
    "Financials",
  ];
  const exchanges = ["NASDAQ", "NYSE", "AMEX"];

  return symbols.map((symbol) => ({
    symbol,
    security_name: `${symbol} Corporation`,
    exchange: exchanges[Math.floor(Math.random() * exchanges.length)],
    sector: sectors[Math.floor(Math.random() * sectors.length)],
    market_cap: Math.floor(Math.random() * 2000000000000) + 50000000000,
    current_price: Math.floor(Math.random() * 500) + 50,
    volume: Math.floor(Math.random() * 50000000) + 1000000,
  }));
};

const generatePriceData = (symbols) => {
  const priceData = [];
  const dates = [];

  // Generate 30 days of price data
  for (let i = 29; i >= 0; i--) {
    const date = new Date();
    date.setDate(date.getDate() - i);
    dates.push(date);
  }

  symbols.forEach((symbol) => {
    let basePrice = Math.floor(Math.random() * 400) + 100;

    dates.forEach((date) => {
      // Add some price variation
      const variation = (Math.random() - 0.5) * 0.1;
      const open = basePrice * (1 + variation);
      const close = open * (1 + (Math.random() - 0.5) * 0.05);
      const high = Math.max(open, close) * (1 + Math.random() * 0.02);
      const low = Math.min(open, close) * (1 - Math.random() * 0.02);
      const volume = Math.floor(Math.random() * 20000000) + 1000000;

      priceData.push({
        symbol,
        date: date.toISOString().split("T")[0],
        open: Math.round(open * 100) / 100,
        high: Math.round(high * 100) / 100,
        low: Math.round(low * 100) / 100,
        close: Math.round(close * 100) / 100,
        volume,
      });

      basePrice = close; // Use previous close as next base
    });
  });

  return priceData;
};

const generateFinancialData = (symbols) => {
  return symbols.map((symbol) => ({
    ticker: symbol,
    year: 2024,
    total_assets: Math.floor(Math.random() * 500000000000) + 100000000000,
    total_liabilities: Math.floor(Math.random() * 300000000000) + 50000000000,
    total_debt: Math.floor(Math.random() * 100000000000) + 10000000000,
    revenue: Math.floor(Math.random() * 200000000000) + 50000000000,
    net_income: Math.floor(Math.random() * 50000000000) + 5000000000,
  }));
};

const generateCompanyProfiles = (stockData) => {
  return stockData.map((stock) => ({
    ticker: stock.symbol,
    name: stock.security_name,
    sector: stock.sector,
    industry: "Software",
    description: `${stock.security_name} is a leading company in the ${stock.sector} sector.`,
    market_cap: stock.market_cap,
    employees: Math.floor(Math.random() * 100000) + 1000,
    founded: Math.floor(Math.random() * 50) + 1970,
    headquarters: "United States",
  }));
};

async function createTables() {
  console.log("📊 Creating database tables to match Python loaders...");

  // Create stock_symbols table (from loadstocksymbols.py)
  await query(`
    CREATE TABLE IF NOT EXISTS stock_symbols (
      symbol VARCHAR(50),
      exchange VARCHAR(100),
      security_name TEXT,
      cqs_symbol VARCHAR(50),
      market_category VARCHAR(50),
      test_issue CHAR(1),
      financial_status VARCHAR(50),
      round_lot_size INT,
      etf CHAR(1),
      secondary_symbol VARCHAR(50)
    )
  `);

  // Create company_profile table (compatible with API routes)
  await query(`
    CREATE TABLE IF NOT EXISTS company_profile (
      ticker VARCHAR(10) PRIMARY KEY,
      name TEXT,
      sector VARCHAR(100),
      industry VARCHAR(100),
      description TEXT,
      market_cap BIGINT,
      employees INTEGER,
      founded INTEGER,
      headquarters VARCHAR(100),
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
  `);

  // Create price_daily table (from loadpricedaily.py)
  await query(`
    CREATE TABLE IF NOT EXISTS price_daily (
      id SERIAL PRIMARY KEY,
      symbol VARCHAR(10) NOT NULL,
      date DATE NOT NULL,
      open DOUBLE PRECISION,
      high DOUBLE PRECISION,
      low DOUBLE PRECISION,
      close DOUBLE PRECISION,
      adj_close DOUBLE PRECISION,
      volume BIGINT,
      dividends DOUBLE PRECISION,
      stock_splits DOUBLE PRECISION,
      fetched_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
  `);

  // Create fundamental_metrics table (from loadfundamentalmetrics.py)
  await query(`
    CREATE TABLE IF NOT EXISTS fundamental_metrics (
      id SERIAL PRIMARY KEY,
      symbol VARCHAR(10) NOT NULL,
      market_cap BIGINT,
      pe_ratio DECIMAL(10,2),
      forward_pe DECIMAL(10,2),
      peg_ratio DECIMAL(10,2),
      price_to_book DECIMAL(10,2),
      price_to_sales DECIMAL(10,2),
      price_to_cash_flow DECIMAL(10,2),
      dividend_yield DECIMAL(8,4),
      dividend_rate DECIMAL(10,2),
      beta DECIMAL(8,4),
      fifty_two_week_high DECIMAL(10,2),
      fifty_two_week_low DECIMAL(10,2),
      revenue_per_share DECIMAL(10,2),
      revenue BIGINT,
      sector VARCHAR(100),
      industry VARCHAR(200),
      full_time_employees INTEGER,
      updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(symbol)
    )
  `);

  // Create annual_balance_sheet table (for financial API compatibility)
  await query(`
    CREATE TABLE IF NOT EXISTS annual_balance_sheet (
      id SERIAL PRIMARY KEY,
      ticker VARCHAR(10),
      year INTEGER,
      total_assets BIGINT,
      total_liabilities BIGINT,
      total_debt BIGINT,
      revenue BIGINT,
      net_income BIGINT,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(ticker, year)
    )
  `);

  // Create portfolio_holdings table (for portfolio features)
  await query(`
    CREATE TABLE IF NOT EXISTS portfolio_holdings (
      id SERIAL PRIMARY KEY,
      user_id VARCHAR(50) DEFAULT 'default',
      symbol VARCHAR(10),
      quantity DECIMAL(10,2),
      average_cost DECIMAL(10,2),
      current_price DECIMAL(10,2),
      market_value DECIMAL(12,2),
      unrealized_pnl DECIMAL(12,2),
      unrealized_pnl_percent DECIMAL(5,2),
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
  `);

  // Create indexes for performance
  await query(`
    CREATE INDEX IF NOT EXISTS idx_fundamental_metrics_symbol ON fundamental_metrics(symbol);
    CREATE INDEX IF NOT EXISTS idx_fundamental_metrics_sector ON fundamental_metrics(sector);
    CREATE INDEX IF NOT EXISTS idx_price_daily_symbol_date ON price_daily(symbol, date);
  `);

  console.log("✅ Tables created successfully (matching Python loaders)");
}

async function seedData() {
  console.log("🌱 Seeding database with mock data...");

  const stockData = generateStockData();
  const priceData = generatePriceData(stockData.map((s) => s.symbol));
  const financialData = generateFinancialData(stockData.map((s) => s.symbol));
  const companyProfiles = generateCompanyProfiles(stockData);

  // Clear existing data
  await query("DELETE FROM price_daily");
  await query("DELETE FROM stock_symbols");
  await query("DELETE FROM fundamental_metrics");
  await query("DELETE FROM company_profile");
  await query("DELETE FROM annual_balance_sheet");
  await query("DELETE FROM portfolio_holdings");

  // Insert stock symbols (exact matching loadstocksymbols.py structure)
  for (const stock of stockData) {
    await query(
      `INSERT INTO stock_symbols (symbol, exchange, security_name, cqs_symbol, market_category, test_issue, financial_status, round_lot_size, etf, secondary_symbol)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)`,
      [
        stock.symbol,
        stock.exchange,
        stock.security_name,
        null,
        "Q",
        "N",
        "N",
        100,
        "N",
        null,
      ]
    );
  }
  console.log(`✅ Inserted ${stockData.length} stock symbols`);

  // Insert company profiles
  for (const company of companyProfiles) {
    await query(
      `INSERT INTO company_profile (ticker, name, sector, industry, description, market_cap, employees, founded, headquarters)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9) ON CONFLICT (ticker) DO NOTHING`,
      [
        company.ticker,
        company.name,
        company.sector,
        company.industry,
        company.description,
        company.market_cap,
        company.employees,
        company.founded,
        company.headquarters,
      ]
    );
  }
  console.log(`✅ Inserted ${companyProfiles.length} company profiles`);

  // Insert fundamental metrics (matching loadfundamentalmetrics.py structure)
  for (const stock of stockData) {
    await query(
      `INSERT INTO fundamental_metrics (
        symbol, market_cap, pe_ratio, forward_pe, peg_ratio, price_to_book, price_to_sales,
        price_to_cash_flow, dividend_yield, dividend_rate, beta, fifty_two_week_high,
        fifty_two_week_low, revenue_per_share, revenue_growth, quarterly_revenue_growth,
        gross_profit, ebitda, operating_income, net_income, earnings_per_share,
        quarterly_earnings_growth, return_on_equity, return_on_assets, debt_to_equity,
        current_ratio, quick_ratio, book_value, shares_outstanding, float_shares,
        short_ratio, short_interest, enterprise_value, enterprise_to_revenue,
        enterprise_to_ebitda, sector, industry, full_time_employees
      ) VALUES (
        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18,
        $19, $20, $21, $22, $23, $24, $25, $26, $27, $28, $29, $30, $31, $32, $33, $34, $35, $36, $37, $38
      ) ON CONFLICT (symbol) DO NOTHING`,
      [
        stock.symbol,
        stock.market_cap,
        Math.round((Math.random() * 50 + 10) * 100) / 100, // pe_ratio
        Math.round((Math.random() * 40 + 8) * 100) / 100, // forward_pe
        Math.round((Math.random() * 3 + 0.5) * 100) / 100, // peg_ratio
        Math.round((Math.random() * 10 + 1) * 100) / 100, // price_to_book
        Math.round((Math.random() * 20 + 2) * 100) / 100, // price_to_sales
        Math.round((Math.random() * 30 + 5) * 100) / 100, // price_to_cash_flow
        Math.round((Math.random() * 0.05 + 0.01) * 10000) / 10000, // dividend_yield
        Math.round((Math.random() * 5 + 0.5) * 100) / 100, // dividend_rate
        Math.round((Math.random() * 2 + 0.5) * 10000) / 10000, // beta
        Math.round(stock.current_price * 1.2 * 100) / 100, // fifty_two_week_high
        Math.round(stock.current_price * 0.8 * 100) / 100, // fifty_two_week_low
        Math.round((Math.random() * 50 + 10) * 100) / 100, // revenue_per_share
        Math.round((Math.random() * 0.2 + 0.05) * 10000) / 10000, // revenue_growth
        Math.round((Math.random() * 0.15 + 0.02) * 10000) / 10000, // quarterly_revenue_growth
        Math.floor(Math.random() * 50000000000) + 10000000000, // gross_profit
        Math.floor(Math.random() * 30000000000) + 5000000000, // ebitda
        Math.floor(Math.random() * 20000000000) + 3000000000, // operating_income
        Math.floor(Math.random() * 15000000000) + 2000000000, // net_income
        Math.round((Math.random() * 20 + 2) * 100) / 100, // earnings_per_share
        Math.round((Math.random() * 0.1 + 0.02) * 10000) / 10000, // quarterly_earnings_growth
        Math.round((Math.random() * 0.3 + 0.1) * 10000) / 10000, // return_on_equity
        Math.round((Math.random() * 0.2 + 0.05) * 10000) / 10000, // return_on_assets
        Math.round((Math.random() * 2 + 0.2) * 100) / 100, // debt_to_equity
        Math.round((Math.random() * 3 + 1) * 10000) / 10000, // current_ratio
        Math.round((Math.random() * 2 + 0.5) * 10000) / 10000, // quick_ratio
        Math.round((Math.random() * 100 + 20) * 100) / 100, // book_value
        Math.floor(Math.random() * 5000000000) + 1000000000, // shares_outstanding
        Math.floor(Math.random() * 4000000000) + 800000000, // float_shares
        Math.round((Math.random() * 10 + 1) * 100) / 100, // short_ratio
        Math.floor(Math.random() * 100000000) + 10000000, // short_interest
        Math.floor(Math.random() * 2000000000000) + 100000000000, // enterprise_value
        Math.round((Math.random() * 15 + 2) * 100) / 100, // enterprise_to_revenue
        Math.round((Math.random() * 20 + 5) * 100) / 100, // enterprise_to_ebitda
        stock.sector,
        "Software",
        Math.floor(Math.random() * 100000) + 1000, // industry, full_time_employees
      ]
    );
  }
  console.log(`✅ Inserted ${stockData.length} fundamental metrics`);

  // Insert price data in batches
  const batchSize = 100;
  for (let i = 0; i < priceData.length; i += batchSize) {
    const batch = priceData.slice(i, i + batchSize);
    for (const price of batch) {
      await query(
        `INSERT INTO price_daily (symbol, date, open, high, low, close, adj_close, volume, dividends, stock_splits)
         VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)`,
        [
          price.symbol,
          price.date,
          price.open,
          price.high,
          price.low,
          price.close,
          price.close,
          price.volume,
          0,
          0,
        ]
      );
    }
    console.log(
      `📈 Inserted price data batch ${Math.ceil((i + batchSize) / batchSize)} of ${Math.ceil(priceData.length / batchSize)}`
    );
  }

  // Insert financial data
  for (const financial of financialData) {
    await query(
      `INSERT INTO annual_balance_sheet (ticker, year, total_assets, total_liabilities, total_debt, revenue, net_income)
       VALUES ($1, $2, $3, $4, $5, $6, $7) ON CONFLICT (ticker, year) DO NOTHING`,
      [
        financial.ticker,
        financial.year,
        financial.total_assets,
        financial.total_liabilities,
        financial.total_debt,
        financial.revenue,
        financial.net_income,
      ]
    );
  }
  console.log(`✅ Inserted ${financialData.length} financial records`);

  // Insert sample portfolio holdings
  const portfolioHoldings = [
    { symbol: "AAPL", quantity: 100, average_cost: 150, current_price: 185.4 },
    { symbol: "MSFT", quantity: 50, average_cost: 320, current_price: 378.85 },
    { symbol: "GOOGL", quantity: 25, average_cost: 120, current_price: 142.3 },
    { symbol: "AMZN", quantity: 30, average_cost: 140, current_price: 155.2 },
  ];

  for (const holding of portfolioHoldings) {
    const marketValue = holding.quantity * holding.current_price;
    const totalCost = holding.quantity * holding.average_cost;
    const unrealizedPnl = marketValue - totalCost;
    const unrealizedPnlPercent = (unrealizedPnl / totalCost) * 100;

    await query(
      `INSERT INTO portfolio_holdings (symbol, quantity, average_cost, current_price, market_value, unrealized_pnl, unrealized_pnl_percent)
       VALUES ($1, $2, $3, $4, $5, $6, $7)`,
      [
        holding.symbol,
        holding.quantity,
        holding.average_cost,
        holding.current_price,
        marketValue,
        unrealizedPnl,
        unrealizedPnlPercent,
      ]
    );
  }
  console.log(`✅ Inserted ${portfolioHoldings.length} portfolio holdings`);
}

async function main() {
  try {
    console.log("🚀 Starting database seeding process...");

    // Initialize database connection
    await initializeDatabase();
    console.log("✅ Database connected");

    // Create tables
    await createTables();

    // Seed data
    await seedData();

    console.log("🎉 Database seeding completed successfully!");
    console.log("\n📊 Summary:");
    console.log("- Stock symbols and company profiles populated");
    console.log("- 30 days of price data for all symbols");
    console.log("- Annual balance sheet data");
    console.log("- Sample portfolio holdings");
    console.log("\n✅ All APIs should now have data to display");

    process.exit(0);
  } catch (error) {
    console.error("❌ Database seeding failed:", error);
    process.exit(1);
  }
}

if (require.main === module) {
  main();
}

module.exports = { main };
