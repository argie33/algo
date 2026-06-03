"""Finalize user isolation setup - migrate admin to real Cognito sub

Revision ID: 014
Revises: 013
Create Date: 2026-06-03 13:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '014'
down_revision = '013'
branch_labels = None
depends_on = None

# Admin's real Cognito sub from Phase 4 setup
ADMIN_COGNITO_SUB = 'b4f87418-8081-70f3-1e2f-8cc69d5557e1'


def upgrade() -> None:
    """Update admin-user placeholder to real Cognito sub in all tables"""

    # Get the connection
    connection = op.get_bind()

    tables = [
        'algo_positions',
        'algo_trades',
        'algo_portfolio_snapshots',
        'algo_trade_adds'
    ]

    for table in tables:
        # Update any rows with the placeholder admin-user to the real Cognito sub
        sql = f"""
        UPDATE {table}
        SET cognito_sub = '{ADMIN_COGNITO_SUB}'
        WHERE cognito_sub = 'admin-user'
        """
        connection.execute(sa.text(sql))
        connection.commit()


def downgrade() -> None:
    """Revert admin to placeholder (for rollback only)"""

    connection = op.get_bind()

    tables = [
        'algo_positions',
        'algo_trades',
        'algo_portfolio_snapshots',
        'algo_trade_adds'
    ]

    for table in tables:
        sql = f"""
        UPDATE {table}
        SET cognito_sub = 'admin-user'
        WHERE cognito_sub = '{ADMIN_COGNITO_SUB}'
        """
        connection.execute(sa.text(sql))
        connection.commit()
