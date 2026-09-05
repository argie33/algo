"""Pillar-scoring modules for StockScoresLoader (loaders/load_stock_scores.py).

Split out of the monolithic loader as a pure mechanical extraction: each module holds one
pillar's `_get_*_metrics`/`_score_*` function pair (or, for scoring_curves.py, the shared
curve-score/percentile-rank helpers), as plain module-level functions with no
StockScoresLoader/self coupling. StockScoresLoader keeps a same-name, same-signature instance
method for each that just delegates to the matching function here - no behavior change, no
public API change.
"""
