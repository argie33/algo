const { query } = require('./utils/database');

async function checkUserApiKeysTable() {
  try {
    console.log('🔍 Checking user_api_keys table...\\n');

    // Check if user_api_keys table exists and its structure
    try {
      const result = await query(`
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_name = 'user_api_keys'
        ORDER BY ordinal_position;
      `);

      if (result.rows.length > 0) {
        console.log('✅ user_api_keys table columns:');
        result.rows.forEach(row => {
          console.log(`   • ${row.column_name} (${row.data_type}) ${row.is_nullable === 'YES' ? 'NULL' : 'NOT NULL'}`);
        });
      } else {
        console.log('❌ user_api_keys table not found');
      }
    } catch (err) {
      console.log('❌ Error checking user_api_keys table:', err.message);
    }

    // Check for data in the table
    console.log('\\n🔍 Checking for actual data...\\n');
    try {
      const dataCheck = await query('SELECT COUNT(*) as count FROM user_api_keys LIMIT 1');
      console.log(`📊 user_api_keys table has ${dataCheck.rows[0]?.count || 0} records`);

      if (dataCheck.rows[0]?.count > 0) {
        // Show sample data structure
        const sample = await query('SELECT * FROM user_api_keys LIMIT 3');
        console.log('📋 Sample records:');
        console.log(JSON.stringify(sample.rows, null, 2));
      }
    } catch (err) {
      console.log('❌ No data in user_api_keys or table does not exist');
    }

  } catch (error) {
    console.error('❌ Database connection error:', error.message);
  } finally {
    process.exit(0);
  }
}

checkUserApiKeysTable();