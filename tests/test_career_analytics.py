"""Unit tests for CareerAnalyticsService."""

import pytest

from app.career.analytics import CareerAnalyticsService
from app.career.repository import CareerRepository
from app.db.connection import get_db
from app.db.models import (
    ApplicationRecord,
    ApplicationStatus,
    AssessmentRecord,
    AssessmentStatus,
    AssessmentType,
    InterviewQuestion,
    JobStatus,
    NormalizedJob,
    WeakArea,
)
from app.db.repository import JobRepository
from app.resume.models import ATSBreakdown, ResumeStatus, TailoredResume
from app.resume.repository import ResumeRepository


@pytest.fixture
def db_conn():
    with get_db(":memory:") as conn:
        yield conn


def test_career_analytics_empty_db(db_conn):
    analytics = CareerAnalyticsService(db_conn)
    summary = analytics.get_summary_metrics()
    assert summary["total_discovered_jobs"] == 0
    assert summary["total_applications"] == 0
    assert summary["conversion_rate"] == "Insufficient data"
    assert analytics.get_resume_ats_distribution() == []
    assert analytics.get_interview_topic_frequency() == []
    assert analytics.get_frequently_missed_questions() == []
    assert analytics.get_assessment_score_history() == []
    assert analytics.get_weak_area_breakdown() == []


def test_career_analytics_populated_db(db_conn):
    job_repo = JobRepository(db_conn)
    career_repo = CareerRepository(db_conn)
    resume_repo = ResumeRepository(db_conn)
    analytics = CareerAnalyticsService(db_conn, job_repo, career_repo, resume_repo)

    # Insert Job
    job_id = job_repo.insert_normalized_job(
        NormalizedJob(
            fingerprint="test-fp-1",
            company="Qualcomm India",
            title="Design Verification Engineer",
            location="Bengaluru",
            source="Manual",
            status=JobStatus.ACTIVE,
            skills=["SystemVerilog", "UVM", "SVA"],
            first_seen="2025-05-01T10:00:00",
            last_seen="2025-05-01T10:00:00",
        )
    )

    # Insert Applications
    job_repo.create_application(
        ApplicationRecord(
            job_id=job_id,
            status=ApplicationStatus.APPLIED,
            applied_at="2025-05-02T12:00:00",
            created_at="2025-05-01T10:00:00",
            updated_at="2025-05-02T12:00:00",
        )
    )

    # Insert Questions
    career_repo.insert_interview_question(
        InterviewQuestion(
            topic="SystemVerilog",
            question="What is the difference between shallow and deep copy?",
            expected_answer="Shallow copies pointers, deep copies objects.",
            company="Qualcomm",
            role="DV",
            times_asked=3,
            was_correct=False,
            feedback="Review OOP memory management.",
            verified=True,
            source="Qualcomm 2024",
            created_at="2025-05-01T10:00:00",
        )
    )
    career_repo.insert_interview_question(
        InterviewQuestion(
            topic="UVM",
            question="Explain UVM phases order.",
            expected_answer="Build, connect, end_of_elaboration, start_of_simulation, run, extract, check, report.",
            company="Qualcomm",
            role="DV",
            times_asked=2,
            was_correct=True,
            verified=True,
            source="Qualcomm 2024",
            created_at="2025-05-01T10:00:00",
        )
    )

    # Insert Weak Area
    career_repo.insert_weak_area(
        WeakArea(
            topic="SystemVerilog",
            description="OOP deep copy memory management",
            evidence_source="Qualcomm 2024",
            severity="high",
            confidence=0.4,
            created_at="2025-05-01T10:00:00",
        )
    )

    # Insert Resume
    resume_repo.insert_tailored_resume(
        TailoredResume(
            resume_id="res-001",
            target_job_id=job_id,
            version=1,
            generated_at="2025-05-01T11:00:00",
            candidate_name="VLSI Candidate",
            professional_summary="Aspiring Design Verification Engineer with hands-on SystemVerilog and UVM experience.",
            markdown_content="# Resume",
            plain_text_content="Resume",
            source_fact_ids=["FACT-1"],
            ats_score=85.0,
            ats_breakdown=ATSBreakdown(
                overall_score=85.0,
                technical_keyword_score=85.0,
                required_skills_coverage=90.0,
                project_relevance_score=85.0,
                role_alignment_score=80.0,
                parser_safety_score=100.0,
                parser_safety_status="PASS",
                fact_integrity_status="PASS",
                quality_gate_met=True,
            ),
            fact_integrity_status="PASS",
            status=ResumeStatus.APPROVED,
        )
    )

    # Insert Assessment
    career_repo.insert_assessment(
        AssessmentRecord(
            job_id=job_id,
            company="Qualcomm India",
            role="Design Verification Engineer",
            assessment_type=AssessmentType.PRE_INTERVIEW,
            title="Final Pre-Interview Test",
            time_limit_minutes=60,
            questions=[],
            status=AssessmentStatus.COMPLETED,
            score=82.5,
            total_questions=10,
            correct_count=8,
            incorrect_count=2,
            topic_breakdown={"SystemVerilog": {"score": 75.0}, "UVM": {"score": 90.0}},
            created_at="2025-05-02T09:00:00",
            completed_at="2025-05-02T09:50:00",
        )
    )

    # Test summary
    summary = analytics.get_summary_metrics()
    assert summary["total_discovered_jobs"] == 1
    assert summary["total_applications"] == 1
    assert summary["applications_applied"] == 1
    assert summary["conversion_rate"] == "100.0%"
    assert summary["unresolved_weak_areas_count"] == 1
    assert summary["total_assessments_taken"] == 1

    # Test resume ATS distribution
    res_dist = analytics.get_resume_ats_distribution()
    assert len(res_dist) == 1
    assert res_dist[0]["company"] == "Qualcomm India"
    assert res_dist[0]["ats_score"] == 85.0
    assert res_dist[0]["fact_integrity"] == "PASS"

    # Test topic frequency
    topics = analytics.get_interview_topic_frequency()
    assert len(topics) == 2
    assert topics[0]["topic"] in ["SystemVerilog", "UVM"]

    # Test frequently missed
    missed = analytics.get_frequently_missed_questions()
    assert len(missed) == 1
    assert missed[0]["topic"] == "SystemVerilog"
    assert "shallow" in missed[0]["question"]

    # Test assessment score history
    history = analytics.get_assessment_score_history()
    assert len(history) == 1
    assert history[0]["score"] == "82.5%"
    assert history[0]["correct_count"] == "8/10"

    # Test weak area breakdown
    weaks = analytics.get_weak_area_breakdown()
    assert len(weaks) == 1
    assert weaks[0]["topic"] == "SystemVerilog"
    assert weaks[0]["severity"] == "HIGH"
