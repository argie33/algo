#!/bin/bash
# PostgreSQL Restore Script with Verification
# Usage: ./restore_database.sh <backup_file> [--verify-only]

set -euo pipefail

# Arguments
BACKUP_FILE="${1:?ERROR: Backup file path required}"
VERIFY_ONLY="${2:-}"

# Database config from environment or defaults
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-stocks}"
DB_USER="${DB_USER:-stocks}"
DB_PASSWORD="${DB_PASSWORD:-}"

log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*"
}

log "════════════════════════════════════════"
log "PostgreSQL Restore Process"
log "════════════════════════════════════════"

# Validate backup file exists and is readable
if [ ! -f "$BACKUP_FILE" ]; then
    log "❌ ERROR: Backup file not found: $BACKUP_FILE"
    exit 1
fi
log "✓ Backup file found: $BACKUP_FILE ($(du -h "$BACKUP_FILE" | cut -f1))"

# Verify backup file is valid gzip
if ! gzip -t "$BACKUP_FILE" 2>/dev/null; then
    log "❌ ERROR: Backup file is corrupted or not valid gzip"
    exit 1
fi
log "✓ Backup file integrity verified (valid gzip)"

# Extract and validate SQL content
log "📋 Validating SQL structure..."
TEMP_SQL=$(mktemp)
if ! gunzip < "$BACKUP_FILE" > "$TEMP_SQL" 2>/dev/null; then
    log "❌ ERROR: Failed to extract backup"
    rm -f "$TEMP_SQL"
    exit 1
fi

# Check for basic PostgreSQL dump structure
if ! head -1 "$TEMP_SQL" | grep -q "PostgreSQL"; then
    log "⚠️  WARNING: Backup might not be a valid PostgreSQL dump (no header)"
else
    log "✓ Backup header validated"
fi

# Count statements in backup
SQL_LINES=$(wc -l < "$TEMP_SQL")
log "✓ Backup contains $SQL_LINES SQL statements"

# If verify-only mode, stop here
if [ "$VERIFY_ONLY" = "--verify-only" ]; then
    log "✅ Verification successful (no restoration performed)"
    rm -f "$TEMP_SQL"
    exit 0
fi

# Confirm database connectivity
log "🔌 Testing database connectivity..."
if ! PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "SELECT 1;" &>/dev/null; then
    log "❌ ERROR: Cannot connect to target database at $DB_HOST:$DB_PORT/$DB_NAME"
    rm -f "$TEMP_SQL"
    exit 1
fi
log "✓ Database connection verified"

# Backup current database before restore (safety measure)
log "💾 Creating safety backup of current $DB_NAME..."
SAFETY_BACKUP="/tmp/${DB_NAME}_safety_backup_$(date +'%Y%m%d_%H%M%S').sql.gz"
if PGPASSWORD="$DB_PASSWORD" pg_dump \
    -h "$DB_HOST" \
    -p "$DB_PORT" \
    -U "$DB_USER" \
    -d "$DB_NAME" \
    2>/dev/null | gzip > "$SAFETY_BACKUP"; then
    log "✓ Safety backup created: $SAFETY_BACKUP"
else
    log "⚠️  WARNING: Could not create safety backup, proceeding anyway"
fi

# Perform restore with error handling
log "🔄 Restoring database from backup..."
if gunzip < "$BACKUP_FILE" | PGPASSWORD="$DB_PASSWORD" psql \
    -h "$DB_HOST" \
    -p "$DB_PORT" \
    -U "$DB_USER" \
    -d "$DB_NAME" \
    --single-transaction \
    2>&1 | tail -20; then

    log "✅ Restore completed successfully"
else
    log "❌ Restore failed — restoring from safety backup..."
    gunzip < "$SAFETY_BACKUP" | PGPASSWORD="$DB_PASSWORD" psql \
        -h "$DB_HOST" \
        -p "$DB_PORT" \
        -U "$DB_USER" \
        -d "$DB_NAME" \
        >/dev/null 2>&1
    log "✓ Rollback to safety backup completed"
    rm -f "$TEMP_SQL"
    exit 1
fi

# Post-restore validation
log "📊 Validating restored data..."
RESTORED_TABLES=$(PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
    -t -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';" 2>/dev/null)
log "✓ Restored database contains $RESTORED_TABLES public tables"

log "════════════════════════════════════════"
log "✅ Restore verification complete"
log "Safety backup available: $SAFETY_BACKUP"
log ""

rm -f "$TEMP_SQL"
exit 0
