"""Internal-bookkeeping-key predicate for SecLoaderBase.transform(), extracted out of
sec_base.py (2026-09-11, file-size ratchet: that file is already past its 2000-line hard
ceiling, so a bug fix landing there must shrink it, not grow it).

sec_statements_aggregate.py's `_aggregate_concepts` attaches several `_{prefix}_{col}`
keys onto each row alongside the real mapped fields, for on-demand lookups elsewhere in
the same module chain (rank tie-breaking, cross-concept provenance, etc.) - never
themselves a real SEC XBRL concept a `field_mapping` entry should exist for.
`_filed_`/`_end_`/`_frame_`/`_span_`/`_is_instant_` are stripped before transform() ever
sees them; `_rank_` and `_concept_` are deliberately kept (read on demand via
`r.get(f"_rank_{sec_field}")` / written by sec_statements_entry_resolution.py's
cross-concept resolution) but must still be recognized and skipped here so transform()'s
"is this an unmapped SEC field" warning doesn't fire on them - `_rank_` always had that
skip; `_concept_` didn't (live-confirmed via CWD/MPU logging spurious "Unmapped SEC field
'_concept_assets'" warnings for a field that maps and loads correctly), same bug class.
"""

from __future__ import annotations

_BOOKKEEPING_PREFIXES = ("_rank_", "_concept_")


def is_bookkeeping_key(sec_field: str) -> bool:
    """True for a `_rank_{col}`/`_concept_{col}` internal key, never a real SEC concept."""
    return sec_field.startswith(_BOOKKEEPING_PREFIXES)
