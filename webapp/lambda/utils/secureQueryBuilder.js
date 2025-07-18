/**
 * Secure Query Builder Utility
 * Replaces vulnerable dynamic SQL construction with secure parameterized queries
 */

class SecureQueryBuilder {
  constructor() {
    // Whitelisted table names (prevent table injection)
    this.allowedTables = new Set([
      'users',
      'user_api_keys',
      'user_notification_preferences', 
      'user_theme_preferences',
      'user_sessions',
      'portfolio_holdings',
      'trade_history',
      'watchlist',
      'alerts',
      'market_data',
      'stock_symbols',
      'technical_indicators',
      'earnings_data',
      'news_articles',
      'sentiment_data',
      'economic_data'
    ]);

    // Whitelisted columns for each table
    this.allowedColumns = {
      users: new Set([
        'id', 'cognito_id', 'email', 'first_name', 'last_name', 
        'phone', 'timezone', 'language', 'currency_preference',
        'created_at', 'updated_at', 'last_login', 'is_active'
      ]),
      user_api_keys: new Set([
        'id', 'user_id', 'provider', 'api_key_encrypted', 'masked_api_key',
        'is_active', 'validation_status', 'created_at', 'updated_at'
      ]),
      user_notification_preferences: new Set([
        'id', 'user_id', 'email_notifications', 'push_notifications', 
        'sms_notifications', 'updated_at'
      ]),
      user_theme_preferences: new Set([
        'id', 'user_id', 'dark_mode', 'primary_color', 'updated_at'
      ])
    };

    // SQL operators whitelist
    this.allowedOperators = new Set([
      '=', '!=', '<>', '<', '>', '<=', '>=', 
      'LIKE', 'ILIKE', 'IN', 'NOT IN', 'IS NULL', 'IS NOT NULL'
    ]);

    // ORDER BY directions
    this.allowedOrderDirections = new Set(['ASC', 'DESC']);
  }

  /**
   * Validate table name against whitelist
   */
  validateTable(tableName) {
    if (!tableName || typeof tableName !== 'string') {
      throw new Error('Invalid table name');
    }

    const cleanTable = tableName.toLowerCase().trim();
    if (!this.allowedTables.has(cleanTable)) {
      throw new Error(`Unauthorized table access: ${tableName}`);
    }

    return cleanTable;
  }

  /**
   * Validate column name against table-specific whitelist
   */
  validateColumn(tableName, columnName) {
    if (!columnName || typeof columnName !== 'string') {
      throw new Error('Invalid column name');
    }

    const cleanTable = this.validateTable(tableName);
    const cleanColumn = columnName.toLowerCase().trim();
    
    const allowedCols = this.allowedColumns[cleanTable];
    if (!allowedCols || !allowedCols.has(cleanColumn)) {
      throw new Error(`Unauthorized column access: ${tableName}.${columnName}`);
    }

    return cleanColumn;
  }

  /**
   * Validate SQL operator
   */
  validateOperator(operator) {
    if (!operator || typeof operator !== 'string') {
      throw new Error('Invalid operator');
    }

    const cleanOp = operator.toUpperCase().trim();
    if (!this.allowedOperators.has(cleanOp)) {
      throw new Error(`Unauthorized operator: ${operator}`);
    }

    return cleanOp;
  }

  /**
   * Build secure SELECT query
   */
  buildSelect(options) {
    const {
      table,
      columns = ['*'],
      where = {},
      orderBy = null,
      limit = null,
      offset = null
    } = options;

    // Validate table
    const validTable = this.validateTable(table);
    
    // Validate columns
    const validColumns = columns.map(col => {
      if (col === '*') return '*';
      return this.validateColumn(validTable, col);
    });

    // Build query parts
    let query = `SELECT ${validColumns.join(', ')} FROM ${validTable}`;
    const params = [];
    let paramIndex = 1;

    // Build WHERE clause
    if (Object.keys(where).length > 0) {
      const whereConditions = [];
      
      for (const [column, condition] of Object.entries(where)) {
        const validColumn = this.validateColumn(validTable, column);
        
        if (typeof condition === 'object' && condition !== null) {
          // Handle complex conditions like { operator: '>', value: 10 }
          const { operator = '=', value } = condition;
          const validOperator = this.validateOperator(operator);
          
          if (validOperator === 'IN' || validOperator === 'NOT IN') {
            if (!Array.isArray(value)) {
              throw new Error(`${validOperator} requires an array value`);
            }
            const placeholders = value.map(() => `$${paramIndex++}`).join(', ');
            whereConditions.push(`${validColumn} ${validOperator} (${placeholders})`);
            params.push(...value);
          } else if (validOperator === 'IS NULL' || validOperator === 'IS NOT NULL') {
            whereConditions.push(`${validColumn} ${validOperator}`);
          } else {
            whereConditions.push(`${validColumn} ${validOperator} $${paramIndex++}`);
            params.push(value);
          }
        } else {
          // Simple equality
          whereConditions.push(`${validColumn} = $${paramIndex++}`);
          params.push(condition);
        }
      }
      
      query += ` WHERE ${whereConditions.join(' AND ')}`;
    }

    // Build ORDER BY clause
    if (orderBy) {
      if (Array.isArray(orderBy)) {
        const orderParts = orderBy.map(order => {
          const { column, direction = 'ASC' } = order;
          const validColumn = this.validateColumn(validTable, column);
          const validDirection = this.allowedOrderDirections.has(direction.toUpperCase()) 
            ? direction.toUpperCase() 
            : 'ASC';
          return `${validColumn} ${validDirection}`;
        });
        query += ` ORDER BY ${orderParts.join(', ')}`;
      } else {
        const { column, direction = 'ASC' } = orderBy;
        const validColumn = this.validateColumn(validTable, column);
        const validDirection = this.allowedOrderDirections.has(direction.toUpperCase()) 
          ? direction.toUpperCase() 
          : 'ASC';
        query += ` ORDER BY ${validColumn} ${validDirection}`;
      }
    }

    // Build LIMIT clause
    if (limit !== null) {
      if (!Number.isInteger(limit) || limit < 1 || limit > 1000) {
        throw new Error('Limit must be an integer between 1 and 1000');
      }
      query += ` LIMIT $${paramIndex++}`;
      params.push(limit);
    }

    // Build OFFSET clause
    if (offset !== null) {
      if (!Number.isInteger(offset) || offset < 0) {
        throw new Error('Offset must be a non-negative integer');
      }
      query += ` OFFSET $${paramIndex++}`;
      params.push(offset);
    }

    return { query, params };
  }

  /**
   * Build secure UPDATE query
   */
  buildUpdate(options) {
    const { table, set = {}, where = {} } = options;

    if (Object.keys(set).length === 0) {
      throw new Error('UPDATE requires at least one field to update');
    }

    if (Object.keys(where).length === 0) {
      throw new Error('UPDATE requires WHERE conditions for security');
    }

    // Validate table
    const validTable = this.validateTable(table);

    const params = [];
    let paramIndex = 1;

    // Build SET clause
    const setClause = [];
    for (const [column, value] of Object.entries(set)) {
      const validColumn = this.validateColumn(validTable, column);
      setClause.push(`${validColumn} = $${paramIndex++}`);
      params.push(value);
    }

    // Build WHERE clause
    const whereClause = [];
    for (const [column, value] of Object.entries(where)) {
      const validColumn = this.validateColumn(validTable, column);
      whereClause.push(`${validColumn} = $${paramIndex++}`);
      params.push(value);
    }

    const query = `UPDATE ${validTable} SET ${setClause.join(', ')} WHERE ${whereClause.join(' AND ')} RETURNING *`;

    return { query, params };
  }

  /**
   * Build secure INSERT query
   */
  buildInsert(options) {
    const { table, data = {}, onConflict = null } = options;

    if (Object.keys(data).length === 0) {
      throw new Error('INSERT requires at least one field');
    }

    // Validate table
    const validTable = this.validateTable(table);

    // Validate columns and build query
    const columns = [];
    const values = [];
    const params = [];
    let paramIndex = 1;

    for (const [column, value] of Object.entries(data)) {
      const validColumn = this.validateColumn(validTable, column);
      columns.push(validColumn);
      values.push(`$${paramIndex++}`);
      params.push(value);
    }

    let query = `INSERT INTO ${validTable} (${columns.join(', ')}) VALUES (${values.join(', ')})`;

    // Handle ON CONFLICT clause
    if (onConflict) {
      if (onConflict.action === 'DO_NOTHING') {
        const conflictColumns = onConflict.columns.map(col => this.validateColumn(validTable, col));
        query += ` ON CONFLICT (${conflictColumns.join(', ')}) DO NOTHING`;
      } else if (onConflict.action === 'DO_UPDATE') {
        const conflictColumns = onConflict.columns.map(col => this.validateColumn(validTable, col));
        const updateColumns = onConflict.update.map(col => {
          const validCol = this.validateColumn(validTable, col);
          return `${validCol} = EXCLUDED.${validCol}`;
        });
        query += ` ON CONFLICT (${conflictColumns.join(', ')}) DO UPDATE SET ${updateColumns.join(', ')}`;
      }
    }

    query += ' RETURNING *';

    return { query, params };
  }

  /**
   * Build secure DELETE query
   */
  buildDelete(options) {
    const { table, where = {} } = options;

    if (Object.keys(where).length === 0) {
      throw new Error('DELETE requires WHERE conditions for security');
    }

    // Validate table
    const validTable = this.validateTable(table);

    const params = [];
    let paramIndex = 1;

    // Build WHERE clause
    const whereClause = [];
    for (const [column, value] of Object.entries(where)) {
      const validColumn = this.validateColumn(validTable, column);
      whereClause.push(`${validColumn} = $${paramIndex++}`);
      params.push(value);
    }

    const query = `DELETE FROM ${validTable} WHERE ${whereClause.join(' AND ')} RETURNING *`;

    return { query, params };
  }

  /**
   * Execute query with automatic logging and monitoring
   */
  async executeSecure(dbConnection, queryBuilder, context = {}) {
    const { query, params } = queryBuilder;
    const startTime = Date.now();

    try {
      // Log query for security monitoring (without sensitive data)
      const logData = {
        query: query.replace(/\$\d+/g, '?'), // Replace params with placeholders
        paramCount: params.length,
        context,
        timestamp: new Date().toISOString()
      };
      
      console.log('🔒 Secure Query:', logData);

      // Execute query
      const result = await dbConnection.query(query, params);
      
      // Log successful execution
      const duration = Date.now() - startTime;
      console.log(`✅ Query executed successfully in ${duration}ms`);
      
      return result;
    } catch (error) {
      // Log failed execution
      const duration = Date.now() - startTime;
      console.error(`❌ Query failed after ${duration}ms:`, error.message);
      
      // Don't expose internal database errors to client
      throw new Error('Database operation failed');
    }
  }
}

module.exports = SecureQueryBuilder;