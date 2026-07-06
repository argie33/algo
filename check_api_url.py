#!/usr/bin/env python3
"""Check API URL configuration."""

import os
from dashboard.api_data_layer import API_BASE_URL

print(f'API_BASE_URL: {API_BASE_URL}')
print(f'DASHBOARD_API_URL env: {os.environ.get("DASHBOARD_API_URL", "[NOT SET]")}')
