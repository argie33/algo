#!/usr/bin/env python3
"""Tests for SEC EDGAR XML parsers (Form 4 and SCHEDULE 13G)."""

import pytest

from utils.external.sec_xml_parser import Form4Parser, Schedule13GParser


class TestForm4Parser:
    """Test Form 4 XML parsing."""

    def test_parse_form4_valid_xml(self) -> None:
        """Test parsing valid Form 4 XML with transaction data."""
        xml_content = """<?xml version="1.0"?>
<ownershipDocument>
    <reportingOwnerId>
        <rptOwnerName>JOHN SMITH</rptOwnerName>
    </reportingOwnerId>
    <reportingOwnerRelationship>
        <officerTitle>CHIEF EXECUTIVE OFFICER</officerTitle>
    </reportingOwnerRelationship>
    <nonDerivativeTransaction>
        <transactionDate>2024-01-15</transactionDate>
        <transactionAmounts>
            <transactionAcquiredDisposedCode>A</transactionAcquiredDisposedCode>
            <transactionShares>
                <sharesOwnedFollowingTransaction>100</sharesOwnedFollowingTransaction>
            </transactionShares>
        </transactionAmounts>
    </nonDerivativeTransaction>
    <nonDerivativeTransaction>
        <transactionDate>2024-01-20</transactionDate>
        <transactionAmounts>
            <transactionAcquiredDisposedCode>D</transactionAcquiredDisposedCode>
            <transactionShares>
                <sharesOwnedFollowingTransaction>50</sharesOwnedFollowingTransaction>
            </transactionShares>
        </transactionAmounts>
    </nonDerivativeTransaction>
    <postTransactionAmounts>
        <sharesOwnedFollowingTransaction>1500</sharesOwnedFollowingTransaction>
        <percentageOfClass>1.25</percentageOfClass>
    </postTransactionAmounts>
</ownershipDocument>
"""
        result = Form4Parser.parse(xml_content, "AAPL")

        assert result["insider_name"] == "JOHN SMITH"
        assert result["insider_title"] == "CHIEF EXECUTIVE OFFICER"
        assert result["shares_owned"] == 1500
        assert result["ownership_pct"] == 1.25
        assert result["recent_buys"] == 1
        assert result["recent_sells"] == 1
        assert result["net_transactions"] == 50  # 100 bought - 50 sold

    def test_parse_form4_missing_reporter(self) -> None:
        """Test parsing Form 4 with missing reportingOwnerId raises error."""
        xml_content = """<?xml version="1.0"?>
<ownershipDocument>
</ownershipDocument>
"""
        with pytest.raises(ValueError, match="missing reportingOwnerId"):
            Form4Parser.parse(xml_content, "AAPL")

    def test_parse_form4_missing_name(self) -> None:
        """Test parsing Form 4 with missing insider name raises error."""
        xml_content = """<?xml version="1.0"?>
<ownershipDocument>
    <reportingOwnerId>
        <rptOwnerName></rptOwnerName>
    </reportingOwnerId>
</ownershipDocument>
"""
        with pytest.raises(ValueError, match="missing rptOwnerName"):
            Form4Parser.parse(xml_content, "AAPL")

    def test_parse_form4_invalid_xml(self) -> None:
        """Test parsing invalid XML raises error."""
        xml_content = "<invalid>not closed"
        with pytest.raises(ValueError, match="Failed to parse Form 4 XML"):
            Form4Parser.parse(xml_content, "AAPL")


class TestSchedule13GParser:
    """Test SCHEDULE 13G XML parsing."""

    def test_parse_schedule13g_valid_xml(self) -> None:
        """Test parsing valid SCHEDULE 13G XML with holdings."""
        xml_content = """<?xml version="1.0"?>
<informationTable>
    <reportingOwner>
        <reportingOwnerName>VANGUARD GROUP INC</reportingOwnerName>
    </reportingOwner>
    <nonDerivativeHolding>
        <holdings>
            <sharesOwnedFollowingTransaction>100000000</sharesOwnedFollowingTransaction>
            <percentageOfClass>5.25</percentageOfClass>
            <valueOwnedFollowingTransaction>
                <value>30000000000</value>
            </valueOwnedFollowingTransaction>
        </holdings>
        <votingPower>
            <solePower>100000000</solePower>
        </votingPower>
        <dispositivePower>
            <solePower>100000000</solePower>
        </dispositivePower>
    </nonDerivativeHolding>
    <amendment>0</amendment>
    <periodOfReport>2024-03-31</periodOfReport>
</informationTable>
"""
        result = Schedule13GParser.parse(xml_content, "MSFT")

        assert result["investor_name"] == "VANGUARD GROUP INC"
        assert result["shares_owned"] == 100000000
        assert result["ownership_pct"] == 5.25
        assert result["value_usd"] == 30000000000  # May need division by 1000 depending on data
        assert result["sole_voting_power"] == 100000000
        assert result["sole_dispositive_power"] == 100000000
        assert result["is_amendment"] is False
        assert result["report_date"] is not None

    def test_parse_schedule13g_missing_investor(self) -> None:
        """Test parsing SCHEDULE 13G with missing investor raises error."""
        xml_content = """<?xml version="1.0"?>
<informationTable>
</informationTable>
"""
        with pytest.raises(ValueError, match="missing reportingOwner"):
            Schedule13GParser.parse(xml_content, "MSFT")

    def test_parse_schedule13g_missing_name(self) -> None:
        """Test parsing SCHEDULE 13G with missing investor name raises error."""
        xml_content = """<?xml version="1.0"?>
<informationTable>
    <reportingOwner>
        <reportingOwnerName></reportingOwnerName>
    </reportingOwner>
</informationTable>
"""
        with pytest.raises(ValueError, match="missing reportingOwnerName"):
            Schedule13GParser.parse(xml_content, "MSFT")

    def test_parse_schedule13g_missing_holdings(self) -> None:
        """Test parsing SCHEDULE 13G with missing holdings raises error."""
        xml_content = """<?xml version="1.0"?>
<informationTable>
    <reportingOwner>
        <reportingOwnerName>VANGUARD</reportingOwnerName>
    </reportingOwner>
</informationTable>
"""
        with pytest.raises(ValueError, match="missing nonDerivativeHolding"):
            Schedule13GParser.parse(xml_content, "MSFT")

    def test_parse_schedule13g_invalid_xml(self) -> None:
        """Test parsing invalid XML raises error."""
        xml_content = "<invalid>not closed"
        with pytest.raises(ValueError, match="Failed to parse SCHEDULE 13G XML"):
            Schedule13GParser.parse(xml_content, "MSFT")

    def test_parse_schedule13g_amendment_flag(self) -> None:
        """Test that amendment flag is correctly detected."""
        xml_content = """<?xml version="1.0"?>
<informationTable>
    <reportingOwner>
        <reportingOwnerName>VANGUARD GROUP INC</reportingOwnerName>
    </reportingOwner>
    <nonDerivativeHolding>
        <holdings>
            <sharesOwnedFollowingTransaction>100000000</sharesOwnedFollowingTransaction>
            <percentageOfClass>5.25</percentageOfClass>
        </holdings>
    </nonDerivativeHolding>
    <amendment>1</amendment>
</informationTable>
"""
        result = Schedule13GParser.parse(xml_content, "MSFT")
        assert result["is_amendment"] is True
