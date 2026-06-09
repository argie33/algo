// Manual trades endpoints - CRUD operations for manually recorded trades
// Works with the existing 'trades' table in the database
const express = require('express');

const { query: dbQuery } = require('../utils/database');
const { authenticateToken } = require('../middleware/auth');
const { sendSuccess, sendError, sendPaginated } = require('../utils/apiResponse');
const { createInputValidationMiddleware, inputSchemas } = require('../middleware/dataValidationMiddleware');
const logger = require('../utils/logger');
const { validateQueryResult, validateAndCoerceRows, validateAndCoerceRow } = require('../utils/responseValidation');
const router = express.Router();

// Require authentication for all manual trades operations
router.use(authenticateToken);

/**
 * GET /manual-trades - List all manual trades for authenticated user
 */
router.get('/', async (req, res) => {
  try {
    const userId = req.user.sub;
    const result = await dbQuery(
      `SELECT id, symbol, side as trade_type, quantity, execution_price as price,
              trade_date as execution_date
       FROM trades
       WHERE user_id = $1
       ORDER BY trade_date DESC`,
      [userId]
    );

    // Validate result structure
    validateQueryResult(result, { requireRows: false });

    // Validate and coerce row types
    const validated = validateAndCoerceRows(result, {
      id: { type: 'int', required: true },
      symbol: { type: 'string', required: true },
      trade_type: { type: 'string', required: false },
      quantity: { type: 'float', required: false },
      price: { type: 'float', required: false },
      execution_date: { type: 'date', required: false }
    });

    return sendSuccess(res, {
      trades: validated,
      count: validated.length
    });
  } catch (err) {
    console.error('Error fetching manual trades', err);
    return sendError(res, 'Failed to fetch trades', 500, 'DB_ERROR');
  }
});

/**
 * GET /manual-trades/:id - Get a specific manual trade (user's own trades only)
 */
router.get('/:id', async (req, res) => {
  try {
    const { id } = req.params;
    const userId = req.user.sub;

    const result = await dbQuery(
      `SELECT id, symbol, side as trade_type, quantity, execution_price as price,
              trade_date as execution_date
       FROM trades
       WHERE id = $1 AND user_id = $2`,
      [id, userId]
    );

    // Validate result structure
    validateQueryResult(result, { requireRows: false });

    if (result.rowCount === 0) {
      return sendError(res, 'Trade not found', 404, 'NOT_FOUND');
    }

    // Validate and coerce the single row
    const trade = validateAndCoerceRow(result.rows[0], {
      id: { type: 'int', required: true },
      symbol: { type: 'string', required: true },
      trade_type: { type: 'string', required: false },
      quantity: { type: 'float', required: false },
      price: { type: 'float', required: false },
      execution_date: { type: 'date', required: false }
    });

    return sendSuccess(res, trade);
  } catch (err) {
    console.error('Error fetching trade', err);
    return sendError(res, 'Failed to fetch trade', 500, 'DB_ERROR');
  }
});

/**
 * POST /manual-trades - Create a new manual trade
 * Body: { symbol, trade_type (buy|sell), quantity, price, execution_date, commission? }
 */
router.post('/', createInputValidationMiddleware(inputSchemas.manualTrade), async (req, res) => {
  try {
    const { symbol, trade_type, quantity, price, execution_date, commission } = req.body;
    const userId = req.user.sub;

    // Normalize trade type (middleware already validated)
    const tradeType = trade_type.toLowerCase() === 'buy' ? 'BUY' : 'SELL';
    const qty = parseFloat(quantity);
    const prc = parseFloat(price);
    const comm = commission !== undefined && commission !== null ? parseFloat(commission) : null;
    const tradeDate = new Date(execution_date);

    const orderValue = qty * prc;

    // Insert trade with user_id
    const result = await dbQuery(
      `INSERT INTO trades (user_id, symbol, side, quantity, execution_price, trade_date)
       VALUES ($1, $2, $3, $4, $5, $6)
       RETURNING id, symbol, side as trade_type, quantity, execution_price as price,
                 trade_date as execution_date`,
      [userId, symbol.toUpperCase(), tradeType, qty, prc, tradeDate]
    );

    // Validate result structure
    validateQueryResult(result, { minRows: 1, maxRows: 1 });

    const trade = validateAndCoerceRow(result.rows[0], {
      id: { type: 'int', required: true },
      symbol: { type: 'string', required: true },
      trade_type: { type: 'string', required: false },
      quantity: { type: 'float', required: false },
      price: { type: 'float', required: false },
      execution_date: { type: 'date', required: false }
    });

    // Update portfolio_holdings with the new position (for buy/sell trades)
    if (['BUY', 'SELL'].includes(tradeType)) {
      try {
        await updatePortfolioHoldings(userId, symbol.toUpperCase(), tradeType, qty, prc);
      } catch (holdingsErr) {
        console.warn('Warning: Failed to update portfolio holdings:', holdingsErr.message);
        // Don't fail the trade creation if portfolio update fails
      }
    }

    return sendSuccess(res, trade, 201);
  } catch (err) {
    console.error('Error creating trade:', err.message, err.stack);
    return sendError(res, 'Failed to create trade', 500, { details: err.message });
  }
});

/**
 * PATCH /manual-trades/:id - Update a manual trade (user's own trades only)
 */
router.patch('/:id', createInputValidationMiddleware(inputSchemas.manualTrade), async (req, res) => {
  try {
    const { id } = req.params;
    const userId = req.user.sub;
    const { symbol, trade_type, quantity, price, execution_date, commission } = req.body;

    // Get existing trade first (verify user ownership)
    const existingResult = await dbQuery(
      'SELECT symbol, type, quantity, execution_price FROM trades WHERE id = $1 AND user_id = $2',
      [id, userId]
    );

    // Validate existing result
    validateQueryResult(existingResult, { requireRows: false });

    if (existingResult.rowCount === 0) {
      return sendError(res, 'Trade not found', 404);
    }

    const existing = validateAndCoerceRow(existingResult.rows[0], {
      symbol: { type: 'string', required: true },
      type: { type: 'string', required: false },
      quantity: { type: 'float', required: false },
      execution_price: { type: 'float', required: false }
    });

    // Prepare update values
    const newSymbol = symbol ? symbol.toUpperCase() : existing.symbol;
    const newType = trade_type ? (trade_type.toLowerCase() === 'buy' ? 'BUY' : 'SELL') : existing.type;
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

    // Validate update result
    validateQueryResult(result, { minRows: 1, maxRows: 1 });

    if (result.rowCount === 0) {
      return sendError(res, 'Trade not found', 404);
    }

    // Validate and coerce the updated trade
    const updatedTrade = validateAndCoerceRow(result.rows[0], {
      id: { type: 'int', required: true },
      symbol: { type: 'string', required: true },
      trade_type: { type: 'string', required: false },
      quantity: { type: 'float', required: false },
      price: { type: 'float', required: false },
      order_value: { type: 'float', required: false },
      commission: { type: 'float', required: false },
      total_cost: { type: 'float', required: false },
      execution_date: { type: 'date', required: false }
    });

    // Recompute portfolio holdings for the symbol
    if (['BUY', 'SELL'].includes(existing.type)) {
      try {
        await recomputeHoldings(userId, existing.symbol);
      } catch (err) {
        console.warn('Warning: Failed to recompute holdings:', err.message);
      }
    }
    if (['BUY', 'SELL'].includes(newType) && newSymbol !== existing.symbol) {
      try {
        await recomputeHoldings(userId, newSymbol);
      } catch (err) {
        console.warn('Warning: Failed to recompute holdings:', err.message);
      }
    }

    return sendSuccess(res, updatedTrade);
  } catch (err) {
    console.error('Error updating trade:', err.message);
    return sendError(res, 'Failed to update trade', 500);
  }
});

/**
 * DELETE /manual-trades/:id - Delete a manual trade (user's own trades only)
 */
router.delete('/:id', async (req, res) => {
  try {
    const { id } = req.params;
    const userId = req.user.sub;

    // Get trade before deleting (verify user ownership)
    const result = await dbQuery(
      'SELECT symbol, type FROM trades WHERE id = $1 AND user_id = $2',
      [id, userId]
    );

    if (result.rowCount === 0) {
      return sendError(res, 'Trade not found', 404);
    }

    const trade = result.rows[0];

    // Delete trade
    await dbQuery(
      'DELETE FROM trades WHERE id = $1 AND user_id = $2',
      [id, userId]
    );

    // Recompute holdings for that symbol
    if (['BUY', 'SELL'].includes(trade.type)) {
      try {
        await recomputeHoldings(userId, trade.symbol);
      } catch (err) {
        console.warn('Warning: Failed to recompute holdings:', err.message);
      }
    }

    return sendSuccess(res, {});
  } catch (err) {
    console.error('Error deleting trade:', err.message);
    return sendError(res, 'Failed to delete trade', 500);
  }
});

/**
 * Helper: Update portfolio_holdings based on a new trade
 */
async function updatePortfolioHoldings(userId, symbol, side, quantity, price) {

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

    const existing = await dbQuery(
      'SELECT quantity FROM portfolio_holdings WHERE user_id = $1 AND symbol = $2',
      [userId, symbol]
    );
    if (existing.rows.length > 0) {
      await dbQuery(
        `UPDATE portfolio_holdings SET quantity = $3, average_cost = $4, current_price = $5, updated_at = CURRENT_TIMESTAMP
         WHERE user_id = $1 AND symbol = $2`,
        [userId, symbol, newQty, newAvgCost, price]
      );
    } else {
      await dbQuery(
        `INSERT INTO portfolio_holdings (user_id, symbol, quantity, average_cost, current_price, created_at, updated_at)
         VALUES ($1, $2, $3, $4, $5, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)`,
        [userId, symbol, newQty, newAvgCost, price]
      );
    }
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
         SET quantity = $3, updated_at = CURRENT_TIMESTAMP
         WHERE user_id = $1 AND symbol = $2`,
        [userId, symbol, newQty]
      );
    }
  }
}

/**
 * Helper: Recompute holdings by summing all buy/sell trades for a user
 */
async function recomputeHoldings(userId, symbol) {
  const tradesResult = await dbQuery(
    `SELECT type, quantity, execution_price
     FROM trades
     WHERE user_id = $1 AND symbol = $2 AND type IN ('BUY', 'SELL')
     ORDER BY execution_date ASC`,
    [userId, symbol]
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
    const existing = await dbQuery(
      'SELECT quantity FROM portfolio_holdings WHERE user_id = $1 AND symbol = $2',
      [userId, symbol]
    );
    if (existing.rows.length > 0) {
      await dbQuery(
        `UPDATE portfolio_holdings SET quantity = $3, average_cost = $4, updated_at = CURRENT_TIMESTAMP
         WHERE user_id = $1 AND symbol = $2`,
        [userId, symbol, totalQty, avgCost]
      );
    } else {
      await dbQuery(
        `INSERT INTO portfolio_holdings (user_id, symbol, quantity, average_cost, current_price, market_value, created_at, updated_at)
         VALUES ($1, $2, $3, $4, $5, $6, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)`,
        [userId, symbol, totalQty, avgCost, 0, 0]
      );
    }
  }
}

module.exports = router;
