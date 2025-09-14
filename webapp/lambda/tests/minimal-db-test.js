// Minimal database connectivity test
process.env.NODE_ENV = 'test';
process.env.DB_HOST = 'localhost';
process.env.DB_USER = 'postgres';
process.env.DB_PASSWORD = 'password';
process.env.DB_NAME = 'stocks';
process.env.DB_PORT = '5432';

const db = require('../utils/database');

async function testDatabase() {
  try {
    console.log('🔄 Testing database connection...');
    
    const pool = await db.initializeDatabase();
    if (!pool) {
      console.error('❌ Database pool is null');
      return false;
    }
    
    const result = await db.query('SELECT NOW() as current_time');
    console.log('✅ Database query successful:', result.rows[0]);
    
    const healthResult = await db.query('SELECT COUNT(*) as table_count FROM information_schema.tables WHERE table_schema = $1', ['public']);
    console.log('✅ Database health check - tables:', healthResult.rows[0]);
    
    await db.closeDatabase();
    console.log('✅ Database connection closed');
    return true;
    
  } catch (error) {
    console.error('❌ Database test failed:', error.message);
    return false;
  }
}

testDatabase().then(success => {
  if (!success) {
    throw new Error('Database test failed');
  }
}).catch(error => {
  console.error('Database test error:', error);
  throw error;
});