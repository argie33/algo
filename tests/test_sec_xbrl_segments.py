#!/usr/bin/env python3
"""Tests for SEC XBRL segment disclosure parser."""

import pytest

from utils.external.sec_xbrl_segments import XBRLSegmentParser


class TestXBRLSegmentParser:
    """Test XBRL segment data parsing."""

    def test_parse_companyfacts_valid_data(self) -> None:
        """Test parsing valid companyfacts response with segment data."""
        facts_response = {
            'cik': '0000320193',
            'entityName': 'Apple Inc',
            'facts': {
                'us-gaap': {
                    'SegmentNumber': {
                        'units': {
                            'pure': [
                                {'value': '3', 'fy': 2023, 'accessionNumber': '0000320193-23-000119'},
                            ]
                        }
                    },
                    'SegmentIdentificationCode': {
                        'units': {
                            'pure': [
                                {'value': 'Americas', 'segment': 'Americas_1', 'fy': 2023},
                                {'value': 'Europe', 'segment': 'Europe_1', 'fy': 2023},
                                {'value': 'Greater China', 'segment': 'GreaterChina_1', 'fy': 2023},
                            ]
                        }
                    },
                    'SegmentRevenue': {
                        'units': {
                            'USD': [
                                {'value': '47000000000', 'segment': 'Americas_1', 'fy': 2023},
                                {'value': '25000000000', 'segment': 'Europe_1', 'fy': 2023},
                                {'value': '18000000000', 'segment': 'GreaterChina_1', 'fy': 2023},
                            ]
                        }
                    },
                }
            }
        }

        result = XBRLSegmentParser.parse_companyfacts(facts_response, "AAPL")

        assert result['data_available'] is True
        assert result['segment_count'] == 3
        assert result['largest_segment_revenue_pct'] == pytest.approx(52.25, 0.1)  # 47B / 90B
        # HHI = (47/90)^2 + (25/90)^2 + (18/90)^2 = 0.2746 + 0.0773 + 0.0400 = 0.3919 * 10000 = 3919
        assert result['revenue_concentration_hhi'] == pytest.approx(3919, 10)

    def test_parse_companyfacts_single_segment(self) -> None:
        """Test parsing with single segment (monopoly case)."""
        facts_response = {
            'cik': '0000123456',
            'entityName': 'Test Corp',
            'facts': {
                'us-gaap': {
                    'SegmentNumber': {
                        'units': {
                            'pure': [
                                {'value': '1', 'fy': 2023},
                            ]
                        }
                    },
                    'SegmentIdentificationCode': {
                        'units': {
                            'pure': [
                                {'value': 'All', 'segment': 'All_1', 'fy': 2023},
                            ]
                        }
                    },
                    'SegmentRevenue': {
                        'units': {
                            'USD': [
                                {'value': '100000000', 'segment': 'All_1', 'fy': 2023},
                            ]
                        }
                    },
                }
            }
        }

        result = XBRLSegmentParser.parse_companyfacts(facts_response, "TEST")

        assert result['data_available'] is True
        assert result['segment_count'] == 1
        assert result['largest_segment_revenue_pct'] == 100.0
        assert result['revenue_concentration_hhi'] == pytest.approx(10000, 10)  # Monopoly

    def test_parse_companyfacts_no_facts(self) -> None:
        """Test parsing with missing facts section."""
        facts_response = {
            'cik': '0000123456',
            'entityName': 'Test Corp',
        }

        result = XBRLSegmentParser.parse_companyfacts(facts_response, "TEST")

        assert result['data_available'] is False
        assert result['reason'] == 'no_us_gaap_facts'

    def test_parse_companyfacts_no_segment_revenue(self) -> None:
        """Test parsing with no SegmentRevenue facts."""
        facts_response = {
            'cik': '0000123456',
            'entityName': 'Test Corp',
            'facts': {
                'us-gaap': {
                    'SegmentNumber': {
                        'units': {
                            'pure': [
                                {'value': '3', 'fy': 2023},
                            ]
                        }
                    },
                }
            }
        }

        result = XBRLSegmentParser.parse_companyfacts(facts_response, "TEST")

        assert result['data_available'] is False
        assert result['reason'] == 'no_segment_revenue_data'

    def test_compute_herfindahl_index(self) -> None:
        """Test Herfindahl index calculation."""
        # Duopoly (50-50): HHI = 0.5^2 + 0.5^2 = 0.5 * 10000 = 5000
        hhi = XBRLSegmentParser._compute_herfindahl_index([50.0, 50.0], 100.0)
        assert hhi == pytest.approx(5000, 1)

        # Monopoly: HHI = 1^2 = 10000
        hhi = XBRLSegmentParser._compute_herfindahl_index([100.0], 100.0)
        assert hhi == pytest.approx(10000, 1)

        # Competitive (4-way): HHI = 4 * (0.25^2) = 2500
        hhi = XBRLSegmentParser._compute_herfindahl_index([25.0, 25.0, 25.0, 25.0], 100.0)
        assert hhi == pytest.approx(2500, 1)

    def test_parse_xbrl_xml(self) -> None:
        """Test parsing raw XBRL XML instance."""
        xml_content = """<?xml version="1.0"?>
<xbrl xmlns:us-gaap="http://xbrl.us/us-gaap/2023-01-31"
      xmlns:xbrli="http://www.xbrl.org/2003/instance">
    <us-gaap:SegmentRevenue contextRef="OperatingSegment_1" unitRef="USD">
        4700000000
    </us-gaap:SegmentRevenue>
    <us-gaap:SegmentRevenue contextRef="OperatingSegment_2" unitRef="USD">
        2500000000
    </us-gaap:SegmentRevenue>
    <us-gaap:SegmentRevenue contextRef="OperatingSegment_3" unitRef="USD">
        1800000000
    </us-gaap:SegmentRevenue>
</xbrl>
"""

        result = XBRLSegmentParser.parse_xbrl_xml(xml_content, "TEST")

        assert result['data_available'] is True
        assert result['segment_count'] == 3
        assert result['largest_segment_revenue_pct'] == pytest.approx(52.25, 0.1)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
