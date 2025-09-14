const fs = require('fs');

const { initializeDatabase, query } = require('./utils/database');

async function populatePriceData() {
  try {
    console.log('🔄 Initializing database connection...');
    await initializeDatabase();
    
    console.log('📊 Reading SQL file...');
    const sqlContent = fs.readFileSync('populate_price_daily.sql', 'utf8');
    
    // Split by semicolon and execute each statement
    const statements = sqlContent.split(';').filter(s => s.trim());
    
    for (let i = 0; i < statements.length; i++) {
      const statement = statements[i].trim();
      if (statement) {
        console.log(`📝 Executing statement ${i+1}/${statements.length}...`);
        await query(statement);
      }
    }
    
    console.log('✅ Price data populated successfully!');
    
    // Verify data
    const result = await query('SELECT COUNT(*) as count FROM price_daily');
    console.log(`📊 Total price_daily records: ${result.rows[0].count}`);
    
  } catch (error) {
    console.error('❌ Error populating price data:', error);
    throw error;
  }
}

populatePriceData();