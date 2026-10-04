"""Tests for the 17-point Consolidated Final Interview Pack generator."""

import pytest

from app.career.assessment import AdaptiveAssessmentEngine
from app.career.bank import QuestionBankService
from app.career.ingestion import (
    CareerIngestionService,
    CareerIngestPayload,
    QuestionIngestItem,
    WeakAreaIngestItem,
)
from app.career.pack import InterviewPackGenerator
from app.career.repository import CareerRepository
from app.db.connection import get_db
from app.db.models import JobStatus, NormalizedJob
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
def bank_service(db_conn, career_repo):
    return QuestionBankService(db_conn, career_repo)


@pytest.fixture
def pack_generator(job_repo, career_repo, assessment_engine, bank_service):
    return InterviewPackGenerator(job_repo, career_repo, assessment_engine, bank_service)


@pytest.fixture
def seeded_env(career_repo, job_repo):
    ingest = CareerIngestionService(career_repo)
    payload = CareerIngestPayload(
        source="NVIDIA DV Interview Prep",
        source_type="interview",
        questions=[
            QuestionIngestItem(
                company="NVIDIA",
                role="ASIC Verification Engineer",
                question="How do you verify a multi-channel DMA controller in UVM?",
                topic="DMA Verification",
                expected_answer="Build an agent per channel, scoreboards with out-of-order tracking, and SVA for arbitrations.",
                was_correct=True,
                source="NVIDIA Interview",
                verified=True,
            )
        ],
        weak_areas=[
            WeakAreaIngestItem(
                topic="DMA Verification",
                description="Complex arbiter corner cases.",
                severity="medium",
                confidence=0.5,
            )
        ],
    )
    ingest.ingest_payload(payload)

    job = NormalizedJob(
        company="NVIDIA Graphics",
        title="ASIC Verification Engineer",
        skills=["SystemVerilog", "UVM", "DMA Verification", "AXI"],
        source="manual",
        status=JobStatus.ACTIVE,
        first_seen="2026-10-04T10:00:00Z",
        last_seen="2026-10-04T10:00:00Z",
        fingerprint="nvidia-asic-pack-test",
    )
    return job_repo.insert_normalized_job(job)


def test_generate_interview_pack_17_points(pack_generator, seeded_env):
    """Test generating the complete 17-component interview pack."""
    job_id = seeded_env
    pack = pack_generator.generate_interview_pack(job_id)

    # 1-4
    assert pack.company == "NVIDIA Graphics"
    assert pack.role == "ASIC Verification Engineer"
    assert len(pack.required_skills) >= 3

    # 5-8
    assert len(pack.historical_questions) >= 1
    assert len(pack.active_weak_areas) >= 1

    # 10-14
    assert len(pack.project_deep_dive_questions) >= 3
    assert len(pack.expected_coding_questions) >= 4  # SVA, constraints, driver, covergroup
    assert len(pack.expected_debugging_questions) >= 3
    assert len(pack.hr_questions) >= 3
    assert len(pack.resume_specific_questions) >= 2

    # 15-17
    assert len(pack.final_revision_checklist) >= 5
    assert 0.0 <= pack.readiness_score <= 100.0
    assert len(pack.last_minute_topics) >= 1
