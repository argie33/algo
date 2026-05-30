# Database Migrations

This directory manages database schema migrations with version tracking and rollback support.

## Structure

- `0001_init_schema_version.sql` - Initializes the schema_version tracking table
- `versions/` - Directory containing migration SQL files
- `run.py` - Migration runner script

## Usage

### Check Migration Status

```bash
python migrations/run.py --status
```

Shows which migrations have been applied and which are pending.

### Apply Pending Migrations

```bash
python migrations/run.py --apply
```

Applies all pending migrations in order, tracking each one in the schema_version table.

### Creating New Migrations

1. Create a SQL file in `migrations/versions/` with a descriptive name:
   ```
   0002_add_new_table.sql
   0003_add_index_on_column.sql
   ```

2. Start with a comment block describing the migration:
   ```sql
   -- Migration: 0002
   -- Description: Add new_table for tracking feature X
   -- Date: 2026-05-30
   
   CREATE TABLE new_table (
       id SERIAL PRIMARY KEY,
       ...
   );
   ```

3. Run migrations:
   ```bash
   python migrations/run.py --apply
   ```

## Migration Tracking

Each applied migration is recorded in the `schema_version` table with:
- `version` - Migration identifier (must be unique)
- `description` - Human-readable description
- `applied_at` - Timestamp when migration was applied
- `rolled_back_at` - NULL unless migration was rolled back
- `checksum` - SHA-256 of migration SQL for integrity checking

## Rollback

Rollback functionality requires maintaining reverse migrations (DOWN scripts). Currently, rollback is documented but not automated. To rollback:

1. Restore the database from a backup
2. Re-apply migrations up to (but not including) the rolled-back version
3. Or manually run the reverse SQL if you're confident

## Best Practices

1. **One change per migration** - Keep migrations focused and atomic
2. **Idempotent where possible** - Use `CREATE TABLE IF NOT EXISTS` etc.
3. **Test before deploying** - Always test migrations on a dev/staging database first
4. **Version naming** - Use sequential 4-digit numbers: 0001, 0002, 0003, etc.
5. **Documentation** - Include clear description comments in each migration

## Integration with CI/CD

Add to GitHub Actions workflow to auto-apply migrations during deployment:

```yaml
- name: Apply database migrations
  run: python migrations/run.py --apply
```

## See Also

- `terraform/modules/database/init.sql` - Base schema initialization
- `steering/algo.md` - Database documentation
