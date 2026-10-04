"""SQLite DAO Repository for managing versioned tailored resumes."""

import json
import sqlite3

from app.resume.models import (
    ATSBreakdown,
    ResumeEducation,
    ResumeExperience,
    ResumeProject,
    ResumeStatus,
    TailoredResume,
)


class ResumeRepository:
    """Repository for persisting, retrieving, and versioning tailored resumes in SQLite."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def _row_to_tailored_resume(self, row: sqlite3.Row) -> TailoredResume:
        contact_info = json.loads(row["contact_info"]) if row["contact_info"] else {}
        tech_skills = json.loads(row["technical_skills"]) if row["technical_skills"] else {}
        projects_data = json.loads(row["projects"]) if row["projects"] else []
        exp_data = json.loads(row["experience"]) if row["experience"] else []
        edu_data = json.loads(row["education"]) if row["education"] else []
        certs_data = json.loads(row["certifications"]) if row["certifications"] else []
        breakdown_data = json.loads(row["ats_breakdown"]) if row["ats_breakdown"] else {}
        source_fids = json.loads(row["source_fact_ids"]) if row["source_fact_ids"] else []

        projects = [ResumeProject.model_validate(p) for p in projects_data]
        experience = [ResumeExperience.model_validate(e) for e in exp_data]
        education = [ResumeEducation.model_validate(ed) for ed in edu_data]
        ats_breakdown = ATSBreakdown.model_validate(breakdown_data)

        return TailoredResume(
            id=row["id"],
            resume_id=row["resume_id"],
            target_job_id=row["target_job_id"],
            version=row["version"],
            candidate_name=row["candidate_name"],
            contact_info=contact_info,
            professional_summary=row["professional_summary"],
            technical_skills_by_category=tech_skills,
            projects=projects,
            experience=experience,
            education=education,
            certifications=certs_data,
            ats_score=row["ats_score"],
            ats_breakdown=ats_breakdown,
            fact_integrity_status=row["fact_integrity_status"],
            source_fact_ids=source_fids,
            status=ResumeStatus(row["status"]),
            plain_text_content=row["plain_text_content"],
            markdown_content=row["markdown_content"],
            generated_at=row["created_at"],
        )

    def insert_tailored_resume(self, resume: TailoredResume) -> int:
        """Insert a newly generated versioned tailored resume."""
        raw_projects = [p.model_dump() for p in resume.projects]
        raw_experience = [e.model_dump() for e in resume.experience]
        raw_education = [ed.model_dump() for ed in resume.education]

        query = """
        INSERT INTO tailored_resumes (
            resume_id, target_job_id, version, candidate_name, contact_info,
            professional_summary, technical_skills, projects, experience,
            education, certifications, ats_score, ats_breakdown,
            fact_integrity_status, source_fact_ids, status, plain_text_content,
            markdown_content, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        cursor = self.conn.execute(
            query,
            (
                resume.resume_id,
                resume.target_job_id,
                resume.version,
                resume.candidate_name,
                json.dumps(resume.contact_info),
                resume.professional_summary,
                json.dumps(resume.technical_skills_by_category),
                json.dumps(raw_projects),
                json.dumps(raw_experience),
                json.dumps(raw_education),
                json.dumps(resume.certifications),
                resume.ats_score,
                json.dumps(resume.ats_breakdown.model_dump()),
                resume.fact_integrity_status,
                json.dumps(resume.source_fact_ids),
                resume.status.value,
                resume.plain_text_content,
                resume.markdown_content,
                resume.generated_at,
            ),
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_tailored_resume(self, resume_id: str) -> TailoredResume | None:
        """Fetch resume by string identifier."""
        cursor = self.conn.execute(
            "SELECT * FROM tailored_resumes WHERE resume_id = ?", (resume_id,)
        )
        row = cursor.fetchone()
        return self._row_to_tailored_resume(row) if row else None

    def list_resumes_for_job(self, job_id: int) -> list[TailoredResume]:
        """List all versions of tailored resumes created for a job."""
        cursor = self.conn.execute(
            "SELECT * FROM tailored_resumes WHERE target_job_id = ? ORDER BY version DESC",
            (job_id,),
        )
        return [self._row_to_tailored_resume(r) for r in cursor.fetchall()]

    def list_tailored_resumes(self) -> list[TailoredResume]:
        """List all tailored resumes stored in database ordered by creation time."""
        cursor = self.conn.execute(
            "SELECT * FROM tailored_resumes ORDER BY created_at DESC"
        )
        return [self._row_to_tailored_resume(r) for r in cursor.fetchall()]

    def list_all_resumes(self) -> list[TailoredResume]:
        """Alias for list_tailored_resumes."""
        return self.list_tailored_resumes()

    def update_resume_status(self, resume_id: str, new_status: ResumeStatus) -> None:
        """Update lifecycle status of a tailored resume (e.g. APPROVED, ARCHIVED)."""
        self.conn.execute(
            "UPDATE tailored_resumes SET status = ? WHERE resume_id = ?",
            (new_status.value, resume_id),
        )
        self.conn.commit()
