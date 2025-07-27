/**
 * Database Schema Fix Utility
 * Applies missing column fixes to portfolio tables to resolve 504 timeout errors
 * This should be run once during deployment to fix the schema mismatch
 */

const { query } = require('./database');
const fs = require('fs');
const path = require('path');

async function applyPortfolioSchemaFix() {
  console.log('🔧 Starting database schema fix for portfolio tables...');
  
  try {
    // Read the migration script
    const migrationPath = path.join(__dirname, '../sql/fix-portfolio-schema-missing-columns.sql');
    const migrationSQL = fs.readFileSync(migrationPath, 'utf8');
    
    console.log('📄 Executing portfolio schema migration...');
    
    // Execute the migration
    await query(migrationSQL);
    
    console.log('✅ Portfolio schema fix applied successfully');
    
    // Verify the fix worked by checking for the columns
    const verifyQuery = `
      SELECT column_name 
      FROM information_schema.columns 
      WHERE table_name IN ('portfolio_holdings', 'portfolio_metadata')
      AND column_name IN ('alpaca_asset_id', 'last_sync_at', 'api_provider')
      ORDER BY table_name, column_name;
    `;
    
    const result = await query(verifyQuery);
    console.log('🔍 Verification - Found columns:', result.rows.map(r => r.column_name));
    
    if (result.rows.length >= 3) {
      console.log('✅ Schema fix verification passed - all required columns present');
      return { success: true, message: 'Portfolio schema fixed successfully' };
    } else {
      console.error('❌ Schema fix verification failed - missing columns');
      return { success: false, message: 'Schema fix incomplete' };
    }
    
  } catch (error) {
    console.error('❌ Failed to apply portfolio schema fix:', error);
    throw new Error(`Schema fix failed: ${error.message}`);
  }
}

// Auto-run if needed (can be controlled by environment variable)
async function autoApplyIfNeeded() {
  if (process.env.AUTO_APPLY_SCHEMA_FIX === 'true') {
    try {
      console.log('🔄 Auto-applying schema fix...');
      await applyPortfolioSchemaFix();
    } catch (error) {
      console.error('⚠️ Auto schema fix failed:', error.message);
      // Don't throw - let the application continue with degraded functionality
    }
  }
}

module.exports = {
  applyPortfolioSchemaFix,
  autoApplyIfNeeded
};