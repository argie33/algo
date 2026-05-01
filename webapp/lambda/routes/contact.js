const express = require("express");

const { sendSuccess, sendError, sendPaginated } = require('../utils/apiResponse');
const router = express.Router();
const { query } = require("../utils/database");

// POST /api/contact - Submit contact form
router.post("/", async (req, res) => {
  try {
    const { name, email, subject, message } = req.body;

    // Validation
    if (!name || !email || !message) {
      return sendError(res, 400, "Name, email, and message are required", "MISSING_FIELDS");
    }

    // Email validation
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(email)) {
      return sendError(res, 400, "Invalid email format", "INVALID_EMAIL");
    }

    // Save to database
    const result = await query(
      `INSERT INTO contact_submissions (name, email, subject, message, submitted_at, status)
       VALUES ($1, $2, $3, $4, NOW(), 'new')
       RETURNING id, created_at`,
      [name, email, subject || null, message]
    );

    const submissionId = result.rows[0].id;
    console.log(`✅ Contact form received from ${email} (${name}) - ID: ${submissionId}`);

    // Return success with submission ID
    return sendSuccess(res, {
      submission_id: submissionId,
      submitted_at: result.rows[0].created_at
    }, "Thank you for your message! We'll get back to you soon.", 201);

  } catch (error) {
    console.error("Error processing contact form:", error);
    return sendError(res, 500, "Failed to submit contact form. Please try again later.", "SUBMIT_ERROR");
  }
});

// GET /api/contact/submissions - Get all submissions (Admin only)
router.get("/submissions", async (req, res) => {
  try {
    // In production, add authentication middleware here
    // For now, we'll allow access - implement auth as needed

    // Check if contact_submissions table exists
    const tableExists = await query(
      `SELECT EXISTS (
        SELECT FROM information_schema.tables
        WHERE table_schema = 'public'
        AND table_name = 'contact_submissions'
      )`
    );

    if (!tableExists.rows[0]?.exists) {
      // Table doesn't exist - return empty result
      return sendSuccess(res, {
        submissions: [],
        total: 0
      });
    }

    const result = await query(
      `SELECT id, name, email, subject, message, status, submitted_at, reviewed_at
       FROM contact_submissions
       ORDER BY submitted_at DESC
       LIMIT 100`
    );

    return sendSuccess(res, {
      submissions: result.rows || [],
      total: result.rowCount || 0
    });

  } catch (error) {
    console.error("Error fetching submissions:", error);
    return sendError(res, 500, "Failed to fetch submissions", "FETCH_ERROR");
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
      return sendError(res, 404, "Submission not found", "NOT_FOUND");
    }

    return sendSuccess(res, result.rows[0]);

  } catch (error) {
    console.error("Error fetching submission:", error);
    return sendError(res, 500, "Failed to fetch submission", "FETCH_ERROR");
  }
});

// PATCH /api/contact/submissions/:id - Mark as reviewed
router.patch("/submissions/:id", async (req, res) => {
  try {
    const { id } = req.params;
    const { status } = req.body;

    if (!['new', 'reviewed', 'archived'].includes(status)) {
      return sendError(res, 400, "Invalid status", "INVALID_STATUS");
    }

    const result = await query(
      `UPDATE contact_submissions
       SET status = $1, reviewed_at = NOW()
       WHERE id = $2
       RETURNING id, status, reviewed_at`,
      [status, id]
    );

    if (result.rowCount === 0) {
      return sendError(res, 404, "Submission not found", "NOT_FOUND");
    }

    return sendSuccess(res, result.rows[0]);

  } catch (error) {
    console.error("Error updating submission:", error);
    return sendError(res, 500, "Failed to update submission", "UPDATE_ERROR");
  }
});

module.exports = router;
