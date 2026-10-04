"""Integration bridge linking Tailored Resumes with Career Knowledge Base and Application Tracking."""

import sqlite3
from datetime import UTC, datetime

from app.career.repository import CareerRepository
from app.career.simulation import (
    ProjectAuthenticityChecker,
    ProjectAuthenticityQuestion,
)
from app.db.models import ApplicationRecord, ApplicationStatus
from app.db.repository import JobRepository
from app.resume.models import TailoredResume
from app.resume.repository import ResumeRepository


class ResumeCareerIntegration:
    """Connects tailored resumes with project defense question generation and application tracking."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        job_repo: JobRepository | None = None,
        resume_repo: ResumeRepository | None = None,
        career_repo: CareerRepository | None = None,
    ):
        self.conn = conn
        self.job_repo = job_repo or JobRepository(conn)
        self.resume_repo = resume_repo or ResumeRepository(conn)
        self.career_repo = career_repo or CareerRepository(conn)
        self.authenticity_checker = ProjectAuthenticityChecker(self.career_repo)

    def generate_defense_questions_for_resume(
        self, resume: TailoredResume
    ) -> list[ProjectAuthenticityQuestion]:
        """Generate rigorous project authenticity defense questions for all projects claimed in the resume."""
        defense_questions: list[ProjectAuthenticityQuestion] = []
        for p in resume.projects:
            qs = self.authenticity_checker.generate_defense_questions_for_project(
                project_name=p.title,
                project_description=" ".join(b.text for b in p.bullets),
            )
            defense_questions.extend(qs)
        return defense_questions

    def prepare_application_with_resume(
        self, job_id: int, resume_id: str
    ) -> ApplicationRecord:
        """
        Associate the approved/tailored resume version with the job application tracker.
        Records an auditable PREPARED lifecycle event.
        Guaranteed Safety: This never marks the application as APPLIED.
        """
        resume = self.resume_repo.get_tailored_resume(resume_id)
        if not resume:
            raise ValueError(f"Tailored resume #{resume_id} not found.")

        now_iso = datetime.now(UTC).isoformat()
        # Ensure application record exists
        app_record = self.job_repo.get_application_by_job_id(job_id)
        if not app_record:
            app_id = self.job_repo.create_application(
                ApplicationRecord(
                    job_id=job_id,
                    status=ApplicationStatus.DISCOVERED,
                    created_at=now_iso,
                    updated_at=now_iso,
                )
            )
            app_record = self.job_repo.get_application(app_id)

        if not app_record or app_record.id is None:
            raise ValueError(f"Application for job #{job_id} could not be initialized.")

        # Prepare application with resume version
        self.job_repo.prepare_application(
            app_id=app_record.id,
            resume_path=f"resumes/{resume_id}.md",
            notes=f"Tailored resume {resume_id} attached with ATS Score {resume.ats_score}/100.",
        )
        self.job_repo.request_human_approval(app_id=app_record.id)
        updated_app = self.job_repo.get_application(app_record.id)
        if not updated_app:
            raise ValueError(f"Application #{app_record.id} not found after preparation.")
        return updated_app
