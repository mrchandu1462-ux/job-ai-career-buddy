"""Job Discovery and Intelligence Pipeline orchestrating discovery, verification, scoring, resume tailoring, and interview prep."""

import sqlite3
from datetime import UTC, datetime
from typing import Any

from app.career.assessment import AdaptiveAssessmentEngine
from app.career.bank import QuestionBankService
from app.career.notifications import ScheduleNotificationService
from app.career.pipeline import HistoricalInterviewPipeline
from app.career.repository import CareerRepository
from app.db.models import (
    ApplicationEvent,
    ApplicationEventType,
    ApplicationRecord,
    ApplicationStatus,
    NotificationRecord,
    NotificationType,
)
from app.db.repository import JobRepository
from app.jobs.classifier import RoleClassifier
from app.jobs.ingestion import IngestionReport, JobIngestInput, JobIngestionService
from app.jobs.package import ApplicationPackage
from app.jobs.sources.base import (
    ActiveVerificationResult,
    JobDiscoveryQuery,
    JobSource,
)
from app.jobs.sources.career_pages import CompanyCareerSource
from app.jobs.sources.job_board import StructuredJobBoardSource
from app.jobs.sources.manual import ManualJobSource
from app.jobs.sources.registry import JobSourceRegistry
from app.jobs.verifier import ActiveStatusVerifier, sync_job_status_from_verification
from app.matching.models import JobMatchResult
from app.matching.ranker import JobRanker
from app.matching.scorer import JobScoringEngine
from app.profile.models import CandidateProfile, FactBank
from app.resume.engine import ResumeTailoringEngine
from app.resume.integration import ResumeCareerIntegration
from app.resume.repository import ResumeRepository


class JobDiscoveryPipeline:
    """
    End-to-end Job Discovery, Verification, Intelligence, and Application Preparation Pipeline.
    Strict local-first architecture with explainable scoring and mandatory human approval gates.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        profile: CandidateProfile,
        fact_bank: FactBank,
    ):
        self.conn = conn
        self.profile = profile
        self.fact_bank = fact_bank

        # Core Repositories
        self.job_repo = JobRepository(conn)
        self.career_repo = CareerRepository(conn)
        self.resume_repo = ResumeRepository(conn)

        # Ingestion & Verification
        self.verifier = ActiveStatusVerifier()
        self.ingestion_service = JobIngestionService(self.job_repo)
        self.registry = JobSourceRegistry()

        # Register default sources
        self.manual_source = ManualJobSource(self.verifier)
        self.career_source = CompanyCareerSource("top_semiconductor", self.verifier)
        self.board_source = StructuredJobBoardSource("verified_boards", self.verifier)
        self.registry.register_source(self.manual_source)
        self.registry.register_source(self.career_source)
        self.registry.register_source(self.board_source)

        # Intelligence Engines
        self.role_classifier = RoleClassifier()
        self.scoring_engine = JobScoringEngine(profile, fact_bank, self.career_repo)
        self.ranker = JobRanker(profile, fact_bank)
        self.career_pipeline = HistoricalInterviewPipeline(conn)
        self.bank_service = QuestionBankService(conn, self.career_repo)
        self.assessment_engine = AdaptiveAssessmentEngine(conn, self.career_repo, self.job_repo)
        self.notification_service = ScheduleNotificationService(conn)

        # Resume Pipeline
        self.resume_engine = ResumeTailoringEngine(
            conn=self.conn,
            fact_bank=fact_bank,
            job_repo=self.job_repo,
            resume_repo=self.resume_repo,
        )
        self.resume_integration = ResumeCareerIntegration(
            conn, self.job_repo, self.resume_repo, self.career_repo
        )

    # -------------------------------------------------------------------------
    # 1. Job Source Management & Discovery Ingestion
    # -------------------------------------------------------------------------
    def register_source(self, source: JobSource) -> None:
        """Register a custom job source into the registry."""
        self.registry.register_source(source)

    def discover_and_ingest(self, query: JobDiscoveryQuery) -> list[IngestionReport]:
        """Search registered sources, ingest into raw/normalized databases, and verify active status."""
        discovered_payloads = self.registry.search_all(query)
        reports: list[IngestionReport] = []

        for p in discovered_payloads:
            ingest_input = JobIngestInput(
                company=p.company,
                title=p.title,
                raw_payload=p.raw_payload,
                location=p.location,
                country=p.country,
                employment_type=p.employment_type,
                source=p.source,
                source_url=p.source_url,
                application_url=p.application_url,
            )
            report = self.ingestion_service.ingest_job(ingest_input)

            # Active Verification
            ver_res = self.verifier.verify(p)
            new_status = sync_job_status_from_verification(None, ver_res)
            self.job_repo.conn.execute(
                "UPDATE normalized_jobs SET status = ? WHERE id = ?",
                (new_status.value, report.normalized_job_id),
            )
            self.job_repo.conn.commit()

            reports.append(report)

        return reports

    def ingest_single_job(self, input_data: JobIngestInput) -> IngestionReport:
        """Directly ingest a single job description."""
        report = self.ingestion_service.ingest_job(input_data)
        # Verify active status
        norm_job = self.job_repo.get_normalized_job(report.normalized_job_id)
        if norm_job:
            ver_res = self.verifier.verify(norm_job)
            new_status = sync_job_status_from_verification(norm_job, ver_res)
            self.job_repo.conn.execute(
                "UPDATE normalized_jobs SET status = ? WHERE id = ?",
                (new_status.value, report.normalized_job_id),
            )
            self.job_repo.conn.commit()
        return report

    def verify_job_active_status(
        self,
        job_id: int,
        is_url_reachable: bool | None = None,
        portal_status: str | None = None,
    ) -> ActiveVerificationResult:
        """Verify active status for an existing normalized job."""
        job = self.job_repo.get_normalized_job(job_id)
        if not job:
            raise ValueError(f"Job #{job_id} not found.")

        result = self.verifier.verify(
            job, is_url_reachable=is_url_reachable, portal_status=portal_status
        )
        new_status = sync_job_status_from_verification(job, result)
        self.job_repo.conn.execute(
            "UPDATE normalized_jobs SET status = ? WHERE id = ?",
            (new_status.value, job_id),
        )
        self.job_repo.conn.commit()
        return result

    # -------------------------------------------------------------------------
    # 2. Hard Eligibility & 7D Relevance Scoring / Ranking
    # -------------------------------------------------------------------------
    def evaluate_and_rank_all_jobs(
        self, eligible_only: bool = False, min_score: float = 0.0
    ) -> list[JobMatchResult]:
        """Score and rank all active jobs in the database."""
        jobs = self.job_repo.list_normalized_jobs()
        return self.ranker.rank_jobs(jobs, eligible_only=eligible_only, min_score=min_score)

    def get_top_india_opportunities(self, limit: int = 10) -> list[JobMatchResult]:
        """Retrieve top eligible opportunities in priority India tech hubs."""
        jobs = self.job_repo.list_normalized_jobs()
        return self.ranker.get_top_india_matches(jobs, limit=limit)

    def get_top_overseas_opportunities(self, limit: int = 10) -> list[JobMatchResult]:
        """Retrieve top eligible overseas opportunities with visa sponsorship tracking."""
        jobs = self.job_repo.list_normalized_jobs()
        return self.ranker.get_top_overseas_matches(jobs, limit=limit)

    # -------------------------------------------------------------------------
    # 3. Application Package Assembly (Resume + Interview Prep + Schedule)
    # -------------------------------------------------------------------------
    def prepare_application_package(
        self,
        job_id: int,
        target_interview_date: str | None = None,
    ) -> ApplicationPackage:
        """
        Assemble a complete Application Package for a target job:
        - Evaluates hard eligibility & itemized 7D match score.
        - Classifies role category.
        - Generates tailored resume candidate with ATS quality gate and Fact Integrity audit.
        - Gathers historical interview questions from Career Knowledge Base.
        - Creates pre-interview adaptive assessment & readiness evaluation.
        - Generates preparation schedule with approval gates.
        - Dispatches explicit user notification.
        """
        job = self.job_repo.get_normalized_job(job_id)
        if not job:
            raise ValueError(f"Job #{job_id} not found.")

        now_iso = datetime.now(UTC).isoformat()

        # 1. Evaluate Eligibility and 7D Score
        match_res = self.scoring_engine.score_job(job)
        role_res = self.role_classifier.classify(job.title, job.description or "")

        # 2. Prepare Tailored Resume Candidate
        tailored_resume = None
        ats_score = None
        ats_target_reached = False
        missing_skills_for_ats: list[str] = []
        fact_integrity_verified = False

        try:
            tailored_resume = self.resume_engine.generate_tailored_resume(job_id=job_id)
            ats_score = tailored_resume.ats_score
            ats_target_reached = (
                tailored_resume.ats_breakdown.quality_gate_met
                if tailored_resume.ats_breakdown
                else (ats_score >= 80.0)
            )
            missing_skills_for_ats = (
                tailored_resume.ats_breakdown.missing_skills
                if tailored_resume.ats_breakdown
                else []
            )
            fact_integrity_verified = tailored_resume.fact_integrity_status == "PASS"

            # Attach resume to application tracker
            self.resume_integration.prepare_application_with_resume(
                job_id=job_id, resume_id=tailored_resume.resume_id
            )
        except (ValueError, KeyError, RuntimeError, sqlite3.Error) as e:
            # If resume tailoring failed due to unverified facts or missing data, record details
            missing_skills_for_ats = [str(e)]

        # 3. Career Interview Intelligence
        review_pool = self.bank_service.build_review_pool_for_job(job)
        hist_count = len(review_pool.company_specific)
        weak_count = len(review_pool.weak_areas)
        job_req_count = len(review_pool.job_specific)

        # 4. Final Assessment & Readiness Scoring
        readiness_res = None
        try:
            readiness_res = self.assessment_engine.compute_job_readiness(job_id=job_id)
        except (ValueError, KeyError, sqlite3.Error):
            pass

        # 5. Preparation Schedule
        prep_schedule = None
        if target_interview_date:
            try:
                prep_schedule = self.assessment_engine.generate_preparation_schedule(
                    job_id=job_id, target_interview_date=target_interview_date
                )
            except (ValueError, KeyError, sqlite3.Error):
                pass

        # 6. Safety & Boundary Disclosures
        what_ai_prepared = [
            f"Normalized job details and verified active status ({job.status.value}).",
            f"Calculated 7-dimension job match score ({int(match_res.match_score)}/100).",
            f"Evaluated hard eligibility rules ({'ELIGIBLE' if match_res.is_eligible else 'INELIGIBLE'}).",
            f"Classified role as {role_res.category.value}.",
        ]
        if tailored_resume:
            what_ai_prepared.append(
                f"Generated ATS-friendly fact-grounded tailored resume (ATS Score: {ats_score}/100, Target Reached: {ats_target_reached})."
            )
        what_ai_prepared.append(
            f"Compiled interview review pool with {review_pool.total_unique_questions} questions ({hist_count} company-specific, {weak_count} weak areas)."
        )

        what_ai_did_not_do = [
            "DID NOT submit any external application.",
            "DID NOT open or automate third-party application forms without approval.",
            "DID NOT send external emails or calendar invites.",
            "DID NOT fabricate any skills, metrics, bug counts, or experience.",
            "DID NOT mark the application as APPLIED (Status remains READY_FOR_REVIEW awaiting human approval).",
        ]

        # 7. Update Application Status to READY_FOR_REVIEW
        app_record = self.job_repo.get_application_by_job_id(job_id)
        if app_record and app_record.id is not None:
            self.job_repo.update_application_status(
                app_record.id,
                ApplicationStatus.READY_FOR_REVIEW,
                notes=f"Application Package prepared. Job Match: {int(match_res.match_score)}/100. Awaiting human review.",
            )
            current_status = ApplicationStatus.READY_FOR_REVIEW
        else:
            current_status = ApplicationStatus.DISCOVERED

        # 8. Dispatch Informative Notification
        self.job_repo.create_notification(
            NotificationRecord(
                job_id=job_id,
                application_id=app_record.id if app_record else None,
                notification_type=NotificationType.HUMAN_APPROVAL_REQUIRED,
                title=f"Application Ready for Review: {job.title} at {job.company}",
                message=(
                    f"WHAT: Application Package prepared for {job.company} ({job.title}).\n"
                    f"SCORE: Job Match {int(match_res.match_score)}/100 | ATS Score: {ats_score or 0}/100.\n"
                    f"ELIGIBILITY: {'ELIGIBLE' if match_res.is_eligible else 'INELIGIBLE'}.\n"
                    f"INTERVIEW PREP: {review_pool.total_unique_questions} questions ready.\n"
                    "ACTION REQUIRED: Human approval needed before submitting application externally."
                ),
                created_at=now_iso,
            )
        )

        return ApplicationPackage(
            job_id=job_id,
            company=job.company,
            title=job.title,
            location=job.location,
            country=job.country,
            application_url=job.application_url,
            eligibility=match_res.hard_filters,
            match_result=match_res,
            role_classification=role_res,
            tailored_resume_id=tailored_resume.resume_id if tailored_resume else None,
            ats_score=ats_score,
            ats_target_reached=ats_target_reached,
            missing_skills_for_ats=missing_skills_for_ats,
            fact_integrity_verified=fact_integrity_verified,
            interview_pool_size=review_pool.total_unique_questions,
            historical_questions_count=hist_count,
            expected_questions_count=job_req_count,
            weak_areas_count=weak_count,
            readiness_assessment=readiness_res,
            preparation_schedule=prep_schedule,
            application_status=current_status,
            human_approval_state="AWAITING_REVIEW",
            what_ai_prepared=what_ai_prepared,
            what_ai_did_not_do=what_ai_did_not_do,
            generated_at=now_iso,
        )

    # -------------------------------------------------------------------------
    # 4. Human Approval Workflow & Confirmed Submission
    # -------------------------------------------------------------------------
    def review_application(
        self,
        application_id: int,
        decision: str,  # "APPROVE", "REJECT", "EDIT"
        notes: str | None = None,
    ) -> ApplicationRecord:
        """
        Process human review decision on a prepared application.
        - APPROVE -> status becomes APPROVED (never APPLIED).
        - REJECT -> status becomes REJECTED.
        - EDIT -> status returns to PREPARING.
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
                notes=notes or "Application approved by candidate for submission.",
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
                    notes=notes or "Human candidate explicitly approved application package.",
                )
            )
            self.job_repo.create_notification(
                NotificationRecord(
                    job_id=app.job_id,
                    application_id=application_id,
                    notification_type=NotificationType.STATUS_CHANGED,
                    title=f"Application Approved: {title} at {company}",
                    message=f"Application for {company} is approved and ready for candidate submission.",
                    created_at=now_iso,
                )
            )
        elif decision_upper == "REJECT":
            self.job_repo.update_application_status(
                application_id,
                ApplicationStatus.REJECTED,
                notes=notes or "Application rejected during candidate review.",
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
                    notes=notes or "Candidate declined this opportunity.",
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

    def record_submission(
        self,
        application_id: int,
        reference_id: str | None = None,
        submission_evidence: str | None = None,
        notes: str | None = None,
    ) -> ApplicationRecord:
        """
        Record confirmed manual application submission.
        Status transitions to APPLIED only when confirmed.
        """
        app = self.job_repo.get_application(application_id)
        if not app:
            raise ValueError(f"Application #{application_id} not found.")

        job = self.job_repo.get_normalized_job(app.job_id)
        now_iso = datetime.now(UTC).isoformat()

        # Update application record
        self.job_repo.conn.execute(
            "UPDATE applications SET status = ?, applied_at = ?, notes = ?, updated_at = ? WHERE id = ?",
            (
                ApplicationStatus.APPLIED.value,
                now_iso,
                notes or f"Application submitted manually. Ref: {reference_id or 'N/A'}",
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
                company=job.company if job else "Company",
                role_title=job.title if job else "Role",
                location=job.location if job else None,
                source=job.source if job else "portal",
                official_application_url=job.application_url if job else None,
                timestamp=now_iso,
                application_status=ApplicationStatus.APPLIED,
                reference_id=reference_id,
                submission_evidence=submission_evidence,
                notes=notes or "Confirmed successful external application submission.",
            )
        )

        # User Notification
        self.job_repo.create_notification(
            NotificationRecord(
                job_id=app.job_id,
                application_id=application_id,
                notification_type=NotificationType.SUBMISSION_SUCCESS,
                title=f"Application Submitted: {job.title if job else 'Role'} at {job.company if job else 'Company'}",
                message=(
                    f"Confirmed application submission for {job.company if job else 'Company'}.\n"
                    f"Reference ID: {reference_id or 'None'}\n"
                    f"Timestamp: {now_iso}"
                ),
                created_at=now_iso,
            )
        )

        updated_app = self.job_repo.get_application(application_id)
        if not updated_app:
            raise ValueError(f"Application #{application_id} could not be retrieved.")
        return updated_app

    # -------------------------------------------------------------------------
    # 5. Dashboard Summary Provider
    # -------------------------------------------------------------------------
    def get_dashboard_summary(self) -> dict[str, Any]:
        """Compile a real-time 'TODAY' summary for the Streamlit dashboard."""
        all_jobs = self.job_repo.list_normalized_jobs()
        all_apps = self.job_repo.list_applications()
        all_weaks = self.career_repo.list_weak_areas(resolved=False)
        top_india = self.get_top_india_opportunities(limit=5)
        top_overseas = self.get_top_overseas_opportunities(limit=5)

        awaiting_approval = [a for a in all_apps if a.status == ApplicationStatus.READY_FOR_REVIEW]
        submitted_apps = [a for a in all_apps if a.status == ApplicationStatus.APPLIED]

        return {
            "total_discovered_jobs": len(all_jobs),
            "top_india_opportunities": [
                {
                    "company": r.company,
                    "title": r.title,
                    "location": r.location,
                    "match_score": r.match_score,
                    "is_eligible": r.is_eligible,
                }
                for r in top_india
            ],
            "top_overseas_opportunities": [
                {
                    "company": r.company,
                    "title": r.title,
                    "country": r.country,
                    "match_score": r.match_score,
                    "requires_sponsorship": r.requires_sponsorship,
                }
                for r in top_overseas
            ],
            "applications_awaiting_approval_count": len(awaiting_approval),
            "applications_submitted_count": len(submitted_apps),
            "unresolved_weak_areas_count": len(all_weaks),
            "unresolved_weak_areas": [w.topic for w in all_weaks[:5]],
        }
