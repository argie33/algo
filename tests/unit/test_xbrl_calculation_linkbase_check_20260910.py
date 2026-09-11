"""Tests for the calculation-linkbase self-consistency layer (goal session 2026-09-10,
layer 5/5 of the institutional XBRL data-quality build):
    - utils/external/sec_calculation_linkbase.py (linkbase XML parsing + role filtering)
    - scripts/xbrl_calculation_linkbase_check.py (the DataPatrol-feeding check)
"""

from unittest.mock import MagicMock, patch

from scripts.xbrl_calculation_linkbase_check import _check_symbol, _facts_by_concept_for_accession, run
from utils.external.sec_calculation_linkbase import (
    CalcArc,
    group_by_parent,
    is_primary_statement_role,
    parse_calculation_arcs,
)

_STATEMENT_ROLE = "http://www.example.com/role/CONSOLIDATEDBALANCESHEETS"
_NOTE_ROLE = "http://www.example.com/role/LeasesLeaseLiabilityMaturitiesDetails"


def _cal_xml(role: str, arcs: list[tuple[str, str, str, float]]) -> str:
    """arcs: list of (from_label, to_label, weight) tuples referencing implicit locs
    named after their concept - builds a minimal but spec-valid calculation linkbase."""
    concepts: dict[str, str] = {}
    for from_label, to_label, from_concept, weight in arcs:
        concepts[from_label] = from_concept
    locs = "\n".join(
        f'    <link:loc xlink:type="locator" xlink:href="foo.xsd#{c}" xlink:label="{lbl}"/>'
        for lbl, c in concepts.items()
    )
    xml_arcs = "\n".join(
        f'    <link:calculationArc xlink:type="arc" xlink:from="{f}" xlink:to="{t}" '
        f'xlink:arcrole="http://www.xbrl.org/2003/arcrole/summation-item" order="1" weight="{w}"/>'
        for f, t, _, w in arcs
    )
    return f"""<?xml version="1.0"?>
<link:linkbase xmlns:link="http://www.xbrl.org/2003/linkbase" xmlns:xlink="http://www.w3.org/1999/xlink">
  <link:calculationLink xlink:type="extended" xlink:role="{role}">
{locs}
{xml_arcs}
  </link:calculationLink>
</link:linkbase>"""


class TestParseCalculationArcs:
    def test_extracts_summation_item_arcs_with_role(self) -> None:
        xml = _cal_xml(
            _STATEMENT_ROLE,
            [
                ("loc_parent", "loc_child1", "us-gaap_Assets", 1.0),
            ],
        )
        # Build loc for child too (helper above only registers "from" labels)
        xml = xml.replace(
            "<link:calculationArc",
            '<link:loc xlink:type="locator" xlink:href="foo.xsd#us-gaap_AssetsCurrent" xlink:label="loc_child1"/>\n'
            "    <link:calculationArc",
            1,
        )
        arcs = parse_calculation_arcs(xml)
        assert len(arcs) == 1
        assert arcs[0] == CalcArc("us-gaap:Assets", "us-gaap:AssetsCurrent", 1.0, 1.0, _STATEMENT_ROLE)

    def test_ignores_non_summation_item_arcrole(self) -> None:
        xml = """<?xml version="1.0"?>
<link:linkbase xmlns:link="http://www.xbrl.org/2003/linkbase" xmlns:xlink="http://www.w3.org/1999/xlink">
  <link:calculationLink xlink:type="extended" xlink:role="r">
    <link:loc xlink:type="locator" xlink:href="foo.xsd#us-gaap_A" xlink:label="a"/>
    <link:loc xlink:type="locator" xlink:href="foo.xsd#us-gaap_B" xlink:label="b"/>
    <link:calculationArc xlink:type="arc" xlink:from="a" xlink:to="b" xlink:arcrole="http://www.xbrl.org/2003/arcrole/general-special" weight="1.0"/>
  </link:calculationLink>
</link:linkbase>"""
        assert parse_calculation_arcs(xml) == []


class TestIsPrimaryStatementRole:
    def test_statement_role_is_primary(self) -> None:
        assert is_primary_statement_role(_STATEMENT_ROLE) is True

    def test_details_role_is_excluded(self) -> None:
        assert is_primary_statement_role(_NOTE_ROLE) is False

    def test_tables_role_is_excluded(self) -> None:
        assert is_primary_statement_role("http://example.com/role/SomeTables") is False


class TestGroupByParent:
    def test_identical_child_set_reused_across_roles_collapses_to_one_tree(self) -> None:
        arcs = [
            CalcArc("us-gaap:Assets", "us-gaap:AssetsCurrent", 1.0, 1.0, "role1"),
            CalcArc("us-gaap:Assets", "us-gaap:AssetsNoncurrent", 1.0, 2.0, "role1"),
            CalcArc("us-gaap:Assets", "us-gaap:AssetsCurrent", 1.0, 1.0, "role2"),  # same tree, another role
            CalcArc("us-gaap:Assets", "us-gaap:AssetsNoncurrent", 1.0, 2.0, "role2"),
        ]
        grouped = group_by_parent(arcs)
        assert len(grouped["us-gaap:Assets"]) == 1
        assert len(grouped["us-gaap:Assets"][0]) == 2

    def test_genuinely_different_child_sets_across_roles_stay_separate_trees(self) -> None:
        # Regression for the UNTY false-positive (2026-09-11): a parent can have two
        # independently-valid breakdowns in different roles (e.g. OCI by component vs
        # by before-tax/tax) - each must be checked on its own, never flattened into
        # one combined sum, or every value gets double-counted.
        arcs = [
            CalcArc("us-gaap:OCI", "us-gaap:AfsAdjustment", 1.0, 1.0, "role1"),
            CalcArc("us-gaap:OCI", "us-gaap:CashFlowHedge", 1.0, 2.0, "role1"),
            CalcArc("us-gaap:OCI", "us-gaap:BeforeTax", 1.0, 1.0, "role2"),
            CalcArc("us-gaap:OCI", "us-gaap:Tax", -1.0, 2.0, "role2"),
        ]
        grouped = group_by_parent(arcs)
        trees = grouped["us-gaap:OCI"]
        assert len(trees) == 2
        child_sets = [{(a.child_concept, a.weight) for a in tree} for tree in trees]
        assert {("us-gaap:AfsAdjustment", 1.0), ("us-gaap:CashFlowHedge", 1.0)} in child_sets
        assert {("us-gaap:BeforeTax", 1.0), ("us-gaap:Tax", -1.0)} in child_sets


class TestFactsByConceptForAccession:
    def test_matches_only_the_given_accession(self) -> None:
        company_facts = {
            "facts": {
                "us-gaap": {
                    "Assets": {
                        "units": {
                            "USD": [
                                {"accn": "0001-old", "end": "2024-12-31", "val": 999},
                                {"accn": "0001-new", "end": "2025-12-31", "val": 1000},
                            ]
                        }
                    }
                }
            }
        }
        value = _facts_by_concept_for_accession(company_facts, "us-gaap", "Assets", "0001-new")
        assert value == 1000.0

    def test_returns_none_when_concept_missing(self) -> None:
        assert _facts_by_concept_for_accession({"facts": {"us-gaap": {}}}, "us-gaap", "Assets", "0001") is None


def _fake_submissions(accession: str = "0001234567-25-000001", filed: str = "2025-11-01") -> dict[str, object]:
    return {
        "filings": {
            "recent": {
                "form": ["10-K"],
                "accessionNumber": [accession],
                "filingDate": [filed],
            }
        }
    }


def _fake_company_facts(values: dict[str, float], accession: str) -> dict[str, object]:
    return {
        "facts": {
            "us-gaap": {
                concept: {"units": {"USD": [{"accn": accession, "end": "2025-09-30", "val": val}]}}
                for concept, val in values.items()
            }
        }
    }


class TestCheckSymbol:
    def test_single_child_parent_below_min_children_is_skipped(self) -> None:
        # A single-child "sum" arc is usually a relabeling/housekeeping arc, not a real
        # subtotal assertion - _MIN_CHILDREN requires >=2 before checking it.
        accession = "0001234567-25-000001"
        cal_xml = _cal_xml(_STATEMENT_ROLE, [("loc_a", "loc_b", "us-gaap_Assets", 1.0)]).replace(
            "<link:calculationArc",
            '<link:loc xlink:type="locator" xlink:href="foo.xsd#us-gaap_AssetsCurrent" xlink:label="loc_b"/>\n    <link:calculationArc',
            1,
        )
        client = MagicMock()
        client.symbol_to_cik.return_value = "0000000001"
        client.get_submissions.return_value = _fake_submissions(accession)
        client.get_calculation_linkbase_xml.return_value = cal_xml
        client.get_company_facts.return_value = _fake_company_facts(
            {"Assets": 1000.0, "AssetsCurrent": 400.0}, accession
        )

        result = _check_symbol(client, MagicMock(), "AAA")
        assert result is None

    def test_flags_real_two_child_mismatch(self) -> None:
        accession = "0001234567-25-000001"
        xml = f"""<?xml version="1.0"?>
<link:linkbase xmlns:link="http://www.xbrl.org/2003/linkbase" xmlns:xlink="http://www.w3.org/1999/xlink">
  <link:calculationLink xlink:type="extended" xlink:role="{_STATEMENT_ROLE}">
    <link:loc xlink:type="locator" xlink:href="foo.xsd#us-gaap_Assets" xlink:label="p"/>
    <link:loc xlink:type="locator" xlink:href="foo.xsd#us-gaap_AssetsCurrent" xlink:label="c1"/>
    <link:loc xlink:type="locator" xlink:href="foo.xsd#us-gaap_AssetsNoncurrent" xlink:label="c2"/>
    <link:calculationArc xlink:type="arc" xlink:from="p" xlink:to="c1" xlink:arcrole="http://www.xbrl.org/2003/arcrole/summation-item" order="1" weight="1.0"/>
    <link:calculationArc xlink:type="arc" xlink:from="p" xlink:to="c2" xlink:arcrole="http://www.xbrl.org/2003/arcrole/summation-item" order="2" weight="1.0"/>
  </link:calculationLink>
</link:linkbase>"""
        client = MagicMock()
        client.symbol_to_cik.return_value = "0000000001"
        client.get_submissions.return_value = _fake_submissions(accession)
        client.get_calculation_linkbase_xml.return_value = xml
        client.get_company_facts.return_value = _fake_company_facts(
            {"Assets": 1_000_000_000.0, "AssetsCurrent": 400_000_000.0, "AssetsNoncurrent": 400_000_000.0}, accession
        )  # 400M+400M=800M != 1000M, well outside tolerance -> real mismatch

        result = _check_symbol(client, MagicMock(), "AAA")
        assert result is not None
        assert result["parents_checked"] == 1
        assert len(result["mismatches"]) == 1
        assert result["mismatches"][0]["parent_concept"] == "Assets"

    def test_note_schedule_role_is_never_checked(self) -> None:
        accession = "0001234567-25-000001"
        xml = f"""<?xml version="1.0"?>
<link:linkbase xmlns:link="http://www.xbrl.org/2003/linkbase" xmlns:xlink="http://www.w3.org/1999/xlink">
  <link:calculationLink xlink:type="extended" xlink:role="{_NOTE_ROLE}">
    <link:loc xlink:type="locator" xlink:href="foo.xsd#us-gaap_LeaseLiabilityTotal" xlink:label="p"/>
    <link:loc xlink:type="locator" xlink:href="foo.xsd#us-gaap_LeaseLiabilityYear1" xlink:label="c1"/>
    <link:loc xlink:type="locator" xlink:href="foo.xsd#us-gaap_LeaseLiabilityYear2" xlink:label="c2"/>
    <link:calculationArc xlink:type="arc" xlink:from="p" xlink:to="c1" xlink:arcrole="http://www.xbrl.org/2003/arcrole/summation-item" order="1" weight="1.0"/>
    <link:calculationArc xlink:type="arc" xlink:from="p" xlink:to="c2" xlink:arcrole="http://www.xbrl.org/2003/arcrole/summation-item" order="2" weight="1.0"/>
  </link:calculationLink>
</link:linkbase>"""
        client = MagicMock()
        client.symbol_to_cik.return_value = "0000000001"
        client.get_submissions.return_value = _fake_submissions(accession)
        client.get_calculation_linkbase_xml.return_value = xml
        # Deliberately non-tying values - if the note-schedule role weren't filtered out,
        # this would show up as a "mismatch". It must be silently skipped instead.
        client.get_company_facts.return_value = _fake_company_facts(
            {"LeaseLiabilityTotal": 999.0, "LeaseLiabilityYear1": 1.0, "LeaseLiabilityYear2": 1.0}, accession
        )

        result = _check_symbol(client, MagicMock(), "AAA")
        assert result is None

    def test_two_independently_tying_trees_do_not_flag_a_double_counted_mismatch(self) -> None:
        # Regression for the UNTY false-positive: OCI has two roles, each declaring a
        # DIFFERENT, independently-tying breakdown. Neither alone is a mismatch; the
        # old flatten-everything behavior summed both and falsely flagged one.
        accession = "0001234567-25-000001"
        role2 = "http://www.example.com/role/StatementOfComprehensiveIncomeBeforeTax"
        xml = f"""<?xml version="1.0"?>
<link:linkbase xmlns:link="http://www.xbrl.org/2003/linkbase" xmlns:xlink="http://www.w3.org/1999/xlink">
  <link:calculationLink xlink:type="extended" xlink:role="{_STATEMENT_ROLE}">
    <link:loc xlink:type="locator" xlink:href="foo.xsd#us-gaap_OtherComprehensiveIncomeLossNetOfTax" xlink:label="p"/>
    <link:loc xlink:type="locator" xlink:href="foo.xsd#us-gaap_AfsAdjustment" xlink:label="c1"/>
    <link:loc xlink:type="locator" xlink:href="foo.xsd#us-gaap_CashFlowHedge" xlink:label="c2"/>
    <link:calculationArc xlink:type="arc" xlink:from="p" xlink:to="c1" xlink:arcrole="http://www.xbrl.org/2003/arcrole/summation-item" order="1" weight="1.0"/>
    <link:calculationArc xlink:type="arc" xlink:from="p" xlink:to="c2" xlink:arcrole="http://www.xbrl.org/2003/arcrole/summation-item" order="2" weight="1.0"/>
  </link:calculationLink>
  <link:calculationLink xlink:type="extended" xlink:role="{role2}">
    <link:loc xlink:type="locator" xlink:href="foo.xsd#us-gaap_OtherComprehensiveIncomeLossNetOfTax" xlink:label="p"/>
    <link:loc xlink:type="locator" xlink:href="foo.xsd#us-gaap_BeforeTax" xlink:label="c3"/>
    <link:loc xlink:type="locator" xlink:href="foo.xsd#us-gaap_Tax" xlink:label="c4"/>
    <link:calculationArc xlink:type="arc" xlink:from="p" xlink:to="c3" xlink:arcrole="http://www.xbrl.org/2003/arcrole/summation-item" order="1" weight="1.0"/>
    <link:calculationArc xlink:type="arc" xlink:from="p" xlink:to="c4" xlink:arcrole="http://www.xbrl.org/2003/arcrole/summation-item" order="2" weight="-1.0"/>
  </link:calculationLink>
</link:linkbase>"""
        client = MagicMock()
        client.symbol_to_cik.return_value = "0000000001"
        client.get_submissions.return_value = _fake_submissions(accession)
        client.get_calculation_linkbase_xml.return_value = xml
        client.get_company_facts.return_value = _fake_company_facts(
            {
                "OtherComprehensiveIncomeLossNetOfTax": 1_012_000.0,
                "AfsAdjustment": 1_438_000.0,
                "CashFlowHedge": -426_000.0,  # 1,438,000 + -426,000 = 1,012,000 - ties
                "BeforeTax": 1_314_000.0,
                "Tax": 302_000.0,  # 1,314,000 - 302,000 = 1,012,000 - also ties
            },
            accession,
        )

        result = _check_symbol(client, MagicMock(), "AAA")
        assert result is not None
        assert result["parents_checked"] == 1
        assert result["mismatches"] == []

    def test_no_10k_in_submissions_returns_none(self) -> None:
        client = MagicMock()
        client.symbol_to_cik.return_value = "0000000001"
        client.get_submissions.return_value = {
            "filings": {"recent": {"form": ["10-Q"], "accessionNumber": ["x"], "filingDate": ["2025-01-01"]}}
        }

        assert _check_symbol(client, MagicMock(), "AAA") is None

    def test_missing_calculation_linkbase_is_not_fatal(self) -> None:
        client = MagicMock()
        client.symbol_to_cik.return_value = "0000000001"
        client.get_submissions.return_value = _fake_submissions()
        client.get_calculation_linkbase_xml.side_effect = FileNotFoundError("no _cal.xml")

        assert _check_symbol(client, MagicMock(), "AAA") is None


class TestRun:
    def test_dry_run_never_writes_to_data_patrol_log(self) -> None:
        conn = MagicMock()
        conn.cursor.return_value = MagicMock()

        with (
            patch("utils.db.connection.get_db_connection", return_value=conn),
            patch("utils.external.sec_edgar_client.SecEdgarClient") as mock_client_cls,
            patch("algo.monitoring.data_patrol.logger.PatrolLogger") as mock_logger_cls,
        ):
            mock_client_cls.return_value.symbol_to_cik.side_effect = ValueError("not found")
            run(limit=5, symbols_override=["ZZZ"], dry_run=True)

        mock_logger_cls.assert_not_called()
        conn.commit.assert_not_called()

    def test_live_run_logs_results_and_commits(self) -> None:
        conn = MagicMock()
        conn.cursor.return_value = MagicMock()

        with (
            patch("utils.db.connection.get_db_connection", return_value=conn),
            patch("utils.external.sec_edgar_client.SecEdgarClient") as mock_client_cls,
            patch("algo.monitoring.data_patrol.logger.PatrolLogger") as mock_logger_cls,
        ):
            mock_client_cls.return_value.symbol_to_cik.side_effect = ValueError("not found")
            run(limit=5, symbols_override=["ZZZ"], dry_run=False)

        mock_logger_cls.return_value.log_results.assert_called_once()
        conn.commit.assert_called_once()
