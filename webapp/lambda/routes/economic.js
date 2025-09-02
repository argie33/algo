const express = require("express");

const { query } = require("../utils/database");

const router = express.Router();

// Get economic data
router.get("/", async (req, res) => {
  try {
    const page = parseInt(req.query.page) || 1;
    const limit = parseInt(req.query.limit) || 25;
    const offset = (page - 1) * limit;
    const series = req.query.series;

    let whereClause = "";
    const queryParams = [];
    let paramCount = 0;

    if (series) {
      paramCount++;
      whereClause = `WHERE series_id = $${paramCount}`;
      queryParams.push(series);
    }

    const economicQuery = `
      SELECT 
        series_id,
        date,
        value
      FROM economic_data
      ${whereClause}
      ORDER BY series_id, date DESC
      LIMIT $${paramCount + 1} OFFSET $${paramCount + 2}
    `;

    const countQuery = `
      SELECT COUNT(*) as total FROM economic_data ${whereClause}
    `;

    queryParams.push(limit, offset);

    const [economicResult, countResult] = await Promise.all([
      query(economicQuery, queryParams),
      query(countQuery, queryParams.slice(0, paramCount)),
    ]);

    // Add null safety check
    if (!countResult || !countResult.rows || countResult.rows.length === 0) {
      console.warn("Economic data count query returned null result, database may be unavailable");
      return res.status(503).json({
        success: false,
        error: "Database temporarily unavailable",
        message: "Economic data temporarily unavailable - database connection issue",
        data: [],
        pagination: {
          page: page,
          limit: limit,
          total: 0,
          totalPages: 0,
          hasNext: false,
          hasPrev: false
        }
      });
    }
    
    const total = parseInt(countResult.rows[0].total);
    const totalPages = Math.ceil(total / limit);

    if (
      !economicResult ||
      !Array.isArray(economicResult.rows) ||
      economicResult.rows.length === 0
    ) {
      return res.status(404).json({
        success: false,
        error: "No data found for this query"
      });
    }

    res.json({
      data: economicResult.rows,
      pagination: {
        page,
        limit,
        total,
        totalPages,
        hasNext: page < totalPages,
        hasPrev: page > 1,
      },
    });
  } catch (error) {
    console.error("Error fetching economic data:", error);
    res.status(500).json({
      success: false,
      error: "Database error",
      message: error.message
    });
  }
});

// Get economic data (for DataValidation page - matches frontend expectation)
router.get("/data", async (req, res) => {
  try {
    const limit = Math.min(parseInt(req.query.limit) || 50, 100);
    console.log(`Economic data endpoint called with limit: ${limit}`);

    const economicQuery = `
      SELECT series_id, date, value
      FROM economic_data 
      ORDER BY date DESC, series_id ASC
      LIMIT $1
    `;

    const result = await query(economicQuery, [limit]);

    if (!result || !Array.isArray(result.rows) || result.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: "No data found for this query"
      });
    }

    res.json({
      data: result.rows,
      count: result.rows.length,
      limit: limit,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error fetching economic data:", error);
    res.status(500).json({
      success: false,
      error: "Database error",
      message: error.message
    });
  }
});

module.exports = router;