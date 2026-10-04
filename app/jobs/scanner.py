"""Fresh Job Scanner engine for continuous 24-hour semiconductor job intelligence."""

import logging
import os
import sqlite3
import time
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.application.intelligence import ApplicationIntelligenceService
from app.career.notifications import ScheduleNotificationService
from app.db.models import (
    AlertMode,
    AlertPriority,
    FreshnessStatus,
    JobAlertRecord,
    JobPriorityCategory,
    JobSourceRunRecord,
    RawJob,
)
from app.db.repository import DuplicateFingerprintError, JobRepository
from app.jobs.classifier import RoleClassifier
from app.jobs.freshness import (
    calculate_fresh_job_priority_score,
    calculate_granular_freshness,
    calculate_job_freshness,
    classify_geography,
    classify_visa_sponsorship_category,
    extract_workplace_type,
)
from app.jobs.normalizer import generate_job_fingerprint, normalize_job_listing
from app.jobs.sources.adapters import (
    FeedJobSourceAdapter,
    JobSourceAdapter,
    SemiconductorCareerPageAdapter,
)
from app.jobs.sources.base import JobDiscoveryQuery, RawJobPayload
from app.jobs.sources.dynamic import (
    GreenhouseCareerAdapter,
    WorkdayCareerAdapter,
)
from app.jobs.watchlist import CompanyWatchlistService
from app.matching.scorer import JobScoringEngine
from app.notifications.email import MockEmailProvider
from app.notifications.service import EmailNotificationService
from app.profile.loader import load_candidate_profile, load_fact_bank
from app.profile.models import CandidateProfile, FactBank

logger = logging.getLogger(__name__)


class ScanReport(BaseModel):
    """Execution metrics from a FreshJobScanner run."""

    model_config = ConfigDict(extra="forbid")

    timestamp: str
    region: str
    window_hours: float
    sources_total: int = 0
    sources_successful: int = 0
    sources_failed: int = 0
    jobs_scanned: int = 0
    jobs_discovered: int = 0
    new_jobs: int = 0
    fresh_24h: int = 0
    india_count: int = 0
    overseas_count: int = 0
    critical_matches: int = 0
    high_matches: int = 0
    duplicates_removed: int = 0
    notifications_proposed: int = 0
    duration_ms: float = 0.0
    discovered_jobs: list[dict[str, Any]] = Field(default_factory=list)


class FreshJobScanner:
    """
    Production-grade 24-Hour Fresh Job Scanner.
    Discovers, verifies, deduplicates, ranks (8D explainable score), and proposes notifications.
    Strictly human-gated: never applies autonomously.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        profile: CandidateProfile | None = None,
        fact_bank: FactBank | None = None,
        adapters: list[JobSourceAdapter] | None = None,
        scoring_engine: JobScoringEngine | None = None,
        notification_service: ScheduleNotificationService | None = None,
        allow_mock: bool = False,
        email_service: EmailNotificationService | None = None,
    ):
        self.conn = conn
        self.profile = profile or load_candidate_profile()
        self.fact_bank = fact_bank or load_fact_bank()
        self.repo = JobRepository(conn)
        self.watchlist_service = CompanyWatchlistService(conn)
        self.scoring_engine = scoring_engine or JobScoringEngine(self.profile, self.fact_bank)
        self.role_classifier = RoleClassifier()
        self.notification_service = notification_service or ScheduleNotificationService(conn)
        self.allow_mock = allow_mock
        self.intelligence_service = ApplicationIntelligenceService(self.fact_bank, self.profile)
        self.email_service = email_service or EmailNotificationService(
            conn, provider=MockEmailProvider() if allow_mock else None
        )


        if adapters is not None:
            # Ensure no MockJobSourceAdapter is injected unless explicitly allowed for testing.
            from app.jobs.sources.adapters import MockJobSourceAdapter
            for a in adapters:
                if isinstance(a, MockJobSourceAdapter) and not allow_mock:
                    raise ValueError(
                        "MockJobSourceAdapter cannot be used in production scans. "
                        "Pass allow_mock=True when constructing the scanner for tests."
                    )
            self.adapters = list(adapters)
        else:
            self.adapters = [
                SemiconductorCareerPageAdapter(),
                FeedJobSourceAdapter(),
                WorkdayCareerAdapter(),
                GreenhouseCareerAdapter(),
            ]

    def register_adapter(self, adapter: JobSourceAdapter) -> None:
        """Register a modular source adapter."""
        from app.jobs.sources.adapters import MockJobSourceAdapter
        if isinstance(adapter, MockJobSourceAdapter) and not self.allow_mock:
            raise ValueError(
                "MockJobSourceAdapter cannot be used in production scans. "
                "Pass allow_mock=True when constructing the scanner for tests."
            )
        self.adapters.append(adapter)

    def scan(
        self,
        region: str = "all",
        hours: float = 24.0,
        dry_run: bool = False,
        min_score: float = 60.0,
        limit: int = 100,
        alert_mode: str | AlertMode = AlertMode.HIGH_AND_CRITICAL,
        company_filter: str | None = None,
        role_filter: str | None = None,
    ) -> ScanReport:
        """
        Execute comprehensive fresh job discovery scan.
        Isolates source failures so degraded sources do not crash the cycle.
        """
        start_time = time.perf_counter()
        now_dt = datetime.now(UTC)
        now_iso = now_dt.isoformat()
        # Acquire scanner lock to ensure only one scan runs at a time
        lock_owner = f"{os.getpid()}-{datetime.now(UTC).isoformat()}"
        if not self.repo.acquire_scanner_lock("fresh_job_scanner", lock_owner, lease_seconds=300):
            logger.error("Another FreshJobScanner instance is already running. Aborting this scan.")
            raise RuntimeError("Scanner lock already held by another process.")

        try:
            report = ScanReport(
                timestamp=now_iso,
                region=region,
                window_hours=hours,
                sources_total=len(self.adapters),
            )

            query = JobDiscoveryQuery(
                keywords=[
                    "Design Verification",
                    "UVM",
                    "SystemVerilog",
                    "RTL Design",
                    "ASIC Verification",
                    "VLSI Engineer",
                    "Graduate Trainee",
                ],
                limit=limit,
            )

            all_discovered: list[dict[str, Any]] = []

            for adapter in self.adapters:
                adapter_start = time.perf_counter()
                adapter_jobs = 0
                adapter_fresh = 0
                adapter_status = "success"
                err_msg = None

                try:
                    if not adapter.supports_region(region):
                        continue

                    raw_payloads = adapter.fetch_jobs(query)
                    adapter_jobs = len(raw_payloads)
                    report.jobs_scanned += adapter_jobs

                    for raw in raw_payloads:
                        if company_filter and company_filter.lower() not in raw.company.lower():
                            continue
                        if role_filter and role_filter.lower() not in raw.title.lower():
                            continue

                        report.jobs_discovered += 1
                        proc_res = self._process_raw_payload(
                            raw=raw,
                            adapter_name=adapter.adapter_name,
                            source_category=adapter.source_category,
                            now_dt=now_dt,
                            hours=hours,
                            min_score=min_score,
                            alert_mode=alert_mode,
                            dry_run=dry_run,
                        )

                        if proc_res.get("is_new"):
                            report.new_jobs += 1
                        if proc_res.get("is_duplicate"):
                            report.duplicates_removed += 1
                        if proc_res.get("is_fresh"):
                            report.fresh_24h += 1
                            adapter_fresh += 1
                        if proc_res.get("is_india"):
                            report.india_count += 1
                        elif proc_res.get("is_overseas"):
                            report.overseas_count += 1
                        if proc_res.get("priority_category") == "CRITICAL":
                            report.critical_matches += 1
                        elif proc_res.get("priority_category") == "HIGH":
                            report.high_matches += 1
                        if proc_res.get("notification_proposed"):
                            report.notifications_proposed += 1

                        if proc_res.get("job_info"):
                            all_discovered.append(proc_res["job_info"])

                    report.sources_successful += 1

                except Exception as e:
                    logger.exception("Source adapter '%s' failed", adapter.adapter_name)
                    report.sources_failed += 1
                    adapter_status = "failed"
                    err_msg = str(e)

                finally:
                    if not dry_run:
                        adapter_dur = (time.perf_counter() - adapter_start) * 1000.0
                        try:
                            self.repo.record_source_run(
                                JobSourceRunRecord(
                                    source_name=adapter.adapter_name,
                                    run_timestamp=now_iso,
                                    status=adapter_status,
                                    jobs_discovered=adapter_jobs,
                                    jobs_accepted=adapter_jobs,
                                    jobs_rejected=0,
                                    fresh_jobs_count=adapter_fresh,
                                    duration_ms=round(adapter_dur, 2),
                                    error_message=err_msg,
                                )
                            )
                        except (sqlite3.Error, OSError) as ex:
                            logger.warning(f"Could not record source run: {ex}")

            report.duration_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
            report.discovered_jobs = all_discovered
            return report
        finally:
            # Release the lock regardless of success or failure
            self.repo.release_scanner_lock("fresh_job_scanner", lock_owner)

    def _process_raw_payload(
        self,
        raw: RawJobPayload,
        adapter_name: str,
        source_category: str,
        now_dt: datetime,
        hours: float,
        min_score: float,
        alert_mode: str | AlertMode = AlertMode.HIGH_AND_CRITICAL,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Normalize, score, deduplicate, and propose notification for a single listing."""
        now_iso = now_dt.isoformat()
        geo = classify_geography(raw.location, raw.country)
        workplace = extract_workplace_type(raw.raw_payload)
        visa_cat, visa_conf = classify_visa_sponsorship_category(raw.raw_payload)

        raw_pub = raw.metadata.get("published_at")
        bucket, age_hours, f_conf, t_source = calculate_granular_freshness(
            published_at=raw_pub,
            now=now_dt,
            timestamp_source="official_listing" if raw_pub else "unverified",
        )
        fresh_status, _, _ = calculate_job_freshness(raw_pub, now=now_dt)

        is_fresh = (age_hours is not None and age_hours <= hours)
        is_watched = self.watchlist_service.is_watched(raw.company)

        # Normalize job listing
        norm_job = normalize_job_listing(
            company=raw.company,
            title=raw.title,
            raw_text=raw.raw_payload,
            source=adapter_name,
            source_url=raw.source_url,
            application_url=raw.application_url or raw.source_url,
            location=raw.location,
            country=raw.country,
            published_at=raw_pub,
            raw_job_id=None,
        )

        # Match calculation via 7D scoring engine
        match_result = self.scoring_engine.score_job(norm_job)
        match_score = float(match_result.match_score)

        # 8D explainable priority score
        score_8d = calculate_fresh_job_priority_score(
            match_score=match_score,
            freshness_bucket=bucket,
            freshness_confidence=f_conf,
            fresher_fit=True,
            is_watchlist=is_watched,
            has_direct_url=bool(raw.application_url or raw.source_url),
            is_india=geo["is_india"],
            visa_supported=(visa_cat.value == "SPONSORSHIP_CONFIRMED"),
        )

        req_id = (
            raw.metadata.get("requisition_id")
            or raw.metadata.get("job_id")
            or raw.metadata.get("req_id")
            if isinstance(raw.metadata, dict)
            else None
        )
        fp = generate_job_fingerprint(
            company=raw.company,
            title=raw.title,
            location=raw.location or "India",
            published_at=raw_pub,
            requisition_id=req_id,
        )

        is_new = False
        is_duplicate = False
        job_id = None
        notification_proposed = False
        materially_changed = False

        if not dry_run:
            existing_job = self.repo.get_normalized_job_by_fingerprint(fp)
            if existing_job:
                is_duplicate = True
                job_id = existing_job.id

                # Detect material change (e.g. substantially updated description or new direct application portal with expanded details)
                if (
                    len(raw.raw_payload) > len(existing_job.description or "") + 80
                    and raw.application_url != existing_job.application_url
                ) or len(raw.raw_payload) > len(existing_job.description or "") + 120:
                    materially_changed = True

                # Update existing job freshness
                if job_id is not None:
                    self.repo.update_normalized_job_freshness(
                        job_id=job_id,
                        freshness_status=fresh_status.value if isinstance(fresh_status, FreshnessStatus) else str(fresh_status),
                        freshness_age_hours=age_hours,
                        freshness_bucket=bucket.value,
                        freshness_confidence=f_conf.value,
                        priority_score=score_8d.total_score,
                        priority_category=score_8d.category.value,
                        is_watchlist=is_watched,
                    )
            else:
                try:
                    # Extend fields
                    norm_job.posted_at = raw_pub
                    norm_job.discovered_at = now_iso
                    norm_job.source_timestamp = raw_pub
                    norm_job.freshness_status = fresh_status.value
                    norm_job.freshness_bucket = bucket.value
                    norm_job.freshness_confidence = f_conf.value
                    norm_job.timestamp_source = t_source
                    norm_job.freshness_age_hours = age_hours
                    norm_job.region = "india" if geo["is_india"] else "overseas"
                    norm_job.city = geo["priority_hub"]
                    norm_job.workplace_type = workplace
                    norm_job.remote_type = workplace
                    norm_job.visa_sponsorship = visa_cat.value
                    norm_job.visa_status = visa_cat.value
                    norm_job.sponsorship_confidence = visa_conf.value
                    norm_job.source_name = adapter_name
                    norm_job.source_type = source_category
                    norm_job.canonical_url = raw.application_url or raw.source_url
                    norm_job.priority_score = score_8d.total_score
                    norm_job.priority_category = score_8d.category.value
                    norm_job.is_watchlist = is_watched

                    # Persist raw job record
                    raw_id = self.repo.insert_raw_job(
                        RawJob(
                            source=adapter_name,
                            source_url=raw.source_url,
                            discovered_at=now_iso,
                            raw_payload=raw.raw_payload,
                            content_hash=raw.content_hash,
                        )
                    )
                    norm_job.raw_job_id = raw_id
                    job_id = self.repo.insert_normalized_job(norm_job)
                    is_new = True

                except DuplicateFingerprintError:
                    is_duplicate = True
                except (sqlite3.Error, ValueError, KeyError) as ex:
                    logger.warning(f"Error persisting normalized job: {ex}")

            # Check if alert should be proposed based on AlertMode
            mode_str = str(alert_mode.value if isinstance(alert_mode, AlertMode) else alert_mode).upper()
            should_alert = False

            if mode_str == "CRITICAL_ONLY":
                should_alert = (score_8d.category == JobPriorityCategory.CRITICAL or score_8d.total_score >= 88.0)
            elif mode_str == "HIGH_AND_CRITICAL":
                should_alert = (score_8d.category in (JobPriorityCategory.CRITICAL, JobPriorityCategory.HIGH) or score_8d.total_score >= 75.0)
            elif mode_str == "ALL_MATCHED":
                should_alert = (score_8d.total_score >= min_score)
            elif mode_str == "WATCHLIST_COMPANIES":
                should_alert = is_watched or (score_8d.category in (JobPriorityCategory.CRITICAL, JobPriorityCategory.HIGH))
            elif mode_str == "HOURLY_CRITICAL":
                should_alert = (score_8d.category == JobPriorityCategory.CRITICAL)
            elif mode_str == "DAILY_DIGEST":
                should_alert = False  # Handled via daily digest generator
            else:
                should_alert = (score_8d.total_score >= min_score)

            if job_id is not None and should_alert:
                existing_alert = self.repo.get_job_alert_by_job_id(job_id)
                can_propose = (not existing_alert) or (materially_changed and existing_alert.notification_count < 3)

                if can_propose:
                    alert_priority = AlertPriority.P0 if score_8d.is_fresh_24h_match else AlertPriority.P1

                    # Create proposal record in notification service
                    prop_id = None
                    try:
                        badge = "🔥 FRESH 24H MATCH" if score_8d.is_fresh_24h_match else "🟢 RELEVANT OPPORTUNITY"
                        age_str = f"{age_hours:.1f} hours ago" if age_hours is not None else "Unknown / Unspecified"
                        rationale_age = f"{age_hours:.1f}h old" if age_hours is not None else "Active portal listing"
                        re_alert_prefix = "[MATERIAL UPDATE] " if materially_changed else ""
                        prop = self.notification_service.propose_schedule_notification(
                            notification_type="opportunity_alert",
                            destination="Candidate Portal",
                            target_company=raw.company,
                            target_role=raw.title,
                            scheduled_time=now_iso,
                            action_type="review_opportunity",
                            subject=f"{re_alert_prefix}[{badge}] {raw.title} at {raw.company}",
                            body_content=(
                                f"Role: {raw.title}\n"
                                f"Company: {raw.company}\n"
                                f"Location: {raw.location or 'India'}\n"
                                f"Posted: {age_str}\n"
                                f"Priority Score: {score_8d.total_score:.0f}/100\n"
                                f"Match: {match_score:.0f}/100\n"
                                f"Score Breakdown: Freshness={score_8d.freshness:.0f}/25, Tech={score_8d.technical_match:.0f}/25, Role={score_8d.role_match:.0f}/15\n"
                                f"Application URL: {raw.application_url or raw.source_url or 'N/A'}\n"
                                f"Status: PROPOSED (Human Approval Required)"
                            ),
                            rationale=f"Fresh verifiable opportunity ({rationale_age}) with strong candidate match ({match_score:.0f}/100).",
                        )
                        prop_id = prop.id if hasattr(prop, "id") else None
                    except (sqlite3.Error, ValueError, KeyError) as ex:
                        logger.warning(f"Failed to propose notification: {ex}")

                    if not existing_alert:
                        self.repo.create_job_alert(
                            JobAlertRecord(
                                job_id=job_id,
                                company=raw.company,
                                title=raw.title,
                                location=raw.location,
                                country=raw.country or "India",
                                published_at=raw_pub,
                                freshness_status=fresh_status,
                                freshness_age_hours=age_hours,
                                match_score=match_score,
                                priority=alert_priority,
                                status="proposed",
                                notification_proposal_id=prop_id,
                                created_at=now_iso,
                                priority_category=score_8d.category,
                                is_fresh_24h_match=score_8d.is_fresh_24h_match,
                                first_notified_at=now_iso,
                                last_notified_at=now_iso,
                                notification_count=1,
                            )
                        )
                    self.repo.mark_job_notified(job_id)
                    notification_proposed = True

                    # Automated Email Alert Dispatch for Qualifying Opportunities
                    try:
                        pkg = self.intelligence_service.create_application_package(
                            job=norm_job,
                            match_score=match_score,
                            freshness_age_hours=age_hours,
                            is_material_update=materially_changed,
                        )
                        if score_8d.category in (JobPriorityCategory.CRITICAL, JobPriorityCategory.HIGH) or score_8d.total_score >= 80.0:
                            self.email_service.process_immediate_alerts([pkg], dry_run=dry_run)
                    except (sqlite3.Error, ValueError, KeyError, RuntimeError, TypeError, OSError) as ex:
                        logger.warning("Email alert dispatch skipped/failed safely: %s", ex)


        return {
            "is_new": is_new,
            "is_duplicate": is_duplicate,
            "is_fresh": is_fresh,
            "is_india": geo["is_india"],
            "is_overseas": geo["is_overseas"],
            "priority_category": score_8d.category.value,
            "score_8d": score_8d.total_score,
            "notification_proposed": notification_proposed,
            "job_info": {
                "company": raw.company,
                "title": raw.title,
                "location": raw.location,
                "country": raw.country,
                "published_at": raw_pub,
                "freshness_bucket": bucket.value,
                "age_hours": age_hours,
                "score": score_8d.total_score,
                "category": score_8d.category.value,
                "is_fresh_24h_match": score_8d.is_fresh_24h_match,
                "is_watchlist": is_watched,
            },
        }
