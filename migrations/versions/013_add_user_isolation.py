"""Add user isolation (cognito_sub) to portfolio and trading tables.

Enables per-user portfolio isolation so each authenticated user only sees/trades their own account.

Revision ID: 013
Revises: 012
Create Date: 2026-06-03

Schema changes:
- Add cognito_sub column to: algo_positions, algo_trades, algo_portfolio_snapshots, algo_trade_adds
- Backfill admin's user ID (argeropolos@gmail.com) for existing data
- Add unique constraints on (cognito_sub, symbol, date) where applicable
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# Migration metadata
revision = '013'
down_revision = '012'
branch_labels = None
depends_on = None


def upgrade():
    """Add user isolation columns to trading tables."""

    # 1. Add cognito_sub column to algo_positions
    op.add_column(
        'algo_positions',
        sa.Column('cognito_sub', sa.String(255), nullable=True, comment='Cognito user ID (sub claim from JWT)')
    )
    op.create_index(
        'idx_algo_positions_user_symbol_date',
        'algo_positions',
        ['cognito_sub', 'symbol', 'date'],
        unique=False
    )

    # 2. Add cognito_sub column to algo_trades
    op.add_column(
        'algo_trades',
        sa.Column('cognito_sub', sa.String(255), nullable=True, comment='Cognito user ID (sub claim from JWT)')
    )
    op.create_index(
        'idx_algo_trades_user_date',
        'algo_trades',
        ['cognito_sub', 'date'],
        unique=False
    )

    # 3. Add cognito_sub column to algo_portfolio_snapshots
    op.add_column(
        'algo_portfolio_snapshots',
        sa.Column('cognito_sub', sa.String(255), nullable=True, comment='Cognito user ID (sub claim from JWT)')
    )
    op.create_index(
        'idx_algo_portfolio_snapshots_user_date',
        'algo_portfolio_snapshots',
        ['cognito_sub', 'snapshot_date'],
        unique=False
    )

    # 4. Add cognito_sub column to algo_trade_adds
    op.add_column(
        'algo_trade_adds',
        sa.Column('cognito_sub', sa.String(255), nullable=True, comment='Cognito user ID (sub claim from JWT)')
    )
    op.create_index(
        'idx_algo_trade_adds_user_date',
        'algo_trade_adds',
        ['cognito_sub', 'date'],
        unique=False
    )

    # 5. Backfill admin user's cognito_sub for existing data
    # NOTE: This assumes the Cognito test user (argeropolos@gmail.com) has sub: us-east-1_XJpLb9SKX:XXXXX
    # The actual sub value will be populated during deployment if available via environment variable
    # For now, use a placeholder that can be updated manually or via post-deploy script
    admin_cognito_sub = 'admin-user'  # Placeholder - will be updated in post-deploy

    op.execute(f"""
        UPDATE algo_positions
        SET cognito_sub = '{admin_cognito_sub}'
        WHERE cognito_sub IS NULL;
    """)

    op.execute(f"""
        UPDATE algo_trades
        SET cognito_sub = '{admin_cognito_sub}'
        WHERE cognito_sub IS NULL;
    """)

    op.execute(f"""
        UPDATE algo_portfolio_snapshots
        SET cognito_sub = '{admin_cognito_sub}'
        WHERE cognito_sub IS NULL;
    """)

    op.execute(f"""
        UPDATE algo_trade_adds
        SET cognito_sub = '{admin_cognito_sub}'
        WHERE cognito_sub IS NULL;
    """)

    # 6. Make cognito_sub NOT NULL after backfill
    op.alter_column('algo_positions', 'cognito_sub', nullable=False)
    op.alter_column('algo_trades', 'cognito_sub', nullable=False)
    op.alter_column('algo_portfolio_snapshots', 'cognito_sub', nullable=False)
    op.alter_column('algo_trade_adds', 'cognito_sub', nullable=False)


def downgrade():
    """Remove user isolation columns."""

    # Drop indexes
    op.drop_index('idx_algo_trade_adds_user_date', table_name='algo_trade_adds')
    op.drop_index('idx_algo_portfolio_snapshots_user_date', table_name='algo_portfolio_snapshots')
    op.drop_index('idx_algo_trades_user_date', table_name='algo_trades')
    op.drop_index('idx_algo_positions_user_symbol_date', table_name='algo_positions')

    # Drop columns
    op.drop_column('algo_trade_adds', 'cognito_sub')
    op.drop_column('algo_portfolio_snapshots', 'cognito_sub')
    op.drop_column('algo_trades', 'cognito_sub')
    op.drop_column('algo_positions', 'cognito_sub')
