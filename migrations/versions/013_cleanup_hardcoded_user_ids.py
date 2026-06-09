"""
Migration: Clean up hardcoded user IDs from alpaca sync

Issue: alpacaSyncScheduler was using hardcoded user IDs ('1', '2') instead of actual Cognito UUIDs.
This caused portfolio sync data to be stored under wrong user IDs.

Action: Remove any portfolio_holdings and portfolio_performance records with user_id = '1' or '2'
since these are synthetic IDs that don't correspond to real users.

The scheduler now properly syncs for all registered users using their actual Cognito UUIDs.
"""

from alembic import op
import sqlalchemy as sa


def upgrade():
    """Clean up records with hardcoded user IDs"""
    connection = op.get_bind()

    # Delete portfolio_holdings with hardcoded user IDs
    connection.execute(sa.text(
        "DELETE FROM portfolio_holdings WHERE user_id IN ('1', '2')"
    ))

    # Delete portfolio_performance with hardcoded user IDs
    connection.execute(sa.text(
        "DELETE FROM portfolio_performance WHERE user_id IN ('1', '2')"
    ))

    print("✓ Cleaned up portfolio records with hardcoded user IDs ('1', '2')")


def downgrade():
    """No downgrade - hardcoded data should not be restored"""
    pass
