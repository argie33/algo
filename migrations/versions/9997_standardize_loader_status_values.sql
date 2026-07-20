-- Migration: Standardize loader status values
-- Issue: Some loaders recorded 'success', others recorded 'COMPLETED'
-- Upstream dependency checks expect 'COMPLETED' or 'INCOMPLETE'
--
-- Fix: Update all 'success' status to 'COMPLETED' for consistency

UPDATE data_loader_status
SET status = 'COMPLETED'
WHERE status = 'success';

-- Note: 42 loaders still have NULL status (no completion tracking)
-- These should be addressed separately by ensuring all loaders record their status
