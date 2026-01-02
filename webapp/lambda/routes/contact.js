const express = require("express");
const router = express.Router();
const { query } = require("../utils/database");

// POST /api/contact - Submit contact form
router.post("/", async (req, res) => {
  try {
    const { name, email, subject, message } = req.body;

    // Validation
    if (!name || !email || !message) {
      return res.status(400).json({
        success: false,
        error: "Name, email, and message are required"
      });
    }

    // Email validation
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(email)) {
      return res.status(400).json({
        success: false,
        error: "Invalid email format"
      });
    }

    // Save to database
    const result = await query(
      `INSERT INTO contact_submissions (name, email, subject, message, submitted_at, status)
       VALUES ($1, $2, $3, $4, NOW(), 'new')
       RETURNING id, created_at`,
      [name, email, subject || null, message]
    );

    console.log(`✅ Contact form received from ${email} (${name})`);

    // Return success with submission ID
    return res.status(201).json({
      success: true,
      message: "Thank you for your message! We'll get back to you soon.",
      data: {
        submission_id: result.rows[0].id,
        submitted_at: result.rows[0].created_at
      }
    });

  } catch (error) {
    console.error("Error processing contact form:", error);
    return res.status(500).json({
      success: false,
      error: "Failed to submit contact form. Please try again later."
    });
  }
});

// GET /api/contact/submissions - Get all submissions (Admin only)
router.get("/submissions", async (req, res) => {
  try {
    // In production, add authentication middleware here
    // For now, we'll allow access - implement auth as needed

    const result = await query(
      `SELECT id, name, email, subject, message, status, submitted_at, reviewed_at
       FROM contact_submissions
       ORDER BY submitted_at DESC
       LIMIT 100`
    );

    return res.status(200).json({
      success: true,
      data: {
        submissions: result.rows,
        total: result.rowCount
      }
    });

  } catch (error) {
    console.error("Error fetching submissions:", error);
    return res.status(500).json({
      success: false,
      error: "Failed to fetch submissions"
    });
  }
});

// GET /api/contact/submissions/:id - Get single submission
router.get("/submissions/:id", async (req, res) => {
  try {
    const { id } = req.params;

    const result = await query(
      `SELECT id, name, email, subject, message, status, submitted_at, reviewed_at
       FROM contact_submissions
       WHERE id = $1`,
      [id]
    );

    if (result.rowCount === 0) {
      return res.status(404).json({
        success: false,
        error: "Submission not found"
      });
    }

    return res.status(200).json({
      success: true,
      data: result.rows[0]
    });

  } catch (error) {
    console.error("Error fetching submission:", error);
    return res.status(500).json({
      success: false,
      error: "Failed to fetch submission"
    });
  }
});

// PATCH /api/contact/submissions/:id - Mark as reviewed
router.patch("/submissions/:id", async (req, res) => {
  try {
    const { id } = req.params;
    const { status } = req.body;

    if (!['new', 'reviewed', 'archived'].includes(status)) {
      return res.status(400).json({
        success: false,
        error: "Invalid status"
      });
    }

    const result = await query(
      `UPDATE contact_submissions
       SET status = $1, reviewed_at = NOW()
       WHERE id = $2
       RETURNING id, status, reviewed_at`,
      [status, id]
    );

    if (result.rowCount === 0) {
      return res.status(404).json({
        success: false,
        error: "Submission not found"
      });
    }

    return res.status(200).json({
      success: true,
      data: result.rows[0]
    });

  } catch (error) {
    console.error("Error updating submission:", error);
    return res.status(500).json({
      success: false,
      error: "Failed to update submission"
    });
  }
});

module.exports = router;
