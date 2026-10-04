"""Tests for Question Bank querying, explainable priority engine, and 8-category review pools."""

import pytest

from app.career.bank import QuestionBankFilter, QuestionBankService
from app.career.ingestion import (
    CareerIngestionService,
    CareerIngestPayload,
    QuestionIngestItem,
    WeakAreaIngestItem,
)
from app.career.repository import CareerRepository
from app.db.connection import get_db
from app.db.models import JobStatus, NormalizedJob


@pytest.fixture
def db_conn():
    with get_db(":memory:") as conn:
        yield conn


@pytest.fixture
def career_repo(db_conn):
    return CareerRepository(db_conn)


@pytest.fixture
def bank_service(db_conn, career_repo):
    return QuestionBankService(db_conn, career_repo)


@pytest.fixture
def populated_bank(career_repo):
    ingest = CareerIngestionService(career_repo)
    payload = CareerIngestPayload(
        source="Multi-company DV historical tests",
        source_type="interview",
        questions=[
            QuestionIngestItem(
                company="Qualcomm",
                role="Design Verification Engineer",
                question="Explain the difference between uvm_component and uvm_sequence_item.",
                topic="UVM Components",
                difficulty="medium",
                was_correct=False,
                source="Qualcomm Technical R1",
                verified=True,
            ),
            QuestionIngestItem(
                company="Qualcomm",
                role="Design Verification Engineer",
                question="How does $past work in SystemVerilog Assertions?",
                topic="SystemVerilog Assertions",
                difficulty="easy",
                was_correct=True,
                source="Qualcomm Technical R1",
                verified=True,
            ),
            QuestionIngestItem(
                company="Texas Instruments",
                role="ASIC Verification Engineer",
                question="Explain Gray code conversion in Async FIFO full detection.",
                topic="Async FIFO",
                difficulty="hard",
                was_correct=False,
                source="TI Technical R2",
                verified=True,
            ),
            QuestionIngestItem(
                company="Texas Instruments",
                role="ASIC Verification Engineer",
                question="What are the 5 channels of AXI4 protocol?",
                topic="AXI Protocol",
                difficulty="medium",
                was_correct=True,
                source="TI Technical R1",
                verified=True,
            ),
            QuestionIngestItem(
                company="AMD",
                role="Design Verification Engineer",
                question="How do you handle clock domain crossing for a multi-bit control bus?",
                topic="Clock Domain Crossing",
                difficulty="hard",
                was_correct=False,
                source="AMD Verification Prep",
                verified=True,
            ),
        ],
        weak_areas=[
            WeakAreaIngestItem(
                topic="Async FIFO",
                description="Trouble with Gray code arithmetic and full flag generation.",
                severity="high",
                confidence=0.3,
            )
        ],
    )
    ingest.ingest_payload(payload)

    # Ingest a repeated question to increment times_asked
    dup_payload = CareerIngestPayload(
        source="Mock Test 2",
        source_type="mock_interview",
        questions=[
            QuestionIngestItem(
                company="Qualcomm",
                role="Design Verification Engineer",
                question="Explain the difference between uvm_component and uvm_sequence_item.",
                topic="UVM Components",
                source="Mock Test 2",
                verified=True,
            )
        ],
    )
    ingest.ingest_payload(dup_payload)


def test_query_questions_with_filters(bank_service, populated_bank):
    """Test multi-dimensional querying by company, topic, difficulty, correctness."""
    # Filter by company
    q_qualcomm = bank_service.query_questions(QuestionBankFilter(company="Qualcomm"))
    assert len(q_qualcomm) == 2
    assert all("Qualcomm" in (q.company or "") for q in q_qualcomm)

    # Filter by topic
    q_fifo = bank_service.query_questions(QuestionBankFilter(topic="FIFO"))
    assert len(q_fifo) == 1
    assert q_fifo[0].topic == "Async FIFO"

    # Filter by previously missed questions
    q_missed = bank_service.query_questions(QuestionBankFilter(was_correct=False))
    assert len(q_missed) == 3

    # Filter by difficulty
    q_hard = bank_service.query_questions(QuestionBankFilter(difficulty="hard"))
    assert len(q_hard) == 2


def test_group_by_questions(bank_service, career_repo, populated_bank):
    """Test grouping questions by company, topic, and correctness."""
    all_qs = career_repo.get_all_questions()

    by_company = bank_service.group_by(all_qs, "company")
    assert "Qualcomm" in by_company
    assert "Texas Instruments" in by_company
    assert "AMD" in by_company

    by_correctness = bank_service.group_by(all_qs, "correctness")
    assert "Correct" in by_correctness
    assert "Incorrect / Missed" in by_correctness


def test_explainable_priority_scoring(bank_service, populated_bank):
    """Test question prioritization with explainable scoring and reasons."""
    target_job = NormalizedJob(
        company="Qualcomm India",
        title="Design Verification Engineer",
        skills=["UVM Components", "SystemVerilog Assertions", "Async FIFO"],
        source="manual",
        status=JobStatus.ACTIVE,
        first_seen="2026-10-04T10:00:00Z",
        last_seen="2026-10-04T10:00:00Z",
        fingerprint="qualcomm-dv-priority-test",
    )

    prioritized = bank_service.prioritize_questions_for_job(target_job)
    assert len(prioritized) == 5

    # Top question should be the missed, repeated, company-matched UVM question
    top_q = prioritized[0]
    assert "uvm_component" in top_q.question.question.lower()
    assert top_q.priority_level == "HIGH"
    assert top_q.priority_score >= 80

    # Ensure reasons explain the selection
    assert any("Previously answered incorrectly" in r for r in top_q.reasons)
    assert any("Appeared in 2 historical interviews" in r for r in top_q.reasons)
    assert any("Qualcomm" in r for r in top_q.reasons)


def test_pre_interview_8_category_review_pool(bank_service, populated_bank):
    """Test generating the complete 8-category review pool."""
    target_job = NormalizedJob(
        company="Texas Instruments",
        title="ASIC Verification Engineer",
        skills=["Async FIFO", "AXI Protocol"],
        source="manual",
        status=JobStatus.ACTIVE,
        first_seen="2026-10-04T10:00:00Z",
        last_seen="2026-10-04T10:00:00Z",
        fingerprint="ti-asic-review-pool-test",
    )

    pool = bank_service.build_review_pool_for_job(target_job)

    assert pool.total_unique_questions == 5
    assert len(pool.company_specific) == 2  # 2 TI questions
    assert len(pool.job_specific) >= 2  # Async FIFO and AXI Protocol
    assert len(pool.previously_missed) == 3
    assert len(pool.weak_areas) >= 1  # Async FIFO weak area
    assert len(pool.frequently_asked) >= 1  # Repeated question
    assert len(pool.must_know) >= 2
