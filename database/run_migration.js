const fs = require('fs');
const path = require('path');
const { query } = require('../webapp/lambda/utils/database');

async function runMigration() {
  try {
    console.log('🔄 Running database migration: Create user_api_keys table');
    
    // Read the SQL migration file
    const migrationPath = path.join(__dirname, 'migrations', '001_create_user_api_keys.sql');
    const migrationSQL = fs.readFileSync(migrationPath, 'utf8');
    
    console.log('📋 Executing SQL migration...');
    
    // Execute the migration
    await query(migrationSQL);
    
    console.log('✅ Migration completed successfully!');
    
    // Verify the table was created
    const result = await query(`
      SELECT column_name, data_type, is_nullable 
      FROM information_schema.columns 
      WHERE table_name = 'user_api_keys' 
      ORDER BY ordinal_position;
    `);
    
    console.log('📊 Table structure verified:');
    console.table(result.rows);
    
    process.exit(0);
  } catch (error) {
    console.error('❌ Migration failed:', error.message);
    console.error('🔍 Error details:', error);
    process.exit(1);
  }
}

runMigration();