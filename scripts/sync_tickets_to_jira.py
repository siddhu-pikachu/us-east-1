#!/usr/bin/env python3
"""
Sync tickets from tickets.csv to Jira.

This script reads all tickets from data/tickets.csv and creates corresponding
Jira issues. It maintains a mapping between local ticket_id and Jira issue keys.
"""

import sys
from pathlib import Path
import pandas as pd

# Add parent directory to path for imports
_root = Path(__file__).parent.parent.resolve()
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from streamlit_app.lib.config import settings
from streamlit_app.lib.jira_adapter import get_client, create_issue, connection_ok, assign_issue
from streamlit_app.lib import data_access as da


def map_priority(csv_priority: str) -> str:
    """Map CSV priority to Jira priority names."""
    priority_map = {
        "Critical": "Highest",
        "High": "High",
        "Medium": "Medium",
        "Low": "Low",
    }
    return priority_map.get(csv_priority, "Medium")


def map_issue_type(csv_type: str) -> str:
    """Map CSV type to Jira issue type."""
    # Common Jira issue types: Task, Story, Bug, Epic
    # You may need to adjust based on your Jira project configuration
    return "Task"


def build_description(row: pd.Series) -> str:
    """Build a comprehensive description from ticket data."""
    parts = [
        row.get("description", ""),
        "",
        "**Details:**",
        f"- Asset ID: {row.get('asset_id', 'N/A')}",
        f"- Type: {row.get('type', 'N/A')}",
        f"- Impact: {row.get('impact', 'N/A')}",
        f"- Estimated Minutes: {row.get('estimated_minutes', 'N/A')}",
        f"- Requires Tools: {row.get('requires_tools', 'N/A')}",
    ]
    
    if pd.notna(row.get("deadline")):
        parts.append(f"- Deadline: {row.get('deadline')}")
    
    if pd.notna(row.get("change_window_start")) and pd.notna(row.get("change_window_end")):
        parts.append(f"- Change Window: {row.get('change_window_start')} to {row.get('change_window_end')}")
    
    if pd.notna(row.get("assigned_to")):
        parts.append(f"- Assigned To: {row.get('assigned_to')}")
    
    # Add location info if available
    if pd.notna(row.get("row")) and pd.notna(row.get("rack")):
        parts.append(f"- Location: Row {row.get('row')}, Rack {row.get('rack')}, U {row.get('u', 'N/A')}")
    
    return "\n".join(parts)


def transition_issue_status(client, issue_key: str, target_status: str) -> bool:
    """Transition a Jira issue to a target status."""
    try:
        # Get available transitions for this issue
        issue = client.issue(issue_key)
        transitions = client.transitions(issue)
        
        # Find the transition ID for the target status
        for transition in transitions:
            if transition['name'].lower() == target_status.lower():
                client.transition_issue(issue, transition['id'])
                return True
        
        # Try common status names
        status_map = {
            "in-progress": ["In Progress", "Start Progress", "Begin"],
            "done": ["Done", "Resolve", "Close"],
            "queued": ["To Do", "Open"],
        }
        
        for status_name in status_map.get(target_status.lower(), []):
            for transition in transitions:
                if status_name.lower() in transition['name'].lower():
                    client.transition_issue(issue, transition['id'])
                    return True
        
        print(f"  ⚠️  Warning: Could not transition {issue_key} to '{target_status}'")
        return False
    except Exception as e:
        print(f"  ⚠️  Warning: Error transitioning {issue_key}: {e}")
        return False


def main():
    """Main sync function."""
    print("=" * 60)
    print("Jira Ticket Sync Script")
    print("=" * 60)
    print()
    
    # Check configuration
    if settings.demo_mode:
        print("❌ ERROR: DEMO_MODE is enabled. Set DEMO_MODE=false in .env to sync with real Jira.")
        sys.exit(1)
    
    if not settings.jira_base_url or not settings.jira_email or not settings.jira_api_token:
        print("❌ ERROR: Jira credentials not configured in .env file.")
        print("   Required: JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN")
        sys.exit(1)
    
    print(f"Jira Base URL: {settings.jira_base_url}")
    print(f"Jira Project Key: {settings.jira_project_key}")
    print(f"Jira Email: {settings.jira_email}")
    print()
    
    # Test connection
    print("Testing Jira connection...")
    if not connection_ok():
        print("❌ ERROR: Failed to connect to Jira. Check your credentials.")
        sys.exit(1)
    print("✅ Jira connection successful!")
    print()
    
    # Load tickets
    print("Loading tickets from CSV...")
    tickets_df = da.load_tickets()
    print(f"✅ Loaded {len(tickets_df)} tickets")
    print()
    
    # Get Jira client
    client = get_client()
    
    # Create mapping file to store ticket_id -> jira_key
    mapping_file = Path("data") / "jira_ticket_mapping.csv"
    existing_mappings = {}
    if mapping_file.exists():
        mapping_df = pd.read_csv(mapping_file)
        existing_mappings = dict(zip(mapping_df["ticket_id"], mapping_df["jira_key"]))
        print(f"📋 Found {len(existing_mappings)} existing Jira mappings")
        print()
    
    # Process each ticket
    new_mappings = {}
    created_count = 0
    skipped_count = 0
    error_count = 0
    
    print("Creating/updating Jira issues...")
    print("-" * 60)
    
    for idx, row in tickets_df.iterrows():
        ticket_id = row["ticket_id"]
        summary = row["summary"]
        status = row.get("status", "queued").lower()
        
        # Check if already mapped
        if ticket_id in existing_mappings:
            jira_key = existing_mappings[ticket_id]
            print(f"⏭️  [{idx+1}/{len(tickets_df)}] {ticket_id} -> {jira_key} (already exists)")
            new_mappings[ticket_id] = jira_key
            skipped_count += 1
            continue
        
        # Create issue
        try:
            print(f"🔄 [{idx+1}/{len(tickets_df)}] Creating {ticket_id}: {summary[:50]}...")
            
            description = build_description(row)
            priority = map_priority(row.get("priority", "Medium"))
            issue_type = map_issue_type(row.get("type", "Task"))
            
            # Build extra fields for Jira
            extra_fields = {
                "priority": {"name": priority},
            }
            
            # Create the issue
            result = create_issue(
                summary=summary,
                description=description,
                issue_type=issue_type,
                extra_fields=extra_fields,
            )
            
            jira_key = result["key"]
            new_mappings[ticket_id] = jira_key
            created_count += 1
            
            print(f"  ✅ Created {jira_key}")
            
            # Assign to technician if available
            assigned_to = row.get("assigned_to")
            if pd.notna(assigned_to) and assigned_to:
                from streamlit_app.lib.jira_adapter import load_tech_jira_mapping
                tech_jira_email_map, tech_jira_account_id_map = load_tech_jira_mapping()
                if assigned_to in tech_jira_email_map:
                    jira_email = tech_jira_email_map[assigned_to]
                    account_id = tech_jira_account_id_map.get(assigned_to)
                    print(f"  🔄 Assigning to {assigned_to} ({jira_email})...")
                    if assign_issue(jira_key, jira_email, account_id):
                        print(f"  ✅ Assigned to {assigned_to}")
                    else:
                        print(f"  ⚠️  Could not assign to {assigned_to}")
            
            # Transition status if needed
            if status == "in-progress":
                print(f"  🔄 Transitioning to 'In Progress'...")
                if transition_issue_status(client, jira_key, "in-progress"):
                    print(f"  ✅ Status updated to 'In Progress'")
                else:
                    print(f"  ⚠️  Could not transition status (may need manual update)")
            elif status == "done":
                print(f"  🔄 Transitioning to 'Done'...")
                if transition_issue_status(client, jira_key, "done"):
                    print(f"  ✅ Status updated to 'Done'")
                else:
                    print(f"  ⚠️  Could not transition status (may need manual update)")
            
        except Exception as e:
            print(f"  ❌ ERROR: {e}")
            error_count += 1
            import traceback
            traceback.print_exc()
        
        print()
    
    # Save mappings
    print("-" * 60)
    print("Saving ticket mappings...")
    all_mappings = {**existing_mappings, **new_mappings}
    mapping_df = pd.DataFrame([
        {"ticket_id": tid, "jira_key": key}
        for tid, key in all_mappings.items()
    ])
    mapping_df.to_csv(mapping_file, index=False)
    print(f"✅ Saved mappings to {mapping_file}")
    print()
    
    # Summary
    print("=" * 60)
    print("Sync Summary")
    print("=" * 60)
    print(f"Total tickets: {len(tickets_df)}")
    print(f"✅ Created: {created_count}")
    print(f"⏭️  Skipped (already exist): {skipped_count}")
    print(f"❌ Errors: {error_count}")
    print()
    print(f"📋 Mapping file: {mapping_file}")
    print("=" * 60)


if __name__ == "__main__":
    main()

