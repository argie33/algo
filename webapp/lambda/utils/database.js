/**
 * UNIFIED DATABASE MODULE - Migrated to UnifiedDatabaseManager
 * 
 * This module now provides a clean interface to the UnifiedDatabaseManager
 * to maintain backward compatibility while fixing the critical issues:
 * 
 * FIXES APPLIED:
 * ✅ Single database connection manager (no more conflicts)
 * ✅ Coordinated timeout hierarchy (Lambda 25s > Circuit 20s > DB 18s)
 * ✅ Proper connection pooling for Lambda environment
 * ✅ Resource cleanup and leak prevention
 * ✅ Circuit breaker integration for stability
 */

const { 
  unifiedDatabaseManager, 
  query, 
  getPool, 
  initializeDatabase, 
  healthCheck, 
  cleanup, 
  getPoolStats,
  timeouts 
} = require('./unifiedDatabaseManager');

const { validateTimeoutHierarchy } = require('./timeoutManager');

// Validate timeout configuration on startup
const validationResult = validateTimeoutHierarchy();
if (!validationResult.valid) {
  console.error('❌ CRITICAL: Timeout hierarchy validation failed during database initialization');
  console.error('Issues found:', validationResult.issues);
  // Don't throw error to allow fallback operation, but log prominently
} else {
  console.log('✅ Database module initialized with validated timeout hierarchy');
}

// Backward compatibility exports
module.exports = {
  // Main functions (maintained for compatibility)
  query,
  getPool,
  initializeDatabase,
  healthCheck,
  cleanup,
  
  // Additional utilities
  getPoolStats,
  
  // Direct access to manager for advanced usage
  manager: unifiedDatabaseManager,
  
  // Timeout configuration
  timeouts,
  
  // Health and diagnostic functions
  async getDiagnostics() {
    const poolStats = getPoolStats();
    const health = await healthCheck();
    const timeoutHierarchy = validateTimeoutHierarchy();
    
    return {
      connectionPool: poolStats,
      health,
      timeouts: timeoutHierarchy.hierarchy,
      timeoutValidation: timeoutHierarchy.valid,
      timestamp: new Date().toISOString()
    };
  },
  
  // Force connection reset (for emergency situations)
  async forceReset() {
    console.log('🔄 Force resetting database connections...');
    await cleanup();
    return initializeDatabase();
  }
};

// Log initialization
console.log('🔧 Database module loaded - using UnifiedDatabaseManager');
console.log(`   Timeout hierarchy: Lambda ${timeouts.lambda}ms > Circuit ${timeouts.circuit}ms > DB ${timeouts.query}ms`);