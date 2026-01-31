const express = require("express");
const router = express.Router();
const { query } = require("../utils/database");
const { sendCommunityWelcomeEmail } = require("../utils/email");

// POST /api/community/signup - Submit email to join community
router.post("/signup", async (req, res) => {
  try {
    const { email } = req.body;

    // Validation
    if (!email) {
      return res.status(400).json({
        success: false,
        error: "Email is required"
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

    // Check if email already subscribed
    const existing = await query(
      `SELECT id FROM community_signups
       WHERE LOWER(email) = LOWER($1) AND status = 'active'`,
      [email]
    );

    if (existing.rowCount > 0) {
      return res.status(200).json({
        success: true,
        message: "You're already subscribed to our community!",
        data: {
          already_subscribed: true
        }
      });
    }

    // Save to database
    const result = await query(
      `INSERT INTO community_signups (email, status, subscribed_at, source, ip_address)
       VALUES ($1, 'active', NOW(), 'website', $2)
       RETURNING id, subscribed_at`,
      [email, req.ip || req.connection.remoteAddress || 'unknown']
    );

    console.log(`✅ Community signup received from ${email}`);

    // Send welcome email (if email service is configured)
    try {
      const firstName = email.split('@')[0]; // Extract first name from email
      await sendCommunityWelcomeEmail(email, firstName);
    } catch (emailError) {
      console.warn(`⚠️ Failed to send welcome email to ${email}:`, emailError.message);
      // Don't fail the signup if email fails - just log the warning
    }

    // Return success
    return res.status(201).json({
      success: true,
      message: "Thank you for joining our community! Check your email for updates.",
      data: {
        subscription_id: result.rows[0].id,
        subscribed_at: result.rows[0].subscribed_at
      }
    });

  } catch (error) {
    console.error("Error processing community signup:", error);
    return res.status(500).json({
      success: false,
      error: "Failed to sign up. Please try again later."
    });
  }
});

// GET /api/community/stats - Get community stats (Admin only)
router.get("/stats", async (req, res) => {
  try {
    // TODO: Add authentication middleware here
    // For now, we'll allow access - implement auth as needed

    const result = await query(
      `SELECT
        COUNT(*) as total_subscribers,
        COUNT(CASE WHEN status = 'active' THEN 1 END) as active_subscribers,
        COUNT(CASE WHEN status = 'unsubscribed' THEN 1 END) as unsubscribed,
        COUNT(CASE WHEN subscribed_at >= NOW() - INTERVAL '7 days' THEN 1 END) as new_this_week,
        COUNT(CASE WHEN subscribed_at >= NOW() - INTERVAL '30 days' THEN 1 END) as new_this_month
       FROM community_signups`
    );

    return res.status(200).json({
      success: true,
      data: {
        stats: result.rows[0]
      }
    });

  } catch (error) {
    console.error("Error fetching community stats:", error);
    return res.status(500).json({
      success: false,
      error: "Failed to fetch stats"
    });
  }
});

// GET /api/community/subscribers - Get all subscribers (Admin only)
router.get("/subscribers", async (req, res) => {
  try {
    // TODO: Add authentication middleware here

    const result = await query(
      `SELECT id, email, status, subscribed_at, source
       FROM community_signups
       ORDER BY subscribed_at DESC
       LIMIT 1000`
    );

    return res.status(200).json({
      success: true,
      data: {
        subscribers: result.rows,
        total: result.rowCount
      }
    });

  } catch (error) {
    console.error("Error fetching subscribers:", error);
    return res.status(500).json({
      success: false,
      error: "Failed to fetch subscribers"
    });
  }
});

// POST /api/community/unsubscribe - Unsubscribe from community
router.post("/unsubscribe", async (req, res) => {
  try {
    const { email } = req.body;

    if (!email) {
      return res.status(400).json({
        success: false,
        error: "Email is required"
      });
    }

    // Update subscription status
    const result = await query(
      `UPDATE community_signups
       SET status = 'unsubscribed', unsubscribed_at = NOW()
       WHERE LOWER(email) = LOWER($1)
       RETURNING id`,
      [email]
    );

    if (result.rowCount === 0) {
      return res.status(404).json({
        success: false,
        error: "Email not found in our subscriber list"
      });
    }

    console.log(`✅ Unsubscribed: ${email}`);

    return res.status(200).json({
      success: true,
      message: "You've been unsubscribed from our community emails."
    });

  } catch (error) {
    console.error("Error processing unsubscribe:", error);
    return res.status(500).json({
      success: false,
      error: "Failed to unsubscribe. Please try again later."
    });
  }
});

module.exports = router;
