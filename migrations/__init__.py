"""Database migrations package.

Provides schema versioning and migration management.

Usage:
    python3 -m migrations.run_migrations            # Apply pending migrations
    python3 -m migrations.run_migrations --status   # Show status
    python3 -m migrations.run_migrations --rollback 001  # Rollback migration
"""
