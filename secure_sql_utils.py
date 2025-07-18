#!/usr/bin/env python3
"""
Secure SQL Utilities for Python Data Loaders
Prevents SQL injection vulnerabilities in Python scripts
"""

import logging
from typing import List, Dict, Any, Optional, Tuple

class SecureSQLBuilder:
    """
    Secure SQL query builder for Python data loaders
    """
    
    def __init__(self):
        # Whitelisted table names - only these tables are allowed
        self.allowed_tables = {
            'price_daily',
            'etf_price_daily', 
            'price_weekly',
            'etf_price_weekly',
            'price_monthly',
            'etf_price_monthly',
            'technicals_daily',
            'technicals_weekly', 
            'technicals_monthly',
            'earnings_estimate',
            'earnings_history',
            'stock_symbols',
            'etf_symbols',
            'market_data',
            'sentiment_data',
            'news_articles',
            'economic_data',
            'aaii_sentiment',
            'fear_greed_index',
            'naaim_exposure',
            'balance_sheet',
            'income_statement',
            'cash_flow',
            'quarterly_balance_sheet',
            'quarterly_income_statement',
            'quarterly_cash_flow',
            'ttm_balance_sheet',
            'ttm_income_statement',
            'ttm_cash_flow',
            'last_updated'
        }
        
        # Whitelisted column patterns
        self.allowed_column_patterns = {
            'symbol', 'date', 'open', 'high', 'low', 'close', 'volume',
            'adj_close', 'period_end', 'created_at', 'updated_at', 'fetched_at',
            'earnings_date', 'eps_estimate', 'revenue_estimate',
            'sentiment_score', 'title', 'content', 'source',
            'rsi', 'macd', 'signal', 'histogram', 'bb_upper', 'bb_middle', 'bb_lower',
            'script_name', 'last_run', 'value', 'percentage'
        }
    
    def validate_table_name(self, table_name: str) -> str:
        """
        Validate table name against whitelist
        
        Args:
            table_name: Table name to validate
            
        Returns:
            Validated table name
            
        Raises:
            ValueError: If table name is not in whitelist
        """
        if not table_name or not isinstance(table_name, str):
            raise ValueError("Table name must be a non-empty string")
        
        clean_table = table_name.lower().strip()
        
        if clean_table not in self.allowed_tables:
            raise ValueError(f"Unauthorized table access: {table_name}")
        
        return clean_table
    
    def validate_column_list(self, columns: str) -> str:
        """
        Validate column list string
        
        Args:
            columns: Comma-separated column names
            
        Returns:
            Validated column list
            
        Raises:
            ValueError: If any column is not allowed
        """
        if not columns or not isinstance(columns, str):
            raise ValueError("Column list must be a non-empty string")
        
        # Parse column names
        column_names = [col.strip().lower() for col in columns.split(',')]
        
        # Validate each column
        for col in column_names:
            if not any(pattern in col for pattern in self.allowed_column_patterns):
                logging.warning(f"Potentially unsafe column name: {col}")
        
        return columns
    
    def build_insert_query(self, table_name: str, columns: str) -> str:
        """
        Build secure INSERT query
        
        Args:
            table_name: Target table name
            columns: Comma-separated column names
            
        Returns:
            Secure INSERT query string
        """
        validated_table = self.validate_table_name(table_name)
        validated_columns = self.validate_column_list(columns)
        
        # Use parameterized query - table name is validated from whitelist
        query = f"INSERT INTO {validated_table} ({validated_columns}) VALUES %s"
        
        logging.info(f"🔒 Built secure INSERT query for table: {validated_table}")
        return query
    
    def build_select_query(self, table_name: str, columns: str = "*", 
                          where_clause: Optional[str] = None,
                          limit: Optional[int] = None) -> Tuple[str, List[Any]]:
        """
        Build secure SELECT query with parameters
        
        Args:
            table_name: Source table name
            columns: Columns to select
            where_clause: WHERE clause template with %s placeholders
            limit: LIMIT value
            
        Returns:
            Tuple of (query_string, parameters_list)
        """
        validated_table = self.validate_table_name(table_name)
        
        if columns != "*":
            validated_columns = self.validate_column_list(columns)
        else:
            validated_columns = "*"
        
        query = f"SELECT {validated_columns} FROM {validated_table}"
        params = []
        
        if where_clause:
            query += f" WHERE {where_clause}"
        
        if limit is not None:
            if not isinstance(limit, int) or limit < 1:
                raise ValueError("Limit must be a positive integer")
            query += " LIMIT %s"
            params.append(limit)
        
        logging.info(f"🔒 Built secure SELECT query for table: {validated_table}")
        return query, params
    
    def build_update_query(self, table_name: str, set_clause: str,
                          where_clause: str) -> str:
        """
        Build secure UPDATE query
        
        Args:
            table_name: Target table name
            set_clause: SET clause with %s placeholders
            where_clause: WHERE clause with %s placeholders
            
        Returns:
            Secure UPDATE query string
        """
        validated_table = self.validate_table_name(table_name)
        
        if not where_clause:
            raise ValueError("UPDATE queries must have WHERE clause for security")
        
        query = f"UPDATE {validated_table} SET {set_clause} WHERE {where_clause}"
        
        logging.info(f"🔒 Built secure UPDATE query for table: {validated_table}")
        return query
    
    def build_delete_query(self, table_name: str, where_clause: str) -> str:
        """
        Build secure DELETE query
        
        Args:
            table_name: Target table name
            where_clause: WHERE clause with %s placeholders
            
        Returns:
            Secure DELETE query string
        """
        validated_table = self.validate_table_name(table_name)
        
        if not where_clause:
            raise ValueError("DELETE queries must have WHERE clause for security")
        
        query = f"DELETE FROM {validated_table} WHERE {where_clause}"
        
        logging.info(f"🔒 Built secure DELETE query for table: {validated_table}")
        return query

def secure_execute_values(cursor, table_name: str, columns: str, data: List[tuple]):
    """
    Secure wrapper for psycopg2.extras.execute_values
    
    Args:
        cursor: Database cursor
        table_name: Target table name
        columns: Column list string
        data: Data tuples to insert
    """
    from psycopg2.extras import execute_values
    
    builder = SecureSQLBuilder()
    secure_query = builder.build_insert_query(table_name, columns)
    
    logging.info(f"🔒 Executing secure bulk insert: {len(data)} rows into {table_name}")
    execute_values(cursor, secure_query, data)

def secure_execute_query(cursor, table_name: str, columns: str = "*",
                        where_clause: Optional[str] = None,
                        params: Optional[List[Any]] = None,
                        limit: Optional[int] = None):
    """
    Secure wrapper for cursor.execute SELECT queries
    
    Args:
        cursor: Database cursor
        table_name: Source table name
        columns: Columns to select
        where_clause: WHERE clause with %s placeholders
        params: Parameters for WHERE clause
        limit: LIMIT value
        
    Returns:
        Query results
    """
    builder = SecureSQLBuilder()
    query, query_params = builder.build_select_query(
        table_name, columns, where_clause, limit
    )
    
    # Combine query params with user params
    all_params = (params or []) + query_params
    
    logging.info(f"🔒 Executing secure SELECT query on {table_name}")
    cursor.execute(query, all_params)
    
    return cursor.fetchall()

# Security audit function
def audit_sql_query(query: str, context: str = "unknown") -> Dict[str, Any]:
    """
    Audit SQL query for potential security issues
    
    Args:
        query: SQL query to audit
        context: Context information for logging
        
    Returns:
        Audit results dictionary
    """
    dangerous_patterns = [
        (r'f".*\{.*\}.*"', 'F-string with variables in SQL'),
        (r"f'.*\{.*\}.*'", 'F-string with variables in SQL'),
        (r'\.format\(', 'String format() method in SQL'),
        (r'%.*%', 'String interpolation in SQL'),
        (r'DROP\s+TABLE', 'DROP TABLE statement'),
        (r'DELETE\s+FROM.*WHERE\s*$', 'DELETE without WHERE clause'),
        (r'UPDATE.*SET.*WHERE\s*$', 'UPDATE without WHERE clause'),
    ]
    
    issues = []
    risk_level = "LOW"
    
    for pattern, description in dangerous_patterns:
        import re
        if re.search(pattern, query, re.IGNORECASE):
            issues.append({
                'pattern': pattern,
                'description': description,
                'risk': 'HIGH' if 'DROP' in pattern or 'DELETE' in pattern or 'f"' in pattern else 'MEDIUM'
            })
            if 'HIGH' in issues[-1]['risk']:
                risk_level = "HIGH"
            elif risk_level != "HIGH" and 'MEDIUM' in issues[-1]['risk']:
                risk_level = "MEDIUM"
    
    audit_result = {
        'query': query[:100] + "..." if len(query) > 100 else query,
        'context': context,
        'risk_level': risk_level,
        'issues': issues,
        'is_secure': len(issues) == 0
    }
    
    if not audit_result['is_secure']:
        logging.warning(f"🚨 SQL Security Issue in {context}: {risk_level} risk")
        for issue in issues:
            logging.warning(f"   - {issue['description']} (Risk: {issue['risk']})")
    
    return audit_result

if __name__ == "__main__":
    # Test the secure SQL builder
    builder = SecureSQLBuilder()
    
    # Test valid operations
    try:
        insert_query = builder.build_insert_query("price_daily", "symbol, date, open, high, low, close, volume")
        print("✅ Valid INSERT query:", insert_query)
        
        select_query, params = builder.build_select_query("price_daily", "symbol, close", "date > %s", 100)
        print("✅ Valid SELECT query:", select_query, "Params:", params)
        
    except ValueError as e:
        print("❌ Security validation failed:", e)
    
    # Test invalid operations
    try:
        invalid_query = builder.build_insert_query("malicious_table", "symbol, date")
        print("❌ This should not succeed:", invalid_query)
    except ValueError as e:
        print("✅ Security validation caught unauthorized table:", e)