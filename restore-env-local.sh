#!/bin/bash
# Restore .env.local from backup if it gets deleted

echo "=== RESTORING .env.local ==="
echo ""

# Check if .env.local exists
if [ -f ".env.local" ]; then
    echo "✓ .env.local already exists - nothing to restore"
    exit 0
fi

# Check if backup exists
if [ -f ".env.local.backup" ]; then
    echo "Restoring from .env.local.backup..."
    cp .env.local.backup .env.local
    echo "✓ Restored: .env.local"
    exit 0
fi

# Fall back to template
if [ -f ".env.local.example" ]; then
    echo "No backup found. Using template .env.local.example"
    echo "IMPORTANT: You must add your real credentials to .env.local"
    echo ""
    cp .env.local.example .env.local
    echo "Created .env.local from template"
    echo "Now edit it and add your credentials:"
    echo "  nano .env.local"
    exit 0
fi

echo "ERROR: Cannot find .env.local, .env.local.backup, or .env.local.example"
echo "Manual setup required - see CREDENTIAL_SETUP.md"
exit 1
