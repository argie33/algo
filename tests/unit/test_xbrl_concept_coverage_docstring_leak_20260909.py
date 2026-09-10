"""Regression test: load_known_concepts() must not treat a concept name merely quoted in a
module/function/class docstring as "known" (fetched).

Same-day follow-up to test_xbrl_concept_coverage_comment_leak_20260909.py - that fix's own
commit explicitly flagged this as a narrower residual risk left open: tokenize.STRING doesn't
distinguish a docstring from any other string literal (a "#" comment is a distinct
tokenize.COMMENT type and was already excluded, but a docstring is still a STRING token).

Live-audited against the real 5,377-payload companyfacts cache: 0 currently-cached filers are
affected today (the docstring-only names in these 22 files right now - segment-dimension/member
concepts like NumberOfSegments/SegmentRevenue/AmericasSegmentMember - none are real top-level
companyfacts concept keys anyway), so this closes a latent correctness bug proactively, not an
active false plateau.

Fixed: load_known_concepts() now additionally excludes STRING tokens whose line falls inside an
AST-identified module/function/class docstring (_docstring_line_ranges()).
"""

from utils.external.xbrl_concept_coverage import load_known_concepts


class TestConceptCoverageDocstringLeak:
    def test_concept_name_only_in_a_module_docstring_is_not_known(self, tmp_path, monkeypatch) -> None:
        import utils.external.xbrl_concept_coverage as mod

        fake_file = tmp_path / "fake_sec_source.py"
        fake_file.write_text(
            '"""This module explains why "TotallyMadeUpConceptName" was never fetched."""\n\n'
            'REAL_CONCEPTS = ["ActuallyFetchedConcept"]\n',
            encoding="utf-8",
        )
        monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(mod, "CONCEPT_SOURCE_FILES", ["fake_sec_source.py"])

        known = load_known_concepts()

        assert "ActuallyFetchedConcept" in known
        assert "TotallyMadeUpConceptName" not in known

    def test_concept_name_only_in_a_function_docstring_is_not_known(self, tmp_path, monkeypatch) -> None:
        import utils.external.xbrl_concept_coverage as mod

        fake_file = tmp_path / "fake_sec_source.py"
        fake_file.write_text(
            "def get_balance_sheet():\n"
            '    """Historical note: "AnotherMadeUpConcept" was tried and rejected."""\n'
            '    return ["ActuallyFetchedConcept2"]\n',
            encoding="utf-8",
        )
        monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(mod, "CONCEPT_SOURCE_FILES", ["fake_sec_source.py"])

        known = load_known_concepts()

        assert "ActuallyFetchedConcept2" in known
        assert "AnotherMadeUpConcept" not in known

    def test_concept_name_in_real_code_string_still_known_even_if_also_mentioned_in_docstring(
        self, tmp_path, monkeypatch
    ) -> None:
        """A concept genuinely fetched in real code must stay known even when the same file's
        docstring also happens to mention it (the common case - most docstring-only concepts in
        the real source files are duplicates of an already-fetched concept, not new gaps)."""
        import utils.external.xbrl_concept_coverage as mod

        fake_file = tmp_path / "fake_sec_source.py"
        fake_file.write_text(
            '"""Fetches "Assets" among other concepts."""\n\nREAL_CONCEPTS = ["Assets"]\n',
            encoding="utf-8",
        )
        monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(mod, "CONCEPT_SOURCE_FILES", ["fake_sec_source.py"])

        known = load_known_concepts()

        assert "Assets" in known
