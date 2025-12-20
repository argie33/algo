/**
 * Alpaca Trading Integration
 * Handles paper trading and real trading execution
 */

const axios = require("axios");

class AlpacaTrader {
  constructor(apiKey, secretKey, isPaper = true) {
    this.apiKey = apiKey;
    this.secretKey = secretKey;
    this.isPaper = isPaper;

    const baseURL = isPaper
      ? "https://paper-api.alpaca.markets"
      : "https://api.alpaca.markets";

    this.client = axios.create({
      baseURL,
      headers: {
        "APCA-API-KEY-ID": apiKey,
        "APCA-API-SECRET-KEY": secretKey,
      },
    });
  }

  /**
   * Get account information
   */
  async getAccount() {
    try {
      const response = await this.client.get("/v2/account");
      return {
        success: true,
        data: response.data,
      };
    } catch (error) {
      console.error("Error getting account:", error.message);
      return {
        success: false,
        error: error.message,
      };
    }
  }

  /**
   * Get current positions
   */
  async getPositions() {
    try {
      const response = await this.client.get("/v2/positions");
      return {
        success: true,
        data: response.data,
      };
    } catch (error) {
      console.error("Error getting positions:", error.message);
      return {
        success: false,
        error: error.message,
      };
    }
  }

  /**
   * Create a market order
   * @param {string} symbol - Stock symbol
   * @param {number} qty - Quantity
   * @param {string} side - 'buy' or 'sell'
   * @param {object} options - Additional options
   */
  async createOrder(symbol, qty, side, options = {}) {
    try {
      if (!symbol || !qty || !side) {
        throw new Error("Missing required parameters: symbol, qty, side");
      }

      if (!["buy", "sell"].includes(side.toLowerCase())) {
        throw new Error("Side must be 'buy' or 'sell'");
      }

      const orderData = {
        symbol: symbol.toUpperCase(),
        qty: Math.max(1, Math.floor(qty)),
        side: side.toLowerCase(),
        type: options.type || "market",
        time_in_force: options.time_in_force || "day",
        ...options,
      };

      console.log(`📝 Creating order: ${side.toUpperCase()} ${qty} shares of ${symbol}`);

      const response = await this.client.post("/v2/orders", orderData);

      return {
        success: true,
        data: response.data,
        message: `Order created: ${side.toUpperCase()} ${qty} shares of ${symbol} at market price`,
      };
    } catch (error) {
      console.error(`Error creating order for ${symbol}:`, error.message);
      return {
        success: false,
        error: error.message,
        symbol,
        qty,
        side,
      };
    }
  }

  /**
   * Get order status
   */
  async getOrder(orderId) {
    try {
      const response = await this.client.get(`/v2/orders/${orderId}`);
      return {
        success: true,
        data: response.data,
      };
    } catch (error) {
      console.error("Error getting order:", error.message);
      return {
        success: false,
        error: error.message,
      };
    }
  }

  /**
   * Get all orders
   */
  async getOrders(status = "all") {
    try {
      const response = await this.client.get("/v2/orders", {
        params: { status },
      });
      return {
        success: true,
        data: response.data,
      };
    } catch (error) {
      console.error("Error getting orders:", error.message);
      return {
        success: false,
        error: error.message,
      };
    }
  }

  /**
   * Cancel an order
   */
  async cancelOrder(orderId) {
    try {
      await this.client.delete(`/v2/orders/${orderId}`);
      return {
        success: true,
        message: `Order ${orderId} cancelled`,
      };
    } catch (error) {
      console.error("Error cancelling order:", error.message);
      return {
        success: false,
        error: error.message,
      };
    }
  }

  /**
   * Get asset information
   */
  async getAsset(symbol) {
    try {
      const response = await this.client.get(`/v2/assets/${symbol}`);
      return {
        success: true,
        data: response.data,
      };
    } catch (error) {
      console.error("Error getting asset:", error.message);
      return {
        success: false,
        error: error.message,
      };
    }
  }

  /**
   * Execute multiple trades
   * @param {array} trades - Array of trade objects
   */
  async executeTrades(trades) {
    const results = {
      executed: [],
      failed: [],
      total: trades.length,
    };

    for (const trade of trades) {
      const { symbol, side, qty } = trade;

      if (!symbol || !side || !qty) {
        results.failed.push({
          symbol,
          error: "Missing required fields",
        });
        continue;
      }

      const orderResult = await this.createOrder(symbol, qty, side);

      if (orderResult.success) {
        results.executed.push({
          symbol,
          side,
          qty,
          orderId: orderResult.data.id,
          status: "submitted",
        });
      } else {
        results.failed.push({
          symbol,
          side,
          qty,
          error: orderResult.error,
        });
      }

      // Add delay between orders to avoid rate limits
      await new Promise((resolve) => setTimeout(resolve, 500));
    }

    return results;
  }

  /**
   * Get buying power
   */
  async getBuyingPower() {
    try {
      const accountResult = await this.getAccount();
      if (accountResult.success) {
        return {
          success: true,
          buying_power: accountResult.data.buying_power,
          cash: accountResult.data.cash,
          portfolio_value: accountResult.data.portfolio_value,
        };
      }
      return accountResult;
    } catch (error) {
      console.error("Error getting buying power:", error.message);
      return {
        success: false,
        error: error.message,
      };
    }
  }

  /**
   * Validate trade execution feasibility
   */
  async validateTrade(symbol, qty, side) {
    try {
      // Check if symbol is tradeable
      const assetResult = await this.getAsset(symbol);
      if (!assetResult.success || !assetResult.data.tradable) {
        return {
          valid: false,
          reason: "Symbol not tradeable",
        };
      }

      // Check buying power for buy orders
      if (side.toLowerCase() === "buy") {
        const buyingPowerResult = await this.getBuyingPower();
        if (buyingPowerResult.success) {
          // DATA INTEGRITY: Use REAL stock price, not hardcoded $150 estimate
          // Get current market price for accurate position sizing
          let currentPrice = null;
          try {
            const priceData = await this.getStockPrice(symbol);
            if (priceData && priceData.price) {
              currentPrice = parseFloat(priceData.price);
            }
          } catch (err) {
            console.warn(`Could not fetch real price for ${symbol}, cannot validate position size`);
          }

          // Only validate if we have real price data
          if (currentPrice !== null && currentPrice > 0) {
            const actualCost = qty * currentPrice;
            if (actualCost > buyingPowerResult.buying_power) {
              return {
                valid: false,
                reason: "Insufficient buying power",
                required: actualCost,
                available: buyingPowerResult.buying_power,
              };
            }
          } else {
            // Cannot validate without real price - return warning but don't block
            console.warn(`Position sizing validation skipped for ${symbol} - real price unavailable`);
          }
        }
      }

      return { valid: true };
    } catch (error) {
      console.error("Error validating trade:", error.message);
      return {
        valid: false,
        reason: error.message,
      };
    }
  }
}

/**
 * Initialize Alpaca trader from environment variables
 */
function initializeAlpacaTrader(isPaper = true) {
  const apiKey = process.env.ALPACA_API_KEY;
  const secretKey = process.env.ALPACA_SECRET_KEY;

  if (!apiKey || !secretKey) {
    console.warn(
      "⚠️ Alpaca credentials not configured. Set ALPACA_API_KEY and ALPACA_SECRET_KEY"
    );
    return null;
  }

  return new AlpacaTrader(apiKey, secretKey, isPaper);
}

module.exports = {
  AlpacaTrader,
  initializeAlpacaTrader,
};
