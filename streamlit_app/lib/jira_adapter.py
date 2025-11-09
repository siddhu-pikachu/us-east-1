from __future__ import annotations

from pathlib import Path
import orjson
from typing import Any, Dict, List, Optional

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
    fields = {
        "project": {"key": settings.jira_project_key},
        "summary": summary,
        "description": description,
        "issuetype": {"name": issue_type},
        **extra_fields,
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

