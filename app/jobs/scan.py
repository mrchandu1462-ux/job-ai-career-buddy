"""CLI Command: python -m app.jobs.scan

Runs the production FreshJobScanner across India and Overseas sources,
calculates 24-hour freshness, scores 8D match priority, and surfaces human-gated notifications.
"""

import argparse
import sys
from datetime import UTC, datetime

from app.db.connection import get_db_connection
from app.jobs.scanner import FreshJobScanner


def main() -> int:
    # Ensure Windows console handles UTF-8 safely
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        description="Fresh Job Scanner — 24-Hour Semiconductor Job Intelligence Engine"
    )
    parser.add_argument(
        "--region",
        type=str,
        default="all",
        choices=["all", "india", "overseas"],
        help="Geographic target market (all, india, overseas)",
    )
    parser.add_argument(
        "--hours",
        type=float,
        default=24.0,
        help="Freshness window in hours (default: 24.0)",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=60.0,
        help="Minimum 8D priority score threshold for notification proposal (default: 60.0)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Execute scan in dry-run mode without writing to SQLite database",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum jobs to inspect per source adapter",
    )

    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("⚡ JOB-AI CAREER BUDDY — 24-HOUR FRESH JOB SCANNER")
    print(f"Target Region : {args.region.upper()}")
    print(f"Freshness Window: <= {args.hours:.0f} Hours")
    print(f"Dry Run Mode  : {'ENABLED' if args.dry_run else 'DISABLED'}")
    print(f"Timestamp     : {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("=" * 60 + "\n")

    conn = get_db_connection()
    try:
        scanner = FreshJobScanner(conn=conn)

        try:
            report = scanner.scan(
                region=args.region,
                hours=args.hours,
                dry_run=args.dry_run,
                min_score=args.min_score,
                limit=args.limit,
            )
        except RuntimeError as e:
            print("=" * 60)
            print(f"🔒 SCANNER LOCKED: {e}")
            print("Another active scanner instance is currently holding the lock. Scan aborted.")
            print("=" * 60 + "\n")
            return 1
    finally:
        conn.close()

    print("=" * 60)
    print("JOB SCAN COMPLETE")
    print("=" * 60)
    print(f"Sources Total         : {report.sources_total}")
    print(f"Sources Healthy       : {report.sources_successful}")
    print(f"Sources Failed        : {report.sources_failed}")
    print(f"Jobs Scanned          : {report.jobs_scanned}")
    print(f"Jobs Discovered       : {report.jobs_discovered}")
    print(f"New Jobs Ingested     : {report.new_jobs}")
    print(f"Fresh <=24h           : {report.fresh_24h}")
    print(f"India Listings        : {report.india_count}")
    print(f"Overseas Listings     : {report.overseas_count}")
    print(f"🔥 Critical Matches    : {report.critical_matches}")
    print(f"🟢 High Matches       : {report.high_matches}")
    print(f"Duplicates Deduplicated: {report.duplicates_removed}")
    print(f"Notifications Proposed: {report.notifications_proposed}")
    print(f"Scan Duration         : {report.duration_ms:.1f}ms")
    print("=" * 60)

    if report.discovered_jobs:
        print("\nTOP DISCOVERED OPPORTUNITIES:")
        for idx, job in enumerate(report.discovered_jobs[:5], start=1):
            badge = "🔥 [CRITICAL]" if job.get("category") == "CRITICAL" else ("🟢 [HIGH]" if job.get("category") == "HIGH" else "🟡 [MATCH]")
            age_str = f"{job.get('age_hours', 0):.1f}h old" if job.get("age_hours") is not None else "Verified fresh"
            wl_str = " ⭐[WATCHLIST]" if job.get("is_watchlist") else ""
            print(f" {idx}. {badge} {job['title']} — {job['company']}{wl_str}")
            print(f"    Score: {job['score']:.0f}/100 | Age: {age_str} | Loc: {job.get('location') or 'India'}")

    print("\n[Audit Rule] No automated external submissions permitted. Review proposals in Streamlit dashboard.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
