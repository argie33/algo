// Portfolio Data Refresh Service
// Integrates API key system with data loaders to refresh portfolio-relevant data

const { query } = require('./database');
const AWS = require('aws-sdk');

class PortfolioDataRefreshService {
  constructor() {
    this.refreshInProgress = new Set();
    // Initialize AWS services for triggering data loaders
    this.ecs = new AWS.ECS({ region: process.env.AWS_REGION || 'us-east-1' });
    this.lambda = new AWS.Lambda({ region: process.env.AWS_REGION || 'us-east-1' });
  }

  /**
   * Trigger data refresh for portfolio-relevant symbols when user adds API keys
   * @param {string} userId - User ID
   * @param {string} provider - Broker provider (alpaca, td_ameritrade, etc.)
   * @param {Array} symbols - Array of symbols from user's portfolio
   */
  async triggerPortfolioDataRefresh(userId, provider, symbols = []) {
    const refreshId = `${userId}-${provider}`;
    
    if (this.refreshInProgress.has(refreshId)) {
      console.log(`⏳ Portfolio data refresh already in progress for ${userId}/${provider}`);
      return { status: 'in_progress', message: 'Refresh already running' };
    }

    try {
      this.refreshInProgress.add(refreshId);
      console.log(`🔄 Starting portfolio data refresh for user ${userId} (${provider})`);

      // 1. Get user's portfolio symbols if not provided
      if (symbols.length === 0) {
        symbols = await this.getUserPortfolioSymbols(userId, provider);
      }

      if (symbols.length === 0) {
        console.log(`ℹ️ No portfolio symbols found for ${userId}/${provider}`);
        return { status: 'no_symbols', message: 'No portfolio symbols to refresh' };
      }

      console.log(`📊 Refreshing data for ${symbols.length} portfolio symbols: ${symbols.slice(0, 5).join(', ')}${symbols.length > 5 ? '...' : ''}`);

      // 2. Trigger priority data loading for these symbols
      const refreshResults = await this.refreshSymbolData(symbols, userId);

      // 3. Update portfolio refresh timestamp
      await this.updatePortfolioRefreshTimestamp(userId, provider);

      console.log(`✅ Portfolio data refresh completed for ${userId}/${provider}`);
      return {
        status: 'completed',
        symbolsRefreshed: symbols.length,
        results: refreshResults,
        timestamp: new Date().toISOString()
      };

    } catch (error) {
      console.error(`❌ Portfolio data refresh failed for ${userId}/${provider}:`, error);
      return {
        status: 'error',
        error: error.message,
        timestamp: new Date().toISOString()
      };
    } finally {
      this.refreshInProgress.delete(refreshId);
    }
  }

  /**
   * Get symbols from user's portfolio holdings
   */
  async getUserPortfolioSymbols(userId, provider) {
    try {
      const result = await query(`
        SELECT DISTINCT symbol 
        FROM portfolio_holdings 
        WHERE user_id = $1 
        AND symbol IS NOT NULL 
        AND symbol != ''
        ORDER BY symbol
      `, [userId]);

      return result.rows.map(row => row.symbol);
    } catch (error) {
      console.error('Error fetching user portfolio symbols:', error);
      return [];
    }
  }

  /**
   * Refresh data for specific symbols by triggering ECS tasks
   */
  async refreshSymbolData(symbols, userId) {
    const results = {
      triggered: [],
      failed: [],
      cached: []
    };

    try {
      // Check which symbols need refresh (haven't been updated recently)
      const symbolsNeedingRefresh = await this.getSymbolsNeedingRefresh(symbols);
      
      if (symbolsNeedingRefresh.length === 0) {
        console.log('📊 All portfolio symbols have recent data');
        results.cached = symbols;
        return results;
      }

      console.log(`🔄 ${symbolsNeedingRefresh.length} symbols need data refresh`);

      // Trigger priority data loading for these symbols
      await this.triggerTechnicalDataLoaders(symbolsNeedingRefresh, userId);

      results.triggered = symbolsNeedingRefresh;
      
      // Store refresh request for processing by scheduled tasks
      await this.storeRefreshRequest(symbolsNeedingRefresh, userId);

      return results;

    } catch (error) {
      console.error('Error refreshing symbol data:', error);
      results.failed = symbols;
      return results;
    }
  }

  /**
   * Check which symbols need fresh data
   */
  async getSymbolsNeedingRefresh(symbols) {
    if (symbols.length === 0) return [];

    try {
      // Check when symbols were last updated
      const placeholders = symbols.map((_, i) => `$${i + 1}`).join(',');
      const result = await query(`
        SELECT symbol 
        FROM price_daily 
        WHERE symbol IN (${placeholders})
        AND date >= CURRENT_DATE - INTERVAL '1 day'
        GROUP BY symbol
      `, symbols);

      const recentSymbols = result.rows.map(row => row.symbol);
      return symbols.filter(symbol => !recentSymbols.includes(symbol));

    } catch (error) {
      console.error('Error checking symbol freshness:', error);
      // If we can't check, assume all need refresh
      return symbols;
    }
  }

  /**
   * Store refresh request for background processing
   */
  async storeRefreshRequest(symbols, userId) {
    try {
      await query(`
        INSERT INTO portfolio_data_refresh_requests 
        (user_id, symbols, status, created_at)
        VALUES ($1, $2, 'pending', NOW())
        ON CONFLICT (user_id) DO UPDATE SET
          symbols = EXCLUDED.symbols,
          status = 'pending',
          created_at = NOW()
      `, [userId, JSON.stringify(symbols)]);

      console.log(`💾 Stored refresh request for ${symbols.length} symbols`);
    } catch (error) {
      // Table might not exist yet - that's okay
      console.log('⚠️ Could not store refresh request (table may not exist):', error.message);
    }
  }

  /**
   * Update portfolio refresh timestamp
   */
  async updatePortfolioRefreshTimestamp(userId, provider) {
    try {
      await query(`
        UPDATE portfolio_metadata 
        SET data_last_refreshed = NOW(), updated_at = NOW()
        WHERE user_id = $1
      `, [userId]);
    } catch (error) {
      console.log('⚠️ Could not update refresh timestamp:', error.message);
    }
  }

  /**
   * Get refresh status for a user
   */
  async getRefreshStatus(userId) {
    try {
      const result = await query(`
        SELECT 
          symbols,
          status,
          created_at,
          completed_at
        FROM portfolio_data_refresh_requests
        WHERE user_id = $1
        ORDER BY created_at DESC
        LIMIT 1
      `, [userId]);

      if (result.rows.length === 0) {
        return { status: 'none', message: 'No refresh requests found' };
      }

      const request = result.rows[0];
      return {
        status: request.status,
        symbols: JSON.parse(request.symbols || '[]'),
        requested: request.created_at,
        completed: request.completed_at,
        inProgress: this.refreshInProgress.has(`${userId}-*`)
      };

    } catch (error) {
      console.error('Error getting refresh status:', error);
      return { status: 'error', error: error.message };
    }
  }

  /**
   * Trigger technical data loaders for specific symbols
   */
  async triggerTechnicalDataLoaders(symbols, userId) {
    try {
      console.log(`🚀 Triggering technical data loaders for ${symbols.length} symbols`);
      
      // Method 1: Try ECS task if cluster exists
      const ecsTriggered = await this.triggerECSDataLoaders(symbols);
      
      if (!ecsTriggered) {
        // Method 2: Fall back to Lambda invocation for smaller symbol sets
        await this.triggerLambdaDataLoaders(symbols);
      }
      
      console.log(`✅ Successfully triggered data loaders for symbols: ${symbols.slice(0, 5).join(', ')}${symbols.length > 5 ? '...' : ''}`);
      
    } catch (error) {
      console.warn(`⚠️ Failed to trigger technical data loaders: ${error.message}`);
      // Don't fail the whole process if data loading fails
    }
  }

  /**
   * Trigger ECS tasks for technical data loading
   */
  async triggerECSDataLoaders(symbols) {
    try {
      // Check if ECS cluster exists (optional - for production deployments)
      const clusterName = process.env.ECS_CLUSTER_NAME || 'stocks-data-processing';
      
      // For small symbol sets, use environment variable approach
      const symbolList = symbols.join(',');
      
      const taskParams = {
        cluster: clusterName,
        taskDefinition: 'loadtechnicalsdaily-task', // Task definition name
        launchType: 'FARGATE',
        networkConfiguration: {
          awsvpcConfiguration: {
            subnets: [
              process.env.SUBNET_ID_1 || 'subnet-12345', // Would be from CloudFormation
              process.env.SUBNET_ID_2 || 'subnet-67890'
            ],
            securityGroups: [process.env.SECURITY_GROUP_ID || 'sg-12345'],
            assignPublicIp: 'ENABLED'
          }
        },
        overrides: {
          containerOverrides: [{
            name: 'loadtechnicalsdaily',
            environment: [
              { name: 'PRIORITY_SYMBOLS', value: symbolList },
              { name: 'TRIGGER_SOURCE', value: 'portfolio_refresh' }
            ]
          }]
        }
      };

      const result = await this.ecs.runTask(taskParams).promise();
      console.log(`🎯 ECS task triggered for technical data loading: ${result.tasks[0]?.taskArn}`);
      return true;
      
    } catch (error) {
      console.log(`⚠️ ECS task triggering failed: ${error.message}`);
      return false; // Fall back to Lambda approach
    }
  }

  /**
   * Trigger Lambda functions for technical data loading (fallback)
   */
  async triggerLambdaDataLoaders(symbols) {
    try {
      // For smaller symbol sets, can invoke a Lambda that processes them
      const payload = {
        symbols: symbols,
        triggerSource: 'portfolio_refresh',
        priority: true
      };

      const params = {
        FunctionName: 'loadtechnicalsdaily-lambda', // Lambda function name
        InvocationType: 'Event', // Async invocation
        Payload: JSON.stringify(payload)
      };

      const result = await this.lambda.invoke(params).promise();
      console.log(`🎯 Lambda triggered for technical data loading: ${result.StatusCode}`);
      
    } catch (error) {
      console.warn(`⚠️ Lambda triggering failed: ${error.message}`);
      // This is a fallback, so just log the warning
    }
  }

  /**
   * Get status of data loading jobs for a user
   */
  async getDataLoadingStatus(userId) {
    try {
      // Check recent ECS tasks for this user's symbols
      const recentTasks = await this.getRecentECSTasks();
      
      // Check refresh requests status
      const refreshStatus = await this.getRefreshStatus(userId);
      
      return {
        ecs_tasks: recentTasks,
        refresh_requests: refreshStatus,
        timestamp: new Date().toISOString()
      };
      
    } catch (error) {
      console.error('Error getting data loading status:', error);
      return { status: 'error', error: error.message };
    }
  }

  /**
   * Get recent ECS tasks related to technical data loading
   */
  async getRecentECSTasks() {
    try {
      const clusterName = process.env.ECS_CLUSTER_NAME || 'stocks-data-processing';
      
      const params = {
        cluster: clusterName,
        family: 'loadtechnicalsdaily-task',
        maxResults: 10,
        sort: 'CREATED_AT',
        order: 'DESC'
      };

      const result = await this.ecs.listTasks(params).promise();
      
      if (result.taskArns.length > 0) {
        const describeTasks = await this.ecs.describeTasks({
          cluster: clusterName,
          tasks: result.taskArns
        }).promise();
        
        return describeTasks.tasks.map(task => ({
          taskArn: task.taskArn,
          lastStatus: task.lastStatus,
          desiredStatus: task.desiredStatus,
          createdAt: task.createdAt,
          startedAt: task.startedAt,
          stoppedAt: task.stoppedAt
        }));
      }
      
      return [];
      
    } catch (error) {
      console.warn(`⚠️ Could not fetch ECS task status: ${error.message}`);
      return [];
    }
  }

  /**
   * Check if data refresh is needed for user's portfolio
   */
  async isRefreshNeeded(userId) {
    try {
      // Check when portfolio data was last refreshed
      const result = await query(`
        SELECT data_last_refreshed 
        FROM portfolio_metadata 
        WHERE user_id = $1
        ORDER BY data_last_refreshed DESC
        LIMIT 1
      `, [userId]);

      if (result.rows.length === 0) {
        return true; // No metadata = needs refresh
      }

      const lastRefresh = result.rows[0].data_last_refreshed;
      if (!lastRefresh) {
        return true; // Never refreshed
      }

      // Refresh needed if data is older than 4 hours
      const hoursSinceRefresh = (new Date() - new Date(lastRefresh)) / (1000 * 60 * 60);
      return hoursSinceRefresh > 4;

    } catch (error) {
      console.error('Error checking refresh need:', error);
      return true; // On error, assume refresh needed
    }
  }
}

// Singleton instance
const portfolioDataRefreshService = new PortfolioDataRefreshService();

module.exports = portfolioDataRefreshService;