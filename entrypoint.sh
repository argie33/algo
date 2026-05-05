#!/bin/sh
set -e

# Pick the loader to run, in priority order:
#   1. LOADER_FILE env var (set by ECS task def)
#   2. First positional arg (e.g. `docker run image foo.py`)
#   3. Derive from container name via ECS metadata (`{loader}-loader` -> `load{loader}.py`)
#   4. Error out with a clear message — never default silently.

if [ -n "${LOADER_FILE:-}" ]; then
  echo "[entrypoint] Running LOADER_FILE=$LOADER_FILE"
  exec python3 "$LOADER_FILE" "$@"
fi

if [ -n "${1:-}" ]; then
  echo "[entrypoint] Running argv: $*"
  exec python3 "$@"
fi

# Try ECS task metadata (v4) — container Name field follows "{loader}-loader" convention
if [ -n "${ECS_CONTAINER_METADATA_URI_V4:-}" ]; then
  CONTAINER_NAME=$(python3 -c "
import os, sys, urllib.request, json
try:
    with urllib.request.urlopen(os.environ['ECS_CONTAINER_METADATA_URI_V4'], timeout=5) as r:
        print(json.load(r).get('Name', ''))
except Exception as e:
    print('', file=sys.stderr)
" 2>/dev/null)
  if [ -n "$CONTAINER_NAME" ]; then
    LOADER_NAME=$(echo "$CONTAINER_NAME" | sed 's/-loader$//')
    SCRIPT="load${LOADER_NAME}.py"
    if [ -f "/app/$SCRIPT" ]; then
      echo "[entrypoint] Derived from container name '$CONTAINER_NAME': $SCRIPT"
      exec python3 "$SCRIPT"
    fi
    echo "[entrypoint] WARN: derived script '$SCRIPT' not found in /app" >&2
  fi
fi

echo "[entrypoint] FATAL: no LOADER_FILE env var, no argv, and no ECS container metadata available." >&2
echo "[entrypoint] Set LOADER_FILE in the task definition's Environment, e.g.:" >&2
echo '  Environment:' >&2
echo '    - Name: LOADER_FILE' >&2
echo '      Value: loadstocksymbols.py' >&2
exit 64
