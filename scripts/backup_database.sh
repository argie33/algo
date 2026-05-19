#!/bin/bash
# PostgreSQL Local Backup Script
# Creates compressed daily backups with automatic retention and metadata tracking
# Usage: ./backup_database.sh [--full|--incremental] [--destination /path/to/backups]

set -euo pipefail

# Configuration
BACKUP_DIR="${1:-.backups}"
BACKUP_TYPE="${2:-full}"
RETENTION_DAYS=30
BACKUP_LOG="${BACKUP_DIR}/backup.log"

# Database config from environment or defaults
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-stocks}"
DB_USER="${DB_USER:-stocks}"
DB_PASSWORD="${DB_PASSWORD:-}"

# Ensure backup directory exists
mkdir -p "$BACKUP_DIR"
touch "$BACKUP_LOG"

# Logging function
log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*" | tee -a "$BACKUP_LOG"
}

log "════════════════════════════════════════"
log "Starting $BACKUP_TYPE backup: $DB_NAME"
log "════════════════════════════════════════"

# Validate database connectivity
if ! PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "SELECT 1;" &>/dev/null; then
    log "❌ ERROR: Cannot connect to database at $DB_HOST:$DB_PORT/$DB_NAME"
    exit 1
fi
log "✓ Database connection verified"

# Create backup filename with timestamp
TIMESTAMP=$(date +'%Y%m%d_%H%M%S')
BACKUP_FILE="$BACKUP_DIR/${DB_NAME}_backup_${TIMESTAMP}.sql.gz"
METADATA_FILE="${BACKUP_FILE}.meta"

# Perform backup
log "📦 Backing up $DB_NAME to $BACKUP_FILE..."
if PGPASSWORD="$DB_PASSWORD" pg_dump \
    -h "$DB_HOST" \
    -p "$DB_PORT" \
    -U "$DB_USER" \
    -d "$DB_NAME" \
    --verbose \
    --format=plain \
    2>>"$BACKUP_LOG" | gzip > "$BACKUP_FILE"; then

    BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    log "✅ Backup successful: $BACKUP_SIZE"

    # Create metadata file
    cat > "$METADATA_FILE" << EOF
{
  "backup_date": "$(date -u +'%Y-%m-%dT%H:%M:%SZ')",
  "database": "$DB_NAME",
  "backup_file": "$(basename "$BACKUP_FILE")",
  "file_size": "$(stat -c %s "$BACKUP_FILE" 2>/dev/null || stat -f %z "$BACKUP_FILE")",
  "backup_type": "$BACKUP_TYPE",
  "format": "gzip-compressed SQL",
  "host": "$DB_HOST",
  "port": "$DB_PORT"
}
EOF
    log "✓ Metadata saved to $METADATA_FILE"
else
    log "❌ Backup failed"
    rm -f "$BACKUP_FILE" "$METADATA_FILE"
    exit 1
fi

# Cleanup old backups (retention policy)
log "🧹 Applying retention policy ($RETENTION_DAYS days)..."
CLEANUP_COUNT=$(find "$BACKUP_DIR" -name "${DB_NAME}_backup_*.sql.gz" -mtime +$RETENTION_DAYS -delete 2>/dev/null | wc -l)
if [ "$CLEANUP_COUNT" -gt 0 ]; then
    log "✓ Deleted $CLEANUP_COUNT old backup(s)"
fi

# Summary
BACKUP_COUNT=$(find "$BACKUP_DIR" -name "${DB_NAME}_backup_*.sql.gz" | wc -l)
log "📊 Backup directory contains $BACKUP_COUNT active backup(s)"
log "════════════════════════════════════════"
log "✅ Backup completed successfully"
log ""

# Exit cleanly
exit 0
