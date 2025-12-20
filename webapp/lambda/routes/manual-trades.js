// Manual trades endpoints - CRUD operations for manually recorded trades
// Works with the existing 'trades' table in the database
const express = require('express');

const { query: dbQuery } = require('../utils/database');

const router = express.Router();

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

    return res.json({
      data: result.rows || [],
      count: result.rowCount || 0,
      success: true
    });
  } catch (err) {
    console.error('Error fetching manual trades:', err.message);
    return res.status(500).json({
      error: 'Failed to fetch trades',
      success: false
    });
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
      return res.status(404).json({
        error: 'Trade not found',
        success: false
      });
    }

    return res.json({
      data: result.rows[0],
      success: true
    });
  } catch (err) {
    console.error('Error fetching trade:', err.message);
    return res.status(500).json({
      error: 'Failed to fetch trade',
      success: false
    });
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
      return res.status(400).json({
        error: 'Missing required fields: symbol, trade_type, quantity, price, execution_date',
        success: false
      });
    }

    // Validate trade_type (must be 3 chars for DB: BUY/SEL)
    const tradeType = trade_type.toLowerCase() === 'buy' ? 'BUY' : trade_type.toLowerCase() === 'sell' ? 'SEL' : null;
    if (!tradeType) {
      return res.status(400).json({
        error: 'trade_type must be "buy" or "sell"',
        success: false
      });
    }

    // Validate numbers
    const qty = parseFloat(quantity);
    const prc = parseFloat(price);
    const comm = commission !== undefined && commission !== null ? parseFloat(commission) : null;

    // Validate commission if provided
    if (comm !== null && isNaN(comm)) {
      return res.status(400).json({
        error: 'commission must be a valid number',
        success: false
      });
    }

    if (isNaN(qty) || qty <= 0 || isNaN(prc) || prc <= 0) {
      return res.status(400).json({
        error: 'quantity and price must be positive numbers',
        success: false
      });
    }

    // Validate date
    const tradeDate = new Date(execution_date);
    if (isNaN(tradeDate.getTime())) {
      return res.status(400).json({
        error: 'Invalid execution_date format',
        success: false
      });
    }
    if (tradeDate > new Date()) {
      return res.status(400).json({
        error: 'execution_date cannot be in the future',
        success: false
      });
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
      return res.status(500).json({
        error: 'Failed to create trade',
        success: false
      });
    }

    const trade = result.rows[0];

    // Update portfolio_holdings with the new position (for buy/sell trades)
    if (['BUY', 'SEL'].includes(tradeType)) {
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
    return res.status(500).json({
      error: 'Failed to create trade',
      details: err.message,
      success: false
    });
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
      'SELECT symbol, type, quantity, execution_price FROM trades WHERE id = $1',
      [id]
    );

    if (existingResult.rowCount === 0) {
      return res.status(404).json({
        error: 'Trade not found',
        success: false
      });
    }

    const existing = existingResult.rows[0];

    // Prepare update values
    const newSymbol = symbol ? symbol.toUpperCase() : existing.symbol;
    const newType = trade_type ? (trade_type.toLowerCase() === 'buy' ? 'BUY' : 'SEL') : existing.type;
    const newQty = quantity !== undefined ? parseFloat(quantity) : existing.quantity;
    const newPrice = price !== undefined ? parseFloat(price) : existing.execution_price;
    const newComm = commission !== undefined ? parseFloat(commission) : null;
    const newDate = execution_date || new Date().toISOString();

    // Validate
    if (newQty <= 0 || newPrice <= 0) {
      return res.status(400).json({
        error: 'quantity and price must be positive numbers',
        success: false
      });
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
      return res.status(404).json({
        error: 'Trade not found',
        success: false
      });
    }

    // Recompute portfolio holdings for the symbol
    if (['BUY', 'SEL'].includes(existing.type)) {
      try {
        await recomputeHoldings(existing.symbol);
      } catch (err) {
        console.warn('Warning: Failed to recompute holdings:', err.message);
      }
    }
    if (['BUY', 'SEL'].includes(newType) && newSymbol !== existing.symbol) {
      try {
        await recomputeHoldings(newSymbol);
      } catch (err) {
        console.warn('Warning: Failed to recompute holdings:', err.message);
      }
    }

    return res.json({
      data: result.rows[0],
      success: true
    });
  } catch (err) {
    console.error('Error updating trade:', err.message);
    return res.status(500).json({
      error: 'Failed to update trade',
      success: false
    });
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
      'SELECT symbol, type FROM trades WHERE id = $1',
      [id]
    );

    if (result.rowCount === 0) {
      return res.status(404).json({
        error: 'Trade not found',
        success: false
      });
    }

    const trade = result.rows[0];

    // Delete trade
    await dbQuery(
      'DELETE FROM trades WHERE id = $1',
      [id]
    );

    // Recompute holdings for that symbol
    if (['BUY', 'SEL'].includes(trade.type)) {
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
    return res.status(500).json({
      error: 'Failed to delete trade',
      success: false
    });
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
  } else if (side === 'SEL') {
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
     WHERE symbol = $1 AND type IN ('BUY', 'SEL')
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
