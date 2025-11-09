#!/usr/bin/env python3
"""
Test script to verify Jira assignment is working correctly.
"""

import sys
from pathlib import Path

_root = Path(__file__).parent.parent.resolve()
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from streamlit_app.lib.config import settings
from streamlit_app.lib.jira_adapter import get_client, assign_issue, connection_ok

if __name__ == "__main__":
    if settings.demo_mode:
        print("❌ ERROR: DEMO_MODE is enabled. Set DEMO_MODE=false in .env")
        sys.exit(1)
    
    print("Testing Jira connection...")
    if not connection_ok():
        print("❌ ERROR: Failed to connect to Jira")
        sys.exit(1)
    print("✅ Connected to Jira")
    print()
    
    # Test with a specific issue
    test_issue = input("Enter Jira issue key to test (e.g., KAN-1): ").strip()
    test_email = input(f"Enter email to assign to (default: {settings.jira_email}): ").strip() or settings.jira_email
    
    print(f"\nAssigning {test_issue} to {test_email}...")
    
    # Get client to inspect user search
    client = get_client()
    print("\nSearching for user...")
    try:
        users = client.search_users(test_email, maxResults=1)
        if users:
            user = users[0]
            print(f"Found user: {user}")
            print(f"  Account ID: {getattr(user, 'accountId', 'N/A')}")
            print(f"  Email: {getattr(user, 'emailAddress', 'N/A')}")
            print(f"  Display Name: {getattr(user, 'displayName', 'N/A')}")
        else:
            print("⚠️  No user found with that email")
    except Exception as e:
        print(f"⚠️  Error searching for user: {e}")
    
    print("\nAttempting assignment...")
    result = assign_issue(test_issue, test_email)
    
    if result:
        print(f"✅ Assignment returned True")
        print(f"\nPlease check Jira issue {test_issue} to verify the assignee field is updated.")
    else:
        print(f"❌ Assignment returned False")
    
    # Verify by reading the issue
    print("\nReading issue to verify assignment...")
    try:
        issue = client.issue(test_issue)
        assignee = issue.fields.assignee
        if assignee:
            print(f"✅ Current assignee: {assignee.displayName} ({assignee.emailAddress})")
        else:
            print("❌ Issue is still unassigned")
    except Exception as e:
        print(f"⚠️  Error reading issue: {e}")

