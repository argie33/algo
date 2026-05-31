# Schema Migrations

Versioned database schema changes with rollback support.

## Structure

```
migrations/
├── versions/          # SQL migration files (numbered, e.g., 001_name.sql, 002_name.sql)
├── run.py            # Migration runner script
└── README.md         # This file
```

## Usage

### Apply a specific migration
```bash
python migrations/run.py apply 001_schema_versioning
```

### Apply all pending migrations
```bash
python migrations/run.py apply --all
```

### Check migration status
```bash
python migrations/run.py status
```

### Rollback a migration
```bash
python migrations/run.py rollback 001_schema_versioning
```

## Migration File Format

Name format: `NNN_description.sql` (e.g., `001_schema_versioning.sql`)

Each migration file can contain one or more SQL statements separated by `;`.

Example:
```sql
-- Migration 001: Add schema version tracking table
-- Description: Enables versioning of database schema changes
-- Created: 2026-05-31

CREATE TABLE IF NOT EXISTS schema_version (
    id SERIAL PRIMARY KEY,
    version VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    applied_at TIMESTAMP DEFAULT NOW(),
    rolled_back_at TIMESTAMP NULL
);

CREATE INDEX IF NOT EXISTS idx_schema_version_version ON schema_version(version);
```

## How It Works

1. **First run:** Creates `schema_version` table to track applied migrations
2. **Apply:** Executes SQL file and records version in `schema_version` table
3. **Status:** Shows applied vs. pending migrations
4. **Rollback:** Marks migration as rolled back without executing reversal SQL (manual rollback logic can be added per migration)

## Integration with Deployment

Add to CI/CD pipeline before deploying new code:
```bash
python migrations/run.py apply --all
```

## Rollback Safety

Rollbacks only mark migrations as rolled back in the `schema_version` table. To add custom rollback logic for a migration, add a corresponding `rollback.sql` file or embed both forward and rollback operations in the migration file.

## Environment Variables

- `DB_HOST` — Database hostname (default: localhost)
- `DB_PORT` — Database port (default: 5432)
- `DB_USER` — Database user (default: postgres)
- `DB_PASSWORD` — Database password
- `DB_NAME` — Database name (default: algo)
- `DB_SSL` — SSL mode (default: require)

Use the same environment variables as the main application (from AWS Secrets Manager or PowerShell profile).
