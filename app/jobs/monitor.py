"""CLI entrypoint for 24-Hour Job Monitoring Engine (Phase 3).

Usage:
    # Single-shot scan (default: 24h freshness, all regions)
    python -m app.jobs.monitor --once --region all --hours 24

    # Run continuous monitoring every 60 minutes
    python -m app.jobs.monitor --region all --hours 24 --interval 60

    # Run continuous monitoring for India semiconductor hubs
    python -m app.jobs.monitor --region india --hours 24 --interval 60

    # Dry-run mode without database persistence
    python -m app.jobs.monitor --once --dry-run
"""

import argparse
import logging
import sqlite3
import sys
from datetime import UTC, datetime

from app.db.connection import get_connection
from app.db.schema import create_schema
from app.jobs.scheduler import (
    DEFAULT_INTERVAL_MINUTES,
    SCAN_LIMIT,
    SCAN_MIN_SCORE,
    SCAN_WINDOW_HOURS,
    ScannerDaemon,
    _print_cycle_report,
)

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="job-ai-monitor",
        description="Phase 3 — Continuous 24-Hour Fresh Job Monitor & Scheduler.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Execute exactly one scan cycle, then exit.",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=None,
        metavar="MINUTES",
        help=f"Minutes between scan cycles when running continuously (e.g. {DEFAULT_INTERVAL_MINUTES}). If omitted, executes a single cycle.",
    )
    parser.add_argument(
        "--region",
        type=str,
        default="all",
        choices=["all", "india", "overseas"],
        help="Geographic focus region (default: all).",
    )
    parser.add_argument(
        "--hours",
        type=float,
        default=SCAN_WINDOW_HOURS,
        help=f"Freshness window in hours (default: {SCAN_WINDOW_HOURS}).",
    )
    parser.add_argument(
        "--fresh-only",
        action="store_true",
        help="Only process and alert on jobs published strictly within <= 24 hours.",
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
        "--alert-mode",
        type=str,
        default="HIGH_AND_CRITICAL",
        choices=["CRITICAL_ONLY", "HIGH_AND_CRITICAL", "ALL_MATCHED", "WATCHLIST_COMPANIES", "DAILY_DIGEST", "HOURLY_CRITICAL"],
        help="Alert filtering mode (default: HIGH_AND_CRITICAL).",
    )
    parser.add_argument(
        "--company",
        type=str,
        default=None,
        help="Optional company filter string (e.g. Qualcomm, NVIDIA).",
    )
    parser.add_argument(
        "--role",
        type=str,
        default=None,
        help="Optional role title filter string (e.g. 'Design Verification').",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Execute cycle without persisting jobs or creating notifications.",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=None,
        help="Optional custom SQLite database path.",
    )
    return parser.parse_args()


def main() -> int:
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

    args = parse_args()

    if args.interval is not None and args.interval < 1:
        print("[ERROR] --interval must be >= 1 minute.", file=sys.stderr)
        return 2

    effective_interval = args.interval or DEFAULT_INTERVAL_MINUTES
    effective_hours = 24.0 if args.fresh_only else args.hours

    conn = get_connection(db_path=args.db_path, auto_init=True)
    try:
        create_schema(conn)
    except (sqlite3.Error, OSError) as exc:
        logger.warning("Schema init warning (non-fatal): %s", exc)

    try:
        daemon = ScannerDaemon(
            conn=conn,
            interval_minutes=effective_interval,
            region=args.region,
            hours=effective_hours,
            min_score=args.min_score,
            limit=args.limit,
            dry_run=args.dry_run,
            alert_mode=args.alert_mode,
            company_filter=args.company,
            role_filter=args.role,
        )

        is_single_shot = args.once or (args.interval is None)

        if is_single_shot:
            print("\n" + "=" * 70)
            print("JOB-AI CAREER BUDDY  |  SINGLE-SHOT SCAN")
            print(f"Region: {args.region.upper()} | Freshness Window: <={effective_hours}h | {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}")
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
                f"\n[INFO] Starting continuous scheduler | interval={effective_interval}m | "
                f"region={args.region} | hours={effective_hours}h | dry_run={args.dry_run}"
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
