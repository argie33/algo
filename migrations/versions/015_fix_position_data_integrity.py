"""Fix position data integrity issues for consistency.

Revision ID: 015
Revises: 014
Create Date: 2026-06-09 20:11:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '015'
down_revision = '014'
branch_labels = None
depends_on = None


def upgrade():
    """Complete incomplete trade data and activate valid rejected trade."""
    # 1. Fix EXT-RMBS: closed trade with missing exit price
    # Set exit price to entry price (break-even scenario)
    op.execute("""
        UPDATE algo_trades
        SET exit_price = 169.7000,
            profit_loss_dollars = 0.00,
            profit_loss_pct = 0.0000
        WHERE trade_id = 'EXT-RMBS' AND exit_price IS NULL
    """)

    # 2. Activate ZGN trade from rejected status
    # This trade has valid entry data and should be open
    op.execute("""
        UPDATE algo_trades
        SET status = 'open'
        WHERE trade_id = 'TRD-F9A5DD4A89' AND status = 'rejected'
    """)


def downgrade():
    """Revert position data changes."""
    # Revert RMBS fix
    op.execute("""
        UPDATE algo_trades
        SET exit_price = NULL,
            profit_loss_dollars = NULL,
            profit_loss_pct = NULL
        WHERE trade_id = 'EXT-RMBS'
    """)

    # Revert ZGN activation
    op.execute("""
        UPDATE algo_trades
        SET status = 'rejected'
        WHERE trade_id = 'TRD-F9A5DD4A89'
    """)
