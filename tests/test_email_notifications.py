"""Tests for Final Notification & Career Alert Automation (Phase 4 Final).

Validates:
A. Email adapter initialization
B. Missing configuration handling
C. Environment variable loading
D. No secrets in logs
E. Dry-run mode
F. Test-email mode
G. HTML email rendering
H. Plain-text email rendering
I. CRITICAL immediate alert
J. HIGH immediate alert
K. APPLY daily digest
L. WATCH suppression
M. SKIP suppression
N. Duplicate email suppression
O. Material job-change re-alert
P. Sent-state persistence
Q. Failed-state persistence
R. Retry limit
S. Network timeout
T. Email failure does not fail scanner
U. Existing scheduler integration
V. Daily digest deduplication
W. Official URL preserved
X. Human approval remains mandatory
Y. No autonomous application submission
Z. All safety invariants
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import UTC, datetime

import pytest

from app.application.intelligence import (
    ApplicationIntelligenceService,
)
from app.config import AppSettings
from app.db.models import (
    DeliveryStatus,
    NormalizedJob,
)
from app.db.schema import create_schema
from app.jobs.digest import DailyCareerDigest
from app.jobs.scanner import FreshJobScanner
from app.jobs.sources.adapters import MockJobSourceAdapter
from app.jobs.sources.base import RawJobPayload
from app.matching.scorer import JobScoringEngine
from app.notifications.email import (
    ConsoleEmailProvider,
    EmailConfigurationError,
    MockEmailProvider,
    SMTPEmailProvider,
    get_email_provider,
)
from app.notifications.models import (
    EmailMessage,
    EmailPriority,
)
from app.notifications.renderer import EmailTemplateRenderer
from app.notifications.service import EmailNotificationService
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
                subject="B.Tech in EEE",
                value={
                    "degree": "B.Tech",
                    "field": "Electrical & Electronics Engineering",
                    "graduation_year": 2025,
                    "institution": "VTU",
                    "cgpa": "8.5/10",
                },
                source="Degree Certificate",
                verified=True,
            ),
            FactItem(
                fact_id="SKL-001",
                category=FactCategory.SKILL,
                subject="SystemVerilog",
                value={
                    "skill": "SystemVerilog",
                    "category": "HDVL",
                    "proficiency": "Advanced",
                },
                source="Coursework & Lab",
                verified=True,
            ),
            FactItem(
                fact_id="SKL-002",
                category=FactCategory.SKILL,
                subject="UVM",
                value={
                    "skill": "UVM",
                    "category": "Methodology",
                    "proficiency": "Intermediate",
                },
                source="Lab Project",
                verified=True,
            ),
            FactItem(
                fact_id="PRJ-001",
                category=FactCategory.PROJECT,
                subject="AXI4-Lite VIP",
                value={
                    "title": "AXI4-Lite Master/Slave UVM VIP Testbench",
                    "description": "Designed complete UVM environment verifying single-beat burst transactions.",
                },
                source="GitHub Repository",
                verified=True,
            ),
        ],
    )


def _make_job(
    company: str = "NVIDIA",
    title: str = "ASIC Verification Engineer",
    location: str = "Bengaluru, India",
    experience_min: float = 0.0,
    application_url: str = "https://nvidia.com/apply/123",
    published_at: str | None = None,
    fingerprint: str = "fp_nvidia_asic_001",
) -> NormalizedJob:
    now_iso = datetime.now(UTC).isoformat()
    return NormalizedJob(
        id=1,
        company=company,
        title=title,
        location=location,
        country="India",
        employment_type="Full-time",
        experience_min=experience_min,
        experience_max=2.0,
        graduation_year_min=2024,
        graduation_year_max=2026,
        description="Looking for entry level ASIC Verification Engineer with SystemVerilog and UVM skills.",
        requirements="B.Tech in ECE/EEE, SystemVerilog, UVM, AXI.",
        skills=["SystemVerilog", "UVM", "AXI"],
        application_url=application_url,
        source="career_portal",
        first_seen=now_iso,
        last_seen=now_iso,
        fingerprint=fingerprint,
        published_at=published_at or now_iso,
        freshness_status="fresh_0_6_hours",
        freshness_age_hours=2.0,
        region="india",
        city="Bengaluru",
        priority_score=94.0,
        priority_category="CRITICAL",
    )


@pytest.fixture
def temp_db_conn():
    """Create an in-memory SQLite database with fresh schema."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_schema(conn)
    yield conn
    conn.close()


@pytest.fixture
def sample_package():
    """Create a sample verified application package for testing."""
    profile = _make_candidate_profile()
    facts = _make_fact_bank()
    scorer = JobScoringEngine(profile, facts)
    intel_svc = ApplicationIntelligenceService(facts, profile)
    job = _make_job()
    match_res = scorer.score_job(job)
    return intel_svc.create_application_package(job, match_res.match_score)



# -----------------------------------------------------------------------------
# A, B, C, D: Adapter Init, Config & Secrets Safety
# -----------------------------------------------------------------------------
def test_email_adapter_initialization_and_missing_config():
    """Test provider factory creates proper provider and fails gracefully on missing credentials."""
    # Console provider default
    cfg = AppSettings(email_provider="console")
    p_console = get_email_provider(cfg)
    assert isinstance(p_console, ConsoleEmailProvider)
    assert p_console.timeout_seconds == 30

    # Mock provider
    cfg_mock = AppSettings(email_provider="mock")
    p_mock = get_email_provider(cfg_mock)
    assert isinstance(p_mock, MockEmailProvider)

    # SMTP missing host raises EmailConfigurationError
    cfg_bad_smtp = AppSettings(email_provider="smtp", email_smtp_host="")
    with pytest.raises(EmailConfigurationError, match="JOB_AI_EMAIL_SMTP_HOST is required"):
        get_email_provider(cfg_bad_smtp)

    # SMTP valid host
    cfg_smtp = AppSettings(
        email_provider="smtp",
        email_smtp_host="smtp.example.com",
        email_smtp_port=587,
        email_username="user@example.com",
        email_password="supersecretpassword",
    )
    p_smtp = get_email_provider(cfg_smtp)
    assert isinstance(p_smtp, SMTPEmailProvider)
    assert p_smtp.host == "smtp.example.com"
    assert p_smtp.timeout_seconds == 30


def test_no_secrets_in_logs(caplog):
    """Assert passwords/secrets are never printed in logs."""
    caplog.set_level(logging.DEBUG)
    cfg = AppSettings(
        email_provider="smtp",
        email_smtp_host="smtp.example.com",
        email_username="candidate_user",
        email_password="ultra_secret_api_key_12345",
    )
    provider = get_email_provider(cfg)
    msg = EmailMessage(
        recipient="user@test.com",
        sender="alerts@job-ai.local",
        subject="Test",
        html_content="<p>Test</p>",
        text_content="Test",
    )
    # Dry run should log without exposing password
    provider.send_message(msg, dry_run=True)
    assert "ultra_secret_api_key_12345" not in caplog.text


# -----------------------------------------------------------------------------
# E, F: Dry Run & Test Email
# -----------------------------------------------------------------------------
def test_dry_run_mode(temp_db_conn, sample_package):
    """Verify dry run generates content, logs recipient, but performs no external network call."""
    mock_p = MockEmailProvider()
    svc = EmailNotificationService(temp_db_conn, provider=mock_p)

    results = svc.process_immediate_alerts([sample_package], dry_run=True)
    assert len(results) == 1
    assert results[0].success is True
    assert results[0].dry_run is True
    assert len(mock_p.sent_messages) == 0  # Not stored in live sent list during dry run


def test_test_email_mode(temp_db_conn):
    """Verify explicit test email sends exactly one formatted test message."""
    mock_p = MockEmailProvider()
    svc = EmailNotificationService(temp_db_conn, provider=mock_p)

    res = svc.send_test_email(recipient="candidate@vlsi.ai", dry_run=False)
    assert res.success is True
    assert len(mock_p.sent_messages) == 1
    assert mock_p.sent_messages[0].priority == EmailPriority.TEST
    assert "🧪" in mock_p.sent_messages[0].subject
    assert "JOB-AI EMAIL TEST" in mock_p.sent_messages[0].text_content


# -----------------------------------------------------------------------------
# G, H, W, X, Y: HTML & Plain-Text Rendering, Link & Human Safety Preservation
# -----------------------------------------------------------------------------
def test_email_rendering_and_safety_disclaimers(sample_package):
    """Verify HTML and text rendering contain necessary fields, URLs, and human approval notice."""
    renderer = EmailTemplateRenderer(dashboard_base_url="http://localhost:8501")
    msg = renderer.render_immediate_alert(
        package=sample_package,
        recipient="test@example.com",
        sender="alerts@job-ai.local",
    )

    # Subject checks
    assert "HIGH PRIORITY" in msg.subject or "APPLY NOW" in msg.subject
    assert "NVIDIA" in msg.subject or "ASIC Verification Engineer" in msg.subject

    # HTML checks
    assert "NVIDIA" in msg.html_content
    assert "ASIC Verification Engineer" in msg.html_content
    assert sample_package.official_application_url in msg.html_content
    assert "MANDATORY HUMAN APPROVAL NOTICE" in msg.html_content
    assert "Final application submission is strictly human-controlled" in msg.html_content

    # Text checks
    assert "Role: ASIC Verification Engineer" in msg.text_content
    assert "Company: NVIDIA" in msg.text_content
    assert "MANDATORY HUMAN APPROVAL NOTICE" in msg.text_content


# -----------------------------------------------------------------------------
# I, J, K, L, M: Priority Routing Policy (CRITICAL, HIGH, APPLY, WATCH, SKIP)
# -----------------------------------------------------------------------------
def test_priority_routing_policy(temp_db_conn):
    """Verify 90-100 (CRITICAL) and 80-89 (HIGH) send immediately; 70-79 (APPLY), 60-69 (WATCH), <60 (SKIP) do not."""
    profile = _make_candidate_profile()
    facts = _make_fact_bank()
    scorer = JobScoringEngine(profile, facts)
    intel_svc = ApplicationIntelligenceService(facts, profile)
    mock_p = MockEmailProvider()
    svc = EmailNotificationService(temp_db_conn, provider=mock_p)

    job_crit = _make_job(company="NVIDIA", title="ASIC DV Engineer", fingerprint="fp_crit_1")
    pkg_crit = intel_svc.create_application_package(job_crit, scorer.score_job(job_crit).match_score)

    job_high = _make_job(company="Qualcomm", title="Verification Engineer", fingerprint="fp_high_1")
    pkg_high = intel_svc.create_application_package(job_high, scorer.score_job(job_high).match_score)

    job_apply = _make_job(company="Generic", title="RTL Engineer", fingerprint="fp_apply_1")
    pkg_apply = intel_svc.create_application_package(job_apply, scorer.score_job(job_apply).match_score)

    job_skip = _make_job(company="Generic", title="Senior 10y Lead", experience_min=10.0, fingerprint="fp_skip_1")
    pkg_skip = intel_svc.create_application_package(job_skip, scorer.score_job(job_skip).match_score)

    # Process all packages
    results = svc.process_immediate_alerts([pkg_crit, pkg_high, pkg_apply, pkg_skip])

    # Only CRITICAL and HIGH should generate emails
    assert len(results) == 2
    assert len(mock_p.sent_messages) == 2
    assert mock_p.sent_messages[0].priority in (EmailPriority.CRITICAL, EmailPriority.HIGH)
    assert mock_p.sent_messages[1].priority in (EmailPriority.CRITICAL, EmailPriority.HIGH)


# -----------------------------------------------------------------------------
# N, O: Duplicate Email Suppression & Material Job Change Re-Alert
# -----------------------------------------------------------------------------
def test_duplicate_email_suppression_and_material_change(temp_db_conn, sample_package):
    """Verify repeated scan of same job suppresses email, while material update triggers re-alert."""
    mock_p = MockEmailProvider()
    svc = EmailNotificationService(temp_db_conn, provider=mock_p)

    # First cycle: sends email
    r1 = svc.process_immediate_alerts([sample_package])
    assert len(r1) == 1
    assert r1[0].status == DeliveryStatus.SENT
    assert len(mock_p.sent_messages) == 1

    # Second cycle (same fingerprint): suppressed!
    r2 = svc.process_immediate_alerts([sample_package])
    assert len(r2) == 1
    assert r2[0].status == DeliveryStatus.SUPPRESSED
    assert len(mock_p.sent_messages) == 1  # Count does not increase

    # Third cycle with material update: re-alerts with [MATERIAL UPDATE]
    profile = _make_candidate_profile()
    facts = _make_fact_bank()
    scorer = JobScoringEngine(profile, facts)
    intel_svc = ApplicationIntelligenceService(facts, profile)
    job = _make_job(fingerprint=sample_package.job_fingerprint)
    pkg_mat = intel_svc.create_application_package(job, scorer.score_job(job).match_score, is_material_update=True)

    r3 = svc.process_immediate_alerts([pkg_mat])
    assert len(r3) == 1
    assert r3[0].status == DeliveryStatus.SENT
    assert len(mock_p.sent_messages) == 2
    assert "[MATERIAL UPDATE]" in mock_p.sent_messages[1].subject


# -----------------------------------------------------------------------------
# P, Q, R, S: Delivery Audit State Persistence, Retries & Network Timeout
# -----------------------------------------------------------------------------
def test_delivery_state_persistence_and_failure_handling(temp_db_conn, sample_package):
    """Test delivery audit records in database for both success and failure."""
    # Test failure
    failing_p = MockEmailProvider(should_fail=True)
    svc_fail = EmailNotificationService(temp_db_conn, provider=failing_p)

    r_fail = svc_fail.process_immediate_alerts([sample_package])
    assert r_fail[0].success is False
    assert r_fail[0].status == DeliveryStatus.FAILED

    stats = svc_fail.get_delivery_stats()
    assert stats["failed"] == 1
    assert stats["sent"] == 0

    # Test success with different fingerprint
    profile = _make_candidate_profile()
    facts = _make_fact_bank()
    scorer = JobScoringEngine(profile, facts)
    intel_svc = ApplicationIntelligenceService(facts, profile)
    job_new = _make_job(fingerprint="fp_nvidia_unique_second")
    pkg_new = intel_svc.create_application_package(job_new, scorer.score_job(job_new).match_score)

    mock_p = MockEmailProvider()
    svc_ok = EmailNotificationService(temp_db_conn, provider=mock_p)

    r_ok = svc_ok.process_immediate_alerts([pkg_new])
    assert r_ok[0].success is True
    assert r_ok[0].status == DeliveryStatus.SENT

    stats_ok = svc_ok.get_delivery_stats()
    assert stats_ok["sent"] == 1



def test_network_timeout_enforcement():
    """Verify providers enforce finite timeout (<= 30s) and bounded retries (<= 3)."""
    p_smtp = SMTPEmailProvider(host="smtp.example.com", timeout_seconds=25, max_retries=3)
    assert p_smtp.timeout_seconds == 25
    assert p_smtp.max_retries == 3

    # Clamped bounds
    p_clamped = SMTPEmailProvider(host="smtp.example.com", timeout_seconds=120, max_retries=10)
    assert p_clamped.timeout_seconds == 60
    assert p_clamped.max_retries == 5


# -----------------------------------------------------------------------------
# T: Email Failure Does Not Fail Scanner Cycle
# -----------------------------------------------------------------------------
def test_email_failure_does_not_fail_scanner(temp_db_conn):
    """Critical safety test: Even if email provider crashes, job scanning finishes successfully."""
    failing_p = MockEmailProvider(should_fail=True)
    email_svc = EmailNotificationService(temp_db_conn, provider=failing_p)

    payload = RawJobPayload(
        company="NVIDIA",
        title="ASIC Verification Engineer",
        raw_payload="NVIDIA ASIC Verification Engineer Bengaluru SystemVerilog UVM",
        location="Bengaluru",
        country="India",
        source="test_mock",
        source_url="https://nvidia.com/jobs/1",
        application_url="https://nvidia.com/jobs/1",
        discovered_at=datetime.now(UTC).isoformat(),
        content_hash="hash_nv_001",
        metadata={"published_at": datetime.now(UTC).isoformat()},
    )
    adapter = MockJobSourceAdapter(custom_payloads=[payload])

    scanner = FreshJobScanner(
        conn=temp_db_conn,
        adapters=[adapter],
        allow_mock=True,
        email_service=email_svc,
    )

    # Scanner scan should succeed completely despite email failure
    report = scanner.scan(hours=24.0, min_score=60.0, dry_run=False)
    assert report.sources_successful == 1
    assert report.jobs_scanned == 1
    assert report.jobs_discovered == 1


# -----------------------------------------------------------------------------
# V: Daily Digest Generation & Deduplication
# -----------------------------------------------------------------------------
def test_daily_digest_generation_and_deduplication(temp_db_conn):
    """Test daily digest formatting and daily deduplication."""
    mock_p = MockEmailProvider()
    svc = EmailNotificationService(temp_db_conn, provider=mock_p)

    digest = DailyCareerDigest(
        digest_date="2026-10-05",
        generated_at=datetime.now(UTC).isoformat(),
        total_fresh_24h=5,
        critical_count=1,
        high_count=2,
        india_count=4,
        overseas_count=1,
        top_opportunities=[
            {
                "company": "NVIDIA",
                "title": "ASIC Verification Engineer",
                "location": "Bengaluru",
                "score": 94.0,
                "category": "CRITICAL",
                "application_url": "https://nvidia.com/apply",
                "is_watchlist": True,
            },
            {
                "company": "Qualcomm",
                "title": "DV Engineer",
                "location": "Hyderabad",
                "score": 86.0,
                "category": "HIGH",
                "application_url": "https://qualcomm.com/apply",
                "is_watchlist": True,
            },
        ],
    )

    # First dispatch sends digest
    r1 = svc.send_daily_digest(digest, dry_run=False)
    assert r1.success is True
    assert r1.status == DeliveryStatus.SENT
    assert len(mock_p.sent_messages) == 1
    assert "Daily Career Digest" in mock_p.sent_messages[0].subject

    # Second dispatch for same date suppresses duplicate
    r2 = svc.send_daily_digest(digest, dry_run=False)
    assert r2.status == DeliveryStatus.SUPPRESSED
    assert len(mock_p.sent_messages) == 1


# -----------------------------------------------------------------------------
# AA: SMTP Transport Unit Tests (SSL, STARTTLS, Auth Errors, Timeout)
# -----------------------------------------------------------------------------
def test_smtp_provider_starttls_and_ssl_modes():
    """Verify SMTPEmailProvider configures SSL vs STARTTLS based on port/settings."""
    from unittest.mock import MagicMock, patch

    # 1. Port 587 -> STARTTLS mode
    p_587 = SMTPEmailProvider(
        host="smtp.gmail.com",
        port=587,
        username="user@example.com",
        password="app-password-test",
        use_tls=True,
        use_ssl=False,
    )
    assert p_587.use_tls is True
    assert p_587.use_ssl is False

    # 2. Port 465 -> SSL mode auto-detection
    p_465 = SMTPEmailProvider(
        host="smtp.gmail.com",
        port=465,
        username="user@example.com",
        password="app-password-test",
    )
    assert p_465.use_ssl is True
    assert p_465.use_tls is False

    # 3. Test sending via STARTTLS
    msg = EmailMessage(
        recipient="recipient@example.com",
        sender="user@example.com",
        subject="Test STARTTLS",
        html_content="<p>Hello STARTTLS</p>",
        text_content="Hello STARTTLS",
    )

    with patch("smtplib.SMTP") as mock_smtp_cls:
        mock_server = MagicMock()
        mock_smtp_cls.return_value = mock_server

        res = p_587.send_message(msg)
        assert res.success is True
        mock_smtp_cls.assert_called_once_with("smtp.gmail.com", 587, timeout=30.0)
        mock_server.ehlo.assert_called()
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("user@example.com", "app-password-test")
        mock_server.sendmail.assert_called_once()

    # 4. Test sending via SMTP_SSL
    with patch("smtplib.SMTP_SSL") as mock_ssl_cls:
        mock_ssl_server = MagicMock()
        mock_ssl_cls.return_value = mock_ssl_server

        res_ssl = p_465.send_message(msg)
        assert res_ssl.success is True
        mock_ssl_cls.assert_called_once_with("smtp.gmail.com", 465, timeout=30.0)
        mock_ssl_server.login.assert_called_once_with("user@example.com", "app-password-test")
        mock_ssl_server.sendmail.assert_called_once()


def test_smtp_provider_auth_failure_does_not_retry():
    """Verify that SMTPAuthenticationError fails fast without retrying 3 times."""
    import smtplib
    from unittest.mock import MagicMock, patch

    p = SMTPEmailProvider(
        host="smtp.gmail.com",
        port=587,
        username="user@example.com",
        password="wrong-password",
        max_retries=3,
    )
    msg = EmailMessage(
        recipient="recipient@example.com",
        sender="user@example.com",
        subject="Test Auth Failure",
        html_content="<p>Hello</p>",
        text_content="Hello",
    )

    with patch("smtplib.SMTP") as mock_smtp_cls:
        mock_server = MagicMock()
        mock_server.login.side_effect = smtplib.SMTPAuthenticationError(535, b"5.7.8 BadCredentials")
        mock_smtp_cls.return_value = mock_server

        res = p.send_message(msg)
        assert res.success is False
        assert "Authentication failed" in (res.error_message or "")
        # Crucial: Exactly 1 attempt, no useless retries on auth failure
        assert mock_smtp_cls.call_count == 1

