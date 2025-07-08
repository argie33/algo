const express = require('express');
const { query } = require('../utils/database');
const { authenticateUser } = require('../utils/auth');

const router = express.Router();

// Get all watchlists for a user
router.get('/', authenticateUser, async (req, res) => {
  try {
    const userId = req.user.id;
    
    const result = await query(`
      SELECT w.*, 
             COUNT(wi.id) as item_count
      FROM watchlists w
      LEFT JOIN watchlist_items wi ON w.id = wi.watchlist_id
      WHERE w.user_id = $1
      GROUP BY w.id
      ORDER BY w.created_at DESC
    `, [userId]);
    
    res.json(result.rows);
  } catch (error) {
    console.error('Error fetching watchlists:', error);
    res.status(500).json({ error: 'Failed to fetch watchlists' });
  }
});

// Get watchlist items for a specific watchlist
router.get('/:id/items', authenticateUser, async (req, res) => {
  try {
    const { id } = req.params;
    const userId = req.user.id;
    
    // First verify the watchlist belongs to the user
    const watchlistResult = await query(`
      SELECT id FROM watchlists WHERE id = $1 AND user_id = $2
    `, [id, userId]);
    
    if (watchlistResult.rows.length === 0) {
      return res.status(404).json({ error: 'Watchlist not found' });
    }
    
    const result = await query(`
      SELECT wi.*, 
             pd.price as current_price,
             pd.change_percent as day_change_percent,
             pd.change_amount as day_change_amount
      FROM watchlist_items wi
      LEFT JOIN price_daily pd ON wi.symbol = pd.symbol
      WHERE wi.watchlist_id = $1
      ORDER BY wi.position_order ASC, wi.added_at DESC
    `, [id]);
    
    res.json(result.rows);
  } catch (error) {
    console.error('Error fetching watchlist items:', error);
    res.status(500).json({ error: 'Failed to fetch watchlist items' });
  }
});

// Create a new watchlist
router.post('/', authenticateUser, async (req, res) => {
  try {
    const userId = req.user.id;
    const { name, description, color } = req.body;
    
    if (!name || name.trim() === '') {
      return res.status(400).json({ error: 'Watchlist name is required' });
    }
    
    const result = await query(`
      INSERT INTO watchlists (user_id, name, description, color)
      VALUES ($1, $2, $3, $4)
      RETURNING *
    `, [userId, name.trim(), description || null, color || '#1976d2']);
    
    res.status(201).json(result.rows[0]);
  } catch (error) {
    if (error.code === '23505') { // unique constraint violation
      return res.status(409).json({ error: 'Watchlist name already exists' });
    }
    console.error('Error creating watchlist:', error);
    res.status(500).json({ error: 'Failed to create watchlist' });
  }
});

// Update a watchlist
router.put('/:id', authenticateUser, async (req, res) => {
  try {
    const { id } = req.params;
    const userId = req.user.id;
    const { name, description, color } = req.body;
    
    if (!name || name.trim() === '') {
      return res.status(400).json({ error: 'Watchlist name is required' });
    }
    
    const result = await query(`
      UPDATE watchlists 
      SET name = $1, description = $2, color = $3, updated_at = CURRENT_TIMESTAMP
      WHERE id = $4 AND user_id = $5
      RETURNING *
    `, [name.trim(), description || null, color || '#1976d2', id, userId]);
    
    if (result.rows.length === 0) {
      return res.status(404).json({ error: 'Watchlist not found' });
    }
    
    res.json(result.rows[0]);
  } catch (error) {
    if (error.code === '23505') { // unique constraint violation
      return res.status(409).json({ error: 'Watchlist name already exists' });
    }
    console.error('Error updating watchlist:', error);
    res.status(500).json({ error: 'Failed to update watchlist' });
  }
});

// Delete a watchlist
router.delete('/:id', authenticateUser, async (req, res) => {
  try {
    const { id } = req.params;
    const userId = req.user.id;
    
    const result = await query(`
      DELETE FROM watchlists 
      WHERE id = $1 AND user_id = $2
      RETURNING *
    `, [id, userId]);
    
    if (result.rows.length === 0) {
      return res.status(404).json({ error: 'Watchlist not found' });
    }
    
    res.json({ message: 'Watchlist deleted successfully' });
  } catch (error) {
    console.error('Error deleting watchlist:', error);
    res.status(500).json({ error: 'Failed to delete watchlist' });
  }
});

// Add item to watchlist
router.post('/:id/items', authenticateUser, async (req, res) => {
  try {
    const { id } = req.params;
    const userId = req.user.id;
    const { symbol, notes, alert_price, alert_type, alert_value } = req.body;
    
    if (!symbol || symbol.trim() === '') {
      return res.status(400).json({ error: 'Symbol is required' });
    }
    
    // First verify the watchlist belongs to the user
    const watchlistResult = await query(`
      SELECT id FROM watchlists WHERE id = $1 AND user_id = $2
    `, [id, userId]);
    
    if (watchlistResult.rows.length === 0) {
      return res.status(404).json({ error: 'Watchlist not found' });
    }
    
    // Get the next position order
    const positionResult = await query(`
      SELECT COALESCE(MAX(position_order), 0) + 1 as next_position
      FROM watchlist_items WHERE watchlist_id = $1
    `, [id]);
    
    const nextPosition = positionResult.rows[0].next_position;
    
    const result = await query(`
      INSERT INTO watchlist_items (watchlist_id, symbol, notes, alert_price, alert_type, alert_value, position_order)
      VALUES ($1, $2, $3, $4, $5, $6, $7)
      RETURNING *
    `, [id, symbol.trim().toUpperCase(), notes || null, alert_price || null, alert_type || null, alert_value || null, nextPosition]);
    
    res.status(201).json(result.rows[0]);
  } catch (error) {
    if (error.code === '23505') { // unique constraint violation
      return res.status(409).json({ error: 'Symbol already exists in this watchlist' });
    }
    console.error('Error adding item to watchlist:', error);
    res.status(500).json({ error: 'Failed to add item to watchlist' });
  }
});

// Update watchlist item
router.put('/:id/items/:itemId', authenticateUser, async (req, res) => {
  try {
    const { id, itemId } = req.params;
    const userId = req.user.id;
    const { notes, alert_price, alert_type, alert_value, position_order } = req.body;
    
    // First verify the watchlist belongs to the user
    const watchlistResult = await query(`
      SELECT id FROM watchlists WHERE id = $1 AND user_id = $2
    `, [id, userId]);
    
    if (watchlistResult.rows.length === 0) {
      return res.status(404).json({ error: 'Watchlist not found' });
    }
    
    const result = await query(`
      UPDATE watchlist_items 
      SET notes = $1, alert_price = $2, alert_type = $3, alert_value = $4, position_order = $5
      WHERE id = $6 AND watchlist_id = $7
      RETURNING *
    `, [notes || null, alert_price || null, alert_type || null, alert_value || null, position_order || 0, itemId, id]);
    
    if (result.rows.length === 0) {
      return res.status(404).json({ error: 'Watchlist item not found' });
    }
    
    res.json(result.rows[0]);
  } catch (error) {
    console.error('Error updating watchlist item:', error);
    res.status(500).json({ error: 'Failed to update watchlist item' });
  }
});

// Delete item from watchlist
router.delete('/:id/items/:itemId', authenticateUser, async (req, res) => {
  try {
    const { id, itemId } = req.params;
    const userId = req.user.id;
    
    // First verify the watchlist belongs to the user
    const watchlistResult = await query(`
      SELECT id FROM watchlists WHERE id = $1 AND user_id = $2
    `, [id, userId]);
    
    if (watchlistResult.rows.length === 0) {
      return res.status(404).json({ error: 'Watchlist not found' });
    }
    
    const result = await query(`
      DELETE FROM watchlist_items 
      WHERE id = $1 AND watchlist_id = $2
      RETURNING *
    `, [itemId, id]);
    
    if (result.rows.length === 0) {
      return res.status(404).json({ error: 'Watchlist item not found' });
    }
    
    res.json({ message: 'Item removed from watchlist successfully' });
  } catch (error) {
    console.error('Error removing item from watchlist:', error);
    res.status(500).json({ error: 'Failed to remove item from watchlist' });
  }
});

// Reorder watchlist items
router.post('/:id/items/reorder', authenticateUser, async (req, res) => {
  try {
    const { id } = req.params;
    const userId = req.user.id;
    const { itemIds } = req.body; // Array of item IDs in new order
    
    if (!Array.isArray(itemIds)) {
      return res.status(400).json({ error: 'itemIds must be an array' });
    }
    
    // First verify the watchlist belongs to the user
    const watchlistResult = await query(`
      SELECT id FROM watchlists WHERE id = $1 AND user_id = $2
    `, [id, userId]);
    
    if (watchlistResult.rows.length === 0) {
      return res.status(404).json({ error: 'Watchlist not found' });
    }
    
    // Update position order for each item
    const updatePromises = itemIds.map((itemId, index) => {
      return query(`
        UPDATE watchlist_items 
        SET position_order = $1 
        WHERE id = $2 AND watchlist_id = $3
      `, [index + 1, itemId, id]);
    });
    
    await Promise.all(updatePromises);
    
    res.json({ message: 'Items reordered successfully' });
  } catch (error) {
    console.error('Error reordering watchlist items:', error);
    res.status(500).json({ error: 'Failed to reorder watchlist items' });
  }
});

module.exports = router;