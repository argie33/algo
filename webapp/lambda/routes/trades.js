/**
 * UNIFIED TRADES API
 * Single endpoint for real trade data from Alpaca API + database
 * Consolidates: alpaca (live from API), manual, user, optimization sources
 */

const express = require('express');
const { query: dbQuery, safeFloat, safeInt } = require('../utils/database');
const router = express.Router();

// Alpaca API service
let AlpacaService;
try {
  AlpacaService = require('../utils/alpacaService');
} catch (e) {
  console.warn('⚠️ AlpacaService not available:', e.message);
}

/**
 * GET /api/trades
 * Get all trades with filtering and pagination
 *
 * Query Parameters:
 * - source: alpaca,manual,optimization (comma-separated)
 * - symbol: AAPL,MSFT (comma-separated)
 * - type: buy,sell (comma-separated)
 * - page: page number (default 1)
 * - limit: items per page (default 50, max 500)
 * - sort: date_desc, date_asc, pnl_desc, pnl_asc (default date_desc)
 *
 * Example: GET /api/trades?source=alpaca,manual&symbol=AAPL&type=buy&limit=20&sort=pnl_desc
 */
router.get('/', async (req, res) => {
  try {
    const {
      source = 'alpaca,manual,optimization,user',
      symbol = null,
      type = null,
      page = 1,
      limit = 50,
      sort = 'date_desc'
    } = req.query;

    // Validate and constrain pagination
    const pageNum = Math.max(1, parseInt(page, 10) || 1);
    const pageSize = Math.min(500, Math.max(1, parseInt(limit, 10) || 50));
    const offset = (pageNum - 1) * pageSize;

    // Parse filter values
    const sources = source
      ? source.split(',').map(s => s.trim()).filter(s => s)
      : ['alpaca', 'manual', 'optimization', 'user'];

    const symbols = symbol
      ? symbol.split(',').map(s => s.trim().toUpperCase()).filter(s => s)
      : null;

    const types = type
      ? type.split(',').map(t => t.trim().toLowerCase()).filter(t => ['buy', 'sell'].includes(t))
      : null;

    // Collect ALL trades (Alpaca API + Database)
    let allTrades = [];

    // 1. Try to fetch REAL Alpaca trades if enabled
    console.log('🔍 Trade fetch check - sources:', sources, 'AlpacaService available:', !!AlpacaService);
    if (sources.includes('alpaca') && AlpacaService) {
      try {
        const apiKey = process.env.ALPACA_API_KEY;
        const secretKey = process.env.ALPACA_SECRET_KEY;
        const isPaper = process.env.ALPACA_PAPER_TRADING === 'true';

        console.log('📋 Alpaca credentials check - key:', apiKey ? 'YES' : 'NO', 'secret:', secretKey ? 'YES' : 'NO', 'paper:', isPaper);

        if (apiKey && secretKey) {
          console.log('🔗 Fetching REAL Alpaca trades from API...');
          const alpaca = new AlpacaService(apiKey, secretKey, isPaper);
          const orders = await alpaca.getOrders({ status: 'closed', limit: 500 }) || [];
          console.log(`📊 Alpaca returned ${orders?.length || 0} orders`);

          if (orders && Array.isArray(orders)) {
            orders.forEach(order => {
              if (order.status === 'filled' || (order.filledQty && order.filledQty > 0)) {
                allTrades.push({
                  id: order.id,
                  symbol: order.symbol,
                  type: (order.side || 'buy').toLowerCase(),
                  quantity: safeInt(order.filledQty || order.qty),
                  price: safeFloat(order.filledAvgPrice || order.limitPrice),
                  executionDate: order.filledAt || order.createdAt || new Date().toISOString(),
                  orderValue: (() => {
                    const price = safeFloat(order.filledAvgPrice || order.limitPrice);
                    const qty = safeInt(order.filledQty || order.qty);
                    return price !== null && qty !== null ? price * qty : null;
                  })(),
                  commission: 0,
                  source: 'alpaca',
                  orderId: order.id,
                  broker: 'alpaca',
                  notes: null,
                  status: order.status,
                  closePrice: null,
                  pnlAmount: null,
                  pnlPercentage: null
                });
              }
            });
            console.log(`✅ Fetched ${allTrades.length} real Alpaca trades`);
          }
        } else {
          console.warn('⚠️ Alpaca credentials missing');
        }
      } catch (err) {
        console.warn('⚠️ Failed to fetch Alpaca trades:', err.message);
        console.error('Stack:', err.stack);
      }
    } else {
      if (!sources.includes('alpaca')) console.log('⏭️  Alpaca not in requested sources');
      if (!AlpacaService) console.log('⏭️  AlpacaService not loaded');
    }

    // 2. Get database trades (from trades table)
    try {
      let whereClause = 'WHERE 1=1';
      const params = [];

      // Symbol filter
      if (symbols && symbols.length > 0) {
        whereClause += ` AND symbol = ANY($${params.length + 1}::text[])`;
        params.push(symbols);
      }

      // Type filter (type is 'buy' or 'sell' - matches actual column name)
      if (types && types.length > 0) {
        whereClause += ` AND type = ANY($${params.length + 1}::text[])`;
        params.push(types);
      }

      const dataQuery = `
        SELECT
          id, symbol, type as side, quantity, execution_price as price, execution_date as trade_date,
          order_value as total_amount, commission
        FROM trades
        ${whereClause}
        ORDER BY execution_date DESC
      `;

      const result = await dbQuery(dataQuery, params);
      console.log(`📊 Database query result: ${result.rowCount} trades found`);
      console.log('📋 Query:', dataQuery);
      console.log('📋 Params:', params);

      result.rows.forEach(row => {
        console.log(`📝 Processing trade: ${row.symbol} ${row.side} ${row.quantity}@${row.price}`);

        allTrades.push({
          id: row.id,
          symbol: row.symbol,
          type: (row.side || 'buy').toLowerCase(),
          quantity: parseFloat(row.quantity),
          price: parseFloat(row.price),
          executionDate: row.trade_date,
          orderValue: row.total_amount ? parseFloat(row.total_amount) : null,
          commission: row.commission ? parseFloat(row.commission) : 0,
          source: 'manual',
          orderId: row.id,
          broker: 'manual',
          notes: null,
          status: 'completed',
          closePrice: null,
          pnlAmount: null,
          pnlPercentage: null
        });
      });
    } catch (err) {
      console.warn('⚠️ Failed to fetch database trades:', err.message);
      console.error('Error stack:', err.stack);
    }

    // 3. Sort and filter results
    allTrades.sort((a, b) => {
      if (sort === 'date_asc') {
        return new Date(a.executionDate) - new Date(b.executionDate);
      } else {
        return new Date(b.executionDate) - new Date(a.executionDate);
      }
    });

    // Paginate
    const total = allTrades.length;
    const paginatedTrades = allTrades.slice(offset, offset + pageSize);

    res.json({
      data: {
        trades: paginatedTrades,
        pagination: {
          page: pageNum,
          limit: pageSize,
          total,
          totalPages: Math.ceil(total / pageSize),
          hasNext: pageNum < Math.ceil(total / pageSize),
          hasPrev: pageNum > 1
        },
        filters: {
          sources,
          symbols,
          types,
          sort
        }
      },
      success: true
    });

  } catch (error) {
    console.error('Error fetching trades:', error.message || error);
    res.status(500).json({
      error: 'Failed to fetch trades',
      success: false
    });
  }
});

/**
 * GET /api/trades/summary
 * Get trade statistics - includes REAL Alpaca data + database trades
 */
router.get('/summary', async (req, res) => {
  try {
    let allTrades = [];

    // 1. Fetch REAL Alpaca trades if credentials available
    if (AlpacaService) {
      try {
        const apiKey = process.env.ALPACA_API_KEY;
        const secretKey = process.env.ALPACA_SECRET_KEY;
        const isPaper = process.env.ALPACA_PAPER_TRADING === 'true';

        if (apiKey && secretKey) {
          console.log('🔗 Fetching REAL Alpaca trades for summary...');
          const alpaca = new AlpacaService(apiKey, secretKey, isPaper);
          const orders = await alpaca.getOrders({ status: 'closed', limit: 500 }) || [];

          if (orders && Array.isArray(orders)) {
            orders.forEach(order => {
              if (order.status === 'filled' || (order.filledQty && order.filledQty > 0)) {
                allTrades.push({
                  symbol: order.symbol,
                  type: (order.side || 'buy').toLowerCase(),
                  quantity: safeInt(order.filledQty || order.qty),
                  price: safeFloat(order.filledAvgPrice || order.limitPrice),
                  orderValue: (() => {
                    const price = safeFloat(order.filledAvgPrice || order.limitPrice);
                    const qty = safeInt(order.filledQty || order.qty);
                    return price !== null && qty !== null ? price * qty : null;
                  })(),
                  commission: 0,
                  pnlAmount: null,
                  source: 'alpaca'
                });
              }
            });
            console.log(`✅ Including ${allTrades.length} real Alpaca trades in summary`);
          }
        }
      } catch (err) {
        console.warn('⚠️ Failed to fetch Alpaca trades for summary:', err.message);
      }
    }

    // 2. Get database trades (from trades table)
    try {
      const result = await dbQuery(`
        SELECT
          symbol, type as side, quantity, execution_price as price, order_value as total_amount, commission
        FROM trades
        ORDER BY execution_date DESC
      `);
      console.log(`📊 Summary: Found ${result.rowCount} database trades for summary`);

      result.rows.forEach(row => {
        allTrades.push({
          symbol: row.symbol,
          type: (row.side || 'buy').toLowerCase(),
          quantity: parseFloat(row.quantity),
          price: parseFloat(row.price),
          orderValue: row.total_amount ? parseFloat(row.total_amount) : 0,
          commission: row.commission ? parseFloat(row.commission) : 0,
          pnlAmount: null,
          source: 'manual'
        });
      });
    } catch (err) {
      console.warn('⚠️ Failed to fetch database trades for summary:', err.message);
      console.error('Error stack:', err.stack);
    }

    // 3. Calculate summary statistics from combined trades
    const totalTrades = allTrades.length;
    const buys = allTrades.filter(t => t.type === 'buy').length;
    const sells = allTrades.filter(t => t.type === 'sell').length;
    const tradesWithValue = allTrades.filter(t => t.orderValue !== null);
    const totalValue = tradesWithValue.reduce((sum, t) => sum + t.orderValue, 0);
    const tradesWithCommission = allTrades.filter(t => t.commission !== null);
    const totalCommission = tradesWithCommission.reduce((sum, t) => sum + t.commission, 0);
    const symbols = new Set(allTrades.map(t => t.symbol));
    const sources = new Set(allTrades.map(t => t.source));

    const tradesWithPnL = allTrades.filter(t => t.pnlAmount !== null);
    const winningTrades = tradesWithPnL.filter(t => t.pnlAmount > 0).length;
    const losingTrades = tradesWithPnL.filter(t => t.pnlAmount < 0).length;
    const totalPnL = tradesWithPnL.reduce((sum, t) => sum + t.pnlAmount, 0);
    const avgPnL = tradesWithPnL.length > 0 ? totalPnL / tradesWithPnL.length : 0;
    const winRate = tradesWithPnL.length > 0 ? (winningTrades / tradesWithPnL.length) * 100 : 0;

    res.json({
      data: {
        totalTrades,
        buys,
        sells,
        totalValue: Math.round(totalValue * 100) / 100,
        totalCommission: Math.round(totalCommission * 100) / 100,
        uniqueSymbols: symbols.size,
        uniqueSources: sources.size,
        winningTrades,
        losingTrades,
        totalPnL: Math.round(totalPnL * 100) / 100,
        avgPnL: Math.round(avgPnL * 100) / 100,
        winRate: Math.round(winRate * 100) / 100
      },
      success: true
    });

  } catch (error) {
    console.error('Error fetching trade summary:', error);
    res.status(500).json({
      error: 'Failed to fetch trade summary',
      success: false
    });
  }
});

module.exports = router;
