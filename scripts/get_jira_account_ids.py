#!/usr/bin/env python3
"""
Helper script to get Jira accountIds for technicians.
Since GDPR strict mode blocks user search, you need to manually get accountIds.

This script will:
1. Show your own accountId (so you can use it as a reference)
2. Help you add accountIds to tech_jira_mapping.csv

To get accountIds for other users:
- Ask them to run this script, OR
- Go to Jira → User Management → find their accountId, OR
- Check the Jira API response when they're assigned to an issue
"""

import sys
from pathlib import Path
import pandas as pd

_root = Path(__file__).parent.parent.resolve()
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from streamlit_app.lib.config import settings
from streamlit_app.lib.jira_adapter import get_client, connection_ok

if __name__ == "__main__":
    if settings.demo_mode:
        print("❌ ERROR: DEMO_MODE is enabled. Set DEMO_MODE=false in .env")
        sys.exit(1)
    
    if not connection_ok():
        print("❌ ERROR: Failed to connect to Jira")
        sys.exit(1)
    
    client = get_client()
    
    # Get current user's accountId
    print("=" * 60)
    print("Your Jira Account Information")
    print("=" * 60)
    try:
        me = client.myself()
        print(f"Email: {me.get('emailAddress')}")
        print(f"Display Name: {me.get('displayName')}")
        print(f"Account ID: {me.get('accountId')}")
        print()
        print("💡 You can use this Account ID in tech_jira_mapping.csv")
        print("   If all techs should map to your account, copy this Account ID")
        print("   to the jira_account_id column for all technicians.")
        print()
    except Exception as e:
        print(f"Error getting user info: {e}")
        sys.exit(1)
    
    # Show current mapping file
    mapping_file = Path("data") / "tech_jira_mapping.csv"
    if mapping_file.exists():
        print("=" * 60)
        print("Current Tech-Jira Mapping")
        print("=" * 60)
        df = pd.read_csv(mapping_file)
        print(df.to_string(index=False))
        print()
        print("💡 To assign different techs to different Jira users:")
        print("   1. Get each user's accountId (ask them or check Jira)")
        print("   2. Edit data/tech_jira_mapping.csv")
        print("   3. Fill in the jira_account_id column")
        print()
        print("   If jira_account_id is empty, the system will try to use")
        print("   the email address (which may not work in GDPR strict mode).")

