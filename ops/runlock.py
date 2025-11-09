import time
from dataclasses import dataclass, field
from typing import Optional, Dict

GRACE_SECONDS = 45
IDLE_TIMEOUT_SECONDS = 20 * 60  # 20 min


@dataclass
class ActiveRun:
    tech: str
    ticket_id: str
    run_id: str
    started_ts: float
    paused_seconds: float = 0.0
    last_activity_ts: float = 0.0
    grace_until: float = 0.0
    paused: bool = False
    _pause_start: float = field(default=0.0, init=False)


class RunState:
    """Manages active runs per technician with grace period and idle timeout."""

    def __init__(self):
        self.by_tech: Dict[str, ActiveRun] = {}

    def can_start(self, tech: str) -> bool:
        """Check if tech can start a new run (no active run)."""
        ar = self.by_tech.get(tech)
        return ar is None

    def start(
        self, tech: str, ticket_id: str, run_id: str, now: Optional[float] = None
    ) -> ActiveRun:
        """Start a new run for a technician."""
        now = now or time.time()
        ar = ActiveRun(
            tech=tech,
            ticket_id=ticket_id,
            run_id=run_id,
            started_ts=now,
            last_activity_ts=now,
            grace_until=now + GRACE_SECONDS,
        )
        self.by_tech[tech] = ar
        return ar

    def abort_if_in_grace(self, tech: str) -> bool:
        """Abort run if still in grace period. Returns True if aborted."""
        ar = self.by_tech.get(tech)
        if not ar:
            return False
        if time.time() <= ar.grace_until:
            del self.by_tech[tech]
            return True
        return False

    def touch(self, tech: str):
        """Update last activity timestamp for a tech's run."""
        ar = self.by_tech.get(tech)
        if ar:
            ar.last_activity_ts = time.time()

    def idle_check(self, tech: str) -> bool:
        """Check if run has been idle for too long."""
        ar = self.by_tech.get(tech)
        if not ar:
            return False
        return (time.time() - ar.last_activity_ts) > IDLE_TIMEOUT_SECONDS
    
    def cleanup_stale_runs(self, max_age_seconds: float = 3600) -> int:
        """
        Remove runs that are older than max_age_seconds (default 1 hour).
        Returns number of runs cleaned up.
        """
        now = time.time()
        to_remove = []
        for tech, ar in self.by_tech.items():
            if (now - ar.started_ts) > max_age_seconds:
                to_remove.append(tech)
        for tech in to_remove:
            del self.by_tech[tech]
        return len(to_remove)

    def pause(self, tech: str):
        """Pause a run (starts tracking pause time)."""
        ar = self.by_tech.get(tech)
        if ar and not ar.paused:
            ar.paused = True
            ar._pause_start = time.time()

    def resume(self, tech: str):
        """Resume a paused run (accumulates pause time)."""
        ar = self.by_tech.get(tech)
        if ar and ar.paused:
            ar.paused = False
            ar.paused_seconds += time.time() - ar._pause_start
            ar._pause_start = 0.0

    def finish(self, tech: str) -> Optional[ActiveRun]:
        """Finish a run and return the ActiveRun record."""
        return self.by_tech.pop(tech, None)

    def get_active(self, tech: str) -> Optional[ActiveRun]:
        """Get active run for a tech, if any."""
        return self.by_tech.get(tech)


def get_runstate(st) -> RunState:
    """Get or create RunState from session state."""
    if "runstate" not in st.session_state:
        st.session_state["runstate"] = RunState()
    return st.session_state["runstate"]

