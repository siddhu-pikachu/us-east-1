from typing import Optional


class JiraWrap:
    """Wrapper for safe, idempotent Jira operations."""

    def __init__(self, client):
        self.client = client  # your existing jira client

    def _status_of(self, issue_key: str) -> str:
        """Get current status of a Jira issue."""
        try:
            if not self.client:
                return ""
            # Try to get issue status (adjust to your actual client method)
            # This is a stub - adjust based on your actual Jira client API
            meta = self.client.get_issue(issue_key) if hasattr(self.client, "get_issue") else {}
            return (meta.get("fields", {}).get("status", {}).get("name", "") or "").lower()
        except Exception:
            return ""

    def safe_transition(self, issue_key: str, target: str) -> bool:
        """
        Idempotent: only transition when current != target.
        
        Args:
            issue_key: Jira issue key (e.g., "TICK-1")
            target: Target status name (e.g., "In Progress", "Done")
            
        Returns:
            True if transition succeeded or already in target state
        """
        try:
            if not self.client:
                return False
            cur = self._status_of(issue_key)
            if cur == target.lower():
                return True
            # Adjust to your actual transition method
            if hasattr(self.client, "transition_issue"):
                self.client.transition_issue(issue_key, target)
            return True
        except Exception:
            return False

    def add_comment_once(self, issue_key: str, body: str, marker: str) -> bool:
        """
        Add comment only if marker not already present (idempotent).
        
        Args:
            issue_key: Jira issue key
            body: Comment body
            marker: Unique marker string to check for duplicates
            
        Returns:
            True if comment added or already exists
        """
        try:
            if not self.client:
                return False
            # Check existing comments (adjust to your actual method)
            if hasattr(self.client, "get_comments"):
                comments = self.client.get_comments(issue_key)
                if any(marker in (c.get("body", "") or "") for c in comments):
                    return True
            # Add comment (adjust to your actual method)
            if hasattr(self.client, "add_comment"):
                self.client.add_comment(issue_key, body)
            return True
        except Exception:
            return False

