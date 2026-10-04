"""Email Notification Service for Job-AI Career Buddy.

Coordinates priority decision logic, freshness validation, deterministic
deduplication, email rendering, delivery audit logging, and human safety boundaries.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from app.config import AppSettings, get_settings
from app.db.models import ApplicationStatus, DeliveryStatus, EmailDeliveryRecord
from app.db.repository import JobRepository
from app.notifications.email import BaseEmailProvider, get_email_provider
from app.notifications.models import DeliveryResult
from app.notifications.renderer import EmailTemplateRenderer

if TYPE_CHECKING:
    from app.application.intelligence import ApplicationPackage
    from app.jobs.digest import DailyCareerDigest

logger = logging.getLogger(__name__)


class EmailNotificationService:
    """High-level service managing automated career alert emails and daily digests."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        settings: AppSettings | None = None,
        provider: BaseEmailProvider | None = None,
        repo: JobRepository | None = None,
    ):
        self.conn = conn
        self.settings = settings or get_settings()
        self.repo = repo or JobRepository(conn)
        self.provider = provider or get_email_provider(self.settings)
        self.renderer = EmailTemplateRenderer(dashboard_base_url=self.settings.dashboard_url)

    def process_immediate_alerts(
        self,
        packages: list[ApplicationPackage],
        dry_run: bool = False,
    ) -> list[DeliveryResult]:
        """
        Process a list of application packages and dispatch immediate alerts for qualifying jobs.

        Priority Policy:
        - 90-100 (CRITICAL): Send immediately.
        - 80-89 (HIGH): Send immediately.
        - 70-79 (APPLY): Suppress from immediate email (routed to daily digest).
        - 60-69 (WATCH): Suppress from immediate email.
        - <60 (SKIP): Suppress.

        Long-Term Deduplication & Safety:
        - Checks if fingerprint has already been successfully delivered across historical days/hours.
        - Suppresses duplicate sends across hourly scans and multi-day rediscoveries (>72h cooldown).
        - Does NOT automatically re-alert merely because time elapsed if job is unchanged.
        - Suppresses notifications if an application has already been submitted by the candidate.
        - Allows re-notification ONLY on genuine material job updates.
        """
        results: list[DeliveryResult] = []
        now_iso = datetime.now(UTC).isoformat()

        for pkg in packages:
            # 1. Eligibility & Priority Gating
            p_level_raw = getattr(pkg, "priority_tier", getattr(pkg, "priority_level", "HIGH"))
            p_level = p_level_raw.value.upper() if hasattr(p_level_raw, "value") else str(p_level_raw).upper()
            if p_level not in ("CRITICAL", "HIGH") and pkg.priority_score < 80.0:
                continue

            # 2. Freshness Gating (immediate alerts require verified <=24h freshness)
            # Ineligible / senior jobs clamped to SKIP are already filtered out
            if p_level == "SKIP":
                continue

            pkg_fp = getattr(pkg, "job_fingerprint", getattr(pkg, "fingerprint", f"fp_{pkg.job_id}"))
            existing_delivery = self.repo.get_email_delivery_by_fingerprint(pkg_fp)
            is_material_update = bool(getattr(pkg, "is_material_update", False))

            # 3. Application-Submitted Suppression Check
            # If candidate has already submitted an application for this opportunity,
            # suppress repeated notifications unless there is an explicit material update.
            app_status = getattr(pkg, "application_status", None)
            is_already_submitted = False
            submitted_statuses = {"applied", "submitted", "submitted_manually", "offer", "interviewing", "accepted"}
            if app_status == ApplicationStatus.APPLIED or (
                isinstance(app_status, (str, ApplicationStatus))
                and str(getattr(app_status, "value", app_status)).lower() in submitted_statuses
            ):
                is_already_submitted = True
            elif getattr(pkg, "job_id", None):
                db_app = self.repo.get_application_by_job_id(pkg.job_id)
                if db_app and (
                    db_app.status == ApplicationStatus.APPLIED
                    or (
                        isinstance(db_app.status, (str, ApplicationStatus))
                        and str(getattr(db_app.status, "value", db_app.status)).lower() in submitted_statuses
                    )
                ):
                    is_already_submitted = True

            if not is_already_submitted and pkg_fp:
                norm = self.repo.get_normalized_job_by_fingerprint(pkg_fp)
                if norm and norm.id:
                    db_app = self.repo.get_application_by_job_id(norm.id)
                    if db_app and (
                        db_app.status == ApplicationStatus.APPLIED
                        or (
                            isinstance(db_app.status, (str, ApplicationStatus))
                            and str(getattr(db_app.status, "value", db_app.status)).lower() in submitted_statuses
                        )
                    ):
                        is_already_submitted = True

            if is_already_submitted and not is_material_update:
                logger.info(
                    "Suppressing notification for job %s (%s) - application already submitted",
                    pkg.job_id,
                    pkg_fp,
                )
                suppressed_record = EmailDeliveryRecord(
                    notification_id=None,
                    job_id=pkg.job_id,
                    application_id=getattr(pkg, "application_id", None),
                    recipient=self.settings.email_to,
                    priority=p_level,
                    subject=f"Suppressed (Already Submitted): {pkg.role} at {pkg.company}",
                    delivery_status=DeliveryStatus.SUPPRESSED,
                    provider=self.settings.email_provider,
                    attempt_count=0,
                    created_at=now_iso,
                    fingerprint=pkg_fp,
                )
                try:
                    self.repo.create_email_delivery(suppressed_record)
                except sqlite3.Error as exc:
                    logger.debug("Could not record suppressed delivery: %s", exc)

                results.append(
                    DeliveryResult(
                        success=True,
                        provider=self.settings.email_provider,
                        status=DeliveryStatus.SUPPRESSED,
                        timestamp=now_iso,
                        dry_run=dry_run,
                        metadata={"reason": "application_already_submitted", "fingerprint": pkg_fp},
                    )
                )
                continue

            # 4. Long-Term Multi-Day Delivery Suppression Check
            if existing_delivery and existing_delivery.delivery_status in (DeliveryStatus.SENT, DeliveryStatus.SUPPRESSED):
                if is_material_update:
                    logger.info("Material update detected for job %s (%s) - re-alerting", pkg.job_id, pkg_fp)
                else:
                    # Suppress duplicate send across hourly scans and multi-day rediscoveries
                    logger.debug("Suppressing duplicate email for job %s (%s)", pkg.job_id, pkg_fp)
                    suppressed_record = EmailDeliveryRecord(
                        notification_id=None,
                        job_id=pkg.job_id,
                        application_id=getattr(pkg, "application_id", None),
                        recipient=self.settings.email_to,
                        priority=p_level,
                        subject=f"Suppressed duplicate: {pkg.role} at {pkg.company}",
                        delivery_status=DeliveryStatus.SUPPRESSED,
                        provider=self.settings.email_provider,
                        attempt_count=0,
                        created_at=now_iso,
                        fingerprint=pkg_fp,
                    )
                    try:
                        self.repo.create_email_delivery(suppressed_record)
                    except sqlite3.Error as exc:
                        logger.debug("Could not record suppressed delivery: %s", exc)

                    results.append(
                        DeliveryResult(
                            success=True,
                            provider=self.settings.email_provider,
                            status=DeliveryStatus.SUPPRESSED,
                            timestamp=now_iso,
                            dry_run=dry_run,
                            metadata={"reason": "duplicate_suppressed", "fingerprint": pkg_fp},
                        )
                    )
                    continue

            # 4. Render Email Message
            msg = self.renderer.render_immediate_alert(
                package=pkg,
                recipient=self.settings.email_to,
                sender=self.settings.email_from,
                is_material_update=is_material_update,
            )

            # 5. Persist Initial Queued Delivery Record
            delivery_record = EmailDeliveryRecord(
                notification_id=None,
                job_id=pkg.job_id,
                application_id=getattr(pkg, "application_id", None),
                recipient=msg.recipient,
                priority=p_level,
                subject=msg.subject,
                delivery_status=DeliveryStatus.QUEUED,
                provider=self.settings.email_provider,
                attempt_count=0,
                created_at=now_iso,
                queued_at=now_iso,
                fingerprint=pkg_fp,
            )


            delivery_id: int | None = None
            try:
                delivery_id = self.repo.create_email_delivery(delivery_record)
            except sqlite3.Error as exc:
                logger.warning("Could not persist initial email delivery record: %s", exc)

            # 6. Dispatch via Provider
            try:
                res = self.provider.send_message(msg, dry_run=dry_run)
                if delivery_id:
                    self.repo.update_email_delivery_status(
                        delivery_id=delivery_id,
                        status=res.status,
                        sent_at=res.timestamp if res.success else None,
                        failed_at=res.timestamp if not res.success else None,
                        last_error=res.error_message,
                        provider_message_id=res.provider_message_id,
                        attempt_increment=res.attempts,
                    )
                results.append(res)
            except (sqlite3.Error, ValueError, KeyError, RuntimeError, TypeError, OSError) as exc:
                logger.exception("Unexpected error sending email alert")
                if delivery_id:
                    self.repo.update_email_delivery_status(
                        delivery_id=delivery_id,
                        status=DeliveryStatus.FAILED,
                        failed_at=datetime.now(UTC).isoformat(),
                        last_error=str(exc),
                        attempt_increment=1,
                    )
                results.append(
                    DeliveryResult(
                        success=False,
                        provider=self.settings.email_provider,
                        status=DeliveryStatus.FAILED,
                        error_message=str(exc),
                        timestamp=datetime.now(UTC).isoformat(),
                        dry_run=dry_run,
                    )
                )

        return results

    def send_daily_digest(
        self,
        digest: DailyCareerDigest,
        dry_run: bool = False,
    ) -> DeliveryResult:
        """
        Send the daily career intelligence digest summarizing lower priority (APPLY/WATCH)
        and fresh opportunities discovered in the last 24 hours.
        """
        now_iso = datetime.now(UTC).isoformat()
        digest_fingerprint = f"digest_{digest.digest_date}"

        # Deduplicate digest per date
        existing = self.repo.get_email_delivery_by_fingerprint(digest_fingerprint)
        if existing and existing.delivery_status == DeliveryStatus.SENT and not dry_run:
            logger.info("Daily digest for %s already sent. Suppressing duplicate.", digest.digest_date)
            return DeliveryResult(
                success=True,
                provider=self.settings.email_provider,
                status=DeliveryStatus.SUPPRESSED,
                timestamp=now_iso,
                dry_run=dry_run,
                metadata={"reason": "digest_already_sent", "date": digest.digest_date},
            )

        msg = self.renderer.render_daily_digest(
            digest=digest,
            recipient=self.settings.email_to,
            sender=self.settings.email_from,
        )

        delivery_record = EmailDeliveryRecord(
            notification_id=None,
            job_id=None,
            application_id=None,
            recipient=msg.recipient,
            priority="DIGEST",
            subject=msg.subject,
            delivery_status=DeliveryStatus.QUEUED,
            provider=self.settings.email_provider,
            attempt_count=0,
            created_at=now_iso,
            queued_at=now_iso,
            fingerprint=digest_fingerprint,
        )

        delivery_id: int | None = None
        try:
            delivery_id = self.repo.create_email_delivery(delivery_record)
        except sqlite3.Error as exc:
            logger.warning("Could not persist digest delivery record: %s", exc)

        try:
            res = self.provider.send_message(msg, dry_run=dry_run)
            if delivery_id:
                self.repo.update_email_delivery_status(
                    delivery_id=delivery_id,
                    status=res.status,
                    sent_at=res.timestamp if res.success else None,
                    failed_at=res.timestamp if not res.success else None,
                    last_error=res.error_message,
                    provider_message_id=res.provider_message_id,
                    attempt_increment=res.attempts,
                )
            return res
        except (sqlite3.Error, ValueError, KeyError, RuntimeError, TypeError, OSError) as exc:
            logger.exception("Failed to send daily digest email")
            if delivery_id:
                self.repo.update_email_delivery_status(
                    delivery_id=delivery_id,
                    status=DeliveryStatus.FAILED,
                    failed_at=datetime.now(UTC).isoformat(),
                    last_error=str(exc),
                    attempt_increment=1,
                )
            return DeliveryResult(
                success=False,
                provider=self.settings.email_provider,
                status=DeliveryStatus.FAILED,
                error_message=str(exc),
                timestamp=datetime.now(UTC).isoformat(),
                dry_run=dry_run,
            )

    def send_test_email(
        self,
        recipient: str | None = None,
        dry_run: bool = False,
    ) -> DeliveryResult:
        """Send a single explicit verification test email."""
        target_to = recipient or self.settings.email_to
        now_iso = datetime.now(UTC).isoformat()

        msg = self.renderer.render_test_email(
            recipient=target_to,
            sender=self.settings.email_from,
        )

        delivery_record = EmailDeliveryRecord(
            notification_id=None,
            job_id=None,
            application_id=None,
            recipient=target_to,
            priority="TEST",
            subject=msg.subject,
            delivery_status=DeliveryStatus.QUEUED,
            provider=self.settings.email_provider,
            attempt_count=0,
            created_at=now_iso,
            queued_at=now_iso,
            fingerprint=f"test_{int(datetime.now(UTC).timestamp())}",
        )

        delivery_id: int | None = None
        try:
            delivery_id = self.repo.create_email_delivery(delivery_record)
        except sqlite3.Error:
            pass

        try:
            res = self.provider.send_message(msg, dry_run=dry_run)
            if delivery_id:
                self.repo.update_email_delivery_status(
                    delivery_id=delivery_id,
                    status=res.status,
                    sent_at=res.timestamp if res.success else None,
                    failed_at=res.timestamp if not res.success else None,
                    last_error=res.error_message,
                    provider_message_id=res.provider_message_id,
                    attempt_increment=res.attempts,
                )
            return res
        except (sqlite3.Error, ValueError, KeyError, RuntimeError, TypeError, OSError) as exc:
            if delivery_id:
                self.repo.update_email_delivery_status(
                    delivery_id=delivery_id,
                    status=DeliveryStatus.FAILED,
                    failed_at=datetime.now(UTC).isoformat(),
                    last_error=str(exc),
                    attempt_increment=1,
                )
            return DeliveryResult(
                success=False,
                provider=self.settings.email_provider,
                status=DeliveryStatus.FAILED,
                error_message=str(exc),
                timestamp=datetime.now(UTC).isoformat(),
                dry_run=dry_run,
            )

    def get_delivery_stats(self) -> dict[str, Any]:
        """Fetch email delivery statistics from the repository."""
        return self.repo.get_email_delivery_stats()

    def list_recent_deliveries(self, limit: int = 50) -> list[EmailDeliveryRecord]:
        """Fetch list of recent email delivery audit records."""
        return self.repo.list_email_deliveries(limit=limit)
