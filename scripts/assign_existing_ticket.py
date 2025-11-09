#!/usr/bin/env python3
"""
Quick script to assign an existing Jira ticket for testing.
Usage: python scripts/assign_existing_ticket.py KAN-1
"""

import sys
from pathlib import Path

_root = Path(__file__).parent.parent.resolve()
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from streamlit_app.lib.config import settings
from streamlit_app.lib.jira_adapter import get_client, assign_issue, connection_ok

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/assign_existing_ticket.py <JIRA_KEY> [email]")
        print(f"Example: python scripts/assign_existing_ticket.py KAN-1 {settings.jira_email}")
        sys.exit(1)
    
    issue_key = sys.argv[1]
    assignee_email = sys.argv[2] if len(sys.argv) > 2 else settings.jira_email
    
    if settings.demo_mode:
        print("❌ ERROR: DEMO_MODE is enabled. Set DEMO_MODE=false in .env")
        sys.exit(1)
    
    print(f"Assigning {issue_key} to {assignee_email}...")
    
    # Test connection
    if not connection_ok():
        print("❌ ERROR: Failed to connect to Jira")
        sys.exit(1)
    
    # Get client for debugging
    client = get_client()
    
    # Check current assignee
    try:
        issue = client.issue(issue_key)
        current_assignee = issue.fields.assignee
        if current_assignee:
            print(f"Current assignee: {current_assignee.displayName} ({current_assignee.emailAddress})")
        else:
            print("Current assignee: Unassigned")
    except Exception as e:
        print(f"⚠️  Error reading issue: {e}")
    
    # Search for user
    print(f"\nSearching for user: {assignee_email}")
    try:
        users = client.search_users(assignee_email, maxResults=1)
        if users:
            user = users[0]
            print(f"Found user:")
            print(f"  Type: {type(user)}")
            print(f"  Attributes: {dir(user)}")
            print(f"  Account ID: {getattr(user, 'accountId', 'N/A')}")
            print(f"  Email: {getattr(user, 'emailAddress', 'N/A')}")
            print(f"  Display Name: {getattr(user, 'displayName', 'N/A')}")
            print(f"  Key: {getattr(user, 'key', 'N/A')}")
        else:
            print("⚠️  No user found")
    except Exception as e:
        print(f"⚠️  Error searching for user: {e}")
        import traceback
        traceback.print_exc()
    
    # Try assignment
    print(f"\nAttempting assignment...")
    result = assign_issue(issue_key, assignee_email)
    
    if result:
        print("✅ Assignment function returned True")
    else:
        print("❌ Assignment function returned False")
    
    # Verify
    print("\nVerifying assignment...")
    try:
        issue = client.issue(issue_key)
        new_assignee = issue.fields.assignee
        if new_assignee:
            print(f"✅ New assignee: {new_assignee.displayName} ({new_assignee.emailAddress})")
        else:
            print("❌ Issue is still unassigned")
    except Exception as e:
        print(f"⚠️  Error verifying: {e}")

