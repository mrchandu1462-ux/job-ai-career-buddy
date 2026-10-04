"""Phase 3 — Continuous 24-Hour Job Monitor Daemon.

Runs FreshJobScanner on a configurable interval (default: 60 minutes), persists
cycle state to the SQLite ``monitor_state`` table, and shuts down gracefully on
SIGINT / SIGTERM.

Usage:
    # Run once, then exit
    python -m app.jobs.scheduler --once

    # Run continuously every 60 minutes (default)
    python -m app.jobs.scheduler

    # Run every 60 minutes, India only
    python -m app.jobs.scheduler --interval 60 --region india

    # Dry-run continuous loop (no database writes)
    python -m app.jobs.scheduler --dry-run
"""

import argparse
import logging
import os
import signal
import sqlite3
import sys
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from app.config import get_settings
from app.db.connection import get_connection
from app.db.repository import JobRepository
from app.db.schema import create_schema
from app.jobs.digest import DailyDigestService
from app.jobs.scanner import FreshJobScanner, ScanReport
from app.notifications.service import EmailNotificationService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Default scan interval in minutes.
DEFAULT_INTERVAL_MINUTES: int = 60

#: Freshness window passed to the scanner on every cycle (hours).
SCAN_WINDOW_HOURS: float = 24.0

#: Minimum 8-D priority score for notification proposals.
SCAN_MIN_SCORE: float = 60.0

#: Maximum jobs to inspect per source adapter per cycle.
SCAN_LIMIT: int = 100

#: Lock key used in scanner_locks table (reused from scanner.py).
LOCK_NAME: str = "fresh_job_scanner"


# ---------------------------------------------------------------------------
# ScannerDaemon
# ---------------------------------------------------------------------------


class ScannerDaemon:
    """
    Continuous job-monitoring daemon.

    Invariants
    ----------
    - Never submits an application autonomously.
    - Never fabricates candidate or job data.
    - Persists all cycle state to ``monitor_state`` in SQLite.
    - Releases the scanner lock on every exit path.
    - Responds to SIGINT / SIGTERM with a clean, graceful shutdown.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        interval_minutes: int = DEFAULT_INTERVAL_MINUTES,
        region: str = "all",
        hours: float = SCAN_WINDOW_HOURS,
        min_score: float = SCAN_MIN_SCORE,
        limit: int = SCAN_LIMIT,
        dry_run: bool = False,
        scanner: FreshJobScanner | None = None,
        alert_mode: str = "HIGH_AND_CRITICAL",
        company_filter: str | None = None,
        role_filter: str | None = None,
    ) -> None:
        if interval_minutes < 1:
            raise ValueError("interval_minutes must be >= 1.")
        if region not in ("all", "india", "overseas"):
            raise ValueError(f"region must be 'all', 'india', or 'overseas', got: {region!r}")

        self.conn = conn
        self.interval_minutes = interval_minutes
        self.region = region
        self.hours = hours
        self.min_score = min_score
        self.limit = limit
        self.dry_run = dry_run
        self.alert_mode = alert_mode
        self.company_filter = company_filter
        self.role_filter = role_filter
        self.repo = JobRepository(conn)

        # Allow injection for tests; default builds production scanner.
        self._scanner = scanner

        self._shutdown_requested: bool = False
        self._cycles_completed: int = 0
        self._cycles_failed: int = 0
        self._consecutive_failures: int = 0
        self._last_successful_scan_at: str | None = None
        self._last_failed_scan_at: str | None = None
        self._last_error: str | None = None
        self._last_report: ScanReport | None = None

    # ------------------------------------------------------------------
    # Signal handling
    # ------------------------------------------------------------------

    def _install_signal_handlers(self) -> None:
        """Register SIGINT and SIGTERM handlers for graceful shutdown."""
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, self._handle_signal)
            except (OSError, ValueError):
                # Can happen if running in non-main thread context during tests.
                pass

    def _handle_signal(self, signum: int, _frame: object) -> None:
        logger.info("Received signal %d — requesting graceful shutdown.", signum)
        self._shutdown_requested = True

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def _save_state(
        self,
        *,
        running: bool,
        cycle_started_at: str | None = None,
        cycle_completed_at: str | None = None,
        last_cycle_at: str | None = None,
        next_cycle_at: str | None = None,
    ) -> None:
        """Persist daemon bookkeeping to monitor_state."""
        if self.dry_run:
            return  # No writes in dry-run mode.
        try:
            self.repo.set_monitor_state_value("scheduler_running", "true" if running else "false")
            self.repo.set_monitor_state_value("daemon_pid", str(os.getpid()))
            self.repo.set_monitor_state_value("interval_minutes", str(self.interval_minutes))
            self.repo.set_monitor_state_value("scheduler_region", self.region)
            self.repo.set_monitor_state_value("cycles_completed", str(self._cycles_completed))
            self.repo.set_monitor_state_value("cycles_failed", str(self._cycles_failed))
            self.repo.set_monitor_state_value("consecutive_failures", str(self._consecutive_failures))

            effective_last = cycle_completed_at or last_cycle_at
            if effective_last is not None:
                self.repo.set_monitor_state_value("last_cycle_at", effective_last)
                self.repo.set_monitor_state_value("last_cycle_completed_at", effective_last)
            if cycle_started_at is not None:
                self.repo.set_monitor_state_value("last_cycle_started_at", cycle_started_at)
            if next_cycle_at is not None:
                self.repo.set_monitor_state_value("next_cycle_at", next_cycle_at)
            if self._last_successful_scan_at is not None:
                self.repo.set_monitor_state_value("last_successful_scan_at", self._last_successful_scan_at)
            if self._last_failed_scan_at is not None:
                self.repo.set_monitor_state_value("last_failed_scan_at", self._last_failed_scan_at)
            if self._last_error is not None:
                self.repo.set_monitor_state_value("last_error", self._last_error)

            if self._last_report is not None:
                self.repo.set_monitor_state_value("last_jobs_discovered", str(self._last_report.jobs_discovered))
                self.repo.set_monitor_state_value("last_fresh_24h", str(self._last_report.fresh_24h))
                self.repo.set_monitor_state_value("last_india_count", str(self._last_report.india_count))
                self.repo.set_monitor_state_value("last_overseas_count", str(self._last_report.overseas_count))
                self.repo.set_monitor_state_value("last_high_matches", str(self._last_report.high_matches))
                self.repo.set_monitor_state_value("last_critical_matches", str(self._last_report.critical_matches))
                self.repo.set_monitor_state_value("last_notifications_proposed", str(self._last_report.notifications_proposed))
        except sqlite3.Error as exc:
            logger.warning("Could not persist daemon state: %s", exc)

    def _check_and_send_daily_digest(self) -> None:
        """Evaluate whether to generate and dispatch the scheduled daily career digest."""
        settings = get_settings()
        if not settings.digest_enabled:
            return

        now_local = datetime.now().astimezone()
        current_hour = now_local.hour
        today_date = now_local.strftime("%Y-%m-%d")

        if current_hour == settings.digest_hour:
            state_key = f"daily_digest_sent_{today_date}"
            already_sent = self.repo.get_monitor_state_value(state_key)
            if not already_sent:
                logger.info("Triggering scheduled daily career digest for %s (hour: %d)", today_date, current_hour)
                try:
                    digest_svc = DailyDigestService(self.conn)
                    digest = digest_svc.generate_daily_digest(hours=24.0, top_n=5)
                    email_svc = EmailNotificationService(self.conn, settings)
                    res = email_svc.send_daily_digest(digest, dry_run=self.dry_run)
                    if res.success:
                        self.repo.set_monitor_state_value(state_key, datetime.now(UTC).isoformat())
                        logger.info("Daily digest email successfully recorded for %s", today_date)
                except (sqlite3.Error, ValueError, KeyError, RuntimeError, TypeError, OSError) as exc:
                    logger.warning("Daily digest dispatch skipped/failed safely: %s", exc)

    # ------------------------------------------------------------------
    # Scanner construction
    # ------------------------------------------------------------------

    def _get_scanner(self) -> FreshJobScanner:
        """Return the injected scanner or build a fresh production instance."""
        if self._scanner is not None:
            return self._scanner
        return FreshJobScanner(conn=self.conn)

    # ------------------------------------------------------------------
    # Core: single cycle
    # ------------------------------------------------------------------

    def run_once(self) -> ScanReport:
        """
        Execute exactly one scan cycle and return the ScanReport.

        Raises
        ------
        RuntimeError
            If the scanner lock is already held (overlapping execution).
        """
        scanner = self._get_scanner()
        kwargs: dict[str, Any] = {
            "region": self.region,
            "hours": self.hours,
            "dry_run": self.dry_run,
            "min_score": self.min_score,
            "limit": self.limit,
        }
        if self.alert_mode != "HIGH_AND_CRITICAL":
            kwargs["alert_mode"] = self.alert_mode
        if self.company_filter is not None:
            kwargs["company_filter"] = self.company_filter
        if self.role_filter is not None:
            kwargs["role_filter"] = self.role_filter

        return scanner.scan(**kwargs)

    # ------------------------------------------------------------------
    # Core: continuous loop
    # ------------------------------------------------------------------

    def run(self) -> int:
        """
        Start the continuous monitoring loop.

        Returns
        -------
        int
            0 on clean shutdown, 1 on unrecoverable startup error.
        """
        self._install_signal_handlers()
        self._save_state(running=True)

        logger.info(
            "ScannerDaemon started | region=%s | interval=%dm | hours=%.1fh | dry_run=%s | pid=%d",
            self.region,
            self.interval_minutes,
            self.hours,
            self.dry_run,
            os.getpid(),
        )

        try:
            while not self._shutdown_requested:
                cycle_start = datetime.now(UTC)
                cycle_iso = cycle_start.isoformat()

                logger.info("Cycle #%d starting at %s", self._cycles_completed + 1, cycle_iso)
                _print_cycle_banner(self._cycles_completed + 1, self.region, self.dry_run)

                try:
                    report = self.run_once()
                    self._cycles_completed += 1
                    self._consecutive_failures = 0
                    self._last_successful_scan_at = datetime.now(UTC).isoformat()
                    self._last_report = report
                    self._last_error = None
                    _print_cycle_report(report)

                    # Scheduled Daily Digest check
                    self._check_and_send_daily_digest()

                except RuntimeError as exc:
                    # Scanner lock already held — skip cycle, do not count as failure.
                    logger.warning("Cycle skipped — lock contention: %s", exc)
                    print(f"\n[WARN] Cycle skipped: {exc}")
                except Exception as exc:
                    self._cycles_failed += 1
                    self._consecutive_failures += 1
                    self._last_failed_scan_at = datetime.now(UTC).isoformat()
                    self._last_error = str(exc)
                    logger.exception("Cycle #%d failed", self._cycles_completed + 1)
                    print(f"\n[ERROR] Cycle failed: {exc}")

                cycle_complete_iso = datetime.now(UTC).isoformat()
                next_cycle_dt = cycle_start + timedelta(minutes=self.interval_minutes)
                next_cycle_iso = next_cycle_dt.isoformat()
                self._save_state(
                    running=True,
                    cycle_started_at=cycle_iso,
                    cycle_completed_at=cycle_complete_iso,
                    next_cycle_at=next_cycle_iso,
                )

                logger.info(
                    "Next cycle scheduled for %s (in %dm).",
                    next_cycle_iso,
                    self.interval_minutes,
                )

                # Sleep in 1-second ticks so we respond to signals promptly.
                sleep_seconds = self.interval_minutes * 60
                for _ in range(sleep_seconds):
                    if self._shutdown_requested:
                        break
                    time.sleep(1)

        finally:
            self._save_state(running=False)
            logger.info(
                "ScannerDaemon stopped | cycles_ok=%d | cycles_failed=%d",
                self._cycles_completed,
                self._cycles_failed,
            )
            print(
                f"\n[INFO] Scheduler stopped. "
                f"Completed {self._cycles_completed} cycles, {self._cycles_failed} failed."
            )

        return 0


# ---------------------------------------------------------------------------
# Printing helpers (no business logic — purely presentation)
# ---------------------------------------------------------------------------


def _print_cycle_banner(cycle_num: int, region: str, dry_run: bool) -> None:
    mode = "[DRY RUN]" if dry_run else "[LIVE]"
    now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    print("\n" + "=" * 70)
    print(f"JOB-AI CAREER BUDDY  |  SCHEDULER CYCLE #{cycle_num}  {mode}")
    print(f"Region: {region.upper()}  |  {now_str}")
    print("=" * 70)


def _print_cycle_report(report: ScanReport) -> None:
    print(f"  Sources  : {report.sources_successful}/{report.sources_total} healthy")
    print(f"  Scanned  : {report.jobs_scanned}  Discovered: {report.jobs_discovered}  New: {report.new_jobs}")
    print(f"  Fresh 24h: {report.fresh_24h}  India: {report.india_count}  Overseas: {report.overseas_count}")
    print(f"  Critical : {report.critical_matches}  High: {report.high_matches}  Notified: {report.notifications_proposed}")
    print(f"  Duration : {report.duration_ms:.1f} ms")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="job-ai-scheduler",
        description=(
            "Phase 3 — Job-AI continuous 24-hour monitor daemon.\n"
            "Runs FreshJobScanner on a configurable interval and surfaces "
            "human-gated opportunity alerts."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Execute a single scan cycle, then exit.",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_INTERVAL_MINUTES,
        metavar="MINUTES",
        help=f"Minutes between scan cycles when running continuously (default: {DEFAULT_INTERVAL_MINUTES}).",
    )
    parser.add_argument(
        "--region",
        type=str,
        default="all",
        choices=["all", "india", "overseas"],
        help="Geographic focus (default: all).",
    )
    parser.add_argument(
        "--hours",
        type=float,
        default=SCAN_WINDOW_HOURS,
        help=f"Freshness window in hours (default: {SCAN_WINDOW_HOURS}).",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=SCAN_MIN_SCORE,
        help=f"Minimum 8-D priority score for notifications (default: {SCAN_MIN_SCORE}).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=SCAN_LIMIT,
        help=f"Maximum jobs to fetch per adapter (default: {SCAN_LIMIT}).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Execute cycles without writing to the database or creating notifications.",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=None,
        help="Optional custom SQLite database path.",
    )
    return parser.parse_args()


def main() -> int:
    """CLI entrypoint: ``python -m app.jobs.scheduler``."""
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    args = _parse_args()

    if args.interval < 1:
        print("[ERROR] --interval must be >= 1 minute.", file=sys.stderr)
        return 2

    conn = get_connection(db_path=args.db_path, auto_init=True)
    try:
        create_schema(conn)
    except (sqlite3.Error, OSError) as exc:
        logger.warning("Schema init warning (non-fatal): %s", exc)

    try:
        daemon = ScannerDaemon(
            conn=conn,
            interval_minutes=args.interval,
            region=args.region,
            hours=args.hours,
            min_score=args.min_score,
            limit=args.limit,
            dry_run=args.dry_run,
        )

        if args.once:
            print("\n" + "=" * 70)
            print("JOB-AI CAREER BUDDY  |  SINGLE-SHOT SCAN")
            print(f"Region: {args.region.upper()}  |  {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}")
            print("=" * 70)
            try:
                report = daemon.run_once()
                _print_cycle_report(report)
                print("\n[OK] Single scan complete.")
                return 0
            except RuntimeError as exc:
                print(f"\n[LOCKED] {exc}", file=sys.stderr)
                return 1
        else:
            print(
                f"\n[INFO] Starting continuous scheduler | interval={args.interval}m | "
                f"region={args.region} | hours={args.hours}h | dry_run={args.dry_run}"
            )
            print("[INFO] Press Ctrl+C to stop.\n")
            return daemon.run()
    finally:
        try:
            conn.close()
        except (sqlite3.Error, OSError) as close_exc:
            logger.debug("Database close suppressed: %s", close_exc)



if __name__ == "__main__":
    sys.exit(main())
