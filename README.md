# Job-AI Career Buddy

A local-first, autonomous-but-human-controlled AI Career Operating System for a 2025 VLSI / Design Verification Engineer candidate.

## Purpose

Job-AI Career Buddy guides semiconductor freshers and engineers through the complete career lifecycle:
**Job Discovery** $\rightarrow$ **7D Matching** $\rightarrow$ **Application Intelligence & Eligibility** $\rightarrow$ **Resume Profile Selection** $\rightarrow$ **Tailored Cover Letter** $\rightarrow$ **Application Package** $\rightarrow$ **ATS Validation** $\rightarrow$ **Historical Interview Preparation** $\rightarrow$ **Turn-by-Turn Mock Simulation** $\rightarrow$ **Final Timed Assessment** $\rightarrow$ **Readiness Gates** $\rightarrow$ **Human Review & Approval** $\rightarrow$ **Manual Submission & Follow-Up Tracking** $\rightarrow$ **Real Interview Debrief & Continuous Learning**.

---

## Core Principles

1. **Zero Fabrication**: Never invents skills, tools, technologies, metrics, coverage percentages, bug counts, project outcomes, employment, or interview history.
2. **Fact-Grounded Candidate Claims**: Every line in every generated resume traces 1-to-1 to verified entries in the candidate Fact Bank.
3. **Truthful ATS Optimization**: Aggressively optimizes resume keywords for ATS scanners ($\ge 80/100$ target); when 80 cannot be reached truthfully, displays explicit `ATS TARGET NOT REACHED` gap diagnostics and truthful adjacent evidence rather than inventing keywords.
4. **Strict Human Safety Gates**: Never autonomously submits job applications, dispatches external emails, or creates calendar events. All external actions require explicit human review and approval.
5. **Historical Interview Intelligence & Separation**: Preserves real interview questions with full provenance (company, role, round, candidate answer, feedback). Generated practice questions are strictly separated from verified historical questions.
6. **Local-First & Private**: Operates entirely on the candidate's machine using local SQLite WAL storage and local document generation.

---

## System Architecture

```text
                                  +-----------------------+
                                  | Candidate Profile &   |
                                  | Verified Fact Bank    |
                                  +-----------+-----------+
                                              |
+-------------------+           +-------------v-------------+           +----------------------+
| Job Discovery &   | --------> | Multi-Dimensional Match   | --------> | Application Package  |
| Continuous Monitor|           | Engine & Eligibility Gate |           | & Tailored Cover Ltr |
+-------------------+           +-------------+-------------+           +----------+-----------+
                                              |                                    |
                                +-------------v-------------+           +----------v-----------+
                                | 6-Factor Priority Scoring |           | Human Review &       |
                                | (CRITICAL / HIGH / APPLY) |           | Manual Submission    |
                                +-------------+-------------+           +----------+-----------+
                                              |                                    |
+-------------------+           +-------------v-------------+           +----------v-----------+
| Historical        | --------> | 8-Category Review Pool &  | --------> | Follow-Up Tracking   |
| Question Bank     |           | 10-Step Topic Curriculum  |           | & Interview Copilot  |
+-------------------+           +---------------------------+           +----------------------+
```

---

## Implemented Features

1. **Application Intelligence & Human-Gated Apply Pipeline (Phase 4 Final)**:
   - **Deterministic Eligibility Classification**: Classifies listings into `ENTRY_LEVEL`, `GRADUATE`, `INTERNSHIP`, `EXPERIENCED`, `SENIOR`, or `UNKNOWN`. Applies hard experience gating ($\ge 3$ years clamped to `SKIP` for 2025 freshers).
   - **Work Authorization & Visa Classification**: Evaluates overseas opportunities for explicit sponsorship terms (`SPONSORSHIP_AVAILABLE`, `INTERNATIONAL_APPLICANTS_ACCEPTED`, `LOCAL_AUTHORIZATION_REQUIRED`, `SPONSORSHIP_UNCLEAR`, `UNKNOWN`). Never guesses or assumes sponsorship.
   - **6-Factor Deterministic Application Priority Scoring**: Technical DV Match (30%), Freshness (20%), Graduate Eligibility (15%), Location / Work Auth (15%), Company / Role Relevance (10%), Application Feasibility (10%). Assigns priority tiers: `CRITICAL` (90–100), `HIGH` (80–89), `APPLY` (70–79), `WATCH` (60–69), `SKIP` (<60).
   - **Truthful Resume Profile Selection**: Selects best profile (`DV_CORE`, `ASIC_VERIFICATION`, `RTL_DESIGN`, `VLSI_INTERN`, `GRADUATE_ENGINEER`, `OVERSEAS_DV`) with explicit selection reasons.
   - **Fact-Grounded Cover Letter Generation**: Generates concise tailored letters grounded exclusively in verified education, SystemVerilog/UVM competencies, and verified project details.
   - **Complete Application Package**: Bundles job details, official application URLs, verification status, resume profile, cover letter draft, warnings, and lifecycle state.
   - **Duplicate Application Prevention**: Fingerprint-based deduplication prevents redundant applications across hourly scans while safely supporting material update re-reviews.
   - **Human Review & Approval Gate**: "Approve for Manual Submission" marks `APPROVED`; candidate manually applies and enters reference to record `SUBMITTED_MANUALLY`. Autonomous external submission is strictly prohibited.
   - **Follow-Up Tracker**: Lightweight tracking for application dates, follow-up milestones, interview stages, and notes.

2. **Interview Prep Copilot & Tailored Practice Generator (Phase 6)**:
   - **Job-Specific Interview Profile**: Synthesizes normalized job records, verified JD requirements, role tiers, and candidate Fact Bank into structured interview preparation profiles without data fabrication.
   - **Deterministic JD Analysis**: Extracts technical competencies (Verilog, SV, UVM, SVA, AXI, AHB, APB, RTL, CDC, FIFO, RAL, Python, Linux, Git), role classifications (Tier 1 Core DV through Tier 4 Adjacent), domains (CPU, GPU, SoC, Memory, Networking, Automotive, Semiconductor), and interview signals.
   - **Truthful Skill-Gap Engine**: Classifies every JD skill requirement against verified candidate profile facts into 5 states: `STRONG`, `FAMILIAR`, `PARTIAL`, `MISSING`, `UNKNOWN` with zero technology hallucination.
   - **Provenanced Question Catalog & Categories**: Standardized question catalog spanning Categories A through M (Digital Design, Verilog, SystemVerilog, UVM, Assertions, Functional Coverage, AXI, FIFO/CDC, Memory Verification, Debugging, Python/Linux/Git, Project Defense, HR/Behavioral) with explicit difficulty tiers (`EASY`, `MEDIUM`, `HARD`, `EXPERT`) and truthfulness labeling (`LIKELY`, `POSSIBLE`, `GENERAL_DV_TOPIC`, `VERIFIED_FROM_JD`, `USER_PROVIDED`).
   - **Grounded Project Defense**: Automatically generates rigorous project deep-dive questions grounded exclusively in the candidate's verified projects (e.g., AXI4-Lite slave verification, Async FIFO Gray-code pointers) without inventing metrics or bug counts.
   - **Interactive Mock Interview Engine**: 6 interview modes (`QUICK` [10], `STANDARD` [20], `DEEP` [40], `COMPANY`, `WEAKNESS`, `PROJECT`) with turn-by-turn question delivery and dynamic session management.
   - **Technical Answer Evaluator**: Evaluates technical completeness, clarity, and concepts identified, grading into `CORRECT`, `PARTIALLY_CORRECT`, `INCORRECT`, `UNCLEAR` with structured `GOOD`, `MISSING`, and `PRACTICE` drill feedback without rigid single-wording constraints.
   - **Weakness Tracking & Persistence**: Tracks topic performance metrics (attempts, correct, partial, incorrect, weakness score, improvement trends) in SQLite `weak_areas` table to drive remediation.
   - **Deterministic Interview Readiness Scorer**: Computes explainable 8-dimensional readiness score ($\ge 85$ `READY`, $\ge 70$ `NEAR_READY`, $\ge 50$ `NEEDS_WORK`, $< 50$ `NOT_READY`) with actionable strengths and remediation points.
   - **Dynamic Study Plan Generator**: Generates personalized 7-day preparation schedules dynamically weighted toward candidate weak areas and specific JD protocol requirements.

3. **Smart Career Intelligence, Watchlists & Alerts (Phase 5)**:
   - **Candidate Profile & Role Hierarchy**: Explicit tier hierarchy (Tier 1: Core DV, Tier 2: RTL/Interns, Tier 3: GET/Graduate, Tier 4: Adjacent Semiconductor) with automated rejection of non-semiconductor/unrelated software/generic QA roles.
   - **Location Intelligence & Visa Disambiguation**: Tier 1 India hubs (Bengaluru, Hyderabad, Chennai), Tier 2 India hubs (Pune, Noida, Gurugram, Ahmedabad, Mysuru, Kochi, Mumbai), and 15 priority overseas markets with deterministic work authorization / visa requirement checks.
   - **Configurable Company Watchlist**: Persistent semiconductor employer watchlist seeded with 28+ leading organizations (NVIDIA, AMD, Intel, Qualcomm, TI, Arm, Broadcom, MediaTek, Synopsys, Cadence, Siemens EDA, Marvell, Micron, Samsung, Apple, Google, Microsoft, NXP, Infineon, STMicro, Renesas, ADI, Microchip, Bosch, L&T Semi, Tessolve, eInfochips, HCLTech, Wipro, SiFive, Tenstorrent, Groq, Rivos) with dynamic enable/disable and priority management.
   - **Explainable Matching & Multi-Dimensional Scoring**: Deterministic 7-D fit + 8-D priority scoring with explainable positive reasons (`+`) and risk gaps (`-`).
   - **Match Classifications**: Structured categories (`CRITICAL`, `HIGH`, `GOOD`, `WATCHLIST`, `LOW`, `REJECTED`).
   - **Smart Alert Engine & Modes**: Configurable alert dispatch modes (`CRITICAL_ONLY`, `HIGH_AND_CRITICAL`, `ALL_MATCHED`, `WATCHLIST_COMPANIES`, `DAILY_DIGEST`, `HOURLY_CRITICAL`) with duplicate suppression across hourly scans.
   - **Material Change Re-Alerting**: Automatically detects substantial job updates ($>80$ char expansion + direct application link) and triggers updated notification proposals (`[MATERIAL UPDATE]`).
   - **Daily Career Digest**: Comprehensive markdown digest and notification proposal summarizing fresh 24h opportunities, top 5 ranked roles, India vs Overseas breakdown, and rejection metrics.

4. **Dynamic Career Portal Synchronization (Phase 4)**: Direct synchronization with JavaScript-heavy career portals including **Workday** (`WorkdayCareerAdapter`) and **Greenhouse** (`GreenhouseCareerAdapter`) for leading semiconductor employers with polite request pacing and resilient retry.

5. **Continuous 24-Hour Job Monitor (Phase 3)**: Reliable, local-first background scheduler (`app.jobs.scheduler`) that performs hourly monitoring, persists state, ensures lock safety, supports graceful shutdown, and deduplicates notification proposals.

6. **Fact-Grounded ATS Resumes & Exporters**: Single-column ATS-safe formatting, ATS score breakdown, adjacent evidence mapping, and export validation for DOCX and PDF formats.

7. **Historical Question Bank & Simulations**: Full provenance search, batch YAML dataset ingestion, and multi-stage interview simulation covering HR, Digital Design, SystemVerilog, UVM, Protocols, Project Deep-Dive, and Debugging.

---

## CLI & Automation Usage

### Automated Email Notification & Career Alert CLI
```powershell
# Send a single test email (dry run mode)
python -m app.notifications.email --test --dry-run

# Send a single verification test email using configured provider
python -m app.notifications.email --test

# Send a test email to an explicit recipient
python -m app.notifications.email --test --to "candidate@example.com"
```

### Interview Prep Copilot CLI
```powershell
# Start quick mock interview (10 questions)
python -m app.jobs.interview --mode quick

# Start project defense mock interview for a specific job fingerprint
python -m app.jobs.interview --job <fingerprint> --mode project

# Start weakness-targeted mock interview
python -m app.jobs.interview --mode weakness

# Run interactive turn-by-turn mock session in terminal
python -m app.jobs.interview --job <fingerprint> --interactive

# Inspect candidate skill gaps against a target role
python -m app.jobs.interview --job <fingerprint> --gaps
```

### Continuous Background Monitor CLI
```powershell
# Run a single scan across all regions within 24h freshness window
python -m app.jobs.monitor --once --region all --hours 24

# Launch continuous daemon (runs every 60 minutes)
python -m app.jobs.monitor --region all --hours 24 --interval 60

# Background launcher with logging
.\scripts\start_monitor.ps1 -Region all -IntervalMinutes 60
```

### Application Tracking & Daily Best Jobs CLI
```powershell
# Display Today's Best Jobs executive summary dashboard
python -m app.application.tracker --report

# List all tracked job applications
python -m app.application.tracker --list

# Filter applications by lifecycle stage
python -m app.application.tracker --list --status reviewing
python -m app.application.tracker --list --status ready_to_apply
python -m app.application.tracker --list --status applied

# Update an application's lifecycle status and candidate notes
python -m app.application.tracker --update-id 1 --new-status applied --notes "Applied on company careers portal"
```

---

## Quickstart

### 1. Clone & Setup Virtual Environment
```powershell
git clone https://github.com/mrchandu1462-ux/job-ai-career-buddy.git
cd job-ai-career-buddy

python -m venv .venv

# On Windows:
.venv\Scripts\activate

# On macOS/Linux:
source .venv/bin/activate
```

### 2. Install Dependencies
```powershell
pip install -r requirements.txt
```

### 3. Configure Email Alerts (Optional)
```powershell
cp .env.example .env
# Edit .env to set JOB_AI_EMAIL_ENABLED, JOB_AI_EMAIL_PROVIDER, etc.
```

### 4. Run Test Suite & Linter
```powershell
python -m pytest -v
python -m ruff check .
```

### 5. Launch Streamlit Dashboard
```powershell
python -m streamlit run app/dashboard.py
```

---

## Project Structure

```text
job-ai/
├── app/
│   ├── application/        # Phase 4 Final: Application intelligence, priority engine, eligibility, cover letter, package
│   ├── career/             # Knowledge base, simulation, learning engine, question bank, notifications, analytics
│   │   └── copilot.py      # Phase 6 Interview Prep Copilot (JD analysis, skill gap, mock engine, readiness, study plan)
│   ├── db/                 # SQLite connection, models, DAO repositories, schema DDL & migrations
│   ├── jobs/               # Discovery, freshness, monitoring service, CLI, adapters, sources, normalizer, digest
│   │   ├── sources/        # Base adapters, career page adapter, RSS feeds, mock test adapter
│   │   │   └── dynamic/    # Dynamic portal adapters (Workday, Greenhouse, base config)
│   │   ├── digest.py       # Daily career digest service & report generator
│   │   ├── watchlist.py    # Configurable semiconductor employer watchlist
│   │   ├── freshness.py    # Deterministic freshness, priority, geography, and attribute extraction
│   │   ├── monitoring_service.py # Fresh job monitor service, deduplication, alert proposals
│   │   ├── scheduler.py    # Continuous daemon loop, state persistence, signal handling
│   │   ├── monitor.py      # CLI entrypoint for automation and scheduled monitoring
│   │   └── interview.py    # CLI entrypoint for Interview Prep Copilot & practice sessions
│   ├── matching/           # Hard filters, relevance scorer, candidate ranker, explainability
│   ├── notifications/      # Final Email & Alert Automation (providers, renderer, deduplication, audit persistence)
│   │   ├── email.py        # Base, Console, Mock, SMTP email providers with TLS and timeouts
│   │   ├── models.py       # EmailMessage, DeliveryResult, EmailPriority models
│   │   ├── renderer.py     # Responsive HTML & clean text templates with human safety disclaimers
│   │   └── service.py      # Email notification dispatcher, deduplication, and retry management
│   ├── profile/            # Pydantic profile & verified fact bank models
│   ├── resume/             # Tailoring engine, ATS scorer, DOCX/PDF exporters & validators
│   ├── config.py           # AppSettings configuration
│   └── dashboard.py        # Streamlit 13-section web interface
├── data/                   # Local SQLite database (git-ignored)
├── docs/                   # Architecture Decision Records (ADRs 0001–0026)
├── profile/                # Candidate profile, fact bank YAML, historical interviews YAML
├── tests/                  # Pytest test suite (295 unit & integration tests)
├── pyproject.toml          # Project configuration & dependencies
├── requirements.txt        # Reproducible dependency manifest
├── .env.example            # Example configuration template for email & scheduler
└── README.md               # Project documentation
```

---

## Testing Baseline

- **Unit & Integration Tests**: 295/295 passing (`pytest -v`)
- **Code Quality**: 100% clean (`ruff check .` with 0 errors / 0 warnings)
- **Database Safety**: Idempotent schema initialization on connect with SQLite WAL mode and foreign keys enabled.
- **Autonomous Submission Policy**: **DISABLED — HUMAN APPROVAL REQUIRED**

