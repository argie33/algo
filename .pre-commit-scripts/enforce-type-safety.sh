#!/bin/bash
# Enforce type safety - prevent disabling critical Pylint checks

# --exclude-dir=.claude also covers .claude/worktrees/* (nested git worktrees used by
# concurrent sessions) - without it, a disable-comment in another session's in-progress,
# uncommitted worktree branch blocks every unrelated commit anywhere in the repo.
if grep -rn '# pylint: disable=comparison-with-callable' --include='*.py' --exclude-dir=migrations --exclude-dir=tests --exclude-dir=.claude . 2>/dev/null || \
   grep -rn '# pylint: disable=unsupported-binary-operation' --include='*.py' --exclude-dir=migrations --exclude-dir=tests --exclude-dir=.claude . 2>/dev/null; then
    echo "BLOCKED: Cannot disable comparison-with-callable or unsupported-binary-operation"
    exit 1
fi
exit 0
