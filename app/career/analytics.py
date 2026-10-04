"""Career Analytics Service calculating factual metrics and trends from SQLite."""

import sqlite3
from typing import Any

from app.career.repository import CareerRepository
from app.db.models import ApplicationStatus
from app.db.repository import JobRepository
from app.resume.repository import ResumeRepository


class CareerAnalyticsService:
    """Computes transparent, factual career analytics derived directly from stored candidate data."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        job_repo: JobRepository | None = None,
        career_repo: CareerRepository | None = None,
        resume_repo: ResumeRepository | None = None,
    ):
        self.conn = conn
        self.job_repo = job_repo or JobRepository(conn)
        self.career_repo = career_repo or CareerRepository(conn)
        self.resume_repo = resume_repo or ResumeRepository(conn)

    def get_summary_metrics(self) -> dict[str, Any]:
        """Aggregate high-level status counts across jobs, applications, resumes, and preparation."""
        all_jobs = self.job_repo.list_normalized_jobs()
        all_apps = self.job_repo.list_applications()
        all_questions = self.career_repo.get_all_questions()
        all_weaks = self.career_repo.list_weak_areas(resolved=False)
        all_assessments = self.career_repo.list_assessments()

        status_counts: dict[str, int] = {}
        for app in all_apps:
            s_val = app.status.value
            status_counts[s_val] = status_counts.get(s_val, 0) + 1

        applied_count = status_counts.get(ApplicationStatus.APPLIED.value, 0)
        total_apps = len(all_apps)
        conversion_rate_str = (
            f"{(applied_count / total_apps * 100):.1f}%" if total_apps > 0 else "Insufficient data"
        )

        return {
            "total_discovered_jobs": len(all_jobs),
            "total_applications": total_apps,
            "status_counts": status_counts,
            "applications_applied": applied_count,
            "applications_ready_for_review": status_counts.get(ApplicationStatus.READY_FOR_REVIEW.value, 0),
            "applications_approved": status_counts.get(ApplicationStatus.APPROVED.value, 0),
            "applications_failed": status_counts.get(ApplicationStatus.FAILED.value, 0),
            "conversion_rate": conversion_rate_str,
            "total_interview_questions": len(all_questions),
            "unresolved_weak_areas_count": len(all_weaks),
            "total_assessments_taken": len(all_assessments),
        }

    def get_resume_ats_distribution(self) -> list[dict[str, Any]]:
        """Retrieve ATS score breakdown and fact integrity status for all tailored resumes."""
        cursor = self.conn.execute(
            """
            SELECT tr.resume_id, tr.target_job_id, tr.version, tr.ats_score,
                   tr.fact_integrity_status, tr.status, tr.created_at, nj.company, nj.title
            FROM tailored_resumes tr
            JOIN normalized_jobs nj ON tr.target_job_id = nj.id
            ORDER BY tr.created_at DESC
            """
        )
        records = []
        for r in cursor.fetchall():
            records.append({
                "resume_id": r["resume_id"],
                "company": r["company"],
                "role": r["title"],
                "version": f"v{r['version']}",
                "ats_score": round(r["ats_score"], 1),
                "fact_integrity": r["fact_integrity_status"],
                "status": r["status"],
                "created_at": r["created_at"][:10] if r["created_at"] else "N/A",
            })
        return records

    def get_interview_topic_frequency(self) -> list[dict[str, Any]]:
        """Retrieve topic distribution and frequency across question bank."""
        cursor = self.conn.execute(
            """
            SELECT topic, COUNT(*) as count, SUM(times_asked) as total_asked
            FROM interview_questions
            GROUP BY topic
            ORDER BY total_asked DESC, count DESC
            LIMIT 10
            """
        )
        return [{"topic": r["topic"], "count": r["count"], "total_asked": r["total_asked"]} for r in cursor.fetchall()]

    def get_frequently_missed_questions(self) -> list[dict[str, Any]]:
        """Retrieve questions candidate previously answered incorrectly or struggled with."""
        cursor = self.conn.execute(
            """
            SELECT id, question, topic, company, role, times_asked, feedback
            FROM interview_questions
            WHERE was_correct = 0
            ORDER BY times_asked DESC
            LIMIT 10
            """
        )
        return [
            {
                "id": r["id"],
                "question": r["question"],
                "topic": r["topic"],
                "company": r["company"] or "General",
                "role": r["role"] or "DV",
                "times_asked": r["times_asked"],
                "feedback": r["feedback"] or "Needs revision",
            }
            for r in cursor.fetchall()
        ]

    def get_assessment_score_history(self) -> list[dict[str, Any]]:
        """Retrieve historical assessment results and scores."""
        assessments = self.career_repo.list_assessments()
        return [
            {
                "id": a.id,
                "title": a.title,
                "type": a.assessment_type.value,
                "score": f"{round(a.score, 1)}%" if a.score is not None else "In Progress",
                "correct_count": f"{a.correct_count}/{a.total_questions}",
                "status": a.status.value,
                "date": a.created_at[:10] if a.created_at else "N/A",
            }
            for a in assessments
        ]

    def get_weak_area_breakdown(self) -> list[dict[str, Any]]:
        """Retrieve all tracked weak areas with severity, confidence, and review count."""
        weaks = self.career_repo.list_weak_areas(resolved=False)
        return [
            {
                "topic": w.topic,
                "description": w.description,
                "severity": w.severity.upper(),
                "confidence": f"{int(w.confidence * 100)}%",
                "review_count": w.review_count,
                "last_reviewed": w.last_reviewed[:10] if w.last_reviewed else "Never",
            }
            for w in weaks
        ]
