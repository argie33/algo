# PostgreSQL Database Backup & Recovery Strategy

## Overview

This document describes the local PostgreSQL backup strategy for the Stock Analytics Platform. The backup system ensures data protection with automatic retention policies and easy recovery procedures.

## Backup Strategy

### Components

| Component | Purpose | Location |
|-----------|---------|----------|
| `backup_database.sh` | Daily backup with compression & retention | `scripts/` |
| `restore_database.sh` | Restore from backup with verification | `scripts/` |
| `setup_backup_cron.sh` | Automated daily scheduling via cron | `scripts/` |
| `.backups/` | Local backup directory (git-ignored) | `.backups/` |

### Backup Characteristics

- **Format**: PostgreSQL native SQL, compressed with gzip
- **Compression Ratio**: ~10:1 (112 MB uncompressed → 11 MB compressed)
- **Retention Policy**: 30 days (configurable)
- **Metadata**: JSON metadata file created for each backup
- **Schedule**: Daily at 2:00 AM (configurable)
- **Storage**: Local `.backups/` directory

### Example Backup File Structure

```
.backups/
├── backup.log                                 # Backup operation log
├── stocks_backup_20260519_020000.sql.gz      # Backup file (compressed)
├── stocks_backup_20260519_020000.sql.gz.meta # Metadata (JSON)
├── stocks_backup_20260518_020000.sql.gz
├── stocks_backup_20260518_020000.sql.gz.meta
└── ...
```

### Metadata Example

```json
{
  "backup_date": "2026-05-19T02:00:00Z",
  "database": "stocks",
  "backup_file": "stocks_backup_20260519_020000.sql.gz",
  "file_size": "11547890",
  "backup_type": "full",
  "format": "gzip-compressed SQL",
  "host": "localhost",
  "port": "5432"
}
```

## Setup Instructions

### Linux / macOS

```bash
# Make scripts executable
chmod +x scripts/backup_database.sh
chmod +x scripts/restore_database.sh
chmod +x scripts/setup_backup_cron.sh

# Setup automated backups (daily at 2 AM)
./scripts/setup_backup_cron.sh

# Verify cron job
crontab -l | grep backup_database
```

### Windows (PowerShell)

Use **Task Scheduler** to run backups:
```powershell
# Or use the provided Python wrapper for Windows
python scripts/backup_database_windows.py
```

## Manual Backup

### Create On-Demand Backup

```bash
# Full backup with default settings
./scripts/backup_database.sh

# Custom destination
./scripts/backup_database.sh /path/to/custom/backup/dir

# Environment variables (optional)
DB_HOST=localhost DB_PORT=5432 DB_NAME=stocks DB_USER=stocks DB_PASSWORD=stocks \
  ./scripts/backup_database.sh
```

### View Backup Log

```bash
tail -f .backups/backup.log
```

## Recovery Procedures

### Restore from Backup (Verify Only)

Before performing actual restoration, verify the backup:

```bash
# Check if backup is valid (no actual restore)
./scripts/restore_database.sh .backups/stocks_backup_20260519_020000.sql.gz --verify-only
```

### Full Database Restore

```bash
# Restore database from backup (creates safety backup first)
./scripts/restore_database.sh .backups/stocks_backup_20260519_020000.sql.gz

# If restore fails, will automatically rollback to safety backup
# Safety backup location printed at end of script
```

### Restore to Different Host

```bash
# Override database connection settings
DB_HOST=backup-server.example.com \
DB_USER=restore_user \
DB_PASSWORD=$PASSWORD \
  ./scripts/restore_database.sh .backups/stocks_backup_20260519_020000.sql.gz
```

## Validation & Testing

### Test Backup/Restore Cycle

```bash
# 1. Create a backup
./scripts/backup_database.sh

# 2. List available backups
ls -lh .backups/*.sql.gz

# 3. Verify backup integrity
./scripts/restore_database.sh .backups/stocks_backup_*.sql.gz --verify-only

# 4. (Optional) Test full restore to separate database
DB_NAME=stocks_test ./scripts/restore_database.sh .backups/stocks_backup_*.sql.gz
```

### Monitor Backup Success

```bash
# Check recent backup operations
tail -50 .backups/backup.log

# Check backup file sizes
du -h .backups/*.sql.gz | tail -10

# Verify metadata
cat .backups/stocks_backup_20260519_020000.sql.gz.meta | jq .
```

## Disaster Recovery Scenarios

### Scenario 1: Corrupted Local Database

1. Stop all application processes
2. Restore from latest backup:
   ```bash
   ./scripts/restore_database.sh .backups/stocks_backup_latest.sql.gz
   ```
3. Validate data integrity
4. Restart application

### Scenario 2: Accidental Data Deletion

1. Identify when data was deleted (check logs)
2. Find backup from before deletion
3. Restore specific tables from that backup:
   ```bash
   # Extract specific table from backup
   gunzip < .backups/stocks_backup_20260518_020000.sql.gz | \
     grep -A 1000 "CREATE TABLE positions" | \
     psql -h localhost -d stocks
   ```

### Scenario 3: Complete Database Loss

1. Ensure PostgreSQL is running and accessible
2. Create empty target database if needed
3. Restore from latest full backup:
   ```bash
   ./scripts/restore_database.sh .backups/stocks_backup_latest.sql.gz
   ```
4. Verify all tables and data:
   ```bash
   psql -c "SELECT * FROM information_schema.tables WHERE table_schema='public';"
   ```

## Retention Policy

- **Default retention**: 30 days
- **Storage cost**: ~350 MB for 30 days of backups (~11-12 MB per day)
- **Oldest backups automatically deleted by `backup_database.sh`

To modify retention:
```bash
# Edit backup_database.sh, change RETENTION_DAYS variable
RETENTION_DAYS=60  # Keep 60 days of backups instead
```

## Environment Variables

All scripts support these environment variables:

| Variable | Default | Purpose |
|----------|---------|---------|
| `DB_HOST` | localhost | PostgreSQL hostname |
| `DB_PORT` | 5432 | PostgreSQL port |
| `DB_NAME` | stocks | Database name |
| `DB_USER` | stocks | Database user |
| `DB_PASSWORD` | (required) | Database password |

## Monitoring & Alerts

### Alert Triggers (Manual Setup Recommended)

```bash
# If backup fails, check:
# 1. PostgreSQL service status
systemctl status postgresql

# 2. Database connectivity
psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c "SELECT 1;"

# 3. Disk space
df -h .backups/

# 4. Recent backup log
tail -20 .backups/backup.log
```

### Disk Space Management

Backups are automatically pruned based on retention policy. To check current usage:

```bash
du -sh .backups/
ls -lhS .backups/*.sql.gz
```

## Integration with CI/CD

The backup strategy is separate from the automated deployment pipeline. However, backups can be tested in CI:

```yaml
# Example: Backup verification step
- name: Verify backup integrity
  run: |
    ./scripts/backup_database.sh
    ./scripts/restore_database.sh .backups/stocks_backup_*.sql.gz --verify-only
```

## AWS RDS Backups (Production)

For AWS RDS instances, Amazon handles automated backups. This local strategy is for:
- **Development environments** (local PostgreSQL)
- **Testing restore procedures**
- **Compliance & audit trails**
- **Point-in-time recovery without AWS costs**

## Troubleshooting

### "Cannot connect to database"
```bash
# Verify PostgreSQL is running
systemctl status postgresql

# Check connection settings
PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c "\dt"
```

### "Backup file is corrupted"
```bash
# Check if file is readable
gzip -t .backups/stocks_backup_*.sql.gz -v

# Get file info
file .backups/stocks_backup_*.sql.gz
```

### "Out of disk space"
```bash
# Reduce retention period
RETENTION_DAYS=7 ./scripts/backup_database.sh

# Manually delete old backups
find .backups/ -name "*.sql.gz" -mtime +14 -delete
```

## Related Documentation

- [Architecture Design](../ARCHITECTURE.md)
- [Disaster Recovery Plan](../DISASTER_RECOVERY.md)
- [Database Schema](../terraform/modules/database/init.sql)

## Maintenance Schedule

| Task | Frequency | Responsibility |
|------|-----------|-----------------|
| Automatic daily backup | Daily 2:00 AM | Cron |
| Backup verification | Weekly | Manual or CI |
| Retention cleanup | Automatic | backup_database.sh |
| Restore test | Monthly | Manual testing |
| Log rotation | Monthly | Manual |

## Support

For issues or questions:
1. Check `.backups/backup.log` for error details
2. Verify database connectivity independently
3. Test restore with `--verify-only` flag
4. Check available disk space
