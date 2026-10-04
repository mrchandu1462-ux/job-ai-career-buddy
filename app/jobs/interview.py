"""Phase 6: CLI entrypoint for Interview Prep Copilot and Mock Practice Generator.

Usage:
    # Run interview analysis on target job
    python -m app.jobs.interview --job qualcomm-soc-dv-hyd-123

    # Generate tailored study plan
    python -m app.jobs.interview --job qualcomm-soc-dv-hyd-123 --plan

    # Check skill gaps
    python -m app.jobs.interview --job qualcomm-soc-dv-hyd-123 --gaps

    # Run quick mock interview simulation (non-interactive smoke test)
    python -m app.jobs.interview --job qualcomm-soc-dv-hyd-123 --mode quick

    # Run project defense practice
    python -m app.jobs.interview --job qualcomm-soc-dv-hyd-123 --mode project
"""

import argparse
import sys
from typing import Any

from app.career.copilot import (
    InterviewCopilotService,
    MockInterviewMode,
)
from app.db.connection import get_connection
from app.db.models import NormalizedJob
from app.db.repository import JobRepository
from app.db.schema import create_schema


def _find_target_job(repo: JobRepository, identifier: str | None) -> NormalizedJob:
    """Resolve normalized job by fingerprint or pick the latest available active job."""
    if identifier:
        job = repo.get_normalized_job_by_fingerprint(identifier)
        if job:
            return job
        try:
            job_id = int(identifier)
            job = repo.get_normalized_job(job_id)
            if job:
                return job
        except ValueError:
            pass

    # Fallback to latest discovered job
    fresh_jobs = repo.list_fresh_jobs(max_age_hours=720.0, limit=1)
    if fresh_jobs:
        return fresh_jobs[0]

    # Fallback default mock job
    return NormalizedJob(
        company="Qualcomm",
        title="Design Verification Engineer",
        location="Bengaluru, India",
        country="India",
        source="cli_default",
        first_seen="2026-10-04T00:00:00Z",
        last_seen="2026-10-04T00:00:00Z",
        fingerprint="default-qualcomm-dv-blr",
        description="Design Verification Engineer responsible for SystemVerilog, UVM testbench development, AXI protocol verification, SVA assertions, and regression debug.",
        requirements="0-2 years experience, B.Tech EEE, SystemVerilog, UVM, AXI.",
        skills=["SystemVerilog", "UVM", "AXI", "SVA", "Python"],
    )


def run_interview_cli(args: Any) -> int:
    """Execute interview copilot analysis, plan generation, or mock interview simulation."""
    conn = get_connection()
    create_schema(conn)
    repo = JobRepository(conn)
    copilot = InterviewCopilotService(conn)

    job = _find_target_job(repo, args.job)
    profile = copilot.analyze_job(job)

    print("\n" + "=" * 70)
    print("JOB-AI CAREER BUDDY  |  INTERVIEW PREP COPILOT")
    print(f"Target Role: {profile.role} at {profile.company}")
    print(f"Job Fingerprint: {profile.job_fingerprint}")
    print("=" * 70)

    # 1. Skill Gaps Display
    if args.gaps or (not args.plan and not args.readiness and not args.interactive):
        print("\n[1] SKILL GAP ANALYSIS")
        print("-" * 50)
        for gap in profile.skill_gaps:
            badge = f"[{gap.proficiency.value}]"
            req = "(Required)" if gap.is_required else "(Preferred)"
            print(f"* {gap.skill_name:<28} {badge:<10} {req}")
            if gap.recommendation:
                print(f"  -> {gap.recommendation}")

    # 2. Readiness Score Display
    if (args.readiness or (not args.plan and not args.gaps and not args.interactive)) and profile.readiness:
        print("\n[2] INTERVIEW READINESS EVALUATION")
        print("-" * 50)
        print(f"Overall Score : {profile.readiness.total_score}/100 -- {profile.readiness.level.value}")
        print(f"Strengths     : {', '.join(profile.readiness.strengths)}")
        if profile.readiness.needs_work:
            print(f"Priority Gaps : {', '.join(profile.readiness.needs_work)}")

    # 3. Tailored Study Plan
    if args.plan and profile.study_plan:
        print("\n[3] 7-DAY TAILORED STUDY PLAN")
        print("-" * 50)
        for day in profile.study_plan.days:
            print(f"\n{day.title} ({day.estimated_minutes} mins):")
            print(f"  Focus Topics: {', '.join(day.focus_topics)}")
            if day.target_weak_areas:
                print(f"  Weak Areas  : {', '.join(day.target_weak_areas)}")
            print(f"  Drills      : {', '.join(day.practice_drills)}")

    # 4. Mock Interview Simulation
    mode_map = {
        "quick": MockInterviewMode.QUICK,
        "standard": MockInterviewMode.STANDARD,
        "deep": MockInterviewMode.DEEP,
        "company": MockInterviewMode.COMPANY,
        "weakness": MockInterviewMode.WEAKNESS,
        "project": MockInterviewMode.PROJECT,
    }
    mode = mode_map.get((args.mode or "").lower(), MockInterviewMode.QUICK)

    if args.interactive:
        print(f"\n[4] INTERACTIVE MOCK INTERVIEW ({mode.value} MODE)")
        print("-" * 50)
        session = copilot.start_mock_interview(job, mode=mode)
        print(f"Started Session {session.session_id} with {len(session.questions)} questions.\n")

        for i, q in enumerate(session.questions, 1):
            print(f"\nQuestion #{i}/{len(session.questions)} [{q.category.value}] ({q.difficulty.value}):")
            print(f"{q.question}\n")
            user_ans = input("Your Answer: ").strip()
            eval_res = copilot.evaluate_mock_turn(session, user_ans)
            print(f"\nEvaluation: {eval_res.status.value} (Accuracy: {eval_res.technical_accuracy:.0%})")
            print(f"Feedback  : {eval_res.feedback}")
            if eval_res.good_points:
                print(f"  + {'; '.join(eval_res.good_points)}")
            if eval_res.missing_points:
                print(f"  - {'; '.join(eval_res.missing_points)}")

        print("\n" + "=" * 70)
        print(f"Mock Interview Complete! Final Score: {session.overall_score or 0.0}/100")
        print("=" * 70 + "\n")
    else:
        # Non-interactive simulation test run
        session = copilot.start_mock_interview(job, mode=mode)
        # Simulate answering the first question
        sample_ans = "Setup time is the minimum time data must be stable before the clock edge, while hold time is after. Delay buffers fix hold violations."
        eval_res = copilot.evaluate_mock_turn(session, sample_ans)
        print(f"\nMock Practice ({mode.value}): Evaluated Turn 1 -> {eval_res.status.value}")

    print("\n[OK] Interview Copilot execution successful.\n")
    return 0


def main() -> None:
    """CLI Parser."""
    parser = argparse.ArgumentParser(description="Job-AI Career Buddy Interview Prep Copilot")
    parser.add_argument("--job", type=str, default=None, help="Job fingerprint or ID to target")
    parser.add_argument(
        "--mode",
        type=str,
        default="quick",
        choices=["quick", "standard", "deep", "company", "weakness", "project"],
        help="Mock interview mode",
    )
    parser.add_argument("--plan", action="store_true", help="Display tailored 7-day study plan")
    parser.add_argument("--gaps", action="store_true", help="Display skill gap breakdown")
    parser.add_argument("--readiness", action="store_true", help="Display readiness score")
    parser.add_argument("--interactive", action="store_true", help="Run interactive terminal interview")

    args = parser.parse_args()
    sys.exit(run_interview_cli(args))


if __name__ == "__main__":
    main()
