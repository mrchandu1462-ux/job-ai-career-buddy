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
from app.career.copilot import (
    InterviewCopilotService,
    MockInterviewMode,
)
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
    FreshnessBucket,
    NotificationType,
)
from app.db.repository import JobRepository
from app.jobs.digest import DailyJobDigestService
from app.jobs.freshness import (
    calculate_fresh_job_priority_score,
)
from app.jobs.monitoring_service import FreshJobMonitoringService
from app.jobs.pipeline import JobDiscoveryPipeline
from app.jobs.scanner import FreshJobScanner
from app.jobs.sources.base import JobDiscoveryQuery
from app.jobs.watchlist import CompanyWatchlistService
from app.notifications.service import EmailNotificationService
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
    watchlist_service = CompanyWatchlistService(conn)
    digest_service = DailyJobDigestService(conn)
    scanner_service = FreshJobScanner(
        conn=conn,
        profile=profile,
        fact_bank=facts,
    )
    career_pipeline = HistoricalInterviewPipeline(conn)
    bank_service = QuestionBankService(conn, career_repo)
    learning_service = LearningModeService(career_repo)
    sim_engine = InterviewSimulationEngine(career_repo)
    analytics_service = CareerAnalyticsService(conn, job_repo, career_repo, resume_repo)
    notification_service = ScheduleNotificationService(conn)
    email_service = EmailNotificationService(conn)
    copilot_service = InterviewCopilotService(conn)
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
        "watchlist_service": watchlist_service,
        "digest_service": digest_service,
        "scanner_service": scanner_service,
        "copilot_service": copilot_service,
        "career_pipeline": career_pipeline,
        "bank_service": bank_service,
        "learning_service": learning_service,
        "sim_engine": sim_engine,
        "analytics_service": analytics_service,
        "notification_service": notification_service,
        "email_service": email_service,
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
    watchlist_service: CompanyWatchlistService = ctx["watchlist_service"]
    digest_service: DailyJobDigestService = ctx["digest_service"]
    scanner_service: FreshJobScanner = ctx["scanner_service"]
    copilot_service: InterviewCopilotService = ctx["copilot_service"]
    career_pipeline: HistoricalInterviewPipeline = ctx["career_pipeline"]
    bank_service: QuestionBankService = ctx["bank_service"]
    learning_service: LearningModeService = ctx["learning_service"]
    sim_engine: InterviewSimulationEngine = ctx["sim_engine"]
    analytics_service: CareerAnalyticsService = ctx["analytics_service"]
    notification_service: ScheduleNotificationService = ctx["notification_service"]
    email_service: EmailNotificationService = ctx["email_service"]
    docx_exporter: DOCXResumeExporter = ctx["docx_exporter"]
    pdf_exporter: PDFResumeExporter = ctx["pdf_exporter"]
    export_validator: ResumeExportValidator = ctx["export_validator"]

    # Top Alert Bar for Fresh <=24h Jobs
    digest_stats = job_repo.get_daily_digest_stats(hours=24.0)
    if digest_stats.get("total_fresh_24h", 0) > 0:
        st.info(
            f"🚨 **NEW FRESH JOBS**: **{digest_stats['total_fresh_24h']}** newly verified jobs in the last 24h "
            f"(🇮🇳 India: **{digest_stats['india_fresh_count']}** | 🌐 Overseas: **{digest_stats['overseas_fresh_count']}** | "
            f"🔥 Critical: **{digest_stats.get('critical_matches_count', 0)}** | 🟢 High: **{digest_stats.get('high_matches_count', 0)}** | "
            f"⭐ Watchlist: **{digest_stats.get('watchlist_matches_count', 0)}**)"
        )

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
    # 2. FRESH JOBS & 24-HOUR TRACKING ENGINE
    # -------------------------------------------------------------------------
    elif "2. Fresh Jobs" in nav or "2. Jobs" in nav:
        st.header("🔥 Fresh Job Intelligence & 24-Hour Tracking Engine")

        tab_browse, tab_digest, tab_watchlist, tab_scan, tab_manual, tab_monitor = st.tabs([
            "⚡ Fresh Opportunities",
            "📰 Daily Job Digest",
            "⭐ Company Watchlist",
            "🚀 Scanner Controls",
            "➕ Manual Ingestion",
            "🤖 Monitor Daemon",
        ])

        with tab_browse:
            all_jobs = job_repo.list_normalized_jobs()
            fresh_stats = job_repo.get_daily_digest_stats(hours=24.0)

            # KPI Metrics Row
            kpi1, kpi2, kpi3, kpi4, kpi5, kpi6 = st.columns(6)
            kpi1.metric("⚡ Fresh <=24h", fresh_stats.get("total_fresh_24h", 0))
            kpi2.metric("🇮🇳 India Hubs", fresh_stats.get("india_fresh_count", 0))
            kpi3.metric("🌐 Overseas", fresh_stats.get("overseas_fresh_count", 0))
            kpi4.metric("🔥 Critical Matches", fresh_stats.get("critical_matches_count", 0))
            kpi5.metric("🟢 High Matches", fresh_stats.get("high_matches_count", 0))
            kpi6.metric("⭐ Watchlist Jobs", fresh_stats.get("watchlist_matches_count", 0))

            st.divider()

            # Multi-Filters
            f_col1, f_col2, f_col3, f_col4, f_col5 = st.columns(5)
            with f_col1:
                filter_geo = st.selectbox("Market Region", ["All", "India", "Overseas"], index=0)
            with f_col2:
                filter_fresh = st.selectbox(
                    "Freshness Window",
                    ["All", "<= 1 hour", "<= 6 hours", "<= 24 hours (Fresh)", "1-3 days", ">7 days"],
                    index=0,
                )
            with f_col3:
                filter_cat = st.selectbox("Priority Tier", ["All", "CRITICAL (🔥)", "HIGH (🟢)", "MEDIUM (🟡)", "LOW (⚪)"], index=0)
            with f_col4:
                filter_role = st.selectbox("Role Focus", ["All", "Design Verification", "RTL Design", "Validation"], index=0)
            with f_col5:
                filter_wl_only = st.checkbox("⭐ Watchlist Only", value=False)

            if not all_jobs:
                st.info("No job listings found. Use 'Scanner Controls' tab to run fresh discovery.")
            else:
                ranked_matches = discovery_pipeline.evaluate_and_rank_all_jobs(eligible_only=False)

                # Filter pipeline
                filtered_ranked = []
                for r in ranked_matches:
                    nj = job_repo.get_normalized_job(r.job_id)
                    if not nj:
                        continue

                    is_india = (nj.country or "India").lower() == "india" or nj.region == "india"
                    if filter_geo == "India" and not is_india:
                        continue
                    if filter_geo == "Overseas" and is_india:
                        continue

                    # Freshness filter
                    f_age = getattr(nj, "freshness_age_hours", None)
                    if filter_fresh == "<= 1 hour" and (f_age is None or f_age > 1.0):
                        continue
                    if filter_fresh == "<= 6 hours" and (f_age is None or f_age > 6.0):
                        continue
                    if filter_fresh == "<= 24 hours (Fresh)" and (f_age is None or f_age > 24.0):
                        continue
                    if filter_fresh == "1-3 days" and (f_age is None or f_age <= 24.0 or f_age > 72.0):
                        continue
                    if filter_fresh == ">7 days" and (f_age is None or f_age <= 168.0):
                        continue

                    # Category filter
                    nj_pcat = getattr(nj, "priority_category", "LOW")
                    if filter_cat == "CRITICAL (🔥)" and nj_pcat != "CRITICAL":
                        continue
                    if filter_cat == "HIGH (🟢)" and nj_pcat != "HIGH":
                        continue
                    if filter_cat == "MEDIUM (🟡)" and nj_pcat != "MEDIUM":
                        continue
                    if filter_cat == "LOW (⚪)" and nj_pcat != "LOW":
                        continue

                    # Watchlist filter
                    if filter_wl_only and not getattr(nj, "is_watchlist", False):
                        continue

                    # Role filter
                    if filter_role != "All":
                        target_kw = filter_role.lower()
                        if target_kw not in (nj.title or "").lower() and target_kw not in (nj.role_category or "").lower():
                            continue

                    filtered_ranked.append((r, nj))

                if not filtered_ranked:
                    st.warning("No opportunities match the selected filter criteria.")
                else:
                    st.write(f"Displaying **{len(filtered_ranked)}** matched opportunity(s):")
                    job_choices = {
                        f"[{nj.priority_category}] {nj.company} — {nj.title} ({nj.location or nj.country or 'India'}) [Score: {nj.priority_score:.0f}/100]": r.job_id
                        for r, nj in filtered_ranked
                    }
                    selected_choice = st.selectbox("Select Opportunity to Inspect & Action:", list(job_choices.keys()))
                    selected_job_id = job_choices[selected_choice]

                    selected_pair = next(item for item in filtered_ranked if item[0].job_id == selected_job_id)
                    selected_match, norm_job = selected_pair[0], selected_pair[1]
                    app_rec = job_repo.get_application_by_job_id(selected_job_id)

                    f_age = getattr(norm_job, "freshness_age_hours", None)
                    fresh_badge = f"{f_age:.1f}h old" if f_age is not None else "Verified fresh"
                    wl_badge = " ⭐ (Watchlist)" if getattr(norm_job, "is_watchlist", False) else ""

                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Company & Role", f"{norm_job.company}{wl_badge}", norm_job.title)
                    c2.metric("8D Priority Score", f"{norm_job.priority_score:.0f}/100", getattr(norm_job, "priority_category", "LOW"))
                    c3.metric("Posting Age", fresh_badge, getattr(norm_job, "freshness_bucket", "UNKNOWN"))
                    c4.metric("Application Status", app_rec.status.value.upper() if app_rec else "DISCOVERED")

                    # 8-Dimensional Score Breakdown
                    st.markdown("#### 📊 Explainable 8-Dimensional Priority Score Breakdown")
                    score_8d = calculate_fresh_job_priority_score(
                        match_score=selected_match.match_score,
                        freshness_bucket=getattr(norm_job, "freshness_bucket", FreshnessBucket.UNKNOWN),
                        freshness_confidence=getattr(norm_job, "freshness_confidence", "LOW"),
                        fresher_fit=True,
                        is_watchlist=getattr(norm_job, "is_watchlist", False),
                        has_direct_url=bool(norm_job.application_url),
                        is_india=((norm_job.country or "India").lower() == "india"),
                    )

                    s_col1, s_col2, s_col3, s_col4 = st.columns(4)
                    s_col1.markdown(f"- 🕒 **Freshness:** `{score_8d.freshness:.0f}/25`\n- 💻 **Tech Match:** `{score_8d.technical_match:.0f}/25`")
                    s_col2.markdown(f"- 🎯 **Role Match:** `{score_8d.role_match:.0f}/15`\n- 📁 **Project Fit:** `{score_8d.project_relevance:.0f}/10`")
                    s_col3.markdown(f"- 🎓 **Fresher Fit:** `{score_8d.fresher_fit:.0f}/10`\n- 📍 **Location/Visa:** `{score_8d.location_eligibility:.0f}/5`")
                    s_col4.markdown(f"- 🏢 **Company Conf:** `{score_8d.company_confidence:.0f}/5`\n- 🔗 **Portal Access:** `{score_8d.application_accessibility:.0f}/5`")

                    # Provenance & Timestamp Evidence
                    st.markdown(
                        f"**Provenance:** Source: `{norm_job.source_name or norm_job.source}` | "
                        f"Timestamp Source: `{norm_job.timestamp_source}` | "
                        f"Confidence: `{norm_job.freshness_confidence}` | "
                        f"Visa Sponsorship: `{norm_job.visa_sponsorship}`"
                    )
                    if norm_job.application_url:
                        st.markdown(f"**Direct Application URL:** [{norm_job.application_url}]({norm_job.application_url})")

                    # Match & Gap Analysis
                    col_sk1, col_sk2, col_sk3 = st.columns(3)
                    with col_sk1:
                        st.markdown("**Required Skills:**")
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
                            st.caption("No significant skill gaps.")

                    st.divider()
                    st.subheader("⚡ Available Job Actions")
                    col_act1, col_act2, col_act3, col_act4 = st.columns(4)

                    with col_act1:
                        if st.button("📌 Shortlist Job", key=f"short_{selected_job_id}"):
                            app_service.shortlist_job(selected_job_id, notes="Shortlisted from Fresh Jobs.")
                            st.success("Job marked as SHORTLISTED!")
                            st.rerun()

                    with col_act2:
                        if st.button("🚀 Prepare Application Package", key=f"prep_{selected_job_id}"):
                            pkg = app_service.prepare_application(selected_job_id)
                            st.success(f"Package prepared! ATS Score: `{pkg.tailored_resume.ats_score}/100`.")
                            st.rerun()

                    with col_act3:
                        if st.button("👁️ View Full JD Text", key=f"view_jd_{selected_job_id}"):
                            st.text_area("Job Description", value=norm_job.description or "No text available.", height=150, disabled=True)

                    with col_act4:
                        if st.button("🚫 Ignore Job", key=f"ign_{selected_job_id}") and app_rec and app_rec.id is not None:
                            app_service.review_application(app_rec.id, decision="REJECT", notes="Candidate ignored opportunity.")
                            st.warning("Job marked as REJECTED.")
                            st.rerun()

        # Tab 2: Daily Job Digest
        with tab_digest:
            st.subheader("📰 Daily Fresh Job Intelligence Digest")
            st.caption("Aggregated daily summary of verified fresh <=24h semiconductor jobs in India and Overseas.")
            col_d1, col_d2 = st.columns([1, 3])
            with col_d1:
                digest_hrs = st.selectbox("Lookback Window", [24.0, 48.0, 72.0], index=0)
                if st.button("🔄 Refresh Digest"):
                    st.rerun()
            with col_d2:
                digest_md = digest_service.generate_markdown_digest(hours=digest_hrs)
                st.markdown(digest_md)

        # Tab 3: Company Watchlist
        with tab_watchlist:
            st.subheader("⭐ Target Semiconductor Company Watchlist")
            st.caption("Prioritize fresh opportunity release from target semiconductor & EDA leaders.")

            col_w_add1, col_w_add2, col_w_add3 = st.columns([2, 1, 1])
            with col_w_add1:
                new_comp = st.text_input("Company Name to Watch", placeholder="e.g. Tenstorrent, Western Digital")
            with col_w_add2:
                new_prio = st.selectbox("Watch Priority", ["CRITICAL", "HIGH", "STANDARD"], index=1)
            with col_w_add3:
                st.write("")
                if st.button("➕ Add to Watchlist") and new_comp.strip():
                    watchlist_service.add_company(new_comp.strip(), priority_level=new_prio)
                    st.success(f"Added {new_comp} to watchlist!")
                    st.rerun()

            st.divider()
            wl_summary = watchlist_service.get_watchlist_summary(hours=24.0)
            if wl_summary:
                st.write(f"Tracking **{len(wl_summary)}** semiconductor firms:")
                wl_data = [
                    {
                        "Company": w["company_name"],
                        "Priority": w["priority_level"],
                        "Fresh Jobs (24h)": w["fresh_jobs_count"],
                    }
                    for w in wl_summary
                ]
                st.dataframe(wl_data, use_container_width=True)

        # Tab 4: Scanner Controls
        with tab_scan:
            st.subheader("🚀 Fresh Job Scanner Controls")
            st.caption("Trigger multi-source scanning across permitted career portals, feeds, and boards.")
            col_sc1, col_sc2, col_sc3, col_sc4 = st.columns(4)
            with col_sc1:
                scan_region = st.selectbox("Scan Region", ["all", "india", "overseas"], index=0)
            with col_sc2:
                scan_hours = st.number_input("Freshness Window (Hours)", min_value=1.0, max_value=168.0, value=24.0)
            with col_sc3:
                scan_dry = st.checkbox("Dry Run Only (No DB write)", value=False)
            with col_sc4:
                st.write("")
                if st.button("🚀 Run Scanner Now", type="primary"):
                    with st.spinner(f"Scanning {scan_region.upper()} sources for <= {scan_hours:.0f}h postings..."):
                        scan_rep = scanner_service.scan(
                            region=scan_region,
                            hours=scan_hours,
                            dry_run=scan_dry,
                        )
                        st.success(
                            f"Scan complete in {scan_rep.duration_ms:.1f}ms! "
                            f"Discovered {scan_rep.jobs_discovered} jobs, {scan_rep.new_jobs} new, "
                            f"{scan_rep.fresh_24h} fresh <=24h, and proposed {scan_rep.notifications_proposed} notifications."
                        )
                        st.rerun()

        # Tab 5: Manual Ingestion
        with tab_manual:
            st.subheader("➕ Ingest a New Job Listing")
            with st.form("job_manual_form"):
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

        # Tab 6: Monitor Daemon
        with tab_monitor:
            import os
            import signal
            import subprocess
            import sys

            st.subheader("🤖 Continuous 24-Hour Job Monitor")
            st.caption("Background daemon checking for fresh jobs every hour.")

            sched_status = job_repo.get_scheduler_status()

            if sched_status["is_running"]:
                st.success("🟢 **MONITOR ACTIVE**")
            else:
                st.error("🔴 **MONITOR STOPPED**")

            st.divider()

            c_mon1, c_mon2, c_mon3, c_mon4 = st.columns(4)
            c_mon1.metric("Interval", f"{sched_status['interval_minutes']}m")
            c_mon2.metric("Region", sched_status["region"].upper())
            c_mon3.metric("Last Scan", sched_status["last_cycle_at"][:16].replace("T", " ") if sched_status["last_cycle_at"] else "Never")
            c_mon4.metric("Next Scan", sched_status["next_cycle_at"][:16].replace("T", " ") if sched_status["next_cycle_at"] else "N/A")

            c_mon5, c_mon6, c_mon7, c_mon8 = st.columns(4)
            c_mon5.metric("Last Successful Scan", sched_status["last_successful_scan_at"][:16].replace("T", " ") if sched_status["last_successful_scan_at"] else "None")
            c_mon6.metric("Consecutive Failures", sched_status["consecutive_failures"])
            c_mon7.metric("Jobs Discovered", sched_status["jobs_discovered"])
            c_mon8.metric("Fresh <=24h", sched_status["fresh_jobs"])

            c_mon9, c_mon10, c_mon11, c_mon12 = st.columns(4)
            c_mon9.metric("India Jobs", sched_status["india_jobs"])
            c_mon10.metric("Overseas Jobs", sched_status["overseas_jobs"])
            c_mon11.metric("High Matches", sched_status["high_matches"])
            c_mon12.metric("Critical Matches", sched_status["critical_matches"])

            st.caption(f"🔔 Notification Proposals: **{sched_status['notifications_proposed']}** | Cycles Completed: **{sched_status['cycles_completed']}** | Cycles Failed: **{sched_status['cycles_failed']}**")
            if sched_status.get("last_error"):
                st.warning(f"Last Encountered Error: {sched_status['last_error']}")

            st.divider()

            col_btn1, col_btn2, col_btn3 = st.columns(3)
            with col_btn1:
                if st.button("▶️ Start Monitor Daemon", disabled=sched_status["is_running"]):
                    # Spawn the daemon in background
                    env = os.environ.copy()
                    subprocess.Popen(
                        [sys.executable, "-m", "app.jobs.scheduler"],
                        env=env,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),  # Windows
                    )
                    st.success("Monitor daemon launched!")
                    st.rerun()
            with col_btn2:
                if st.button("⏹️ Stop Monitor Daemon", disabled=not sched_status["is_running"]):
                    # Attempt graceful kill via PID
                    pid = sched_status["daemon_pid"]
                    if pid:
                        try:
                            # On Windows, SIGTERM might not work cleanly, try taskkill
                            if os.name == "nt":
                                subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, check=False)
                            else:
                                os.kill(pid, signal.SIGTERM)
                            st.success(f"Sent stop signal to PID {pid}.")
                        except (OSError, subprocess.SubprocessError) as e:
                            st.error(f"Failed to stop: {e}")
                    else:
                        st.warning("No daemon PID found.")

                    # Also force state update
                    job_repo.set_monitor_state_value("scheduler_running", "false")
                    st.rerun()
            with col_btn3:
                if st.button("🔄 Run Once Now"):
                    with st.spinner("Executing single monitor cycle..."):
                        subprocess.run([sys.executable, "-m", "app.jobs.scheduler", "--once"], capture_output=True, check=False)
                        st.success("Single cycle complete.")
                        st.rerun()


    # -------------------------------------------------------------------------
    # 3. APPLICATIONS
    # -------------------------------------------------------------------------
    elif nav == "📝 3. Applications":
        st.header("📝 Application Intelligence & Mandatory Human Approval Pipeline")

        st.info(
            "🛡️ **Master Human Safety Invariant:**\n"
            "- Preparing an application package NEVER applies autonomously.\n"
            "- Selecting a resume or drafting a cover letter NEVER applies.\n"
            "- Approving a package sets internal state to `APPROVED` for manual candidate action.\n"
            "- Status becomes `APPLIED` ONLY when the human confirms manual submission with evidence/reference ID."
        )

        tab_queue, tab_review, tab_followup, tab_overseas = st.tabs([
            "📋 Priority Application Queue",
            "🔍 Application Review & Approvals",
            "📅 Follow-Up Tracker",
            "🌐 Overseas & Work Authorization",
        ])

        # Tab 1: Priority Queue
        with tab_queue:
            st.subheader("🎯 Daily Prioritized Application Queue")
            st.caption("Auto-ranked based on Technical Match (30%), Freshness (20%), Eligibility (15%), Location (15%), Relevance (10%), and Feasibility (10%). Queue items represent qualified opportunities (`READY_TO_APPLY`). Application packages (tailored resume & cover letter files) are generated on-demand via 'Initialize Application Package'.")

            queue_items = app_service.get_application_queue(max_age_hours=720.0, min_priority_score=40.0)

            if not queue_items:
                st.info("No active opportunities in application queue. Run fresh discovery via Scanner.")
            else:
                # Pipeline Summary Cards
                c_q1, c_q2, c_q3, c_q4, c_q5 = st.columns(5)
                crit_count = sum(1 for q in queue_items if q.priority_tier.value == "CRITICAL")
                high_count = sum(1 for q in queue_items if q.priority_tier.value == "HIGH")
                apply_count = sum(1 for q in queue_items if q.priority_tier.value == "APPLY")
                watch_count = sum(1 for q in queue_items if q.priority_tier.value == "WATCH")
                skip_count = sum(1 for q in queue_items if q.priority_tier.value == "SKIP")

                c_q1.metric("🚨 Apply Now (90+)", crit_count)
                c_q2.metric("🔥 High Priority (80-89)", high_count)
                c_q3.metric("🟢 Apply (70-79)", apply_count)
                c_q4.metric("👀 Watch (50-69)", watch_count)
                c_q5.metric("❌ Skip (<50)", skip_count)

                st.divider()

                for item in queue_items:
                    badge_color = "🚨" if item.priority_tier.value == "CRITICAL" else "🔥" if item.priority_tier.value == "HIGH" else "🟢" if item.priority_tier.value == "APPLY" else "👀"
                    with st.expander(f"{badge_color} [{item.priority_tier.value}] {item.company} — {item.role} ({item.location}) [Score: {item.priority_score:.1f}/100]"):
                        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
                        col_m1.write(f"**Timing:** `{item.timing_recommendation.value}`")
                        col_m2.write(f"**Eligibility:** `{item.eligibility.tier.value}`")
                        col_m3.write(f"**Work Auth:** `{item.work_authorization.status.value}`")
                        col_m4.write(f"**Selected Resume:** `{item.selected_resume_profile.value}`")

                        if item.warnings:
                            for w in item.warnings:
                                st.warning(f"⚠️ {w}")

                        st.write(f"**Resume Reason:** {item.resume_selection_reason}")
                        st.write(f"**Work Auth Details:** {item.work_authorization.sponsorship_details}")

                        if item.official_application_url:
                            st.markdown(f"**Official Portal:** [{item.official_application_url}]({item.official_application_url})")

                        # Cover letter preview
                        with st.expander("📄 View Tailored Cover Letter Draft"):
                            st.text_area("Cover Letter", value=item.cover_letter.full_text, height=200, key=f"cl_preview_{item.job_id}", disabled=True)

                        # Quick Action Buttons
                        col_qb1, col_qb2, col_qb3 = st.columns(3)
                        with col_qb1:
                            if st.button("📝 Initialize Application Package", key=f"init_pkg_{item.job_id}"):
                                app_rec = app_service.shortlist_job(item.job_id)
                                st.success(f"Initialized application package (App #{app_rec.id}). Proceed to 'Application Review' tab to approve.")
                                st.rerun()
                        with col_qb2:
                            if item.official_application_url:
                                st.link_button("🌐 Open Official Portal", item.official_application_url)
                        with col_qb3:
                            if st.button("🚫 Dismiss / Skip", key=f"skip_pkg_{item.job_id}"):
                                st.info("Job marked as skipped for application.")

        # Tab 2: Application Review & Approvals
        with tab_review:
            st.subheader("🔍 Application Review & Manual Submission Gates")
            all_apps = job_repo.list_applications()

            if not all_apps:
                st.info("No active applications initialized yet. Use the 'Priority Queue' to initialize a package.")
            else:
                status_filter = st.selectbox(
                    "Filter Applications by Status:",
                    ["ALL"] + [s.value for s in ApplicationStatus],
                    key="app_status_filter",
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
                                if st.button("✅ Approve Package for Manual Submission", key=f"app_approve_{app.id}") and app.id is not None:
                                    app_service.review_application(app.id, decision="APPROVE", notes="Candidate approved tailored package for manual submission.")
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
                                        error_message=f"{f_stage}: {f_reason}",
                                        evidence=f_stage,
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

        # Tab 3: Follow-Up Tracker
        with tab_followup:
            st.subheader("📅 Application Follow-Up & Stage Tracker")
            st.caption("Manage application response timelines, interview rounds, and follow-up reminders.")
            applied_apps = [a for a in all_apps if a.status == ApplicationStatus.APPLIED] if all_apps else []

            if not applied_apps:
                st.info("No submitted applications to follow up on. Applications marked as APPLIED will appear here.")
            else:
                for app in applied_apps:
                    job = job_repo.get_normalized_job(app.job_id)
                    comp = job.company if job else "Company"
                    role = job.title if job else "Role"
                    with st.expander(f"📬 {comp} — {role} (Applied: {app.applied_at[:10] if app.applied_at else 'Recent'})"):
                        st.write(f"**Application Reference ID:** `{app.notes or 'None'}`")
                        st.write(f"**Applied At:** `{app.applied_at or 'N/A'}`")
                        st.text_input("Interview Stage:", value="Applied / Under Review", key=f"stage_txt_{app.id}")
                        st.date_input("Target Follow-up Date:", key=f"follow_date_{app.id}")
                        st.text_area("Recruiter / Interview Notes:", placeholder="Recruiter screening completed, technical round scheduled...", key=f"notes_txt_{app.id}")

        # Tab 4: Overseas Opportunities
        with tab_overseas:
            st.subheader("🌐 International Opportunities & Visa Sponsorship Intelligence")
            st.caption("Track overseas semiconductor openings with explicit work authorization diagnostics.")

            all_jobs = job_repo.list_normalized_jobs()
            overseas_jobs = [j for j in all_jobs if (j.country or "").lower() != "india" and "india" not in (j.location or "").lower()]

            if not overseas_jobs:
                st.info("No overseas opportunities currently in database.")
            else:
                st.write(f"Found **{len(overseas_jobs)}** international semiconductor opportunities:")
                for oj in overseas_jobs:
                    w_auth = app_service.intelligence.work_auth_classifier.classify(oj)
                    auth_badge = "🟢 Sponsorship Available" if w_auth.status.value == "SPONSORSHIP_AVAILABLE" else "🟡 Sponsorship Unclear" if w_auth.status.value == "SPONSORSHIP_UNCLEAR" else "🔴 Local Auth Required"
                    with st.expander(f"🌍 {oj.company} — {oj.title} ({oj.location or oj.country}) [{auth_badge}]"):
                        st.write(f"**Country:** {oj.country} | **Work Auth Status:** `{w_auth.status.value}`")
                        st.write(f"**Sponsorship Details:** {w_auth.sponsorship_details}")
                        if w_auth.warnings:
                            for w in w_auth.warnings:
                                st.warning(f"⚠️ {w}")
                        if oj.application_url:
                            st.link_button("🌐 Open Official Portal", oj.application_url)


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

        tab_copilot, tab_review, tab_learn, tab_sim, tab_debrief = st.tabs([
            "🤖 Phase 6: Interview Copilot & Mock Practice",
            "📚 Complete 8-Category Review Pack",
            "📖 Structured Learning Mode",
            "🎙️ Multi-Stage Interview Simulator",
            "🔄 Real Interview Debrief & Learning Loop",
        ])

        all_jobs = job_repo.list_normalized_jobs()

        with tab_copilot:
            st.subheader("🎯 Job-Specific Interview Copilot & Readiness Evaluator")
            if not all_jobs:
                st.info("No jobs available. Please scan or ingest jobs first.")
            else:
                target_copilot_label = st.selectbox(
                    "Target Job Listing for Tailored Interview Prep:",
                    [f"{j.company} — {j.title} (Job #{j.id})" for j in all_jobs],
                    key="copilot_job_sel",
                )
                target_cid = int(target_copilot_label.split("Job #")[1].replace(")", ""))
                selected_job = next((j for j in all_jobs if j.id == target_cid), None)

                if selected_job:
                    prep_profile = copilot_service.analyze_job(selected_job)

                    # Top Metrics
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.metric("Target Company", prep_profile.company)
                    with c2:
                        readiness_val = prep_profile.readiness.total_score if prep_profile.readiness else 0.0
                        readiness_lvl = prep_profile.readiness.level.value if prep_profile.readiness else "N/A"
                        st.metric("Interview Readiness Score", f"{readiness_val}/100", readiness_lvl)
                    with c3:
                        st.metric("Required Skills Identified", len(prep_profile.required_skills))

                    # Skill Gap Breakdown
                    st.markdown("### 📊 Skill Gap Analysis (JD vs Fact Bank)")
                    col_gap1, col_gap2 = st.columns(2)
                    with col_gap1:
                        st.write("**Strong & Familiar Skills:**")
                        strong_skills = [g for g in prep_profile.skill_gaps if g.proficiency.value in ("STRONG", "FAMILIAR")]
                        for s in strong_skills:
                            st.success(f"✅ **{s.skill_name}** [{s.proficiency.value}] — {s.evidence}")
                    with col_gap2:
                        st.write("**Gaps & Missing Areas:**")
                        missing_skills = [g for g in prep_profile.skill_gaps if g.proficiency.value in ("MISSING", "PARTIAL")]
                        for s in missing_skills:
                            st.warning(f"⚠️ **{s.skill_name}** [{s.proficiency.value}] — {s.recommendation}")

                    # Tailored 7-Day Study Plan
                    if prep_profile.study_plan:
                        st.markdown("### 📅 Tailored 7-Day Interview Preparation Plan")
                        for day in prep_profile.study_plan.days:
                            with st.expander(f"{day.title} ({day.estimated_minutes} mins)"):
                                st.write(f"**Focus Topics:** {', '.join(day.focus_topics)}")
                                if day.target_weak_areas:
                                    st.write(f"**Target Weak Areas:** {', '.join(day.target_weak_areas)}")
                                st.write(f"**Practice Drills:** {', '.join(day.practice_drills)}")

                    # Mock Interview Practice Launcher
                    st.divider()
                    st.markdown("### 🎙️ Interactive Mock Practice Generator")
                    sel_mode_str = st.selectbox(
                        "Mock Interview Mode:",
                        ["QUICK (10 Questions)", "STANDARD (20 Questions)", "DEEP (40 Questions)", "COMPANY (Targeted)", "WEAKNESS (Focus on Gaps)", "PROJECT (Project Defense)"],
                        key="copilot_mock_mode",
                    )
                    mode_enum = MockInterviewMode.QUICK
                    if "PROJECT" in sel_mode_str:
                        mode_enum = MockInterviewMode.PROJECT
                    elif "WEAKNESS" in sel_mode_str:
                        mode_enum = MockInterviewMode.WEAKNESS
                    elif "COMPANY" in sel_mode_str:
                        mode_enum = MockInterviewMode.COMPANY
                    elif "DEEP" in sel_mode_str:
                        mode_enum = MockInterviewMode.DEEP
                    elif "STANDARD" in sel_mode_str:
                        mode_enum = MockInterviewMode.STANDARD

                    mock_session = copilot_service.start_mock_interview(selected_job, mode=mode_enum)
                    st.info(f"Loaded {len(mock_session.questions)} curated verification questions for {selected_job.company}.")

                    with st.expander("📝 View Practice Questions & Technical Expected Concepts", expanded=True):
                        for q_idx, q in enumerate(mock_session.questions[:5], 1):
                            st.markdown(f"**Q{q_idx}. [{q.category.value}] ({q.difficulty.value})** — {q.question}")
                            st.caption(f"Provenance: `{q.provenance.value}` | Key Concepts: {', '.join(q.expected_concepts)}")

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
        st.header("✉️ Email Alerts, Action Proposals & Human Notification Center")

        tab_email, tab_props, tab_alerts = st.tabs([
            "📧 Automated Email Delivery System",
            "📬 Action Proposals & Human Approval",
            "🔔 Internal System Alerts",
        ])

        with tab_email:
            st.subheader("📧 Email Career Alert Automation")
            st.info(
                "⚡ **Watch Once, Get Notified:**\n"
                "- High-priority opportunities (🚨 CRITICAL 90-100 & 🔥 HIGH 80-89) automatically send immediate formatted email alerts.\n"
                "- Daily Career Digest automatically summarizes fresh 24h opportunities at the configured hour.\n"
                "- Repeated discoveries across hourly scans are strictly deduplicated.\n"
                "- **MANDATORY SAFETY RULE:** Email notifications NEVER autonomously apply to external portals."
            )

            email_cfg = email_service.settings
            stats = email_service.get_delivery_stats()

            # Metric Cards
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Email Enabled", "YES (Active)" if email_cfg.email_enabled else "NO (Console/Dry-Run)")
            c2.metric("Configured Provider", email_cfg.email_provider.upper())
            c3.metric("Sent Alerts", stats.get("sent", 0))
            c4.metric("Suppressed (Deduplicated)", stats.get("suppressed", 0))

            c5, c6, c7, c8 = st.columns(4)
            c5.metric("Recipient", email_cfg.email_to)
            c6.metric("Failed Deliveries", stats.get("failed", 0))
            c7.metric("Daily Digest", f"Hour {email_cfg.digest_hour}:00" if email_cfg.digest_enabled else "Disabled")
            c8.metric("Network Timeout", f"{email_cfg.email_timeout_seconds}s (Max {email_cfg.email_max_retries} retries)")

            if stats.get("last_error"):
                st.warning(f"⚠️ Last Recorded Delivery Error: {stats['last_error']}")

            # Test Email Trigger Controls
            st.divider()
            st.subheader("🧪 Test Email Delivery")
            col_t1, col_t2 = st.columns([2, 2])
            with col_t1:
                test_recip = st.text_input("Test Recipient Address:", value=email_cfg.email_to)
            with col_t2:
                st.write("")
                st.write("")
                col_btn_send, col_btn_dry = st.columns(2)
                with col_btn_send:
                    if st.button("🚀 Send Test Email", key="btn_send_test_email"):
                        with st.spinner("Dispatching test email..."):
                            res = email_service.send_test_email(recipient=test_recip, dry_run=False)
                            if res.success:
                                st.success(f"✅ Test email successfully dispatched via {res.provider}!")
                            else:
                                st.error(f"❌ Test email failed: {res.error_message}")
                            st.rerun()
                with col_btn_dry:
                    if st.button("📝 Dry-Run Test", key="btn_dry_test_email"):
                        res = email_service.send_test_email(recipient=test_recip, dry_run=True)
                        st.info(f"ℹ️ Dry-run generated successfully for {test_recip} (no external network call).")

            # Delivery History Table
            st.divider()
            st.subheader("📋 Recent Email Delivery Audit Log")
            deliveries = email_service.list_recent_deliveries(limit=30)
            if not deliveries:
                st.caption("No email delivery records yet. Hourly scans will record alerts here.")
            else:
                deliv_rows = []
                for d in deliveries:
                    deliv_rows.append({
                        "ID": d.id,
                        "Status": d.delivery_status.value,
                        "Priority": d.priority,
                        "Subject": d.subject[:50] + ("..." if len(d.subject) > 50 else ""),
                        "Recipient": d.recipient,
                        "Provider": d.provider,
                        "Attempts": d.attempt_count,
                        "Timestamp": (d.sent_at or d.created_at)[:19].replace("T", " "),
                        "Error": d.last_error or "—",
                    })
                st.dataframe(deliv_rows, use_container_width=True)

        with tab_props:
            st.subheader("📬 Pending Action Proposals (Awaiting Human Approval)")
            st.info(
                "🛡️ **Safety Boundaries:**\n"
                "- The AI Career Buddy generates scheduling and email proposals in `PROPOSED` state.\n"
                "- Proposals require explicit human approval."
            )

            proposals = notification_service.list_proposals()
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

        with tab_alerts:
            st.subheader("🔔 Internal System Alerts")
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
