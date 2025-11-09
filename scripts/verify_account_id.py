#!/usr/bin/env python3
"""
Verify if an accountId is valid by trying to get user info.
"""

import sys
from pathlib import Path

_root = Path(__file__).parent.parent.resolve()
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from streamlit_app.lib.config import settings
from streamlit_app.lib.jira_adapter import get_client, connection_ok
import requests
from requests.auth import HTTPBasicAuth

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/verify_account_id.py <accountId>")
        print("Example: python scripts/verify_account_id.py 712020:f6963fbf-66e4-4c46-96fb-1cc499140dcb")
        sys.exit(1)
    
    account_id = sys.argv[1]
    
    if settings.demo_mode:
        print("❌ ERROR: DEMO_MODE is enabled. Set DEMO_MODE=false in .env")
        sys.exit(1)
    
    if not connection_ok():
        print("❌ ERROR: Failed to connect to Jira")
        sys.exit(1)
    
    print(f"Verifying accountId: {account_id}")
    print()
    
    # Try to get user info via REST API
    try:
        url = f"{settings.jira_base_url}/rest/api/3/user"
        auth = HTTPBasicAuth(settings.jira_email, settings.jira_api_token)
        params = {"accountId": account_id}
        
        response = requests.get(url, auth=auth, params=params)
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            user_data = response.json()
            print("✅ AccountId is valid!")
            print(f"   Display Name: {user_data.get('displayName')}")
            print(f"   Email: {user_data.get('emailAddress')}")
            print(f"   Account ID: {user_data.get('accountId')}")
        else:
            print(f"❌ Failed: {response.text}")
            print()
            print("Possible issues:")
            print("1. AccountId format is incorrect")
            print("2. User doesn't exist in this Jira instance")
            print("3. API token doesn't have permission to view this user")
    except Exception as e:
        print(f"❌ Error: {e}")

