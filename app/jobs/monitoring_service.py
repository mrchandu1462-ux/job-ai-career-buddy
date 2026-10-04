"""Fresh Job Monitoring and Alert Engine (Phase 5).

Proactively discovers newly posted semiconductor / VLSI opportunities published within 24 hours,
evaluates candidate fit via the existing 7D matching engine, isolates adapter failures,
deduplicates cross-source listings, and proposes human-gated opportunity notifications.
"""

import logging
import sqlite3
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from app.career.notifications import (
    ScheduleNotificationService,
)
from app.db.models import RawJob
from app.db.repository import DuplicateFingerprintError, JobRepository
from app.jobs.classifier import RoleClassifier
from app.jobs.freshness import (
    calculate_alert_priority,
    calculate_job_freshness,
    classify_geography,
    extract_visa_sponsorship,
    extract_workplace_type,
)
from app.jobs.models import (
    AlertPriority,
    FreshnessStatus,
    JobAlertRecord,
    JobSourceRunRecord,
    MonitoringCycleReport,
)
from app.jobs.normalizer import generate_job_fingerprint, normalize_job_listing
from app.jobs.sources.adapters import (
    FeedJobSourceAdapter,
    JobSourceAdapter,
    SemiconductorCareerPageAdapter,
)
from app.jobs.sources.base import JobDiscoveryQuery, RawJobPayload
from app.matching.scorer import JobScoringEngine
from app.profile.models import CandidateProfile, FactBank

logger = logging.getLogger(__name__)


class FreshJobMonitoringService:
    """
    Automated and manual Fresh Job Monitoring & Alerting Engine.
    Strictly preserves zero fabrication, local SQLite persistence, and human approval safeguards.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        profile: CandidateProfile,
        fact_bank: FactBank,
        adapters: list[JobSourceAdapter] | None = None,
        job_repo: JobRepository | None = None,
        scoring_engine: JobScoringEngine | None = None,
        notification_service: ScheduleNotificationService | None = None,
    ):
        self.conn = conn
        self.profile = profile
        self.fact_bank = fact_bank
        self.job_repo = job_repo or JobRepository(conn)
        self.scoring_engine = scoring_engine or JobScoringEngine(profile, fact_bank)
        self.role_classifier = RoleClassifier()
        self.notification_service = notification_service or ScheduleNotificationService(conn)

        # Register default adapters if none provided
        if adapters is not None:
            self.adapters = list(adapters)
        else:
            self.adapters = [
                SemiconductorCareerPageAdapter(),
                FeedJobSourceAdapter(),
            ]

    def register_adapter(self, adapter: JobSourceAdapter) -> None:
        """Register an additional source adapter."""
        self.adapters.append(adapter)

    def run_monitoring_cycle(
        self,
        region: str = "all",
        fresh_only: bool = False,
        dry_run: bool = False,
        limit: int = 50,
    ) -> MonitoringCycleReport:
        """
        Execute a complete monitoring cycle across all registered adapters.
        - Isolates failures per adapter.
        - Deduplicates cross-source postings into single canonical jobs.
        - Calculates verified freshness (<24h) and 7D match score.
        - Assigns P0/P1 alert priorities.
        - If dry_run is False, persists jobs, audits source runs, and creates human-reviewable proposals.
        """
        run_id = f"run_{uuid.uuid4().hex[:10]}"
        now = datetime.now(UTC)
        run_timestamp = now.isoformat()

        sources_checked = 0
        sources_successful = 0
        sources_failed = 0
        total_raw_jobs = 0
        source_health_map: dict[str, dict[str, Any]] = {}
        all_raw_payloads: list[RawJobPayload] = []

        query = JobDiscoveryQuery(
            keywords=self.profile.candidate.target_roles,
            locations=self.profile.candidate.locations.india_priority,
            country="India" if region == "india" else ("Overseas" if region == "overseas" else None),
            limit=limit,
        )

        # 1. Fetch jobs from each adapter with failure isolation
        for adapter in self.adapters:
            if not adapter.supports_region(region):
                continue

            sources_checked += 1
            adapter_start = time.perf_counter()
            adapter_status = "success"
            error_msg = None
            fetched_payloads: list[RawJobPayload] = []

            try:
                fetched_payloads = adapter.fetch_jobs(query)
                sources_successful += 1
                total_raw_jobs += len(fetched_payloads)
                all_raw_payloads.extend(fetched_payloads)
            except Exception as exc:  # noqa: BLE001
                sources_failed += 1
                adapter_status = "failed"
                error_msg = str(exc)
                logger.warning(f"Source adapter '{adapter.adapter_name}' failed during monitoring: {exc}")

            duration_ms = round((time.perf_counter() - adapter_start) * 1000.0, 2)
            fresh_count = sum(
                1
                for p in fetched_payloads
                if calculate_job_freshness(p.metadata.get("published_at"), now)[0]
                in (FreshnessStatus.FRESH_0_6_HOURS, FreshnessStatus.FRESH_6_24_HOURS)
            )

            source_run_record = JobSourceRunRecord(
                source_name=adapter.adapter_name,
                run_timestamp=run_timestamp,
                status=adapter_status,
                jobs_discovered=len(fetched_payloads),
                jobs_accepted=len(fetched_payloads) if adapter_status == "success" else 0,
                jobs_rejected=0 if adapter_status == "success" else len(fetched_payloads),
                fresh_jobs_count=fresh_count,
                duration_ms=duration_ms,
                error_message=error_msg,
            )

            source_health_map[adapter.adapter_name] = {
                "status": adapter_status,
                "jobs_discovered": len(fetched_payloads),
                "fresh_count": fresh_count,
                "duration_ms": duration_ms,
                "error": error_msg,
            }

            if not dry_run:
                try:
                    self.job_repo.record_source_run(source_run_record)
                except sqlite3.Error as db_exc:
                    logger.error(f"Failed to record source run in DB: {db_exc}")


        # 2. Multi-Source Deduplication
        # Merge identical jobs discovered across multiple sources into a single canonical job record
        deduped_jobs_map: dict[str, dict[str, Any]] = {}

        for payload in all_raw_payloads:
            published_at = payload.metadata.get("published_at")
            workplace_type = payload.metadata.get("workplace_type") or extract_workplace_type(payload.raw_payload)
            visa = payload.metadata.get("visa_sponsorship") or extract_visa_sponsorship(payload.raw_payload)

            fingerprint = generate_job_fingerprint(
                company=payload.company, title=payload.title, location=payload.location
            )

            if fingerprint in deduped_jobs_map:
                # Merge source reference into existing canonical entry
                existing_entry = deduped_jobs_map[fingerprint]
                if payload.source not in existing_entry["sources"]:
                    existing_entry["sources"].append(payload.source)
                # Keep earliest verified publication date
                if published_at and (not existing_entry["published_at"] or published_at < existing_entry["published_at"]):
                    existing_entry["published_at"] = published_at
            else:
                deduped_jobs_map[fingerprint] = {
                    "payload": payload,
                    "published_at": published_at,
                    "workplace_type": workplace_type,
                    "visa_sponsorship": visa,
                    "sources": [payload.source],
                }

        # 3. Normalization, Freshness Calculation, 7D Matching, and Prioritization
        evaluated_alerts: list[JobAlertRecord] = []
        fresh_24h_count = 0
        p0_count = 0
        p1_count = 0
        p2_count = 0
        p3_count = 0
        notifications_count = 0

        for fingerprint, entry in deduped_jobs_map.items():
            payload: RawJobPayload = entry["payload"]
            published_at = entry["published_at"]
            sources_list = entry["sources"]

            # Normalized Job model
            norm_job = normalize_job_listing(
                company=payload.company,
                title=payload.title,
                raw_text=payload.raw_payload,
                location=payload.location,
                country=payload.country,
                employment_type=payload.employment_type,
                source=payload.source,
                application_url=payload.application_url,
                published_at=published_at,
                workplace_type=entry["workplace_type"],
                visa_sponsorship=entry["visa_sponsorship"],
                source_references=sources_list,
            )

            freshness_status, age_hours, _ = calculate_job_freshness(published_at, now)

            # Check fresh_only filter
            if fresh_only and freshness_status not in (FreshnessStatus.FRESH_0_6_HOURS, FreshnessStatus.FRESH_6_24_HOURS):
                continue

            if freshness_status in (FreshnessStatus.FRESH_0_6_HOURS, FreshnessStatus.FRESH_6_24_HOURS):
                fresh_24h_count += 1

            # 7D Match Score Evaluation
            match_res = self.scoring_engine.score_job(norm_job)
            match_score = round(match_res.match_score, 1)

            # Role Category classification
            role_class = self.role_classifier.classify(norm_job.title, norm_job.description or "")
            priority = calculate_alert_priority(
                match_score=match_score,
                is_eligible=match_res.is_eligible,
                freshness=freshness_status,
                role_category=role_class.category.value,
            )

            if priority == AlertPriority.P0:
                p0_count += 1
            elif priority == AlertPriority.P1:
                p1_count += 1
            elif priority == AlertPriority.P2:
                p2_count += 1
            else:
                p3_count += 1

            persisted_job_id = None
            notification_proposal_id = None

            # 4. Persistence & Alert Deduplication (when not dry_run)
            if not dry_run:
                # Insert Raw Job
                raw_job = RawJob(
                    source=payload.source,
                    source_url=payload.source_url,
                    discovered_at=payload.discovered_at,
                    raw_payload=payload.raw_payload,
                    content_hash=payload.content_hash,
                )
                try:
                    raw_id = self.job_repo.insert_raw_job(raw_job)
                    norm_job.raw_job_id = raw_id
                except sqlite3.Error as exc:
                    logger.debug(f"Raw job insertion skipped or exists: {exc}")

                # Insert Normalized Job (or get existing ID)
                try:
                    persisted_job_id = self.job_repo.insert_normalized_job(norm_job)
                except DuplicateFingerprintError:
                    existing_job = self.job_repo.get_normalized_job_by_fingerprint(norm_job.fingerprint)
                    if existing_job:
                        persisted_job_id = existing_job.id

                # Alert & Notification Gate for Qualifying P0 / P1 jobs
                if persisted_job_id is not None:
                    existing_alert = self.job_repo.get_job_alert_by_job_id(persisted_job_id)

                    # Create Notification Proposal ONLY if not already alerted
                    if existing_alert is None and priority in (AlertPriority.P0, AlertPriority.P1):
                        geo_info = classify_geography(norm_job.location, norm_job.country)
                        fresh_text = f"{age_hours:.1f} hours ago" if age_hours is not None else "Recently verified"

                        # Truthful Adjacent & Missing Summary
                        why_bullets = [f"Direct Match: {s}" for s in match_res.score_breakdown.matching_skills[:4]]
                        if not why_bullets:
                            why_bullets.append(f"Target Role Alignment: {role_class.category.value}")

                        missing_bullets = [f"Missing Fact: {m}" for m in match_res.score_breakdown.missing_skills[:3]]

                        body_content = (
                            f"🏢 Company: {norm_job.company}\n"
                            f"💼 Role: {norm_job.title} ({norm_job.employment_type or 'Full-time'})\n"
                            f"📍 Location: {norm_job.location or 'Not specified'} ({geo_info['market_region']})\n"
                            f"🕒 Published: {fresh_text} | Discovered: {run_timestamp[:16].replace('T', ' ')}\n"
                            f"🎯 7D Match Score: {match_score}/100 [Priority: {priority.value}]\n\n"
                            f"✅ Key Strengths:\n" + "\n".join(f"- {b}" for b in why_bullets) + "\n\n"
                            "⚠️ Missing Verification Requirements:\n" + ("\n".join(f"- {m}" for m in missing_bullets) if missing_bullets else "- None identified") + "\n\n"
                            f"🔗 Official Portal: {norm_job.application_url or payload.source_url or 'N/A'}\n"
                            f"🛡️ Human Action: Review in Fresh Jobs dashboard. Preparing/approving will NEVER auto-submit."
                        )

                        proposal = self.notification_service.propose_schedule_notification(
                            notification_type="email_reminder",
                            destination="candidate@vlsi-career.internal",
                            target_company=norm_job.company,
                            target_role=norm_job.title,
                            scheduled_time=run_timestamp,
                            action_type="fresh_job_alert",
                            subject=f"🔥 [{priority.value}] Fresh DV Job: {norm_job.company} — {norm_job.title} ({norm_job.location or 'India'})",
                            body_content=body_content,
                            rationale=f"Fresh {priority.value} opportunity published {fresh_text} with {int(match_score)}% candidate match.",
                        )
                        notification_proposal_id = proposal.id
                        notifications_count += 1

                    # Persist Job Alert record
                    alert_record = JobAlertRecord(
                        job_id=persisted_job_id,
                        company=norm_job.company,
                        title=norm_job.title,
                        location=norm_job.location,
                        country=norm_job.country,
                        published_at=norm_job.published_at,
                        freshness_status=freshness_status,
                        freshness_age_hours=age_hours,
                        match_score=match_score,
                        priority=priority,
                        status="proposed",
                        notification_proposal_id=notification_proposal_id,
                        created_at=run_timestamp,
                    )
                    try:
                        alert_id = self.job_repo.create_job_alert(alert_record)
                        alert_record.id = alert_id
                    except sqlite3.Error as exc:
                        logger.debug(f"Job alert persistence skipped or exists: {exc}")

                    evaluated_alerts.append(alert_record)


            else:
                # Dry run alert item
                alert_record = JobAlertRecord(
                    job_id=0,
                    company=norm_job.company,
                    title=norm_job.title,
                    location=norm_job.location,
                    country=norm_job.country,
                    published_at=norm_job.published_at,
                    freshness_status=freshness_status,
                    freshness_age_hours=age_hours,
                    match_score=match_score,
                    priority=priority,
                    status="proposed",
                    notification_proposal_id=None,
                    created_at=run_timestamp,
                )
                evaluated_alerts.append(alert_record)

        report = MonitoringCycleReport(
            run_id=run_id,
            timestamp=run_timestamp,
            region=region,
            sources_checked=sources_checked,
            sources_successful=sources_successful,
            sources_failed=sources_failed,
            total_jobs_found=total_raw_jobs,
            unique_jobs_ingested=len(deduped_jobs_map),
            fresh_24h_jobs_count=fresh_24h_count,
            p0_count=p0_count,
            p1_count=p1_count,
            p2_count=p2_count,
            p3_count=p3_count,
            notifications_generated=notifications_count,
            source_health=source_health_map,
            alerts=evaluated_alerts,
            dry_run=dry_run,
        )

        return report

    def get_last_monitoring_run_summary(self) -> dict[str, Any]:
        """Aggregate summary metrics of recent source runs and fresh job discoveries."""
        runs = self.job_repo.list_source_runs(limit=10)
        recent_alerts = self.job_repo.list_job_alerts(limit=50)

        total_discovered = sum(r.jobs_discovered for r in runs)
        fresh_jobs = sum(r.fresh_jobs_count for r in runs)
        p0_alerts = [a for a in recent_alerts if a.priority == AlertPriority.P0]
        p1_alerts = [a for a in recent_alerts if a.priority == AlertPriority.P1]
        failed_runs = [r for r in runs if r.status == "failed"]

        last_run_time = runs[0].run_timestamp[:19].replace("T", " ") if runs else "No runs recorded"

        return {
            "last_run_timestamp": last_run_time,
            "sources_monitored": len(runs),
            "total_jobs_discovered": total_discovered,
            "fresh_jobs_count": fresh_jobs,
            "p0_opportunities": len(p0_alerts),
            "p1_opportunities": len(p1_alerts),
            "source_failures": len(failed_runs),
            "recent_runs": runs,
        }

    def list_active_alerts(
        self,
        priority: AlertPriority | str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[JobAlertRecord]:
        """List opportunity alerts."""
        p_str = priority.value if isinstance(priority, AlertPriority) else (priority if priority != "ALL" else None)
        return self.job_repo.list_job_alerts(priority=p_str, status=status, limit=limit)
