const express = require('express');
const { query } = require('../utils/database');
const { authenticateToken } = require('../middleware/auth');

const router = express.Router();

// Apply authentication middleware to all portfolio routes
router.use(authenticateToken);

// Portfolio analytics endpoint for advanced metrics
router.get('/analytics', async (req, res) => {
  const userId = req.user.sub; // Use authenticated user's ID
  const { timeframe = '1y' } = req.query;
  
  console.log(`Portfolio analytics endpoint called for authenticated user: ${userId}, timeframe: ${timeframe}`);
  
  try {
    // Get portfolio holdings
    const holdingsQuery = `
      SELECT 
        symbol,
        quantity,
        market_value,
        cost_basis,
        pnl,
        pnl_percent,
        weight,
        sector,
        last_updated
      FROM portfolio_holdings
      WHERE user_id = $1
      ORDER BY market_value DESC
    `;
    
    const holdingsResult = await query(holdingsQuery, [userId]);
    const holdings = holdingsResult.rows;
    
    // Get portfolio performance history
    const performanceQuery = `
      SELECT 
        date,
        total_value,
        daily_pnl,
        daily_pnl_percent,
        total_pnl,
        total_pnl_percent,
        benchmark_return,
        alpha,
        beta,
        sharpe_ratio,
        max_drawdown,
        volatility
      FROM portfolio_performance
      WHERE user_id = $1
      AND date >= NOW() - INTERVAL $2
      ORDER BY date DESC
    `;
    
    const timeframeMap = {
      '1w': '7 days',
      '1m': '30 days',
      '3m': '90 days',
      '6m': '180 days',
      '1y': '365 days',
      '2y': '730 days'
    };
    
    const performanceResult = await query(performanceQuery, [userId, timeframeMap[timeframe] || '365 days']);
    const performance = performanceResult.rows;
    
    // Calculate advanced analytics
    const analytics = calculateAdvancedAnalytics(holdings, performance);
    
    res.json({
      success: true,
      data: {
        holdings: holdings,
        performance: performance,
        analytics: analytics,
        summary: {
          totalValue: holdings.reduce((sum, h) => sum + parseFloat(h.market_value || 0), 0),
          totalPnL: holdings.reduce((sum, h) => sum + parseFloat(h.pnl || 0), 0),
          numPositions: holdings.length,
          topSector: getTopSector(holdings),
          concentration: calculateConcentration(holdings),
          riskScore: analytics.riskScore
        }
      },
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Error fetching portfolio analytics:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch portfolio analytics',
      details: error.message
    });
  }
});

// Portfolio risk analysis endpoint
router.get('/risk-analysis', async (req, res) => {
  const userId = req.user.sub; // Use authenticated user's ID
  
  console.log(`Portfolio risk analysis endpoint called for user: ${userId}`);
  
  try {
    // Get current holdings for risk analysis
    const holdingsQuery = `
      SELECT 
        symbol,
        quantity,
        market_value,
        weight,
        sector,
        beta,
        volatility
      FROM portfolio_holdings
      WHERE user_id = $1
      ORDER BY market_value DESC
    `;
    
    const holdingsResult = await query(holdingsQuery, [userId]);
    const holdings = holdingsResult.rows;
    
    // Calculate risk metrics
    const riskAnalysis = calculateRiskMetrics(holdings);
    
    res.json({
      success: true,
      data: {
        portfolioBeta: riskAnalysis.portfolioBeta,
        portfolioVolatility: riskAnalysis.portfolioVolatility,
        var95: riskAnalysis.var95,
        var99: riskAnalysis.var99,
        sectorConcentration: riskAnalysis.sectorConcentration,
        positionConcentration: riskAnalysis.positionConcentration,
        correlationMatrix: riskAnalysis.correlationMatrix,
        riskScore: riskAnalysis.riskScore,
        recommendations: generateRiskRecommendations(riskAnalysis)
      },
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Error performing portfolio risk analysis:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to perform portfolio risk analysis',
      details: error.message
    });
  }
});

// Portfolio optimization suggestions
router.get('/optimization', async (req, res) => {
  const userId = req.user.sub; // Use authenticated user's ID
  
  console.log(`Portfolio optimization endpoint called for authenticated user: ${userId}`);
  
  try {
    // Get current portfolio
    const holdingsQuery = `
      SELECT 
        symbol,
        quantity,
        market_value,
        weight,
        sector,
        expected_return,
        volatility,
        beta
      FROM portfolio_holdings
      WHERE user_id = $1
    `;
    
    const holdingsResult = await query(holdingsQuery, [userId]);
    const holdings = holdingsResult.rows;
    
    // Generate optimization suggestions
    const optimizations = generateOptimizationSuggestions(holdings);
    
    res.json({
      success: true,
      data: {
        currentAllocation: calculateCurrentAllocation(holdings),
        suggestedAllocation: optimizations.suggestedAllocation,
        rebalanceNeeded: optimizations.rebalanceNeeded,
        expectedImprovement: optimizations.expectedImprovement,
        actions: optimizations.actions,
        riskReduction: optimizations.riskReduction,
        diversificationScore: optimizations.diversificationScore
      },
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Error generating portfolio optimization:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to generate portfolio optimization',
      details: error.message
    });
  }
});

// Helper functions for calculations
function calculateAdvancedAnalytics(holdings, performance) {
  const totalValue = holdings.reduce((sum, h) => sum + parseFloat(h.market_value || 0), 0);
  
  // Calculate Sharpe ratio
  const returns = performance.slice(0, 252).map(p => parseFloat(p.daily_pnl_percent || 0));
  const avgReturn = returns.reduce((sum, r) => sum + r, 0) / returns.length;
  const volatility = Math.sqrt(returns.reduce((sum, r) => sum + Math.pow(r - avgReturn, 2), 0) / returns.length);
  const sharpeRatio = volatility > 0 ? (avgReturn * 252) / (volatility * Math.sqrt(252)) : 0;
  
  // Calculate max drawdown
  let maxDrawdown = 0;
  let peak = 0;
  performance.forEach(p => {
    const value = parseFloat(p.total_value || 0);
    if (value > peak) peak = value;
    const drawdown = (peak - value) / peak;
    if (drawdown > maxDrawdown) maxDrawdown = drawdown;
  });
  
  // Calculate alpha and beta
  const benchmarkReturns = performance.slice(0, 252).map(p => parseFloat(p.benchmark_return || 0));
  const { alpha, beta } = calculateAlphaBeta(returns, benchmarkReturns);
  
  // Risk score (1-10, 10 being highest risk)
  const riskScore = Math.min(10, Math.max(1, 
    (volatility * 100 * 2) + 
    (maxDrawdown * 100 * 0.5) + 
    (Math.abs(beta - 1) * 2)
  ));
  
  return {
    sharpeRatio: sharpeRatio,
    maxDrawdown: maxDrawdown,
    alpha: alpha,
    beta: beta,
    volatility: volatility,
    riskScore: Math.round(riskScore * 10) / 10,
    calmarRatio: avgReturn * 252 / (maxDrawdown || 0.01),
    sortinoRatio: calculateSortinoRatio(returns),
    informationRatio: calculateInformationRatio(returns, benchmarkReturns)
  };
}

function calculateRiskMetrics(holdings) {
  const totalValue = holdings.reduce((sum, h) => sum + parseFloat(h.market_value || 0), 0);
  
  // Portfolio beta (weighted average)
  const portfolioBeta = holdings.reduce((sum, h) => {
    const weight = parseFloat(h.market_value || 0) / totalValue;
    const beta = parseFloat(h.beta || 1);
    return sum + (weight * beta);
  }, 0);
  
  // Portfolio volatility (simplified)
  const portfolioVolatility = holdings.reduce((sum, h) => {
    const weight = parseFloat(h.market_value || 0) / totalValue;
    const volatility = parseFloat(h.volatility || 0.2);
    return sum + (weight * volatility);
  }, 0);
  
  // VaR calculations (simplified)
  const var95 = portfolioVolatility * 1.645; // 95% confidence
  const var99 = portfolioVolatility * 2.326; // 99% confidence
  
  // Sector concentration
  const sectorMap = {};
  holdings.forEach(h => {
    const sector = h.sector || 'Other';
    const value = parseFloat(h.market_value || 0);
    sectorMap[sector] = (sectorMap[sector] || 0) + value;
  });
  
  const sectorConcentration = Object.values(sectorMap).map(value => value / totalValue);
  
  // Position concentration (top 10 positions)
  const sortedHoldings = holdings.sort((a, b) => parseFloat(b.market_value || 0) - parseFloat(a.market_value || 0));
  const top10Concentration = sortedHoldings.slice(0, 10).reduce((sum, h) => sum + parseFloat(h.market_value || 0), 0) / totalValue;
  
  return {
    portfolioBeta,
    portfolioVolatility,
    var95,
    var99,
    sectorConcentration,
    positionConcentration: top10Concentration,
    riskScore: Math.round((portfolioBeta + portfolioVolatility * 5 + top10Concentration * 2) * 10) / 10
  };
}

function generateOptimizationSuggestions(holdings) {
  const totalValue = holdings.reduce((sum, h) => sum + parseFloat(h.market_value || 0), 0);
  
  // Current allocation
  const currentAllocation = holdings.map(h => ({
    symbol: h.symbol,
    weight: parseFloat(h.market_value || 0) / totalValue,
    sector: h.sector
  }));
  
  // Simple optimization suggestions
  const actions = [];
  const overweightThreshold = 0.15; // 15%
  const underweightThreshold = 0.02; // 2%
  
  currentAllocation.forEach(position => {
    if (position.weight > overweightThreshold) {
      actions.push({
        type: 'reduce',
        symbol: position.symbol,
        currentWeight: position.weight,
        suggestedWeight: overweightThreshold,
        reason: 'Overweight position - reduce concentration risk'
      });
    } else if (position.weight < underweightThreshold && position.weight > 0) {
      actions.push({
        type: 'consider_exit',
        symbol: position.symbol,
        currentWeight: position.weight,
        reason: 'Very small position - consider consolidating'
      });
    }
  });
  
  return {
    suggestedAllocation: currentAllocation, // Simplified
    rebalanceNeeded: actions.length > 0,
    actions: actions,
    expectedImprovement: {
      riskReduction: '5-10%',
      expectedReturn: '+0.5-1.0%'
    },
    diversificationScore: Math.min(10, holdings.length / 2) // Simple score
  };
}

function calculateAlphaBeta(returns, benchmarkReturns) {
  if (returns.length !== benchmarkReturns.length || returns.length === 0) {
    return { alpha: 0, beta: 1 };
  }
  
  const avgReturn = returns.reduce((sum, r) => sum + r, 0) / returns.length;
  const avgBenchmark = benchmarkReturns.reduce((sum, r) => sum + r, 0) / benchmarkReturns.length;
  
  let covariance = 0;
  let benchmarkVariance = 0;
  
  for (let i = 0; i < returns.length; i++) {
    covariance += (returns[i] - avgReturn) * (benchmarkReturns[i] - avgBenchmark);
    benchmarkVariance += Math.pow(benchmarkReturns[i] - avgBenchmark, 2);
  }
  
  const beta = benchmarkVariance > 0 ? covariance / benchmarkVariance : 1;
  const alpha = avgReturn - (beta * avgBenchmark);
  
  return { alpha, beta };
}

function calculateSortinoRatio(returns) {
  const avgReturn = returns.reduce((sum, r) => sum + r, 0) / returns.length;
  const downside = returns.filter(r => r < 0);
  
  if (downside.length === 0) return 0;
  
  const downsideDeviation = Math.sqrt(downside.reduce((sum, r) => sum + Math.pow(r, 2), 0) / downside.length);
  return downsideDeviation > 0 ? (avgReturn * 252) / (downsideDeviation * Math.sqrt(252)) : 0;
}

function calculateInformationRatio(returns, benchmarkReturns) {
  if (returns.length !== benchmarkReturns.length) return 0;
  
  const excessReturns = returns.map((r, i) => r - benchmarkReturns[i]);
  const avgExcess = excessReturns.reduce((sum, r) => sum + r, 0) / excessReturns.length;
  const trackingError = Math.sqrt(excessReturns.reduce((sum, r) => sum + Math.pow(r - avgExcess, 2), 0) / excessReturns.length);
  
  return trackingError > 0 ? (avgExcess * 252) / (trackingError * Math.sqrt(252)) : 0;
}

function getTopSector(holdings) {
  const sectorMap = {};
  holdings.forEach(h => {
    const sector = h.sector || 'Other';
    const value = parseFloat(h.market_value || 0);
    sectorMap[sector] = (sectorMap[sector] || 0) + value;
  });
  
  return Object.entries(sectorMap).reduce((top, [sector, value]) => 
    value > top.value ? { sector, value } : top, 
    { sector: 'None', value: 0 }
  ).sector;
}

function calculateConcentration(holdings) {
  const totalValue = holdings.reduce((sum, h) => sum + parseFloat(h.market_value || 0), 0);
  const top5Value = holdings
    .sort((a, b) => parseFloat(b.market_value || 0) - parseFloat(a.market_value || 0))
    .slice(0, 5)
    .reduce((sum, h) => sum + parseFloat(h.market_value || 0), 0);
  
  return totalValue > 0 ? top5Value / totalValue : 0;
}

function calculateCurrentAllocation(holdings) {
  const totalValue = holdings.reduce((sum, h) => sum + parseFloat(h.market_value || 0), 0);
  return holdings.map(h => ({
    symbol: h.symbol,
    weight: parseFloat(h.market_value || 0) / totalValue,
    sector: h.sector
  }));
}

function generateRiskRecommendations(riskAnalysis) {
  const recommendations = [];
  
  if (riskAnalysis.portfolioBeta > 1.3) {
    recommendations.push({
      type: 'high_beta',
      message: 'Portfolio has high beta - consider adding defensive positions',
      priority: 'medium'
    });
  }
  
  if (riskAnalysis.positionConcentration > 0.5) {
    recommendations.push({
      type: 'concentration',
      message: 'High concentration in top positions - consider diversifying',
      priority: 'high'
    });
  }
  
  if (riskAnalysis.portfolioVolatility > 0.25) {
    recommendations.push({
      type: 'volatility',
      message: 'High portfolio volatility - consider adding stable assets',
      priority: 'medium'
    });
  }
  
  return recommendations;
}

// =======================
// SECURE API KEY MANAGEMENT AND PORTFOLIO IMPORT
// =======================

const crypto = require('crypto');

// Encrypt API keys using AES-256-GCM
function encryptApiKey(apiKey, userSalt) {
  const algorithm = 'aes-256-gcm';
  const secretKey = process.env.API_KEY_ENCRYPTION_SECRET || 'default-dev-secret-key-32-chars!!';
  const key = crypto.scryptSync(secretKey, userSalt, 32);
  const iv = crypto.randomBytes(16);
  
  const cipher = crypto.createCipher(algorithm, key);
  cipher.setAAD(Buffer.from(userSalt));
  
  let encrypted = cipher.update(apiKey, 'utf8', 'hex');
  encrypted += cipher.final('hex');
  
  const authTag = cipher.getAuthTag();
  
  return {
    encrypted,
    iv: iv.toString('hex'),
    authTag: authTag.toString('hex')
  };
}

// Decrypt API keys 
function decryptApiKey(encryptedData, userSalt) {
  const algorithm = 'aes-256-gcm';
  const secretKey = process.env.API_KEY_ENCRYPTION_SECRET || 'default-dev-secret-key-32-chars!!';
  const key = crypto.scryptSync(secretKey, userSalt, 32);
  
  const decipher = crypto.createDecipher(algorithm, key);
  decipher.setAAD(Buffer.from(userSalt));
  decipher.setAuthTag(Buffer.from(encryptedData.authTag, 'hex'));
  
  let decrypted = decipher.update(encryptedData.encrypted, 'hex', 'utf8');
  decrypted += decipher.final('utf8');
  
  return decrypted;
}

// Store encrypted API key for user
router.post('/api-keys', async (req, res) => {
  try {
    const userId = req.user.sub;
    const { brokerName, apiKey, apiSecret, sandbox = true } = req.body;
    
    // Validate required fields
    if (!brokerName || !apiKey) {
      return res.status(400).json({
        success: false,
        error: 'Broker name and API key are required',
        timestamp: new Date().toISOString()
      });
    }
    
    // Create user-specific salt
    const userSalt = crypto.createHash('sha256').update(userId).digest('hex').slice(0, 16);
    
    // Encrypt the API credentials
    const encryptedApiKey = encryptApiKey(apiKey, userSalt);
    const encryptedApiSecret = apiSecret ? encryptApiKey(apiSecret, userSalt) : null;
    
    // Store in database with no logging of plaintext keys
    const insertQuery = `
      INSERT INTO user_api_keys (
        user_id, broker_name, encrypted_api_key, encrypted_api_secret, 
        key_iv, key_auth_tag, secret_iv, secret_auth_tag,
        is_sandbox, created_at, last_used
      ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, CURRENT_TIMESTAMP, NULL)
      ON CONFLICT (user_id, broker_name) 
      DO UPDATE SET
        encrypted_api_key = EXCLUDED.encrypted_api_key,
        encrypted_api_secret = EXCLUDED.encrypted_api_secret,
        key_iv = EXCLUDED.key_iv,
        key_auth_tag = EXCLUDED.key_auth_tag,
        secret_iv = EXCLUDED.secret_iv,
        secret_auth_tag = EXCLUDED.secret_auth_tag,
        is_sandbox = EXCLUDED.is_sandbox,
        updated_at = CURRENT_TIMESTAMP
    `;
    
    await query(insertQuery, [
      userId,
      brokerName,
      encryptedApiKey.encrypted,
      encryptedApiSecret?.encrypted || null,
      encryptedApiKey.iv,
      encryptedApiKey.authTag,
      encryptedApiSecret?.iv || null,
      encryptedApiSecret?.authTag || null,
      sandbox
    ]);
    
    console.log(`API key stored securely for user ${userId}, broker: ${brokerName}`);
    
    res.json({
      success: true,
      message: 'API key stored securely',
      broker: brokerName,
      sandbox,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Error storing API key:', error.message); // Don't log full error which might contain keys
    res.status(500).json({
      success: false,
      error: 'Failed to store API key securely',
      timestamp: new Date().toISOString()
    });
  }
});

// List user's connected brokers (without exposing keys)
router.get('/api-keys', async (req, res) => {
  try {
    const userId = req.user.sub;
    
    const selectQuery = `
      SELECT broker_name, is_sandbox, created_at, last_used, updated_at
      FROM user_api_keys 
      WHERE user_id = $1
      ORDER BY updated_at DESC
    `;
    
    const result = await query(selectQuery, [userId]);
    
    res.json({
      success: true,
      data: result.rows.map(row => ({
        broker: row.broker_name,
        sandbox: row.is_sandbox,
        connected: true,
        lastUsed: row.last_used,
        connectedAt: row.created_at
      })),
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Error fetching API keys:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch connected brokers',
      timestamp: new Date().toISOString()
    });
  }
});

// Delete API key
router.delete('/api-keys/:brokerName', async (req, res) => {
  try {
    const userId = req.user.sub;
    const { brokerName } = req.params;
    
    const deleteQuery = `
      DELETE FROM user_api_keys 
      WHERE user_id = $1 AND broker_name = $2
    `;
    
    const result = await query(deleteQuery, [userId, brokerName]);
    
    if (result.rowCount === 0) {
      return res.status(404).json({
        success: false,
        error: 'API key not found',
        timestamp: new Date().toISOString()
      });
    }
    
    console.log(`API key deleted for user ${userId}, broker: ${brokerName}`);
    
    res.json({
      success: true,
      message: 'API key deleted successfully',
      broker: brokerName,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Error deleting API key:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to delete API key',
      timestamp: new Date().toISOString()
    });
  }
});

// Test broker connection
router.post('/test-connection/:brokerName', async (req, res) => {
  try {
    const userId = req.user.sub;
    const { brokerName } = req.params;
    
    console.log(`Testing connection for user ${userId}, broker: ${brokerName}`);
    
    // Get encrypted API credentials
    const keyQuery = `
      SELECT encrypted_api_key, encrypted_api_secret, key_iv, key_auth_tag, 
             secret_iv, secret_auth_tag, is_sandbox
      FROM user_api_keys 
      WHERE user_id = $1 AND broker_name = $2
    `;
    
    const keyResult = await query(keyQuery, [userId, brokerName]);
    
    if (keyResult.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: 'No API key found for this broker. Please connect your account first.',
        timestamp: new Date().toISOString()
      });
    }
    
    const keyData = keyResult.rows[0];
    const userSalt = crypto.createHash('sha256').update(userId).digest('hex').slice(0, 16);
    
    // Decrypt API credentials
    const apiKey = decryptApiKey({
      encrypted: keyData.encrypted_api_key,
      iv: keyData.key_iv,
      authTag: keyData.key_auth_tag
    }, userSalt);
    
    const apiSecret = keyData.encrypted_api_secret ? decryptApiKey({
      encrypted: keyData.encrypted_api_secret,
      iv: keyData.secret_iv,
      authTag: keyData.secret_auth_tag
    }, userSalt) : null;
    
    // Test connection based on broker
    let connectionResult;
    switch (brokerName.toLowerCase()) {
      case 'alpaca':
        const AlpacaService = require('../utils/alpacaService');
        const alpaca = new AlpacaService(apiKey, apiSecret, keyData.is_sandbox);
        connectionResult = await alpaca.validateCredentials();
        
        if (connectionResult.valid) {
          // Get basic account info
          const account = await alpaca.getAccount();
          connectionResult.accountInfo = {
            accountId: account.accountId,
            status: account.status,
            portfolioValue: account.portfolioValue,
            cash: account.cash,
            environment: account.environment
          };
        }
        break;
        
      default:
        return res.status(400).json({
          success: false,
          error: `Broker '${brokerName}' connection testing not yet implemented`,
          supportedBrokers: ['alpaca'],
          timestamp: new Date().toISOString()
        });
    }
    
    // Update last used timestamp if connection successful
    if (connectionResult.valid) {
      await query(
        'UPDATE user_api_keys SET last_used = CURRENT_TIMESTAMP WHERE user_id = $1 AND broker_name = $2',
        [userId, brokerName]
      );
    }
    
    res.json({
      success: true,
      connection: connectionResult,
      broker: brokerName,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error(`Connection test error for broker ${req.params.brokerName}:`, error.message);
    res.status(500).json({
      success: false,
      error: 'Failed to test broker connection',
      details: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Import portfolio from connected broker
router.post('/import/:brokerName', async (req, res) => {
  try {
    const userId = req.user.sub;
    const { brokerName } = req.params;
    
    console.log(`Portfolio import initiated for user ${userId}, broker: ${brokerName}`);
    
    // Get encrypted API credentials
    const keyQuery = `
      SELECT encrypted_api_key, encrypted_api_secret, key_iv, key_auth_tag, 
             secret_iv, secret_auth_tag, is_sandbox
      FROM user_api_keys 
      WHERE user_id = $1 AND broker_name = $2
    `;
    
    const keyResult = await query(keyQuery, [userId, brokerName]);
    
    if (keyResult.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: 'No API key found for this broker. Please connect your account first.',
        timestamp: new Date().toISOString()
      });
    }
    
    const keyData = keyResult.rows[0];
    const userSalt = crypto.createHash('sha256').update(userId).digest('hex').slice(0, 16);
    
    // Decrypt API credentials (never log these)
    const apiKey = decryptApiKey({
      encrypted: keyData.encrypted_api_key,
      iv: keyData.key_iv,
      authTag: keyData.key_auth_tag
    }, userSalt);
    
    const apiSecret = keyData.encrypted_api_secret ? decryptApiKey({
      encrypted: keyData.encrypted_api_secret,
      iv: keyData.secret_iv,
      authTag: keyData.secret_auth_tag
    }, userSalt) : null;
    
    // Import portfolio data based on broker
    let portfolioData;
    switch (brokerName.toLowerCase()) {
      case 'alpaca':
        portfolioData = await importFromAlpaca(apiKey, apiSecret, keyData.is_sandbox);
        break;
      case 'robinhood':
        portfolioData = await importFromRobinhood(apiKey, apiSecret, keyData.is_sandbox);
        break;
      case 'td_ameritrade':
        portfolioData = await importFromTDAmeritrade(apiKey, apiSecret, keyData.is_sandbox);
        break;
      default:
        return res.status(400).json({
          success: false,
          error: `Broker '${brokerName}' is not supported yet`,
          supportedBrokers: ['alpaca', 'robinhood', 'td_ameritrade'],
          timestamp: new Date().toISOString()
        });
    }
    
    // Store imported portfolio data
    await storeImportedPortfolio(userId, portfolioData);
    
    // Update last used timestamp
    await query(
      'UPDATE user_api_keys SET last_used = CURRENT_TIMESTAMP WHERE user_id = $1 AND broker_name = $2',
      [userId, brokerName]
    );
    
    console.log(`Portfolio import completed successfully for user ${userId}, ${portfolioData.holdings.length} positions imported`);
    
    res.json({
      success: true,
      message: 'Portfolio imported successfully',
      data: {
        broker: brokerName,
        holdingsCount: portfolioData.holdings.length,
        totalValue: portfolioData.totalValue,
        importedAt: new Date().toISOString(),
        summary: portfolioData.summary
      },
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error(`Portfolio import error for broker ${req.params.brokerName}:`, error.message);
    res.status(500).json({
      success: false,
      error: 'Failed to import portfolio. Please check your API credentials and try again.',
      details: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Broker-specific import functions
async function importFromAlpaca(apiKey, apiSecret, sandbox) {
  try {
    const AlpacaService = require('../utils/alpacaService');
    const alpaca = new AlpacaService(apiKey, apiSecret, sandbox);
    
    // Validate credentials first
    const validation = await alpaca.validateCredentials();
    if (!validation.valid) {
      throw new Error(`Invalid Alpaca credentials: ${validation.error}`);
    }
    
    console.log(`🔗 Connected to Alpaca ${validation.environment} environment`);
    
    // Get comprehensive portfolio data
    const portfolioSummary = await alpaca.getPortfolioSummary();
    
    // Transform Alpaca positions to our format
    const holdings = portfolioSummary.positions.map(position => ({
      symbol: position.symbol,
      quantity: position.quantity,
      market_value: position.marketValue,
      cost_basis: position.costBasis,
      pnl: position.unrealizedPL,
      pnl_percent: position.unrealizedPLPercent,
      weight: portfolioSummary.summary.totalValue > 0 ? 
        (position.marketValue / portfolioSummary.summary.totalValue) : 0,
      sector: position.sector || 'Unknown',
      current_price: position.currentPrice,
      average_entry_price: position.averageEntryPrice,
      day_change: position.unrealizedIntradayPL,
      day_change_percent: position.unrealizedIntradayPLPercent,
      exchange: position.exchange,
      asset_class: position.assetClass,
      last_updated: position.lastUpdated
    }));
    
    return {
      holdings: holdings,
      totalValue: portfolioSummary.summary.totalValue,
      summary: {
        positions: holdings.length,
        cash: portfolioSummary.summary.totalCash,
        totalPnL: portfolioSummary.summary.totalPnL,
        totalPnLPercent: portfolioSummary.summary.totalPnLPercent,
        dayPnL: portfolioSummary.summary.dayPnL,
        dayPnLPercent: portfolioSummary.summary.dayPnLPercent,
        buyingPower: portfolioSummary.summary.buyingPower,
        accountStatus: portfolioSummary.account.status,
        environment: validation.environment
      },
      account: portfolioSummary.account,
      performance: portfolioSummary.performance,
      sectorAllocation: portfolioSummary.sectorAllocation,
      riskMetrics: portfolioSummary.riskMetrics,
      broker: 'alpaca',
      importedAt: new Date().toISOString()
    };
    
  } catch (error) {
    console.error('Alpaca import error:', error.message);
    throw new Error(`Failed to import from Alpaca: ${error.message}`);
  }
}

async function importFromRobinhood(apiKey, apiSecret, sandbox) {
  // TODO: Implement Robinhood API integration
  return {
    holdings: [],
    totalValue: 0,
    summary: { positions: 0, cash: 0 }
  };
}

async function importFromTDAmeritrade(apiKey, apiSecret, sandbox) {
  // TODO: Implement TD Ameritrade API integration
  return {
    holdings: [],
    totalValue: 0,
    summary: { positions: 0, cash: 0 }
  };
}

async function storeImportedPortfolio(userId, portfolioData) {
  const client = await query('BEGIN');
  
  try {
    // Clear existing holdings for this user
    await query('DELETE FROM portfolio_holdings WHERE user_id = $1', [userId]);
    
    // Store portfolio metadata
    const portfolioMetaQuery = `
      INSERT INTO portfolio_metadata (
        user_id, broker, total_value, total_cash, total_pnl, 
        total_pnl_percent, day_pnl, day_pnl_percent, 
        positions_count, account_status, environment, imported_at
      ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, CURRENT_TIMESTAMP)
      ON CONFLICT (user_id, broker) 
      DO UPDATE SET
        total_value = EXCLUDED.total_value,
        total_cash = EXCLUDED.total_cash,
        total_pnl = EXCLUDED.total_pnl,
        total_pnl_percent = EXCLUDED.total_pnl_percent,
        day_pnl = EXCLUDED.day_pnl,
        day_pnl_percent = EXCLUDED.day_pnl_percent,
        positions_count = EXCLUDED.positions_count,
        account_status = EXCLUDED.account_status,
        environment = EXCLUDED.environment,
        imported_at = CURRENT_TIMESTAMP
    `;
    
    await query(portfolioMetaQuery, [
      userId,
      portfolioData.broker || 'unknown',
      portfolioData.totalValue || 0,
      portfolioData.summary?.cash || 0,
      portfolioData.summary?.totalPnL || 0,
      portfolioData.summary?.totalPnLPercent || 0,
      portfolioData.summary?.dayPnL || 0,
      portfolioData.summary?.dayPnLPercent || 0,
      portfolioData.holdings?.length || 0,
      portfolioData.summary?.accountStatus || 'unknown',
      portfolioData.summary?.environment || 'unknown'
    ]);
    
    // Insert new holdings with enhanced data
    for (const holding of portfolioData.holdings) {
      const insertHoldingQuery = `
        INSERT INTO portfolio_holdings (
          user_id, symbol, quantity, market_value, cost_basis, 
          pnl, pnl_percent, weight, sector, current_price,
          average_entry_price, day_change, day_change_percent,
          exchange, asset_class, broker, last_updated
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, CURRENT_TIMESTAMP)
      `;
      
      await query(insertHoldingQuery, [
        userId,
        holding.symbol,
        holding.quantity || 0,
        holding.market_value || 0,
        holding.cost_basis || 0,
        holding.pnl || 0,
        holding.pnl_percent || 0,
        holding.weight || 0,
        holding.sector || 'Unknown',
        holding.current_price || 0,
        holding.average_entry_price || 0,
        holding.day_change || 0,
        holding.day_change_percent || 0,
        holding.exchange || '',
        holding.asset_class || 'equity',
        portfolioData.broker || 'unknown'
      ]);
    }
    
    // Store performance history if available
    if (portfolioData.performance && portfolioData.performance.length > 0) {
      // Clear existing performance data
      await query('DELETE FROM portfolio_performance WHERE user_id = $1', [userId]);
      
      for (const perfData of portfolioData.performance) {
        const insertPerfQuery = `
          INSERT INTO portfolio_performance (
            user_id, date, total_value, daily_pnl, daily_pnl_percent,
            total_pnl, total_pnl_percent, broker
          ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
          ON CONFLICT (user_id, date, broker) DO UPDATE SET
            total_value = EXCLUDED.total_value,
            daily_pnl = EXCLUDED.daily_pnl,
            daily_pnl_percent = EXCLUDED.daily_pnl_percent,
            total_pnl = EXCLUDED.total_pnl,
            total_pnl_percent = EXCLUDED.total_pnl_percent
        `;
        
        await query(insertPerfQuery, [
          userId,
          perfData.date,
          perfData.equity || 0,
          perfData.profitLoss || 0,
          perfData.profitLossPercent || 0,
          perfData.equity - (perfData.baseValue || 0),
          perfData.profitLossPercent || 0,
          portfolioData.broker || 'unknown'
        ]);
      }
    }
    
    await query('COMMIT');
    console.log(`✅ Portfolio data stored successfully for user ${userId}`);
    
  } catch (error) {
    await query('ROLLBACK');
    console.error('Error storing portfolio data:', error);
    throw new Error(`Failed to store portfolio data: ${error.message}`);
  }
}

// Risk analytics endpoints
router.get('/risk/var', authenticateToken, async (req, res) => {
  try {
    const userId = req.user.userId;
    const confidence = parseFloat(req.query.confidence) || 0.95;
    const timeHorizon = parseInt(req.query.timeHorizon) || 252; // 1 year default
    
    // Get portfolio holdings with historical data
    const holdingsQuery = `
      SELECT ph.symbol, ph.quantity, ph.average_price,
             (ph.quantity * COALESCE(pd.close_price, ph.average_price)) as market_value,
             se.sector, se.market_cap_tier
      FROM portfolio_holdings ph
      LEFT JOIN price_daily pd ON ph.symbol = pd.symbol 
        AND pd.date = (SELECT MAX(date) FROM price_daily WHERE symbol = ph.symbol)
      LEFT JOIN stock_symbols_enhanced se ON ph.symbol = se.symbol
      WHERE ph.user_id = $1 AND ph.quantity > 0
    `;
    
    const holdings = await query(holdingsQuery, [userId]);
    
    if (holdings.length === 0) {
      return res.json({ var: 0, cvar: 0, message: 'No portfolio holdings found' });
    }
    
    // Calculate portfolio VaR using Monte Carlo simulation
    const portfolioVar = await calculatePortfolioVaR(holdings, confidence, timeHorizon);
    
    res.json({
      success: true,
      var: portfolioVar.var,
      cvar: portfolioVar.cvar,
      confidence: confidence,
      timeHorizon: timeHorizon,
      methodology: 'Monte Carlo Simulation',
      asOfDate: new Date().toISOString().split('T')[0]
    });
    
  } catch (error) {
    console.error('Portfolio VaR calculation error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to calculate portfolio VaR',
      details: error.message
    });
  }
});

router.get('/risk/stress-test', authenticateToken, async (req, res) => {
  try {
    const userId = req.user.userId;
    const scenario = req.query.scenario || 'market_crash';
    
    // Get portfolio holdings
    const holdingsQuery = `
      SELECT ph.symbol, ph.quantity, ph.average_price,
             (ph.quantity * COALESCE(pd.close_price, ph.average_price)) as market_value,
             se.sector, se.beta
      FROM portfolio_holdings ph
      LEFT JOIN price_daily pd ON ph.symbol = pd.symbol 
        AND pd.date = (SELECT MAX(date) FROM price_daily WHERE symbol = ph.symbol)
      LEFT JOIN stock_symbols_enhanced se ON ph.symbol = se.symbol
      WHERE ph.user_id = $1 AND ph.quantity > 0
    `;
    
    const holdings = await query(holdingsQuery, [userId]);
    
    if (holdings.length === 0) {
      return res.json({ impact: 0, message: 'No portfolio holdings found' });
    }
    
    // Define stress scenarios
    const scenarios = {
      market_crash: { market: -0.20, volatility: 0.40 },
      recession: { market: -0.15, volatility: 0.35 },
      inflation_spike: { market: -0.10, volatility: 0.30 },
      rate_hike: { market: -0.08, volatility: 0.25 },
      sector_rotation: { market: -0.05, volatility: 0.20 }
    };
    
    const stressTest = calculateStressTestImpact(holdings, scenarios[scenario]);
    
    res.json({
      success: true,
      scenario: scenario,
      description: getScenarioDescription(scenario),
      impact: stressTest.impact,
      newValue: stressTest.newValue,
      currentValue: stressTest.currentValue,
      worstHolding: stressTest.worstHolding,
      bestHolding: stressTest.bestHolding,
      sectorImpacts: stressTest.sectorImpacts
    });
    
  } catch (error) {
    console.error('Stress test error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to perform stress test',
      details: error.message
    });
  }
});

router.get('/risk/correlation', authenticateToken, async (req, res) => {
  try {
    const userId = req.user.userId;
    const period = req.query.period || '1y';
    
    // Get portfolio holdings
    const holdingsQuery = `
      SELECT DISTINCT ph.symbol
      FROM portfolio_holdings ph
      WHERE ph.user_id = $1 AND ph.quantity > 0
    `;
    
    const holdings = await query(holdingsQuery, [userId]);
    
    if (holdings.length < 2) {
      return res.json({ correlations: [], message: 'Need at least 2 holdings for correlation analysis' });
    }
    
    // Calculate correlation matrix
    const correlationMatrix = await calculateCorrelationMatrix(holdings.map(h => h.symbol), period);
    
    res.json({
      success: true,
      correlations: correlationMatrix,
      symbols: holdings.map(h => h.symbol),
      period: period,
      highCorrelations: correlationMatrix.filter(c => Math.abs(c.correlation) > 0.7),
      averageCorrelation: correlationMatrix.reduce((sum, c) => sum + Math.abs(c.correlation), 0) / correlationMatrix.length
    });
    
  } catch (error) {
    console.error('Correlation analysis error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to calculate correlations',
      details: error.message
    });
  }
});

router.get('/risk/concentration', authenticateToken, async (req, res) => {
  try {
    const userId = req.user.userId;
    
    // Get portfolio holdings with detailed info
    const holdingsQuery = `
      SELECT ph.symbol, ph.quantity, ph.average_price,
             (ph.quantity * COALESCE(pd.close_price, ph.average_price)) as market_value,
             se.sector, se.industry, se.market_cap_tier, se.country
      FROM portfolio_holdings ph
      LEFT JOIN price_daily pd ON ph.symbol = pd.symbol 
        AND pd.date = (SELECT MAX(date) FROM price_daily WHERE symbol = ph.symbol)
      LEFT JOIN stock_symbols_enhanced se ON ph.symbol = se.symbol
      WHERE ph.user_id = $1 AND ph.quantity > 0
      ORDER BY market_value DESC
    `;
    
    const holdings = await query(holdingsQuery, [userId]);
    
    if (holdings.length === 0) {
      return res.json({ concentration: {}, message: 'No portfolio holdings found' });
    }
    
    const concentrationAnalysis = calculateConcentrationRisk(holdings);
    
    res.json({
      success: true,
      ...concentrationAnalysis,
      recommendations: generateConcentrationRecommendations(concentrationAnalysis)
    });
    
  } catch (error) {
    console.error('Concentration analysis error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to analyze concentration risk',
      details: error.message
    });
  }
});

// Helper functions for risk calculations

async function calculatePortfolioVaR(holdings, confidence, timeHorizon) {
  const totalValue = holdings.reduce((sum, h) => sum + parseFloat(h.market_value || 0), 0);
  
  // Simplified VaR calculation - in production would use more sophisticated models
  const portfolioVolatility = await estimatePortfolioVolatility(holdings);
  const zScore = confidence === 0.95 ? 1.645 : confidence === 0.99 ? 2.326 : 1.282;
  
  const dailyVaR = totalValue * portfolioVolatility * zScore / Math.sqrt(252);
  const valueAtRisk = dailyVaR * Math.sqrt(timeHorizon);
  const cvar = valueAtRisk * 1.3; // Simplified CVaR estimate
  
  return { var: valueAtRisk, cvar };
}

async function estimatePortfolioVolatility(holdings) {
  // Get historical volatility for each holding
  const volatilities = [];
  const weights = [];
  const totalValue = holdings.reduce((sum, h) => sum + parseFloat(h.market_value || 0), 0);
  
  for (const holding of holdings) {
    const weight = parseFloat(holding.market_value) / totalValue;
    weights.push(weight);
    
    // Get historical volatility from technical indicators or estimate based on sector
    try {
      const volQuery = `
        SELECT historical_volatility_20d 
        FROM technical_indicators 
        WHERE symbol = $1 
        ORDER BY date DESC 
        LIMIT 1
      `;
      const volResult = await query(volQuery, [holding.symbol]);
      
      let volatility = 0.25; // Default volatility
      if (volResult.length > 0 && volResult[0].historical_volatility_20d) {
        volatility = parseFloat(volResult[0].historical_volatility_20d);
      } else {
        // Estimate based on market cap tier
        const marketCapTier = holding.market_cap_tier;
        volatility = marketCapTier === 'large_cap' ? 0.20 : 
                    marketCapTier === 'mid_cap' ? 0.25 : 0.35;
      }
      
      volatilities.push(volatility);
    } catch (error) {
      volatilities.push(0.25); // Default if can't get data
    }
  }
  
  // Calculate weighted average volatility (simplified - ignores correlations)
  const portfolioVol = weights.reduce((sum, weight, i) => sum + weight * volatilities[i], 0);
  return portfolioVol;
}

function calculateStressTestImpact(holdings, scenario) {
  const currentValue = holdings.reduce((sum, h) => sum + parseFloat(h.market_value || 0), 0);
  let newValue = 0;
  const impacts = [];
  
  holdings.forEach(holding => {
    const beta = parseFloat(holding.beta) || 1.0;
    const sectorMultiplier = getSectorStressMultiplier(holding.sector);
    
    const stockImpact = scenario.market * beta * sectorMultiplier;
    const newHoldingValue = parseFloat(holding.market_value) * (1 + stockImpact);
    
    newValue += newHoldingValue;
    impacts.push({
      symbol: holding.symbol,
      currentValue: parseFloat(holding.market_value),
      newValue: newHoldingValue,
      impact: stockImpact
    });
  });
  
  const totalImpact = (newValue - currentValue) / currentValue;
  
  impacts.sort((a, b) => a.impact - b.impact);
  
  // Group by sector
  const sectorImpacts = holdings.reduce((acc, holding) => {
    const sector = holding.sector || 'Unknown';
    if (!acc[sector]) acc[sector] = { currentValue: 0, newValue: 0 };
    
    const impact = impacts.find(i => i.symbol === holding.symbol);
    acc[sector].currentValue += parseFloat(holding.market_value);
    acc[sector].newValue += impact.newValue;
    
    return acc;
  }, {});
  
  return {
    impact: totalImpact,
    newValue,
    currentValue,
    worstHolding: impacts[0],
    bestHolding: impacts[impacts.length - 1],
    sectorImpacts: Object.entries(sectorImpacts).map(([sector, data]) => ({
      sector,
      impact: (data.newValue - data.currentValue) / data.currentValue
    }))
  };
}

function getSectorStressMultiplier(sector) {
  const multipliers = {
    'Technology': 1.2,
    'Financials': 1.1,
    'Energy': 1.3,
    'Real Estate': 1.2,
    'Consumer Discretionary': 1.1,
    'Industrials': 1.0,
    'Healthcare': 0.8,
    'Consumer Staples': 0.7,
    'Utilities': 0.6
  };
  return multipliers[sector] || 1.0;
}

async function calculateCorrelationMatrix(symbols, period) {
  // Simplified correlation calculation
  const correlations = [];
  
  for (let i = 0; i < symbols.length; i++) {
    for (let j = i + 1; j < symbols.length; j++) {
      // In production, would calculate actual correlation from price data
      // For now, estimate based on sector similarity
      const correlation = estimateCorrelation(symbols[i], symbols[j]);
      
      correlations.push({
        symbol1: symbols[i],
        symbol2: symbols[j],
        correlation: correlation
      });
    }
  }
  
  return correlations;
}

function estimateCorrelation(symbol1, symbol2) {
  // Simplified correlation estimate - in production would use actual price data
  // Same sector = higher correlation, different sectors = lower correlation
  return Math.random() * 0.6 + 0.1; // Random between 0.1 and 0.7
}

function calculateConcentrationRisk(holdings) {
  const totalValue = holdings.reduce((sum, h) => sum + parseFloat(h.market_value || 0), 0);
  
  // Position concentration
  const positions = holdings.map(h => ({
    symbol: h.symbol,
    weight: parseFloat(h.market_value) / totalValue,
    value: parseFloat(h.market_value)
  })).sort((a, b) => b.weight - a.weight);
  
  // Sector concentration
  const sectors = holdings.reduce((acc, h) => {
    const sector = h.sector || 'Unknown';
    acc[sector] = (acc[sector] || 0) + parseFloat(h.market_value);
    return acc;
  }, {});
  
  const sectorWeights = Object.entries(sectors).map(([sector, value]) => ({
    sector,
    weight: value / totalValue,
    value
  })).sort((a, b) => b.weight - a.weight);
  
  // HHI calculation
  const positionHHI = positions.reduce((sum, p) => sum + p.weight * p.weight, 0);
  const sectorHHI = sectorWeights.reduce((sum, s) => sum + s.weight * s.weight, 0);
  
  return {
    positionConcentration: {
      top5Weight: positions.slice(0, 5).reduce((sum, p) => sum + p.weight, 0),
      top10Weight: positions.slice(0, 10).reduce((sum, p) => sum + p.weight, 0),
      largestPosition: positions[0],
      herfindahlIndex: positionHHI,
      positions: positions.slice(0, 10)
    },
    sectorConcentration: {
      topSector: sectorWeights[0],
      top3Weight: sectorWeights.slice(0, 3).reduce((sum, s) => sum + s.weight, 0),
      herfindahlIndex: sectorHHI,
      sectors: sectorWeights
    },
    overallRiskScore: Math.min(10, (positionHHI + sectorHHI) * 10)
  };
}

function generateConcentrationRecommendations(analysis) {
  const recommendations = [];
  
  if (analysis.positionConcentration.largestPosition.weight > 0.2) {
    recommendations.push({
      type: 'position_concentration',
      severity: 'high',
      message: `Consider reducing ${analysis.positionConcentration.largestPosition.symbol} position (${(analysis.positionConcentration.largestPosition.weight * 100).toFixed(1)}% of portfolio)`
    });
  }
  
  if (analysis.sectorConcentration.topSector.weight > 0.4) {
    recommendations.push({
      type: 'sector_concentration',
      severity: 'medium',
      message: `Consider diversifying beyond ${analysis.sectorConcentration.topSector.sector} sector (${(analysis.sectorConcentration.topSector.weight * 100).toFixed(1)}% of portfolio)`
    });
  }
  
  if (analysis.overallRiskScore > 7) {
    recommendations.push({
      type: 'overall_concentration',
      severity: 'high',
      message: 'Portfolio shows high concentration risk. Consider broader diversification.'
    });
  }
  
  return recommendations;
}

function getScenarioDescription(scenario) {
  const descriptions = {
    market_crash: 'Severe market decline (-20%) with increased volatility',
    recession: 'Economic recession scenario (-15%) with sector rotation',
    inflation_spike: 'High inflation environment (-10%) affecting growth stocks',
    rate_hike: 'Federal Reserve rate increases (-8%) impacting rate-sensitive sectors',
    sector_rotation: 'Market rotation (-5%) between growth and value'
  };
  return descriptions[scenario] || 'Custom stress scenario';
}

module.exports = router;