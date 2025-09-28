const { query } = require('./utils/database');

const fs = require('fs').promises;

async function applyDatabaseFixes() {
  try {
    console.log('🔧 Applying database schema fixes...');

    // Read the SQL fix file
    const sqlContent = await fs.readFile('./fix_critical_missing_columns.sql', 'utf8');

    // Split into individual statements (basic splitting by semicolon)
    const statements = sqlContent
      .split(';')
      .map(stmt => stmt.trim())
      .filter(stmt => stmt.length > 0 && !stmt.startsWith('--') && !stmt.includes('check_name'));

    console.log(`📋 Found ${statements.length} SQL statements to execute`);

    for (let i = 0; i < statements.length; i++) {
      const statement = statements[i];
      if (statement.includes('DO $$') || statement.includes('CREATE TABLE') || statement.includes('INSERT INTO') || statement.includes('CREATE INDEX')) {
        try {
          console.log(`⚙️  Executing statement ${i + 1}...`);
          await query(statement);
          console.log(`✅ Statement ${i + 1} executed successfully`);
        } catch (error) {
          console.warn(`⚠️  Statement ${i + 1} warning: ${error.message}`);
          // Continue with other statements
        }
      }
    }

    console.log('🎯 Database fixes completed!');

    // Verify the fixes
    console.log('🔍 Verifying database schema...');

    try {
      const closePriceCheck = await query(`
        SELECT EXISTS (
          SELECT 1 FROM information_schema.columns
          WHERE table_name = 'price_daily' AND column_name = 'close_price'
        ) as has_close_price
      `);
      console.log(`📊 price_daily.close_price: ${closePriceCheck.rows[0].has_close_price ? '✅ EXISTS' : '❌ MISSING'}`);
    } catch (err) {
      console.log(`📊 price_daily.close_price: ❌ CHECK FAILED - ${err.message}`);
    }

    try {
      const portfolioCheck = await query(`
        SELECT EXISTS (
          SELECT 1 FROM information_schema.tables
          WHERE table_name = 'portfolio_performance'
        ) as has_portfolio_performance
      `);
      console.log(`📈 portfolio_performance table: ${portfolioCheck.rows[0].has_portfolio_performance ? '✅ EXISTS' : '❌ MISSING'}`);

      if (portfolioCheck.rows[0].has_portfolio_performance) {
        const pnlCheck = await query(`
          SELECT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'portfolio_performance' AND column_name = 'daily_pnl_percent'
          ) as has_daily_pnl_percent
        `);
        console.log(`💹 daily_pnl_percent column: ${pnlCheck.rows[0].has_daily_pnl_percent ? '✅ EXISTS' : '❌ MISSING'}`);
      }
    } catch (err) {
      console.log(`📈 portfolio_performance: ❌ CHECK FAILED - ${err.message}`);
    }

    try {
      const sentimentCheck = await query(`
        SELECT EXISTS (
          SELECT 1 FROM information_schema.tables
          WHERE table_name = 'sentiment_analysis'
        ) as has_sentiment_analysis
      `);
      console.log(`🎭 sentiment_analysis table: ${sentimentCheck.rows[0].has_sentiment_analysis ? '✅ EXISTS' : '❌ MISSING'}`);
    } catch (err) {
      console.log(`🎭 sentiment_analysis: ❌ CHECK FAILED - ${err.message}`);
    }

    process.exit(0);
  } catch (error) {
    console.error('❌ Database fix failed:', error);
    process.exit(1);
  }
}

// Run the fixes
applyDatabaseFixes();