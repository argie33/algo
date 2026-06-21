#!/usr/bin/env python3
"""Migration: Add configurable grade thresholds to algo_config.

ISSUE #31 FIX: Make hardcoded grade thresholds configurable via the algo_config database table.

Previously, grade thresholds were hardcoded in:
  - algo_swing_score.py: 85/75/65/55/45 for A+/A/B/C/D
  - load_swing_trader_scores.py: 85/75/65/55/45 for A+/A/B/C/D
  - algo_advanced_filters.py: 90/80/70/60/50 for A+/A/B/C/D

This migration adds configurable thresholds to algo_config:
  - swing_grade_threshold_aplus through swing_grade_threshold_d (85/75/65/55/45 defaults)
  - advanced_filters_grade_threshold_aplus through advanced_filters_grade_threshold_d (90/80/70/60/50 defaults)

All code has been updated to load these values dynamically from the database.
"""

from utils.db.context import DatabaseContext


DESCRIPTION = "Add configurable grade thresholds to algo_config"


def up():
    """Add configurable grade thresholds to algo_config."""
    with DatabaseContext("write") as cur:
        cur.execute("""
            INSERT INTO algo_config (key, value, value_type, description, updated_by)
            VALUES
                ('swing_grade_threshold_aplus', '85', 'int', 'Swing score: A+ grade threshold (score >= this value)', 'migration'),
                ('swing_grade_threshold_a', '75', 'int', 'Swing score: A grade threshold (score >= this value)', 'migration'),
                ('swing_grade_threshold_b', '65', 'int', 'Swing score: B grade threshold (score >= this value)', 'migration'),
                ('swing_grade_threshold_c', '55', 'int', 'Swing score: C grade threshold (score >= this value)', 'migration'),
                ('swing_grade_threshold_d', '45', 'int', 'Swing score: D grade threshold (score >= this value)', 'migration'),
                ('advanced_filters_grade_threshold_aplus', '90', 'int', 'Advanced filters: A+ grade threshold (score >= this value)', 'migration'),
                ('advanced_filters_grade_threshold_a', '80', 'int', 'Advanced filters: A grade threshold (score >= this value)', 'migration'),
                ('advanced_filters_grade_threshold_b', '70', 'int', 'Advanced filters: B grade threshold (score >= this value)', 'migration'),
                ('advanced_filters_grade_threshold_c', '60', 'int', 'Advanced filters: C grade threshold (score >= this value)', 'migration'),
                ('advanced_filters_grade_threshold_d', '50', 'int', 'Advanced filters: D grade threshold (score >= this value)', 'migration')
            ON CONFLICT (key) DO NOTHING
        """)


def down():
    """Remove configurable grade thresholds from algo_config."""
    with DatabaseContext("write") as cur:
        cur.execute("""
            DELETE FROM algo_config
            WHERE key IN (
                'swing_grade_threshold_aplus', 'swing_grade_threshold_a', 'swing_grade_threshold_b',
                'swing_grade_threshold_c', 'swing_grade_threshold_d',
                'advanced_filters_grade_threshold_aplus', 'advanced_filters_grade_threshold_a',
                'advanced_filters_grade_threshold_b', 'advanced_filters_grade_threshold_c',
                'advanced_filters_grade_threshold_d'
            )
        """)
