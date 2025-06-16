import { BaseEngine, Position, Portfolio, OrderFill, Trade } from '../../types';
import { Config } from '../../config';
import { Logger } from 'pino';

export interface PortfolioMetrics {
  totalValue: number;
  cashBalance: number;
  positionsValue: number;
  dayPnL: number;
  totalPnL: number;
  unrealizedPnL: number;
  realizedPnL: number;
  leverage: number;
  exposure: number;
  updated: number;
}

/**
 * Real-time portfolio and position management engine
 */
export class PortfolioEngine extends BaseEngine {
  private portfolio: Portfolio;
  private positions: Map<string, Position> = new Map();
  private dayStartPositions: Map<string, Position> = new Map();
  private cashBalance: number = 100000; // Starting cash
  private dayStartCash: number = 100000;

  constructor(config: Config, logger: Logger) {
    super('PortfolioEngine', config, logger);
    
    this.portfolio = {
      cash: this.cashBalance,
      portfolio_value: this.cashBalance,
      positions: new Map(),
      day_trade_count: 0,
      pattern_day_trader: false,
      trading_blocked: false,
      account_blocked: false,
      transfers_blocked: false,
      equity: this.cashBalance,
      last_equity: this.cashBalance,
      multiplier: 1,
      buying_power: this.cashBalance,
      initial_margin: 0,
      maintenance_margin: 0,
      sma: 0,
      daytrade_buying_power: this.cashBalance,
      regt_buying_power: this.cashBalance,
      updated_at: Date.now()
    };
  }

  async initialize(): Promise<void> {
    this.logger.info('Initializing Portfolio Engine...');
    
    try {
      // Initialize positions for enabled symbols
      const enabledSymbols = this.config.getEnabledSymbols();
      enabledSymbols.forEach((symbolConfig: any) => {
        const position: Position = {
          symbol: symbolConfig.symbol,
          quantity: 0,
          market_value: 0,
          cost_basis: 0,
          unrealized_pnl: 0,
          realized_pnl: 0,
          average_entry_price: 0,
          last_price: 0,
          updated_at: Date.now()
        };
        
        this.positions.set(symbolConfig.symbol, position);
        this.dayStartPositions.set(symbolConfig.symbol, { ...position });
      });
      
      // Start portfolio monitoring
      this.startPortfolioMonitoring();
      
      this.logger.info('Portfolio Engine initialized successfully');
      
    } catch (error) {
      this.logger.error({ error }, 'Failed to initialize Portfolio Engine');
      throw error;
    }
  }

  async start(): Promise<void> {
    if (this.isRunning) return;
    
    this.logger.info('Starting Portfolio Engine...');
    this.isRunning = true;
    
    this.logger.info('Portfolio Engine started successfully');
  }

  async stop(): Promise<void> {
    if (!this.isRunning) return;
    
    this.logger.info('Stopping Portfolio Engine...');
    this.isRunning = false;
    
    this.logger.info('Portfolio Engine stopped');
  }

  /**
   * Process order fill and update positions
   */
  processFill(fill: OrderFill): void {
    if (!this.isRunning) return;
    
    try {
      const position = this.positions.get(fill.symbol);
      if (!position) {
        this.logger.warn({ symbol: fill.symbol }, 'Position not found for fill');
        return;
      }

      // Update position based on fill
      this.updatePositionWithFill(position, fill);
      
      // Update cash balance
      const cashChange = fill.side === 'buy' 
        ? -(fill.quantity * fill.price + fill.commission)
        : (fill.quantity * fill.price - fill.commission);
      
      this.cashBalance += cashChange;
      
      // Recalculate portfolio metrics
      this.calculatePortfolioMetrics();
      
      // Emit position update
      this.emit('positionUpdate', position);
      
      // Emit P&L update
      const pnlUpdate = {
        symbol: fill.symbol,
        realized_pnl: position.realized_pnl,
        unrealized_pnl: position.unrealized_pnl,
        total_pnl: position.realized_pnl + position.unrealized_pnl,
        timestamp: Date.now()
      };
      
      this.emit('pnlUpdate', pnlUpdate);
      
      this.logger.info({ 
        fill, 
        newPosition: position.quantity,
        cashBalance: this.cashBalance 
      }, 'Position updated from fill');
      
      this.incrementMetric('fills_processed');
      
    } catch (error) {
      this.logger.error({ error, fill }, 'Failed to process fill');
      this.incrementMetric('fill_processing_errors');
    }
  }

  /**
   * Process trade data to update market values and unrealized P&L
   */
  processTrade(trade: Trade): void {
    if (!this.isRunning) return;
    
    try {
      const position = this.positions.get(trade.symbol);
      if (!position) {
        return; // No position in this symbol
      }

      // Update last price
      position.last_price = trade.price;
      
      // Recalculate market value and unrealized P&L
      if (position.quantity !== 0) {
        position.market_value = position.quantity * trade.price;
        position.unrealized_pnl = position.market_value - position.cost_basis;
      }
      
      position.updated_at = Date.now();
      
      // Update portfolio metrics
      this.calculatePortfolioMetrics();
      
      // Update metrics
      this.updateMetric(`${trade.symbol}_last_price`, trade.price);
      this.updateMetric(`${trade.symbol}_market_value`, position.market_value);
      
    } catch (error) {
      this.logger.error({ error, trade }, 'Failed to process trade');
    }
  }

  /**
   * Update position with order fill
   */
  private updatePositionWithFill(position: Position, fill: OrderFill): void {
    const previousQuantity = position.quantity;
    const fillQuantity = fill.side === 'buy' ? fill.quantity : -fill.quantity;
    const newQuantity = previousQuantity + fillQuantity;

    // Calculate realized P&L for closing trades
    let realizedPnL = 0;
    
    if (previousQuantity !== 0 && Math.sign(previousQuantity) !== Math.sign(fillQuantity)) {
      // This is a closing or partially closing trade
      const closedQuantity = Math.min(Math.abs(fillQuantity), Math.abs(previousQuantity));
      const avgExitPrice = fill.price;
      const avgEntryPrice = position.average_entry_price;
      
      if (previousQuantity > 0) {
        // Closing long position
        realizedPnL = closedQuantity * (avgExitPrice - avgEntryPrice);
      } else {
        // Closing short position
        realizedPnL = closedQuantity * (avgEntryPrice - avgExitPrice);
      }
      
      position.realized_pnl += realizedPnL;
    }

    // Update position quantity
    position.quantity = newQuantity;

    // Update average entry price and cost basis
    if (newQuantity === 0) {
      // Position closed
      position.average_entry_price = 0;
      position.cost_basis = 0;
      position.market_value = 0;
      position.unrealized_pnl = 0;
    } else if (Math.sign(newQuantity) === Math.sign(fillQuantity)) {
      // Adding to position or opening new position
      const totalCost = position.cost_basis + (fill.quantity * fill.price);
      const totalQuantity = Math.abs(newQuantity);
      position.average_entry_price = totalCost / totalQuantity;
      position.cost_basis = totalQuantity * position.average_entry_price;
      position.market_value = newQuantity * fill.price;
      position.unrealized_pnl = position.market_value - position.cost_basis;
    }

    position.last_price = fill.price;
    position.updated_at = Date.now();
  }

  /**
   * Calculate portfolio-level metrics
   */
  private calculatePortfolioMetrics(): void {
    let totalPositionValue = 0;
    let totalUnrealizedPnL = 0;
    let totalRealizedPnL = 0;
    let grossExposure = 0;
    let netExposure = 0;

    this.positions.forEach(position => {
      totalPositionValue += position.market_value;
      totalUnrealizedPnL += position.unrealized_pnl;
      totalRealizedPnL += position.realized_pnl;
      grossExposure += Math.abs(position.market_value);
      netExposure += position.market_value;
    });

    const totalValue = this.cashBalance + totalPositionValue;
    const totalPnL = totalRealizedPnL + totalUnrealizedPnL;
    const dayPnL = this.calculateDayPnL();

    // Update portfolio object
    this.portfolio.cash = this.cashBalance;
    this.portfolio.portfolio_value = totalValue;
    this.portfolio.positions = new Map(this.positions);
    this.portfolio.equity = totalValue;
    this.portfolio.updated_at = Date.now();

    // Update metrics
    this.updateMetric('portfolio_value', totalValue);
    this.updateMetric('cash_balance', this.cashBalance);
    this.updateMetric('positions_value', totalPositionValue);
    this.updateMetric('total_pnl', totalPnL);
    this.updateMetric('unrealized_pnl', totalUnrealizedPnL);
    this.updateMetric('realized_pnl', totalRealizedPnL);
    this.updateMetric('day_pnl', dayPnL);
    this.updateMetric('gross_exposure', grossExposure);
    this.updateMetric('net_exposure', netExposure);
    
    const leverage = totalValue > 0 ? grossExposure / totalValue : 0;
    this.updateMetric('leverage', leverage);
  }

  /**
   * Calculate day P&L
   */
  private calculateDayPnL(): number {
    let dayPnL = this.cashBalance - this.dayStartCash;

    this.positions.forEach((position, symbol) => {
      const dayStartPosition = this.dayStartPositions.get(symbol);
      if (dayStartPosition) {
        // P&L from position changes
        const positionPnL = position.realized_pnl - dayStartPosition.realized_pnl;
        const unrealizedPnL = position.unrealized_pnl - dayStartPosition.unrealized_pnl;
        dayPnL += positionPnL + unrealizedPnL;
      }
    });

    return dayPnL;
  }

  /**
   * Start portfolio monitoring
   */
  private startPortfolioMonitoring(): void {
    setInterval(() => {
      this.calculatePortfolioMetrics();
      
      // Check for daily reset
      if (this.shouldResetDailyCounters()) {
        this.resetDailyCounters();
      }
    }, 1000); // Update every second
  }

  /**
   * Check if daily counters should be reset
   */
  private shouldResetDailyCounters(): boolean {
    const now = new Date();
    const hour = now.getHours();
    const minute = now.getMinutes();
    
    // Reset at market open (9:30 AM)
    return hour === 9 && minute === 30;
  }

  /**
   * Reset daily counters
   */
  private resetDailyCounters(): void {
    this.dayStartCash = this.cashBalance;
    
    this.positions.forEach((position, symbol) => {
      this.dayStartPositions.set(symbol, { ...position });
    });
    
    this.logger.info('Daily portfolio counters reset');
  }

  /**
   * Get current portfolio
   */
  getPortfolio(): Portfolio {
    return { ...this.portfolio };
  }

  /**
   * Get all positions
   */
  getPositions(): Map<string, Position> {
    return new Map(this.positions);
  }

  /**
   * Get position for specific symbol
   */
  getPosition(symbol: string): Position | undefined {
    const position = this.positions.get(symbol);
    return position ? { ...position } : undefined;
  }

  /**
   * Get portfolio metrics
   */
  getPortfolioMetrics(): PortfolioMetrics {
    const totalPositionValue = Array.from(this.positions.values())
      .reduce((sum, pos) => sum + pos.market_value, 0);
    
    const totalUnrealizedPnL = Array.from(this.positions.values())
      .reduce((sum, pos) => sum + pos.unrealized_pnl, 0);
    
    const totalRealizedPnL = Array.from(this.positions.values())
      .reduce((sum, pos) => sum + pos.realized_pnl, 0);

    const totalValue = this.cashBalance + totalPositionValue;
    const grossExposure = Array.from(this.positions.values())
      .reduce((sum, pos) => sum + Math.abs(pos.market_value), 0);

    return {
      totalValue,
      cashBalance: this.cashBalance,
      positionsValue: totalPositionValue,
      dayPnL: this.calculateDayPnL(),
      totalPnL: totalRealizedPnL + totalUnrealizedPnL,
      unrealizedPnL: totalUnrealizedPnL,
      realizedPnL: totalRealizedPnL,
      leverage: totalValue > 0 ? grossExposure / totalValue : 0,
      exposure: grossExposure,
      updated: Date.now()
    };
  }

  /**
   * Get buying power
   */
  getBuyingPower(): number {
    // Simplified buying power calculation
    return Math.max(0, this.cashBalance);
  }

  /**
   * Check if sufficient buying power for order
   */
  hasSufficientBuyingPower(symbol: string, quantity: number, price: number): boolean {
    const orderValue = quantity * price;
    const buyingPower = this.getBuyingPower();
    
    return buyingPower >= orderValue;
  }

  /**
   * Get maximum position size for symbol
   */
  getMaxPositionSize(symbol: string): number {
    const symbolConfig = this.config.getSymbolConfig(symbol);
    return symbolConfig?.maxPositionSize || 0;
  }

  /**
   * Get current exposure for symbol
   */
  getSymbolExposure(symbol: string): number {
    const position = this.positions.get(symbol);
    return position ? Math.abs(position.market_value) : 0;
  }
}
