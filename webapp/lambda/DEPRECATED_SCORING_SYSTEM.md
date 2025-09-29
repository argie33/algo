# Deprecated Scoring System

## Overview
The `/api/scoring` endpoints have been deprecated in favor of the `/api/scores` system.

## Migration Guide

### Old System (DEPRECATED)
- `/api/scoring` - Academic scoring framework
- Complex multi-factor calculations
- On-demand calculations

### New System (CURRENT)
- `/api/scores` - Production stock scores system
- Pre-calculated scores stored in `stock_scores` table
- Simple 4-factor model: Momentum, Trend, Value, Quality
- Fast database queries

## Deprecated Files
- `routes/scoring.js.deprecated` - Old scoring routes
- `tests/unit/routes/scoring.test.js.deprecated` - Old unit tests
- `tests/integration/routes/scoring.integration.test.js.deprecated` - Old integration tests

## Current System
Use the following instead:
- `routes/scores.js` - Current scores system
- `loadstockscores.py` - Loader to calculate scores from database
- `/api/scores` - List all scores
- `/api/scores/:symbol` - Get individual stock score
- `/api/scores/ping` - Health check

## Database Schema
The current system uses the `stock_scores` table populated by the Python loader.