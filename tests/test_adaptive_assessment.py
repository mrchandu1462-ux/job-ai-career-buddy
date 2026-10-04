"""Tests for Adaptive Assessment Engine, Remediation, Scoring, and Preparation Scheduling."""

from datetime import UTC, datetime, timedelta

import pytest

from app.career.assessment import AdaptiveAssessmentEngine
from app.career.ingestion import (
    CareerIngestionService,
    CareerIngestPayload,
    QuestionIngestItem,
    WeakAreaIngestItem,
)
from app.career.repository import CareerRepository
from app.db.connection import get_db
from app.db.models import (
    AssessmentStatus,
    AssessmentType,
    JobStatus,
    NormalizedJob,
)
from app.db.repository import JobRepository


@pytest.fixture
def db_conn():
    with get_db(":memory:") as conn:
        yield conn


@pytest.fixture
def career_repo(db_conn):
    return CareerRepository(db_conn)


@pytest.fixture
def job_repo(db_conn):
    return JobRepository(db_conn)


@pytest.fixture
def assessment_engine(db_conn, career_repo, job_repo):
    return AdaptiveAssessmentEngine(db_conn, career_repo, job_repo)


@pytest.fixture
def seeded_knowledge_base(career_repo, job_repo):
    ingest = CareerIngestionService(career_repo)
    payload = CareerIngestPayload(
        source="Qualcomm & Synopsys Historical Prep",
        source_type="interview",
        questions=[
            QuestionIngestItem(
                company="Qualcomm",
                role="Design Verification Engineer",
                question="Explain how UVM TLM FIFO differs from standard TLM mailbox.",
                topic="UVM TLM",
                expected_answer="TLM FIFO provides unbounded/bounded storage with built-in put/get export implementations.",
                was_correct=True,
                source="Qualcomm Interview",
                verified=True,
            ),
            QuestionIngestItem(
                company="Qualcomm",
                role="Design Verification Engineer",
                question="What is the hazard with using $rose in a multi-clock assertion?",
                topic="SystemVerilog Assertions",
                expected_answer="$rose samples values in preponed region of the assertion clock domain.",
                was_correct=False,
                source="Qualcomm Mock 2",
                verified=True,
            ),
            QuestionIngestItem(
                company="Qualcomm",
                role="Design Verification Engineer",
                question="How do you handle constraint conflicts with solve...before in SystemVerilog?",
                topic="SystemVerilog Randomization",
                expected_answer="solve...before only modifies probability distribution, it cannot resolve logical contradictions in constraints.",
                was_correct=True,
                source="Synopsys Prep",
                verified=True,
            ),
        ],
        weak_areas=[
            WeakAreaIngestItem(
                topic="SystemVerilog Assertions",
                description="Trouble with multi-clock assertion sampling edge cases.",
                severity="high",
                confidence=0.35,
            )
        ],
    )
    ingest.ingest_payload(payload)

    job = NormalizedJob(
        company="Qualcomm India",
        title="Design Verification Engineer",
        location="Bengaluru",
        country="India",
        skills=["UVM TLM", "SystemVerilog Assertions", "SystemVerilog Randomization"],
        source="manual",
        status=JobStatus.ACTIVE,
        first_seen="2026-10-04T10:00:00Z",
        last_seen="2026-10-04T10:00:00Z",
        fingerprint="qualcomm-dv-blr-assess-01",
    )
    job_id = job_repo.insert_normalized_job(job)
    return job_id


def test_generate_timed_mock_test(assessment_engine, seeded_knowledge_base):
    """Test generating a timed mock test with question limits and target duration."""
    job_id = seeded_knowledge_base
    mock_test = assessment_engine.generate_mock_test(
        job_id=job_id, time_limit_minutes=30, num_questions=3
    )

    assert mock_test.id is not None
    assert mock_test.assessment_type == AssessmentType.TIMED_MOCK
    assert mock_test.time_limit_minutes == 30
    assert len(mock_test.questions) == 3
    assert mock_test.status == AssessmentStatus.CREATED
    assert "Qualcomm" in mock_test.title


def test_generate_final_pre_interview_assessment(assessment_engine, seeded_knowledge_base):
    """Test generating a final comprehensive pre-interview readiness assessment."""
    job_id = seeded_knowledge_base
    pre_int = assessment_engine.generate_pre_interview_assessment(
        job_id=job_id, time_limit_minutes=60
    )

    assert pre_int.id is not None
    assert pre_int.assessment_type == AssessmentType.PRE_INTERVIEW
    assert pre_int.time_limit_minutes == 60
    assert len(pre_int.questions) >= 3
    assert pre_int.company == "Qualcomm India"


def test_scoring_and_adaptive_weak_area_feedback(assessment_engine, career_repo, seeded_knowledge_base):
    """Test submitting answers, scoring, and automatic weak area adaptation."""
    job_id = seeded_knowledge_base
    mock_test = assessment_engine.generate_mock_test(job_id=job_id, num_questions=3)

    q1 = mock_test.questions[0]
    q2 = mock_test.questions[1]
    q3 = mock_test.questions[2]

    # Submit 2 correct, 1 incorrect
    answers = [
        {"question_id": q1.question_id, "user_answer": "Candidate answer 1", "was_correct": True, "time_spent_seconds": 120},
        {"question_id": q2.question_id, "user_answer": "Candidate answer 2", "was_correct": False, "time_spent_seconds": 180},
        {"question_id": q3.question_id, "user_answer": "Candidate answer 3", "was_correct": True, "time_spent_seconds": 90},
    ]

    scored = assessment_engine.submit_assessment_answers(mock_test.id, answers)
    assert scored.status == AssessmentStatus.COMPLETED
    assert scored.score == 66.7
    assert scored.correct_count == 2
    assert scored.incorrect_count == 1
    assert scored.completed_at is not None

    # Check topic breakdown
    assert len(scored.topic_breakdown) >= 2

    # Verify that the missed topic (q2.topic) triggered a weak-area update
    weak_areas = career_repo.list_weak_areas(topic=q2.topic)
    assert len(weak_areas) >= 1
    assert weak_areas[0].confidence <= 0.35  # Confidence reduced/adjusted


def test_remediation_test_isolates_mistakes(assessment_engine, seeded_knowledge_base):
    """Test generating a follow-up remediation test targeting questions answered incorrectly."""
    job_id = seeded_knowledge_base
    mock_test = assessment_engine.generate_mock_test(job_id=job_id, num_questions=2)

    # Mark first question correct, second incorrect
    q_incorrect = mock_test.questions[1]
    answers = [
        {"question_id": mock_test.questions[0].question_id, "was_correct": True},
        {"question_id": q_incorrect.question_id, "was_correct": False, "user_answer": "Wrong answer"},
    ]
    assessment_engine.submit_assessment_answers(mock_test.id, answers)

    # Generate remediation test targeting the previous assessment
    remediation = assessment_engine.generate_remediation_test(
        previous_assessment_id=mock_test.id, time_limit_minutes=25
    )

    assert remediation.id is not None
    assert remediation.assessment_type == AssessmentType.REMEDIATION
    assert remediation.time_limit_minutes == 25
    assert len(remediation.questions) >= 1
    assert any(q.question_id == q_incorrect.question_id for q in remediation.questions)


def test_job_readiness_scoring(assessment_engine, seeded_knowledge_base):
    """Test objective job readiness evaluation calculation."""
    job_id = seeded_knowledge_base
    readiness = assessment_engine.compute_job_readiness(job_id)

    assert readiness.job_id == job_id
    assert 0.0 <= readiness.overall_readiness_score <= 100.0
    assert readiness.readiness_level in ["High Readiness", "Moderate Readiness", "Needs Preparation"]
    assert len(readiness.topic_scores) > 0
    assert readiness.recommended_action is not None


def test_preparation_schedule_and_user_approval_gates(assessment_engine, seeded_knowledge_base):
    """Test schedule generation and human-in-the-loop milestone approval."""
    job_id = seeded_knowledge_base
    target_interview = (datetime.now(UTC).date() + timedelta(days=7)).isoformat()

    schedule = assessment_engine.generate_preparation_schedule(
        job_id=job_id, target_interview_date=target_interview
    )

    assert schedule.id is not None
    assert len(schedule.milestones) >= 4

    # Milestones must require approval and be unapproved by default
    for m in schedule.milestones:
        assert m.requires_user_approval is True
        assert m.approved is False

    # Perform candidate approval on milestone 0
    approved_m = assessment_engine.approve_schedule_milestone(schedule.id, milestone_index=0)
    assert approved_m.approved is True
