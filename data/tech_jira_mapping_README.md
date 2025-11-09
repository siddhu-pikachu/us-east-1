# Technician to Jira User Mapping

This file maps local technician names to Jira user emails and accountIds.

## Configuration

Edit `data/tech_jira_mapping.csv` to map your local technician names to Jira users.

**Format:**
```csv
tech_name,jira_email,jira_account_id
Ava,user1@example.com,712020:1f53d9b6-0af2-4586-8dd8-dde7a7988eba
Ben,user2@example.com,712020:2a4e8c7d-1b3e-4597-9ee9-ef8f9a0b1c2d
...
```

## Important: AccountId is Required for GDPR Strict Mode

Jira Cloud with GDPR strict mode **blocks user search by email**. To assign tickets correctly, you **must** provide the `jira_account_id` for each technician.

## How to Get AccountIds

### Option 1: Run the helper script
```bash
python scripts/get_jira_account_ids.py
```
This shows your own accountId. If all techs map to you, copy it to all rows.

### Option 2: Get from Jira UI
1. Go to Jira → Settings → User Management
2. Find the user
3. Their accountId is shown in the URL or user details

### Option 3: Ask each user
Each user can run `scripts/get_jira_account_ids.py` to get their own accountId.

## Current Setup

Currently, all technicians are mapped to the same Jira account (yours). This means:
- ✅ All tickets are assigned to you in Jira
- ✅ The local system correctly tracks which technician is working on each ticket
- ✅ A comment is automatically added to each Jira ticket showing the actual technician name

**This is fine for demo/testing purposes** - you can see who's working on what in the local system and in Jira comments.

## To Assign Different Techs to Different Jira Users

**Yes, you need unique Jira accounts for each technician** if you want them to show as assignees in Jira.

**Steps:**
1. Create Jira accounts for each technician (each needs a unique email)
2. Get each user's accountId (they can run `scripts/get_jira_account_ids.py`)
3. Edit `data/tech_jira_mapping.csv`
4. Update the `jira_email` and `jira_account_id` columns for each technician

**Example:**
```csv
tech_name,jira_email,jira_account_id
Ava,ava@example.com,712020:ava-account-id-here
Ben,ben@example.com,712020:ben-account-id-here
Chen,chen@example.com,712020:chen-account-id-here
...
```

**Note:** If you can't create multiple accounts, the current setup works fine - the technician name will appear in Jira comments even though the assignee field shows your name.

## Automatic Integration

The mapping is used **automatically** when:
- ✅ **Auto-assigning tickets** (Manager page) - Assigns in both local system AND Jira
- ✅ **Syncing tickets** (sync script) - Assigns existing tickets in Jira

**No manual scripts needed** - everything happens automatically when you click "Auto-Assign Tickets"!

