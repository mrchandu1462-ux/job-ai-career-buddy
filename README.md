# Job-AI Career Buddy

A local-first, autonomous-but-human-controlled AI Career Operating System for a 2025 VLSI / Design Verification Engineer candidate.

## Purpose

Job-AI Career Buddy guides semiconductor freshers and engineers through the complete career lifecycle:
**Job Discovery** $\rightarrow$ **7D Matching** $\rightarrow$ **Fact-Grounded Resume Tailoring** $\rightarrow$ **ATS Validation** $\rightarrow$ **Historical Interview Preparation** $\rightarrow$ **Turn-by-Turn Mock Simulation** $\rightarrow$ **Final Timed Assessment** $\rightarrow$ **Readiness Gates** $\rightarrow$ **Preparation Scheduling** $\rightarrow$ **Human Approval** $\rightarrow$ **Confirmed Application Tracking** $\rightarrow$ **Real Interview Debrief & Continuous Learning**.

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
| Job Discovery &   | --------> | Multi-Dimensional Match   | --------> | Fact-Grounded Resume |
| Raw Ingestion     |           | Engine (7 Dimensions)     |           | Generator & ATS Gate |
+-------------------+           +---------------------------+           +----------+-----------+
                                                                                   |
                                                                        +----------v-----------+
                                                                        | ATS-Safe Document    |
                                                                        | Exporters (DOCX/PDF) |
                                                                        +----------------------+
                                              |
+-------------------+           +-------------v-------------+           +----------------------+
| Historical        | --------> | 8-Category Review Pool &  | --------> | Turn-by-Turn Multi-  |
| Question Bank     |           | 10-Step Topic Curriculum  |           | Stage Simulator      |
+-------------------+           +-------------+-------------+           +----------+-----------+
                                              |                                    |
                                +-------------v-------------+                      |
                                | Timed Final Assessment &  | <--------------------+
                                | Remediation Test Engine   |
                                +-------------+-------------+
                                              |
                                +-------------v-------------+
                                | Readiness Calculation     |
                                | & Diagnostic Gate         |
                                +-------------+-------------+
                                              |
                                +-------------v-------------+
                                | Adaptive Prep Schedule &  |
                                | Human Notification Center |
                                +-------------+-------------+
                                              |
                                +-------------v-------------+
                                | Application Lifecycle &   |
                                | Submission Audit Trail    |
                                +-------------+-------------+
                                              |
                                +-------------v-------------+
                                | Real Interview Debrief &  |
                                | Career Learning Loop      |
                                +-------------+-------------+
                                              |
                                +-------------v-------------+
                                | Transparent SQLite Career |
                                | Analytics Dashboard       |
                                +---------------------------+
```

---

## Implemented Features

1. **Dashboard Overview**: Unified command center with live status metrics, pending human approvals, readiness score banner, and priority India tech hub listings.
2. **Fresh Job Monitoring & Alert Engine (Phase 5)**:
   - **24-Hour Deterministic Freshness**: Calculates publication age in hours and groups opportunities into `<6h (Ultra-Fresh)`, `6-24h (Fresh)`, `1-3 Days (Recent)`, `Older`, and `Unknown`. Zero timestamp fabrication.
   - **India + Overseas Geographic Coverage**: Priority semiconductor tech hubs in India (Bengaluru, Hyderabad, Chennai, Pune, Noida, etc.) and global markets (US, UK, Germany, Netherlands, Singapore, Canada, etc.).
   - **Modular Source Adapters**: Pluggable adapter architecture (`SemiconductorCareerPageAdapter`, `FeedJobSourceAdapter`, `MockJobSourceAdapter`) with per-source failure isolation and health audits in `job_source_runs`.
   - **Cross-Source Deduplication**: Deterministic fingerprinting combines multi-source listings into a single canonical record while preserving all source references.
   - **7D Matching & Alert Prioritization**: Leverages candidate Fact Bank and 7D scoring engine to assign **P0** (fresh $<24$h + strong match), **P1** (fresh $<24$h + reasonable match), **P2** (recent 1–3d + strong match), and **P3** alerts.
   - **Alert Deduplication & Human Gating**: Automatically generates proposed email notifications in `PROPOSED` state without alert spam. Strictly zero autonomous application submissions or external communications.
3. **Job Discovery & Matching**: Multi-source ingestion (manual JD paste, career portals), semiconductor classification, deduplication, hard eligibility filters, and 7-dimensional scoring.
4. **Application Tracking & Human Gates**: Status lifecycle tracking (`discovered` $\rightarrow$ `shortlisted` $\rightarrow$ `preparing` $\rightarrow$ `ready_for_review` $\rightarrow$ `approved` $\rightarrow$ `applied` / `failed` / `rejected`) with immutable chronological audit logging.
5. **Fact-Grounded ATS Resumes**: Single-column ATS-safe formatting, ATS score breakdown, adjacent evidence mapping, and export validation for DOCX and PDF formats.
6. **Interview Preparation & Learning**:
   - **Pre-Interview Review Pack**: 8 categorized pools (Must Know, Frequently Asked, Previously Missed, Job-Specific, Company-Specific, Weak Areas, Fundamentals, Advanced).
   - **Structured Learning Mode**: 10-step curriculum with topic breakdown and interactive drills.
   - **Turn-by-Turn Simulator**: Multi-stage interview simulation covering HR, Digital Design, SystemVerilog, UVM, Protocols, Project Deep-Dive, and Debugging.
   - **Real Interview Debrief**: Outcome logging and automatic knowledge loop refinement.
7. **Question Bank**: Full provenance search and batch YAML dataset ingestion.
8. **Final Assessment & Readiness**: Timed mock tests (hidden answers during exam), score breakdown, remediation drill generation, and readiness gates.
9. **Schedule & Notifications**: Adaptive prep milestone generation and human-gated email/calendar proposals (`PROPOSED` state).
10. **Career Analytics**: Transparent database-backed conversion metrics, score distributions, and topic analytics.
11. **Candidate Profile & Fact Bank**: Ground truth verified fact viewer and system status monitor.

---

## CLI & Automation Usage

### Fresh Job Monitoring CLI
The monitoring engine can be executed directly from the terminal or scheduled via cron/Task Scheduler:

```powershell
# Run monitoring across all configured sources and regions
python -m app.jobs.monitor

# Target domestic India tech hubs only
python -m app.jobs.monitor --region india

# Target international overseas markets
python -m app.jobs.monitor --region overseas

# Filter strictly for jobs published within the last 24 hours
python -m app.jobs.monitor --fresh-only

# Dry-run mode: fetch, normalize, score, and rank without database writes or notifications
python -m app.jobs.monitor --dry-run

# Limit candidate jobs evaluated per adapter
python -m app.jobs.monitor --limit 20
```

---

## Local Setup

### 1. Clone & Environment Setup
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

### 3. Run Test Suite & Linter
```powershell
python -m pytest -v
python -m ruff check .
```

### 4. Launch Streamlit Dashboard
```powershell
python -m streamlit run app/dashboard.py
```

---

## Project Structure

```text
job-ai/
├── app/
│   ├── application/        # Application lifecycle & preparation service
│   ├── career/             # Knowledge base, simulation, learning engine, question bank, notifications, analytics
│   ├── db/                 # SQLite connection, models, DAO repositories, schema DDL & migrations
│   ├── jobs/               # Discovery, freshness, monitoring service, CLI, adapters, sources, normalizer
│   │   ├── sources/        # Base adapters, career page adapter, RSS feeds, mock test adapter
│   │   ├── freshness.py    # Deterministic freshness, priority, geography, and attribute extraction
│   │   ├── monitoring_service.py # Fresh job monitor service, deduplication, alert proposals
│   │   └── monitor.py      # CLI entrypoint for automation and scheduled monitoring
│   ├── matching/           # Hard filters, relevance scorer, candidate ranker
│   ├── profile/            # Pydantic profile & verified fact bank models
│   ├── resume/             # Tailoring engine, ATS scorer, DOCX/PDF exporters & validators
│   ├── config.py           # AppSettings configuration
│   └── dashboard.py        # Streamlit 12-section web interface (including Fresh Jobs tab)
├── data/                   # Local SQLite database (git-ignored)
├── docs/                   # Architecture Decision Records (ADRs 0001–0018)
├── profile/                # Candidate profile, fact bank YAML, historical interviews YAML
├── tests/                  # Pytest test suite (125 unit & integration tests)
├── pyproject.toml          # Project configuration & dependencies
├── requirements.txt        # Reproducible dependency manifest
└── README.md               # Project documentation
```

---

## Testing Baseline

- **Unit & Integration Tests**: 125/125 passing (`pytest -v`)
- **Code Quality**: 100% clean (`ruff check .` with 0 errors / 0 warnings)
- **Database Safety**: Idempotent schema initialization on connect with SQLite WAL mode and foreign keys enabled.

