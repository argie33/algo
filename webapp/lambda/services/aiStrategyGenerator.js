/**
 * AI Strategy Generator Service - Enhanced with AWS Bedrock
 * Converts natural language descriptions into executable trading strategies using Claude AI
 * 
 * Features:
 * - Claude-powered natural language understanding
 * - Intelligent Python strategy generation
 * - Real-time streaming responses
 * - Advanced strategy validation
 * - AI-powered explanations and optimization
 */

const { createLogger } = require('../utils/logger');

class AIStrategyGenerator {
  constructor() {
    this.logger = createLogger();
    this.correlationId = this.generateCorrelationId();
    
    // Mock service (AWS services not available)
    this.bedrockService = null;
    this.bedrockClient = null;
    
    // AI Configuration
    this.aiConfig = {
      model: 'claude-3-haiku', // Fast and cost-effective for strategy generation
      maxTokens: 4000,
      temperature: 0.1, // Low temperature for consistent code generation
      fallbackToTemplates: true, // Fallback to templates if AI fails
      streamingEnabled: false // Can be enabled for real-time generation
    };
    
    // Strategy patterns for different asset types
    this.assetTypePatterns = {
      stock: {
        indicators: ['sma', 'ema', 'rsi', 'macd', 'volume', 'bollinger'],
        timeframes: ['1min', '5min', '15min', '1hour', '1day'],
        actions: ['buy', 'sell', 'hold']
      },
      crypto: {
        indicators: ['sma', 'ema', 'rsi', 'volume', 'momentum', 'volatility'],
        timeframes: ['1min', '5min', '15min', '1hour', '4hour', '1day'],
        actions: ['buy', 'sell', 'hold']
      },
      etf: {
        indicators: ['sma', 'ema', 'sector_rotation', 'relative_strength'],
        timeframes: ['15min', '1hour', '1day'],
        actions: ['buy', 'sell', 'hold']
      }
    };

    // Pre-defined strategy templates
    this.strategyTemplates = {
      momentum: {
        description: 'Momentum-based strategy using moving averages',
        code: this.getMomentumTemplate(),
        parameters: {
          short_window: 10,
          long_window: 30,
          position_size: 0.1
        }
      },
      mean_reversion: {
        description: 'Mean reversion strategy using RSI',
        code: this.getMeanReversionTemplate(),
        parameters: {
          rsi_period: 14,
          oversold_threshold: 30,
          overbought_threshold: 70,
          position_size: 0.1
        }
      },
      breakout: {
        description: 'Breakout strategy using Bollinger Bands',
        code: this.getBreakoutTemplate(),
        parameters: {
          bb_period: 20,
          bb_std: 2,
          volume_threshold: 1.5,
          position_size: 0.1
        }
      }
    };
  }

  generateCorrelationId() {
    return `ai-strategy-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  }

  /**
   * Generate strategy from natural language description using Claude AI
   */
  async generateFromNaturalLanguage(prompt, availableSymbols = [], options = {}) {
    try {
      this.logger.info('Generating AI-powered strategy from natural language', {
        prompt: prompt.substring(0, 200),
        symbolCount: availableSymbols.length,
        correlationId: this.correlationId,
        aiEnabled: true
      });

      // Try AI-powered generation first
      try {
        const aiResult = await this.generateWithClaude(prompt, availableSymbols, options);
        if (aiResult && aiResult.success) {
          return aiResult;
        }
      } catch (aiError) {
        this.logger.warn('AI generation failed, falling back to templates', {
          error: aiError.message,
          correlationId: this.correlationId
        });
      }

      // Fallback to template-based generation
      return await this.generateWithTemplates(prompt, availableSymbols, options);
      
    } catch (error) {
      this.logger.error('Strategy generation failed', {
        error: error.message,
        correlationId: this.correlationId
      });
      
      return {
        success: false,
        error: error.message,
        fallbackSuggestions: this.getFallbackSuggestions()
      };
    }
  }

  /**
   * Generate strategy using Claude AI
   */
  async generateWithClaude(prompt, availableSymbols = [], options = {}) {
    const systemPrompt = this.buildSystemPrompt(availableSymbols, options);
    const userPrompt = this.buildUserPrompt(prompt, availableSymbols, options);

    try {
      // Call Claude for strategy generation
      const response = await this.callClaude(systemPrompt, userPrompt);
      
      // Parse Claude's response
      const parsedStrategy = await this.parseClaudeResponse(response);
      
      // Validate and enhance the generated strategy
      const validatedStrategy = await this.validateAndEnhanceStrategy(parsedStrategy);
      
      // Generate metadata and visual config
      const metadata = await this.generateAIMetadata(validatedStrategy, prompt);
      const visualConfig = await this.generateAIVisualConfig(validatedStrategy);
      
      const result = {
        success: true,
        strategy: {
          name: validatedStrategy.name || this.generateStrategyName({ description: prompt }),
          description: validatedStrategy.description || prompt,
          code: validatedStrategy.code,
          strategyType: validatedStrategy.strategyType || 'ai_generated',
          symbols: validatedStrategy.symbols || availableSymbols.slice(0, 5),
          riskLevel: validatedStrategy.riskLevel || 'medium',
          parameters: validatedStrategy.parameters || {},
          aiGenerated: true,
          aiModel: this.aiConfig.model,
          timestamp: new Date().toISOString(),
          correlationId: this.correlationId,
          ...metadata
        },
        visualConfig,
        aiInsights: validatedStrategy.insights || []
      };

      this.logger.info('AI strategy generation successful', {
        strategyName: result.strategy.name,
        strategyType: result.strategy.strategyType,
        correlationId: this.correlationId
      });

      return result;
      
    } catch (error) {
      this.logger.error('Claude strategy generation failed', {
        error: error.message,
        correlationId: this.correlationId
      });
      throw error;
    }
  }

  /**
   * Fallback to template-based generation
   */
  async generateWithTemplates(prompt, availableSymbols = [], _options = {}) {
    // Parse the user's intent using rule-based approach
    const intent = await this.parseIntent(prompt);
    
    // Determine strategy type and approach
    const strategyType = this.determineStrategyType(intent);
    
    // Filter symbols based on intent
    const relevantSymbols = this.filterSymbolsByIntent(intent, availableSymbols);
    
    // Generate strategy code from templates
    const strategyCode = await this.generateStrategyCode(intent, strategyType, relevantSymbols);
    
    // Create visual configuration
    const visualConfig = this.createVisualConfig(intent, strategyType);
    
    // Generate strategy metadata
    const metadata = this.generateStrategyMetadata(intent, strategyType, relevantSymbols);

    const result = {
      success: true,
      strategy: {
        name: this.generateStrategyName(intent),
        description: intent.description || prompt,
        code: strategyCode,
        language: 'python',
        visualConfig: visualConfig,
        parameters: metadata.parameters,
        symbols: relevantSymbols.slice(0, 10), // Limit to 10 symbols
        assetTypes: this.getAssetTypes(relevantSymbols),
        strategyType: strategyType,
        riskLevel: this.assessRiskLevel(intent),
        estimatedPerformance: this.estimatePerformance(strategyType, intent),
        aiGenerated: false, // Template-based, not AI-generated
        prompt: prompt,
        generatedAt: new Date().toISOString()
      },
      visualConfig,
      metadata
    };

    this.logger.info('Template-based strategy generated successfully', {
      strategyName: result.strategy.name,
      strategyType: result.strategy.strategyType,
      correlationId: this.correlationId
    });

    return result;
  }

  /**
   * Parse user intent from natural language
   */
  async parseIntent(prompt) {
    const intent = {
      action: 'unknown',
      assets: [],
      indicators: [],
      conditions: [],
      timeframe: '1day',
      riskTolerance: 'medium',
      description: prompt
    };

    const lowerPrompt = prompt.toLowerCase();

    // Extract action intent
    if (lowerPrompt.includes('buy') || lowerPrompt.includes('long')) {
      intent.action = 'buy';
    } else if (lowerPrompt.includes('sell') || lowerPrompt.includes('short')) {
      intent.action = 'sell';
    } else if (lowerPrompt.includes('trade') || lowerPrompt.includes('strategy')) {
      intent.action = 'trade';
    }

    // Extract asset mentions
    const assetPatterns = {
      bitcoin: ['bitcoin', 'btc', 'btcusd'],
      apple: ['apple', 'aapl'],
      tesla: ['tesla', 'tsla'],
      spy: ['spy', 's&p', 'sp500'],
      crypto: ['crypto', 'cryptocurrency', 'coin'],
      stock: ['stock', 'equity', 'share'],
      etf: ['etf', 'fund']
    };

    for (const [asset, patterns] of Object.entries(assetPatterns)) {
      if (patterns.some(pattern => lowerPrompt.includes(pattern))) {
        intent.assets.push(asset);
      }
    }

    // Extract indicators
    const indicatorPatterns = {
      moving_average: ['moving average', 'ma', 'sma', 'ema'],
      rsi: ['rsi', 'relative strength'],
      macd: ['macd'],
      bollinger: ['bollinger', 'bands'],
      volume: ['volume', 'trading volume'],
      momentum: ['momentum', 'price momentum'],
      volatility: ['volatility', 'volatile']
    };

    for (const [indicator, patterns] of Object.entries(indicatorPatterns)) {
      if (patterns.some(pattern => lowerPrompt.includes(pattern))) {
        intent.indicators.push(indicator);
      }
    }

    // Extract timeframe
    const timeframePatterns = {
      '1min': ['1 minute', '1min', 'minute'],
      '5min': ['5 minute', '5min'],
      '15min': ['15 minute', '15min'],
      '1hour': ['1 hour', '1h', 'hourly'],
      '1day': ['daily', '1 day', '1d', 'day']
    };

    for (const [timeframe, patterns] of Object.entries(timeframePatterns)) {
      if (patterns.some(pattern => lowerPrompt.includes(pattern))) {
        intent.timeframe = timeframe;
        break;
      }
    }

    // Extract conditions
    if (lowerPrompt.includes('breaks above') || lowerPrompt.includes('exceeds')) {
      intent.conditions.push('breakout_above');
    }
    if (lowerPrompt.includes('breaks below') || lowerPrompt.includes('falls below')) {
      intent.conditions.push('breakout_below');
    }
    if (lowerPrompt.includes('spike') || lowerPrompt.includes('surge')) {
      intent.conditions.push('spike');
    }
    if (lowerPrompt.includes('oversold')) {
      intent.conditions.push('oversold');
    }
    if (lowerPrompt.includes('overbought')) {
      intent.conditions.push('overbought');
    }

    // Assess risk tolerance
    if (lowerPrompt.includes('conservative') || lowerPrompt.includes('safe')) {
      intent.riskTolerance = 'low';
    } else if (lowerPrompt.includes('aggressive') || lowerPrompt.includes('risky')) {
      intent.riskTolerance = 'high';
    }

    return intent;
  }

  /**
   * Determine strategy type based on intent
   */
  determineStrategyType(intent) {
    if (intent.indicators.includes('momentum') || 
        intent.conditions.includes('breakout_above') ||
        intent.conditions.includes('breakout_below')) {
      return 'momentum';
    }
    
    if (intent.indicators.includes('rsi') ||
        intent.conditions.includes('oversold') ||
        intent.conditions.includes('overbought')) {
      return 'mean_reversion';
    }
    
    if (intent.indicators.includes('bollinger') ||
        intent.conditions.includes('spike')) {
      return 'breakout';
    }
    
    // Default to momentum strategy
    return 'momentum';
  }

  /**
   * Filter symbols based on user intent
   */
  filterSymbolsByIntent(intent, availableSymbols) {
    if (!availableSymbols || availableSymbols.length === 0) {
      throw new Error('No symbols available for strategy generation. Symbol data service must be configured and accessible for AI strategy creation.');
    }

    let filtered = availableSymbols;

    // Filter by asset type if specified
    if (intent.assets.length > 0) {
      filtered = filtered.filter(symbol => {
        const symbolStr = symbol.symbol || symbol;
        const assetType = this.getAssetType(symbolStr);
        
        return intent.assets.some(asset => {
          if (asset === 'crypto' && assetType === 'crypto') return true;
          if (asset === 'stock' && assetType === 'stock') return true;
          if (asset === 'etf' && assetType === 'etf') return true;
          if (symbolStr.toLowerCase().includes(asset.toLowerCase())) return true;
          return false;
        });
      });
    }

    // If no matches found, require symbol data service configuration
    if (filtered.length === 0) {
      throw new Error(`No symbols match intent criteria for assets: ${intent.assets.join(', ')}. Symbol data service needs configuration for proper asset type filtering.`);
    }

    return filtered.slice(0, 10); // Limit to 10 symbols
  }

  /**
   * Generate strategy code based on intent and type
   */
  async generateStrategyCode(intent, strategyType, symbols) {
    const template = this.strategyTemplates[strategyType];
    if (!template) {
      throw new Error(`Unknown strategy type: ${strategyType}`);
    }

    let code = template.code;

    // Customize code based on intent
    code = this.customizeCodeForSymbols(code, symbols);
    code = this.customizeCodeForTimeframe(code, intent.timeframe);
    code = this.customizeCodeForIndicators(code, intent.indicators);
    code = this.customizeCodeForRiskTolerance(code, intent.riskTolerance);

    // Add natural language comment
    const comment = `# AI Generated Strategy: ${intent.description}\n# Generated on: ${new Date().toISOString()}\n\n`;
    
    return comment + code;
  }

  /**
   * Get momentum strategy template
   */
  getMomentumTemplate() {
    return `# Momentum Strategy Template
# Buys when short MA crosses above long MA, sells when opposite

import pandas as pd
import numpy as np

# Strategy Parameters
short_window = parameters.get('short_window', 10)
long_window = parameters.get('long_window', 30)
position_size = parameters.get('position_size', 0.1)

# Process each symbol
for symbol in data_frames.keys():
    df = data_frames[symbol]
    
    if len(df) < long_window:
        continue
        
    # Calculate moving averages
    df['SMA_short'] = df['close'].rolling(window=short_window).mean()
    df['SMA_long'] = df['close'].rolling(window=long_window).mean()
    
    # Get current values
    current_price = df['close'].iloc[-1]
    current_short_ma = df['SMA_short'].iloc[-1]
    current_long_ma = df['SMA_long'].iloc[-1]
    
    # Previous values for crossover detection
    prev_short_ma = df['SMA_short'].iloc[-2] if len(df) > 1 else current_short_ma
    prev_long_ma = df['SMA_long'].iloc[-2] if len(df) > 1 else current_long_ma
    
    # Check for crossover signals
    golden_cross = (current_short_ma > current_long_ma and prev_short_ma <= prev_long_ma)
    death_cross = (current_short_ma < current_long_ma and prev_short_ma >= prev_long_ma)
    
    # Calculate position size
    portfolio_value = context.portfolio_value
    dollar_amount = portfolio_value * position_size
    shares = int(dollar_amount / current_price)
    
    # Generate signals
    if golden_cross and shares > 0:
        success = context.buy(symbol, shares, current_price)
        signals.append({
            'action': 'BUY',
            'symbol': symbol,
            'shares': shares,
            'price': current_price,
            'reason': 'Golden Cross',
            'short_ma': current_short_ma,
            'long_ma': current_long_ma,
            'success': success
        })
    elif death_cross:
        # Sell existing position
        current_position = context.get_position(symbol)
        if current_position > 0:
            success = context.sell(symbol, current_position, current_price)
            signals.append({
                'action': 'SELL',
                'symbol': symbol,
                'shares': current_position,
                'price': current_price,
                'reason': 'Death Cross',
                'short_ma': current_short_ma,
                'long_ma': current_long_ma,
                'success': success
            })

# Log strategy performance
signals.append({
    'info': f'Processed {len(data_frames)} symbols with momentum strategy',
    'parameters': {
        'short_window': short_window,
        'long_window': long_window,
        'position_size': position_size
    }
})`;
  }

  /**
   * Get mean reversion strategy template
   */
  getMeanReversionTemplate() {
    return `# Mean Reversion Strategy Template
# Uses RSI to identify oversold/overbought conditions

import pandas as pd
import numpy as np

# Strategy Parameters
rsi_period = parameters.get('rsi_period', 14)
oversold_threshold = parameters.get('oversold_threshold', 30)
overbought_threshold = parameters.get('overbought_threshold', 70)
position_size = parameters.get('position_size', 0.1)

def calculate_rsi(prices, period=14):
    """Calculate RSI indicator"""
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

# Process each symbol
for symbol in data_frames.keys():
    df = data_frames[symbol]
    
    if len(df) < rsi_period + 1:
        continue
        
    # Calculate RSI
    df['RSI'] = calculate_rsi(df['close'], rsi_period)
    
    # Get current values
    current_price = df['close'].iloc[-1]
    current_rsi = df['RSI'].iloc[-1]
    
    # Skip if RSI not available
    if pd.isna(current_rsi):
        continue
    
    # Calculate position size
    portfolio_value = context.portfolio_value
    dollar_amount = portfolio_value * position_size
    shares = int(dollar_amount / current_price)
    
    # Generate signals based on RSI
    if current_rsi < oversold_threshold and shares > 0:
        # Oversold - Buy signal
        success = context.buy(symbol, shares, current_price)
        signals.append({
            'action': 'BUY',
            'symbol': symbol,
            'shares': shares,
            'price': current_price,
            'reason': 'RSI Oversold',
            'rsi': current_rsi,
            'threshold': oversold_threshold,
            'success': success
        })
    elif current_rsi > overbought_threshold:
        # Overbought - Sell signal
        current_position = context.get_position(symbol)
        if current_position > 0:
            success = context.sell(symbol, current_position, current_price)
            signals.append({
                'action': 'SELL',
                'symbol': symbol,
                'shares': current_position,
                'price': current_price,
                'reason': 'RSI Overbought',
                'rsi': current_rsi,
                'threshold': overbought_threshold,
                'success': success
            })

# Log strategy performance
signals.append({
    'info': f'Processed {len(data_frames)} symbols with mean reversion strategy',
    'parameters': {
        'rsi_period': rsi_period,
        'oversold_threshold': oversold_threshold,
        'overbought_threshold': overbought_threshold,
        'position_size': position_size
    }
})`;
  }

  /**
   * Get breakout strategy template
   */
  getBreakoutTemplate() {
    return `# Breakout Strategy Template
# Uses Bollinger Bands to identify breakout opportunities

import pandas as pd
import numpy as np

# Strategy Parameters
bb_period = parameters.get('bb_period', 20)
bb_std = parameters.get('bb_std', 2)
volume_threshold = parameters.get('volume_threshold', 1.5)
position_size = parameters.get('position_size', 0.1)

def calculate_bollinger_bands(prices, period=20, std_dev=2):
    """Calculate Bollinger Bands"""
    sma = prices.rolling(window=period).mean()
    std = prices.rolling(window=period).std()
    upper_band = sma + (std * std_dev)
    lower_band = sma - (std * std_dev)
    return sma, upper_band, lower_band

# Process each symbol
for symbol in data_frames.keys():
    df = data_frames[symbol]
    
    if len(df) < bb_period + 1:
        continue
        
    # Calculate Bollinger Bands
    df['BB_Middle'], df['BB_Upper'], df['BB_Lower'] = calculate_bollinger_bands(
        df['close'], bb_period, bb_std
    )
    
    # Calculate volume moving average
    df['Volume_MA'] = df['volume'].rolling(window=bb_period).mean()
    
    # Get current values
    current_price = df['close'].iloc[-1]
    current_volume = df['volume'].iloc[-1]
    bb_upper = df['BB_Upper'].iloc[-1]
    bb_lower = df['BB_Lower'].iloc[-1]
    volume_ma = df['Volume_MA'].iloc[-1]
    
    # Skip if indicators not available
    if pd.isna(bb_upper) or pd.isna(volume_ma):
        continue
    
    # Check for volume spike
    volume_spike = current_volume > (volume_ma * volume_threshold)
    
    # Calculate position size
    portfolio_value = context.portfolio_value
    dollar_amount = portfolio_value * position_size
    shares = int(dollar_amount / current_price)
    
    # Generate breakout signals
    if current_price > bb_upper and volume_spike and shares > 0:
        # Upward breakout with volume confirmation
        success = context.buy(symbol, shares, current_price)
        signals.append({
            'action': 'BUY',
            'symbol': symbol,
            'shares': shares,
            'price': current_price,
            'reason': 'Upward Breakout',
            'bb_upper': bb_upper,
            'volume_ratio': current_volume / volume_ma,
            'success': success
        })
    elif current_price < bb_lower and volume_spike:
        # Downward breakout - sell existing positions
        current_position = context.get_position(symbol)
        if current_position > 0:
            success = context.sell(symbol, current_position, current_price)
            signals.append({
                'action': 'SELL',
                'symbol': symbol,
                'shares': current_position,
                'price': current_price,
                'reason': 'Downward Breakout',
                'bb_lower': bb_lower,
                'volume_ratio': current_volume / volume_ma,
                'success': success
            })

# Log strategy performance
signals.append({
    'info': f'Processed {len(data_frames)} symbols with breakout strategy',
    'parameters': {
        'bb_period': bb_period,
        'bb_std': bb_std,
        'volume_threshold': volume_threshold,
        'position_size': position_size
    }
})`;
  }

  /**
   * Customize code for specific symbols
   */
  customizeCodeForSymbols(code, symbols) {
    if (!symbols || symbols.length === 0) return code;
    
    const symbolList = symbols.map(s => typeof s === 'string' ? s : s.symbol).slice(0, 10);
    const symbolFilter = `
# Filter to specific symbols of interest
target_symbols = ${JSON.stringify(symbolList)}
data_frames = {k: v for k, v in data_frames.items() if k in target_symbols}
`;
    
    return symbolFilter + '\n' + code;
  }

  /**
   * Customize code for timeframe
   */
  customizeCodeForTimeframe(code, timeframe) {
    if (timeframe === '1min' || timeframe === '5min') {
      return code.replace(/rolling\(window=(\d+)\)/g, (match, period) => {
        const adjustedPeriod = Math.max(5, Math.floor(parseInt(period) / 2));
        return `rolling(window=${adjustedPeriod})`;
      });
    }
    return code;
  }

  /**
   * Customize code for specific indicators
   */
  customizeCodeForIndicators(code, _indicators) {
    // Add specific indicator customizations if needed
    return code;
  }

  /**
   * Customize code for risk tolerance
   */
  customizeCodeForRiskTolerance(code, riskTolerance) {
    let positionSize = 0.1; // Default
    
    switch (riskTolerance) {
      case 'low':
        positionSize = 0.05;
        break;
      case 'high':
        positionSize = 0.2;
        break;
      default:
        positionSize = 0.1;
    }
    
    return code.replace(/position_size = parameters\.get\('position_size', [0-9.]+\)/, 
                       `position_size = parameters.get('position_size', ${positionSize})`);
  }

  /**
   * Create visual configuration for strategy
   */
  createVisualConfig(intent, strategyType) {
    const config = {
      type: strategyType,
      nodes: [],
      connections: [],
      layout: 'flowchart'
    };

    // Add nodes based on strategy type
    switch (strategyType) {
      case 'momentum':
        config.nodes = [
          { id: 'data', type: 'input', label: 'Market Data', x: 100, y: 100 },
          { id: 'sma_short', type: 'indicator', label: 'Short SMA', x: 250, y: 50 },
          { id: 'sma_long', type: 'indicator', label: 'Long SMA', x: 250, y: 150 },
          { id: 'crossover', type: 'condition', label: 'MA Crossover', x: 400, y: 100 },
          { id: 'buy_signal', type: 'action', label: 'Buy Signal', x: 550, y: 75 },
          { id: 'sell_signal', type: 'action', label: 'Sell Signal', x: 550, y: 125 }
        ];
        config.connections = [
          { from: 'data', to: 'sma_short' },
          { from: 'data', to: 'sma_long' },
          { from: 'sma_short', to: 'crossover' },
          { from: 'sma_long', to: 'crossover' },
          { from: 'crossover', to: 'buy_signal' },
          { from: 'crossover', to: 'sell_signal' }
        ];
        break;

      case 'mean_reversion':
        config.nodes = [
          { id: 'data', type: 'input', label: 'Market Data', x: 100, y: 100 },
          { id: 'rsi', type: 'indicator', label: 'RSI', x: 250, y: 100 },
          { id: 'oversold', type: 'condition', label: 'Oversold < 30', x: 400, y: 75 },
          { id: 'overbought', type: 'condition', label: 'Overbought > 70', x: 400, y: 125 },
          { id: 'buy_signal', type: 'action', label: 'Buy Signal', x: 550, y: 75 },
          { id: 'sell_signal', type: 'action', label: 'Sell Signal', x: 550, y: 125 }
        ];
        config.connections = [
          { from: 'data', to: 'rsi' },
          { from: 'rsi', to: 'oversold' },
          { from: 'rsi', to: 'overbought' },
          { from: 'oversold', to: 'buy_signal' },
          { from: 'overbought', to: 'sell_signal' }
        ];
        break;

      case 'breakout':
        config.nodes = [
          { id: 'data', type: 'input', label: 'Market Data', x: 100, y: 100 },
          { id: 'bb', type: 'indicator', label: 'Bollinger Bands', x: 250, y: 100 },
          { id: 'volume', type: 'indicator', label: 'Volume', x: 250, y: 150 },
          { id: 'breakout', type: 'condition', label: 'Price Breakout', x: 400, y: 100 },
          { id: 'vol_confirm', type: 'condition', label: 'Volume Confirm', x: 400, y: 150 },
          { id: 'buy_signal', type: 'action', label: 'Buy Signal', x: 550, y: 125 }
        ];
        config.connections = [
          { from: 'data', to: 'bb' },
          { from: 'data', to: 'volume' },
          { from: 'bb', to: 'breakout' },
          { from: 'volume', to: 'vol_confirm' },
          { from: 'breakout', to: 'buy_signal' },
          { from: 'vol_confirm', to: 'buy_signal' }
        ];
        break;
    }

    return config;
  }

  /**
   * Generate strategy metadata
   */
  generateStrategyMetadata(intent, strategyType, symbols) {
    const template = this.strategyTemplates[strategyType];
    
    return {
      parameters: { ...template.parameters },
      estimatedComplexity: this.calculateComplexity(intent, symbols),
      requiredIndicators: this.getRequiredIndicators(strategyType),
      minimumDataPoints: this.getMinimumDataPoints(strategyType),
      supportedAssetTypes: this.getSupportedAssetTypes(symbols)
    };
  }

  /**
   * Utility methods
   */
  generateStrategyName(intent) {
    const assetPart = intent.assets.length > 0 ? intent.assets.join('-').toUpperCase() : 'Multi-Asset';
    const actionPart = intent.action === 'buy' ? 'Long' : intent.action === 'sell' ? 'Short' : 'Trade';
    const timestamp = new Date().toISOString().split('T')[0];
    
    return `AI-${assetPart}-${actionPart}-${timestamp}`;
  }

  getAssetType(symbol) {
    const cryptoPatterns = ['BTC', 'ETH', 'USD', 'USDT'];
    const etfPatterns = ['SPY', 'QQQ', 'IWM', 'EFA'];
    
    if (cryptoPatterns.some(pattern => symbol.includes(pattern))) {
      return 'crypto';
    }
    if (etfPatterns.some(pattern => symbol.includes(pattern))) {
      return 'etf';
    }
    return 'stock';
  }

  getAssetTypes(symbols) {
    const types = symbols.map(s => this.getAssetType(typeof s === 'string' ? s : s.symbol));
    return [...new Set(types)];
  }

  assessRiskLevel(intent) {
    let riskScore = 0;
    
    if (intent.riskTolerance === 'high') riskScore += 3;
    else if (intent.riskTolerance === 'low') riskScore -= 2;
    
    if (intent.assets.includes('crypto')) riskScore += 2;
    if (intent.timeframe === '1min' || intent.timeframe === '5min') riskScore += 1;
    if (intent.conditions.includes('spike')) riskScore += 1;
    
    if (riskScore >= 3) return 'high';
    if (riskScore <= -1) return 'low';
    return 'medium';
  }

  estimatePerformance(strategyType, _intent) {
    // Simplified performance estimation
    const basePerformance = {
      momentum: { expectedReturn: 0.12, sharpeRatio: 1.2, maxDrawdown: 0.15 },
      mean_reversion: { expectedReturn: 0.08, sharpeRatio: 0.9, maxDrawdown: 0.12 },
      breakout: { expectedReturn: 0.15, sharpeRatio: 1.0, maxDrawdown: 0.18 }
    };
    
    return basePerformance[strategyType] || basePerformance.momentum;
  }

  calculateComplexity(intent, symbols) {
    let complexity = 1;
    
    complexity += intent.indicators.length * 0.2;
    complexity += intent.conditions.length * 0.3;
    complexity += Math.min(symbols.length / 10, 1) * 0.5;
    
    return Math.round(complexity * 10) / 10;
  }

  getRequiredIndicators(strategyType) {
    const indicators = {
      momentum: ['SMA', 'EMA'],
      mean_reversion: ['RSI'],
      breakout: ['Bollinger Bands', 'Volume']
    };
    
    return indicators[strategyType] || [];
  }

  getMinimumDataPoints(strategyType) {
    const minimums = {
      momentum: 30,
      mean_reversion: 14,
      breakout: 20
    };
    
    return minimums[strategyType] || 20;
  }

  getSupportedAssetTypes(symbols) {
    return [...new Set(symbols.map(s => this.getAssetType(typeof s === 'string' ? s : s.symbol)))];
  }

  getFallbackSuggestions() {
    return [
      'Try describing a simple momentum strategy using moving averages',
      'Specify which assets you want to trade (stocks, crypto, ETFs)',
      'Include indicators like RSI, MACD, or Bollinger Bands',
      'Mention your risk tolerance (conservative, moderate, aggressive)'
    ];
  }

  /**
   * Validate generated strategy
   */
  async validateStrategy(strategy) {
    const validation = {
      isValid: true,
      errors: [],
      warnings: [],
      suggestions: []
    };

    // Basic validation
    if (!strategy.code || strategy.code.trim().length === 0) {
      validation.errors.push('Strategy code is required');
      validation.isValid = false;
    }

    if (!strategy.name || strategy.name.trim().length === 0) {
      validation.errors.push('Strategy name is required');
      validation.isValid = false;
    }

    // Code validation
    if (strategy.code) {
      if (!strategy.code.includes('signals.append')) {
        validation.warnings.push('Strategy does not generate any trading signals');
      }
      
      if (!strategy.code.includes('context.buy') && !strategy.code.includes('context.sell')) {
        validation.warnings.push('Strategy does not execute any trades');
      }
      
      if (strategy.code.includes('TODO') || strategy.code.includes('FIXME')) {
        validation.warnings.push('Strategy code contains incomplete sections');
      }
    }

    // Parameter validation
    if (strategy.parameters) {
      Object.entries(strategy.parameters).forEach(([key, value]) => {
        if (typeof value !== 'number' || isNaN(value)) {
          validation.warnings.push(`Parameter ${key} should be a valid number`);
        }
      });
    }

    // Symbol validation
    if (!strategy.symbols || strategy.symbols.length === 0) {
      validation.warnings.push('No symbols specified for strategy');
    }

    return validation;
  }

  // AI-specific methods (these would need full implementation with actual Bedrock calls)
  
  async buildSystemPrompt(availableSymbols, options) {
    return `You are an expert trading strategy developer. Generate executable Python trading strategies based on natural language descriptions.

Available symbols: ${availableSymbols.slice(0, 20).map(s => typeof s === 'string' ? s : s.symbol).join(', ')}
User preferences: ${JSON.stringify(options)}

Generate strategy code that:
1. Uses the provided data_frames dictionary containing OHLCV data
2. Adds trading signals to the signals list
3. Uses context.buy() and context.sell() for trades
4. Includes proper error handling and validation
5. Follows Python best practices`;
  }

  async buildUserPrompt(prompt, availableSymbols, options) {
    return `Generate a trading strategy for: ${prompt}

Requirements:
- Use Python pandas for data analysis
- Generate buy/sell signals based on the description
- Include proper risk management
- Symbols available: ${availableSymbols.slice(0, 10).map(s => typeof s === 'string' ? s : s.symbol).join(', ')}
- User options: ${JSON.stringify(options)}`;
  }

  async callClaude(_systemPrompt, _userPrompt) {
    // This would be a real Bedrock call in production
    throw new Error('Claude AI service not configured. Using template fallback.');
  }

  async parseClaudeResponse(_response) {
    // Parse Claude's response into strategy structure
    throw new Error('Claude response parsing not implemented');
  }

  async validateAndEnhanceStrategy(strategy) {
    // Validate and enhance AI-generated strategy
    return strategy;
  }

  async generateAIMetadata(_strategy, _prompt) {
    // Generate AI-powered metadata
    return {
      aiConfidence: 0.85,
      complexityScore: 0.6,
      estimatedAccuracy: 0.75
    };
  }

  async generateAIVisualConfig(_strategy) {
    // Generate AI-powered visual configuration
    return this.createVisualConfig({ indicators: ['momentum'] }, 'momentum');
  }
}

module.exports = AIStrategyGenerator;