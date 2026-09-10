"""Regression test: load_known_concepts() must not treat a concept name merely quoted in a
comment as "known" (fetched).

User-flagged 2026-09-09: xbrl_concept_coverage_scan.py reported 0 undismissed gaps despite
~900+ symbol-level "missing SEC/XBRL data" scored inputs. Root cause: load_known_concepts()
regex-scanned each source file's RAW text - comments included - so any PascalCase concept name
merely quoted in a comment (common in this codebase's documentation style, e.g. explaining why
a concept was superseded/rejected) was counted the same as a real fetch-list entry, hiding a
genuine gap for that concept from every future scan. Live-confirmed 51 such concepts across the
22 source files (e.g. "GeneralAndAdministrativeExpense", tagged by 2,825 real filers and never
actually fetched anywhere) were invisible to the scan purely because they happened to appear in
a comment somewhere.

Fixed: load_known_concepts() now tokenizes each file and only scans real STRING tokens
(tokenize.COMMENT is a distinct token type, never matched).
"""

from utils.external.xbrl_concept_coverage import load_known_concepts


class TestConceptCoverageCommentLeak:
    def test_concept_name_only_in_a_comment_is_not_known(self, tmp_path, monkeypatch) -> None:
        import utils.external.xbrl_concept_coverage as mod

        fake_file = tmp_path / "fake_sec_source.py"
        fake_file.write_text(
            '# This module used to fetch "TotallyMadeUpConceptName" but it was removed.\n'
            'REAL_CONCEPTS = ["ActuallyFetchedConcept"]\n',
            encoding="utf-8",
        )
        monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(mod, "CONCEPT_SOURCE_FILES", ["fake_sec_source.py"])

        known = load_known_concepts()

        assert "ActuallyFetchedConcept" in known
        assert "TotallyMadeUpConceptName" not in known
