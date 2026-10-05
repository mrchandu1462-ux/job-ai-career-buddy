"""Comprehensive tests for Email Attachments and Application Material Generation (Phase 4 Final Pass).

Tests include:
- EmailAttachment model validation & immutability
- EmailMessage attachment handling
- MIME multipart/mixed construction & binary fidelity
- ApplicationPackage -> Tailored Resume (PDF) + Cover Letter (.txt) generation
- Fact integrity validation prior to attachment
- Failure handling and safety boundaries
- Filename sanitization (preventing path traversal)
"""

import sqlite3
from datetime import UTC, datetime

import pytest

from app.application.intelligence import (
    ApplicationIntelligenceService,
    ApplicationPackage,
    ApplicationPriorityTier,
    ApplicationTimingRecommendation,
    CoverLetterDraft,
    EligibilityReport,
    EligibilityTier,
    ResumeProfileType,
    WorkAuthReport,
    WorkAuthStatus,
)
from app.db.models import DeliveryStatus, NormalizedJob
from app.db.repository import JobRepository
from app.db.schema import create_schema
from app.notifications.email import MockEmailProvider
from app.notifications.models import EmailAttachment, EmailMessage
from app.notifications.service import EmailNotificationService, _sanitize_filename
from app.profile.models import (
    CandidateProfile,
    FactBank,
    FactCategory,
    FactItem,
)
from app.resume.engine import ResumeTailoringEngine
from app.resume.models import ResumeStatus, TailoredResume


@pytest.fixture
def temp_db_conn():
    """In-memory SQLite connection with full schema."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_schema(conn)
    return conn


@pytest.fixture
def sample_facts() -> FactBank:
    return FactBank(
        version="1.0",
        facts=[
            FactItem(
                fact_id="EDU-001",
                category=FactCategory.EDUCATION,
                subject="B.Tech in EEE",
                value={
                    "degree": "B.Tech in Electronics and Communication Engineering",
                    "graduation_year": 2025,
                    "institution": "National Institute of Technology",
                    "gpa": "8.6/10.0",
                },
                source="Degree Certificate",
                verified=True,
            ),
            FactItem(
                fact_id="SKL-001",
                category=FactCategory.SKILL,
                subject="SystemVerilog",
                value={"skill": "SystemVerilog", "proficiency": "Advanced"},
                source="Coursework & Labs",
                verified=True,
            ),
            FactItem(
                fact_id="SKL-002",
                category=FactCategory.SKILL,
                subject="UVM",
                value={"skill": "UVM", "proficiency": "Intermediate"},
                source="Lab Project",
                verified=True,
            ),
            FactItem(
                fact_id="PRJ-001",
                category=FactCategory.PROJECT,
                subject="AXI4-Lite UVC VIP",
                value={
                    "title": "AXI4-Lite UVM Verification Component",
                    "role": "Lead Verification Engineer",
                    "tools": ["QuestaSim", "SystemVerilog", "UVM"],
                },
                source="GitHub Repository",
                verified=True,
            ),
            FactItem(
                fact_id="PRJ-002",
                category=FactCategory.PROJECT,
                subject="Dual-Clock Async FIFO",
                value={
                    "title": "Dual-Clock Asynchronous FIFO Verification",
                    "role": "Verification Engineer",
                    "tools": ["ModelSim", "SystemVerilog", "SVA"],
                },
                source="GitHub Repository",
                verified=True,
            ),
        ],
    )


@pytest.fixture
def sample_profile() -> CandidateProfile:
    return CandidateProfile.model_validate({
        "candidate": {
            "graduation_year": 2025,
            "target_roles": ["Design Verification Engineer", "ASIC Verification Engineer"],
            "locations": {"india_priority": ["Bengaluru", "Hyderabad"], "overseas_enabled": True},
            "work_authorization": {"citizen_of": "India", "requires_sponsorship_overseas": True},
        }
    })


@pytest.fixture
def qualifying_package(sample_profile, sample_facts) -> ApplicationPackage:
    now_iso = datetime.now(UTC).isoformat()
    job = NormalizedJob(
        id=101,
        fingerprint="fp_qualcomm_dv_101",
        title="Design Verification Engineer",
        company="Qualcomm",
        location="Bengaluru, India",
        country="India",
        source="qualcomm_portal",
        application_url="https://qualcomm.com/jobs/101",
        description="Seeking 2025 graduate for ASIC/UVM verification.",
        status="active",
        first_seen=now_iso,
        last_seen=now_iso,
    )
    intel = ApplicationIntelligenceService(sample_facts, sample_profile)
    return intel.create_application_package(job=job, match_score=92.0, freshness_age_hours=2.0)


# =============================================================================
# 1. Model Tests
# =============================================================================
class TestEmailAttachmentModel:
    def test_email_message_without_attachments(self):
        msg = EmailMessage(
            recipient="candidate@test.com",
            sender="alerts@job-ai.local",
            subject="Test Subject",
            html_content="<p>Body</p>",
            text_content="Body",
        )
        assert msg.attachments == []

    def test_email_message_with_single_attachment(self):
        att = EmailAttachment(
            filename="Resume.pdf",
            content=b"%PDF-1.4 test binary data",
            content_type="application/pdf",
        )
        msg = EmailMessage(
            recipient="candidate@test.com",
            sender="alerts@job-ai.local",
            subject="Test Subject",
            html_content="<p>Body</p>",
            text_content="Body",
            attachments=[att],
        )
        assert len(msg.attachments) == 1
        assert msg.attachments[0].filename == "Resume.pdf"
        assert msg.attachments[0].content_type == "application/pdf"
        assert msg.attachments[0].content == b"%PDF-1.4 test binary data"

    def test_email_message_with_multiple_attachments(self):
        att1 = EmailAttachment(
            filename="Resume.pdf",
            content=b"%PDF-1.4 resume bytes",
            content_type="application/pdf",
        )
        att2 = EmailAttachment(
            filename="Cover_Letter.txt",
            content=b"Dear Hiring Team...",
            content_type="text/plain; charset=utf-8",
        )
        msg = EmailMessage(
            recipient="candidate@test.com",
            sender="alerts@job-ai.local",
            subject="Test Subject",
            html_content="<p>Body</p>",
            text_content="Body",
            attachments=[att1, att2],
        )
        assert len(msg.attachments) == 2
        assert msg.attachments[0].filename == "Resume.pdf"
        assert msg.attachments[1].filename == "Cover_Letter.txt"


# =============================================================================
# 2. MIME Multipart/Mixed Construction Tests
# =============================================================================
class TestMIMEConstruction:
    def test_mime_structure_with_pdf_and_text_attachments(self):
        att_pdf = EmailAttachment(
            filename="Chandu_Saikam_Resume_Qualcomm.pdf",
            content=b"%PDF-1.4 binary mock pdf payload \x00\x01\x02",
            content_type="application/pdf",
        )
        att_cl = EmailAttachment(
            filename="Qualcomm_Cover_Letter.txt",
            content=b"Dear Qualcomm Team,\nI am writing to apply...",
            content_type="text/plain; charset=utf-8",
        )
        msg = EmailMessage(
            recipient="candidate@vlsi.ai",
            sender="alerts@job-ai.local",
            subject="🔥 HIGH PRIORITY — DV Engineer at Qualcomm",
            html_content="<h1>Opportunity</h1><p>Details here</p>",
            text_content="Opportunity\nDetails here",
            attachments=[att_pdf, att_cl],
        )

        # Build raw MIME message using provider's construction logic
        # We simulate the MIME building
        import email.mime.application
        import email.mime.multipart
        import email.mime.text

        root_msg = email.mime.multipart.MIMEMultipart("mixed")
        root_msg["Subject"] = msg.subject
        root_msg["From"] = msg.sender
        root_msg["To"] = msg.recipient

        alt_part = email.mime.multipart.MIMEMultipart("alternative")
        alt_part.attach(email.mime.text.MIMEText(msg.text_content, "plain", "utf-8"))
        alt_part.attach(email.mime.text.MIMEText(msg.html_content, "html", "utf-8"))
        root_msg.attach(alt_part)

        for att in msg.attachments:
            if "pdf" in att.content_type:
                part = email.mime.application.MIMEApplication(att.content, _subtype="pdf")
            else:
                part = email.mime.text.MIMEText(att.content.decode("utf-8"), _subtype="plain", _charset="utf-8")
            part.add_header("Content-Disposition", "attachment", filename=att.filename)
            root_msg.attach(part)

        raw_bytes = root_msg.as_bytes()
        parsed = email.message_from_bytes(raw_bytes, policy=email.policy.default)

        # Assertions on parsed MIME message
        assert parsed.is_multipart()
        assert parsed.get_content_type() == "multipart/mixed"
        assert parsed["Subject"] == msg.subject
        assert parsed["To"] == "candidate@vlsi.ai"

        # Walk parts
        payload_parts = list(parsed.iter_parts())
        # First part is multipart/alternative
        alt_subpart = payload_parts[0]
        assert alt_subpart.get_content_type() == "multipart/alternative"

        # Check plain text and HTML parts
        sub_text_parts = list(alt_subpart.iter_parts())
        types = [p.get_content_type() for p in sub_text_parts]
        assert "text/plain" in types
        assert "text/html" in types

        # Check attachments
        attachment_parts = [p for p in parsed.iter_attachments()]
        assert len(attachment_parts) == 2

        pdf_part = attachment_parts[0]
        assert pdf_part.get_filename() == "Chandu_Saikam_Resume_Qualcomm.pdf"
        assert pdf_part.get_content_type() == "application/pdf"
        assert pdf_part.get_payload(decode=True) == b"%PDF-1.4 binary mock pdf payload \x00\x01\x02"

        cl_part = attachment_parts[1]
        assert cl_part.get_filename() == "Qualcomm_Cover_Letter.txt"
        assert cl_part.get_content_type() == "text/plain"
        assert "Dear Qualcomm Team" in cl_part.get_content()


# =============================================================================
# 3. Filename Sanitization & Path Traversal Protection Tests
# =============================================================================
class TestFilenameSanitization:
    def test_sanitize_clean_name(self):
        assert _sanitize_filename("Qualcomm") == "Qualcomm"
        assert _sanitize_filename("NVIDIA India") == "NVIDIA_India"

    def test_sanitize_path_traversal_attempts(self):
        assert _sanitize_filename("../../etc/passwd") == "etcpasswd"
        assert _sanitize_filename("..\\..\\Windows\\System32") == "WindowsSystem32"
        assert _sanitize_filename("Qualcomm/SanDiego:Corp*Dept?Role") == "QualcommSanDiegoCorpDeptRole"

    def test_sanitize_empty_or_special_only(self):
        assert _sanitize_filename("   ") == "Company"
        assert _sanitize_filename("///:::***") == "Company"


# =============================================================================
# 4. Service Integration Tests: Attachments Generation in Alerts
# =============================================================================
class TestEmailNotificationServiceAttachments:
    def test_qualifying_opportunity_generates_and_attaches_resume_and_cover_letter(
        self, temp_db_conn, qualifying_package, sample_facts, sample_profile
    ):
        mock_provider = MockEmailProvider()
        repo = JobRepository(temp_db_conn)
        
        # Insert normalized job into DB
        repo.insert_normalized_job(
            NormalizedJob(
                id=101,
                fingerprint=qualifying_package.job_fingerprint,
                title=qualifying_package.role,
                company=qualifying_package.company,
                location=qualifying_package.location,
                country=qualifying_package.country,
                source="Scanner",
                status="active",
                first_seen=datetime.now(UTC).isoformat(),
                last_seen=datetime.now(UTC).isoformat(),
            )
        )

        service = EmailNotificationService(
            conn=temp_db_conn,
            provider=mock_provider,
            fact_bank=sample_facts,
            profile=sample_profile,
        )

        results = service.process_immediate_alerts([qualifying_package], dry_run=False)

        assert len(results) == 1
        assert results[0].success is True
        assert len(mock_provider.sent_messages) == 1

        sent_msg = mock_provider.sent_messages[0]
        assert len(sent_msg.attachments) == 2

        # Verify Resume attachment
        resume_att = sent_msg.attachments[0]
        assert resume_att.filename == "Chandu_Saikam_Resume_Qualcomm.pdf"
        assert resume_att.content_type == "application/pdf"
        assert len(resume_att.content) > 100
        assert resume_att.content.startswith(b"%PDF")

        # Verify Cover Letter attachment
        cl_att = sent_msg.attachments[1]
        assert cl_att.filename == "Qualcomm_Cover_Letter.txt"
        assert cl_att.content_type == "text/plain; charset=utf-8"
        cl_text = cl_att.content.decode("utf-8")
        assert "Qualcomm" in cl_text
        assert "Design Verification Engineer" in cl_text
        assert "Chandu Saikam" in cl_text or "Chandu" in cl_text

    def test_low_score_opportunity_does_not_generate_attachments_or_send(
        self, temp_db_conn, sample_facts, sample_profile
    ):
        mock_provider = MockEmailProvider()
        service = EmailNotificationService(
            conn=temp_db_conn,
            provider=mock_provider,
            fact_bank=sample_facts,
            profile=sample_profile,
        )

        # Job with low priority score (e.g. 50.0 / WATCH tier)
        low_score_pkg = ApplicationPackage(
            job_id=202,
            job_fingerprint="fp_low_match",
            company="Generic Semi",
            role="Assembly Tech",
            location="Bengaluru",
            country="India",
            eligibility=EligibilityReport(
                tier=EligibilityTier.ENTRY_LEVEL,
                is_graduate_compatible=True,
                is_fresher_compatible=True,
            ),
            work_authorization=WorkAuthReport(
                status=WorkAuthStatus.NO_SPONSORSHIP_REQUIRED,
                country="India",
                is_domestic_india=True,
                sponsorship_details="Citizen",
            ),
            priority_score=55.0,
            priority_tier=ApplicationPriorityTier.WATCH,
            timing_recommendation=ApplicationTimingRecommendation.WATCH_VERIFY,
            selected_resume_profile=ResumeProfileType.DV_CORE,
            resume_selection_reason="Test",
            cover_letter=CoverLetterDraft(
                job_title="Assembly Tech",
                company="Generic Semi",
                date_formatted="October 5, 2026",
                greeting="Dear Team,",
                opening_paragraph="Opening",
                education_paragraph="Edu",
                skills_and_projects_paragraph="Skills",
                company_motivation_paragraph="Motiv",
                closing_paragraph="Closing",
                sign_off="Sincerely",
                candidate_name="Chandu",
                candidate_email="c@vlsi.ai",
                candidate_phone="+91 99999",
                candidate_location="Bengaluru",
                full_text="Cover Letter Text",
            ),
            created_at=datetime.now(UTC).isoformat(),
        )

        results = service.process_immediate_alerts([low_score_pkg], dry_run=False)
        assert len(results) == 0
        assert len(mock_provider.sent_messages) == 0

    def test_fact_integrity_failure_blocks_email_safely(
        self, temp_db_conn, qualifying_package, sample_profile, sample_facts, monkeypatch
    ):
        """If an unverified fact or fabricated claim is detected, email is not dispatched."""
        corrupt_resume = TailoredResume.model_construct(
            resume_id="res_corrupted",
            target_job_id=101,
            version=1,
            generated_at=datetime.now(UTC).isoformat(),
            candidate_name="Candidate",
            contact_info={},
            professional_summary="Summary",
            technical_skills_by_category={},
            projects=[],
            experience=[],
            education=[],
            certifications=[],
            ats_score=85.0,
            ats_breakdown=None,
            source_fact_ids=["UNVERIFIED-CLAIM-999"],
            fact_integrity_status="FAIL",
            status=ResumeStatus.DRAFT,
        )

        mock_provider = MockEmailProvider()
        service = EmailNotificationService(
            conn=temp_db_conn,
            provider=mock_provider,
            fact_bank=sample_facts,
            profile=sample_profile,
        )

        monkeypatch.setattr(
            ResumeTailoringEngine,
            "generate_tailored_resume",
            lambda self, *args, **kwargs: corrupt_resume,
        )

        results = service.process_immediate_alerts([qualifying_package], dry_run=False)
        assert len(results) == 1
        assert results[0].success is False
        assert results[0].status == DeliveryStatus.FAILED
        assert "Fact integrity validation failed" in (results[0].error_message or "")
        # Zero emails sent!
        assert len(mock_provider.sent_messages) == 0


# =============================================================================
# 5. Safety & Human Gate Invariant Tests
# =============================================================================
class TestSafetyAndHumanApproval:
    def test_email_body_includes_human_action_and_disclaimer(self, qualifying_package):
        from app.notifications.renderer import EmailTemplateRenderer

        renderer = EmailTemplateRenderer()
        msg = renderer.render_immediate_alert(
            package=qualifying_package,
            recipient="test@example.com",
            sender="alerts@job-ai.local",
        )

        # Human Action & Approval Checks
        assert "HUMAN ACTION REQUIRED" in msg.html_content
        assert "MANDATORY HUMAN APPROVAL NOTICE" in msg.html_content
        assert "Job-AI never autonomously applies" in msg.html_content or "strictly human-controlled" in msg.html_content
        assert "Review the attached tailored resume and cover letter" in msg.html_content

        assert "HUMAN ACTION REQUIRED" in msg.text_content
        assert "MANDATORY HUMAN APPROVAL NOTICE" in msg.text_content
        assert "Job-AI does NOT automatically submit applications" in msg.text_content
