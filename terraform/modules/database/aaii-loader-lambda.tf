# ============================================================
# AAII Sentiment Loader Lambda - REMOVED 2026-08-10
# ============================================================
# Was STATUS "SUPERSEDED, should be decommissioned" since 2026-07-20 (Session 301):
# scripts/aaii_loader_function.py -- the only real implementation this Lambda ever
# had -- was a fabricated-data generator (deterministic formula, zero connection to
# the actual AAII investor sentiment survey) and was deleted in commit 676a415c5 as
# presumed test cruft. This Lambda had been a no-op stub since (deploy workflow fell
# back to a 501 handler when the source file was missing). It was also never actually
# scheduled -- invoked once per Terraform apply, not on a cadence.
#
# The REAL loader (loaders/load_aaii_sentiment.py, standard ECS-loader pattern,
# Playwright-based Incapsula bypass + XLS parse from aaii.com) was separately restored
# Session 301 and is the live source of the aaii_sentiment table. This Lambda was
# fully redundant with it.
#
# Removed rather than left in place because, beyond being dead weight, it carried a
# real credential exposure: its aws_lambda_function.aaii_loader resource set
# DB_PASSWORD = local.rds_password directly as a plaintext Lambda environment
# variable (visible to anyone with lambda:GetFunctionConfiguration on it, and logged
# to CloudTrail) instead of referencing Secrets Manager at runtime like every other
# credential path in this codebase. A no-op stub with no real code to actually
# consume that password wasn't worth patching in place - just removed it, its IAM
# role/policies, and its output.tf entry (aaii_loader_function_name). The shared
# aws_lambda_layer_version.psycopg2 layer (modules/database/main.tf) was NOT touched
# - it's used by another, still-live Lambda in this module.
#
# The `.github/workflows/deploy-all-infrastructure.yml` steps that build/zip
# scripts/aaii_loader_function.py and invoke this Lambda as a "fallback" step are
# left in place for now (both are `continue-on-error`/best-effort, so they don't
# break the pipeline when this Lambda no longer exists to invoke) - cleaning those up
# is a smaller follow-up, not blocking.
