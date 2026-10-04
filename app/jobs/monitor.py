"""CLI and Automation Entrypoint for Fresh Job Monitoring Engine (Phase 5).

Usage:
    python -m app.jobs.monitor
    python -m app.jobs.monitor --region india
    python -m app.jobs.monitor --region overseas
    python -m app.jobs.monitor --fresh-only
    python -m app.jobs.monitor --dry-run
    python -m app.jobs.monitor --limit 20
"""

import argparse
import sys

from app.db.connection import get_connection
from app.jobs.monitoring_service import FreshJobMonitoringService
from app.profile.loader import load_candidate_profile, load_fact_bank


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="job-ai-monitor",
        description="Fresh Job Monitoring & Alert Engine for VLSI / Semiconductor Opportunities.",
    )
    parser.add_argument(
        "--region",
        type=str,
        choices=["all", "india", "overseas"],
        default="all",
        help="Geographic focus region (default: all).",
    )
    parser.add_argument(
        "--fresh-only",
        action="store_true",
        help="Only process and alert on jobs published strictly within <= 24 hours.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Execute monitoring cycle without persisting jobs or creating notifications.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum jobs to fetch per adapter (default: 50).",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=None,
        help="Optional custom SQLite database path.",
    )
    return parser.parse_args()


def print_banner(dry_run: bool, region: str, fresh_only: bool) -> None:
    mode_str = "[DRY RUN — NO PERSISTENCE]" if dry_run else "[LIVE PERSISTENCE & ALERTING]"
    print("=" * 72)
    print(f"JOB-AI CAREER BUDDY — FRESH JOB MONITORING ENGINE {mode_str}")
    print(f"Target Region: {region.upper()} | Freshness Filter: {'<= 24 Hours' if fresh_only else 'All Discovery'}")
    print("=" * 72)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    args = parse_args()

    conn = get_connection(db_path=args.db_path, auto_init=True)
    profile = load_candidate_profile()
    fact_bank = load_fact_bank()

    print_banner(dry_run=args.dry_run, region=args.region, fresh_only=args.fresh_only)

    monitor_service = FreshJobMonitoringService(
        conn=conn,
        profile=profile,
        fact_bank=fact_bank,
    )

    report = monitor_service.run_monitoring_cycle(
        region=args.region,
        fresh_only=args.fresh_only,
        dry_run=args.dry_run,
        limit=args.limit,
    )

    print("\n--- SOURCE ADAPTER HEALTH AUDIT ---")
    for name, health in report.source_health.items():
        status_icon = "[OK]" if health["status"] == "success" else "[FAILED]"
        print(
            f"  {status_icon:8} {name:32} | Discovered: {health['jobs_discovered']:2} | "
            f"Fresh (<24h): {health['fresh_count']:2} | Latency: {health['duration_ms']:.1f}ms"
        )
        if health.get("error"):
            print(f"     [!] Error: {health['error']}")

    print("\n--- MONITORING CYCLE RESULTS ---")
    print(f"  * Run ID:                    {report.run_id}")
    print(f"  * Sources Checked:           {report.sources_checked} (Success: {report.sources_successful}, Failed: {report.sources_failed})")
    print(f"  * Total Raw Jobs Found:      {report.total_jobs_found}")
    print(f"  * Unique Canonical Jobs:     {report.unique_jobs_ingested}")
    print(f"  * Verified Fresh (<24h):     {report.fresh_24h_jobs_count}")
    print(f"  * Priority P0 Opportunities: {report.p0_count}")
    print(f"  * Priority P1 Opportunities: {report.p1_count}")
    print(f"  * Priority P2 Opportunities: {report.p2_count}")
    print(f"  * Priority P3 Opportunities: {report.p3_count}")
    print(f"  * Notifications Proposed:    {report.notifications_generated}")

    if report.alerts:
        print("\n--- TOP OPPORTUNITY ALERTS ---")
        for alert in report.alerts[:10]:
            p_badge = f"[{alert.priority.value}]"
            fresh_badge = f"({alert.freshness_status.value})"
            print(
                f"  {p_badge:5} {alert.company:24} | {alert.title:35} | "
                f"Score: {alert.match_score:4.1f}% | {fresh_badge}"
            )

    print("=" * 72)
    if args.dry_run:
        print("[INFO] Dry-run complete. No database records or notifications were created.")
    else:
        print("[OK] Monitoring cycle persisted. Review fresh opportunities in Streamlit Dashboard.")
    print("=" * 72)

    return 0



if __name__ == "__main__":
    sys.exit(main())
