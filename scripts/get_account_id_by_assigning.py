#!/usr/bin/env python3
"""
Try to get accountId by attempting to assign a test ticket to an email.
If assignment succeeds, we can read back the accountId from the issue.
"""

import sys
from pathlib import Path

_root = Path(__file__).parent.parent.resolve()
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from streamlit_app.lib.config import settings
from streamlit_app.lib.jira_adapter import get_client, connection_ok, assign_issue

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python scripts/get_account_id_by_assigning.py <jira_key> <email>")
        print("Example: python scripts/get_account_id_by_assigning.py KAN-1 rapetisiddhu@gmail.com")
        sys.exit(1)
    
    issue_key = sys.argv[1]
    email = sys.argv[2]
    
    if settings.demo_mode:
        print("❌ ERROR: DEMO_MODE is enabled. Set DEMO_MODE=false in .env")
        sys.exit(1)
    
    if not connection_ok():
        print("❌ ERROR: Failed to connect to Jira")
        sys.exit(1)
    
    print(f"Attempting to assign {issue_key} to {email}...")
    print("(This will help us get the accountId)")
    print()
    
    # Try assigning with just email
    result = assign_issue(issue_key, email, None)
    
    if result:
        print("✅ Assignment succeeded!")
        print()
        print("Reading issue to get accountId...")
        try:
            client = get_client()
            issue = client.issue(issue_key)
            assignee = issue.fields.assignee
            if assignee:
                account_id = getattr(assignee, 'accountId', None)
                if account_id:
                    print(f"✅ Found accountId: {account_id}")
                    print(f"   Display Name: {assignee.displayName}")
                    print(f"   Email: {assignee.emailAddress}")
                    print()
                    print(f"Add this to tech_jira_mapping.csv:")
                    print(f"  jira_account_id: {account_id}")
                else:
                    print("⚠️  Issue assigned but accountId not found in response")
                    print(f"   Assignee: {assignee.displayName} ({assignee.emailAddress})")
            else:
                print("❌ Issue is still unassigned")
        except Exception as e:
            print(f"❌ Error reading issue: {e}")
    else:
        print("❌ Assignment failed")
        print()
        print("You'll need to get the accountId manually:")
        print("1. Ask the user to run: python scripts/get_jira_account_ids.py")
        print("2. Or check Jira → Settings → User Management")

