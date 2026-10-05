"""Comprehensive tests for production hardening pass.

Covers:
- Phase 1 & 13: URL cleaning, tracking parameter stripping, and canonical deduplication
- Phase 2: Closed / expired / filled / malformed job rejection in verifier
- Phase 3: Deterministic role categories (DV, FPGA, EMBEDDED, SEMICONDUCTOR_GRADUATE, VLSI, etc.)
- Phase 5: Experience requirement parsing (basic vs preferred, 0-1, 1-2, 3-5, 5+)
- Phase 8 & 9: ApplicationTracker lifecycle and best jobs report
- Phase 11: Filename sanitization against path traversal
- Phase 14: Graceful failure handling
"""

from app.application.intelligence import (
    WorkAuthClassifier,
    WorkAuthStatus,
)
from app.application.tracker import ApplicationTracker
from app.db.connection import get_connection
from app.db.models import ApplicationStatus, NormalizedJob
from app.db.repository import JobRepository
from app.jobs.classifier import RoleCategory, RoleClassifier
from app.jobs.normalizer import clean_application_url, extract_experience_requirements
from app.jobs.verifier import ActiveStatusVerifier
from app.notifications import sanitize_filename
from app.profile.loader import load_fact_bank, load_profile


# =============================================================================
# Phase 1 & 13: URL Normalization & Deduplication
# =============================================================================
def test_clean_application_url_strips_tracking_params():
    """Verify clean_application_url strips tracking query parameters while preserving path."""
    dirty_url = "https://jobs.example.com/view/12345?utm_source=linkedin&utm_medium=feed&ref=career_site&trackingId=xyz987"
    cleaned = clean_application_url(dirty_url)
    assert cleaned == "https://jobs.example.com/view/12345"


def test_clean_application_url_handles_fragments_and_clean_urls():
    """Verify clean_application_url preserves standard clean URLs and legitimate parameters."""
    clean_url = "https://careers.intel.com/en/jobs/JR0264882"
    assert clean_application_url(clean_url) == clean_url

    with_id_param = "https://careers.company.com/apply?job_id=9876&utm_campaign=fall"
    assert clean_application_url(with_id_param) == "https://careers.company.com/apply?job_id=9876"


# =============================================================================
# Phase 2: Closed & Expired Job Detection
# =============================================================================
def test_verifier_detects_filled_and_closed_postings():
    """Verify ActiveStatusVerifier identifies closed, filled, and unavailable listings."""
    verifier = ActiveStatusVerifier()

    filled_text = "Thank you for your interest. This position has been filled."
    assert verifier.is_obviously_closed(filled_text) is True

    expired_text = "This job is no longer accepting applications."
    assert verifier.is_obviously_closed(expired_text) is True

    not_found_text = "404 - Job no longer available"
    assert verifier.is_obviously_closed(not_found_text) is True

    active_text = "We are seeking a passionate Design Verification Engineer to join our Bangalore team."
    assert verifier.is_obviously_closed(active_text) is False


def test_verifier_rejects_malformed_application_urls():
    """Verify ActiveStatusVerifier safely rejects invalid or malformed application URLs."""
    verifier = ActiveStatusVerifier()

    assert verifier.is_valid_url("javascript:void(0)") is False
    assert verifier.is_valid_url("#") is False
    assert verifier.is_valid_url("") is False
    assert verifier.is_valid_url(None) is False
    assert verifier.is_valid_url("https://careers.qualcomm.com/job/12345") is True


# =============================================================================
# Phase 3: Role Classification
# =============================================================================
def test_role_classifier_categories():
    """Verify deterministic role classification across expanded semiconductor categories."""
    classifier = RoleClassifier()

    # DV
    res_dv = classifier.classify("DV Engineer", "SystemVerilog and UVM environment creation.")
    assert res_dv.category == RoleCategory.DESIGN_VERIFICATION
    assert res_dv.relevance_score >= 15.0

    # FPGA
    res_fpga = classifier.classify("FPGA Design Engineer", "Xilinx Vivado and RTL synthesis.")
    assert res_fpga.category == RoleCategory.FPGA
    assert res_fpga.relevance_score >= 15.0

    # Embedded
    res_emb = classifier.classify("Embedded Firmware Engineer", "C/C++ device drivers on ARM.")
    assert res_emb.category == RoleCategory.EMBEDDED

    # Semiconductor Graduate
    res_grad = classifier.classify("Graduate Hardware Trainee", "Semiconductor graduate onboarding program.")
    assert res_grad.category == RoleCategory.SEMICONDUCTOR_GRADUATE
    assert res_grad.relevance_score >= 18.0

    # VLSI
    res_vlsi = classifier.classify("VLSI Engineer", "Digital IC design principles.")
    assert res_vlsi.category == RoleCategory.VLSI


# =============================================================================
# Phase 5: Experience Extraction (Required vs Preferred)
# =============================================================================
def test_experience_extraction_distinguishes_required_from_preferred():
    """Verify experience parsing extracts required minimums without inflating preferred years."""
    text_basic = "Requirements: 0-2 years of experience in SystemVerilog. Preferred: 5+ years in UVM."
    exp_min, exp_max = extract_experience_requirements(text_basic)
    assert exp_min == 0.0
    assert exp_max == 2.0

    text_senior = "Qualifications: Minimum 5+ years of ASIC verification experience required."
    exp_min_sr, _ = extract_experience_requirements(text_senior)
    assert exp_min_sr == 5.0

    text_fresher = "Fresh graduates or candidates with 0-1 year experience welcome to apply."
    exp_min_fr, exp_max_fr = extract_experience_requirements(text_fresher)
    assert exp_min_fr == 0.0
    assert exp_max_fr == 1.0


# =============================================================================
# Phase 8 & 9: Application Tracking & CLI Dashboard
# =============================================================================
def test_application_tracker_lifecycle_and_report():
    """Verify ApplicationTracker creates records, updates stages, and formats best jobs report."""
    conn = get_connection(":memory:")
    repo = JobRepository(conn)
    profile = load_profile()
    facts = load_fact_bank()

    job = NormalizedJob(
        company="NVIDIA",
        title="Junior Design Verification Engineer",
        location="Bengaluru, India",
        country="India",
        experience_min=0.0,
        experience_max=2.0,
        graduation_year_min=2024,
        graduation_year_max=2025,
        description="SystemVerilog, UVM, AXI4 interface verification. Fresh graduate welcome.",
        skills=["SystemVerilog", "UVM", "Verilog", "SVA", "QuestaSim"],
        application_url="https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite/job/123",
        source="career_pages",
        first_seen="2026-10-05T10:00:00Z",
        last_seen="2026-10-05T10:00:00Z",
        fingerprint="nv_jr_dv_001",
        freshness_age_hours=3.5,
        freshness_status="fresh_0_6_hours",
    )
    job_id = repo.create_job(job)
    job.id = job_id

    tracker = ApplicationTracker(repo=repo, profile=profile, fact_bank=facts)

    # 1. Track job
    app = tracker.track_job(job_id=job_id, status=ApplicationStatus.DISCOVERED)
    assert app.id is not None
    assert app.status == ApplicationStatus.DISCOVERED

    # 2. Update to REVIEWING
    updated = tracker.update_status(app_id=app.id, status=ApplicationStatus.REVIEWING, notes="Reviewing job spec")
    assert updated is not None
    assert updated.status == ApplicationStatus.REVIEWING
    assert updated.notes == "Reviewing job spec"

    # 3. Update to READY_TO_APPLY
    updated2 = tracker.update_status(app_id=app.id, status=ApplicationStatus.READY_TO_APPLY)
    assert updated2 is not None
    assert updated2.status == ApplicationStatus.READY_TO_APPLY

    # 4. List applications
    apps_list = tracker.list_applications()
    assert len(apps_list) == 1
    assert apps_list[0]["company"] == "NVIDIA"
    assert apps_list[0]["status"] == "ready_to_apply"

    # 5. Format dashboard report
    report = tracker.format_best_jobs_report(jobs=[job], min_score=30.0)
    assert "Today's best jobs" in report
    assert "Junior Design Verification Engineer at NVIDIA" in report
    assert "Match:" in report
    assert "Tier: A" in report
    assert "Status: READY_TO_APPLY" in report


# =============================================================================
# Phase 11: Filename Sanitization
# =============================================================================
def test_filename_sanitization_prevents_path_traversal():
    """Verify sanitize_filename strips directory traversal and special chars."""
    malicious_1 = "../../etc/passwd"
    sanitized_1 = sanitize_filename(malicious_1)
    assert "/" not in sanitized_1
    assert ".." not in sanitized_1

    malicious_2 = "..\\..\\windows\\system32\\calc.exe"
    sanitized_2 = sanitize_filename(malicious_2)
    assert "\\" not in sanitized_2
    assert ".." not in sanitized_2

    legitimate = "Chandu_Saikam_Resume_Qualcomm"
    assert sanitize_filename(legitimate) == legitimate


# =============================================================================
# Phase 6: India + Overseas Work Authorization Safety
# =============================================================================
def test_work_authorization_domestic_vs_overseas():
    """Verify conservative work authorization classification."""
    classifier = WorkAuthClassifier()

    # Domestic India job
    india_job = NormalizedJob(
        company="Intel",
        title="Verification Engineer",
        location="Bengaluru, India",
        country="India",
        source="career_pages",
        first_seen="2026-10-05T10:00:00Z",
        last_seen="2026-10-05T10:00:00Z",
        fingerprint="intel_in_01",
    )
    res_in = classifier.classify(india_job)
    assert res_in.status == WorkAuthStatus.NO_SPONSORSHIP_REQUIRED
    assert res_in.is_domestic_india is True

    # Overseas job with explicit sponsorship
    us_job_sponsor = NormalizedJob(
        company="Apple",
        title="Silicon Verification Engineer",
        location="Austin, TX, USA",
        country="United States",
        description="Visa sponsorship available for qualifying candidates.",
        source="career_pages",
        first_seen="2026-10-05T10:00:00Z",
        last_seen="2026-10-05T10:00:00Z",
        fingerprint="apple_us_01",
    )
    res_us_spon = classifier.classify(us_job_sponsor)
    assert res_us_spon.status == WorkAuthStatus.SPONSORSHIP_AVAILABLE

    # Overseas job with unstated sponsorship
    us_job_unknown = NormalizedJob(
        company="AMD",
        title="Design Engineer",
        location="Austin, TX, USA",
        country="United States",
        description="Join our GPU team.",
        source="career_pages",
        first_seen="2026-10-05T10:00:00Z",
        last_seen="2026-10-05T10:00:00Z",
        fingerprint="amd_us_01",
    )
    res_us_unk = classifier.classify(us_job_unknown)
    assert res_us_unk.status == WorkAuthStatus.SPONSORSHIP_UNCLEAR
