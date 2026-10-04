import sqlite3
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.career.assessment import AdaptiveAssessmentEngine
from app.career.bank import QuestionBankService, QuestionReviewPool
from app.career.ingestion import CareerIngestionService, IngestionResult
from app.career.notifications import (
    ProposedScheduleNotification,
    ScheduleNotificationService,
)
from app.career.pack import InterviewPack, InterviewPackGenerator
from app.career.repository import CareerRepository
from app.db.models import (
    ApplicationEvent,
    ApplicationEventType,
    AssessmentRecord,
    InterviewQuestion,
    InterviewSession,
    PreparationSchedule,
    ReadinessAssessment,
    ScheduleMilestone,
    WeakArea,
)
from app.db.repository import JobRepository


class InterviewQuestionOutcome(BaseModel):
    """Details of a specific question asked during a real technical/HR interview."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question: str = Field(..., min_length=5)
    topic: str = Field(..., min_length=2)
    difficulty: str = Field(default="medium")
    user_answer: str | None = None
    expected_answer: str | None = None
    was_correct: bool = True
    feedback: str | None = None


class InterviewOutcomeDebrief(BaseModel):
    """Complete post-interview debrief payload for career knowledge learning loop."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    company: str = Field(..., min_length=1)
    role: str = Field(..., min_length=1)
    round: str = Field(..., min_length=1)
    date: str = Field(..., description="ISO-8601 date string.")
    outcome: str = Field(..., description="'passed', 'rejected', 'offer', 'next_round'")
    general_feedback: str | None = None
    questions: list[InterviewQuestionOutcome] = Field(default_factory=list)
    application_id: int | None = None


class InterviewOutcomeReport(BaseModel):
    """Structured report returned after processing an interview outcome."""

    model_config = ConfigDict(extra="forbid")

    session_id: int
    company: str
    role: str
    outcome: str
    questions_logged: int
    weak_areas_created: int
    weak_areas_updated: int
    message: str


class PipelineExecutionSummary(BaseModel):
    """Summary record for an end-to-end pipeline execution."""

    model_config = ConfigDict(extra="forbid")

    job_id: int
    company: str
    role: str
    question_pool_count: int
    assessment_id: int | None = None
    assessment_score: float | None = None
    readiness_score: float
    readiness_level: str
    schedule_id: int
    proposed_notifications: list[ProposedScheduleNotification] = Field(default_factory=list)



class HistoricalInterviewPipeline:
    """End-to-end pipeline coordinating ingestion, preparation pools, final testing, readiness evaluation, and approval-gated scheduling."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.job_repo = JobRepository(conn)
        self.career_repo = CareerRepository(conn)
        self.ingestion_service = CareerIngestionService(self.career_repo)
        self.assessment_engine = AdaptiveAssessmentEngine(conn, self.career_repo, self.job_repo)
        self.bank_service = QuestionBankService(conn, self.career_repo)
        self.notification_service = ScheduleNotificationService(conn)
        self.pack_generator = InterviewPackGenerator(
            self.job_repo, self.career_repo, self.assessment_engine, self.bank_service
        )

    # 1. Ingestion
    def import_historical_data_from_file(self, file_path: str) -> IngestionResult:
        """Import historical interviews, mock records, and verified knowledge items from a YAML/JSON file."""
        return self.ingestion_service.import_from_file(file_path)

    # 2. Complete Question Review Pool
    def get_job_question_pool(self, job_id: int) -> QuestionReviewPool:
        """Generate the complete 8-category question review pool for a target job."""
        job = self.job_repo.get_normalized_job(job_id)
        if not job:
            raise ValueError(f"Job #{job_id} not found.")
        return self.bank_service.build_review_pool_for_job(job)

    # 3. Adaptive Final Assessment Generation & Scoring
    def create_final_assessment(self, job_id: int, time_limit_minutes: int = 60) -> AssessmentRecord:
        """Create a final pre-interview assessment drill covering job requirements and candidate weak areas."""
        return self.assessment_engine.generate_pre_interview_assessment(
            job_id=job_id, time_limit_minutes=time_limit_minutes
        )

    def submit_final_assessment(
        self, assessment_id: int, user_answers: list[dict[str, Any]]
    ) -> AssessmentRecord:
        """Submit candidate answers, score assessment, update topic stats, and adapt weak areas."""
        return self.assessment_engine.submit_assessment_answers(
            assessment_id=assessment_id, user_answers=user_answers
        )

    # 4. Readiness Evaluation
    def calculate_readiness(
        self,
        job_id: int,
        ready_threshold: float = 80.0,
        critical_topic_ready_min: float = 65.0,
        borderline_threshold: float = 65.0,
        critical_topic_fail_min: float = 60.0,
        critical_topics: list[str] | None = None,
    ) -> ReadinessAssessment:
        """Evaluate candidate readiness score and check configurable readiness gates."""
        return self.assessment_engine.compute_job_readiness(
            job_id=job_id,
            ready_threshold=ready_threshold,
            critical_topic_ready_min=critical_topic_ready_min,
            borderline_threshold=borderline_threshold,
            critical_topic_fail_min=critical_topic_fail_min,
            critical_topics=critical_topics,
        )

    # 5. Scheduling & Email/Calendar Proposal Generation (Human Approval Required)
    def propose_scheduling_and_notifications(
        self,
        job_id: int,
        target_interview_date: str,
        destination_email: str,
    ) -> dict[str, Any]:
        """
        Generate a multi-day preparation schedule and create draft email/calendar proposals.
        Guaranteed human-in-the-loop: all external actions start in unapproved / proposed state.
        """
        job = self.job_repo.get_normalized_job(job_id)
        if not job:
            raise ValueError(f"Job #{job_id} not found.")

        # 1. Generate schedule with unapproved milestones
        schedule: PreparationSchedule = self.assessment_engine.generate_preparation_schedule(
            job_id=job_id, target_interview_date=target_interview_date
        )

        # 2. Draft Email Notification Proposal
        email_prop = self.notification_service.propose_schedule_notification(
            notification_type="email_reminder",
            destination=destination_email,
            target_company=job.company,
            target_role=job.title,
            scheduled_time=target_interview_date,
            action_type="interview_prep_schedule",
            subject=f"DV Interview Preparation Schedule: {job.title} at {job.company}",
            body_content=(
                f"Proposed preparation schedule for your upcoming interview with {job.company}.\n"
                f"Milestones planned: {len(schedule.milestones)} sessions covering {', '.join(job.skills[:4])}.\n"
                "Please review and approve in the Career Operating System dashboard."
            ),
            rationale=f"Automated schedule proposal for target interview on {target_interview_date}.",
        )

        # 3. Draft Calendar Event Proposal
        cal_prop = self.notification_service.propose_schedule_notification(
            notification_type="calendar_event",
            destination="Candidate Primary Calendar",
            target_company=job.company,
            target_role=job.title,
            scheduled_time=target_interview_date,
            action_type="final_assessment_block",
            subject=f"Prep Block: Final Assessment for {job.company}",
            body_content=f"Focused 60-minute pre-interview review block for {job.title}.",
            rationale="Reserved preparation calendar block.",
        )

        return {
            "schedule": schedule,
            "proposed_notifications": [email_prop, cal_prop],
        }

    # 6. Human Approval Actions
    def approve_schedule_milestone(
        self, schedule_id: int, milestone_index: int
    ) -> ScheduleMilestone:
        """Candidate approval for a specific preparation schedule milestone."""
        return self.assessment_engine.approve_schedule_milestone(schedule_id, milestone_index)

    def approve_notification(self, proposal_id: int) -> ProposedScheduleNotification:
        """Candidate approval for sending an email reminder or creating a calendar event."""
        return self.notification_service.approve_proposal(proposal_id)

    def reject_notification(self, proposal_id: int) -> ProposedScheduleNotification:
        """Candidate rejection for an email reminder or calendar event."""
        return self.notification_service.reject_proposal(proposal_id)

    # 7. Consolidated Pack
    def generate_interview_pack(self, job_id: int) -> InterviewPack:
        """Generate the comprehensive 17-point revision pack."""
        return self.pack_generator.generate_interview_pack(job_id)

    # 8. Real Interview Debrief & Learning Loop
    def record_interview_outcome(
        self, debrief: InterviewOutcomeDebrief
    ) -> InterviewOutcomeReport:
        """
        Ingest real interview debrief data, updating Question Bank with provenance,
        adapting candidate weak areas, and closing the career learning loop.
        """
        now_iso = datetime.now(UTC).isoformat()

        # 1. Insert Interview Session
        session = InterviewSession(
            company=debrief.company,
            role=debrief.role,
            date=debrief.date,
            round=debrief.round,
            outcome=debrief.outcome,
            notes=debrief.general_feedback,
            created_at=now_iso,
        )
        session_id = self.career_repo.insert_interview_session(session)

        # 2. Ingest questions and update weak areas
        questions_logged = 0
        weak_areas_created = 0
        weak_areas_updated = 0

        existing_all = self.career_repo.get_all_questions()
        existing_lookup = {q.question.strip().lower(): q for q in existing_all}

        for q in debrief.questions:
            q_clean = q.question.strip().lower()
            if q_clean in existing_lookup:
                matched_q = existing_lookup[q_clean]
                if matched_q.id is not None:
                    was_cor_int = 1 if q.was_correct else 0
                    self.conn.execute(
                        """
                        UPDATE interview_questions
                        SET times_asked = times_asked + 1,
                            was_correct = ?,
                            feedback = ?,
                            user_answer = ?
                        WHERE id = ?
                        """,
                        (was_cor_int, q.feedback or matched_q.feedback, q.user_answer, matched_q.id),
                    )
                    self.conn.commit()
                    questions_logged += 1
            else:
                new_q = InterviewQuestion(
                    session_id=session_id,
                    company=debrief.company,
                    role=debrief.role,
                    question=q.question,
                    topic=q.topic,
                    category="Technical" if q.topic != "HR" else "Behavioral",
                    user_answer=q.user_answer,
                    expected_answer=q.expected_answer,
                    feedback=q.feedback,
                    was_correct=q.was_correct,
                    difficulty=q.difficulty,
                    source=f"Real Interview: {debrief.company} ({debrief.round})",
                    verified=True,
                    times_asked=1,
                    created_at=now_iso,
                )
                self.career_repo.insert_interview_question(new_q)
                questions_logged += 1

            if not q.was_correct:
                existing_weaks = self.career_repo.list_weak_areas(resolved=False, topic=q.topic)
                if existing_weaks:
                    w = existing_weaks[0]
                    if w.id is not None:
                        new_conf = max(0.1, round(w.confidence - 0.15, 2))
                        self.conn.execute(
                            """
                            UPDATE weak_areas
                            SET review_count = review_count + 1,
                                confidence = ?,
                                last_reviewed = ?
                            WHERE id = ?
                            """,
                            (new_conf, now_iso, w.id),
                        )
                        self.conn.commit()
                        weak_areas_updated += 1
                else:
                    new_wa = WeakArea(
                        topic=q.topic,
                        description=f"Real interview gap at {debrief.company} ({debrief.round}): '{q.question[:100]}'",
                        evidence_source=f"Real Interview: {debrief.company} ({debrief.round})",
                        severity="high",
                        confidence=0.35,
                        created_at=now_iso,
                    )
                    self.career_repo.insert_weak_area(new_wa)
                    weak_areas_created += 1

        # 3. If application ID is linked, audit the interview event
        if debrief.application_id is not None:
            app = self.job_repo.get_application(debrief.application_id)
            if app and app.id is not None:
                job = self.job_repo.get_normalized_job(app.job_id)
                self.job_repo.record_application_event(
                    ApplicationEvent(
                        application_id=app.id,
                        job_id=app.job_id,
                        event_type=ApplicationEventType.STATUS_CHANGED,
                        company=job.company if job else debrief.company,
                        role_title=job.title if job else debrief.role,
                        location=job.location if job else None,
                        source="career_buddy",
                        official_application_url=job.application_url if job else None,
                        timestamp=now_iso,
                        resume_version=None,
                        cover_letter_version=None,
                        application_status=app.status,
                        reference_id=None,
                        submission_evidence=None,
                        notes=f"Interview round '{debrief.round}' debrief recorded. Outcome: {debrief.outcome.upper()}",
                    )
                )

        return InterviewOutcomeReport(
            session_id=session_id,
            company=debrief.company,
            role=debrief.role,
            outcome=debrief.outcome,
            questions_logged=questions_logged,
            weak_areas_created=weak_areas_created,
            weak_areas_updated=weak_areas_updated,
            message=f"Successfully ingested interview debrief from {debrief.company} ({debrief.round}). Logged {questions_logged} questions, updated/created {weak_areas_created + weak_areas_updated} weak area tracks.",
        )

