"""Tests for Phase 4 Final: Application Intelligence & Human-Gated Apply Pipeline."""


from app.application.intelligence import (
    ApplicationIntelligenceService,
    ApplicationPriorityEngine,
    ApplicationPriorityTier,
    ApplicationTimingRecommendation,
    CoverLetterGenerator,
    EligibilityClassifier,
    EligibilityTier,
    ResumeProfileSelector,
    ResumeProfileType,
    WorkAuthClassifier,
    WorkAuthStatus,
)
from app.application.service import ApplicationPipelineService
from app.db.connection import get_connection
from app.db.models import (
    ApplicationStatus,
    NormalizedJob,
    RawJob,
)
from app.db.repository import JobRepository
from app.profile.models import CandidateProfile, FactBank, FactCategory, FactItem


def _make_candidate_profile() -> CandidateProfile:
    return CandidateProfile.model_validate({
        "candidate": {
            "graduation_year": 2025,
            "experience_level": "Fresher / Entry-Level",
            "target_roles": [
                "Design Verification Engineer",
                "ASIC Verification Engineer",
                "SoC Verification Engineer",
                "RTL Design Engineer",
            ],
            "locations": {
                "india_priority": ["Bengaluru", "Hyderabad", "Chennai"],
                "overseas_enabled": True,
            },
            "work_authorization": {
                "citizen_of": "India",
                "requires_sponsorship_overseas": True,
            },
        }
    })



def _make_fact_bank() -> FactBank:
    return FactBank(
        version="1.0",
        facts=[
            FactItem(
                fact_id="EDU-001",
                category=FactCategory.EDUCATION,
                subject="B.Tech in ECE",
                value={
                    "degree": "Bachelor of Technology",
                    "specialization": "Electronics and Communication Engineering",
                    "institution": "National Institute of Technology",
                    "graduation_year": 2025,
                },
                source="Transcript",
                verified=True,
            ),
            FactItem(
                fact_id="SKILL-001",
                category=FactCategory.SKILL,
                subject="SystemVerilog",
                value={"skill_name": "SystemVerilog", "proficiency": "Advanced"},
                source="Coursework",
                verified=True,
            ),
            FactItem(
                fact_id="SKILL-002",
                category=FactCategory.SKILL,
                subject="UVM",
                value={"skill_name": "UVM", "proficiency": "Intermediate"},
                source="Project",
                verified=True,
            ),
            FactItem(
                fact_id="PROJ-001",
                category=FactCategory.PROJECT,
                subject="AXI4-Lite UVC Testbench",
                value={
                    "title": "AXI4-Lite Slave Verification IP",
                    "technologies": ["SystemVerilog", "UVM", "SVA", "QuestaSim"],
                },
                source="GitHub",
                verified=True,
            ),
        ],
    )


def _make_job(**kwargs) -> NormalizedJob:
    defaults = {
        "company": "Qualcomm India",
        "title": "Design Verification Engineer — 2025 Graduate",
        "location": "Bengaluru, India",
        "country": "India",
        "source": "career_page",
        "first_seen": "2026-10-04T00:00:00Z",
        "last_seen": "2026-10-04T00:00:00Z",
        "fingerprint": "qualcomm-dv-2025-blr",
        "description": "SystemVerilog, UVM, constrained random testing, AXI4 bus verification, and SVA assertions.",
        "requirements": "B.Tech ECE/EEE 2025 graduate. 0-1 years experience.",
        "skills": ["SystemVerilog", "UVM", "AXI4", "SVA"],
        "experience_min": 0.0,
        "application_url": "https://qualcomm.wd5.myworkdayjobs.com/careers/dv-2025",
    }
    defaults.update(kwargs)
    return NormalizedJob(**defaults)


# -----------------------------------------------------------------------------
# Test Cases
# -----------------------------------------------------------------------------


def test_eligibility_classification_entry_and_graduate():
    classifier = EligibilityClassifier()
    job_grad = _make_job(title="Design Verification Engineer — Campus GET", experience_min=0.0)
    report = classifier.classify(job_grad, candidate_grad_year=2025)

    assert report.tier in (EligibilityTier.GRADUATE, EligibilityTier.ENTRY_LEVEL)
    assert report.is_graduate_compatible is True
    assert report.is_fresher_compatible is True


def test_eligibility_classification_senior_rejection():
    classifier = EligibilityClassifier()
    job_sr = _make_job(
        title="Principal ASIC Verification Engineer",
        experience_min=8.0,
        requirements="Requires 8+ years of industry experience.",
    )
    report = classifier.classify(job_sr, candidate_grad_year=2025)

    assert report.tier == EligibilityTier.SENIOR
    assert report.is_graduate_compatible is False
    assert report.is_fresher_compatible is False
    assert any("8" in w for w in report.warnings)


def test_eligibility_classification_internship():
    classifier = EligibilityClassifier()
    job_intern = _make_job(title="VLSI Design Verification Intern", experience_min=0.0)
    report = classifier.classify(job_intern, candidate_grad_year=2025)

    assert report.tier == EligibilityTier.INTERNSHIP
    assert report.is_graduate_compatible is True


def test_work_authorization_domestic_india():
    classifier = WorkAuthClassifier()
    job_in = _make_job(location="Bengaluru, India", country="India")
    report = classifier.classify(job_in, candidate_citizen_of="India")

    assert report.status == WorkAuthStatus.NO_SPONSORSHIP_REQUIRED
    assert report.is_domestic_india is True


def test_work_authorization_overseas_sponsorship_explicit():
    classifier = WorkAuthClassifier()
    job_us_sponsor = _make_job(
        location="Austin, TX, USA",
        country="USA",
        description="Visa sponsorship available for qualified candidates.",
    )
    report = classifier.classify(job_us_sponsor, candidate_citizen_of="India")

    assert report.status == WorkAuthStatus.SPONSORSHIP_AVAILABLE
    assert report.is_domestic_india is False


def test_work_authorization_overseas_no_sponsorship():
    classifier = WorkAuthClassifier()
    job_us_nosponsor = _make_job(
        location="Santa Clara, CA, USA",
        country="USA",
        description="Must be authorized to work in the US without requiring sponsorship.",
    )
    report = classifier.classify(job_us_nosponsor, candidate_citizen_of="India")

    assert report.status == WorkAuthStatus.LOCAL_AUTHORIZATION_REQUIRED
    assert report.is_domestic_india is False
    assert len(report.warnings) > 0


def test_resume_profile_selection_tracks():
    selector = ResumeProfileSelector()
    classifier = EligibilityClassifier()

    # Core DV
    job_dv = _make_job(title="Design Verification Engineer")
    el_dv = classifier.classify(job_dv)
    p_dv, _ = selector.select_profile(job_dv, el_dv)
    assert p_dv == ResumeProfileType.DV_CORE

    # ASIC
    job_asic = _make_job(title="ASIC Verification Engineer")
    el_asic = classifier.classify(job_asic)
    p_asic, _ = selector.select_profile(job_asic, el_asic)
    assert p_asic == ResumeProfileType.ASIC_VERIFICATION

    # RTL
    job_rtl = _make_job(title="RTL Design Engineer")
    el_rtl = classifier.classify(job_rtl)
    p_rtl, _ = selector.select_profile(job_rtl, el_rtl)
    assert p_rtl == ResumeProfileType.RTL_DESIGN

    # Intern
    job_intern = _make_job(title="Silicon Verification Intern")
    el_intern = classifier.classify(job_intern)
    p_intern, _ = selector.select_profile(job_intern, el_intern)
    assert p_intern == ResumeProfileType.VLSI_INTERN

    # Overseas
    job_overseas = _make_job(title="Design Verification Engineer", location="Munich, Germany", country="Germany")
    el_overseas = classifier.classify(job_overseas)
    p_overseas, _ = selector.select_profile(job_overseas, el_overseas)
    assert p_overseas == ResumeProfileType.OVERSEAS_DV


def test_cover_letter_generation_grounded_in_facts():
    facts = _make_fact_bank()
    profile = _make_candidate_profile()
    gen = CoverLetterGenerator(facts, profile)
    job = _make_job(company="Texas Instruments", title="Digital Verification Engineer")

    draft = gen.generate(job, ResumeProfileType.DV_CORE)

    assert "Texas Instruments" in draft.company
    assert "Digital Verification Engineer" in draft.job_title
    assert "SystemVerilog" in draft.full_text
    assert "UVM" in draft.full_text
    assert "AXI4-Lite" in draft.full_text
    assert "2025" in draft.full_text
    # Ensure zero fabricated company claims
    assert "I have worked 10 years at Texas Instruments" not in draft.full_text


def test_priority_engine_scoring_and_gating():
    engine = ApplicationPriorityEngine()
    classifier = EligibilityClassifier()
    auth_classifier = WorkAuthClassifier()

    job_high = _make_job(experience_min=0.0)
    el_high = classifier.classify(job_high)
    auth_high = auth_classifier.classify(job_high)

    score, tier, timing = engine.compute_priority(
        job=job_high,
        match_score=90.0,
        eligibility=el_high,
        work_auth=auth_high,
        freshness_age_hours=3.0,
    )

    assert score >= 85.0
    assert tier in (ApplicationPriorityTier.CRITICAL, ApplicationPriorityTier.HIGH)
    assert timing in (ApplicationTimingRecommendation.APPLY_NOW, ApplicationTimingRecommendation.HIGH_PRIORITY)

    # Ineligible gating check
    job_senior = _make_job(title="Staff DV Engineer", experience_min=6.0)
    el_senior = classifier.classify(job_senior)
    auth_senior = auth_classifier.classify(job_senior)

    score_sr, tier_sr, timing_sr = engine.compute_priority(
        job=job_senior,
        match_score=95.0,  # High technical match should be gated by senior requirement
        eligibility=el_senior,
        work_auth=auth_senior,
        freshness_age_hours=2.0,
    )

    assert score_sr <= 45.0
    assert tier_sr == ApplicationPriorityTier.SKIP
    assert timing_sr == ApplicationTimingRecommendation.SKIP


def test_application_package_creation_and_queue():
    facts = _make_fact_bank()
    profile = _make_candidate_profile()
    service = ApplicationIntelligenceService(facts, profile)

    job = _make_job(title="Design Verification Engineer")
    package = service.create_application_package(job, match_score=85.0, freshness_age_hours=4.0)

    assert package.company == "Qualcomm India"
    assert package.priority_tier in (ApplicationPriorityTier.CRITICAL, ApplicationPriorityTier.HIGH)
    assert package.selected_resume_profile == ResumeProfileType.DV_CORE
    assert package.cover_letter is not None
    assert package.url_verification_status == "VERIFIED"
    assert package.application_status == ApplicationStatus.DISCOVERED


def test_human_approval_pipeline_lifecycle():
    conn = get_connection(":memory:", auto_init=True)
    job_repo = JobRepository(conn)
    facts = _make_fact_bank()
    profile = _make_candidate_profile()
    service = ApplicationPipelineService(conn, profile, facts)

    # Insert a job
    job = _make_job()
    raw_id = job_repo.insert_raw_job(
        RawJob(
            source="career_page",
            source_url="https://ti.com/job/123",
            discovered_at="2026-10-04T00:00:00Z",
            raw_payload="{}",
            content_hash="mockhash123",
        )
    )
    job.raw_job_id = raw_id
    job_id = job_repo.insert_normalized_job(job)

    # 1. Build Package
    pkg = service.build_application_package(job_id)
    assert pkg.job_id == job_id
    assert pkg.priority_score > 0

    # 2. Shortlist
    app_rec = service.shortlist_job(job_id)
    assert app_rec.status == ApplicationStatus.SHORTLISTED

    # 3. Review & Approve (Sets internal state to APPROVED)
    reviewed = service.review_application(app_rec.id, decision="APPROVE")
    assert reviewed.status == ApplicationStatus.APPROVED

    # Invariant: Approved does NOT mean submitted!
    re_read = job_repo.get_application(app_rec.id)
    assert re_read.status == ApplicationStatus.APPROVED
    assert re_read.applied_at is None

    # 4. Human Confirms Manual Submission
    submitted = service.record_submission(
        application_id=app_rec.id,
        reference_id="TI-REQ-2025-998",
        submission_evidence="Confirmed manual submission on TI workday portal.",
    )
    assert submitted.reference_id == "TI-REQ-2025-998"

    final_app = job_repo.get_application(app_rec.id)
    assert final_app.status == ApplicationStatus.APPLIED
    assert final_app.applied_at is not None



def test_duplicate_application_prevention():
    conn = get_connection(":memory:", auto_init=True)
    job_repo = JobRepository(conn)
    facts = _make_fact_bank()
    profile = _make_candidate_profile()
    service = ApplicationPipelineService(conn, profile, facts)

    job = _make_job()
    raw_id = job_repo.insert_raw_job(
        RawJob(
            source="career_page",
            source_url="https://ti.com/job/123",
            discovered_at="2026-10-04T00:00:00Z",
            raw_payload="{}",
            content_hash="mockhash456",
        )
    )
    job.raw_job_id = raw_id
    job_id = job_repo.insert_normalized_job(job)

    # First shortlist
    app1 = service.shortlist_job(job_id)
    # Second shortlist on same job does NOT create duplicate application row
    app2 = service.shortlist_job(job_id)

    assert app1.id == app2.id
    all_apps = job_repo.list_applications()
    assert len(all_apps) == 1

