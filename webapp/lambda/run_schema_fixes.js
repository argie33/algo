const { readFileSync } = require('fs');

const { query } = require('./utils/database');

async function executeSchemaFixes() {
  try {
    console.log('📋 Executing additional database schema fixes...');
    
    // Read the SQL fix file
    const sqlContent = readFileSync('./fix_additional_columns.sql', 'utf8');
    
    // Execute the SQL fixes
    const result = await query(sqlContent);
    console.log('✅ Database schema fixes executed successfully');
    
    process.exit(0);
  } catch (error) {
    console.error('❌ Error executing schema fixes:', error);
    process.exit(1);
  }
}

executeSchemaFixes();