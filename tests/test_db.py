"""Tests for SQLite schema, models, connection management, and repository operations."""

import hashlib
import json
from pathlib import Path

import pytest

from app.db.connection import DatabaseConnection, get_connection, get_db
from app.db.models import (
    ApplicationRecord,
    ApplicationStatus,
    JobStatus,
    NormalizedJob,
    RawJob,
)
from app.db.repository import DuplicateFingerprintError, JobRepository


@pytest.fixture
def memory_db():
    """Provides an initialized in-memory database connection for testing."""
    with get_db(":memory:") as conn:
        yield conn


@pytest.fixture
def repo(memory_db):
    """Provides a JobRepository instance backed by the in-memory database."""
    return JobRepository(memory_db)


def test_database_initialization(memory_db):
    """Verify database connection and required pragmas."""
    cursor = memory_db.execute("PRAGMA foreign_keys;")
    assert cursor.fetchone()[0] == 1


def test_table_creation(memory_db):
    """Verify that all three core tables exist after schema creation."""
    cursor = memory_db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"
    )
    table_names = [row[0] for row in cursor.fetchall()]
    assert "raw_jobs" in table_names
    assert "normalized_jobs" in table_names
    assert "applications" in table_names


def test_indexes_creation(memory_db):
    """Verify that expected indexes exist."""
    cursor = memory_db.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%';"
    )
    index_names = [row[0] for row in cursor.fetchall()]
    assert "idx_normalized_jobs_fingerprint" in index_names
    assert "idx_normalized_jobs_company" in index_names
    assert "idx_normalized_jobs_status" in index_names
    assert "idx_normalized_jobs_location" in index_names
    assert "idx_normalized_jobs_first_seen" in index_names
    assert "idx_raw_jobs_content_hash" in index_names
    assert "idx_applications_status" in index_names
    assert "idx_applications_job_id" in index_names


def test_insert_and_get_raw_job(repo):
    payload = json.dumps({"title": "DV Engineer", "company": "SemiCorp"})
    content_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()

    raw_job = RawJob(
        source="manual",
        source_url="https://example.com/careers/dv-123",
        discovered_at="2026-10-04T10:00:00Z",
        raw_payload=payload,
        content_hash=content_hash,
    )

    raw_id = repo.insert_raw_job(raw_job)
    assert raw_id > 0

    fetched = repo.get_raw_job(raw_id)
    assert fetched is not None
    assert fetched.source == "manual"
    assert fetched.content_hash == content_hash
    assert fetched.source_url == "https://example.com/careers/dv-123"

    by_hash = repo.get_raw_job_by_hash(content_hash)
    assert by_hash is not None
    assert by_hash.id == raw_id


def test_insert_and_get_normalized_job(repo):
    normalized = NormalizedJob(
        company="SemiCorp",
        title="Design Verification Engineer",
        location="Bengaluru",
        country="India",
        employment_type="Full-time",
        experience_min=0.0,
        experience_max=1.0,
        graduation_year_min=2024,
        graduation_year_max=2025,
        description="Looking for entry level DV engineer with SystemVerilog and UVM knowledge.",
        requirements="B.Tech in ECE / VLSI",
        skills=["SystemVerilog", "UVM", "Verilog"],
        application_url="https://example.com/jobs/1",
        source="manual",
        status=JobStatus.ACTIVE,
        first_seen="2026-10-04T10:00:00Z",
        last_seen="2026-10-04T10:00:00Z",
        fingerprint="semicorp-dv-engineer-bengaluru-2025",
    )

    job_id = repo.insert_normalized_job(normalized)
    assert job_id > 0

    fetched = repo.get_normalized_job(job_id)
    assert fetched is not None
    assert fetched.company == "SemiCorp"
    assert fetched.title == "Design Verification Engineer"
    assert fetched.skills == ["SystemVerilog", "UVM", "Verilog"]
    assert fetched.fingerprint == "semicorp-dv-engineer-bengaluru-2025"

    by_fp = repo.get_normalized_job_by_fingerprint("semicorp-dv-engineer-bengaluru-2025")
    assert by_fp is not None
    assert by_fp.id == job_id


def test_fingerprint_uniqueness_and_duplicate_handling(repo):
    job1 = NormalizedJob(
        company="TechVLSI",
        title="RTL Design Intern",
        location="Hyderabad",
        country="India",
        source="manual",
        first_seen="2026-10-04T10:00:00Z",
        last_seen="2026-10-04T10:00:00Z",
        fingerprint="fp-techvlsi-rtl-intern-hyd",
    )
    repo.insert_normalized_job(job1)

    job2 = NormalizedJob(
        company="TechVLSI Duplicate",
        title="RTL Design Intern",
        location="Hyderabad",
        country="India",
        source="manual",
        first_seen="2026-10-04T11:00:00Z",
        last_seen="2026-10-04T11:00:00Z",
        fingerprint="fp-techvlsi-rtl-intern-hyd",
    )

    with pytest.raises(DuplicateFingerprintError) as excinfo:
        repo.insert_normalized_job(job2)
    assert "already exists" in str(excinfo.value)


def test_application_lifecycle_and_status(repo):
    job = NormalizedJob(
        company="SiliconDynamics",
        title="ASIC Verification Engineer",
        location="Bengaluru",
        country="India",
        source="manual",
        first_seen="2026-10-04T10:00:00Z",
        last_seen="2026-10-04T10:00:00Z",
        fingerprint="fp-sd-asic-dv-blr",
    )
    job_id = repo.insert_normalized_job(job)

    app_record = ApplicationRecord(
        job_id=job_id,
        status=ApplicationStatus.DISCOVERED,
        notes="Strong match for APB project",
        created_at="2026-10-04T10:00:00Z",
        updated_at="2026-10-04T10:00:00Z",
    )
    app_id = repo.create_application(app_record)
    assert app_id > 0

    fetched_app = repo.get_application(app_id)
    assert fetched_app is not None
    assert fetched_app.status == ApplicationStatus.DISCOVERED

    # Advance status through workflow
    repo.update_application_status(
        app_id=app_id,
        status=ApplicationStatus.SHORTLISTED,
        notes="Shortlisted by user for tailoring",
    )
    updated = repo.get_application(app_id)
    assert updated.status == ApplicationStatus.SHORTLISTED
    assert updated.notes == "Shortlisted by user for tailoring"

    repo.update_application_status(
        app_id=app_id,
        status=ApplicationStatus.APPLIED,
        applied_at="2026-10-04T12:00:00Z",
    )
    applied = repo.get_application(app_id)
    assert applied.status == ApplicationStatus.APPLIED
    assert applied.applied_at == "2026-10-04T12:00:00Z"

    # List applications by status
    applied_list = repo.list_applications(status=ApplicationStatus.APPLIED)
    assert len(applied_list) == 1
    assert applied_list[0].id == app_id

    shortlisted_list = repo.list_applications(status=ApplicationStatus.SHORTLISTED)
    assert len(shortlisted_list) == 0


def test_querying_jobs_with_filters(repo):
    job1 = NormalizedJob(
        company="AlphaSilicon",
        title="DV Engineer",
        location="Bengaluru",
        country="India",
        source="manual",
        first_seen="2026-10-04T08:00:00Z",
        last_seen="2026-10-04T08:00:00Z",
        fingerprint="fp-alpha-blr",
    )
    job2 = NormalizedJob(
        company="BetaVLSI",
        title="RTL Engineer",
        location="Noida",
        country="India",
        source="manual",
        first_seen="2026-10-04T09:00:00Z",
        last_seen="2026-10-04T09:00:00Z",
        fingerprint="fp-beta-noida",
    )
    repo.insert_normalized_job(job1)
    repo.insert_normalized_job(job2)

    assert repo.count_normalized_jobs() == 2

    blr_jobs = repo.list_normalized_jobs(location="Bengaluru")
    assert len(blr_jobs) == 1
    assert blr_jobs[0].company == "AlphaSilicon"

    beta_jobs = repo.list_normalized_jobs(company="BetaVLSI")
    assert len(beta_jobs) == 1
    assert beta_jobs[0].title == "RTL Engineer"


def test_database_persistence_across_reopen(tmp_path: Path):
    db_file = tmp_path / "test_persist.db"

    # Step 1: Open, initialize and insert data
    with DatabaseConnection(db_file) as conn:
        r = JobRepository(conn)
        job = NormalizedJob(
            company="PersistSemicon",
            title="Verification Intern",
            location="Chennai",
            country="India",
            source="manual",
            first_seen="2026-10-04T10:00:00Z",
            last_seen="2026-10-04T10:00:00Z",
            fingerprint="fp-persist-chennai",
        )
        r.insert_normalized_job(job)

    # Step 2: Reopen from disk file and verify data persists
    conn2 = get_connection(db_file)
    r2 = JobRepository(conn2)
    persisted_job = r2.get_normalized_job_by_fingerprint("fp-persist-chennai")
    assert persisted_job is not None
    assert persisted_job.company == "PersistSemicon"
    assert persisted_job.location == "Chennai"
    conn2.close()


def test_fresh_database_initialization_creates_normalized_jobs(tmp_path: Path):
    """Verify that a freshly created connection immediately has normalized_jobs table."""
    fresh_db = tmp_path / "fresh_test.db"
    assert not fresh_db.exists()

    conn = get_connection(fresh_db)
    cursor = conn.execute("SELECT count(*) FROM normalized_jobs;")
    count = cursor.fetchone()[0]
    assert count == 0
    conn.close()


def test_fresh_database_initialization_creates_every_required_current_table(tmp_path: Path):
    """Verify that a fresh database creates all 14 required tables across all subsystems."""
    fresh_db = tmp_path / "all_tables_test.db"
    conn = get_connection(fresh_db)

    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = {row[0] for row in cursor.fetchall()}

    required_tables = {
        "raw_jobs",
        "normalized_jobs",
        "applications",
        "application_events",
        "notifications",
        "interview_sessions",
        "interview_questions",
        "weak_areas",
        "preparation_sessions",
        "knowledge_items",
        "assessments",
        "preparation_schedules",
        "tailored_resumes",
        "proposed_schedule_notifications",
    }

    assert required_tables.issubset(tables), f"Missing tables: {required_tables - tables}"
    conn.close()


def test_reopening_initialized_database_does_not_destroy_data(tmp_path: Path):
    """Verify reopening database preserves records and auto-init is non-destructive."""
    db_file = tmp_path / "preserve_test.db"
    conn1 = get_connection(db_file)
    repo1 = JobRepository(conn1)

    job = NormalizedJob(
        company="NVIDIA India",
        title="Design Verification Engineer",
        location="Bengaluru",
        country="India",
        source="manual",
        first_seen="2026-10-04T10:00:00Z",
        last_seen="2026-10-04T10:00:00Z",
        fingerprint="fp-nvidia-blr-preserve",
    )
    job_id = repo1.insert_normalized_job(job)
    conn1.close()

    # Reopen multiple times
    for _ in range(3):
        conn_reopened = get_connection(db_file)
        repo_reopened = JobRepository(conn_reopened)
        fetched = repo_reopened.get_normalized_job(job_id)
        assert fetched is not None
        assert fetched.company == "NVIDIA India"
        assert fetched.fingerprint == "fp-nvidia-blr-preserve"
        conn_reopened.close()


def test_schema_initialization_is_idempotent_when_called_multiple_times(memory_db):
    """Verify calling create_schema multiple times causes no errors or duplicate table issues."""
    from app.db.schema import create_schema

    create_schema(memory_db)
    create_schema(memory_db)
    create_schema(memory_db)

    # Database still operational
    cursor = memory_db.execute("SELECT count(*) FROM normalized_jobs;")
    assert cursor.fetchone()[0] == 0
