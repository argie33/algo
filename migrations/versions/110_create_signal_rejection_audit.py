"""Create audit table for signal rejections.

Revision ID: 110
Revises: 109
Create Date: 2026-07-19

Track every signal rejection with full details for analysis and debugging.
"""
from alembic import op
import sqlalchemy as sa

# Revision identifiers, used by Alembic.
revision = '110'
down_revision = '109'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create signal rejection audit table."""
    op.create_table(
        'algo_signal_rejections',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('rejection_date', sa.Date, nullable=False, index=True),
        sa.Column('symbol', sa.String(10), nullable=False, index=True),
        sa.Column('rejection_stage', sa.String(50), nullable=False),  # 'phase7', 'phase8_earnings', 'phase8_slippage', etc.
        sa.Column('rejection_reason', sa.String(200), nullable=False),
        sa.Column('entry_price', sa.Numeric(10, 2), nullable=True),
        sa.Column('risk_pct', sa.Numeric(5, 2), nullable=True),
        sa.Column('stop_loss_pct', sa.Numeric(5, 2), nullable=True),
        sa.Column('signal_quality_score', sa.Numeric(5, 2), nullable=True),
        sa.Column('atr', sa.Numeric(8, 4), nullable=True),
        sa.Column('sma_50', sa.Numeric(8, 2), nullable=True),
        sa.Column('market_exposure_pct', sa.Numeric(5, 2), nullable=True),
        sa.Column('notes', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    # Composite index for analysis: (rejection_date, rejection_stage)
    op.create_index(
        'idx_signal_rejections_date_stage',
        'algo_signal_rejections',
        ['rejection_date', 'rejection_stage'],
    )

    # Index for tracking rejections by symbol
    op.create_index(
        'idx_signal_rejections_symbol',
        'algo_signal_rejections',
        ['symbol', 'rejection_date'],
    )


def downgrade() -> None:
    """Drop signal rejection audit table."""
    op.drop_table('algo_signal_rejections')
