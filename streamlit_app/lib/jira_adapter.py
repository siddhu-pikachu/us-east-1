from __future__ import annotations

from pathlib import Path
import orjson
from typing import Any, Dict, List, Optional, Tuple

from .config import settings

# Lazy import to avoid Jira client overhead in Demo Mode
_jira_client = None


def _demo_store_path() -> Path:
    return Path("data") / "demo_jira.json"


def _load_demo() -> Dict[str, Any]:
    path = _demo_store_path()
    if path.exists():
        return orjson.loads(path.read_bytes())
    return {"issues": []}


def _save_demo(payload: Dict[str, Any]) -> None:
    _demo_store_path().write_bytes(orjson.dumps(payload, option=orjson.OPT_INDENT_2))


def get_client():
    global _jira_client
    if settings.demo_mode:
        return None
    if _jira_client is None:
        from jira import JIRA  # import here

        _jira_client = JIRA(
            server=settings.jira_base_url,
            basic_auth=(settings.jira_email, settings.jira_api_token),
        )
    return _jira_client


def connection_ok() -> bool:
    if settings.demo_mode:
        return True
    try:
        client = get_client()
        me = client.myself()
        return bool(me and me.get("emailAddress"))
    except Exception:
        return False


def search_issues(jql: str, max_results: int = 20) -> List[Dict[str, Any]]:
    if settings.demo_mode:
        data = _load_demo()
        issues = [i for i in data["issues"] if i.get("matches", True)]
        return issues[:max_results]
    client = get_client()
    items = client.search_issues(jql, maxResults=max_results)
    results = []
    for it in items:
        results.append({"key": it.key, "fields": it.raw.get("fields", {})})
    return results


def create_issue(
    summary: str,
    description: str,
    issue_type: str = "Task",
    extra_fields: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    extra_fields = extra_fields or {}
    if settings.demo_mode:
        data = _load_demo()
        key = f"{settings.jira_project_key}-{len(data['issues'])+1}"
        payload = {
            "key": key,
            "fields": {
                "summary": summary,
                "description": description,
                "issuetype": {"name": issue_type},
                **extra_fields,
            },
        }
        data["issues"].append(payload)
        _save_demo(data)
        return payload
    client = get_client()
    
    # Handle priority field - Jira may require different formats
    # The error suggests it wants priority name as a string, not dict
    normalized_fields = {}
    if "priority" in extra_fields:
        priority_value = extra_fields["priority"]
        # Extract priority name if it's a dict
        if isinstance(priority_value, dict) and "name" in priority_value:
            priority_name = priority_value["name"]
            # Try multiple formats that Jira might accept
            try:
                # Method 1: Try to get priority ID from Jira
                priorities = client.priorities()
                priority_obj = None
                for p in priorities:
                    if p.name == priority_name:
                        priority_obj = p
                        break
                if priority_obj:
                    # Use priority ID (most reliable)
                    normalized_fields["priority"] = {"id": str(priority_obj.id)}
                else:
                    # Fallback: use name as string (as error message suggests)
                    normalized_fields["priority"] = priority_name
            except Exception:
                # If we can't fetch priorities, try using name as string
                normalized_fields["priority"] = priority_name
        else:
            normalized_fields["priority"] = priority_value
    
    # Copy other extra fields
    for key, value in extra_fields.items():
        if key != "priority":
            normalized_fields[key] = value
    
    fields = {
        "project": {"key": settings.jira_project_key},
        "summary": summary,
        "description": description,
        "issuetype": {"name": issue_type},
        **normalized_fields,
    }
    issue = client.create_issue(fields=fields)
    return {"key": issue.key, "fields": issue.raw.get("fields", {})}


def add_comment(issue_key: str, comment: str) -> None:
    if settings.demo_mode:
        data = _load_demo()
        for i in data["issues"]:
            if i["key"] == issue_key:
                i.setdefault("comments", []).append(comment)
        _save_demo(data)
        return
    client = get_client()
    client.add_comment(issue_key, comment)


def add_labels(issue_key: str, labels: List[str]) -> bool:
    """
    Add labels to a Jira issue.
    
    Args:
        issue_key: Jira issue key (e.g., "KAN-1")
        labels: List of label strings to add
        
    Returns:
        True if labels were added successfully, False otherwise
    """
    if not labels:
        return True
    
    if settings.demo_mode:
        data = _load_demo()
        for i in data["issues"]:
            if i["key"] == issue_key:
                existing_labels = i["fields"].get("labels", [])
                i["fields"]["labels"] = list(set(existing_labels + labels))
        _save_demo(data)
        return True
    
    try:
        client = get_client()
        issue = client.issue(issue_key)
        existing_labels = issue.fields.labels or []
        # Merge existing labels with new ones (avoid duplicates)
        all_labels = list(set(existing_labels + labels))
        issue.update(fields={"labels": all_labels})
        return True
    except Exception as e:
        print(f"Error adding labels to {issue_key}: {e}")
        return False


def assign_issue(issue_key: str, assignee_email: str = None, account_id: str = None) -> bool:
    """
    Assign a Jira issue to a user by email or accountId.
    
    Args:
        issue_key: Jira issue key (e.g., "KAN-1")
        assignee_email: Email address of the assignee
        account_id: Optional accountId (if known, avoids user search which may be blocked by GDPR)
        
    Returns:
        True if assignment succeeded, False otherwise
    """
    if settings.demo_mode:
        data = _load_demo()
        for i in data["issues"]:
            if i["key"] == issue_key:
                i["fields"]["assignee"] = {"emailAddress": assignee_email}
        _save_demo(data)
        return True
    
    try:
        client = get_client()
        import requests
        from requests.auth import HTTPBasicAuth
        
        # Method 1: Use REST API directly with accountId (most reliable, works with GDPR strict mode)
        # This is the recommended approach for Jira Cloud
        try:
            url = f"{settings.jira_base_url}/rest/api/2/issue/{issue_key}/assignee"
            auth = HTTPBasicAuth(settings.jira_email, settings.jira_api_token)
            headers = {"Content-Type": "application/json"}
            
            # Use accountId if provided (this is the most reliable method)
            account_id_to_use = account_id
            if not account_id_to_use and assignee_email:
                # Try to get accountId if assigning to current user
                try:
                    me = client.myself()
                    if me and me.get('emailAddress') == assignee_email:
                        account_id_to_use = me.get('accountId')
                except Exception:
                    pass
            
            # Try with accountId first (most reliable and works with GDPR strict mode)
            if account_id_to_use:
                payload = {"accountId": account_id_to_use}
                response = requests.put(url, json=payload, auth=auth, headers=headers)
                if response.status_code == 204:
                    # Verify assignment worked
                    issue = client.issue(issue_key)
                    if issue.fields.assignee:
                        return True
                elif response.status_code != 204:
                    try:
                        error_data = response.json()
                        print(f"Jira API error (accountId): {error_data}")
                    except:
                        print(f"Jira API returned status {response.status_code}: {response.text}")
            
            # Try with emailAddress as fallback (may work in some Jira configurations)
            if assignee_email:
                payload = {"emailAddress": assignee_email}
                response = requests.put(url, json=payload, auth=auth, headers=headers)
                if response.status_code == 204:
                    # Verify assignment worked
                    issue = client.issue(issue_key)
                    if issue.fields.assignee:
                        return True
                elif response.status_code != 204:
                    try:
                        error_data = response.json()
                        print(f"Jira API error (emailAddress): {error_data}")
                    except:
                        print(f"Jira API returned status {response.status_code}: {response.text}")
        except Exception as e1:
            print(f"REST API assignment failed: {e1}")
        
        # Method 2: Try using jira library's update method with accountId
        try:
            issue = client.issue(issue_key)
            if account_id:
                issue.update(fields={'assignee': {'accountId': account_id}})
                issue = client.issue(issue_key)
                if issue.fields.assignee:
                    return True
        except Exception as e2:
            pass
        
        # Method 3: Try using jira library's assign() method
        try:
            issue = client.issue(issue_key)
            if hasattr(issue, 'assign'):
                issue.assign(assignee_email)
                issue = client.issue(issue_key)
                if issue.fields.assignee:
                    return True
        except Exception as e3:
            pass
        
        # If all methods fail, print detailed error
        print(f"Warning: Could not assign {issue_key} to {assignee_email}")
        print(f"  Tried: REST API (accountId/emailAddress), jira library update, assign() method")
        return False
    except Exception as e:
        print(f"Error assigning issue {issue_key}: {e}")
        import traceback
        traceback.print_exc()
        return False


def load_tech_jira_mapping() -> Tuple[Dict[str, str], Dict[str, str]]:
    """
    Load the mapping from local tech names to Jira user emails and accountIds.
    
    Returns:
        Tuple of (tech_name -> jira_email dict, tech_name -> jira_account_id dict)
    """
    mapping_file = Path("data") / "tech_jira_mapping.csv"
    email_map = {}
    account_id_map = {}
    
    if not mapping_file.exists():
        return email_map, account_id_map
    
    try:
        import pandas as pd
        df = pd.read_csv(mapping_file)
        # Filter out rows where jira_email is empty or NaN
        df = df[df["jira_email"].notna() & (df["jira_email"] != "")]
        
        for _, row in df.iterrows():
            tech_name = row["tech_name"]
            email = row["jira_email"]
            account_id = row.get("jira_account_id", "")
            
            email_map[tech_name] = email
            # Only add accountId if it's not empty/NaN
            if pd.notna(account_id) and account_id and str(account_id).strip():
                account_id_map[tech_name] = str(account_id).strip()
    except Exception as e:
        print(f"Warning: Could not load tech-Jira mapping: {e}")
    
    return email_map, account_id_map

