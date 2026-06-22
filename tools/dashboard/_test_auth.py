"""Quick test script for dashboard auth + data loading."""
import json
import os

import boto3


os.environ["AWS_PROFILE"] = "algo-developer"
client = boto3.client("secretsmanager", region_name="us-east-1")
r = client.get_secret_value(SecretId="algo/dashboard-config")
s = json.loads(r["SecretString"])
os.environ["DASHBOARD_API_URL"] = s.get("api_url", "")
os.environ["COGNITO_USER_POOL_ID"] = s.get("cognito_user_pool_id", "")
os.environ["COGNITO_CLIENT_ID"] = s.get("cognito_user_pool_client_id", "")

from tools.dashboard.api_data_layer import set_api_url, set_cognito_auth


set_api_url(s.get("api_url", ""))

from tools.dashboard.cognito_auth import get_cognito_auth as get_auth


auth = get_auth(require_auth=True)
print(f"Auth: {type(auth).__name__} authenticated={auth.is_authenticated() if auth else False}")
if auth and auth.is_authenticated():
    set_cognito_auth(auth)
    from tools.dashboard.dashboard import render_dashboard
    from tools.dashboard.fetchers import load_all
    data = load_all()
    errors = {k: v.get("_error", "")[:50] for k, v in data.items() if isinstance(v, dict) and "_error" in v}
    ok_keys = [k for k in data if not (isinstance(data[k], dict) and "_error" in data[k])]
    print(f"OK ({len(ok_keys)}): {ok_keys}")
    print(f"FAILED ({len(errors)}): {list(errors.items())[:8]}")
    pos = data.get("pos")
    if isinstance(pos, dict) and "items" in pos:
        missing = [p.get("symbol") for p in pos["items"] if not p.get("sector")]
        print(f"Positions: {len(pos['items'])}, missing sector: {missing}")
    layout = render_dashboard(data)
    print("Render: OK")
