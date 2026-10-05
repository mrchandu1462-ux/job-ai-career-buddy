"""Tests for Phase 5 Job Intelligence, 7D Scoring, Application Package, and Human Approval Pipeline."""

import pytest

from app.career.repository import CareerRepository
from app.db.connection import get_db
from app.db.models import (
    ApplicationEventType,
    ApplicationStatus,
    InterviewQuestion,
    JobStatus,
    WeakArea,
)
from app.jobs.package import ApplicationPackage
from app.jobs.pipeline import JobDiscoveryPipeline
from app.jobs.sources.base import JobDiscoveryQuery
from app.matching.models import EligibilityStatus, TechnicalSkillCategory
from app.profile.models import (
    CandidateDetails,
    CandidateLocations,
    CandidateProfile,
    FactBank,
    FactCategory,
    FactItem,
    ProjectFact,
    SkillFact,
    WorkAuthorization,
)


@pytest.fixture
def db_conn():
    with get_db(":memory:") as conn:
        yield conn


@pytest.fixture
def sample_candidate_and_facts():
    profile = CandidateProfile(
        candidate=CandidateDetails(
            target_roles=[
                "Design Verification Engineer",
                "Functional Verification Engineer",
                "ASIC Verification Engineer",
                "RTL Design Engineer",
                "Verification Intern",
                "Graduate Engineer Trainee",
            ],
            graduation_year=2025,
            experience_level="Fresher / Entry-Level",
            locations=CandidateLocations(
                india_priority=["Bengaluru", "Hyderabad", "Chennai", "Pune", "Noida"],
                overseas_enabled=True,
                overseas_require_sponsorship=True,
            ),
            work_authorization=WorkAuthorization(
                citizen_of="India",
                requires_sponsorship_overseas=True,
            ),
        )
    )

    facts = FactBank(
        version="1.0",
        facts=[
            FactItem(
                fact_id="EDU-001",
                category=FactCategory.EDUCATION,
                subject="B.Tech in Electronics and Communication Engineering",
                value={"degree": "B.Tech in ECE", "institution": "National Institute of Technology", "graduation_year": 2025, "gpa": "7.38/10"},
                verified=True,
            ),
            SkillFact(
                fact_id="SKILL-SV-01",
                subject="SystemVerilog",
                value={"topics": ["OOP", "Assertions", "Randomization", "Interfaces"]},
                verified=True,
            ),
            SkillFact(
                fact_id="SKILL-UVM-01",
                subject="UVM",
                value={"topics": ["Scoreboard", "Driver", "Monitor", "Sequences", "TLM"]},
                verified=True,
            ),
            SkillFact(
                fact_id="SKILL-V-01",
                subject="Verilog",
                value="RTL & Testbench",
                verified=True,
            ),
            SkillFact(
                fact_id="SKILL-SVA-01",
                subject="SVA",
                value="Concurrent and Immediate Assertions",
                verified=True,
            ),
            SkillFact(
                fact_id="SKILL-TOOL-01",
                subject="Questa",
                value="QuestaSim simulation and waveform analysis",
                verified=True,
            ),
            SkillFact(
                fact_id="SKILL-PY-01",
                subject="Python",
                value="Test scripting and automation",
                verified=True,
            ),
            SkillFact(
                fact_id="SKILL-LINUX-01",
                subject="Linux",
                value="Bash scripting and simulation workflows",
                verified=True,
            ),
            ProjectFact(
                fact_id="PROJ-APB-01",
                subject="APB Protocol Verification",
                value={"technologies": ["SystemVerilog", "UVM", "APB", "FIFO", "Questa"]},
                verified=True,
            ),
            ProjectFact(
                fact_id="PROJ-FIFO-01",
                subject="Asynchronous FIFO Verification",
                value={"technologies": ["SystemVerilog", "CDC", "FIFO", "Assertions"]},
                verified=True,
            ),
        ],
    )
    return profile, facts


@pytest.fixture
def career_repo_with_history(db_conn):
    repo = CareerRepository(db_conn)
    # Populate historical interview questions and weak areas
    repo.insert_interview_question(
        InterviewQuestion(
            company="Texas Instruments",
            role="Design Verification Engineer",
            question="Explain difference between virtual interface and abstract class in SystemVerilog.",
            category="technical",
            topic="SystemVerilog OOP",
            source="TI Campus Interview 2024",
            verified=True,
            created_at="2026-09-01T10:00:00+00:00",
        )
    )
    repo.insert_interview_question(
        InterviewQuestion(
            company="Texas Instruments",
            role="Design Verification Engineer",
            question="How does UVM factory override by type work?",
            category="technical",
            topic="UVM Factory",
            source="TI Campus Interview 2024",
            verified=True,
            created_at="2026-09-01T10:00:00+00:00",
        )
    )
    repo.insert_interview_question(
        InterviewQuestion(
            company="Texas Instruments",
            role="Design Verification Engineer",
            question="Explain 2-flop synchronizer MTBF and Gray coding in async FIFO pointers.",
            category="technical",
            topic="Clock Domain Crossing",
            source="TI Campus Interview 2024",
            verified=True,
            created_at="2026-09-01T10:00:00+00:00",
        )
    )
    repo.insert_weak_area(
        WeakArea(
            topic="Clock Domain Crossing",
            description="2-flop synchronizer MTBF and Gray coding for async FIFO pointers.",
            severity="high",
            confidence=0.4,
            created_at="2026-09-01T10:00:00+00:00",
        )
    )
    return repo


def test_job_discovery_pipeline_end_to_end(db_conn, sample_candidate_and_facts, career_repo_with_history):
    """Test full JobDiscoveryPipeline: search, ingestion, verification, 7D scoring, ranking, and application packaging."""
    profile, facts = sample_candidate_and_facts
    pipeline = JobDiscoveryPipeline(conn=db_conn, profile=profile, fact_bank=facts)

    # 1. Load sample postings into company career source
    pipeline.career_source.load_structured_postings([
        {
            "company": "Texas Instruments",
            "title": "Design Verification Engineer",
            "description": """
            Looking for a Design Verification Engineer in Bengaluru.
            Requirements:
            - 2025 batch B.Tech/M.Tech in ECE/VLSI.
            - 0-1 years of experience in SystemVerilog, UVM, and SVA.
            - Knowledge of APB and FIFO protocols.
            - Experience with QuestaSim or VCS and Python scripting.
            """,
            "location": "Bengaluru",
            "country": "India",
            "url": "https://careers.ti.com/job/dv-bengaluru-2025",
        },
        {
            "company": "Synopsys",
            "title": "Senior Staff Verification Engineer",
            "description": """
            Senior Staff DV Engineer in Hyderabad.
            Requires 8+ years of UVM and SystemVerilog experience in SoC verification.
            """,
            "location": "Hyderabad",
            "country": "India",
            "url": "https://synopsys.com/careers/job-sr-dv",
        },
        {
            "company": "Arm Ltd",
            "title": "Graduate Verification Engineer",
            "description": """
            Graduate Verification Engineer in Cambridge, UK.
            2025 graduate. 0-1 years experience in SystemVerilog, UVM, and Python.
            """,
            "location": "Cambridge",
            "country": "United Kingdom",
            "url": "https://arm.com/careers/job-grad-dv",
        },
    ])

    # 2. Discover and Ingest
    query = JobDiscoveryQuery(keywords=["Verification"], limit=10)
    reports = pipeline.discover_and_ingest(query)
    assert len(reports) == 3
    assert all(r.raw_job_id > 0 for r in reports)
    assert all(r.normalized_job_id > 0 for r in reports)

    # 3. Verify Active Statuses in DB
    ti_job = pipeline.job_repo.get_normalized_job_by_fingerprint("texasinstruments-designverificationengineer-bengaluru")
    assert ti_job is not None
    assert ti_job.status == JobStatus.ACTIVE

    # 4. Evaluate and Rank All Jobs
    ranked_all = pipeline.evaluate_and_rank_all_jobs(eligible_only=False)
    assert len(ranked_all) == 3

    # Hard filter check: Senior staff role should be INELIGIBLE
    sr_match = next(r for r in ranked_all if r.company == "Synopsys")
    assert sr_match.is_eligible is False
    assert sr_match.match_score == 0.0
    assert sr_match.hard_filters.status == EligibilityStatus.INELIGIBLE
    assert any("exceeding entry-level" in f for f in sr_match.hard_filters.failed_criteria)

    # Eligible India Tech Hub Ranking
    top_india = pipeline.get_top_india_opportunities(limit=5)
    assert len(top_india) == 1
    ti_match = top_india[0]
    assert ti_match.company == "Texas Instruments"
    assert ti_match.is_eligible is True
    assert ti_match.match_score >= 80.0

    # Verify 7-Dimension Breakdown
    b7d = ti_match.breakdown_7d
    assert b7d is not None
    assert b7d.role_relevance == 20.0
    assert b7d.technical_match >= 20.0
    assert b7d.project_alignment >= 16.0
    assert b7d.fresher_fit == 10.0
    assert b7d.location_preference == 10.0
    assert b7d.interview_relevance >= 8.0
    assert b7d.freshness_quality == 5.0
    assert len(b7d.itemized_reasons) == 7

    # Verify Skill Details Categorization
    sv_detail = next(s for s in b7d.skill_details if s.skill_name == "SystemVerilog")
    assert sv_detail.category == TechnicalSkillCategory.VERIFIED_MATCH
    assert sv_detail.evidence_fact_id == "SKILL-SV-01"

    # 5. Overseas Opportunity Segmentation
    top_overseas = pipeline.get_top_overseas_opportunities(limit=5)
    assert len(top_overseas) == 1
    arm_match = top_overseas[0]
    assert arm_match.company == "Arm Ltd"
    assert arm_match.is_overseas is True
    assert arm_match.requires_sponsorship is True

    # 6. Assemble Application Package
    package: ApplicationPackage = pipeline.prepare_application_package(
        job_id=ti_job.id, target_interview_date="2026-10-15T10:00:00"
    )
    assert package.company == "Texas Instruments"
    assert package.job_id == ti_job.id
    assert package.ats_score is not None
    assert package.ats_score >= 80.0
    assert package.ats_target_reached is True
    assert package.fact_integrity_verified is True
    assert package.interview_pool_size > 0
    assert package.historical_questions_count >= 2
    assert package.weak_areas_count >= 1
    assert package.application_status == ApplicationStatus.READY_FOR_REVIEW
    assert package.human_approval_state == "AWAITING_REVIEW"

    # Verify Safety & Transparency Disclosures
    assert any("DID NOT submit" in s for s in package.what_ai_did_not_do)
    assert any("DID NOT fabricate" in s for s in package.what_ai_did_not_do)
    assert any("DID NOT mark the application as APPLIED" in s for s in package.what_ai_did_not_do)

    # 7. Check User Notification Dispatched
    notifications = pipeline.job_repo.list_notifications(unread_only=True)
    assert len(notifications) >= 1
    approval_notif = next(n for n in notifications if "Ready for Review" in n.title)
    assert "Texas Instruments" in approval_notif.message
    assert "ACTION REQUIRED" in approval_notif.message

    # 8. Human Review: Approve Application (Must NOT transition to APPLIED!)
    app_record = pipeline.job_repo.get_application_by_job_id(ti_job.id)
    approved_app = pipeline.review_application(
        application_id=app_record.id,
        decision="APPROVE",
        notes="Reviewed and approved tailored resume and test plan.",
    )
    assert approved_app.status == ApplicationStatus.APPROVED
    assert approved_app.status != ApplicationStatus.APPLIED

    # Check audit events
    events = pipeline.job_repo.get_application_events(app_record.id)
    assert any(e.event_type == ApplicationEventType.APPROVED for e in events)

    # 9. Confirmed Submission: ONLY this can set status to APPLIED
    submitted_app = pipeline.record_submission(
        application_id=app_record.id,
        reference_id="TI-REQ-2025-9988",
        submission_evidence="Official TI Portal Submission Screen with Confirmation #TI-REQ-2025-9988",
    )
    assert submitted_app.status == ApplicationStatus.APPLIED
    assert submitted_app.applied_at is not None

    # Check final audit events
    events_after_submit = pipeline.job_repo.get_application_events(app_record.id)
    assert any(e.event_type == ApplicationEventType.SUBMITTED for e in events_after_submit)

    # 10. Dashboard Summary Verification
    dashboard_summary = pipeline.get_dashboard_summary()
    assert dashboard_summary["total_discovered_jobs"] == 3
    assert len(dashboard_summary["top_india_opportunities"]) == 1
    assert dashboard_summary["applications_submitted_count"] == 1
    assert dashboard_summary["unresolved_weak_areas_count"] >= 1


def test_application_review_rejection_and_edit_flows(db_conn, sample_candidate_and_facts):
    """Test candidate rejecting or requesting edits on an application package."""
    profile, facts = sample_candidate_and_facts
    pipeline = JobDiscoveryPipeline(conn=db_conn, profile=profile, fact_bank=facts)

    # Ingest manual job
    manual_src = pipeline.manual_source
    payload = manual_src.submit_manual_job(
        company="NXP Semiconductors",
        title="Verification Trainee",
        raw_text="SystemVerilog, UVM in Noida. 2025 batch.",
        location="Noida",
    )
    assert payload.company == "NXP Semiconductors"
    report = pipeline.discover_and_ingest(JobDiscoveryQuery(keywords=["Verification"]))
    nxp_job_id = report[0].normalized_job_id

    # Prepare package
    pipeline.prepare_application_package(nxp_job_id)
    app = pipeline.job_repo.get_application_by_job_id(nxp_job_id)
    assert app.status == ApplicationStatus.READY_FOR_REVIEW

    # Candidate requests edits
    app_edit = pipeline.review_application(app.id, decision="EDIT", notes="Please emphasize APB project more.")
    assert app_edit.status == ApplicationStatus.PREPARING

    # Re-prepare and reject
    pipeline.prepare_application_package(nxp_job_id)
    app_rejected = pipeline.review_application(app.id, decision="REJECT", notes="Location preference changed.")
    assert app_rejected.status == ApplicationStatus.REJECTED
    assert app_rejected.status != ApplicationStatus.APPLIED
