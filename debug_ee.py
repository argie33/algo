#!/usr/bin/env python3
"""Debug EE extraction in detail."""

from utils.external.sec_statements import get_income_statement
from utils.external.sec_edgar_client import SecEdgarClient

client = SecEdgarClient()
statements = get_income_statement(client, "EE", period="annual")

print(f"Total statements: {len(statements)}\n")

for stmt in statements:
    print(f"Year {stmt['fiscal_year']} ({stmt['form']}):")
    print(f"  Period end: {stmt.get('period_end')}")
    print(f"  Net income: {stmt.get('net_income_loss')}")
    print(f"  Revenues: {stmt.get('revenues')}")
    print(f"  Revenue (ASC 606): {stmt.get('revenue_from_contract_with_customer_excluding_assessed_tax')}")
    print(f"  Sales revenue: {stmt.get('sales_revenue_net')}")
    print()
