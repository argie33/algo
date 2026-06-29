--
-- MIGRATION 037: Create Swing Score Grade Thresholds Configuration
-- Purpose: Move hardcoded grade assignment logic from API to database
-- References: ARCHITECTURAL_AUDIT_CALCULATIONS.md violation #6
--

-- Swing Score Grade Configuration: Define grade thresholds and logic
-- Consolidates hardcoded grade assignment from:
--   1. algo.js /swing-scores endpoint (lines 960-964)
--   2. algo.js /swing-scores endpoint pass_gates logic (line 984)
CREATE TABLE IF NOT EXISTS swing_score_grades (
    grade_id SERIAL PRIMARY KEY,
    grade_letter VARCHAR(5) NOT NULL UNIQUE,       -- 'A', 'B', 'C', 'D'
    min_score INT NOT NULL,                         -- Minimum score for this grade
    max_score INT NOT NULL,                         -- Maximum score for this grade (exclusive)
    description TEXT,                               -- Grade definition
    pass_gates BOOLEAN DEFAULT FALSE,               -- Does this grade pass entry gates?
    fail_reason VARCHAR(255),                       -- Reason if fail_reason is set

    -- Configuration version control
    version INT DEFAULT 1,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(100),

    CONSTRAINT grade_range_check CHECK (min_score < max_score)
);

-- Seed initial grade configuration from current hardcoded values
-- Current logic: score >= 80 = A, >= 70 = B, >= 60 = C, < 60 = D
-- Pass gates threshold is 60
INSERT INTO swing_score_grades (
    grade_letter, min_score, max_score, description, pass_gates, fail_reason, is_active, updated_by
) VALUES
    ('A', 80, 100, 'Excellent swing score — strong entry signal', TRUE, NULL, TRUE, 'migration'),
    ('B', 70, 80, 'Good swing score — acceptable entry signal', TRUE, NULL, TRUE, 'migration'),
    ('C', 60, 70, 'Fair swing score — marginal entry signal', TRUE, NULL, TRUE, 'migration'),
    ('D', 0, 60, 'Poor swing score — entry gate failed', FALSE, 'Score below threshold', TRUE, 'migration')
ON CONFLICT (grade_letter) DO NOTHING;

-- Create index for fast grade lookup by score
CREATE INDEX IF NOT EXISTS idx_swing_score_grades_score
ON swing_score_grades(min_score, max_score)
WHERE is_active;

-- Add grade reference to swing_trader_scores (if not already present)
ALTER TABLE swing_trader_scores
ADD COLUMN IF NOT EXISTS grade_id INT REFERENCES swing_score_grades(grade_id);

CREATE INDEX IF NOT EXISTS idx_swing_trader_scores_grade_id
ON swing_trader_scores(grade_id);
