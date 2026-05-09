#!/usr/bin/env python3
import re

file_path = './src/App.jsx'

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# List of imports to convert to lazy loading
imports_to_convert = [
    'TradeTracker',
    'PortfolioDashboard',
    'PerformanceMetrics',
    'HedgeHelper',
    'PortfolioOptimizerNew',
    'ServiceHealth',
    'Settings',
    'SignalIntelligence',
    'AuditViewer',
    'NotificationCenter',
    'Home',
    'Firm',
    'Contact',
    'About',
    'OurTeam',
    'MissionValues',
    'ResearchInsights',
    'ArticleDetail',
    'Terms',
    'Privacy',
    'InvestmentTools',
    'WealthManagement',
    'LoginPage',
]

# Convert each import
for component in imports_to_convert:
    # Pattern for both regular pages and marketing pages
    patterns = [
        (
            f'import {component} from "./pages/{component}";',
            f'const {component} = React.lazy(() => import("./pages/{component}"));'
        ),
        (
            f'import {component} from "./pages/marketing/{component}";',
            f'const {component} = React.lazy(() => import("./pages/marketing/{component}"));'
        ),
    ]

    for old_pattern, new_pattern in patterns:
        if old_pattern in content:
            content = content.replace(old_pattern, new_pattern)
            print(f"[OK] Converted {component}")

# Write back
with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("\n[SUCCESS] All imports converted to lazy loading!")
