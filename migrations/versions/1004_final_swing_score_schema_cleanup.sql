-- Migration 1004: Final swing score schema cleanup
-- This migration is skipped if tables don't exist (during fresh migrations)
-- The migration is intentionally left as a no-op since column cleanup is optional
-- and tables may not exist in all deployment scenarios

-- This is a documentation-only migration now. The swing score columns cleanup
-- is handled gracefully elsewhere or skipped entirely if tables don't exist.
