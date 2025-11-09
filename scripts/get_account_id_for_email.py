#!/usr/bin/env python3
"""
Get accountId for a specific email address.
Since GDPR strict mode blocks user search, this tries alternative methods.
"""

import sys
from pathlib import Path

_root = Path(__file__).parent.parent.resolve()
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from streamlit_app.lib.config import settings
from streamlit_app.lib.jira_adapter import get_client, connection_ok

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/get_account_id_for_email.py <email>")
        print("Example: python scripts/get_account_id_for_email.py rapetisiddhu@gmail.com")
        sys.exit(1)
    
    email = sys.argv[1]
    
    if settings.demo_mode:
        print("❌ ERROR: DEMO_MODE is enabled. Set DEMO_MODE=false in .env")
        sys.exit(1)
    
    if not connection_ok():
        print("❌ ERROR: Failed to connect to Jira")
        sys.exit(1)
    
    client = get_client()
    
    print(f"Attempting to get accountId for: {email}")
    print()
    
    # Method 1: Try search_users (may fail in GDPR strict mode)
    print("Method 1: Searching for user by email...")
    try:
        users = client.search_users(email, maxResults=1)
        if users:
            user = users[0]
            account_id = getattr(user, 'accountId', None)
            if account_id:
                print(f"✅ Found accountId: {account_id}")
                print(f"   Display Name: {getattr(user, 'displayName', 'N/A')}")
                print()
                print(f"Add this to tech_jira_mapping.csv:")
                print(f"  jira_account_id: {account_id}")
                sys.exit(0)
            else:
                print("⚠️  User found but no accountId")
        else:
            print("⚠️  No user found")
    except Exception as e:
        print(f"❌ Failed (expected in GDPR strict mode): {e}")
    
    print()
    print("=" * 60)
    print("Alternative Methods to Get AccountId:")
    print("=" * 60)
    print("1. Ask the user to run: python scripts/get_jira_account_ids.py")
    print("   (They need to be logged into Jira with that account)")
    print()
    print("2. Go to Jira → Settings → User Management")
    print("   Find the user and check their accountId in the URL or details")
    print()
    print("3. Assign a test ticket to that email, then check the issue")
    print("   The assignee field will contain the accountId")
    print()
    print("4. If you have admin access, check the Jira API directly:")
    print("   GET /rest/api/2/user?username={email}")

