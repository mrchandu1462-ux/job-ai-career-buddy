"""Tests for Career Knowledge Ingestion, Deduplication, and Preparation Engine."""

import pytest

from app.career.engine import PreparationEngine
from app.career.ingestion import (
    CareerIngestionService,
    CareerIngestPayload,
    KnowledgeIngestItem,
    QuestionIngestItem,
    WeakAreaIngestItem,
    normalize_question_text,
)
from app.career.repository import CareerRepository
from app.db.connection import get_db
from app.db.models import (
    InterviewSession,
    JobStatus,
    NormalizedJob,
)
from app.db.repository import JobRepository


@pytest.fixture
def db_conn():
    """Yields an initialized in-memory database connection."""
    with get_db(":memory:") as conn:
        yield conn


@pytest.fixture
def career_repo(db_conn):
    return CareerRepository(db_conn)


@pytest.fixture
def job_repo(db_conn):
    return JobRepository(db_conn)


@pytest.fixture
def ingest_service(career_repo):
    return CareerIngestionService(career_repo)


@pytest.fixture
def prep_engine(career_repo, job_repo):
    return PreparationEngine(career_repo, job_repo)


def test_question_text_normalization():
    """Verify deterministic string normalization."""
    q1 = "What is the difference between $display and $write in Verilog?"
    q2 = "what is the difference between $display and $write in verilog??  "
    assert normalize_question_text(q1) == normalize_question_text(q2)


def test_batch_ingestion_and_provenance(ingest_service, career_repo):
    """Test importing a batch payload and verifying that provenance is strictly preserved."""
    payload = CareerIngestPayload(
        source="Texas Instruments Campus Interview 2025",
        source_type="interview",
        original_reference="Round 1 Technical Sheet",
        session=InterviewSession(
            company="Texas Instruments",
            role="Design Verification Engineer",
            date="2026-08-20",
            round="Technical 1",
            outcome="passed",
            notes="Focused on SystemVerilog assertions and UVM sequence items.",
            created_at="2026-08-20T10:00:00Z",
        ),
        questions=[
            QuestionIngestItem(
                question="Explain concurrent assertions vs immediate assertions in SystemVerilog.",
                topic="SystemVerilog Assertions",
                category="technical",
                user_answer="Concurrent assertions are evaluated at clock edge.",
                expected_answer="Concurrent assertions execute over time based on clock cycles using sampled values; immediate assertions execute in procedural code like if-statements.",
                was_correct=True,
                source="TI Technical Interview 2025",
                source_type="interview",
                original_reference="Q1",
                verified=True,
            )
        ],
        weak_areas=[
            WeakAreaIngestItem(
                topic="SystemVerilog Assertions",
                description="Need more practice with antecedent and consequent sequence overlap (`|->` vs `|=>`).",
                evidence_source="TI Technical Interview 2025",
                source_type="interview_feedback",
                severity="medium",
                confidence=0.45,
            )
        ],
        knowledge_items=[
            KnowledgeIngestItem(
                topic="SystemVerilog Assertions",
                concept="Implication Operators",
                explanation="|-> is overlapped implication (antecedent matches, consequent checked in same cycle); |=> is non-overlapped (checked next cycle).",
                source="IEEE Standard for SystemVerilog 1800-2017",
                source_type="lrm",
                verified=True,
            )
        ],
    )

    result = ingest_service.ingest_payload(payload)
    assert result.session_id is not None
    assert result.questions_inserted == 1
    assert result.weak_areas_inserted == 1
    assert result.knowledge_items_inserted == 1
    assert len(result.errors) == 0

    # Verify provenance on inserted question
    questions = career_repo.get_all_questions()
    assert len(questions) == 1
    assert "TI Technical Interview 2025 [interview] (Q1)" in questions[0].source
    assert questions[0].verified is True


def test_duplicate_question_deduplication(ingest_service, career_repo):
    """Test that identical questions across different sessions increment times_asked rather than duplicating."""
    q_item_1 = QuestionIngestItem(
        question="What is the difference between wire and reg in Verilog?",
        topic="Verilog Fundamentals",
        source="Qualcomm Mock Round",
        source_type="mock",
        was_correct=True,
    )
    q_item_2 = QuestionIngestItem(
        question="what is the difference between WIRE and REG in Verilog?!",
        topic="Verilog Fundamentals",
        source="Intel Technical Interview",
        source_type="interview",
        was_correct=True,
    )

    q_id_1, is_new_1 = ingest_service.ingest_question(q_item_1)
    assert is_new_1 is True

    q_id_2, is_new_2 = ingest_service.ingest_question(q_item_2)
    assert is_new_2 is False
    assert q_id_1 == q_id_2

    # Verify times_asked is incremented
    fetched = career_repo.get_interview_question(q_id_1)
    assert fetched is not None
    assert fetched.times_asked == 2

    # Verify all questions returns only 1 record
    all_qs = career_repo.get_all_questions()
    assert len(all_qs) == 1


def test_verified_vs_unverified_knowledge_separation(ingest_service, career_repo):
    """AI-generated or unverified answers must NEVER be silently converted into verified knowledge."""
    ai_item = QuestionIngestItem(
        question="Explain UVM Objection mechanism.",
        topic="UVM Objections",
        expected_answer="AI explanation of drop_objection",
        source="Chat Bot Study Helper",
        source_type="ai_generated",
        verified=True,  # Attempting to claim verified on AI source
    )
    q_id, _ = ingest_service.ingest_question(ai_item)
    saved = career_repo.get_interview_question(q_id)
    assert saved is not None
    # System must force verified=False for ai_generated source_type
    assert saved.verified is False


def test_preparation_engine_plan_generation(ingest_service, job_repo, prep_engine):
    """Test generating a comprehensive, prioritized preparation plan for a job listing."""
    # 1. Seed Career Knowledge Base
    payload = CareerIngestPayload(
        source="VLSI Prep Batch 1",
        source_type="study_notes",
        questions=[
            QuestionIngestItem(
                company="Qualcomm",
                role="Design Verification Engineer",
                question="How does UVM factory override by type work?",
                topic="UVM Factory",
                was_correct=True,
                times_asked=2,
                source="Qualcomm Prep",
                verified=True,
            ),
            QuestionIngestItem(
                company="Qualcomm",
                role="Design Verification Engineer",
                question="Explain the difference between fork-join, fork-join_any, and fork-join_none.",
                topic="SystemVerilog Concurrency",
                user_answer="fork-join_none waits for all threads.",
                expected_answer="fork-join_none spawns processes and continues immediately without blocking parent process.",
                was_correct=False,  # Missed question
                source="Qualcomm Mock Test",
                verified=False,
            ),
        ],
        weak_areas=[
            WeakAreaIngestItem(
                topic="SystemVerilog Concurrency",
                description="Confused on process synchronization with disable fork and wait fork.",
                severity="high",
                confidence=0.3,
            )
        ],
        knowledge_items=[
            KnowledgeIngestItem(
                topic="SystemVerilog Concurrency",
                concept="Fork Join Types",
                explanation="join blocks until all finish; join_any blocks until first finishes; join_none does not block parent.",
                source="SystemVerilog LRM Section 9.3",
                verified=True,
            )
        ],
    )
    ingest_service.ingest_payload(payload)

    # 2. Insert Target Job
    target_job = NormalizedJob(
        company="Qualcomm India",
        title="Design Verification Engineer",
        location="Bengaluru",
        country="India",
        skills=["SystemVerilog", "SystemVerilog Concurrency", "UVM Factory"],
        source="manual",
        status=JobStatus.ACTIVE,
        first_seen="2026-10-04T10:00:00Z",
        last_seen="2026-10-04T10:00:00Z",
        fingerprint="qualcomm-dv-blr-plan-test",
    )
    job_id = job_repo.insert_normalized_job(target_job)

    # 3. Generate Preparation Plan
    plan = prep_engine.prepare_for_job(job_id)

    assert plan.job_id == job_id
    assert plan.company == "Qualcomm India"
    assert len(plan.historical_questions) >= 2
    assert len(plan.incorrect_questions) == 1
    assert plan.incorrect_questions[0].topic == "SystemVerilog Concurrency"

    # Weak areas should be present and prioritized
    assert len(plan.weak_areas) >= 1
    assert plan.weak_areas[0].topic == "SystemVerilog Concurrency"

    # Topic prioritization: SystemVerilog Concurrency has weak area (+3) + missed question (+2) + job skill (+2)
    assert plan.priority_topics[0] == "SystemVerilog Concurrency"

    # Recommended sessions generated
    assert len(plan.recommended_sessions) > 0
    top_session = plan.recommended_sessions[0]
    assert top_session.focus_topic == "SystemVerilog Concurrency"
    assert len(top_session.target_weak_areas) > 0
    assert len(top_session.practice_questions) > 0

    # Verified knowledge items included
    assert len(plan.verified_knowledge) >= 1
    assert plan.verified_knowledge[0].concept == "Fork Join Types"
    assert plan.verified_knowledge[0].verified is True


def test_prepare_for_nonexistent_job_raises_error(prep_engine):
    """Attempting to prepare for an invalid job_id raises ValueError."""
    with pytest.raises(ValueError, match="not found"):
        prep_engine.prepare_for_job(999999)
