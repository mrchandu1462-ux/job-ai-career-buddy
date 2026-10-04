"""Streamlit interactive dashboard for the Job AI Career Operating System.

Provides a unified personal AI Career Buddy interface connecting discovery, matching,
fact-grounded ATS resume generation, export validation, historical question banks,
structured learning mode, turn-by-turn interview simulation, pre-interview final assessments,
readiness gates, preparation schedules, human approval gates, and career analytics.
"""

from datetime import UTC, datetime
from pathlib import Path

import streamlit as st

from app.application.service import ApplicationPipelineService
from app.career.analytics import CareerAnalyticsService
from app.career.bank import QuestionBankService
from app.career.learning import CURATED_TOPIC_SUBTOPICS, LearningModeService
from app.career.notifications import (
    NotificationDispatchStatus,
    ScheduleNotificationService,
)
from app.career.pipeline import (
    HistoricalInterviewPipeline,
    InterviewOutcomeDebrief,
    InterviewQuestionOutcome,
)
from app.career.repository import CareerRepository
from app.career.simulation import InterviewSimulationEngine, SimulationStage
from app.db.connection import get_connection
from app.db.models import (
    ApplicationStatus,
    NotificationType,
)
from app.db.repository import JobRepository
from app.jobs.models import FreshnessStatus
from app.jobs.monitoring_service import FreshJobMonitoringService
from app.jobs.pipeline import JobDiscoveryPipeline
from app.jobs.sources.base import JobDiscoveryQuery
from app.profile.loader import load_fact_bank, load_profile
from app.resume.export.docx import DOCXResumeExporter
from app.resume.export.pdf import PDFResumeExporter
from app.resume.export.validation import ResumeExportValidator
from app.resume.repository import ResumeRepository

# Page Configuration
st.set_page_config(
    page_title="Job AI — VLSI Career Operating System",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_resource
def get_system_context():
    """Initialize database connection, candidate profile, and all backend services."""
    conn = get_connection()
    profile = load_profile()
    facts = load_fact_bank()

    job_repo = JobRepository(conn)
    career_repo = CareerRepository(conn)
    resume_repo = ResumeRepository(conn)

    app_service = ApplicationPipelineService(
        conn=conn, profile=profile, fact_bank=facts, artifacts_dir="artifacts/resumes"
    )
    discovery_pipeline = JobDiscoveryPipeline(conn=conn, profile=profile, fact_bank=facts)
    monitor_service = FreshJobMonitoringService(
        conn=conn,
        profile=profile,
        fact_bank=facts,
        job_repo=job_repo,
    )
    career_pipeline = HistoricalInterviewPipeline(conn)
    bank_service = QuestionBankService(conn, career_repo)
    learning_service = LearningModeService(career_repo)
    sim_engine = InterviewSimulationEngine(career_repo)
    analytics_service = CareerAnalyticsService(conn, job_repo, career_repo, resume_repo)
    notification_service = ScheduleNotificationService(conn)
    docx_exporter = DOCXResumeExporter(output_dir="artifacts/resumes")
    pdf_exporter = PDFResumeExporter(output_dir="artifacts/resumes")
    export_validator = ResumeExportValidator()

    return {
        "conn": conn,
        "profile": profile,
        "facts": facts,
        "job_repo": job_repo,
        "career_repo": career_repo,
        "resume_repo": resume_repo,
        "app_service": app_service,
        "discovery_pipeline": discovery_pipeline,
        "monitor_service": monitor_service,
        "career_pipeline": career_pipeline,
        "bank_service": bank_service,
        "learning_service": learning_service,
        "sim_engine": sim_engine,
        "analytics_service": analytics_service,
        "notification_service": notification_service,
        "docx_exporter": docx_exporter,
        "pdf_exporter": pdf_exporter,
        "export_validator": export_validator,
    }


def main():
    ctx = get_system_context()
    profile = ctx["profile"]
    facts = ctx["facts"]
    job_repo: JobRepository = ctx["job_repo"]
    career_repo: CareerRepository = ctx["career_repo"]
    resume_repo: ResumeRepository = ctx["resume_repo"]
    app_service: ApplicationPipelineService = ctx["app_service"]
    discovery_pipeline: JobDiscoveryPipeline = ctx["discovery_pipeline"]
    monitor_service: FreshJobMonitoringService = ctx["monitor_service"]
    career_pipeline: HistoricalInterviewPipeline = ctx["career_pipeline"]
    bank_service: QuestionBankService = ctx["bank_service"]
    learning_service: LearningModeService = ctx["learning_service"]
    sim_engine: InterviewSimulationEngine = ctx["sim_engine"]
    analytics_service: CareerAnalyticsService = ctx["analytics_service"]
    notification_service: ScheduleNotificationService = ctx["notification_service"]
    docx_exporter: DOCXResumeExporter = ctx["docx_exporter"]
    pdf_exporter: PDFResumeExporter = ctx["pdf_exporter"]
    export_validator: ResumeExportValidator = ctx["export_validator"]

    # Sidebar Header & Profile Summary
    st.sidebar.title("⚡ Job AI Career Buddy")
    st.sidebar.caption(
        f"**Candidate:** {profile.candidate.graduation_year} VLSI Fresher\n\n"
        f"**Target Roles:** {', '.join(profile.candidate.target_roles[:2])}\n\n"
        f"**Priority Hubs:** {', '.join(profile.candidate.locations.india_priority[:3])}\n\n"
        f"**Verified Fact Items:** {len(facts.facts)} Ground Truth"
    )
    st.sidebar.divider()

    nav = st.sidebar.radio(
        "Navigation",
        [
            "📊 1. Dashboard",
            "🔥 2. Fresh Jobs",
            "📝 3. Applications",
            "📄 4. Resumes",
            "🧠 5. Interview Preparation",
            "📚 6. Question Bank",
            "🎯 7. Final Assessment",
            "🛡️ 8. Readiness",
            "📅 9. Schedule",
            "✉️ 10. Email & Notifications",
            "📈 11. Career Analytics",
            "⚙️ 12. Settings",
        ],
    )

    # -------------------------------------------------------------------------
    # 1. DASHBOARD
    # -------------------------------------------------------------------------
    if nav == "📊 1. Dashboard":
        st.header("📊 Career Operating System — Personal AI Career Buddy")

        summary = analytics_service.get_summary_metrics()
        monitor_summary = monitor_service.get_last_monitoring_run_summary()
        all_jobs = job_repo.list_normalized_jobs()
        all_apps = job_repo.list_applications()
        weaks = career_repo.list_weak_areas(resolved=False)
        proposals = notification_service.list_proposals(status=NotificationDispatchStatus.PROPOSED)

        # Top Metrics Grid
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Jobs Found", summary.get("total_discovered_jobs", 0))
        c2.metric("Fresh (<24h)", monitor_summary.get("fresh_jobs_count", 0))
        c3.metric("P0/P1 Alerts", monitor_summary.get("p0_opportunities", 0) + monitor_summary.get("p1_opportunities", 0))
        c4.metric("Applied", summary.get("applications_applied", 0))
        c5.metric("Unresolved Weaks", summary.get("unresolved_weak_areas_count", 0))

        # Career Readiness & Weak Areas Banner
        st.divider()
        col_banner1, col_banner2 = st.columns([1, 1])

        with col_banner1:
            st.subheader("🎯 Current DV Interview Readiness")
            if all_jobs:
                first_job = all_jobs[0]
                if first_job.id is not None:
                    readiness = career_pipeline.calculate_readiness(first_job.id)
                    st.metric(
                        label=f"Readiness ({first_job.company} — {first_job.title})",
                        value=f"{int(readiness.overall_readiness_score)}%",
                        delta=readiness.readiness_level,
                    )
                    st.write(f"**Recommended Action:** {readiness.recommended_action}")
            else:
                st.info("Ingest or discover jobs to calculate job-specific readiness.")

            st.subheader("⚠️ Critical Weak Areas")
            if weaks:
                for w in weaks[:4]:
                    st.markdown(f"- 🔴 **{w.topic}** (Confidence: {int(w.confidence * 100)}%, Severity: `{w.severity.upper()}`): {w.description[:90]}...")
            else:
                st.success("No active weak areas tracked! Keep practicing.")

        with col_banner2:
            st.subheader("🔔 Pending Human Actions")
            pending_items = []
            ready_apps = [a for a in all_apps if a.status == ApplicationStatus.READY_FOR_REVIEW]
            for a in ready_apps:
                j = job_repo.get_normalized_job(a.job_id)
                comp = j.company if j else f"Job #{a.job_id}"
                pending_items.append(f"Review tailored resume & package for **{comp}** (App #{a.id})")

            for p in proposals[:3]:
                pending_items.append(f"Approve scheduling proposal: *{p.subject}* ({p.target_company})")

            if pending_items:
                for item in pending_items:
                    st.markdown(f"- ⏳ {item}")
            else:
                st.caption("No urgent actions pending approval.")

        # Top India Tech Hub Opportunities
        st.subheader("🌟 Priority India Tech Hub Listings")
        disc_summary = discovery_pipeline.get_dashboard_summary()
        if disc_summary.get("top_india_opportunities"):
            st.dataframe(disc_summary["top_india_opportunities"], use_container_width=True)
        else:
            st.info("No India opportunities currently displayed. Explore the Fresh Jobs section.")

    # -------------------------------------------------------------------------
    # 2. FRESH JOBS & DISCOVERY
    # -------------------------------------------------------------------------
    elif "2. Fresh Jobs" in nav or "2. Jobs" in nav:
        st.header("🔥 Fresh Job Monitoring & Alert Engine (India + Overseas)")

        # Last Monitoring Run Summary Bar
        run_summary = monitor_service.get_last_monitoring_run_summary()
        all_jobs = job_repo.list_normalized_jobs()

        # Count Freshness Categories
        count_0_6h = sum(1 for j in all_jobs if getattr(j, "freshness_status", None) == FreshnessStatus.FRESH_0_6_HOURS)
        count_6_24h = sum(1 for j in all_jobs if getattr(j, "freshness_status", None) == FreshnessStatus.FRESH_6_24_HOURS)
        count_india = sum(1 for j in all_jobs if (getattr(j, "country", None) or "India").lower() == "india")
        count_overseas = len(all_jobs) - count_india
        count_p0 = run_summary.get("p0_opportunities", 0)
        count_p1 = run_summary.get("p1_opportunities", 0)

        # KPI Metrics Row
        kpi1, kpi2, kpi3, kpi4, kpi5, kpi6 = st.columns(6)
        kpi1.metric("⚡ Fresh <6h", count_0_6h)
        kpi2.metric("🕒 Fresh 6-24h", count_6_24h)
        kpi3.metric("🇮🇳 India Hubs", count_india)
        kpi4.metric("🌐 Overseas", count_overseas)
        kpi5.metric("🔥 P0 Alerts", count_p0)
        kpi6.metric("✨ P1 Alerts", count_p1)

        st.divider()

        # Monitoring Execution Controls & Trigger
        with st.expander("⚡ Run Fresh Job Monitor On-Demand", expanded=False):
            col_m1, col_m2, col_m3, col_m4 = st.columns([2, 1, 1, 2])
            with col_m1:
                sel_region = st.selectbox("Target Region", ["all", "india", "overseas"], index=0)
            with col_m2:
                sel_fresh_only = st.checkbox("Fresh <=24h Only", value=False)
            with col_m3:
                sel_dry_run = st.checkbox("Dry Run (No Save)", value=False)
            with col_m4:
                st.write("")
                if st.button("🚀 Run Monitoring Cycle Now", type="primary"):
                    with st.spinner("Executing fresh job monitoring cycle across adapters..."):
                        cycle_report = monitor_service.run_monitoring_cycle(
                            region=sel_region,
                            fresh_only=sel_fresh_only,
                            dry_run=sel_dry_run,
                            limit=20,
                        )
                        st.success(
                            f"Cycle complete! Checked {cycle_report.sources_checked} sources, found {cycle_report.total_jobs_found} raw jobs, "
                            f"{cycle_report.unique_jobs_ingested} unique canonical, {cycle_report.fresh_24h_jobs_count} fresh (<24h), "
                            f"and proposed {cycle_report.notifications_generated} human-gated alerts."
                        )
                        st.rerun()

            st.caption(
                f"**Last Run:** `{run_summary.get('last_run_timestamp')}` | "
                f"**Sources Monitored:** {run_summary.get('sources_monitored')} | "
                f"**Source Failures:** {run_summary.get('source_failures')} (Isolated safely)"
            )

        # Ingest Manual Listing Expander
        with (
            st.expander("➕ Ingest a New Job Listing (Manual or Paste JD)", expanded=False),
            st.form("job_ingestion_form"),
        ):
            col_c, col_t = st.columns(2)
            in_company = col_c.text_input("Company Name", value="Qualcomm India")
            in_title = col_t.text_input("Job Title", value="Design Verification Engineer")
            col_l, col_u = st.columns(2)
            in_location = col_l.text_input("Location", value="Bengaluru")
            in_url = col_u.text_input("Application URL", value="https://qualcomm.wd5.myworkdayjobs.com/careers/dv-2025")
            in_jd = st.text_area(
                "Job Description Text",
                value="Seeking a 2025 batch fresher for Design Verification Engineer in Bengaluru. Experience in SystemVerilog, UVM, SVA assertions, AXI4/APB bus protocols, and asynchronous FIFO CDC verification.",
                height=100,
            )
            submitted = st.form_submit_button("Ingest and Score Job")
            if submitted and in_company and in_title and in_jd:
                discovery_pipeline.manual_source.submit_manual_job(
                    company=in_company,
                    title=in_title,
                    raw_text=in_jd,
                    location=in_location,
                    application_url=in_url,
                )
                report = discovery_pipeline.discover_and_ingest(JobDiscoveryQuery(keywords=[in_title], limit=5))
                st.success(f"Job ingested! Assigned ID: {report[0].normalized_job_id if report else 'Done'}")
                st.rerun()

        # Multi-Filters
        st.subheader("🎯 Filter & Browse Opportunities")
        f_col1, f_col2, f_col3, f_col4 = st.columns(4)
        with f_col1:
            filter_geo = st.selectbox("Geography", ["All", "India", "Overseas"], index=0)
        with f_col2:
            filter_fresh = st.selectbox("Freshness", ["All", "<6h (Ultra-Fresh)", "<24h (Fresh)", "1-3 Days", "Older", "Unknown"], index=0)
        with f_col3:
            filter_match = st.selectbox("7D Match Score", ["All", "80%+ (Strong Match)", "70%+", "60%+"], index=0)
        with f_col4:
            filter_role = st.selectbox("Role Focus", ["All", "Design Verification", "RTL Design", "Validation"], index=0)

        if not all_jobs:
            st.info("No job listings found in database. Run a monitoring cycle above or ingest a job.")
        else:
            ranked_matches = discovery_pipeline.evaluate_and_rank_all_jobs(eligible_only=False)

            # Apply Filters
            filtered_ranked = []
            for r in ranked_matches:
                nj = job_repo.get_normalized_job(r.job_id)
                if not nj:
                    continue

                # Geo Filter
                is_india = (nj.country or "India").lower() == "india"
                if filter_geo == "India" and not is_india:
                    continue
                if filter_geo == "Overseas" and is_india:
                    continue

                # Freshness Filter
                f_status = getattr(nj, "freshness_status", None)
                if filter_fresh == "<6h (Ultra-Fresh)" and f_status != FreshnessStatus.FRESH_0_6_HOURS:
                    continue
                if filter_fresh == "<24h (Fresh)" and f_status not in (FreshnessStatus.FRESH_0_6_HOURS, FreshnessStatus.FRESH_6_24_HOURS):
                    continue
                if filter_fresh == "1-3 Days" and f_status != FreshnessStatus.RECENT_1_3_DAYS:
                    continue

                # Match Score Filter
                if filter_match == "80%+ (Strong Match)" and r.match_score < 80.0:
                    continue
                if filter_match == "70%+" and r.match_score < 70.0:
                    continue
                if filter_match == "60%+" and r.match_score < 60.0:
                    continue

                # Role Filter
                if filter_role != "All":
                    target_kw = filter_role.lower()
                    if target_kw not in (nj.title or "").lower() and target_kw not in (nj.role_category or "").lower():
                        continue

                filtered_ranked.append((r, nj))

            if not filtered_ranked:
                st.warning("No opportunities match the selected filter criteria. Try adjusting the filters above.")
            else:
                st.write(f"Displaying **{len(filtered_ranked)}** matched opportunity(s):")
                job_choices = {
                    f"{nj.company} — {nj.title} ({nj.location or 'India'}) [{getattr(nj, 'freshness_status', 'unknown')}] [Match: {int(r.match_score)}/100]": r.job_id
                    for r, nj in filtered_ranked
                }
                selected_choice = st.selectbox("Select Opportunity to Inspect & Action:", list(job_choices.keys()))
                selected_job_id = job_choices[selected_choice]

                selected_pair = next(item for item in filtered_ranked if item[0].job_id == selected_job_id)
                selected_match, norm_job = selected_pair[0], selected_pair[1]
                app_rec = job_repo.get_application_by_job_id(selected_job_id)

                # Priority and Freshness Badges
                f_stat = getattr(norm_job, "freshness_status", "unknown")
                f_age = getattr(norm_job, "freshness_age_hours", None)
                fresh_badge = f"{f_age:.1f}h ago" if f_age is not None else str(f_stat)

                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Company & Role", f"{norm_job.company}", norm_job.title)
                c2.metric("7D Match Score", f"{int(selected_match.match_score)}/100")
                c3.metric("Freshness Status", f"{f_stat.upper()}", fresh_badge)
                c4.metric("Application Status", app_rec.status.value.upper() if app_rec else "DISCOVERED")

                geo_loc = f"{norm_job.location or 'Not specified'}, {norm_job.country or 'India'}"
                st.write(f"📍 **Location:** {geo_loc} | 🏢 **Workplace:** `{getattr(norm_job, 'workplace_type', 'unknown')}` | 🛡️ **Visa Sponsorship:** `{getattr(norm_job, 'visa_sponsorship', 'unknown')}`")
                st.write(f"🔗 **Discovered From Source(s):** `{', '.join(getattr(norm_job, 'source_references', []) or [norm_job.source])}`")
                if norm_job.application_url:
                    st.markdown(f"**Official Job Application Portal:** [{norm_job.application_url}]({norm_job.application_url})")

                # Match Details
                col_sk1, col_sk2, col_sk3 = st.columns(3)
                with col_sk1:
                    st.markdown("**Required Skills from JD:**")
                    for s in norm_job.skills:
                        st.markdown(f"- 📌 {s}")
                with col_sk2:
                    st.markdown("**Candidate Matching Skills:**")
                    for s in selected_match.score_breakdown.matching_skills:
                        st.markdown(f"- ✅ {s}")
                with col_sk3:
                    st.markdown("**Missing Skills / Gaps:**")
                    if selected_match.score_breakdown.missing_skills:
                        for s in selected_match.score_breakdown.missing_skills:
                            st.markdown(f"- ⚠️ {s}")
                    else:
                        st.caption("No significant skill gaps identified.")

                # Truthful Adjacent Evidence
                st.subheader("🔗 Truthful Adjacent Evidence Mapping")
                st.info(
                    "When exact JD keywords are not directly in candidate profile, Job AI identifies truthful adjacent verified evidence without fabricating skills:\n"
                    "- AXI / Bus Protocols → AXI4 UVC Verification IP & QuestaSim\n"
                    "- CDC / Clock Domain Crossing → Dual-clock Asynchronous FIFO with 2-FF Gray synchronizers\n"
                    "- Formal / Assertions → SystemVerilog SVA concurrent properties and coverage"
                )

                # Actions
                st.divider()
                st.subheader("⚡ Available Job Actions")
                col_act1, col_act2, col_act3, col_act4 = st.columns(4)

                with col_act1:
                    if st.button("📌 Shortlist Job", key=f"short_{selected_job_id}"):
                        app_service.shortlist_job(selected_job_id, notes="Shortlisted from Fresh Jobs view.")
                        st.success("Job marked as SHORTLISTED!")
                        st.rerun()

                with col_act2:
                    if st.button("🚀 Prepare Application Package", key=f"prep_{selected_job_id}"):
                        pkg = app_service.prepare_application(selected_job_id)
                        st.success(f"Application Package prepared! Status: `{pkg.status.value}`. Tailored Resume ATS Score: `{pkg.tailored_resume.ats_score}/100`.")
                        st.rerun()

                with col_act3:
                    if st.button("👁️ View Full JD Text", key=f"view_jd_{selected_job_id}"):
                        st.text_area("Job Description", value=norm_job.description or "No text available.", height=150, disabled=True)

                with col_act4:
                    if st.button("🚫 Ignore Job", key=f"ign_{selected_job_id}") and app_rec and app_rec.id is not None:
                        app_service.review_application(app_rec.id, decision="REJECT", notes="Candidate ignored opportunity.")
                        st.warning("Job marked as REJECTED.")
                        st.rerun()

    # -------------------------------------------------------------------------
    # 3. APPLICATIONS
    # -------------------------------------------------------------------------
    elif nav == "📝 3. Applications":
        st.header("📝 Application Tracking & Mandatory Human Approval Gates")
        all_apps = job_repo.list_applications()

        st.info(
            "🛡️ **Master Human Safety Rule:**\n"
            "- Preparing an application NEVER applies.\n"
            "- Tailoring a resume NEVER applies.\n"
            "- Approving a package NEVER applies.\n"
            "- Status becomes `APPLIED` ONLY upon explicit manual confirmation with a portal reference ID and confirmation evidence."
        )

        if not all_apps:
            st.info("No applications initialized yet.")
        else:
            status_filter = st.selectbox(
                "Filter Applications by Status:",
                ["ALL"] + [s.value for s in ApplicationStatus],
            )
            filtered = all_apps if status_filter == "ALL" else [a for a in all_apps if a.status.value == status_filter]
            st.write(f"Displaying **{len(filtered)}** application record(s):")

            for app in filtered:
                job = job_repo.get_normalized_job(app.job_id)
                comp = job.company if job else "Company"
                role = job.title if job else "Role"
                loc = job.location if job else "Location"

                with st.expander(f"🏢 {comp} — {role} [{app.status.value.upper()}] (App #{app.id})", expanded=(app.status == ApplicationStatus.READY_FOR_REVIEW)):
                    st.write(f"**Location:** {loc} | **Created:** {app.created_at[:19].replace('T', ' ')} | **Updated:** {app.updated_at[:19].replace('T', ' ')}")
                    st.write(f"**Current Status:** `{app.status.value.upper()}`")
                    st.write(f"**Notes:** {app.notes or 'None'}")
                    if app.tailored_resume_path:
                        st.write(f"**Tailored Resume:** `{app.tailored_resume_path}`")
                    if job and job.application_url:
                        st.markdown(f"**Official Portal:** [{job.application_url}]({job.application_url})")

                    # Review Gates
                    if app.status in [ApplicationStatus.READY_FOR_REVIEW, ApplicationStatus.DISCOVERED, ApplicationStatus.SHORTLISTED, ApplicationStatus.PREPARING]:
                        st.subheader("Human Approval Actions")
                        col_ap, col_ed, col_rj = st.columns(3)
                        with col_ap:
                            if st.button("✅ Approve Package", key=f"app_approve_{app.id}") and app.id is not None:
                                app_service.review_application(app.id, decision="APPROVE", notes="Candidate approved tailored package.")
                                st.success("Application approved! Candidate can now submit on company portal.")
                                st.rerun()
                        with col_ed:
                            edit_note = st.text_input("Revision notes:", key=f"app_edit_note_{app.id}", placeholder="Specific revisions...")
                            if st.button("✏️ Request Edits", key=f"app_edit_{app.id}") and app.id is not None:
                                app_service.review_application(app.id, decision="EDIT", notes=edit_note)
                                st.warning("Returned to PREPARING status.")
                                st.rerun()
                        with col_rj:
                            if st.button("❌ Reject Opportunity", key=f"app_reject_{app.id}") and app.id is not None:
                                app_service.review_application(app.id, decision="REJECT", notes="Candidate declined role.")
                                st.error("Marked as REJECTED.")
                                st.rerun()

                    # Confirmed Submission Box
                    if app.status == ApplicationStatus.APPROVED:
                        st.subheader("📤 Record Manual Application Submission")
                        with st.form(key=f"manual_submit_form_{app.id}"):
                            ref_id = st.text_input("Portal Confirmation / Reference ID:", placeholder="e.g., REQ-2025-9812")
                            evidence_text = st.text_area("Confirmation Proof / Notes:", placeholder="Paste portal email confirmation or receipt text...")
                            submitted_btn = st.form_submit_button("Confirm Manual Submission (Set Status to APPLIED)")
                            if submitted_btn and app.id is not None:
                                app_service.record_submission(
                                    application_id=app.id,
                                    reference_id=ref_id,
                                    submission_evidence=evidence_text,
                                    notes="Candidate manually submitted on career portal.",
                                )
                                st.success("Submission successfully recorded! Status is now APPLIED.")
                                st.rerun()

                    # Failure Recording Box
                    if app.status in [ApplicationStatus.APPROVED, ApplicationStatus.PREPARING]:
                        with (
                            st.expander("⚠️ Record Submission Failure (Audit Failure Reason)"),
                            st.form(key=f"fail_form_{app.id}"),
                        ):
                            f_stage = st.selectbox("Failure Stage:", ["portal_upload", "workday_authentication", "eligibility_rejected", "expired_link"], key=f"stage_{app.id}")
                            f_reason = st.text_area("Failure Reason & Description:", placeholder="e.g., Job posting expired during submission", key=f"reason_{app.id}")
                            fail_btn = st.form_submit_button("Record Submission Failure")
                            if fail_btn and f_reason and app.id is not None:
                                app_service.record_submission_failure(
                                    application_id=app.id,
                                    failure_reason=f_reason,
                                    failure_stage=f_stage,
                                )
                                st.error("Submission failure audited. Status marked FAILED.")
                                st.rerun()

                    if app.status == ApplicationStatus.APPLIED:
                        st.success(f"🎉 **CONFIRMED APPLIED** at `{app.applied_at or app.updated_at}`")

                    # Chronological Audit Trail
                    st.caption("Chronological Audit Events:")
                    if app.id is not None:
                        events = job_repo.get_application_events(app.id)
                        for ev in events:
                            st.markdown(f"- `{ev.timestamp[:19].replace('T', ' ')}` — **{ev.event_type.value}** ({ev.application_status.value}): {ev.notes or ''}")

    # -------------------------------------------------------------------------
    # 4. RESUMES
    # -------------------------------------------------------------------------
    elif nav == "📄 4. Resumes":
        st.header("📄 Fact-Grounded ATS Resumes, Integrity Gates & Export Validation")
        all_resumes = resume_repo.list_tailored_resumes()
        all_jobs = job_repo.list_normalized_jobs()
        with st.expander("⚡ Generate Tailored Resume for Job", expanded=(len(all_resumes) == 0)):
            if all_jobs:
                job_tailor_choice = st.selectbox(
                    "Select Target Job:",
                    [f"{j.company} — {j.title} (ID: {j.id})" for j in all_jobs],
                    key="tailor_resume_job_sel",
                )
                target_tailor_jid = int(job_tailor_choice.split("ID: ")[1].replace(")", ""))
                if st.button("Generate Fact-Grounded Tailored Resume", key="btn_gen_tailor"):
                    app_pkg = app_service.prepare_application(target_tailor_jid)
                    st.success(f"Tailored resume generated for {job_tailor_choice}! ATS Score: {int(app_pkg.tailored_resume.ats_score)}/100")
                    st.rerun()
            else:
                st.info("No jobs available. Ingest a job in the Jobs tab first.")

        if not all_resumes:
            st.info("No tailored resumes generated yet. Select a job above or in the Jobs tab and generate a tailored resume.")
        else:
            resume_options = {
                f"{r.resume_id} — {r.target_company} ({r.target_role}) [ATS: {int(r.ats_score)}/100 | Integrity: {r.fact_integrity_status}]": r.resume_id
                for r in all_resumes
            }
            selected_res_id = st.selectbox("Select Tailored Resume Version:", list(resume_options.keys()))
            resume = resume_repo.get_tailored_resume(resume_options[selected_res_id])

            if resume:
                c1, c2, c3 = st.columns(3)
                c1.metric("ATS Score", f"{int(resume.ats_score)}/100")
                c2.metric("ATS Quality Gate (>=80)", "PASS" if resume.ats_score >= 80.0 else "TARGET NOT REACHED")
                c3.metric("Fact Integrity Status", resume.fact_integrity_status)

                if resume.ats_score < 80.0:
                    st.error("🚨 **ATS TARGET NOT REACHED** (< 80/100)")
                    st.markdown(
                        "**Reason Score Cannot Reach 80 Truthfully:** Candidate's verified Fact Bank does not contain direct evidence for "
                        "some required job skills. Per the Master Safety Rules, Job AI will **never** fabricate skills, metrics, or experience."
                    )

                # ATS Breakdown
                ats = resume.ats_breakdown
                st.subheader("📊 ATS Scoring Dimension Breakdown")
                col_a1, col_a2, col_a3, col_a4, col_a5 = st.columns(5)
                col_a1.metric("Technical Keywords (30%)", f"{int(ats.technical_keyword_score)}/100")
                col_a2.metric("Skills Coverage (30%)", f"{int(ats.required_skills_coverage)}/100")
                col_a3.metric("Project Relevance (20%)", f"{int(ats.project_relevance_score)}/100")
                col_a4.metric("Role Alignment (10%)", f"{int(ats.role_alignment_score)}/100")
                col_a5.metric("Parser Safety (10%)", f"{int(ats.parser_safety_score)}/100")

                # Supported vs Missing vs Adjacent
                with st.expander("🔍 Fact Integrity & Requirement Alignment", expanded=True):
                    col_req1, col_req2, col_req3 = st.columns(3)
                    with col_req1:
                        st.markdown("**Supported Requirements:**")
                        for s in ats.matching_skills:
                            st.markdown(f"- ✅ {s}")
                    with col_req2:
                        st.markdown("**Missing / Unsupported Requirements:**")
                        if ats.unsupported_requirements:
                            for u in ats.unsupported_requirements:
                                st.markdown(f"- ⚠️ {u}")
                        else:
                            st.caption("Zero unsupported requirements.")
                    with col_req3:
                        st.markdown("**Truthful Adjacent Evidence:**")
                        if ats.adjacent_evidence_found:
                            for k, v in ats.adjacent_evidence_found.items():
                                st.markdown(f"- 🔗 **{k}**: {v}")
                        else:
                            st.caption("Standard direct mapping.")

                # Document Export & Validation
                st.subheader("📤 ATS-Safe Document Export & Post-Export Validation")
                col_exp1, col_exp2 = st.columns(2)

                docx_filename = f"{resume.resume_id}.docx"
                pdf_filename = f"{resume.resume_id}.pdf"

                # Generate and validate DOCX
                docx_path = docx_exporter.export(resume, filename=docx_filename)
                docx_val = export_validator.validate_export(docx_path, resume)

                # Generate and validate PDF
                pdf_path = pdf_exporter.export(resume, filename=pdf_filename)
                pdf_val = export_validator.validate_export(pdf_path, resume)

                with col_exp1:
                    st.markdown(f"**DOCX Format:** `{'PASS' if docx_val.is_export_validated else 'FAIL'}`")
                    st.caption(f"Extracted length: {docx_val.extracted_text_length} chars | Sections: {', '.join(docx_val.sections_detected)}")
                    if docx_val.is_export_validated and Path(docx_path).exists():
                        with open(docx_path, "rb") as f:
                            st.download_button(
                                label="⬇️ Download Validated DOCX",
                                data=f.read(),
                                file_name=docx_filename,
                                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                key=f"dl_docx_{resume.resume_id}",
                            )

                with col_exp2:
                    st.markdown(f"**PDF Format:** `{'PASS' if pdf_val.is_export_validated else 'FAIL'}`")
                    st.caption(f"Extracted length: {pdf_val.extracted_text_length} chars | Sections: {', '.join(pdf_val.sections_detected)}")
                    if pdf_val.is_export_validated and Path(pdf_path).exists():
                        with open(pdf_path, "rb") as f:
                            st.download_button(
                                label="⬇️ Download Validated PDF",
                                data=f.read(),
                                file_name=pdf_filename,
                                mime="application/pdf",
                                key=f"dl_pdf_{resume.resume_id}",
                            )

                # Render Views
                tab_text, tab_md, tab_facts = st.tabs(["Plaintext / Parser-Safe View", "Markdown View", "Fact Bank Provenance"])
                with tab_text:
                    st.code(resume.plain_text_content or "No plaintext generated.", language="text")
                with tab_md:
                    st.markdown(resume.markdown_content or "No markdown generated.")
                with tab_facts:
                    st.write("**Supporting Verified Fact IDs:**")
                    st.write(resume.source_fact_ids)

    # -------------------------------------------------------------------------
    # 5. INTERVIEW PREPARATION
    # -------------------------------------------------------------------------
    elif nav == "🧠 5. Interview Preparation":
        st.header("🧠 Pre-Interview Review Pack, Structured Learning & Interview Simulation")

        tab_review, tab_learn, tab_sim, tab_debrief = st.tabs([
            "📚 Complete 8-Category Review Pack",
            "📖 Structured Learning Mode",
            "🎙️ Multi-Stage Interview Simulator",
            "🔄 Real Interview Debrief & Learning Loop",
        ])

        all_jobs = job_repo.list_normalized_jobs()

        with tab_review:
            st.subheader("Complete Pre-Interview Review Pack (Go Through ALL Questions)")
            if not all_jobs:
                st.info("Ingest a job to generate a company/role review pack.")
            else:
                target_j_label = st.selectbox(
                    "Target Job for Review Pack:",
                    [f"{j.company} — {j.title} (Job #{j.id})" for j in all_jobs],
                    key="rev_pack_job_sel",
                )
                target_jid = int(target_j_label.split("Job #")[1].replace(")", ""))
                pool = bank_service.build_pre_interview_review_pool(target_jid)

                st.write(f"Total Unique Questions in Review Pool: **{pool.total_unique_questions}**")

                categories = [
                    ("Must Know", pool.must_know),
                    ("Frequently Asked", pool.frequently_asked),
                    ("Previously Missed", pool.previously_missed),
                    ("Job-Specific", pool.job_specific),
                    ("Company-Specific", pool.company_specific),
                    ("Weak Areas", pool.weak_areas),
                    ("Fundamentals", pool.fundamentals),
                    ("Advanced / Bonus", pool.advanced_bonus),
                ]

                for cat_name, q_list in categories:
                    with st.expander(f"📌 Category: {cat_name} ({len(q_list)} questions)", expanded=(len(q_list) > 0 and cat_name in ["Must Know", "Weak Areas"])):
                        if not q_list:
                            st.caption("No questions in this category.")
                        else:
                            for idx, q in enumerate(q_list):
                                q_label = "VERIFIED HISTORICAL" if q.verified else "GENERATED / PRACTICE"
                                st.markdown(f"**Q{idx + 1}. [{q.topic}]** `{q_label}` — {q.question}")
                                if q.expected_answer:
                                    with st.expander(f"💡 Show Expected Answer (Q{idx + 1})"):
                                        st.write(q.expected_answer)
                                        if q.feedback:
                                            st.caption(f"Feedback: {q.feedback}")

        with tab_learn:
            st.subheader("📖 Structured Learning Mode (10-Step Curriculum)")
            available_topics = list(CURATED_TOPIC_SUBTOPICS.keys())
            selected_topic = st.selectbox("Select VLSI Topic to Master:", available_topics)

            curriculum = learning_service.get_topic_curriculum(selected_topic)
            st.write(f"**Topic Overview:** {curriculum.concept_summary}")

            st.markdown("### 📋 Structured Subtopic Hierarchy")
            for idx, sub in enumerate(curriculum.key_subtopics):
                st.markdown(f"{idx + 1}. **{sub}**")

            st.divider()
            st.subheader("✍️ Interactive Practice Drill")
            if curriculum.practice_questions:
                q_to_practice = curriculum.practice_questions[0]
                st.markdown(f"**Practice Question:** {q_to_practice.question}")
                user_pract_ans = st.text_area("Your Detailed Verification Answer:", height=100, key=f"pract_{q_to_practice.id}")

                col_eval1, col_eval2 = st.columns(2)
                with col_eval1:
                    if st.button("Mark Correct & Evaluate", key=f"eval_cor_{q_to_practice.id}") and q_to_practice.id is not None:
                        res = learning_service.evaluate_practice_answer(
                            q_to_practice.id, user_answer=user_pract_ans, was_correct=True
                        )
                        st.success(f"Evaluation: {res.feedback} | Confidence updated to {int(res.updated_confidence * 100)}%")
                with col_eval2:
                    if st.button("Mark Incorrect & Record Gap", key=f"eval_inc_{q_to_practice.id}") and q_to_practice.id is not None:
                        res = learning_service.evaluate_practice_answer(
                            q_to_practice.id, user_answer=user_pract_ans, was_correct=False
                        )
                        st.error(f"Evaluation: {res.feedback} | Confidence updated to {int(res.updated_confidence * 100)}%")
            else:
                st.info("No practice questions currently loaded for this topic.")

        with tab_sim:
            st.subheader("🎙️ Realistic Turn-by-Turn Multi-Stage Interview Simulator")
            stages_list = [
                SimulationStage.HR,
                SimulationStage.DIGITAL_DESIGN,
                SimulationStage.SYSTEM_VERILOG,
                SimulationStage.UVM,
                SimulationStage.PROTOCOL,
                SimulationStage.PROJECT_DEEP_DIVE,
                SimulationStage.DEBUGGING,
                SimulationStage.BEHAVIORAL,
            ]

            if "active_sim" not in st.session_state and st.button("🚀 Start New Full Interview Simulation"):
                sess = sim_engine.start_simulation(company="Qualcomm India", role="Design Verification Engineer", stages=stages_list)
                st.session_state["active_sim"] = sess
                st.rerun()

            if "active_sim" in st.session_state:
                sim_sess = st.session_state["active_sim"]
                st.write(f"**Simulation Session:** `{sim_sess.session_id}` | Company: **{sim_sess.company}** | Role: **{sim_sess.role}**")
                st.progress(sim_sess.current_stage_index / len(sim_sess.stages))

                if not sim_sess.is_completed:
                    current_st = sim_sess.stages[sim_sess.current_stage_index]
                    q_text = sim_engine.get_next_question_for_stage(sim_sess, project_name="AXI4 UVC Testbench")

                    st.markdown(f"### Stage {sim_sess.current_stage_index + 1}/{len(sim_sess.stages)}: **{current_st.value}**")
                    st.markdown(f"**Interviewer:** *\"{q_text}\"*")

                    ans_input = st.text_area("Your Response:", height=100, key=f"sim_turn_{sim_sess.current_stage_index}")

                    col_s1, col_s2 = st.columns(2)
                    with col_s1:
                        if st.button("Submit (Strong / Correct)", key=f"sub_str_{sim_sess.current_stage_index}"):
                            sim_engine.submit_turn_response(sim_sess, user_response=ans_input, was_correct=True)
                            st.rerun()
                    with col_s2:
                        if st.button("Submit (Struggled / Incorrect)", key=f"sub_strug_{sim_sess.current_stage_index}"):
                            sim_engine.submit_turn_response(sim_sess, user_response=ans_input, was_correct=False)
                            st.rerun()
                else:
                    st.success(f"🎉 **Interview Simulation Completed!** Final Score: `{sim_sess.overall_score}%`")
                    st.subheader("Turn History & Feedback")
                    for t in sim_sess.turns:
                        st.markdown(f"- **[{t.stage.value}]** *{t.question}* → `{'PASS' if t.evaluated_correctness else 'GAP'}`: {t.feedback}")

                    if st.button("Reset Simulation"):
                        del st.session_state["active_sim"]
                        st.rerun()

        with tab_debrief:
            st.subheader("🔄 Real Interview Debrief & Continuous Learning Loop")
            st.write(
                "After completing a real technical or HR interview round, record the questions asked, your responses, "
                "and interviewer feedback here. The Career Buddy will automatically ingest verified historical questions "
                "with full provenance, detect new weak areas, update topic confidence, and refine future preparation."
            )

            with st.form("interview_debrief_form"):
                col_d_c, col_d_r = st.columns(2)
                d_company = col_d_c.text_input("Company Name:", value="NVIDIA India")
                d_role = col_d_r.text_input("Role Title:", value="Design Verification Engineer")

                col_d_rnd, col_d_out = st.columns(2)
                d_round = col_d_rnd.selectbox("Interview Round:", ["Round 1 — Technical Screening", "Round 2 — Technical Deep Dive", "Round 3 — Managerial / Architecture", "HR / Behavioral"])
                d_outcome = col_d_out.selectbox("Round Outcome:", ["passed", "next_round", "offer", "rejected"])

                d_date = st.date_input("Interview Date:", value=datetime.now(UTC).date())
                d_gen_feedback = st.text_area("General Feedback & Interviewer Remarks:", placeholder="e.g., Strong on SystemVerilog OOP, but need deeper precision on AXI burst wrap calculations and multi-clock SVA.")

                st.markdown("### 📝 Specific Interview Questions Asked")
                col_q1, col_q2 = st.columns([3, 1])
                q1_text = col_q1.text_input("Question 1:", value="Explain 2-FF Gray code pointer synchronization in an Asynchronous FIFO.")
                q1_topic = col_q2.selectbox("Topic Q1:", ["Async FIFO", "Clock Domain Crossing", "UVM", "SystemVerilog OOP", "AXI Protocol", "SystemVerilog Assertions", "Digital Design"], key="q1_top")
                q1_cor = col_q1.checkbox("Answered Correctly? (Uncheck if struggled)", value=True, key="q1_cor")
                q1_fb = col_q1.text_input("Interviewer Feedback / Note (Q1):", value="Candidate clearly explained pointer wrap and metastability protection.", key="q1_fb")

                st.divider()
                col_q2a, col_q2b = st.columns([3, 1])
                q2_text = col_q2a.text_input("Question 2:", value="In AXI4, what is the difference between FIXED, INCR, and WRAP bursts?")
                q2_topic = col_q2b.selectbox("Topic Q2:", ["AXI Protocol", "Async FIFO", "UVM", "SystemVerilog OOP", "SystemVerilog Assertions", "Digital Design"], key="q2_top")
                q2_cor = col_q2a.checkbox("Answered Correctly? (Uncheck if struggled)", value=False, key="q2_cor")
                q2_fb = col_q2a.text_input("Interviewer Feedback / Note (Q2):", value="Review WRAP burst address calculation formula and alignment restrictions.", key="q2_fb")

                debrief_submit = st.form_submit_button("📥 Ingest Interview Debrief & Update Career Learning Loop")

                if debrief_submit and d_company and q1_text:
                    questions_payload = [
                        InterviewQuestionOutcome(
                            question=q1_text,
                            topic=q1_topic,
                            was_correct=q1_cor,
                            feedback=q1_fb,
                        ),
                    ]
                    if q2_text:
                        questions_payload.append(
                            InterviewQuestionOutcome(
                                question=q2_text,
                                topic=q2_topic,
                                was_correct=q2_cor,
                                feedback=q2_fb,
                            )
                        )

                    debrief_obj = InterviewOutcomeDebrief(
                        company=d_company,
                        role=d_role,
                        round=d_round,
                        date=d_date.isoformat(),
                        outcome=d_outcome,
                        general_feedback=d_gen_feedback,
                        questions=questions_payload,
                    )

                    rep = career_pipeline.record_interview_outcome(debrief_obj)
                    st.success(f"🎉 {rep.message}")
                    st.rerun()


    # -------------------------------------------------------------------------
    # 6. QUESTION BANK
    # -------------------------------------------------------------------------
    elif nav == "📚 6. Question Bank":
        st.header("📚 Historical Interview Question Bank & Dataset Ingestion")

        tab_bank, tab_provenance = st.tabs(["🔍 Search & Filter Question Bank", "📥 Ingest Historical Dataset"])

        with tab_bank:
            all_qs = career_repo.get_all_questions()
            st.write(f"Total Stored Questions: **{len(all_qs)}**")

            col_f1, col_f2, col_f3 = st.columns(3)
            filter_comp = col_f1.text_input("Filter by Company:", value="")
            filter_topic = col_f2.text_input("Filter by Topic:", value="")
            filter_ver = col_f3.selectbox("Type Filter:", ["ALL", "VERIFIED HISTORICAL", "GENERATED / PRACTICE"])

            filtered_qs = all_qs
            if filter_comp:
                filtered_qs = [q for q in filtered_qs if q.company and filter_comp.lower() in q.company.lower()]
            if filter_topic:
                filtered_qs = [q for q in filtered_qs if filter_topic.lower() in q.topic.lower()]
            if filter_ver == "VERIFIED HISTORICAL":
                filtered_qs = [q for q in filtered_qs if q.verified]
            elif filter_ver == "GENERATED / PRACTICE":
                filtered_qs = [q for q in filtered_qs if not q.verified]

            st.write(f"Showing **{len(filtered_qs)}** question(s):")

            # Display with strict separation of historical vs generated
            for q in filtered_qs:
                badge = "🟢 VERIFIED HISTORICAL" if q.verified else "🟡 GENERATED / PRACTICE"
                with st.expander(f"{badge} | [{q.topic}] {q.question[:90]}..."):
                    st.markdown(f"**Full Question:** {q.question}")
                    st.write(f"**Company:** {q.company or 'General'} | **Role:** {q.role or 'DV'} | **Times Asked:** {q.times_asked}")
                    st.write(f"**Source Provenance:** `{q.source}` | **Verification State:** `{'VERIFIED' if q.verified else 'UNVERIFIED'}`")
                    if q.expected_answer:
                        st.write(f"**Expected Answer:** {q.expected_answer}")
                    if q.user_answer:
                        st.write(f"**Previous Candidate Answer:** {q.user_answer}")
                    if q.feedback:
                        st.write(f"**Feedback:** {q.feedback}")

        with tab_provenance:
            st.subheader("📥 Ingest Historical Interview Questions & Provenance")
            st.write("Import structured YAML files containing historical questions, rounds, and candidate mistakes.")
            import_path = st.text_input("Dataset YAML File Path:", value="profile/historical_interviews.yaml")

            if st.button("Execute Batch Ingestion"):
                if Path(import_path).exists():
                    res = career_pipeline.import_historical_data_from_file(import_path)
                    st.success(f"Ingestion successful! Imported {res.questions_imported} questions, {res.weak_areas_imported} weak areas.")
                    st.rerun()
                else:
                    st.error(f"File not found at path: {import_path}")

    # -------------------------------------------------------------------------
    # 7. FINAL ASSESSMENT
    # -------------------------------------------------------------------------
    elif nav == "🎯 7. Final Assessment":
        st.header("🎯 Pre-Interview Final Assessment & Remediation Testing")
        all_jobs = job_repo.list_normalized_jobs()

        if not all_jobs:
            st.info("No jobs available. Ingest a job first.")
        else:
            job_sel = st.selectbox(
                "Target Job for Final Assessment:",
                [f"{j.company} — {j.title} (ID: {j.id})" for j in all_jobs],
                key="assessment_target_job_sel",
            )
            target_job_id = int(job_sel.split("ID: ")[1].replace(")", ""))

            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                if st.button("📝 Generate Timed Mock Test (45 mins)"):
                    test = discovery_pipeline.assessment_engine.generate_timed_mock_test(target_job_id)
                    st.session_state["active_assessment"] = test
                    st.success(f"Mock Test generated with {len(test.questions)} questions!")

            with col_btn2:
                if st.button("🎓 Generate 9-Section Final Assessment (60 mins)"):
                    test = career_pipeline.create_final_assessment(target_job_id)
                    st.session_state["active_assessment"] = test
                    st.success(f"Final Assessment generated with {len(test.questions)} questions across 9 sections!")

            if "active_assessment" in st.session_state:
                test = st.session_state["active_assessment"]
                st.subheader(f"📋 {test.title} (Time Limit: {test.time_limit_minutes} mins)")
                st.caption("Answer each question in detail. Answers are hidden during test execution to ensure realistic evaluation.")

                user_answers = []
                with st.form("final_assessment_submission_form"):
                    for idx, q_item in enumerate(test.questions):
                        st.markdown(f"**Q{idx + 1}. [{q_item.topic}]** {q_item.question}")
                        ans = st.text_area(f"Your Answer (Q{idx + 1}):", key=f"asmt_q_{q_item.question_id}", height=80)
                        user_answers.append({"question_id": q_item.question_id, "user_answer": ans})

                    submitted_test = st.form_submit_button("Submit Assessment for Evaluation")
                    if submitted_test and test.id is not None:
                        scored_test = career_pipeline.submit_final_assessment(
                            test.id, user_answers=user_answers
                        )
                        st.session_state["scored_assessment"] = scored_test
                        st.success(f"Assessment scored! Overall Score: {scored_test.score or 0.0}% ({scored_test.correct_count}/{scored_test.total_questions} correct)")
                        st.rerun()

            if "scored_assessment" in st.session_state:
                scored = st.session_state["scored_assessment"]
                st.subheader("📊 Assessment Performance Breakdown")
                st.metric("Final Score", f"{scored.score or 0.0}%", f"{scored.correct_count}/{scored.total_questions} correct")
                st.json(scored.topic_breakdown)

                if scored.incorrect_count > 0:
                    st.warning(f"Detected {scored.incorrect_count} missed questions. Generate a remediation drill:")
                    if st.button("🔄 Generate Remediation Test for Missed Topics") and scored.id is not None:
                        remed_test = discovery_pipeline.assessment_engine.generate_remediation_test(scored.id)
                        st.session_state["active_assessment"] = remed_test
                        st.success(f"Remediation test created with {len(remed_test.questions)} targeted questions!")
                        st.rerun()

    # -------------------------------------------------------------------------
    # 8. READINESS
    # -------------------------------------------------------------------------
    elif nav == "🛡️ 8. Readiness":
        st.header("🛡️ Interview Readiness Gates & Topic Diagnostics")
        all_jobs = job_repo.list_normalized_jobs()

        if not all_jobs:
            st.info("Ingest a job to calculate job-specific readiness.")
        else:
            job_sel = st.selectbox(
                "Select Job to Evaluate Readiness:",
                [f"{j.company} — {j.title} (ID: {j.id})" for j in all_jobs],
                key="readiness_job_sel",
            )
            target_job_id = int(job_sel.split("ID: ")[1].replace(")", ""))
            readiness = career_pipeline.calculate_readiness(target_job_id)

            c1, c2 = st.columns(2)
            c1.metric("Overall Readiness Score", f"{int(readiness.overall_readiness_score)}%")
            c2.metric("Readiness Level Gate", readiness.readiness_level)

            st.write(f"**Recommended Preparation Action:** {readiness.recommended_action}")

            st.subheader("Topic Mastery Breakdown")
            for topic, score in readiness.topic_scores.items():
                col_t, col_b = st.columns([1, 3])
                col_t.write(f"**{topic}**")
                col_b.progress(score / 100.0)

            col_m, col_w = st.columns(2)
            with col_m:
                st.markdown("**Mastered Topics (>=80%):**")
                for m in readiness.mastered_topics:
                    st.markdown(f"- ✅ {m}")
            with col_w:
                st.markdown("**Topics Needing Review (<70%):**")
                for w in readiness.weak_topics:
                    st.markdown(f"- ⚠️ {w}")

    # -------------------------------------------------------------------------
    # 9. SCHEDULE
    # -------------------------------------------------------------------------
    elif nav == "📅 9. Schedule":
        st.header("📅 Personalized Interview Preparation Schedule")
        all_jobs = job_repo.list_normalized_jobs()

        if not all_jobs:
            st.info("Ingest a job first.")
        else:
            job_sel = st.selectbox(
                "Target Job for Preparation Schedule:",
                [f"{j.company} — {j.title} (ID: {j.id})" for j in all_jobs],
                key="schedule_job_sel",
            )
            target_job_id = int(job_sel.split("ID: ")[1].replace(")", ""))
            interview_date = st.date_input("Target Interview Date:", value=datetime.now(UTC).date())

            if st.button("Generate Adaptive Schedule"):
                target_iso = f"{interview_date.isoformat()}T10:00:00"
                sched = discovery_pipeline.assessment_engine.generate_preparation_schedule(
                    job_id=target_job_id, target_interview_date=target_iso
                )
                st.session_state["active_sched"] = sched
                st.success("Preparation Schedule generated!")

            if "active_sched" in st.session_state:
                sched = st.session_state["active_sched"]
                st.subheader(f"📅 Schedule for {sched.company} — {sched.title}")
                st.write(f"**Target Interview Date:** {sched.target_interview_date[:10] if sched.target_interview_date else 'Not set'}")

                for m in sched.milestones:
                    st.markdown(f"### {m.day_offset} — **{m.topic}** ({m.target_date})")
                    st.write(f"**Activity:** {m.activity_type.upper()} | **Estimated Time:** {m.estimated_minutes} mins")
                    st.write(f"**Milestone Goal:** {m.milestone_goal}")
                    st.divider()

    # -------------------------------------------------------------------------
    # 10. EMAIL / NOTIFICATIONS
    # -------------------------------------------------------------------------
    elif nav == "✉️ 10. Email & Notifications":
        st.header("✉️ External Action Proposals & Human Notification Center")

        st.info(
            "🛡️ **Safety Boundaries:**\n"
            "- The AI Career Buddy generates scheduling and email proposals in `PROPOSED` state.\n"
            "- It NEVER sends external emails or creates calendar events autonomously.\n"
            "- Proposals require explicit human approval."
        )

        proposals = notification_service.list_proposals()
        st.subheader("📬 Pending Action Proposals (Awaiting Human Approval)")

        if not proposals:
            st.caption("No pending proposals.")
        else:
            for p in proposals:
                with st.expander(f"✉️ {p.notification_type.upper()}: {p.subject} [{p.status.upper()}]"):
                    st.write(f"**Company:** {p.target_company} | **Role:** {p.target_role}")
                    st.write(f"**Scheduled Time:** {p.scheduled_time}")
                    st.write(f"**Rationale:** {p.rationale}")
                    st.text_area("Content Body:", value=p.body_content, height=80, disabled=True)

                    if p.status in (NotificationDispatchStatus.PROPOSED, "proposed"):
                        col_ap, col_rj = st.columns(2)
                        with col_ap:
                            if st.button(f"✅ Approve Proposal #{p.id}", key=f"prop_app_{p.id}"):
                                notification_service.approve_proposal(p.id)
                                st.success("Proposal marked APPROVED.")
                                st.rerun()
                        with col_rj:
                            if st.button(f"❌ Reject Proposal #{p.id}", key=f"prop_rej_{p.id}"):
                                notification_service.reject_proposal(p.id)
                                st.error("Proposal marked REJECTED.")
                                st.rerun()

        st.divider()
        st.subheader("🔔 Notification Action Center")
        notifications = job_repo.list_notifications()
        if notifications:
            for n in notifications:
                col_icon = "⚠️" if n.notification_type == NotificationType.HUMAN_APPROVAL_REQUIRED else "ℹ️"
                st.markdown(f"- {col_icon} **{n.title}** (`{n.created_at[:19].replace('T', ' ')}`): {n.message}")
        else:
            st.caption("No alerts in notification center.")

    # -------------------------------------------------------------------------
    # 11. CAREER ANALYTICS
    # -------------------------------------------------------------------------
    elif nav == "📈 11. Career Analytics":
        st.header("📈 Transparent Career Analytics & Factual Distribution Trends")
        st.info("All analytics are computed strictly from verified SQLite records without data invention.")

        summary = analytics_service.get_summary_metrics()

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Jobs", summary.get("total_discovered_jobs", 0))
        c2.metric("Total Applications", summary.get("total_applications", 0))
        c3.metric("Confirmed Applied", summary.get("applications_applied", 0))
        c4.metric("Conversion Rate", summary.get("conversion_rate", "Insufficient data"))

        # ATS Score Distribution Table
        st.subheader("📄 Tailored Resume ATS Score Distribution")
        res_dist = analytics_service.get_resume_ats_distribution()
        if res_dist:
            st.dataframe(res_dist, use_container_width=True)
        else:
            st.info("Insufficient data: No tailored resumes created yet.")

        # Question Bank Topic Frequency
        st.subheader("📊 Question Bank Topic Frequency")
        topic_freq = analytics_service.get_interview_topic_frequency()
        if topic_freq:
            st.dataframe(topic_freq, use_container_width=True)
        else:
            st.info("Insufficient data: Question bank is empty.")

        # Frequently Missed Questions
        st.subheader("⚠️ Most Frequently Missed Questions")
        missed_qs = analytics_service.get_frequently_missed_questions()
        if missed_qs:
            st.dataframe(missed_qs, use_container_width=True)
        else:
            st.success("No incorrect questions recorded! Great performance.")

        # Assessment Score History
        st.subheader("🎯 Assessment Score History")
        asmt_hist = analytics_service.get_assessment_score_history()
        if asmt_hist:
            st.dataframe(asmt_hist, use_container_width=True)
        else:
            st.info("Insufficient data: No assessments completed yet.")

    # -------------------------------------------------------------------------
    # 12. SETTINGS
    # -------------------------------------------------------------------------
    elif nav == "⚙️ 12. Settings":
        st.header("⚙️ Candidate Profile & Ground Truth Fact Bank")

        tab_cand, tab_bank_view, tab_sys = st.tabs(["👤 Candidate Profile", "🏛️ Verified Fact Bank", "🔧 System Status"])

        with tab_cand:
            st.write(f"**Target Graduation Year:** {profile.candidate.graduation_year}")
            st.write(f"**Experience Level:** {profile.candidate.experience_level}")
            st.write(f"**Target Roles:** {', '.join(profile.candidate.target_roles)}")
            st.write(f"**India Priority Hubs:** {', '.join(profile.candidate.locations.india_priority)}")
            st.write(f"**Overseas Opportunities:** {profile.candidate.locations.overseas_enabled} (Requires sponsorship: {profile.candidate.locations.overseas_require_sponsorship})")

        with tab_bank_view:
            st.write(f"Total Verified Fact Items: **{len(facts.facts)}**")
            fact_rows = [
                {
                    "Fact ID": f.fact_id,
                    "Category": f.category.value,
                    "Subject": f.subject,
                    "Verified": f.verified,
                }
                for f in facts.facts
            ]
            st.dataframe(fact_rows, use_container_width=True)

        with tab_sys:
            st.write("**Database Connection:** SQLite WAL Mode (`data/job_ai.db`)")
            st.write("**Resume Export Directory:** `artifacts/resumes/`")
            st.success("All backend subsystems active and operational.")


if __name__ == "__main__":
    main()
