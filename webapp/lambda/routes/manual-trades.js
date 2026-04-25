// Manual trades endpoints - CRUD operations for manually recorded trades
// Works with the existing 'trades' table in the database
const express = require('express');

const { query: dbQuery } = require('../utils/database');
const { authenticateToken } = require('../middleware/auth');
const { sendSuccess, sendError, sendPaginated } = require('../utils/apiResponse');
const router = express.Router();

// Require authentication for all manual trades operations
router.use(authenticateToken);

/**
 * GET /manual-trades - List all manual trades
 */
router.get('/', async (req, res) => {
  try {
    const result = await dbQuery(
      `SELECT id, symbol, type as trade_type, quantity, execution_price as price,
              order_value,
              commission,
              CASE WHEN commission IS NOT NULL THEN order_value + commission ELSE NULL END as total_cost,
              execution_date
       FROM trades
       ORDER BY execution_date DESC`,
      []
    );

    return sendSuccess(res, {
      data: result.rows || [],
      count: result.rowCount || 0}));
  } catch (err) {
    console.error('Error fetching manual trades:', err.message);
    return sendError(res, 'Failed to fetch trades', 500);
  }
});

/**
 * GET /manual-trades/:id - Get a specific manual trade
 */
router.get('/:id', async (req, res) => {
  try {
    const { id } = req.params;

    const result = await dbQuery(
      `SELECT id, symbol, type as trade_type, quantity, execution_price as price,
              order_value,
              commission,
              CASE WHEN commission IS NOT NULL THEN order_value + commission ELSE NULL END as total_cost,
              execution_date
       FROM trades
       WHERE id = $1`,
      [id]
    );

    if (result.rowCount === 0) {
      return sendError(res, 'Trade not found', 404);
    }

    return sendSuccess(res, {
      data: result.rows[0]}));
  } catch (err) {
    console.error('Error fetching trade:', err.message);
    return sendError(res, 'Failed to fetch trade', 500);
  }
});

/**
 * POST /manual-trades - Create a new manual trade
 * Body: { symbol, trade_type (buy|sell), quantity, price, execution_date, commission? }
 */
router.post('/', async (req, res) => {
  try {
    const { symbol, trade_type, quantity, price, execution_date, commission } = req.body;

    // Validate required fields
    if (!symbol || !trade_type || quantity === undefined || price === undefined || !execution_date) {
      return sendError(res, 'Missing required fields: symbol, trade_type, quantity, price, execution_date', 400);
    }

    // Validate trade_type (must be 3 chars for DB: BUY/SEL)
    const tradeType = trade_type.toLowerCase() === 'buy' ? 'BUY' : trade_type.toLowerCase() === 'sell' ? 'SELL' : null;
    if (!tradeType) {
      return sendError(res, 'trade_type must be "buy" or "sell"', 400);
    }

    // Validate numbers
    const qty = parseFloat(quantity);
    const prc = parseFloat(price);
    const comm = commission !== undefined && commission !== null ? parseFloat(commission) : null;

    // Validate commission if provided
    if (comm !== null && isNaN(comm)) {
      return sendError(res, 'commission must be a valid number', 400);
    }

    if (isNaN(qty) || qty <= 0 || isNaN(prc) || prc <= 0) {
      return sendError(res, 'quantity and price must be positive numbers', 400);
    }

    // Validate date
    const tradeDate = new Date(execution_date);
    if (isNaN(tradeDate.getTime())) {
      return sendError(res, 'Invalid execution_date format', 400);
    }
    if (tradeDate > new Date()) {
      return sendError(res, 'execution_date cannot be in the future', 400);
    }

    const orderValue = qty * prc;

    // Insert trade
    const result = await dbQuery(
      `INSERT INTO trades (symbol, type, quantity, execution_price, execution_date, order_value, commission)
       VALUES ($1, $2, $3, $4, $5, $6, $7)
       RETURNING id, symbol, type as trade_type, quantity, execution_price as price,
                 order_value,
                 commission,
                 CASE WHEN commission IS NOT NULL THEN order_value + commission ELSE NULL END as total_cost,
                 execution_date`,
      [symbol.toUpperCase(), tradeType, qty, prc, tradeDate, orderValue, comm]
    );

    if (result.rowCount === 0) {
      return sendError(res, 'Failed to create trade', 500);
    }

    const trade = result.rows[0];

    // Update portfolio_holdings with the new position (for buy/sell trades)
    if (['BUY', 'SELL'].includes(tradeType)) {
      try {
        await updatePortfolioHoldings(symbol.toUpperCase(), tradeType, qty, prc);
      } catch (holdingsErr) {
        console.warn('Warning: Failed to update portfolio holdings:', holdingsErr.message);
        // Don't fail the trade creation if portfolio update fails
      }
    }

    return res.status(201).json({
      data: trade,
      success: true
    });
  } catch (err) {
    console.error('Error creating trade:', err.message, err.stack);
    return sendError(res, 'Failed to create trade', 500);
  }
});

/**
 * PATCH /manual-trades/:id - Update a manual trade
 */
router.patch('/:id', async (req, res) => {
  try {
    const { id } = req.params;
    const { symbol, trade_type, quantity, price, execution_date, commission } = req.body;

    // Get existing trade first
    const existingResult = await dbQuery(
      'SELECT symbol, side, quantity, execution_price FROM trades WHERE id = $1',
      [id]
    );

    if (existingResult.rowCount === 0) {
      return sendError(res, 'Trade not found', 404);
    }

    const existing = existingResult.rows[0];

    // Prepare update values
    const newSymbol = symbol ? symbol.toUpperCase() : existing.symbol;
    const newType = trade_type ? (trade_type.toLowerCase() === 'buy' ? 'BUY' : 'SELL') : existing.side;
    const newQty = quantity !== undefined ? parseFloat(quantity) : existing.quantity;
    const newPrice = price !== undefined ? parseFloat(price) : existing.execution_price;
    const newComm = commission !== undefined ? parseFloat(commission) : null;
    const newDate = execution_date || new Date().toISOString();

    // Validate
    if (newQty <= 0 || newPrice <= 0) {
      return sendError(res, 'quantity and price must be positive numbers', 400);
    }

    const newOrderValue = newQty * newPrice;

    // Update trade
    const result = await dbQuery(
      `UPDATE trades
       SET symbol = $1, type = $2, quantity = $3, execution_price = $4, execution_date = $5, order_value = $6, commission = $7
       WHERE id = $8
       RETURNING id, symbol, type as trade_type, quantity, execution_price as price,
                 order_value,
                 commission,
                 CASE WHEN commission IS NOT NULL THEN order_value + commission ELSE NULL END as total_cost,
                 execution_date`,
      [newSymbol, newType, newQty, newPrice, newDate, newOrderValue, newComm, id]
    );

    if (result.rowCount === 0) {
      return sendError(res, 'Trade not found', 404);
    }

    // Recompute portfolio holdings for the symbol
    if (['BUY', 'SELL'].includes(existing.type)) {
      try {
        await recomputeHoldings(existing.symbol);
      } catch (err) {
        console.warn('Warning: Failed to recompute holdings:', err.message);
      }
    }
    if (['BUY', 'SELL'].includes(newType) && newSymbol !== existing.symbol) {
      try {
        await recomputeHoldings(newSymbol);
      } catch (err) {
        console.warn('Warning: Failed to recompute holdings:', err.message);
      }
    }

    return sendSuccess(res, {
      data: result.rows[0]}));
  } catch (err) {
    console.error('Error updating trade:', err.message);
    return sendError(res, 'Failed to update trade', 500);
  }
});

/**
 * DELETE /manual-trades/:id - Delete a manual trade
 */
router.delete('/:id', async (req, res) => {
  try {
    const { id } = req.params;

    // Get trade before deleting
    const result = await dbQuery(
      'SELECT symbol, side FROM trades WHERE id = $1',
      [id]
    );

    if (result.rowCount === 0) {
      return sendError(res, 'Trade not found', 404);
    }

    const trade = result.rows[0];

    // Delete trade
    await dbQuery(
      'DELETE FROM trades WHERE id = $1',
      [id]
    );

    // Recompute holdings for that symbol
    if (['BUY', 'SELL'].includes(trade.type)) {
      try {
        await recomputeHoldings(trade.symbol);
      } catch (err) {
        console.warn('Warning: Failed to recompute holdings:', err.message);
      }
    }

    return res.json({
      success: true
    });
  } catch (err) {
    console.error('Error deleting trade:', err.message);
    return sendError(res, 'Failed to delete trade', 500);
  }
});

/**
 * Helper: Update portfolio_holdings based on a new trade
 * Uses 'manual-trades' as the system user_id for manual trade positions
 */
async function updatePortfolioHoldings(symbol, side, quantity, price) {
  const userId = 'manual-trades'; // System user for manual trades

  if (side === 'BUY') {
    const currentResult = await dbQuery(
      'SELECT quantity, average_cost FROM portfolio_holdings WHERE user_id = $1 AND symbol = $2',
      [userId, symbol]
    );

    let newQty, newAvgCost;
    if (currentResult.rowCount === 0) {
      newQty = quantity;
      newAvgCost = price;
    } else {
      const current = currentResult.rows[0];
      newQty = parseFloat(current.quantity) + quantity;
      newAvgCost = (parseFloat(current.quantity) * parseFloat(current.average_cost) + quantity * price) / newQty;
    }

    await dbQuery(
      `INSERT INTO portfolio_holdings (user_id, symbol, quantity, average_cost, current_price, market_value, created_at, updated_at)
       VALUES ($1, $2, $3, $4, $5, $6, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
       ON CONFLICT (user_id, symbol) DO UPDATE SET
         quantity = $3,
         average_cost = $4,
         updated_at = CURRENT_TIMESTAMP`,
      [userId, symbol, newQty, newAvgCost, price, newQty * price]
    );
  } else if (side === 'SELL') {
    const currentResult = await dbQuery(
      'SELECT quantity FROM portfolio_holdings WHERE user_id = $1 AND symbol = $2',
      [userId, symbol]
    );

    if (currentResult.rowCount === 0) {
      console.warn(`Warning: Selling ${quantity} shares of ${symbol} but no position exists`);
      return;
    }

    const current = currentResult.rows[0];
    const newQty = Math.max(0, parseFloat(current.quantity) - quantity);

    if (newQty === 0) {
      await dbQuery(
        'DELETE FROM portfolio_holdings WHERE user_id = $1 AND symbol = $2',
        [userId, symbol]
      );
    } else {
      await dbQuery(
        `UPDATE portfolio_holdings
         SET quantity = $3, market_value = $3 * current_price, updated_at = CURRENT_TIMESTAMP
         WHERE user_id = $1 AND symbol = $2`,
        [userId, symbol, newQty]
      );
    }
  }
}

/**
 * Helper: Recompute holdings by summing all buy/sell trades
 * Uses 'manual-trades' as the system user_id for manual trade positions
 */
async function recomputeHoldings(symbol) {
  const userId = 'manual-trades'; // System user for manual trades

  const tradesResult = await dbQuery(
    `SELECT type, quantity, execution_price
     FROM trades
     WHERE symbol = $1 AND type IN ('BUY', 'SELL')
     ORDER BY execution_date ASC`,
    [symbol]
  );

  let totalQty = 0;
  let totalCost = 0;

  for (const trade of tradesResult.rows) {
    if (trade.type === 'BUY') {
      totalCost += parseFloat(trade.quantity) * parseFloat(trade.execution_price);
      totalQty += parseFloat(trade.quantity);
    } else {
      totalQty -= parseFloat(trade.quantity);
    }
  }

  const avgCost = totalQty > 0 ? totalCost / totalQty : 0;

  if (totalQty <= 0) {
    await dbQuery(
      'DELETE FROM portfolio_holdings WHERE user_id = $1 AND symbol = $2',
      [userId, symbol]
    );
  } else {
    await dbQuery(
      `INSERT INTO portfolio_holdings (user_id, symbol, quantity, average_cost, current_price, market_value, created_at, updated_at)
       VALUES ($1, $2, $3, $4, $5, $6, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
       ON CONFLICT (user_id, symbol) DO UPDATE SET
         quantity = $3,
         average_cost = $4,
         updated_at = CURRENT_TIMESTAMP`,
      [userId, symbol, totalQty, avgCost, 0, 0]
    );
  }
}

module.exports = router;
