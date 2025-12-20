/**
 * DEPRECATED - Response Formatter Middleware
 *
 * This file is deprecated and should not be used.
 *
 * See RULES.md for the unified API response pattern:
 * - Use direct res.json({data: {...}, success: true}) for success
 * - Use res.status(code).json({error: "msg", success: false}) for errors
 * - Use res.json({items: [...], pagination: {...}, success: true}) for paginated lists
 *
 * All routes should use standard Express methods only.
 * Remove this file once all routes are migrated.
 */

// Commented out error - middleware file kept for reference only
// See RULES.md for the unified API response pattern
// throw new Error('responseFormatter middleware is deprecated...');
