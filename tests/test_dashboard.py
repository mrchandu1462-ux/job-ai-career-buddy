"""Unit tests for Streamlit dashboard backend initialization and service bindings."""

from app.dashboard import get_system_context


def test_dashboard_system_context_initialization():
    ctx = get_system_context()

    assert "conn" in ctx
    assert "profile" in ctx
    assert "facts" in ctx
    assert "job_repo" in ctx
    assert "career_repo" in ctx
    assert "resume_repo" in ctx
    assert "app_service" in ctx
    assert "discovery_pipeline" in ctx
    assert "career_pipeline" in ctx
    assert "bank_service" in ctx
    assert "learning_service" in ctx
    assert "sim_engine" in ctx
    assert "analytics_service" in ctx
    assert "notification_service" in ctx
    assert "docx_exporter" in ctx
    assert "pdf_exporter" in ctx
    assert "export_validator" in ctx

    # Verify candidate facts ground truth count
    assert len(ctx["facts"].facts) > 0
    assert ctx["profile"].candidate.graduation_year == 2025


def test_dashboard_queries_normalized_jobs_without_operational_error():
    """Verify that all queries executed on dashboard startup run cleanly without OperationalError."""
    ctx = get_system_context()

    # Exact queries executed at start of dashboard.py
    summary = ctx["analytics_service"].get_summary_metrics()
    assert isinstance(summary, dict)

    jobs = ctx["job_repo"].list_normalized_jobs()
    assert isinstance(jobs, list)

    apps = ctx["job_repo"].list_applications()
    assert isinstance(apps, list)

    weaks = ctx["career_repo"].list_weak_areas()
    assert isinstance(weaks, list)

    proposals = ctx["notification_service"].list_proposals()
    assert isinstance(proposals, list)

    resumes = ctx["resume_repo"].list_tailored_resumes()
    assert isinstance(resumes, list)

