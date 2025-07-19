#!/usr/bin/env python3
"""
Comprehensive Data Quality Validation System
Implements institutional-grade data validation and quality scoring for financial data.
"""

import os
import sys
import json
import logging
import traceback
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import boto3
import psycopg2
from psycopg2.extras import RealDictCursor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('/tmp/data_quality_validator.log', mode='a')
    ]
)
logger = logging.getLogger(__name__)

class DataQualityLevel(Enum):
    """Data quality levels."""
    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"
    CRITICAL = "critical"

@dataclass
class QualityCheck:
    """Individual quality check result."""
    name: str
    description: str
    passed: bool
    score: float
    details: Dict[str, Any]
    severity: str

@dataclass
class QualityReport:
    """Complete quality report for a dataset."""
    dataset_name: str
    table_name: str
    check_timestamp: datetime
    overall_score: float
    quality_level: DataQualityLevel
    record_count: int
    checks: List[QualityCheck]
    recommendations: List[str]
    metadata: Dict[str, Any]

class DataQualityValidator:
    """
    Comprehensive data quality validator for financial datasets.
    """
    
    def __init__(self):
        """Initialize the data quality validator."""
        self.db_config = self._get_database_config()
        self.connection = None
        
        # Quality thresholds
        self.quality_thresholds = {
            DataQualityLevel.EXCELLENT: 0.95,
            DataQualityLevel.GOOD: 0.85,
            DataQualityLevel.FAIR: 0.70,
            DataQualityLevel.POOR: 0.50,
            DataQualityLevel.CRITICAL: 0.0
        }
        
        logger.info("🔍 Data Quality Validator initialized")
    
    def _get_database_config(self) -> Dict[str, str]:
        """Get database configuration from AWS Secrets Manager."""
        try:
            secret_arn = os.environ.get("DB_SECRET_ARN")
            if not secret_arn:
                raise ValueError("DB_SECRET_ARN environment variable not set")
            
            client = boto3.client("secretsmanager")
            response = client.get_secret_value(SecretId=secret_arn)
            secret = json.loads(response["SecretString"])
            
            return {
                'host': secret["host"],
                'port': secret.get("port", "5432"),
                'user': secret["username"],
                'password': secret["password"],
                'database': secret["dbname"]
            }
        except Exception as e:
            logger.error(f"❌ Failed to get database config: {e}")
            raise
    
    def _get_connection(self):
        """Get database connection."""
        if not self.connection or self.connection.closed:
            self.connection = psycopg2.connect(
                host=self.db_config['host'],
                port=self.db_config['port'],
                user=self.db_config['user'],
                password=self.db_config['password'],
                database=self.db_config['database'],
                sslmode="require"
            )
        return self.connection
    
    def _categorize_quality_level(self, score: float) -> DataQualityLevel:
        """Categorize quality score into quality level."""
        for level, threshold in self.quality_thresholds.items():
            if score >= threshold:
                return level
        return DataQualityLevel.CRITICAL
    
    def _validate_stock_symbols(self) -> QualityCheck:
        """Validate stock symbols data quality."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Get basic statistics
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_count,
                    COUNT(DISTINCT symbol) as unique_symbols,
                    COUNT(CASE WHEN name IS NULL OR name = '' THEN 1 END) as missing_names,
                    COUNT(CASE WHEN exchange IS NULL OR exchange = '' THEN 1 END) as missing_exchanges
                FROM stock_symbols
            """)
            
            result = cursor.fetchone()
            total_count = result['total_count']
            
            if total_count == 0:
                return QualityCheck(
                    name="stock_symbols_validation",
                    description="Stock symbols table validation",
                    passed=False,
                    score=0.0,
                    details={"error": "No data found in stock_symbols table"},
                    severity="critical"
                )
            
            # Calculate quality metrics
            unique_ratio = result['unique_symbols'] / total_count
            missing_name_ratio = result['missing_names'] / total_count
            missing_exchange_ratio = result['missing_exchanges'] / total_count
            
            # Calculate overall score
            score = (unique_ratio * 0.4 + (1 - missing_name_ratio) * 0.3 + (1 - missing_exchange_ratio) * 0.3)
            
            details = {
                "total_symbols": total_count,
                "unique_symbols": result['unique_symbols'],
                "missing_names": result['missing_names'],
                "missing_exchanges": result['missing_exchanges'],
                "unique_ratio": unique_ratio,
                "missing_name_ratio": missing_name_ratio,
                "missing_exchange_ratio": missing_exchange_ratio
            }
            
            passed = score >= 0.8
            severity = "info" if score >= 0.9 else "warning" if score >= 0.7 else "error"
            
            return QualityCheck(
                name="stock_symbols_validation",
                description="Stock symbols table validation",
                passed=passed,
                score=score,
                details=details,
                severity=severity
            )
            
        except Exception as e:
            logger.error(f"❌ Stock symbols validation failed: {e}")
            return QualityCheck(
                name="stock_symbols_validation",
                description="Stock symbols table validation",
                passed=False,
                score=0.0,
                details={"error": str(e)},
                severity="critical"
            )
    
    def validate_dataset(self, dataset_name: str) -> QualityReport:
        """
        Validate a complete dataset and generate quality report.
        
        Args:
            dataset_name: Name of the dataset to validate
            
        Returns:
            QualityReport with comprehensive validation results
        """
        logger.info(f"🔍 Starting data quality validation for dataset: {dataset_name}")
        
        checks = []
        
        # Run all validation checks
        checks.append(self._validate_stock_symbols())
        
        # Calculate overall score
        total_score = sum(check.score for check in checks)
        overall_score = total_score / len(checks) if checks else 0.0
        
        # Determine quality level
        quality_level = self._categorize_quality_level(overall_score)
        
        # Generate recommendations
        recommendations = []
        for check in checks:
            if not check.passed:
                recommendations.append(f"Fix issues in {check.name}")
        
        # Create quality report
        report = QualityReport(
            dataset_name=dataset_name,
            table_name="multiple",
            check_timestamp=datetime.now(),
            overall_score=overall_score,
            quality_level=quality_level,
            record_count=sum(check.details.get("total_records", 0) for check in checks),
            checks=checks,
            recommendations=recommendations,
            metadata={
                "validator_version": "1.0.0",
                "total_checks": len(checks),
                "passed_checks": sum(1 for check in checks if check.passed),
                "failed_checks": sum(1 for check in checks if not check.passed)
            }
        )
        
        logger.info(f"✅ Data quality validation completed for {dataset_name}")
        logger.info(f"📊 Overall score: {overall_score:.3f} ({quality_level.value})")
        
        return report


def main():
    """Main execution function."""
    try:
        # Verify environment
        if not os.environ.get("DB_SECRET_ARN"):
            logger.error("❌ DB_SECRET_ARN environment variable not set")
            sys.exit(1)
        
        # Create validator
        validator = DataQualityValidator()
        
        # Run validation
        report = validator.validate_dataset("financial_data")
        
        # Print results
        print(f"\n📊 Data Quality Report: {report.overall_score:.3f} ({report.quality_level.value})")
        
        # Exit with appropriate code
        if report.quality_level in [DataQualityLevel.EXCELLENT, DataQualityLevel.GOOD]:
            logger.info("🎉 Data quality validation passed!")
            sys.exit(0)
        else:
            logger.warning(f"⚠️ Data quality issues detected: {report.quality_level.value}")
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"❌ Fatal error in data quality validation: {e}")
        logger.error(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()