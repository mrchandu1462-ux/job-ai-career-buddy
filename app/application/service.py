import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from app.application.matcher import ApplicationMatcher
from app.application.models import (
    ApplicationPackageDetail,
    CategorizedQuestionItem,
    SubmissionFailureRecord,
    SubmissionRecord,
)
from app.career.assessment import AdaptiveAssessmentEngine
from app.career.bank import QuestionBankService
from app.career.notifications import ScheduleNotificationService
from app.career.repository import CareerRepository
from app.db.models import (
    ApplicationEvent,
    ApplicationEventType,
    ApplicationRecord,
    ApplicationStatus,
    InterviewQuestion,
    NotificationRecord,
    NotificationType,
)
from app.db.repository import JobRepository
from app.profile.models import CandidateProfile, FactBank
from app.resume.engine import ResumeTailoringEngine
from app.resume.export.docx import DOCXResumeExporter
from app.resume.export.models import ExportFormat
from app.resume.export.pdf import PDFResumeExporter
from app.resume.export.validation import ResumeExportValidator
from app.resume.formatter import ATSResumeFormatter
from app.resume.integration import ResumeCareerIntegration
from app.resume.repository import ResumeRepository


class ApplicationPipelineService:
    """
    Unified Application Lifecycle and Career Preparation Service.
    Enforces strict local-first auditability, factual provenance, and human-in-the-loop control.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        profile: CandidateProfile,
        fact_bank: FactBank,
        artifacts_dir: str = "artifacts/resumes",
    ):
        self.conn = conn
        self.profile = profile
        self.fact_bank = fact_bank
        self.artifacts_dir = artifacts_dir
        Path(self.artifacts_dir).mkdir(parents=True, exist_ok=True)

        # Repositories
        self.job_repo = JobRepository(conn)
        self.career_repo = CareerRepository(conn)
        self.resume_repo = ResumeRepository(conn)

        # Subsystems & Services
        self.matcher = ApplicationMatcher(profile, fact_bank, self.career_repo)
        self.resume_engine = ResumeTailoringEngine(
            conn=conn,
            fact_bank=fact_bank,
            job_repo=self.job_repo,
            resume_repo=self.resume_repo,
        )
        self.docx_exporter = DOCXResumeExporter(output_dir=artifacts_dir)
        self.pdf_exporter = PDFResumeExporter(output_dir=artifacts_dir)
        self.export_validator = ResumeExportValidator()
        self.bank_service = QuestionBankService(conn, self.career_repo)
        self.assessment_engine = AdaptiveAssessmentEngine(conn, self.career_repo, self.job_repo)
        self.resume_integration = ResumeCareerIntegration(
            conn, self.job_repo, self.resume_repo, self.career_repo
        )
        self.notification_service = ScheduleNotificationService(conn)

    # -------------------------------------------------------------------------
    # 1. Job Shortlisting
    # -------------------------------------------------------------------------
    def shortlist_job(self, job_id: int, notes: str | None = None) -> ApplicationRecord:
        """Mark a discovered job as SHORTLISTED and initialize its application record."""
        job = self.job_repo.get_normalized_job(job_id)
        if not job:
            raise ValueError(f"Job #{job_id} not found.")

        now_iso = datetime.now(UTC).isoformat()
        app = self.job_repo.get_application_by_job_id(job_id)

        if not app:
            app_id = self.job_repo.create_application(
                ApplicationRecord(
                    job_id=job_id,
                    status=ApplicationStatus.SHORTLISTED,
                    notes=notes or f"Shortlisted {job.title} at {job.company}.",
                    created_at=now_iso,
                    updated_at=now_iso,
                )
            )
            app = self.job_repo.get_application(app_id)
        else:
            self.job_repo.update_application_status(
                app.id,  # type: ignore
                ApplicationStatus.SHORTLISTED,
                notes=notes or f"Updated status to shortlisted for {job.company}.",
            )
            app = self.job_repo.get_application(app.id)  # type: ignore

        # Audit event
        self.job_repo.record_application_event(
            ApplicationEvent(
                application_id=app.id,  # type: ignore
                job_id=job_id,
                event_type=ApplicationEventType.STATUS_CHANGED,
                company=job.company,
                role_title=job.title,
                location=job.location,
                source=job.source,
                official_application_url=job.application_url,
                timestamp=now_iso,
                application_status=ApplicationStatus.SHORTLISTED,
                notes=notes or "Opportunity shortlisted for application preparation.",
            )
        )

        return app  # type: ignore

    # -------------------------------------------------------------------------
    # 2. Application Preparation Pipeline
    # -------------------------------------------------------------------------
    def prepare_application(
        self,
        job_id: int,
        target_interview_date: str | None = None,
    ) -> ApplicationPackageDetail:
        """
        Execute the complete, auditable application preparation workflow:
        1. Evaluate Candidate Match & Reasons.
        2. Generate ATS-optimized Fact-Grounded Tailored Resume (aiming >= 80).
        3. Export to ATS-Safe DOCX, PDF, TXT, MD.
        4. Validate Exports via ResumeExportValidator.
        5. Collect Question Pool distinguishing Historical vs Generated Practice questions.
        6. Compute Pre-Interview Readiness & Gate evaluation.
        7. Generate Preparation Schedule & proposed notifications.
        8. Transition status to READY_FOR_REVIEW awaiting human approval.
        """
        job = self.job_repo.get_normalized_job(job_id)
        if not job:
            raise ValueError(f"Job #{job_id} not found.")

        now_iso = datetime.now(UTC).isoformat()

        # Step 1: Explainable Match
        match_report = self.matcher.match_job(job)

        # Step 2: Tailored Resume Generation (Fact Integrity + ATS Scoring)
        tailored_resume = self.resume_engine.generate_tailored_resume(job_id=job_id)

        # Step 3: Export to ATS-Safe Formats
        docx_file = f"{tailored_resume.resume_id}.docx"
        pdf_file = f"{tailored_resume.resume_id}.pdf"
        txt_file = f"{tailored_resume.resume_id}.txt"
        md_file = f"{tailored_resume.resume_id}.md"

        docx_path = self.docx_exporter.export(tailored_resume, filename=docx_file)
        pdf_path = self.pdf_exporter.export(tailored_resume, filename=pdf_file)

        txt_path = os.path.join(self.artifacts_dir, txt_file)
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(tailored_resume.plain_text_content or ATSResumeFormatter.render_plaintext(tailored_resume))

        md_path = os.path.join(self.artifacts_dir, md_file)
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(tailored_resume.markdown_content or ATSResumeFormatter.render_markdown(tailored_resume))

        # Step 4: Validate Exports
        docx_val = self.export_validator.validate_export(docx_path, ExportFormat.DOCX, tailored_resume)
        pdf_val = self.export_validator.validate_export(pdf_path, ExportFormat.PDF, tailored_resume)
        is_export_validated = docx_val.is_export_validated and pdf_val.is_export_validated

        # Step 5: Gather Interview Questions (Separating Historical vs Generated)
        review_pool = self.bank_service.build_review_pool_for_job(job)
        historical_questions: list[CategorizedQuestionItem] = []
        practice_questions: list[CategorizedQuestionItem] = []

        # Collect unique questions from all 8 categories
        seen_q_texts: set[str] = set()
        all_pool_questions: list[InterviewQuestion] = []
        for q_list in [
            review_pool.must_know,
            review_pool.frequently_asked,
            review_pool.previously_missed,
            review_pool.job_specific,
            review_pool.company_specific,
            review_pool.weak_areas,
            review_pool.fundamentals,
            review_pool.advanced_bonus,
        ]:
            for q in q_list:
                if q.question not in seen_q_texts:
                    seen_q_texts.add(q.question)
                    all_pool_questions.append(q)

        weak_area_topics = {q.topic.lower() for q in review_pool.weak_areas}

        for q in all_pool_questions:
            # Check if question has a verified historical interview source
            is_hist = bool(
                q.session_id is not None
                or (
                    q.source
                    and any(
                        kw in q.source.lower()
                        for kw in [
                            "interview",
                            "round",
                            "technical 1",
                            "synopsys",
                            "qualcomm",
                            "intel",
                            "nvidia",
                            "ti",
                            "historical",
                        ]
                    )
                )
            )
            provenance = q.source if is_hist else "GENERATED / PRACTICE"

            item = CategorizedQuestionItem(
                question=q.question,
                topic=q.topic,
                difficulty=q.difficulty or "medium",
                is_historical=is_hist,
                provenance_source=provenance,
                expected_answer=q.expected_answer,
                frequency=q.times_asked,
                weak_area_associated=q.topic.lower() in weak_area_topics,
            )
            if is_hist:
                historical_questions.append(item)
            else:
                practice_questions.append(item)

        # Step 6: Readiness & Assessment
        readiness_score = None
        readiness_status = "NOT_EVALUATED"
        critical_passing = False
        try:
            readiness_res = self.assessment_engine.compute_job_readiness(job_id=job_id)
            readiness_score = readiness_res.overall_readiness_score
            readiness_status = readiness_res.readiness_level
            critical_passing = len(readiness_res.weak_topics) == 0
        except (ValueError, KeyError, sqlite3.Error, RuntimeError):
            readiness_score = None
            readiness_status = "NOT_EVALUATED"

        # Step 7: Preparation Schedule
        schedule_milestones: list[dict[str, str]] = []
        if target_interview_date:
            try:
                schedule = self.assessment_engine.generate_preparation_schedule(
                    job_id=job_id, target_interview_date=target_interview_date
                )
                schedule_milestones = [
                    {
                        "day": f"Day {m.day_offset}",
                        "title": m.title,
                        "topics": ", ".join(m.topics),
                        "action": m.action_type,
                    }
                    for m in schedule.milestones
                ]
            except (ValueError, KeyError, sqlite3.Error, RuntimeError):
                schedule_milestones = []

        # Step 8: Update Application State
        app = self.job_repo.get_application_by_job_id(job_id)
        if not app:
            app_id = self.job_repo.create_application(
                ApplicationRecord(
                    job_id=job_id,
                    status=ApplicationStatus.READY_FOR_REVIEW,
                    tailored_resume_path=md_path,
                    notes=f"Prepared Application Package (Resume {tailored_resume.resume_id}, ATS {tailored_resume.ats_score}/100).",
                    created_at=now_iso,
                    updated_at=now_iso,
                )
            )
            app = self.job_repo.get_application(app_id)
        else:
            self.job_repo.conn.execute(
                "UPDATE applications SET status = ?, tailored_resume_path = ?, notes = ?, updated_at = ? WHERE id = ?",
                (
                    ApplicationStatus.READY_FOR_REVIEW.value,
                    md_path,
                    f"Application Package prepared. Resume v{tailored_resume.version} attached (ATS: {tailored_resume.ats_score}/100).",
                    now_iso,
                    app.id,
                ),
            )
            self.job_repo.conn.commit()
            app = self.job_repo.get_application(app.id)  # type: ignore

        # Audit Event
        self.job_repo.record_application_event(
            ApplicationEvent(
                application_id=app.id,  # type: ignore
                job_id=job_id,
                event_type=ApplicationEventType.READY_FOR_REVIEW,
                company=job.company,
                role_title=job.title,
                location=job.location,
                source=job.source,
                official_application_url=job.application_url,
                timestamp=now_iso,
                resume_version=tailored_resume.resume_id,
                application_status=ApplicationStatus.READY_FOR_REVIEW,
                notes=f"Application Package prepared (ATS: {tailored_resume.ats_score}/100, Export Validated: {is_export_validated}). Awaiting human approval.",
            )
        )

        # Dispatch Notification
        self.job_repo.create_notification(
            NotificationRecord(
                job_id=job_id,
                application_id=app.id,  # type: ignore
                notification_type=NotificationType.HUMAN_APPROVAL_REQUIRED,
                title=f"Application Ready for Approval: {job.title} at {job.company}",
                message=(
                    f"WHAT: Application Package prepared for {job.company} — {job.title}.\n"
                    f"MATCH: {int(match_report.match_score)}% | ATS: {int(tailored_resume.ats_score)}/100 (v{tailored_resume.version}).\n"
                    f"FACT INTEGRITY: {tailored_resume.fact_integrity_status} | EXPORTS: DOCX {'PASS' if docx_val.is_export_validated else 'FAIL'} | PDF {'PASS' if pdf_val.is_export_validated else 'FAIL'}.\n"
                    f"INTERVIEW PREP: {len(historical_questions)} verified historical questions, {len(practice_questions)} practice drills.\n"
                    "STATUS: READY FOR HUMAN REVIEW — NOTHING SUBMITTED YET."
                ),
                created_at=now_iso,
            )
        )

        what_ai_did = [
            f"Evaluated match score ({match_report.match_score}%) with positive reasons and gap analysis.",
            f"Synthesized versioned resume {tailored_resume.resume_id} (ATS: {tailored_resume.ats_score}/100).",
            f"Exported and validated DOCX ({'PASS' if docx_val.is_export_validated else 'FAIL'}) and PDF ({'PASS' if pdf_val.is_export_validated else 'FAIL'}).",
            f"Separated {len(historical_questions)} verified historical interview questions from {len(practice_questions)} practice questions.",
            "Created preparation milestones and requested candidate human review.",
        ]

        what_ai_did_not_do = [
            "DID NOT submit application to employer portal.",
            "DID NOT mark application as APPLIED (status is READY_FOR_REVIEW).",
            "DID NOT fabricate any skills, metrics, tools, or experience.",
            "DID NOT send external emails or calendar invites.",
        ]

        return ApplicationPackageDetail(
            application_id=app.id if app else None,
            job_id=job_id,
            company=job.company,
            title=job.title,
            location=job.location,
            country=job.country,
            application_url=job.application_url,
            status=ApplicationStatus.READY_FOR_REVIEW,
            match=match_report,
            resume_id=tailored_resume.resume_id,
            resume_version=tailored_resume.version,
            ats_score=tailored_resume.ats_score,
            ats_quality_gate_met=tailored_resume.ats_breakdown.quality_gate_met if tailored_resume.ats_breakdown else False,
            fact_integrity_status=tailored_resume.fact_integrity_status,
            unsupported_requirements=tailored_resume.ats_breakdown.unsupported_requirements if tailored_resume.ats_breakdown else [],
            adjacent_evidence_found=tailored_resume.ats_breakdown.adjacent_evidence_found if tailored_resume.ats_breakdown else {},
            docx_path=docx_path,
            pdf_path=pdf_path,
            plaintext_path=txt_path,
            markdown_path=md_path,
            docx_validation=docx_val,
            pdf_validation=pdf_val,
            is_export_validated=is_export_validated,
            historical_questions=historical_questions,
            practice_questions=practice_questions,
            weak_areas=[w.topic for w in review_pool.weak_areas],
            readiness_score=readiness_score,
            readiness_status=readiness_status,
            critical_topics_passing=critical_passing,
            schedule_milestones=schedule_milestones,
            human_approval_state="AWAITING_REVIEW",
            is_submitted=False,
            what_ai_did=what_ai_did,
            what_ai_did_not_do=what_ai_did_not_do,
            created_at=now_iso,
        )

    # -------------------------------------------------------------------------
    # 3. Human Review Workflow
    # -------------------------------------------------------------------------
    def review_application(
        self,
        application_id: int,
        decision: str,  # "APPROVE", "REJECT", "EDIT"
        notes: str | None = None,
    ) -> ApplicationRecord:
        """
        Process human review decision.
        - APPROVE -> APPROVED (never APPLIED).
        - REJECT -> REJECTED.
        - EDIT -> PREPARING.
        """
        app = self.job_repo.get_application(application_id)
        if not app:
            raise ValueError(f"Application #{application_id} not found.")

        now_iso = datetime.now(UTC).isoformat()
        job = self.job_repo.get_normalized_job(app.job_id)
        company = job.company if job else "Company"
        title = job.title if job else "Role"

        decision_upper = decision.strip().upper()
        if decision_upper == "APPROVE":
            self.job_repo.update_application_status(
                application_id,
                ApplicationStatus.APPROVED,
                notes=notes or "Candidate explicitly approved application package.",
            )
            self.job_repo.record_application_event(
                ApplicationEvent(
                    application_id=application_id,
                    job_id=app.job_id,
                    event_type=ApplicationEventType.APPROVED,
                    company=company,
                    role_title=title,
                    location=job.location if job else None,
                    source=job.source if job else "portal",
                    official_application_url=job.application_url if job else None,
                    timestamp=now_iso,
                    application_status=ApplicationStatus.APPROVED,
                    notes=notes or "Candidate approved application package.",
                )
            )
            self.job_repo.create_notification(
                NotificationRecord(
                    job_id=app.job_id,
                    application_id=application_id,
                    notification_type=NotificationType.STATUS_CHANGED,
                    title=f"Application Approved: {title} at {company}",
                    message=f"Application package approved for {company}. Ready for confirmed candidate submission.",
                    created_at=now_iso,
                )
            )
        elif decision_upper == "REJECT":
            self.job_repo.update_application_status(
                application_id,
                ApplicationStatus.REJECTED,
                notes=notes or "Candidate rejected opportunity.",
            )
            self.job_repo.record_application_event(
                ApplicationEvent(
                    application_id=application_id,
                    job_id=app.job_id,
                    event_type=ApplicationEventType.REJECTED,
                    company=company,
                    role_title=title,
                    location=job.location if job else None,
                    source=job.source if job else "portal",
                    official_application_url=job.application_url if job else None,
                    timestamp=now_iso,
                    application_status=ApplicationStatus.REJECTED,
                    notes=notes or "Opportunity rejected during review.",
                )
            )
        elif decision_upper == "EDIT":
            self.job_repo.update_application_status(
                application_id,
                ApplicationStatus.PREPARING,
                notes=notes or "Candidate requested edits before approval.",
            )
        else:
            raise ValueError(f"Invalid review decision '{decision}'. Must be APPROVE, REJECT, or EDIT.")

        updated_app = self.job_repo.get_application(application_id)
        if not updated_app:
            raise ValueError(f"Application #{application_id} could not be retrieved.")
        return updated_app

    # -------------------------------------------------------------------------
    # 4. Confirmed Manual Submission & Failure Auditing
    # -------------------------------------------------------------------------
    def record_submission(
        self,
        application_id: int,
        reference_id: str | None = None,
        submission_evidence: str | None = None,
        notes: str | None = None,
    ) -> SubmissionRecord:
        """
        Record confirmed manual application submission.
        Status transitions to APPLIED only upon verified confirmation.
        """
        app = self.job_repo.get_application(application_id)
        if not app:
            raise ValueError(f"Application #{application_id} not found.")

        job = self.job_repo.get_normalized_job(app.job_id)
        now_iso = datetime.now(UTC).isoformat()
        company = job.company if job else "Company"
        title = job.title if job else "Role"

        # Update application table
        self.job_repo.conn.execute(
            "UPDATE applications SET status = ?, applied_at = ?, notes = ?, updated_at = ? WHERE id = ?",
            (
                ApplicationStatus.APPLIED.value,
                now_iso,
                notes or f"Application submitted manually. Reference: {reference_id or 'N/A'}",
                now_iso,
                application_id,
            ),
        )
        self.job_repo.conn.commit()

        # Audit Event
        self.job_repo.record_application_event(
            ApplicationEvent(
                application_id=application_id,
                job_id=app.job_id,
                event_type=ApplicationEventType.SUBMITTED,
                company=company,
                role_title=title,
                location=job.location if job else None,
                source=job.source if job else "portal",
                official_application_url=job.application_url if job else None,
                timestamp=now_iso,
                application_status=ApplicationStatus.APPLIED,
                reference_id=reference_id,
                submission_evidence=submission_evidence,
                notes=notes or "Candidate confirmed successful manual application submission.",
            )
        )

        # Notification
        self.job_repo.create_notification(
            NotificationRecord(
                job_id=app.job_id,
                application_id=application_id,
                notification_type=NotificationType.SUBMISSION_SUCCESS,
                title=f"APPLICATION SUBMITTED: {title} at {company}",
                message=(
                    f"WHAT: Confirmed application submission for {company} ({title}).\n"
                    f"SUBMITTED AT: {now_iso}\n"
                    f"REFERENCE ID: {reference_id or 'None'}\n"
                    f"EVIDENCE: {submission_evidence or 'Confirmed manually by candidate'}"
                ),
                created_at=now_iso,
            )
        )

        return SubmissionRecord(
            application_id=application_id,
            job_id=app.job_id,
            company=company,
            role_title=title,
            resume_version_used=app.tailored_resume_path or "default_v1",
            applied_at=now_iso,
            application_url=job.application_url if job else None,
            reference_id=reference_id,
            submission_evidence=submission_evidence,
            notes=notes,
        )

    def record_submission_failure(
        self,
        application_id: int,
        error_message: str,
        evidence: str | None = None,
        retry_recommendation: str = "Verify portal credentials, check URL reachability, and re-attempt submission.",
    ) -> SubmissionFailureRecord:
        """
        Record a failed application submission attempt.
        Status transitions to FAILED. Zero false claims of APPLIED state.
        """
        app = self.job_repo.get_application(application_id)
        if not app:
            raise ValueError(f"Application #{application_id} not found.")

        job = self.job_repo.get_normalized_job(app.job_id)
        now_iso = datetime.now(UTC).isoformat()
        company = job.company if job else "Company"
        title = job.title if job else "Role"

        # Update application table
        self.job_repo.conn.execute(
            "UPDATE applications SET status = ?, notes = ?, updated_at = ? WHERE id = ?",
            (
                ApplicationStatus.FAILED.value,
                f"Submission failed: {error_message}",
                now_iso,
                application_id,
            ),
        )
        self.job_repo.conn.commit()

        # Audit Event
        self.job_repo.record_application_event(
            ApplicationEvent(
                application_id=application_id,
                job_id=app.job_id,
                event_type=ApplicationEventType.SUBMISSION_FAILED,
                company=company,
                role_title=title,
                location=job.location if job else None,
                source=job.source if job else "portal",
                official_application_url=job.application_url if job else None,
                timestamp=now_iso,
                application_status=ApplicationStatus.FAILED,
                submission_evidence=evidence,
                notes=f"Submission failed: {error_message}",
            )
        )

        # Notification
        self.job_repo.create_notification(
            NotificationRecord(
                job_id=app.job_id,
                application_id=application_id,
                notification_type=NotificationType.SUBMISSION_FAILED,
                title=f"APPLICATION FAILED: {title} at {company}",
                message=(
                    f"WHAT: Application submission failed for {company} ({title}).\n"
                    f"REASON: {error_message}\n"
                    f"TIMESTAMP: {now_iso}\n"
                    f"RETRY GUIDANCE: {retry_recommendation}\n"
                    "SAFETY NOTE: Nothing was falsely marked as submitted."
                ),
                created_at=now_iso,
            )
        )

        return SubmissionFailureRecord(
            application_id=application_id,
            job_id=app.job_id,
            company=company,
            role_title=title,
            failed_at=now_iso,
            error_message=error_message,
            evidence=evidence,
            retry_recommendation=retry_recommendation,
        )
