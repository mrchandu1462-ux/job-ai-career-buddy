"""Comprehensive tests for Fact-Grounded Resume Tailoring Engine, ATS Scoring, and Fact Integrity Validator."""

import pytest

from app.db.connection import get_db
from app.db.models import ApplicationStatus, JobStatus, NormalizedJob
from app.db.repository import JobRepository
from app.profile.models import (
    FactBank,
    FactCategory,
    FactItem,
)
from app.resume.ats import ATSScorer
from app.resume.engine import ResumeTailoringEngine
from app.resume.formatter import ATSResumeFormatter
from app.resume.integration import ResumeCareerIntegration
from app.resume.models import (
    ResumeBullet,
    ResumeEducation,
    ResumeProject,
    ResumeStatus,
    TailoredResume,
)
from app.resume.validator import FactIntegrityValidator


@pytest.fixture
def db_conn():
    with get_db(":memory:") as conn:
        yield conn


@pytest.fixture
def sample_fact_bank():
    return FactBank(
        facts=[
            FactItem(
                fact_id="EDU-001",
                category=FactCategory.EDUCATION,
                subject="B.Tech in Electronics and Communication Engineering",
                value={"degree": "Bachelor of Technology", "institution": "NIT", "graduation_year": 2025, "gpa": "8.6/10.0"},
                verified=True,
            ),
            FactItem(
                fact_id="SKILL-001",
                category=FactCategory.SKILL,
                subject="SystemVerilog",
                value={"skill_name": "SystemVerilog", "proficiency": "Advanced"},
                verified=True,
            ),
            FactItem(
                fact_id="SKILL-002",
                category=FactCategory.SKILL,
                subject="UVM",
                value={"skill_name": "UVM", "proficiency": "Intermediate"},
                verified=True,
            ),
            FactItem(
                fact_id="SKILL-003",
                category=FactCategory.SKILL,
                subject="AXI Protocol",
                value={"skill_name": "AXI4 Protocol", "proficiency": "Intermediate"},
                verified=True,
            ),
            FactItem(
                fact_id="SKILL-004",
                category=FactCategory.SKILL,
                subject="Async FIFO & CDC",
                value={"skill_name": "Async FIFO & CDC", "proficiency": "Intermediate"},
                verified=True,
            ),
            FactItem(
                fact_id="PROJ-001",
                category=FactCategory.PROJECT,
                subject="AXI4 Interface Verification IP",
                value={
                    "title": "AXI4 UVC Testbench Environment",
                    "technologies": ["SystemVerilog", "UVM", "QuestaSim", "SVA"],
                    "role": "Lead Verification Developer",
                    "bullets": [
                        "Architected a modular UVM testbench environment comprising active master agent, passive monitor, and scoreboard.",
                        "Developed constrained-random sequence library generating single, incremental, and wrap burst transfers.",
                        "Implemented SystemVerilog concurrent assertions (SVA) verifying VALID/READY handshakes.",
                    ],
                },
                verified=True,
            ),
            FactItem(
                fact_id="PROJ-002",
                category=FactCategory.PROJECT,
                subject="Async FIFO CDC Verification",
                value={
                    "title": "Dual-Clock Async FIFO Verification",
                    "technologies": ["Verilog", "SystemVerilog", "SVA", "ModelSim"],
                    "role": "Verification Developer",
                    "bullets": [
                        "Designed dual-clock asynchronous FIFO with 2-flip-flop synchronizers and Gray pointer conversion.",
                        "Verified full and empty condition flag generation logic preventing overflow.",
                    ],
                },
                verified=True,
            ),
            FactItem(
                fact_id="UNVERIFIED-001",
                category=FactCategory.SKILL,
                subject="Formal Verification",
                value={"skill_name": "JasperGold Formal Verification"},
                verified=False,  # Unverified
            ),
        ]
    )


@pytest.fixture
def target_job(db_conn):
    job_repo = JobRepository(db_conn)
    job = NormalizedJob(
        company="Qualcomm India",
        title="Design Verification Engineer",
        location="Bengaluru",
        country="India",
        skills=["SystemVerilog", "UVM", "AXI Protocol", "Async FIFO", "SVA"],
        source="manual",
        status=JobStatus.ACTIVE,
        first_seen="2026-10-04T10:00:00Z",
        last_seen="2026-10-04T10:00:00Z",
        fingerprint="qualcomm-dv-resume-test-01",
    )
    job_id = job_repo.insert_normalized_job(job)
    job.id = job_id
    return job


def test_fact_grounded_resume_generation_and_ats_quality_gate(db_conn, sample_fact_bank, target_job):
    """Test generating a tailored resume achieving >= 80 ATS quality gate and 100% Fact Integrity."""
    engine = ResumeTailoringEngine(db_conn, fact_bank=sample_fact_bank)

    resume = engine.generate_tailored_resume(job_id=target_job.id, version=1)

    assert resume.id is not None
    assert resume.resume_id.startswith("res_qualcomm_")
    assert resume.version == 1
    assert resume.fact_integrity_status == "PASS"
    assert resume.ats_score >= 80.0
    assert resume.ats_breakdown.quality_gate_met is True
    assert resume.status == ResumeStatus.READY_FOR_REVIEW

    # Check that projects and skills are present
    assert len(resume.projects) >= 2
    assert "Hardware Description & Verification" in resume.technical_skills_by_category
    assert len(resume.education) >= 1
    assert resume.education[0].graduation_year == 2025


def test_validator_rejects_unverified_and_nonexistent_facts(sample_fact_bank):
    """Test that FactIntegrityValidator catches unverified facts and nonexistent IDs."""
    validator = FactIntegrityValidator(sample_fact_bank)

    # Valid fact IDs
    is_valid, errs = validator.validate_fact_ids(["SKILL-001", "PROJ-001"])
    assert is_valid is True
    assert len(errs) == 0

    # Nonexistent fact ID
    is_valid_fake, errs_fake = validator.validate_fact_ids(["FAKE-SKILL-999"])
    assert is_valid_fake is False
    assert any("does not exist" in e for e in errs_fake)

    # Unverified fact ID
    is_valid_unver, errs_unver = validator.validate_fact_ids(["UNVERIFIED-001"])
    assert is_valid_unver is False
    assert any("unverified" in e for e in errs_unver)


def test_validator_detects_fabricated_metrics(sample_fact_bank, target_job):
    """Test that validator flags fabricated coverage percentages and bug counts."""
    validator = FactIntegrityValidator(sample_fact_bank)

    fabricated_resume = TailoredResume(
        resume_id="res_fake_001",
        target_job_id=target_job.id,
        version=1,
        generated_at="2026-10-04T10:00:00Z",
        candidate_name="Candidate",
        professional_summary="B.Tech graduate in VLSI Design Verification.",
        technical_skills_by_category={"Skills": ["SystemVerilog", "UVM"]},
        projects=[
            ResumeProject(
                title="AXI Verification",
                technologies=["SystemVerilog", "UVM"],
                source_fact_id="PROJ-001",
                bullets=[
                    ResumeBullet(
                        text="Achieved 100% coverage and found 27 bugs during regression.",
                        source_fact_ids=["PROJ-001"],
                        verified=True,
                    )
                ],
            )
        ],
        education=[
            ResumeEducation(
                degree="B.Tech",
                institution="NIT",
                graduation_year=2025,
                source_fact_id="EDU-001",
            )
        ],
        ats_score=85.0,
        ats_breakdown=ATSScorer().score_resume(
            TailoredResume.model_construct(
                resume_id="res_fake_001",
                target_job_id=target_job.id,
                version=1,
                generated_at="2026-10-04T10:00:00Z",
                candidate_name="Candidate",
                professional_summary="Summary",
                technical_skills_by_category={"Skills": ["SystemVerilog"]},
                projects=[],
                experience=[],
                education=[],
                ats_score=85.0,
                ats_breakdown=None,  # type: ignore
                fact_integrity_status="FAIL",
                source_fact_ids=["PROJ-001", "EDU-001"],
                status=ResumeStatus.DRAFT,
            ),
            job=target_job,
            fact_integrity_status="FAIL",
        ),
        fact_integrity_status="FAIL",
        source_fact_ids=["PROJ-001", "EDU-001"],
        status=ResumeStatus.NEEDS_REVISION,
    )

    report = validator.audit_resume(fabricated_resume)
    assert report.integrity_status == "FAIL"
    assert len(report.fabricated_metrics_detected) >= 1
    assert any("100% coverage" in m or "27 bugs" in m for m in report.fabricated_metrics_detected)


def test_ats_quality_gate_failure_and_missing_skills_reporting(db_conn, sample_fact_bank):
    """Test that a JD with missing requirements reports ATS TARGET NOT REACHED without fabricating skills."""
    job_repo = JobRepository(db_conn)
    # Target job requiring skills candidate does NOT possess (PCIe, Formal, UVM RAL, USB)
    unmatched_job = NormalizedJob(
        company="Synopsys Inc",
        title="Senior PCIe Formal Verification Engineer",
        skills=["PCIe Gen 5", "JasperGold Formal", "UVM RAL", "USB4", "Formal Verification"],
        source="manual",
        status=JobStatus.ACTIVE,
        first_seen="2026-10-04T10:00:00Z",
        last_seen="2026-10-04T10:00:00Z",
        fingerprint="synopsys-pcie-formal-unmatched",
    )
    job_id = job_repo.insert_normalized_job(unmatched_job)
    unmatched_job.id = job_id

    engine = ResumeTailoringEngine(db_conn, fact_bank=sample_fact_bank)
    resume = engine.generate_tailored_resume(job_id=job_id, version=1)

    # Must NOT invent PCIe or Formal skills
    assert resume.ats_breakdown.quality_gate_met is False
    assert resume.status == ResumeStatus.NEEDS_REVISION
    assert len(resume.ats_breakdown.missing_skills) >= 3
    assert any("pcie gen 5" in s for s in resume.ats_breakdown.missing_skills)
    assert any("ATS TARGET NOT REACHED" in r for r in resume.ats_breakdown.score_rationale)


def test_ats_parser_safe_formatting(db_conn, sample_fact_bank, target_job):
    """Test that rendered Markdown and Plaintext resumes conform to ATS single-column parser guidelines."""
    engine = ResumeTailoringEngine(db_conn, fact_bank=sample_fact_bank)
    resume = engine.generate_tailored_resume(job_id=target_job.id)

    # Markdown format check
    md = ATSResumeFormatter.render_markdown(resume)
    assert "# CANDIDATE NAME" in md
    assert "## PROFESSIONAL SUMMARY" in md
    assert "## TECHNICAL SKILLS" in md
    assert "## TECHNICAL PROJECTS" in md
    assert "## EDUCATION" in md
    assert "<table>" not in md.lower()
    assert "<div>" not in md.lower()

    # Plaintext format check
    txt = ATSResumeFormatter.render_plaintext(resume)
    assert "PROFESSIONAL SUMMARY" in txt
    assert "TECHNICAL SKILLS" in txt
    assert "TECHNICAL PROJECTS" in txt
    assert "EDUCATION" in txt
    assert len(txt) > 200


def test_resume_career_and_application_integration(db_conn, sample_fact_bank, target_job):
    """Test project defense generation and linking tailored resume to application tracker without premature APPLIED state."""
    engine = ResumeTailoringEngine(db_conn, fact_bank=sample_fact_bank)
    resume = engine.generate_tailored_resume(job_id=target_job.id)

    integration = ResumeCareerIntegration(db_conn)

    # 1. Generate defense questions for claimed projects
    defense_qs = integration.generate_defense_questions_for_resume(resume)
    assert len(defense_qs) >= 4
    assert any("Sequence vs Sequencer" in q.focus_aspect or "Topology" in q.focus_aspect for q in defense_qs)

    # 2. Attach tailored resume to application tracker
    app_record = integration.prepare_application_with_resume(job_id=target_job.id, resume_id=resume.resume_id)
    assert app_record.status == ApplicationStatus.READY_FOR_REVIEW
    assert app_record.tailored_resume_path == f"resumes/{resume.resume_id}.md"

    # CRITICAL: Preparing resume must NEVER transition status to APPLIED
    assert app_record.status != ApplicationStatus.APPLIED


def test_ats_resume_versioning_and_immutability(db_conn, sample_fact_bank, target_job):
    """Test that resumes are versioned sequentially and previous versions are preserved."""
    engine = ResumeTailoringEngine(db_conn, fact_bank=sample_fact_bank)

    # Version 1
    res_v1 = engine.generate_tailored_resume(job_id=target_job.id)
    assert res_v1.version == 1
    assert "v1" in res_v1.resume_id

    # Version 2 (auto-increment)
    res_v2 = engine.generate_tailored_resume(job_id=target_job.id)
    assert res_v2.version == 2
    assert "v2" in res_v2.resume_id

    # Version 3 (explicit version parameter)
    res_v3 = engine.generate_tailored_resume(job_id=target_job.id, version=3)
    assert res_v3.version == 3

    # Check persistence and retrieval of all versions
    all_versions = engine.resume_repo.list_resumes_for_job(target_job.id)
    assert len(all_versions) == 3
    assert [r.version for r in all_versions] == [3, 2, 1]


def test_ats_adjacent_evidence_and_unsupported_requirements(db_conn, sample_fact_bank):
    """Test that missing JD skills find truthful adjacent evidence without fabricating."""
    job_repo = JobRepository(db_conn)
    complex_job = NormalizedJob(
        company="NVIDIA",
        title="ASIC Verification Engineer - High Speed Protocols",
        skills=["PCIe Gen 5", "JasperGold Formal", "SpyGlass CDC", "Quantum Computing"],
        source="manual",
        status=JobStatus.ACTIVE,
        first_seen="2026-10-04T10:00:00Z",
        last_seen="2026-10-04T10:00:00Z",
        fingerprint="nvidia-pcie-formal-quantum-test",
    )
    job_id = job_repo.insert_normalized_job(complex_job)
    complex_job.id = job_id

    engine = ResumeTailoringEngine(db_conn, fact_bank=sample_fact_bank)
    resume = engine.generate_tailored_resume(job_id=job_id)

    breakdown = resume.ats_breakdown
    assert len(breakdown.missing_skills) >= 3

    # Check adjacent evidence mapping for known domains
    assert "pcie gen 5" in breakdown.adjacent_evidence_found
    assert "AXI4 Protocol" in breakdown.adjacent_evidence_found["pcie gen 5"]

    assert "jaspergold formal" in breakdown.adjacent_evidence_found
    assert "SystemVerilog Assertions" in breakdown.adjacent_evidence_found["jaspergold formal"]

    assert "spyglass cdc" in breakdown.adjacent_evidence_found
    assert "Async FIFO" in breakdown.adjacent_evidence_found["spyglass cdc"]

    # Check unsupported requirement with zero adjacent evidence
    assert any("quantum computing" in u.lower() for u in breakdown.unsupported_requirements)


def test_ats_resume_application_eligibility_gates(db_conn, sample_fact_bank, target_job):
    """Test the application eligibility gate checks fact integrity, score criteria, and human review."""
    engine = ResumeTailoringEngine(db_conn, fact_bank=sample_fact_bank)
    resume = engine.generate_tailored_resume(job_id=target_job.id)

    is_eligible, reasons = engine.check_application_eligibility(resume)
    assert is_eligible is True
    assert len(reasons) == 0
    assert resume.fact_integrity_status == "PASS"
    assert resume.ats_score >= 80.0

    # Test Draft status requiring human review
    resume.status = ResumeStatus.DRAFT
    is_eligible_draft, reasons_draft = engine.check_application_eligibility(resume)
    assert is_eligible_draft is True
    assert len(reasons_draft) == 1
    assert any("human review" in r.lower() for r in reasons_draft)
