/**
 * Database Mock for Integration Tests
 * Provides in-memory database simulation using table schemas from Python loaders
 */

// Basic schemas for mock database (based on Python loader scripts)
const schemas = {
  // Core tables from Python loaders
  stocks: true,
  price_daily: true,
  fundamental_metrics: true,

  // User and portfolio tables
  users: true,
  user_dashboard_settings: true,
  user_notification_settings: true,
  alerts: true,
  portfolio_holdings: true,
  portfolio_performance: true,

  // Test tables for rollback scenarios
  test_rollback_error: true,
  test_app_error_rollback: true,
  test_manual_rollback: true,
  test_nested_rollback: true,
  test_orders: true,
  test_order_items: true,
  test_inventory: true,
  test_complex_rollback: true,
  test_resource_cleanup: true,
  test_portfolio_positions: true,
  test_portfolio_transactions: true
};

// In-memory storage for mock tables
let mockTables = new Map();
let mockTransactionState = null;

// Mock query results counter for generating IDs
let queryIdCounter = 1;

/**
 * Initialize mock database with schemas from Python loaders
 */
async function initializeDatabase() {
  mockTables.clear();

  // Initialize all tables with empty data
  if (!schemas) {
    console.warn('⚠️ No schemas found, initializing empty mock database');
    return true;
  }

  const schemaDefinitions = Object.keys(schemas);
  for (const tableName of schemaDefinitions) {
    mockTables.set(tableName, []);
  }

  console.log(`✅ Mock database initialized with ${schemaDefinitions.length} tables`);
  return true;
}

/**
 * Mock query executor with basic SQL parsing
 */
async function query(sql, params = []) {
  console.log(`🔍 Mock query: ${sql.substring(0, 100)}...`);

  // Handle different SQL operations
  const normalizedSql = sql.trim().toUpperCase();

  if (normalizedSql.startsWith('CREATE TABLE')) {
    return handleCreateTable(sql);
  }

  if (normalizedSql.startsWith('INSERT')) {
    return handleInsert(sql, params);
  }

  if (normalizedSql.startsWith('SELECT')) {
    return handleSelect(sql, params);
  }

  if (normalizedSql.startsWith('UPDATE')) {
    return handleUpdate(sql, params);
  }

  if (normalizedSql.startsWith('DELETE')) {
    return handleDelete(sql, params);
  }

  // Default response for unsupported queries
  return { rows: [], rowCount: 0 };
}

/**
 * Handle CREATE TABLE statements
 */
function handleCreateTable(sql) {
  // Extract table name (handle TEMPORARY tables and IF NOT EXISTS)
  const match = sql.match(/CREATE\s+(?:TEMPORARY\s+)?TABLE(?:\s+IF\s+NOT\s+EXISTS)?\s+([a-zA-Z_][a-zA-Z0-9_]*)/i);
  if (match) {
    const tableName = match[1].toLowerCase();
    if (!mockTables.has(tableName)) {
      mockTables.set(tableName, []);
      console.log(`✅ Created mock table: ${tableName}`);
    }
  }
  return { rows: [], rowCount: 0 };
}

/**
 * Handle INSERT statements
 */
function handleInsert(sql, params) {
  // Extract table name
  const match = sql.match(/INSERT INTO\s+([a-zA-Z_][a-zA-Z0-9_]*)/i);
  if (!match) {
    throw new Error('Invalid INSERT statement');
  }

  const tableName = match[1].toLowerCase();
  if (!mockTables.has(tableName)) {
    mockTables.set(tableName, []);
  }

  const table = mockTables.get(tableName);

  // Extract values and columns
  const valuesMatch = sql.match(/VALUES\s*\((.*?)\)/i);
  const columnsMatch = sql.match(/\((.*?)\)\s*VALUES/i);

  if (valuesMatch) {
    // Create a mock row with the inserted data
    const mockRow = { id: queryIdCounter++ };

    // If we have column names, use them
    if (columnsMatch) {
      const columns = columnsMatch[1].split(',').map(col => col.trim().replace(/['"]/g, ''));
      const values = params.length > 0 ? params : parseValues(valuesMatch[1]);

      columns.forEach((col, index) => {
        mockRow[col] = values[index] !== undefined ? values[index] : null;
      });
    } else {
      // Generic row with parameters
      params.forEach((param, index) => {
        mockRow[`col_${index}`] = param;
      });
    }

    // Special handling for test tables with constraints
    if (tableName.includes('rollback') || tableName.includes('test_')) {
      // Check for duplicate values that should cause constraint violations
      if (mockRow.value && table.some(row => row.value === mockRow.value)) {
        throw new Error('duplicate key value violates unique constraint');
      }
    }

    table.push(mockRow);

    // Return appropriate result for RETURNING clause
    if (sql.toUpperCase().includes('RETURNING')) {
      return { rows: [mockRow], rowCount: 1 };
    }

    return { rows: [], rowCount: 1 };
  }

  return { rows: [], rowCount: 0 };
}

/**
 * Handle SELECT statements
 */
function handleSelect(sql, params) {
  // Extract table name
  const fromMatch = sql.match(/FROM\s+([a-zA-Z_][a-zA-Z0-9_]*)/i);
  if (!fromMatch) {
    // Handle simple queries like SELECT 1
    if (sql.match(/SELECT\s+\d+/i)) {
      return { rows: [{ test: 1 }], rowCount: 1 };
    }
    return { rows: [], rowCount: 0 };
  }

  const tableName = fromMatch[1].toLowerCase();
  const table = mockTables.get(tableName) || [];

  // Handle COUNT queries
  if (sql.toUpperCase().includes('COUNT(*)')) {
    const count = table.length;
    return { rows: [{ count: count.toString() }], rowCount: 1 };
  }

  // Handle WHERE clauses
  let filteredRows = [...table];
  const whereMatch = sql.match(/WHERE\s+(.+?)(?:ORDER BY|GROUP BY|LIMIT|$)/i);
  if (whereMatch && params.length > 0) {
    const condition = whereMatch[1];
    // Simple parameter substitution for test purposes
    filteredRows = table.filter((row, index) => {
      // Very basic filtering - in real scenarios this would need proper SQL parsing
      return true; // For now, return all rows
    });
  }

  // Handle ORDER BY
  if (sql.toUpperCase().includes('ORDER BY')) {
    const orderMatch = sql.match(/ORDER BY\s+([a-zA-Z_][a-zA-Z0-9_]*)/i);
    if (orderMatch) {
      const orderBy = orderMatch[1].toLowerCase();
      filteredRows.sort((a, b) => {
        if (a[orderBy] < b[orderBy]) return -1;
        if (a[orderBy] > b[orderBy]) return 1;
        return 0;
      });
    }
  }

  return { rows: filteredRows, rowCount: filteredRows.length };
}

/**
 * Handle UPDATE statements
 */
function handleUpdate(sql, params) {
  const match = sql.match(/UPDATE\s+([a-zA-Z_][a-zA-Z0-9_]*)/i);
  if (!match) return { rows: [], rowCount: 0 };

  const tableName = match[1].toLowerCase();
  const table = mockTables.get(tableName) || [];

  // Simple update - in a real mock this would parse SET clause properly
  table.forEach(row => {
    if (params.length > 0) {
      row.updated = true;
    }
  });

  return { rows: [], rowCount: table.length };
}

/**
 * Handle DELETE statements
 */
function handleDelete(sql, params) {
  const match = sql.match(/DELETE FROM\s+([a-zA-Z_][a-zA-Z0-9_]*)/i);
  if (!match) return { rows: [], rowCount: 0 };

  const tableName = match[1].toLowerCase();
  const table = mockTables.get(tableName) || [];
  const originalLength = table.length;

  // Clear the table for simple DELETE (in real mock would handle WHERE clauses)
  mockTables.set(tableName, []);

  return { rows: [], rowCount: originalLength };
}

/**
 * Parse VALUES from SQL string
 */
function parseValues(valuesStr) {
  return valuesStr.split(',').map(val => {
    val = val.trim();
    // Remove quotes and convert to appropriate type
    if (val.startsWith("'") || val.startsWith('"')) {
      return val.slice(1, -1);
    }
    if (!isNaN(val)) {
      return parseFloat(val);
    }
    return val;
  });
}

/**
 * Mock transaction implementation
 */
async function transaction(callback) {
  // Save current state for rollback
  const savedState = new Map();
  mockTables.forEach((value, key) => {
    savedState.set(key, [...value]);
  });

  // Mock client with query method
  const mockClient = {
    query: async (sql, params) => {
      if (sql === 'BEGIN' || sql === 'COMMIT' || sql === 'ROLLBACK') {
        return { rows: [], rowCount: 0 };
      }
      return query(sql, params);
    },
    release: () => {} // Mock release
  };

  try {
    // Execute the callback
    const result = await callback(mockClient);
    return result;
  } catch (error) {
    // Rollback on error - restore saved state
    mockTables.clear();
    savedState.forEach((value, key) => {
      mockTables.set(key, value);
    });
    throw error;
  }
}

/**
 * Get mock pool with connect method
 */
function getPool() {
  return {
    connect: async () => ({
      query: async (sql, params) => query(sql, params),
      release: () => {}
    })
  };
}

/**
 * Mock cached query (same as regular query)
 */
const cachedQuery = query;

/**
 * Clear query cache (no-op in mock)
 */
function clearQueryCache() {
  // No-op
}

/**
 * Close database (reset mock)
 */
async function closeDatabase() {
  mockTables.clear();
  console.log("✅ Mock database closed");
}

/**
 * Health check (always healthy in mock)
 */
function healthCheck() {
  return {
    status: 'healthy',
    totalConnections: 1,
    idle: 0,
    waiting: 0
  };
}

module.exports = {
  initializeDatabase,
  getPool,
  query,
  cachedQuery,
  clearQueryCache,
  transaction,
  closeDatabase,
  healthCheck,
  // Test utilities
  _getMockTables: () => mockTables,
  _resetMock: () => {
    mockTables.clear();
    queryIdCounter = 1;
  }
};