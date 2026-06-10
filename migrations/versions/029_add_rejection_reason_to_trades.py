"""Add rejection_reason field to algo_trades to capture Alpaca API errors."""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '029_add_rejection_reason'
down_revision = '028_cleanup_hardcoded_user_ids'
branch_labels = None
depends_on = None


def upgrade():
    """Add rejection_reason column to algo_trades."""
    op.add_column(
        'algo_trades',
        sa.Column('rejection_reason', sa.Text(), nullable=True, comment='Error message from Alpaca API when order is rejected')
    )


def downgrade():
    """Remove rejection_reason column from algo_trades."""
    op.drop_column('algo_trades', 'rejection_reason')
