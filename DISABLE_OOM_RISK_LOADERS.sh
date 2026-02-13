#!/bin/bash
# Temporarily disable loaders that could cause heap corruption
# Rename to prevent accidental execution

echo "Disabling high-risk OOM loaders..."

for file in loadfactormetrics.py loaddailycompanydata.py; do
  if [ -f "$file" ]; then
    mv "$file" "$file.DISABLED"
    echo "  ✅ Disabled $file"
  fi
done

echo "High-risk loaders disabled. Re-enable with: .DISABLED suffix removal"
