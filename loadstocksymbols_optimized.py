#!/usr/bin/env python3
"""
Optimized Stock Symbols Loader
Uses the enhanced data loader framework for improved performance and reliability.
"""

import os
import re
import csv
import json
import sys
import logging
import requests
from typing import Dict, List, Generator, Any
from enhanced_data_loader import DataLoaderOptimizer, create_data_validator, log_data_loader_start, log_data_loader_end

# Configure logging
logger = logging.getLogger(__name__)

class OptimizedStockSymbolsLoader:
    """
    Enhanced stock symbols loader with comprehensive data validation and optimization.
    """
    
    def __init__(self):
        """Initialize the optimized loader."""
        self.loader = DataLoaderOptimizer(
            loader_name="stock_symbols_optimized",
            table_name="stock_symbols",
            batch_size=2000  # Increased batch size for better performance
        )
        
        # Data source URLs
        self.nasdaq_url = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
        self.other_url = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
        
        # Enhanced exclusion patterns for better data quality
        self.exclusion_patterns = [
            r"\bpreferred\b",
            r"\bredeemable warrant(s)?\b", 
            r"\bwarrant(s)?\b",
            r"\bright(s)?\b",
            r"\bunit(s)?\b",
            r"\bclass [abc]\b",
            r"\bseries [abc]\b",
            r"\bdepositary share(s)?\b",
            r"\btest\b",
            r"\bwhen issued\b"
        ]
        
        # Compile patterns for performance
        self.compiled_patterns = [re.compile(pattern, re.IGNORECASE) for pattern in self.exclusion_patterns]
        
        # Create data validator
        self.data_validator = create_data_validator(
            required_fields=['symbol', 'name', 'exchange', 'market_category'],
            field_validators={
                'symbol': self._validate_symbol,
                'name': self._validate_name,
                'exchange': self._validate_exchange,
                'market_category': self._validate_market_category
            }
        )
    
    def _validate_symbol(self, symbol: str) -> bool:
        """Validate stock symbol format."""
        if not symbol or len(symbol) > 10:
            return False
        
        # Symbol should be alphanumeric with optional dots/dashes
        if not re.match(r'^[A-Z0-9.-]+$', symbol):
            return False
        
        # Exclude test symbols and invalid patterns
        if symbol.startswith('TEST') or symbol.endswith('.TEST'):
            return False
        
        return True
    
    def _validate_name(self, name: str) -> bool:
        """Validate company name."""
        if not name or len(name) > 500:
            return False
        
        # Check for exclusion patterns in name
        for pattern in self.compiled_patterns:
            if pattern.search(name):
                return False
        
        return True
    
    def _validate_exchange(self, exchange: str) -> bool:
        """Validate exchange code."""
        valid_exchanges = {'NASDAQ', 'NYSE', 'AMEX', 'ARCA', 'BATS'}
        return exchange in valid_exchanges
    
    def _validate_market_category(self, category: str) -> bool:
        """Validate market category."""
        valid_categories = {'Q', 'G', 'S', 'N', 'A', 'P', 'Z'}
        return category in valid_categories
    
    def fetch_nasdaq_symbols(self) -> Generator[Dict[str, Any], None, None]:
        """
        Fetch and process NASDAQ listed symbols.
        
        Yields:
            Dictionary containing symbol data
        """
        logger.info("📥 Fetching NASDAQ listed symbols...")
        
        try:
            response = requests.get(self.nasdaq_url, timeout=30)
            response.raise_for_status()
            
            # Parse CSV data
            lines = response.text.strip().split('\n')
            
            # Skip header and footer
            data_lines = lines[1:-1]  # Remove header and footer
            
            reader = csv.reader(data_lines, delimiter='|')
            
            for row in reader:
                if len(row) >= 4:
                    symbol = row[0].strip()
                    name = row[1].strip()
                    market_category = row[2].strip()
                    test_issue = row[3].strip()
                    
                    # Skip test issues
                    if test_issue == 'Y':
                        continue
                    
                    yield {
                        'symbol': symbol,
                        'name': name,
                        'exchange': 'NASDAQ',
                        'market_category': market_category,
                        'sector': None,  # Not available in NASDAQ data
                        'industry': None,  # Not available in NASDAQ data
                        'country': 'USA',
                        'is_etf': self._detect_etf(name),
                        'updated_at': 'NOW()'
                    }
            
            logger.info(f"✅ NASDAQ symbols fetch completed")
            
        except Exception as e:
            logger.error(f"❌ Failed to fetch NASDAQ symbols: {e}")
            raise
    
    def fetch_other_symbols(self) -> Generator[Dict[str, Any], None, None]:
        """
        Fetch and process other exchange symbols.
        
        Yields:
            Dictionary containing symbol data
        """
        logger.info("📥 Fetching other exchange symbols...")
        
        try:
            response = requests.get(self.other_url, timeout=30)
            response.raise_for_status()
            
            # Parse CSV data
            lines = response.text.strip().split('\n')
            
            # Skip header and footer
            data_lines = lines[1:-1]  # Remove header and footer
            
            reader = csv.reader(data_lines, delimiter='|')
            
            exchange_mapping = {
                'A': 'AMEX',
                'N': 'NYSE', 
                'P': 'ARCA',
                'Z': 'BATS'
            }
            
            for row in reader:
                if len(row) >= 4:
                    symbol = row[0].strip()
                    name = row[1].strip()
                    exchange_code = row[2].strip()
                    test_issue = row[6].strip() if len(row) > 6 else 'N'
                    
                    # Skip test issues
                    if test_issue == 'Y':
                        continue
                    
                    exchange = exchange_mapping.get(exchange_code, 'OTHER')
                    
                    yield {
                        'symbol': symbol,
                        'name': name,
                        'exchange': exchange,
                        'market_category': exchange_code,
                        'sector': None,  # Not available in other data
                        'industry': None,  # Not available in other data
                        'country': 'USA',
                        'is_etf': self._detect_etf(name),
                        'updated_at': 'NOW()'
                    }
            
            logger.info(f"✅ Other exchange symbols fetch completed")
            
        except Exception as e:
            logger.error(f"❌ Failed to fetch other exchange symbols: {e}")
            raise
    
    def _detect_etf(self, name: str) -> bool:
        """Detect if a security is an ETF based on name patterns."""
        etf_patterns = [
            r'\betf\b',
            r'\bfund\b',
            r'\btrust\b',
            r'\bindex\b',
            r'\bshares\b'
        ]
        
        name_lower = name.lower()
        for pattern in etf_patterns:
            if re.search(pattern, name_lower):
                return True
        
        return False
    
    def combined_data_source(self) -> Generator[Dict[str, Any], None, None]:
        """
        Combined data source that fetches from both NASDAQ and other exchanges.
        
        Yields:
            Dictionary containing symbol data
        """
        # Fetch NASDAQ symbols
        yield from self.fetch_nasdaq_symbols()
        
        # Fetch other exchange symbols
        yield from self.fetch_other_symbols()
    
    def validate_table_schema(self) -> bool:
        """Validate that the stock_symbols table has the required schema."""
        required_columns = [
            {'name': 'symbol', 'type': 'varchar'},
            {'name': 'name', 'type': 'varchar'},
            {'name': 'exchange', 'type': 'varchar'},
            {'name': 'market_category', 'type': 'varchar'},
            {'name': 'sector', 'type': 'varchar'},
            {'name': 'industry', 'type': 'varchar'},
            {'name': 'country', 'type': 'varchar'},
            {'name': 'is_etf', 'type': 'boolean'},
            {'name': 'updated_at', 'type': 'timestamp'}
        ]
        
        return self.loader.validate_table_schema(required_columns)
    
    def run_optimized_load(self) -> Dict[str, Any]:
        """
        Execute the optimized stock symbols loading process.
        
        Returns:
            Processing results and metrics
        """
        log_data_loader_start(
            "OptimizedStockSymbolsLoader",
            "Load stock symbols from NASDAQ and other exchanges with enhanced validation"
        )
        
        try:
            # Validate table schema first
            if not self.validate_table_schema():
                raise Exception("Table schema validation failed")
            
            # Process data with optimization
            result = self.loader.process_data_with_validation(
                data_source_func=self.combined_data_source,
                data_validator_func=self.data_validator,
                conflict_columns=['symbol']  # Use symbol as the unique key for conflict resolution
            )
            
            log_data_loader_end(
                "OptimizedStockSymbolsLoader",
                result['success'],
                result.get('metrics')
            )
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Optimized stock symbols loading failed: {e}")
            log_data_loader_end("OptimizedStockSymbolsLoader", False)
            raise


def main():
    """Main execution function."""
    try:
        # Verify environment variables
        if not os.environ.get("DB_SECRET_ARN"):
            logger.error("❌ DB_SECRET_ARN environment variable not set")
            sys.exit(1)
        
        # Create and run the optimized loader
        loader = OptimizedStockSymbolsLoader()
        result = loader.run_optimized_load()
        
        if result['success']:
            logger.info("🎉 Stock symbols loading completed successfully!")
            sys.exit(0)
        else:
            logger.error("❌ Stock symbols loading failed!")
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"❌ Fatal error in stock symbols loader: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()