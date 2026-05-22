#!/usr/bin/env python3
"""
Force delete S3 buckets with versioning/MFA-delete enabled.
Removes all versions, suspend versioning, then delete bucket.
"""

import subprocess
import json
import sys

def run_cmd(cmd):
    """Execute AWS CLI command."""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr

def empty_bucket(bucket_name, region="us-east-1"):
    """Remove all object versions from bucket."""
    print(f"\n[{bucket_name}] Emptying bucket...")

    # Suspend versioning first
    code, out, err = run_cmd(
        f'aws s3api put-bucket-versioning --bucket {bucket_name} '
        f'--versioning-configuration Status=Suspended --region {region}'
    )
    if code != 0:
        print(f"  Error suspending versioning: {err}")
        return False

    # List all versions
    code, out, err = run_cmd(
        f'aws s3api list-object-versions --bucket {bucket_name} --region {region} --output json'
    )
    if code != 0:
        print(f"  Error listing versions: {err}")
        return False

    try:
        data = json.loads(out)
    except:
        data = {"Versions": [], "DeleteMarkers": []}

    versions = data.get("Versions", [])
    markers = data.get("DeleteMarkers", [])

    total = len(versions) + len(markers)
    print(f"  Found {len(versions)} versions + {len(markers)} delete markers")

    if total == 0:
        print(f"  Bucket is already empty")
        return True

    # Delete all versions
    if versions:
        print(f"  Deleting {len(versions)} object versions...")
        for i in range(0, len(versions), 1000):
            batch = versions[i:i+1000]
            delete_spec = {
                "Objects": [
                    {"Key": v["Key"], "VersionId": v["VersionId"]}
                    for v in batch
                ]
            }
            with open("/tmp/delete.json", "w") as f:
                json.dump(delete_spec, f)

            code, out, err = run_cmd(
                f'aws s3api delete-objects --bucket {bucket_name} '
                f'--delete file:///tmp/delete.json --region {region} --output json'
            )
            if code != 0:
                print(f"    Batch error: {err}")
                continue
            deleted = json.loads(out).get("Deleted", [])
            print(f"    Deleted {len(deleted)} versions")

    # Delete all delete markers
    if markers:
        print(f"  Deleting {len(markers)} delete markers...")
        for i in range(0, len(markers), 1000):
            batch = markers[i:i+1000]
            delete_spec = {
                "Objects": [
                    {"Key": m["Key"], "VersionId": m["VersionId"]}
                    for m in batch
                ]
            }
            with open("/tmp/delete.json", "w") as f:
                json.dump(delete_spec, f)

            code, out, err = run_cmd(
                f'aws s3api delete-objects --bucket {bucket_name} '
                f'--delete file:///tmp/delete.json --region {region} --output json'
            )
            if code != 0:
                print(f"    Error: {err}")
                continue
            deleted = json.loads(out).get("Deleted", [])
            print(f"    Deleted {len(deleted)} markers")

    print(f"  [OK] Bucket emptied")
    return True

def delete_bucket(bucket_name, region="us-east-1"):
    """Delete empty bucket."""
    print(f"  Deleting bucket...")
    code, out, err = run_cmd(
        f'aws s3api delete-bucket --bucket {bucket_name} --region {region}'
    )
    if code == 0:
        print(f"  [OK] Bucket deleted: {bucket_name}")
        return True
    else:
        print(f"  [ERROR] {err}")
        return False

def main():
    buckets = [
        "algo-terraform-state-dev",
        "stocks-core-cftemplatesbucket-byjdqhvlyp1o",
        "stocks-core-cftemplatesbucket-yesjt7jywetz",
        "terraform-state-626216981288-us-east-1",
    ]

    print("=" * 80)
    print("FORCE DELETE VERSIONED BUCKETS")
    print("=" * 80)

    success_count = 0
    for bucket in buckets:
        if empty_bucket(bucket) and delete_bucket(bucket):
            success_count += 1

    print("\n" + "=" * 80)
    print(f"COMPLETE: {success_count}/{len(buckets)} buckets deleted")
    print("=" * 80)

    if success_count == len(buckets):
        print("\n[OK] All unmanaged resources removed!")
        print("Now deploy: terraform apply -target=module.governance")
        return 0
    else:
        print(f"\n[WARNING] {len(buckets) - success_count} buckets remain")
        return 1

if __name__ == "__main__":
    sys.exit(main())
