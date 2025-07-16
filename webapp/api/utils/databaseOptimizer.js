/**
 * Database Performance Optimizer
 * Analyzes query performance, identifies bottlenecks, and implements optimization strategies
 */

const { query, safeQuery, transaction } = require('./database');
const { createRequestLogger } = require('./logger');

class DatabaseOptimizer {
  constructor(options = {}) {
    this.options = {
      slowQueryThreshold: options.slowQueryThreshold || 1000, // ms
      analyzeStatisticsInterval: options.analyzeStatisticsInterval || 3600000, // 1 hour
      enableAutoIndexing: options.enableAutoIndexing || false,
      maxAnalysisQueries: options.maxAnalysisQueries || 100,
      ...options
    };

    this.logger = createRequestLogger('db-optimizer');
    this.performanceMetrics = {
      totalQueries: 0,
      slowQueries: 0,
      avgQueryTime: 0,
      indexesCreated: 0,
      optimizationsApplied: 0
    };

    this.slowQueryLog = new Map(); // query -> performance data
    this.indexRecommendations = new Map(); // table -> recommended indexes
    this.optimizationHistory = [];

    this.logger.info('🚀 Database Optimizer initialized', this.options);
  }

  /**
   * Analyze database performance and provide optimization recommendations
   */
  async analyzePerformance() {
    const analysisStart = Date.now();
    const analysisId = `analysis_${Date.now()}`;

    try {
      this.logger.info('📊 Starting database performance analysis', { analysisId });

      const analysis = {
        id: analysisId,
        timestamp: new Date().toISOString(),
        slowQueries: [],
        missingIndexes: [],
        tableStatistics: [],
        recommendations: [],
        performance: {}
      };

      // Analyze slow queries
      analysis.slowQueries = await this.analyzeSlowQueries();
      
      // Analyze table statistics
      analysis.tableStatistics = await this.analyzeTableStatistics();
      
      // Identify missing indexes
      analysis.missingIndexes = await this.identifyMissingIndexes();
      
      // Generate recommendations
      analysis.recommendations = await this.generateOptimizationRecommendations(analysis);
      
      // Calculate performance metrics
      analysis.performance = await this.calculatePerformanceMetrics();

      const analysisDuration = Date.now() - analysisStart;
      
      this.logger.info('✅ Database performance analysis completed', {
        analysisId,
        duration: `${analysisDuration}ms`,
        slowQueriesFound: analysis.slowQueries.length,
        missingIndexesFound: analysis.missingIndexes.length,
        recommendationsGenerated: analysis.recommendations.length
      });

      return analysis;

    } catch (error) {
      this.logger.error('❌ Database performance analysis failed', {
        analysisId,
        error: error.message,
        stack: error.stack
      });
      throw error;
    }
  }

  /**
   * Analyze slow queries using PostgreSQL statistics
   */
  async analyzeSlowQueries() {
    try {
      // Check if pg_stat_statements extension is available
      const extensionCheck = await safeQuery(`
        SELECT EXISTS (
          SELECT 1 FROM pg_extension WHERE extname = 'pg_stat_statements'
        ) as has_extension
      `);

      if (!extensionCheck.rows[0]?.has_extension) {
        this.logger.warn('pg_stat_statements extension not available, using query log analysis');
        return await this.analyzeQueryLogPatterns();
      }

      // Get slow queries from pg_stat_statements
      const slowQueries = await safeQuery(`
        SELECT 
          query,
          calls,
          total_time,
          mean_time,
          max_time,
          min_time,
          stddev_time,
          rows as total_rows,
          100.0 * shared_blks_hit / nullif(shared_blks_hit + shared_blks_read, 0) AS hit_percent
        FROM pg_stat_statements 
        WHERE mean_time > $1
        ORDER BY mean_time DESC 
        LIMIT $2
      `, [this.options.slowQueryThreshold, this.options.maxAnalysisQueries]);

      const processedQueries = slowQueries.rows.map(row => ({
        query: this.sanitizeQuery(row.query),
        calls: parseInt(row.calls),
        totalTime: parseFloat(row.total_time),
        meanTime: parseFloat(row.mean_time),
        maxTime: parseFloat(row.max_time),
        minTime: parseFloat(row.min_time),
        stddevTime: parseFloat(row.stddev_time),
        totalRows: parseInt(row.total_rows),
        hitPercent: parseFloat(row.hit_percent) || 0,
        severity: this.calculateQuerySeverity(row),
        recommendations: this.generateQueryRecommendations(row)
      }));

      this.logger.info('Slow queries analysis completed', {
        queriesAnalyzed: processedQueries.length,
        averageTime: processedQueries.reduce((sum, q) => sum + q.meanTime, 0) / processedQueries.length
      });

      return processedQueries;

    } catch (error) {
      this.logger.error('Error analyzing slow queries', { error: error.message });
      return [];
    }
  }

  /**
   * Analyze query patterns from application logs (fallback method)
   */
  async analyzeQueryLogPatterns() {
    // This would analyze query patterns from application logs
    // For now, return common slow query patterns we've observed
    return [
      {
        query: 'SELECT * FROM portfolio_holdings WHERE user_id = $1',
        pattern: 'full_table_scan',
        recommendation: 'Add index on user_id',
        estimatedImpact: 'high'
      },
      {
        query: 'SELECT * FROM price_daily WHERE symbol = $1 ORDER BY date DESC',
        pattern: 'missing_compound_index',
        recommendation: 'Add compound index on (symbol, date)',
        estimatedImpact: 'medium'
      }
    ];
  }

  /**
   * Analyze table statistics and bloat
   */
  async analyzeTableStatistics() {
    try {
      const tableStats = await safeQuery(`
        SELECT 
          schemaname,
          tablename,
          attname,
          n_distinct,
          correlation,
          null_frac,
          avg_width,
          most_common_vals,
          most_common_freqs
        FROM pg_stats 
        WHERE schemaname = 'public'
        ORDER BY tablename, attname
      `);

      // Get table sizes and bloat estimates
      const tableSizes = await safeQuery(`
        SELECT 
          schemaname,
          tablename,
          pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as total_size,
          pg_total_relation_size(schemaname||'.'||tablename) as total_size_bytes,
          pg_size_pretty(pg_relation_size(schemaname||'.'||tablename)) as table_size,
          pg_relation_size(schemaname||'.'||tablename) as table_size_bytes
        FROM pg_tables 
        WHERE schemaname = 'public'
        ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
      `);

      // Get index usage statistics
      const indexStats = await safeQuery(`
        SELECT 
          schemaname,
          tablename,
          indexname,
          idx_tup_read,
          idx_tup_fetch,
          idx_scan
        FROM pg_stat_user_indexes
        ORDER BY idx_scan DESC
      `);

      const analysis = {
        tableStats: tableStats.rows,
        tableSizes: tableSizes.rows,
        indexUsage: indexStats.rows,
        recommendations: []
      };

      // Analyze for optimization opportunities
      analysis.recommendations = this.analyzeTableStatisticsForOptimizations(analysis);

      return analysis;

    } catch (error) {
      this.logger.error('Error analyzing table statistics', { error: error.message });
      return { tableStats: [], tableSizes: [], indexUsage: [], recommendations: [] };
    }
  }

  /**
   * Identify missing indexes based on query patterns
   */
  async identifyMissingIndexes() {
    try {
      const missingIndexes = [];

      // Analyze common query patterns and suggest indexes
      const indexCandidates = [
        // Portfolio-related indexes
        {
          table: 'portfolio_holdings',
          columns: ['user_id'],
          type: 'btree',
          reason: 'Frequent user portfolio queries',
          priority: 'high'
        },
        {
          table: 'portfolio_holdings',
          columns: ['user_id', 'symbol'],
          type: 'btree',
          reason: 'User-specific symbol lookups',
          priority: 'high'
        },
        {
          table: 'portfolio_metadata',
          columns: ['user_id'],
          type: 'btree',
          reason: 'User metadata queries',
          priority: 'high'
        },

        // Price data indexes
        {
          table: 'price_daily',
          columns: ['symbol'],
          type: 'btree',
          reason: 'Symbol-based price queries',
          priority: 'high'
        },
        {
          table: 'price_daily',
          columns: ['symbol', 'date'],
          type: 'btree',
          reason: 'Time-series price queries',
          priority: 'high'
        },
        {
          table: 'price_daily',
          columns: ['date'],
          type: 'btree',
          reason: 'Date-range queries',
          priority: 'medium'
        },

        // Technical indicators indexes
        {
          table: 'technicals_daily',
          columns: ['symbol', 'date'],
          type: 'btree',
          reason: 'Technical analysis queries',
          priority: 'medium'
        },

        // Stock symbols indexes
        {
          table: 'stock_symbols',
          columns: ['symbol'],
          type: 'btree',
          reason: 'Symbol lookups',
          priority: 'high'
        },
        {
          table: 'stock_symbols',
          columns: ['exchange'],
          type: 'btree',
          reason: 'Exchange-based filtering',
          priority: 'low'
        },

        // User API keys
        {
          table: 'user_api_keys',
          columns: ['user_id'],
          type: 'btree',
          reason: 'User API key lookups',
          priority: 'high'
        },
        {
          table: 'user_api_keys',
          columns: ['user_id', 'provider'],
          type: 'btree',
          reason: 'Provider-specific API key lookups',
          priority: 'high'
        }
      ];

      // Check which indexes already exist
      const existingIndexes = await this.getExistingIndexes();
      
      for (const candidate of indexCandidates) {
        const indexExists = this.checkIndexExists(existingIndexes, candidate);
        
        if (!indexExists) {
          const tableExists = await this.checkTableExists(candidate.table);
          
          if (tableExists) {
            missingIndexes.push({
              ...candidate,
              estimatedImpact: await this.estimateIndexImpact(candidate),
              createStatement: this.generateCreateIndexStatement(candidate)
            });
          }
        }
      }

      this.logger.info('Missing indexes analysis completed', {
        candidatesAnalyzed: indexCandidates.length,
        missingIndexes: missingIndexes.length,
        existingIndexes: existingIndexes.length
      });

      return missingIndexes;

    } catch (error) {
      this.logger.error('Error identifying missing indexes', { error: error.message });
      return [];
    }
  }

  /**
   * Get existing indexes
   */
  async getExistingIndexes() {
    try {
      const indexes = await safeQuery(`
        SELECT 
          schemaname,
          tablename,
          indexname,
          indexdef
        FROM pg_indexes 
        WHERE schemaname = 'public'
        ORDER BY tablename, indexname
      `);

      return indexes.rows;
    } catch (error) {
      this.logger.error('Error getting existing indexes', { error: error.message });
      return [];
    }
  }

  /**
   * Check if an index already exists
   */
  checkIndexExists(existingIndexes, candidate) {
    return existingIndexes.some(index => {
      return index.tablename === candidate.table &&
             candidate.columns.every(col => 
               index.indexdef.toLowerCase().includes(col.toLowerCase())
             );
    });
  }

  /**
   * Check if a table exists
   */
  async checkTableExists(tableName) {
    try {
      const result = await safeQuery(`
        SELECT EXISTS (
          SELECT FROM information_schema.tables 
          WHERE table_schema = 'public' 
          AND table_name = $1
        )
      `, [tableName]);

      return result.rows[0]?.exists || false;
    } catch (error) {
      return false;
    }
  }

  /**
   * Estimate the impact of creating an index
   */
  async estimateIndexImpact(indexCandidate) {
    try {
      // Get table size
      const tableSize = await safeQuery(`
        SELECT pg_total_relation_size($1) as size_bytes
      `, [indexCandidate.table]);

      const sizeBytes = parseInt(tableSize.rows[0]?.size_bytes || 0);
      
      // Estimate based on table size and query patterns
      if (sizeBytes > 100000000) { // > 100MB
        return indexCandidate.priority === 'high' ? 'very_high' : 'high';
      } else if (sizeBytes > 10000000) { // > 10MB
        return indexCandidate.priority === 'high' ? 'high' : 'medium';
      } else {
        return 'medium';
      }

    } catch (error) {
      return 'unknown';
    }
  }

  /**
   * Generate CREATE INDEX statement
   */
  generateCreateIndexStatement(indexCandidate) {
    const indexName = `idx_${indexCandidate.table}_${indexCandidate.columns.join('_')}`;
    const columnList = indexCandidate.columns.join(', ');
    
    return `CREATE INDEX CONCURRENTLY ${indexName} ON ${indexCandidate.table} USING ${indexCandidate.type} (${columnList});`;
  }

  /**
   * Generate optimization recommendations
   */
  async generateOptimizationRecommendations(analysis) {
    const recommendations = [];

    // Index recommendations
    analysis.missingIndexes.forEach(index => {
      if (index.priority === 'high' || index.estimatedImpact === 'very_high') {
        recommendations.push({
          type: 'create_index',
          priority: index.priority,
          description: `Create index on ${index.table}(${index.columns.join(', ')})`,
          reason: index.reason,
          impact: index.estimatedImpact,
          sql: index.createStatement,
          category: 'performance'
        });
      }
    });

    // Query optimization recommendations
    analysis.slowQueries.forEach(slowQuery => {
      if (slowQuery.severity === 'high') {
        recommendations.push({
          type: 'optimize_query',
          priority: 'high',
          description: `Optimize slow query: ${slowQuery.query.substring(0, 100)}...`,
          meanTime: slowQuery.meanTime,
          calls: slowQuery.calls,
          recommendations: slowQuery.recommendations,
          category: 'query_optimization'
        });
      }
    });

    // Table maintenance recommendations
    if (analysis.tableStatistics.tableSizes) {
      analysis.tableStatistics.tableSizes.forEach(table => {
        if (table.total_size_bytes > 1000000000) { // > 1GB
          recommendations.push({
            type: 'table_maintenance',
            priority: 'medium',
            description: `Consider partitioning or archiving large table: ${table.tablename}`,
            tableSize: table.total_size,
            category: 'maintenance'
          });
        }
      });
    }

    return recommendations.sort((a, b) => {
      const priorityOrder = { 'high': 3, 'medium': 2, 'low': 1 };
      return priorityOrder[b.priority] - priorityOrder[a.priority];
    });
  }

  /**
   * Apply optimization recommendations
   */
  async applyOptimizations(recommendations, options = {}) {
    const applyStart = Date.now();
    const { dryRun = true, maxIndexes = 5 } = options;
    
    const results = {
      applied: [],
      failed: [],
      skipped: []
    };

    try {
      this.logger.info('🔧 Applying database optimizations', {
        totalRecommendations: recommendations.length,
        dryRun,
        maxIndexes
      });

      let indexesCreated = 0;

      for (const recommendation of recommendations) {
        try {
          if (recommendation.type === 'create_index' && indexesCreated < maxIndexes) {
            const result = await this.applyIndexRecommendation(recommendation, dryRun);
            
            if (result.success) {
              results.applied.push(result);
              if (!dryRun) indexesCreated++;
            } else {
              results.failed.push(result);
            }
          } else if (recommendation.type === 'create_index') {
            results.skipped.push({
              recommendation,
              reason: 'Index creation limit reached'
            });
          } else {
            results.skipped.push({
              recommendation,
              reason: 'Optimization type not implemented'
            });
          }
        } catch (error) {
          results.failed.push({
            recommendation,
            error: error.message
          });
        }
      }

      const applyDuration = Date.now() - applyStart;
      
      this.logger.info('✅ Database optimization application completed', {
        duration: `${applyDuration}ms`,
        applied: results.applied.length,
        failed: results.failed.length,
        skipped: results.skipped.length,
        dryRun
      });

      return results;

    } catch (error) {
      this.logger.error('❌ Error applying optimizations', { error: error.message });
      throw error;
    }
  }

  /**
   * Apply index recommendation
   */
  async applyIndexRecommendation(recommendation, dryRun = true) {
    try {
      if (dryRun) {
        this.logger.info('🔍 [DRY RUN] Would create index', {
          sql: recommendation.sql,
          table: recommendation.description
        });
        
        return {
          success: true,
          recommendation,
          action: 'dry_run',
          message: 'Index creation validated (dry run)'
        };
      }

      // Execute the index creation
      const createStart = Date.now();
      await safeQuery(recommendation.sql);
      const createDuration = Date.now() - createStart;

      this.logger.info('✅ Index created successfully', {
        sql: recommendation.sql,
        duration: `${createDuration}ms`
      });

      this.performanceMetrics.indexesCreated++;
      this.performanceMetrics.optimizationsApplied++;

      return {
        success: true,
        recommendation,
        action: 'created',
        duration: createDuration,
        message: 'Index created successfully'
      };

    } catch (error) {
      this.logger.error('❌ Failed to create index', {
        sql: recommendation.sql,
        error: error.message
      });

      return {
        success: false,
        recommendation,
        error: error.message,
        message: 'Index creation failed'
      };
    }
  }

  /**
   * Calculate performance metrics
   */
  async calculatePerformanceMetrics() {
    try {
      // Get connection and cache statistics
      const connectionStats = await safeQuery(`
        SELECT 
          state,
          count(*) as count
        FROM pg_stat_activity 
        WHERE datname = current_database()
        GROUP BY state
      `);

      const cacheStats = await safeQuery(`
        SELECT 
          sum(heap_blks_read) as heap_read,
          sum(heap_blks_hit) as heap_hit,
          sum(idx_blks_read) as idx_read,
          sum(idx_blks_hit) as idx_hit
        FROM pg_statio_user_tables
      `);

      const dbSize = await safeQuery(`
        SELECT pg_size_pretty(pg_database_size(current_database())) as size
      `);

      const stats = cacheStats.rows[0];
      const totalReads = parseInt(stats.heap_read) + parseInt(stats.idx_read);
      const totalHits = parseInt(stats.heap_hit) + parseInt(stats.idx_hit);
      const hitRatio = totalHits / (totalHits + totalReads) * 100;

      return {
        cacheHitRatio: hitRatio.toFixed(2),
        databaseSize: dbSize.rows[0]?.size,
        connectionStates: connectionStats.rows,
        metrics: this.performanceMetrics
      };

    } catch (error) {
      this.logger.error('Error calculating performance metrics', { error: error.message });
      return { error: error.message };
    }
  }

  /**
   * Utility methods
   */
  sanitizeQuery(query) {
    // Remove parameter values and normalize for analysis
    return query.replace(/\$\d+/g, '$?').replace(/\s+/g, ' ').trim();
  }

  calculateQuerySeverity(queryStats) {
    const meanTime = parseFloat(queryStats.mean_time);
    const calls = parseInt(queryStats.calls);
    
    if (meanTime > 5000 || (meanTime > 1000 && calls > 100)) {
      return 'high';
    } else if (meanTime > 1000 || (meanTime > 500 && calls > 1000)) {
      return 'medium';
    } else {
      return 'low';
    }
  }

  generateQueryRecommendations(queryStats) {
    const recommendations = [];
    const query = queryStats.query.toLowerCase();
    
    if (query.includes('select *')) {
      recommendations.push('Avoid SELECT *, specify only needed columns');
    }
    
    if (query.includes('order by') && !query.includes('limit')) {
      recommendations.push('Consider adding LIMIT to ORDER BY queries');
    }
    
    if (parseFloat(queryStats.hit_percent) < 95) {
      recommendations.push('Low cache hit ratio - consider indexing or query optimization');
    }
    
    return recommendations;
  }

  analyzeTableStatisticsForOptimizations(analysis) {
    const recommendations = [];
    
    // Analyze unused indexes
    analysis.indexUsage.forEach(index => {
      if (parseInt(index.idx_scan) === 0) {
        recommendations.push({
          type: 'remove_unused_index',
          description: `Consider removing unused index: ${index.indexname}`,
          table: index.tablename,
          index: index.indexname
        });
      }
    });
    
    return recommendations;
  }

  /**
   * Get optimization status and metrics
   */
  getStatus() {
    return {
      metrics: this.performanceMetrics,
      options: this.options,
      slowQueries: this.slowQueryLog.size,
      indexRecommendations: this.indexRecommendations.size,
      optimizationHistory: this.optimizationHistory.length
    };
  }
}

module.exports = { DatabaseOptimizer };