#!/bin/bash
# Enforce type safety - prevent disabling critical Pylint checks

if grep -rn '# pylint: disable=comparison-with-callable' --include='*.py' --exclude-dir=migrations --exclude-dir=tests . 2>/dev/null || \
   grep -rn '# pylint: disable=unsupported-binary-operation' --include='*.py' --exclude-dir=migrations --exclude-dir=tests . 2>/dev/null; then
    echo "BLOCKED: Cannot disable comparison-with-callable or unsupported-binary-operation"
    exit 1
fi
exit 0
