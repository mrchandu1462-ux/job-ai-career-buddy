"""Company watchlist tracking service for semiconductor and VLSI employers."""

import sqlite3
from typing import Any

from app.db.models import CompanyWatchlistRecord
from app.db.repository import JobRepository


class CompanyWatchlistService:
    """Manages target semiconductor companies and tracks newly released opportunities."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.repo = JobRepository(conn)
        self.repo.seed_default_watchlist()

    def list_watchlist(self, is_active: bool = True) -> list[CompanyWatchlistRecord]:
        """List active semiconductor companies on the watchlist."""
        return self.repo.list_watchlist(is_active=is_active)

    def add_company(
        self,
        company_name: str,
        priority_level: str = "HIGH",
        notes: str | None = None,
    ) -> int:
        """Add or update a target company on the watchlist."""
        return self.repo.add_watchlist_company(
            company_name=company_name,
            priority_level=priority_level,
            notes=notes,
        )

    def remove_company(self, company_name: str) -> bool:
        """Remove a company from the watchlist."""
        return self.repo.remove_watchlist_company(company_name)

    def enable_company(self, company_name: str) -> bool:
        """Re-activate an existing watchlist company."""
        return self.repo.set_watchlist_company_active(company_name, is_active=True)

    def disable_company(self, company_name: str) -> bool:
        """De-activate a watchlist company without deleting historical tracking."""
        return self.repo.set_watchlist_company_active(company_name, is_active=False)

    def set_company_priority(self, company_name: str, priority_level: str) -> bool:
        """Set or update priority tier for a watchlist company."""
        return self.repo.set_watchlist_company_priority(company_name, priority_level)

    def get_company_priority(self, company_name: str) -> str | None:
        """Get priority level for a company if watchlisted."""
        record = self.repo.get_watchlist_company(company_name)
        return record.priority_level if record and record.is_active else None

    def is_watched(self, company_name: str) -> bool:
        """Check if a company is currently watched."""
        return self.repo.is_company_in_watchlist(company_name)

    def get_watchlist_summary(self, hours: float = 24.0) -> list[dict[str, Any]]:
        """
        Aggregate count of fresh jobs in the last N hours for each watchlist company.
        """
        watchlist = self.list_watchlist(is_active=True)
        fresh_jobs = self.repo.list_fresh_jobs(max_age_hours=hours, limit=500)

        summary = []
        for entry in watchlist:
            c_name = entry.company_name.strip().lower()
            matching = [
                j for j in fresh_jobs
                if c_name in j.company.lower() or j.company.lower() in c_name
            ]
            summary.append({
                "company_name": entry.company_name,
                "priority_level": entry.priority_level,
                "fresh_jobs_count": len(matching),
                "jobs": matching,
            })
        return summary
