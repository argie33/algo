"""Migration: Add index on data_patrol_log(created_at DESC) to fix COUNT(*) timeouts.

ISSUE D-002 FIX: data_patrol_log lacks index on (created_at DESC), causing COUNT(*) queries to timeout.

This migration adds a descending index on the created_at column to optimize queries that:
  - Filter or sort by created_at in descending order (most recent first)
  - Perform COUNT(*) operations across the table
  - Use LIMIT/OFFSET patterns with created_at ordering
"""
from alembic import op
import sqlalchemy as sa


def upgrade():
    """Add descending index on data_patrol_log.created_at."""
    op.execute("""
        CREATE INDEX idx_data_patrol_log_created_at_desc ON data_patrol_log(created_at DESC)
    """)


def downgrade():
    """Remove the descending index on data_patrol_log.created_at."""
    op.execute("""
        DROP INDEX IF EXISTS idx_data_patrol_log_created_at_desc
    """)
