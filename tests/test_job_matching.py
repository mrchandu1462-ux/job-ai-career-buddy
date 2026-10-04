"""Tests for Job Ingestion, Normalization, Hard Eligibility Filtering, and Deterministic Scoring."""

import pytest

from app.db.connection import get_db
from app.db.models import ApplicationStatus
from app.db.repository import JobRepository
from app.jobs.ingestion import JobIngestInput, JobIngestionService
from app.jobs.normalizer import (
    detect_seniority_flag,
    extract_experience_requirements,
    extract_graduation_years,
    extract_vlsi_skills,
    generate_job_fingerprint,
    normalize_job_listing,
)
from app.matching.filters import HardFilterEngine
from app.matching.ranker import JobRanker
from app.matching.scorer import JobScoringEngine
from app.profile.models import (
    CandidateDetails,
    CandidateLocations,
    CandidateProfile,
    FactBank,
    ProjectFact,
    SkillFact,
    WorkAuthorization,
)


@pytest.fixture
def db_conn():
    with get_db(":memory:") as conn:
        yield conn


@pytest.fixture
def job_repo(db_conn):
    return JobRepository(db_conn)


@pytest.fixture
def ingest_service(job_repo):
    return JobIngestionService(job_repo)


@pytest.fixture
def sample_candidate():
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
            SkillFact(
                fact_id="SKILL-SV-01",
                subject="SystemVerilog",
                value={"topics": ["OOP", "Assertions", "Randomization"]},
                verified=True,
            ),
            SkillFact(
                fact_id="SKILL-UVM-01",
                subject="UVM",
                value={"topics": ["Scoreboard", "Driver", "Monitor", "Sequences"]},
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
                value="QuestaSim / ModelSim simulation",
                verified=True,
            ),
            SkillFact(
                fact_id="SKILL-PY-01",
                subject="Python",
                value="Test scripting and automation",
                verified=True,
            ),
            ProjectFact(
                fact_id="PROJ-APB-01",
                subject="APB Protocol Verification",
                value={"technologies": ["SystemVerilog", "UVM", "APB", "FIFO"]},
                verified=True,
            ),
        ],
    )
    return profile, facts


def test_job_normalization_utilities():
    """Test text parsing for skills, experience, graduation year, and fingerprints."""
    jd_text = """
    Job Description:
    Looking for a Design Verification Engineer to join our SoC team in Bengaluru.
    Requirements:
    - B.Tech in ECE / VLSI (2024 - 2025 batch passouts).
    - 0-1 years of experience in SystemVerilog and UVM.
    - Hands-on with SVA, Functional Coverage, and AXI/APB bus protocols.
    - Familiarity with QuestaSim or Synopsys VCS simulator and Python scripting.
    """

    skills = extract_vlsi_skills(jd_text)
    assert "SystemVerilog" in skills
    assert "UVM" in skills
    assert "SVA" in skills
    assert "Functional Coverage" in skills
    assert "AXI" in skills
    assert "APB" in skills
    assert "Questa" in skills
    assert "VCS" in skills
    assert "Python" in skills

    exp_min, exp_max = extract_experience_requirements(jd_text)
    assert exp_min == 0.0
    assert exp_max == 1.0

    grad_min, grad_max = extract_graduation_years(jd_text)
    assert grad_min == 2024
    assert grad_max == 2025

    fp = generate_job_fingerprint(company="Intel India", title="DV Engineer", location="Bengaluru")
    assert fp == "intelindia-dvengineer-bengaluru"

    assert detect_seniority_flag("Staff Verification Engineer", 0.0) is True
    assert detect_seniority_flag("Design Verification Engineer", 3.0) is True
    assert detect_seniority_flag("Design Verification Engineer", 0.0) is False


def test_job_ingestion_and_deduplication(ingest_service, job_repo):
    """Test raw payload storage, normalization, deduplication, and application audit tracking."""
    raw_text = """
    We are hiring an Entry Level ASIC Verification Engineer in Hyderabad.
    0-1 years experience. Must know SystemVerilog, UVM, and Verilog.
    """

    input_data = JobIngestInput(
        company="AMD India",
        title="ASIC Verification Engineer",
        raw_payload=raw_text,
        location="Hyderabad",
        source="career_portal",
        application_url="https://amd.com/careers/job101",
    )

    # First Ingestion
    report1 = ingest_service.ingest_job(input_data)
    assert report1.is_new is True
    assert report1.raw_job_id > 0
    assert report1.normalized_job_id > 0
    assert report1.is_senior_role is False
    assert report1.extracted_skills_count >= 3
    assert report1.application_id is not None

    # Check that application record was created in DISCOVERED status
    app = job_repo.get_application(report1.application_id)
    assert app is not None
    assert app.status == ApplicationStatus.DISCOVERED

    # Check audit events
    events = job_repo.get_application_events(report1.application_id)
    assert len(events) == 1
    assert events[0].company == "AMD India"

    # Second Ingestion with duplicate fingerprint -> should update last_seen, not duplicate
    report2 = ingest_service.ingest_job(input_data)
    assert report2.is_new is False
    assert report2.normalized_job_id == report1.normalized_job_id
    assert job_repo.count_normalized_jobs() == 1


def test_hard_eligibility_filter(sample_candidate):
    """Test hard criteria enforcement: graduation year, experience, senior roles, and location constraints."""
    profile, _ = sample_candidate
    filter_engine = HardFilterEngine(profile)

    # 1. Eligible Entry-Level DV Job in India
    job_ok = normalize_job_listing(
        company="Synopsys",
        title="Design Verification Engineer",
        raw_text="2025 batch passout. 0-1 years experience in SystemVerilog.",
        location="Bengaluru",
        country="India",
    )
    res_ok = filter_engine.evaluate(job_ok)
    assert res_ok.is_eligible is True
    assert res_ok.is_overseas is False

    # 2. Ineligible Graduation Year (requires 2021 batch)
    job_bad_grad = normalize_job_listing(
        company="Qualcomm",
        title="DV Engineer",
        raw_text="Only 2021 to 2022 batch graduates eligible. 1 year experience.",
        location="Bengaluru",
    )
    res_bad_grad = filter_engine.evaluate(job_bad_grad)
    assert res_bad_grad.is_eligible is False
    assert any("Graduation year" in f for f in res_bad_grad.failed_criteria)

    # 3. Ineligible Senior Role (5+ years)
    job_senior = normalize_job_listing(
        company="NVIDIA",
        title="Senior Verification Engineer",
        raw_text="Minimum 5+ years of experience in UVM testbench architecture.",
        location="Pune",
    )
    res_senior = filter_engine.evaluate(job_senior)
    assert res_senior.is_eligible is False
    assert any("exceeding entry-level" in f for f in res_senior.failed_criteria)

    # 4. Incompatible Role (Web Developer)
    job_web = normalize_job_listing(
        company="GenericTech",
        title="Senior React Web Developer",
        raw_text="Full stack javascript developer with node.js.",
        location="Noida",
    )
    res_web = filter_engine.evaluate(job_web)
    assert res_web.is_eligible is False
    assert any("Role title" in f for f in res_web.failed_criteria)

    # 5. Overseas Job with Sponsorship Tracking
    job_overseas = normalize_job_listing(
        company="Arm Ltd",
        title="Graduate Verification Engineer",
        raw_text="2025 graduate. 0-1 year experience in SystemVerilog and UVM.",
        location="Cambridge",
        country="United Kingdom",
    )
    res_overseas = filter_engine.evaluate(job_overseas)
    assert res_overseas.is_eligible is True
    assert res_overseas.is_overseas is True
    assert res_overseas.requires_sponsorship is True


def test_soft_relevance_scoring_and_provenance(sample_candidate):
    """Test deterministic relevance scoring strictly against verified candidate facts."""
    profile, facts = sample_candidate
    scoring_engine = JobScoringEngine(profile, facts)

    # Job requiring verified skills: SystemVerilog, UVM, SVA, APB, Questa, Python in Bengaluru
    job_high_match = normalize_job_listing(
        company="Texas Instruments",
        title="Design Verification Engineer",
        raw_text="""
        Design Verification Engineer in Bengaluru.
        Skills: SystemVerilog, UVM, SVA, APB, Questa, Python.
        0-1 years experience, 2025 batch.
        """,
        location="Bengaluru",
        country="India",
    )

    match = scoring_engine.score_job(job_high_match)
    assert match.is_eligible is True
    assert match.match_score >= 80.0
    assert "SystemVerilog" in match.score_breakdown.matching_skills
    assert "UVM" in match.score_breakdown.matching_skills
    assert "SVA" in match.score_breakdown.matching_skills
    assert any("Verified Candidate Fact" in r for r in match.score_breakdown.reasons)

    # Job requiring unverified skill: UVM RAL, AXI
    job_partial_match = normalize_job_listing(
        company="MediaTek",
        title="ASIC Verification Engineer",
        raw_text="""
        Requires SystemVerilog, UVM, UVM RAL, and AXI protocol.
        0-2 years experience. Noida.
        """,
        location="Noida",
        country="India",
    )
    match_partial = scoring_engine.score_job(job_partial_match)
    assert match_partial.is_eligible is True
    assert "UVM RAL" in match_partial.score_breakdown.missing_skills
    assert any("- UVM RAL requested by employer" in g for g in match_partial.score_breakdown.gaps)


def test_job_ranker_and_segmentation(sample_candidate):
    """Test ranking multiple jobs descending by score and segmenting India vs Overseas."""
    profile, facts = sample_candidate
    ranker = JobRanker(profile, facts)

    jobs = [
        normalize_job_listing(
            company="Broadcom",
            title="Design Verification Engineer",
            raw_text="SystemVerilog, UVM, SVA, Questa in Bengaluru. 0-1 yrs.",
            location="Bengaluru",
            country="India",
        ),
        normalize_job_listing(
            company="Qualcomm USA",
            title="Verification Engineer",
            raw_text="SystemVerilog, UVM, SVA, Python in San Diego. 0-1 yrs.",
            location="San Diego",
            country="United States",
        ),
        normalize_job_listing(
            company="LegacyCo",
            title="Principal Verification Architect",
            raw_text="10+ years experience in UVM architecture.",
            location="Chennai",
            country="India",
        ),
    ]

    all_ranked = ranker.rank_jobs(jobs, eligible_only=False)
    assert len(all_ranked) == 3
    # First ranked should have highest match score
    assert all_ranked[0].match_score >= all_ranked[1].match_score

    # Eligible only ranking should filter out Senior role
    eligible_ranked = ranker.rank_jobs(jobs, eligible_only=True)
    assert len(eligible_ranked) == 2
    assert all(r.is_eligible for r in eligible_ranked)

    top_india = ranker.get_top_india_matches(jobs)
    assert len(top_india) == 1
    assert top_india[0].company == "Broadcom"
    assert top_india[0].is_overseas is False

    top_overseas = ranker.get_top_overseas_matches(jobs)
    assert len(top_overseas) == 1
    assert top_overseas[0].company == "Qualcomm USA"
    assert top_overseas[0].is_overseas is True
    assert top_overseas[0].requires_sponsorship is True
