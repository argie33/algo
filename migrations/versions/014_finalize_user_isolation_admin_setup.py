"""Finalize user isolation setup - migrate admin to real Cognito sub

Note: Admin's real Cognito sub will be populated via setup script during deployment.
For now, this migration serves as a no-op to maintain version continuity.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.database_context import DatabaseContext

DESCRIPTION = "Finalize user isolation admin setup"


def up():
    """Update admin-user placeholder to real Cognito sub in all tables (if available)"""
    with DatabaseContext('write') as cur:
        # Admin's real Cognito sub - will be populated via setup script
        # For now, keep the 'admin-user' placeholder
        # The setup script (scripts/setup-user-isolation.ps1) will populate this after Cognito setup
        # Tables already have 'admin-user' placeholder from previous migrations
        pass


def down():
    """Revert admin to placeholder (for rollback only)"""
    with DatabaseContext('write') as cur:
        # Nothing to revert - admin is already at 'admin-user' placeholder
        pass
