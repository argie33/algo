// Test database connectivity for stock screening
const { query } = require('./utils/database');

async function testDatabase() {
  console.log('🔍 Testing database connection...');
  
  try {
    // Test basic connection
    const testResult = await query('SELECT 1 as test', [], 5000);
    console.log('✅ Database connection successful:', testResult.rows[0]);
    
    // Test stock_symbols table exists
    const tableCheckResult = await query(`
      SELECT table_name 
      FROM information_schema.tables 
      WHERE table_schema = 'public' 
      AND table_name IN ('stock_symbols', 'price_daily', 'symbols')
    `);
    
    console.log('📊 Available tables:', tableCheckResult.rows.map(r => r.table_name));
    
    // Test if we have stock data
    if (tableCheckResult.rows.some(r => r.table_name === 'stock_symbols')) {
      const stockCountResult = await query('SELECT COUNT(*) as count FROM stock_symbols WHERE is_active = TRUE LIMIT 10');
      console.log('📈 Active stocks in database:', stockCountResult.rows[0].count);
      
      // Get sample data
      const sampleResult = await query('SELECT symbol, name, sector, exchange FROM stock_symbols WHERE is_active = TRUE LIMIT 5');
      console.log('📋 Sample stocks:', sampleResult.rows);
    } else {
      console.log('⚠️  stock_symbols table not found');
    }
    
  } catch (error) {
    console.error('❌ Database error:', error.message);
    console.error('   Error code:', error.code);
    console.error('   Error details:', error.detail);
  }
}

testDatabase().then(() => {
  console.log('🏁 Database test completed');
  process.exit(0);
}).catch(err => {
  console.error('💥 Test failed:', err);
  process.exit(1);
});