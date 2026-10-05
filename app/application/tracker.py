"""Lightweight Human-in-the-Loop Application Tracker and Daily Opportunity Reporter."""

import argparse
from datetime import UTC, datetime

from app.application.intelligence import (
    ApplicationPriorityEngine,
    ApplicationPriorityTier,
    EligibilityClassifier,
    WorkAuthClassifier,
)
from app.db.connection import get_connection
from app.db.models import ApplicationRecord, ApplicationStatus, NormalizedJob
from app.db.repository import JobRepository
from app.matching.scorer import JobScoringEngine
from app.profile.loader import load_fact_bank, load_profile
from app.profile.models import CandidateProfile, FactBank


class ApplicationTracker:
    """Manages application lifecycle progression and generates actionable status reports."""

    def __init__(
        self,
        repo: JobRepository | None = None,
        profile: CandidateProfile | None = None,
        fact_bank: FactBank | None = None,
    ) -> None:
        if repo is None:
            conn = get_connection()
            self.repo = JobRepository(conn)
        else:
            self.repo = repo
        self.profile = profile or load_profile()
        self.fact_bank = fact_bank or load_fact_bank()
        self.scoring_engine = JobScoringEngine(self.profile, self.fact_bank)
        self.eligibility_classifier = EligibilityClassifier()
        self.work_auth_classifier = WorkAuthClassifier()
        self.priority_engine = ApplicationPriorityEngine()

    def track_job(
        self,
        job_id: int,
        status: ApplicationStatus = ApplicationStatus.DISCOVERED,
        notes: str | None = None,
        tailored_resume_path: str | None = None,
        cover_letter_path: str | None = None,
    ) -> ApplicationRecord:
        """Create or return existing application tracking record for a job."""
        existing = self.repo.get_application_by_job_id(job_id)
        if existing:
            return existing

        now_iso = datetime.now(UTC).isoformat()
        record = ApplicationRecord(
            job_id=job_id,
            status=status,
            notes=notes,
            tailored_resume_path=tailored_resume_path,
            cover_letter_path=cover_letter_path,
            created_at=now_iso,
            updated_at=now_iso,
        )
        app_id = self.repo.create_application(record)
        record.id = app_id
        return record

    def update_status(
        self,
        app_id: int,
        status: ApplicationStatus,
        notes: str | None = None,
        applied_at: str | None = None,
        tailored_resume_path: str | None = None,
        cover_letter_path: str | None = None,
    ) -> ApplicationRecord | None:
        """Update lifecycle status and metadata for an existing tracked application."""
        if status == ApplicationStatus.APPLIED and not applied_at:
            applied_at = datetime.now(UTC).isoformat()

        self.repo.update_application_status(
            app_id=app_id,
            status=status,
            notes=notes,
            applied_at=applied_at,
            tailored_resume_path=tailored_resume_path,
            cover_letter_path=cover_letter_path,
        )
        return self.repo.get_application(app_id)

    def list_applications(
        self, status: ApplicationStatus | None = None
    ) -> list[dict[str, object]]:
        """List tracked applications joined with job details."""
        apps = self.repo.list_applications(status=status)
        results: list[dict[str, object]] = []
        for app in apps:
            job = self.repo.get_job_by_id(app.job_id)
            results.append(
                {
                    "application_id": app.id,
                    "job_id": app.job_id,
                    "company": job.company if job else "Unknown",
                    "title": job.title if job else "Unknown",
                    "location": job.location if job else "Unknown",
                    "application_url": job.application_url if job else None,
                    "status": app.status.value,
                    "applied_at": app.applied_at,
                    "notes": app.notes,
                    "resume_path": app.tailored_resume_path,
                    "cover_letter_path": app.cover_letter_path,
                    "created_at": app.created_at,
                    "updated_at": app.updated_at,
                }
            )
        return results

    def format_best_jobs_report(
        self,
        jobs: list[NormalizedJob] | None = None,
        limit: int = 10,
        min_score: float = 60.0,
    ) -> str:
        """Format an executive text dashboard of top ranked opportunities."""
        if jobs is None:
            jobs = self.repo.list_normalized_jobs(limit=100)

        scored_items: list[tuple[NormalizedJob, float, ApplicationPriorityTier, str, str, str, str, bool, bool]] = []

        for job in jobs:
            score_res = self.scoring_engine.score_job(job)
            if score_res.match_score < min_score:
                continue

            eligibility = self.eligibility_classifier.classify(job)
            work_auth = self.work_auth_classifier.classify(job)
            _priority_score, priority_tier, _ = self.priority_engine.compute_priority(
                job=job,
                match_score=score_res.match_score,
                eligibility=eligibility,
                work_auth=work_auth,
                freshness_age_hours=job.freshness_age_hours,
            )

            # Determine freshness display
            age = job.freshness_age_hours
            if age is not None:
                freshness_str = f"{round(age)}h" if age >= 1 else "<1h"
            else:
                freshness_str = job.freshness_status or "Unknown"

            # Check if tracked and determine package generation status
            tracked_app = self.repo.get_application_by_job_id(job.id) if job.id else None
            tier_is_a = priority_tier in (
                ApplicationPriorityTier.CRITICAL,
                ApplicationPriorityTier.HIGH,
                ApplicationPriorityTier.APPLY,
            )

            if tracked_app:
                app_status = tracked_app.status.value.upper()
                has_resume = bool(tracked_app.tailored_resume_path)
                has_cover_letter = bool(tracked_app.cover_letter_path)
                if has_resume and has_cover_letter:
                    package_status = "GENERATED"
                elif has_resume or has_cover_letter:
                    package_status = "PARTIAL"
                else:
                    package_status = "NOT_GENERATED"
            else:
                app_status = "READY_TO_APPLY" if tier_is_a else "REVIEWING"
                has_resume = False
                has_cover_letter = False
                package_status = "NOT_GENERATED"

            tier_label = "A" if tier_is_a else ("B" if priority_tier == ApplicationPriorityTier.WATCH else "C")
            scored_items.append((
                job,
                score_res.match_score,
                priority_tier,
                freshness_str,
                tier_label,
                app_status,
                package_status,
                has_resume,
                has_cover_letter,
            ))

        # Sort descending by match score
        scored_items.sort(key=lambda x: x[1], reverse=True)
        top_items = scored_items[:limit]

        if not top_items:
            return "Today's best jobs\n-----------------\nNo qualifying jobs found matching criteria."

        lines = ["Today's best jobs", "-----------------", ""]
        for idx, (
            job,
            score,
            _tier,
            freshness_str,
            tier_label,
            curr_status,
            package_status,
            has_resume,
            has_cover_letter,
        ) in enumerate(top_items, 1):
            location_str = job.location or "Not specified"
            clean_title = job.title.replace("—", "-").replace("–", "-")

            lines.append(f"{idx}. {clean_title} at {job.company}")
            lines.append(f"   Match: {round(score)}")
            lines.append(f"   Freshness: {freshness_str}")
            lines.append(f"   Tier: {tier_label}")
            lines.append(f"   Location: {location_str}")
            lines.append(f"   Status: {curr_status}")
            lines.append(f"   Package: {package_status}")
            if package_status == "GENERATED":
                lines.append("   Resume: ✓")
                lines.append("   Cover Letter: ✓")
            elif package_status == "PARTIAL":
                lines.append(f"   Resume: {'✓' if has_resume else '✗'}")
                lines.append(f"   Cover Letter: {'✓' if has_cover_letter else '✗'}")
            if job.application_url:
                lines.append(f"   Apply: {job.application_url}")
            lines.append("")

        return "\n".join(lines).strip()


def main() -> None:
    """CLI entry point for application tracking and summary dashboard."""
    parser = argparse.ArgumentParser(description="Job-AI Application Tracker & Opportunity Dashboard")
    parser.add_argument("--report", action="store_true", help="Display Today's Best Jobs report")
    parser.add_argument("--list", action="store_true", help="List all tracked applications")
    parser.add_argument("--status", type=str, choices=[s.value for s in ApplicationStatus], help="Filter by application status")
    parser.add_argument("--update-id", type=int, help="Application ID to update")
    parser.add_argument("--new-status", type=str, choices=[s.value for s in ApplicationStatus], help="New status to set")
    parser.add_argument("--notes", type=str, help="Notes for application status update")

    args = parser.parse_args()
    tracker = ApplicationTracker()

    if args.update_id and args.new_status:
        updated = tracker.update_status(
            app_id=args.update_id,
            status=ApplicationStatus(args.new_status),
            notes=args.notes,
        )
        if updated:
            print(f"Successfully updated application #{args.update_id} status to {args.new_status}.")
        else:
            print(f"Failed to update application #{args.update_id}.")
        return

    if args.list:
        filter_status = ApplicationStatus(args.status) if args.status else None
        apps = tracker.list_applications(status=filter_status)
        print(f"--- Tracked Applications ({len(apps)}) ---")
        for app in apps:
            print(f"#{app['application_id']} | Job #{app['job_id']} | {app['company']} - {app['title']} | Status: {app['status']} | Notes: {app['notes']}")
        return

    # Default to report
    report = tracker.format_best_jobs_report()
    print(report)


if __name__ == "__main__":
    main()
