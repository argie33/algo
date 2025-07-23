/**
 * Database Table Initialization Utility
 * Ensures all required tables exist for core application functionality
 */

const { query, healthCheck } = require('./database');
const fs = require('fs').promises;
const path = require('path');

// Cache initialization status to avoid repeated checks
let initializationStatus = {
  isInitialized: false,
  lastChecked: null,
  tables: {},
  errors: []
};

// Required tables for core functionality
const REQUIRED_TABLES = [
  'users',
  'user_api_keys', 
  'portfolio_holdings',
  'portfolio_metadata'
];

// Optional tables that enhance functionality
const OPTIONAL_TABLES = [
  'market_data',
  'stock_symbols',
  'symbols'
];

/**
 * Check if specific tables exist in the database
 */
async function checkTablesExist(tableNames) {
  try {
    const placeholders = tableNames.map((_, index) => `$${index + 1}`).join(',');
    const result = await query(`
      SELECT table_name, table_type
      FROM information_schema.tables 
      WHERE table_schema = 'public' 
      AND table_name IN (${placeholders})
    `, tableNames);

    const existingTables = result.rows.map(row => row.table_name);
    const tableStatus = {};
    
    tableNames.forEach(tableName => {
      tableStatus[tableName] = existingTables.includes(tableName);
    });

    return {
      success: true,
      tableStatus,
      existingTables,
      missingTables: tableNames.filter(table => !existingTables.includes(table))
    };
  } catch (error) {
    console.error('Error checking table existence:', error);
    return {
      success: false,
      error: error.message,
      tableStatus: {},
      existingTables: [],
      missingTables: tableNames
    };
  }
}

/**
 * Initialize required database tables
 */
async function initializeRequiredTables(options = {}) {
  const { 
    force = false, 
    verbose = true,
    checkOnly = false 
  } = options;

  const startTime = Date.now();
  const operationId = Math.random().toString(36).substring(7);

  if (verbose) {
    console.log(`🚀 [${operationId}] Starting database table initialization...`);
  }

  try {
    // Check if we need to run initialization
    if (!force && initializationStatus.isInitialized) {
      const timeSinceLastCheck = Date.now() - initializationStatus.lastChecked;
      if (timeSinceLastCheck < 300000) { // 5 minutes cache
        if (verbose) {
          console.log(`✅ [${operationId}] Using cached initialization status (${Math.round(timeSinceLastCheck/1000)}s ago)`);
        }
        return initializationStatus;
      }
    }

    // Test database connectivity first
    if (verbose) {
      console.log(`🔍 [${operationId}] Testing database connectivity...`);
    }
    
    const healthResult = await healthCheck();
    if (!healthResult.healthy) {
      throw new Error(`Database connectivity failed: ${healthResult.error}`);
    }

    if (verbose) {
      console.log(`✅ [${operationId}] Database connectivity confirmed`);
    }

    // Check which tables currently exist
    const allTables = [...REQUIRED_TABLES, ...OPTIONAL_TABLES];
    const tableCheck = await checkTablesExist(allTables);

    if (!tableCheck.success) {
      throw new Error(`Failed to check table existence: ${tableCheck.error}`);
    }

    const missingRequired = REQUIRED_TABLES.filter(table => !tableCheck.tableStatus[table]);
    const missingOptional = OPTIONAL_TABLES.filter(table => !tableCheck.tableStatus[table]);

    if (verbose) {
      console.log(`📊 [${operationId}] Table status:`, {
        existing: tableCheck.existingTables.length,
        missingRequired: missingRequired.length,
        missingOptional: missingOptional.length,
        requiredTablesPresent: missingRequired.length === 0
      });
    }

    // If only checking, return current status
    if (checkOnly) {
      const result = {
        success: true,
        isInitialized: missingRequired.length === 0,
        tables: tableCheck.tableStatus,
        existingTables: tableCheck.existingTables,
        missingRequired,
        missingOptional,
        checkDuration: Date.now() - startTime,
        operationId
      };

      if (verbose) {
        console.log(`✅ [${operationId}] Table check completed in ${result.checkDuration}ms`);
      }

      return result;
    }

    // Create missing tables if needed
    if (missingRequired.length > 0 || missingOptional.length > 0) {
      if (verbose) {
        console.log(`🔧 [${operationId}] Creating missing tables...`);
        console.log(`   Required missing: ${missingRequired.join(', ') || 'none'}`);
        console.log(`   Optional missing: ${missingOptional.join(', ') || 'none'}`);
      }

      // Read and execute initialization SQL
      const sqlPath = path.join(__dirname, '..', 'sql', 'initialize-required-tables.sql');
      const initSQL = await fs.readFile(sqlPath, 'utf8');

      if (verbose) {
        console.log(`📄 [${operationId}] Executing table creation SQL...`);
      }

      // Execute the initialization SQL
      await query(initSQL);

      if (verbose) {
        console.log(`✅ [${operationId}] Table creation SQL executed successfully`);
      }

      // Verify tables were created
      const verifyCheck = await checkTablesExist(allTables);
      const stillMissingRequired = REQUIRED_TABLES.filter(table => !verifyCheck.tableStatus[table]);

      if (stillMissingRequired.length > 0) {
        throw new Error(`Failed to create required tables: ${stillMissingRequired.join(', ')}`);
      }

      if (verbose) {
        console.log(`✅ [${operationId}] All required tables verified as created`);
      }
    }

    // Update cache
    const finalCheck = await checkTablesExist(allTables);
    initializationStatus = {
      isInitialized: true,
      lastChecked: Date.now(),
      tables: finalCheck.tableStatus,
      existingTables: finalCheck.existingTables,
      missingRequired: REQUIRED_TABLES.filter(table => !finalCheck.tableStatus[table]),
      missingOptional: OPTIONAL_TABLES.filter(table => !finalCheck.tableStatus[table]),
      errors: [],
      operationId,
      duration: Date.now() - startTime
    };

    if (verbose) {
      console.log(`🎉 [${operationId}] Database initialization completed successfully in ${initializationStatus.duration}ms`);
      console.log(`   ✅ Required tables: ${REQUIRED_TABLES.length - initializationStatus.missingRequired.length}/${REQUIRED_TABLES.length}`);
      console.log(`   ⚠️ Optional tables: ${OPTIONAL_TABLES.length - initializationStatus.missingOptional.length}/${OPTIONAL_TABLES.length}`);
    }

    return {
      success: true,
      ...initializationStatus
    };

  } catch (error) {
    const errorDuration = Date.now() - startTime;
    console.error(`❌ [${operationId}] Database initialization failed after ${errorDuration}ms:`, error);

    const errorResult = {
      success: false,
      isInitialized: false,
      error: error.message,
      errorCode: error.code,
      duration: errorDuration,
      operationId,
      tables: initializationStatus.tables || {},
      missingRequired: REQUIRED_TABLES,
      missingOptional: OPTIONAL_TABLES
    };

    // Update cache with error state
    initializationStatus = {
      ...initializationStatus,
      isInitialized: false,
      lastChecked: Date.now(),
      errors: [...(initializationStatus.errors || []), {
        message: error.message,
        timestamp: new Date().toISOString(),
        operationId
      }]
    };

    return errorResult;
  }
}

/**
 * Get current initialization status from cache
 */
function getInitializationStatus() {
  return {
    ...initializationStatus,
    cacheAge: initializationStatus.lastChecked ? Date.now() - initializationStatus.lastChecked : null
  };
}

/**
 * Clear initialization cache (force re-check on next call)
 */
function clearInitializationCache() {
  initializationStatus = {
    isInitialized: false,
    lastChecked: null,
    tables: {},
    errors: []
  };
}

/**
 * Quick check if required tables exist (uses cache if available)
 */
async function areRequiredTablesInitialized() {
  try {
    const status = await initializeRequiredTables({ checkOnly: true, verbose: false });
    return status.success && status.isInitialized;
  } catch (error) {
    console.error('Error checking table initialization status:', error);
    return false;
  }
}

module.exports = {
  initializeRequiredTables,
  checkTablesExist,
  getInitializationStatus,
  clearInitializationCache,
  areRequiredTablesInitialized,
  REQUIRED_TABLES,
  OPTIONAL_TABLES
};