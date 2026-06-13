import sys
sys.path.insert(0, 'lambda/api')
import api_router

status = api_router.get_import_status()
print("API Router Fix Verification:")
print(f"  Critical failures: {status['critical_failures']}")
print(f"  Total routes: {status['total_routes']}")
print(f"  Successful routes: {status['successful_routes']}")
print(f"  Failed routes: {status['failed_routes']}")

if not status['critical_failures']:
    print("\nResult: PASS - All critical routes imported successfully")
    sys.exit(0)
else:
    print("\nResult: FAIL - Critical routes failed")
    sys.exit(1)
