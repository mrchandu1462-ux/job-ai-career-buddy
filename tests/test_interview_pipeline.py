"""Tests for the end-to-end Historical Interview Import + Final Assessment Pipeline."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.career.notifications import NotificationDispatchStatus
from app.career.pipeline import HistoricalInterviewPipeline
from app.db.connection import get_db
from app.db.models import AssessmentStatus, JobStatus, NormalizedJob
from app.db.repository import JobRepository


@pytest.fixture
def db_conn():
    with get_db(":memory:") as conn:
        yield conn


@pytest.fixture
def pipeline(db_conn):
    return HistoricalInterviewPipeline(db_conn)


@pytest.fixture
def target_job_id(db_conn):
    job_repo = JobRepository(db_conn)
    job = NormalizedJob(
        company="Qualcomm India",
        title="Design Verification Engineer",
        location="Bengaluru",
        country="India",
        skills=["UVM Components", "Clock Domain Crossing", "Async FIFO", "AXI Protocol", "SystemVerilog Assertions"],
        source="manual",
        status=JobStatus.ACTIVE,
        first_seen="2026-10-04T10:00:00Z",
        last_seen="2026-10-04T10:00:00Z",
        fingerprint="qualcomm-dv-pipeline-test-01",
    )
    return job_repo.insert_normalized_job(job)


def test_import_historical_data_from_yaml(pipeline):
    """Test importing verified historical interviews from profile/historical_interviews.yaml."""
    yaml_path = Path("profile/historical_interviews.yaml")
    assert yaml_path.exists(), "profile/historical_interviews.yaml must exist"

    result = pipeline.import_historical_data_from_file(str(yaml_path))

    assert result.session_id is not None
    assert result.questions_inserted == 7
    assert result.weak_areas_inserted == 2
    assert result.knowledge_items_inserted == 2
    assert len(result.errors) == 0

    # Test re-importing the same file -> questions should be deduplicated (times_asked incremented)
    result_dup = pipeline.import_historical_data_from_file(str(yaml_path))
    assert result_dup.questions_deduplicated == 7
    assert result_dup.questions_inserted == 0


def test_get_job_question_review_pool(pipeline, target_job_id):
    """Test generating the complete 8-category review pool for the target job."""
    pipeline.import_historical_data_from_file("profile/historical_interviews.yaml")

    review_pool = pipeline.get_job_question_pool(target_job_id)

    assert review_pool.job_id == target_job_id
    assert review_pool.company == "Qualcomm India"
    assert review_pool.total_unique_questions == 7
    assert len(review_pool.company_specific) == 2  # 2 Qualcomm questions
    assert len(review_pool.job_specific) >= 5
    assert len(review_pool.previously_missed) >= 2  # CDC & CRV missed
    assert len(review_pool.weak_areas) >= 1  # CDC weak area


def test_run_adaptive_final_assessment_and_feedback(pipeline, target_job_id):
    """Test generating, attempting, and scoring the final pre-interview assessment."""
    pipeline.import_historical_data_from_file("profile/historical_interviews.yaml")

    # 1. Create final assessment
    assessment = pipeline.create_final_assessment(target_job_id, time_limit_minutes=60)
    assert assessment.id is not None
    assert assessment.status == AssessmentStatus.CREATED
    assert len(assessment.questions) > 0

    # 2. Submit answers (answering questions with feedback)
    user_answers = [
        {
            "question_id": q.question_id,
            "user_answer": "Candidate verified response",
            "was_correct": (i % 2 == 0),
            "time_spent_seconds": 90,
            "feedback": "Evaluated during pipeline test.",
        }
        for i, q in enumerate(assessment.questions)
    ]

    scored = pipeline.submit_final_assessment(assessment.id, user_answers)
    assert scored.status == AssessmentStatus.COMPLETED
    assert scored.score is not None
    assert scored.completed_at is not None
    assert len(scored.topic_breakdown) > 0


def test_readiness_calculation_and_gates(pipeline, target_job_id):
    """Test readiness score calculation and readiness gates."""
    pipeline.import_historical_data_from_file("profile/historical_interviews.yaml")

    readiness = pipeline.calculate_readiness(
        target_job_id,
        ready_threshold=80.0,
        critical_topic_ready_min=65.0,
    )

    assert readiness.job_id == target_job_id
    assert 0.0 <= readiness.overall_readiness_score <= 100.0
    # Because CDC has active weak area with 0.35 confidence, CDC is < 60% fail threshold -> Needs Preparation
    assert readiness.readiness_level in ["Needs Preparation", "Moderate Readiness"]
    assert "Clock Domain Crossing" in readiness.weak_topics


def test_propose_scheduling_and_notifications_with_human_approval(pipeline, target_job_id):
    """Test schedule proposal, notification generation, and mandatory candidate approval gates."""
    pipeline.import_historical_data_from_file("profile/historical_interviews.yaml")
    target_date = (datetime.now(UTC).date() + timedelta(days=5)).isoformat()

    proposal_bundle = pipeline.propose_scheduling_and_notifications(
        job_id=target_job_id,
        target_interview_date=target_date,
        destination_email="candidate@vlsi-cos.internal",
    )

    schedule = proposal_bundle["schedule"]
    notifications = proposal_bundle["proposed_notifications"]

    assert schedule.id is not None
    assert len(schedule.milestones) >= 4
    # All milestones require human approval and are unapproved by default
    assert all(m.requires_user_approval and not m.approved for m in schedule.milestones)

    # Notifications are created in PROPOSED state awaiting human confirmation
    assert len(notifications) == 2
    email_notif = notifications[0]
    cal_notif = notifications[1]
    assert email_notif.status == NotificationDispatchStatus.PROPOSED
    assert cal_notif.status == NotificationDispatchStatus.PROPOSED

    # Candidate explicitly approves milestone 0
    approved_milestone = pipeline.approve_schedule_milestone(schedule.id, milestone_index=0)
    assert approved_milestone.approved is True

    # Candidate approves email notification
    approved_email = pipeline.approve_notification(email_notif.id)
    assert approved_email.status == NotificationDispatchStatus.APPROVED
    assert approved_email.approved_at is not None

    # Candidate rejects calendar event
    rejected_cal = pipeline.reject_notification(cal_notif.id)
    assert rejected_cal.status == NotificationDispatchStatus.REJECTED


def test_generate_consolidated_pack_via_pipeline(pipeline, target_job_id):
    """Test generating the consolidated 17-point interview pack."""
    pipeline.import_historical_data_from_file("profile/historical_interviews.yaml")

    pack = pipeline.generate_interview_pack(target_job_id)
    assert pack.company == "Qualcomm India"
    assert pack.role == "Design Verification Engineer"
    assert len(pack.historical_questions) >= 2
    assert len(pack.expected_coding_questions) >= 4
    assert len(pack.final_revision_checklist) >= 5


def test_record_interview_outcome_and_learning_loop(pipeline, db_conn, target_job_id):
    """Test recording real interview debrief, updating question bank, and updating weak area tracks."""
    from app.career.pipeline import InterviewOutcomeDebrief, InterviewQuestionOutcome
    from app.db.models import ApplicationRecord, ApplicationStatus

    job_repo = JobRepository(db_conn)
    app_id = job_repo.create_application(
        ApplicationRecord(
            job_id=target_job_id,
            status=ApplicationStatus.APPLIED,
            created_at="2026-10-04T10:00:00Z",
            updated_at="2026-10-04T10:00:00Z",
        )
    )

    debrief = InterviewOutcomeDebrief(
        company="NVIDIA",
        role="Design Verification Engineer",
        round="Round 2 Technical",
        date="2026-10-04T15:00:00Z",
        outcome="next_round",
        general_feedback="Solid digital design, but struggled on multi-clock SVA assertions.",
        application_id=app_id,
        questions=[
            InterviewQuestionOutcome(
                question="Explain setup and hold time margin in clock domain crossings.",
                topic="Clock Domain Crossing",
                difficulty="hard",
                user_answer="Candidate explained MTBF and 2FF synchronizers accurately.",
                expected_answer="Setup/hold checks with multi-cycle and set_false_path exceptions.",
                was_correct=True,
                feedback="Clear and accurate explanation.",
            ),
            InterviewQuestionOutcome(
                question="How do you write a multi-clock concurrent SVA assertion with $rose and event expressions?",
                topic="SystemVerilog Assertions",
                difficulty="hard",
                user_answer="Struggled on multi-clock preponed sampling region.",
                expected_answer="Use sequence with ##1 and @(posedge clk2) binding.",
                was_correct=False,
                feedback="Review multi-clock SVA semantics and clocking blocks.",
            ),
        ],
    )

    report = pipeline.record_interview_outcome(debrief)

    assert report.session_id is not None
    assert report.company == "NVIDIA"
    assert report.questions_logged == 2
    assert report.weak_areas_created >= 1

    # Verify questions are now in question bank with verified=True
    all_qs = pipeline.career_repo.get_questions_by_company("NVIDIA")
    assert len(all_qs) == 2
    assert all(q.verified for q in all_qs)

    # Verify weak area was registered for SVA
    sva_weaks = pipeline.career_repo.list_weak_areas(topic="SystemVerilog Assertions")
    assert len(sva_weaks) >= 1
    assert sva_weaks[0].severity == "high"
    assert sva_weaks[0].confidence <= 0.35

    # Verify application audit event was logged
    events = job_repo.get_application_events(app_id)
    assert len(events) >= 1
    assert "Round 2 Technical" in events[-1].notes

