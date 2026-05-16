#!/usr/bin/env python3
"""Check deployment status of infrastructure changes."""

import sys
import json

def check_terraform_config():
    """Check if terraform.tfvars has cognito_enabled = false."""
    try:
        import os
        tfvars_path = os.path.join(os.path.dirname(__file__), 'terraform', 'terraform.tfvars')
        with open(tfvars_path, 'r') as f:
            content = f.read()
            # Check for cognito_enabled with flexible spacing and false value
            if 'cognito_enabled' in content and 'false' in content:
                # More flexible check: look for the actual setting
                for line in content.split('\n'):
                    if 'cognito_enabled' in line and 'false' in line:
                        print("[OK] terraform.tfvars: cognito_enabled = false")
                        return True
            print("[FAIL] terraform.tfvars: cognito_enabled not set to false")
            return False
    except Exception as e:
        print(f"[ERROR] Cannot read terraform.tfvars: {e}")
        return False

def check_terraform_api_gateway_config():
    """Check if API Gateway route is configured to use NONE auth."""
    try:
        import os
        services_path = os.path.join(os.path.dirname(__file__), 'terraform', 'modules', 'services', 'main.tf')
        with open(services_path, 'r') as f:
            content = f.read()
            # Check for the conditional authorization_type
            if 'authorization_type = var.cognito_enabled ? "JWT" : "NONE"' in content:
                print("[OK] API Gateway route will use NONE auth when cognito_enabled = false")
                return True
            else:
                print("[WARN] API Gateway route configuration may need review")
                return False
    except Exception as e:
        print(f"[ERROR] Cannot read services/main.tf: {e}")
        return False

def main():
    """Run all checks."""
    print("=" * 70)
    print("DEPLOYMENT STATUS CHECK")
    print("=" * 70)

    print("\n1. TERRAFORM CONFIGURATION")
    print("-" * 70)
    config_ok = check_terraform_config()
    api_gw_ok = check_terraform_api_gateway_config()

    print("\n2. DEPLOYMENT STATUS")
    print("-" * 70)
    print("To verify deployment status, check GitHub Actions:")
    print("  1. Go to: https://github.com/argie33/algo/actions")
    print("  2. Find: deploy-all-infrastructure workflow")
    print("  3. Check status: If FAILED, read logs; if PASSED, continue; if RUNNING, wait")
    print()
    print("Once workflow completes:")
    print("  curl -w 'Status: %%{http_code}\\n' \\")
    print("    https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/algo/status")
    print()
    print("Expected: 200 with real data (not 401 Unauthorized)")

    print("\n3. WHAT'S HAPPENING")
    print("-" * 70)
    print("When GitHub Actions runs deploy-all-infrastructure.yml:")
    print("  1. Terraform reads terraform.tfvars (cognito_enabled = false)")
    print("  2. Terraform plan shows: authorization_type 'JWT' -> 'NONE'")
    print("  3. Terraform apply updates API Gateway route in AWS")
    print("  4. API Gateway auto-deploy pushes new config (happens in ~30s)")
    print("  5. Data endpoints now return 200 instead of 401")

    print("\n4. MANUAL TRIGGER (if needed)")
    print("-" * 70)
    print("If workflow hasn't run yet:")
    print("  1. Go to GitHub Actions")
    print("  2. Select 'Deploy All Infrastructure'")
    print("  3. Click 'Run workflow'")
    print("  4. Leave defaults, click 'Run'")
    print("  5. Monitor logs for 15-20 minutes")

    print("\n" + "=" * 70)
    if config_ok and api_gw_ok:
        print("[READY] Configuration is correct. Awaiting workflow completion.")
        return 0
    else:
        print("[ACTION NEEDED] Review configuration above.")
        return 1

if __name__ == '__main__':
    sys.exit(main())
