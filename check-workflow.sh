#!/bin/bash
# Check GitHub Actions workflow status
# Usage: bash check-workflow.sh

RUN_ID="25137535667"
URL="https://api.github.com/repos/argie33/algo/actions/runs/$RUN_ID"

echo "Checking workflow status..."
echo "Run: $URL"
echo ""

python3 << 'EOF'
import urllib.request, json, sys

try:
    url = "https://api.github.com/repos/argie33/algo/actions/runs/25137535667"
    req = urllib.request.Request(url)
    req.add_header('Accept', 'application/vnd.github+json')

    with urllib.request.urlopen(req) as r:
        run = json.loads(r.read().decode())

    print(f"Status: {run['status'].upper()}")
    print(f"Conclusion: {run.get('conclusion', 'PENDING').upper()}")

    jobs_url = f"{url}/jobs"
    jobs_req = urllib.request.Request(jobs_url)
    jobs_req.add_header('Accept', 'application/vnd.github+json')

    with urllib.request.urlopen(jobs_req) as r:
        jobs = json.loads(r.read().decode())

    print("\nJob Status:")
    for job in jobs['jobs']:
        if job['status'] == 'completed' and job['conclusion'] == 'success':
            print(f"  [OK] {job['name']}")
        elif job['status'] == 'completed':
            print(f"  [FAIL] {job['name']}")
        elif job['status'] == 'in_progress':
            print(f"  [>>] {job['name']}")
        else:
            print(f"  [...] {job['name']}")

    if run['status'] == 'completed':
        print(f"\n[COMPLETE] Workflow finished: {run['conclusion']}")
        if run['conclusion'] == 'success':
            print("Ready to capture execution proof!")
        sys.exit(0)
    else:
        print(f"\n[IN PROGRESS] Still running...")
        sys.exit(1)

except urllib.error.HTTPError as e:
    if e.code == 403:
        print("Rate limited - retrying in 60 seconds...")
        sys.exit(1)
    print(f"Error: {e}")
    sys.exit(1)
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
EOF
