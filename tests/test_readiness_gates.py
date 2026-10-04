"""Tests for Interview Readiness Scoring and Configurable Readiness Gate thresholds."""

import pytest

from app.career.assessment import AdaptiveAssessmentEngine
from app.career.ingestion import (
    CareerIngestionService,
    CareerIngestPayload,
    WeakAreaIngestItem,
)
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


def test_readiness_gate_high_readiness(assessment_engine, career_repo, job_repo):
    """Test candidate with no active weak areas meets High Readiness threshold."""
    job = NormalizedJob(
        company="Synopsys",
        title="Design Verification Engineer",
        skills=["SystemVerilog", "UVM", "Assertions"],
        source="manual",
        status=JobStatus.ACTIVE,
        first_seen="2026-10-04T10:00:00Z",
        last_seen="2026-10-04T10:00:00Z",
        fingerprint="synopsys-dv-high-readiness",
    )
    job_id = job_repo.insert_normalized_job(job)

    readiness = assessment_engine.compute_job_readiness(job_id)
    assert readiness.overall_readiness_score == 90.0
    assert readiness.readiness_level == "High Readiness"
    assert "well-prepared" in readiness.recommended_action.lower()


def test_readiness_gate_critical_topic_blocking_readiness(assessment_engine, career_repo, job_repo):
    """Test that a single low critical topic (e.g. UVM confidence 0.35) triggers Needs Preparation even if other topics are high."""
    ingest = CareerIngestionService(career_repo)
    payload = CareerIngestPayload(
        source="UVM Gap Ingestion",
        source_type="mock_interview",
        weak_areas=[
            WeakAreaIngestItem(
                topic="UVM",
                description="Failed UVM phase and factory questions.",
                severity="critical",
                confidence=0.35,  # 35% in UVM
            )
        ],
    )
    ingest.ingest_payload(payload)

    job = NormalizedJob(
        company="Synopsys",
        title="Design Verification Engineer",
        skills=["SystemVerilog", "UVM", "Digital Design"],
        source="manual",
        status=JobStatus.ACTIVE,
        first_seen="2026-10-04T10:00:00Z",
        last_seen="2026-10-04T10:00:00Z",
        fingerprint="synopsys-dv-crit-blocking",
    )
    job_id = job_repo.insert_normalized_job(job)

    # Average: (90 + 35 + 90) / 3 = 71.7%
    # Overall is >= 65%, but critical topic UVM is 35% (< 60% fail threshold)
    readiness = assessment_engine.compute_job_readiness(job_id)
    assert readiness.overall_readiness_score == 71.7
    assert readiness.readiness_level == "Needs Preparation"
    assert "UVM" in readiness.weak_topics
    assert "threshold" in readiness.recommended_action.lower()
