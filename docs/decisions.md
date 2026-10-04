# Architectural Decision Records (ADRs)

## ADR-0001: Local-First Architecture with SQLite
- **Status**: Accepted
- **Context**: The Job AI system processes personal candidate information, fact banks, and parsed job listings. Data privacy, reliability, offline capability, and zero external dependency for core storage are priorities.
- **Decision**: Use a local SQLite database for V1 storage with Pydantic for data validation and schema definitions.
- **Consequences**: Fast local queries, easy backups, zero operational database maintenance overhead.

## ADR-0002: Fact Bank for Strict Anti-Hallucination
- **Status**: Accepted
- **Context**: LLMs tend to embellish or hallucinate experience, metrics, projects, and skills during resume and cover letter generation.
- **Decision**: Enforce a "Fact Bank" system (`facts.yaml`) where every resume bullet point, claimed skill, or cover letter statement must explicitly map to an immutable `fact_id`. The resume generation workflow will follow: `facts -> gap analysis -> select facts -> constrained rewriting -> validation -> human review`.
- **Consequences**: Complete provenance and zero invented claims.

## ADR-0003: Deterministic Hard Eligibility and Scoring
- **Status**: Accepted
- **Context**: Eligibility criteria for freshers (e.g., graduation year, degree requirements, mandatory skills, location preference, work authorization) must be reliable, explainable, and consistent.
- **Decision**: Hard filtering and initial relevance scoring will be strictly deterministic rather than prompt-based. LLMs may later assist in unstructured extraction and explanation generation, but never make raw pass/fail eligibility decisions.
- **Consequences**: Consistent, debuggable, and transparent job ranking.

## ADR-0004: Mandatory Human-in-the-Loop
- **Status**: Accepted
- **Context**: Fully autonomous job application submission risks spamming low-fit roles, generating inaccurate submissions, and violating portal terms of service.
- **Decision**: No automated application submission or unsupervised browser automation. The system assists preparation and tracking; application submission is manual by the candidate.
- **Consequences**: High-quality applications, user agency, and safety.

## ADR-0005: Strict Schema Validation & Extra Forbidden for Profile and Fact Bank
- **Status**: Accepted
- **Context**: Silent ingestion of unvalidated, malformed, or extra unknown fields could cause profile corruption or bypass anti-hallucination fact verification.
- **Decision**: All Pydantic profile and fact models enforce `extra="forbid"`, unique `fact_id` constraints across the bank, explicit verification status (`verified: bool`), and fail loudly upon invalid YAML structure or out-of-bound values.
- **Consequences**: Early detection of configuration errors, zero tolerance for corrupted profile claims.

## ADR-0006: Three-Tier Storage: raw_jobs, normalized_jobs, and applications
- **Status**: Accepted
- **Context**: Job postings need reproducible parsing, deduplication across sources, and isolated human-in-the-loop application tracking.
- **Decision**: 
  1. `raw_jobs` stores original, untampered payloads with content hashes for replayability.
  2. `normalized_jobs` stores structured, cleaned fields with a strict UNIQUE `fingerprint` constraint for deduplication.
  3. `applications` tracks candidate review states (`discovered`, `shortlisted`, `preparing`, `ready_for_review`, `approved`, `applied`, `rejected`, `withdrawn`) with foreign keys to jobs.
  4. Personal candidate data is kept strictly out of the jobs database tables.
- **Consequences**: Complete audit trail, re-parse capability, robust deduplication, and zero privacy leakage into job tables.

## ADR-0007: Immutable Application Audit Events & Notification Foundation
- **Status**: Accepted
- **Context**: State contamination can occur if opening a portal page or generating a resume artifact mistakenly marks an application as "applied". Furthermore, candidates need clear audit proof, timestamps, and notifications for approval and submission outcomes.
- **Decision**:
  1. `application_events` records every discrete lifecycle action (`job_discovered`, `page_opened`, `prepared`, `ready_for_review`, `approved`, `submitted`, `submission_failed`, `status_changed`, `rejected`, `withdrawn`) with full context (timestamps, resume version, reference IDs, and submission evidence).
  2. Opening pages, preparing resumes, or granting approvals NEVER marks an application as `applied`. Only a confirmed manual submission transitions status to `applied` and logs a `submitted` audit event.
  3. `notifications` table captures asynchronous user-facing alerts (`human_approval_required`, `submission_success`, `submission_failed`, `status_changed`).
- **Consequences**: Provable audit history, zero accidental status transitions, and decoupled notification support.

## ADR-0008: Career & Interview Knowledge Base Architecture
- **Status**: Accepted
- **Context**: Candidates accumulate valuable interview history (questions, answers, mock rounds, feedback, weak areas, revision logs) across companies and preparation sessions. This historical knowledge must be preserved and matched to new jobs to power targeted preparation.
- **Decision**:
  1. Maintain 5 core entities: `interview_sessions`, `interview_questions`, `weak_areas`, `preparation_sessions`, and `knowledge_items`.
  2. Every question and knowledge item carries provenance (`source`) and explicit verification state (`verified: bool`). Model-generated answers are not treated as verified facts.
  3. Relational matching links `Job -> Topics/Skills -> Previous Questions -> Weak Areas -> Knowledge Items` for targeted revision.
  4. The system serves learning and preparation only, with zero automated candidate impersonation during live interviews.
- **Consequences**: Persistent career learning repository, zero fact contamination, and structured interview preparation.

## ADR-0009: Provenance-Aware Ingestion & Deterministic Preparation Engine
- **Status**: Accepted
- **Context**: Ingesting preparation material must prevent accidental conversion of AI-generated content into verified ground-truth, avoid duplicate question inflation across mock interviews, and produce explainable preparation plans for target jobs.
- **Decision**:
  1. Ingestion strictly tracks provenance metadata (`source`, `source_type`, `original_reference`). AI-generated items (`source_type == "ai_generated"`) are permanently enforced as `verified: false`.
  2. Deterministic text normalization collapses whitespace, strips punctuation, and matches substantially identical questions, incrementing `times_asked` frequency rather than inserting redundant rows.
  3. The preparation engine calculates deterministic topic priority scores based on: (1) job skills, (2) active weak areas weighted by severity/confidence, (3) previously missed questions, and (4) high-frequency questions.
- **Consequences**: Robust deduplication, transparent topic prioritization, and zero unverified AI claim leakage.

## ADR-0010: Adaptive Assessment, Remediation, and Human-Approved Preparation Scheduling
- **Status**: Accepted
- **Context**: Preparation requires dynamic feedback loops where mock interview mistakes automatically adjust topic confidence, generate focused remediation tests, and formulate multi-day schedules. Furthermore, scheduling and external actions must remain strictly controlled by the candidate.
- **Decision**:
  1. `AdaptiveAssessmentEngine` generates timed mocks (`timed_mock`), final pre-interview assessments (`pre_interview`), and mistake-isolating tests (`remediation`).
  2. Answer submissions dynamically adapt candidate weak areas (adjusting confidence upwards/downwards and marking resolution).
  3. Preparation schedules formulate structured milestone days with `requires_user_approval = true` and remain in an unapproved state until explicit confirmation by the candidate.
- **Consequences**: Adaptive learning loops, automated weak-area updates, and strict human agency for all scheduling actions.

## ADR-0011: Separation of Hard Eligibility Filtering from Deterministic Fact-Grounded Scoring
- **Status**: Accepted
- **Context**: Freshers applying for semiconductor roles must not waste time on ineligible senior postings, incompatible graduation cohorts, or overseas roles without sponsorship. Furthermore, relevance scores must be explainable and strictly computed against verified candidate facts.
- **Decision**:
  1. `HardFilterEngine` executes binary pass/fail checks on graduation year (2025 cohort), experience bounds ($\le 2.0$ yrs), semiconductor role compatibility, and overseas sponsorship allowance.
  2. `JobScoringEngine` computes a deterministic $0-100$ relevance score matching job requirements exclusively against verified Fact Bank entries with itemized reasons (`+`) and gaps (`-`).
  3. Ineligible jobs are flagged and clamped to match score 0 for safety, with detailed failure criteria preserved for transparent auditing.

## ADR-0012: Career Question Bank, Structured Learning, Simulation & Human-Approved Notification Proposals
- **Status**: Accepted
- **Context**: A comprehensive VLSI Career Operating System must provide deep question querying (by company, role, round, topic, frequency, correctness), structured topic curriculum with multi-observation weak area resolution, multi-stage interactive interview simulations, resume project authenticity checks, 17-point consolidated revision packs, and human-approved draft notifications for calendar/email dispatch.
- **Decision**:
  1. `QuestionBankService`: Multi-dimensional filtering, explainable priority scoring (`+35` missed, `+25` repeated, `+20` job skills, `+20` weak areas, `+15` company, `+10` role, `+10` fundamentals), and 8-category review pool generation (Must Know, Frequently Asked, Previously Missed, Job-Specific, Company-Specific, Weak Areas, Fundamentals, Advanced).
  2. `LearningModeService`: Provides structured subtopics (Async FIFO, UVM, SystemVerilog OOP, SVA, AXI, CDC, CRV, Digital Design), practice evaluations, and multi-observation confidence updates requiring multiple successful attempts to mark mastered.
  3. `InterviewSimulationEngine` & `ProjectAuthenticityChecker`: Multi-stage simulation (HR -> Digital Design -> SystemVerilog -> UVM -> Protocol -> Project Deep Dive -> Debugging -> Behavioral) and deep-dive resume project defense questions to verify hands-on authenticity.
  4. `InterviewPackGenerator`: Synthesizes authoritative 17-component interview preparation packs.
  5. `ScheduleNotificationService`: Generates draft notifications (`PROPOSED` status) requiring explicit human approval gates before any external dispatch.

## ADR-0013: Fact-Grounded Resume Tailoring Engine, ATS Scoring & Hard Quality Gates
- **Status**: Accepted
- **Context**: Tailoring resumes for semiconductor verification freshers requires strict adherence to factual integrity: zero hallucination of metrics (coverage percentages, bug counts), tools, protocols, or company experience. Additionally, resumes must pass ATS parsers (single-column, standard headings, no tables/graphics/icons) with an explainable quality target ($\ge 80/100$) and connect to project defense interview questions.
- **Decision**:
  1. `FactIntegrityValidator`: Audits all resume bullet points and claims against verified `FactBank` entries. Rejects unverified or unknown fact IDs and flags fabricated metric patterns.
  2. `ATSScorer`: Computes a deterministic multi-dimensional score (30% Technical keywords, 30% Required skills coverage, 20% Project relevance, 10% Role alignment, 10% Parser safety). Enforces an 80-point hard quality gate (`quality_gate_met = score >= 80.0 and fact_integrity == "PASS"`). If a profile cannot reach 80, the system reports `ATS TARGET NOT REACHED` with explicit missing gaps rather than fabricating keywords.
  3. `ATSResumeFormatter`: Renders ATS-safe Markdown and Plaintext formats with standard sections and zero parser-breaking elements.
  4. `ResumeTailoringEngine` & `ResumeRepository`: Synthesizes versioned resumes (`v1`, `v2`, etc.) in SQLite without overwriting past iterations.
  5. `ResumeCareerIntegration`: Generates deep-dive project defense questions for every claimed project via `ProjectAuthenticityChecker` and attaches tailored resumes to `applications` with `PREPARED` / `READY_FOR_REVIEW` audit events without premature `APPLIED` transitions.

## ADR-0014: Job Discovery Sources, Active Status Verification, 7D Explainable Scoring & Application Packaging
- **Status**: Accepted
- **Context**: A dependable Career Operating System must continuously discover semiconductor opportunities across diverse sources, verify active status using provenance signals, deduplicate postings deterministically, classify specialized semiconductor roles, compute an itemized 7-dimension match score against candidate verified facts, and prepare a consolidated Application Package (linking tailored resumes, ATS scores, interview intelligence, and preparation schedules) governed by strict human approval gates.
- **Decision**:
  1. `JobSource` Abstraction & Registry: Modular architecture (`ManualJobSource`, `CompanyCareerSource`, `StructuredJobBoardSource`, `JobSourceRegistry`) enabling decoupled multi-source discovery (`search()`, `fetch_job()`, `normalize()`, `verify_active()`).
  2. `ActiveStatusVerifier`: Multi-tier verification distinguishing `ACTIVE`, `EXPIRED`, `ARCHIVED`, and `UNKNOWN` based on career portal signals, content expiration checks, URL reachability, and freshness timestamps. Never assumes active without verification evidence.
  3. `RoleClassifier`: Categorizes postings into `DESIGN_VERIFICATION`, `FUNCTIONAL_VERIFICATION`, `ASIC_VERIFICATION`, `SOC_VERIFICATION`, `RTL_DESIGN`, `VERIFICATION_INTERN`, `RTL_INTERN`, `VLSI_INTERN`, `GRADUATE_ENGINEER_TRAINEE`, and `OTHER` with explainable relevance scoring and justification.
  4. Itemized 7-Dimension Match Scoring (`JobScoreBreakdown7D`):
     - Role Relevance (20 pts)
     - Technical Skill Match (25 pts, classifying into `VERIFIED_MATCH`, `PARTIAL_MATCH`, `MISSING`, `UNKNOWN`)
     - Project Alignment (20 pts)
     - Fresher / Experience Fit (10 pts)
     - Tech Hub Location Preference (10 pts)
     - Interview Knowledge Availability (10 pts)
     - Freshness & Source Provenance (5 pts)
     - Hard gate: Ineligible roles clamped to 0 with explicit disqualification explanations.
  5. `ApplicationPackage` & `JobDiscoveryPipeline`: Assembles complete packages unifying Job Data, Eligibility, 7D Scoring, Tailored Resume candidate, ATS Score, Fact Integrity, Question Review Pool, Pre-Interview Test Drill, and Preparation Schedule.
  6. Human Approval & Safety Invariants: Status transitions strictly follow `DISCOVERED` -> `PREPARING` -> `READY_FOR_REVIEW` -> `APPROVED` -> `APPLIED`. Status only transitions to `APPLIED` upon confirmed manual submission. Zero autonomous external form submissions, emails, or calendar modifications.

## ADR-0015: ATS Resume Quality Rule, Truthful Adjacent Evidence & Application Eligibility Gates
- **Status**: Accepted
- **Context**: Tailored resume generation must maximize truthful ATS relevance (target score $\ge 80/100$) using only verified candidate facts. It must never fabricate skills or metrics to artificially inflate scores. Where direct evidence is missing, the system must discover truthful adjacent candidate evidence (e.g., AXI4 for bus protocols, SVA for formal properties, Async FIFO for CDC) or explicitly report unsupported requirements as skill gaps. Resumes must remain immutable versioned artifacts, and an application eligibility gate must ensure all safety constraints are satisfied before review.
- **Decision**:
  1. `ATSScorer` Enhancements:
     - Itemized 5-dimension breakdown: Technical Keyword Density (30%), Required Skills Coverage (30%), Project Relevance (20%), Role Alignment (10%), Parser Safety (10%).
     - Adjacent domain evidence mapping: Evaluates non-matching requirements against verified candidate competencies without converting assumptions into facts.
     - Unsupported requirement auditing: Explicitly enumerates JD requirements lacking direct candidate evidence.
     - Gap disclosure: If score $<80$, reports `ATS TARGET NOT REACHED` with explicit missing skills and required candidate evidence.
  2. `ResumeTailoringEngine` Versioning & Immutability:
     - Automatically auto-increments version numbers (`v1`, `v2`, etc.) per job target, guaranteeing historical versions are never overwritten.
     - Implements `check_application_eligibility()` validating that:
       a. Fact integrity = PASS (all claims map to verified `FactBank` entries)
       b. ATS score $\ge 80.0$ OR explicit truthful gap explanations are recorded
       c. Zero unsupported claims or fabricated metrics exist
       d. Human candidate review is required before external submission.
  3. `ATSResumeFormatter`: Renders parser-safe single-column Markdown and Plaintext formats with zero tables, columns, textboxes, icons, or decorative symbols.

## ADR-0016: ATS-Safe Resume Export Subsystem, End-to-End Application Pipeline & Submission Audit Trail
- **Status**: Accepted
- **Context**: A complete career application lifecycle requires generating production-ready, parser-safe file artifacts (DOCX, PDF, Plaintext, Markdown), validating exported content against verified candidate claims without corruption or metric fabrication, unifying job matching with interview prep (cleanly separating verified historical questions from practice drills), enforcing human review gates, and establishing an immutable audit trail for confirmed submissions and failed attempts.
- **Decision**:
  1. `ATS-Safe Resume Export Subsystem` (`app/resume/export/`):
     - `DOCXResumeExporter`: Produces single-column, standard 1-inch margin, clean typography `.docx` files without tables, textboxes, shapes, graphics, or icons.
     - `PDFResumeExporter`: Produces searchable, extractable, single-column PDF documents using ReportLab Flowables without multi-column layouts or raster backgrounds.
     - `ResumeExportValidator`: Extracts text from exported files via `python-docx` and `pypdf`, auditing that candidate identity, contact info, professional summary, technical skills, project claims, and education match the validated model with zero introduced claims or fabricated metrics.
     - `ExportValidationReport`: Returns `status: PASS / FAIL` and sets `is_export_validated = True` only upon passing all checks.
  2. `End-to-End Application Pipeline` (`app/application/`):
     - `ApplicationMatcher`: Computes explainable 7D relevance matches with itemized positive factors, skill gaps, and adjacent evidence mappings.
     - `ApplicationPipelineService`:
       - Shortlists discovered jobs (`SHORTLISTED`).
       - Prepares full `ApplicationPackageDetail` linking exact tailored resume version, ATS score ($\ge 80$), validated DOCX/PDF export artifacts, 8-category question pool (distinguishing verified historical questions from generated practice drills), final assessment, readiness scoring, and preparation schedule milestones.
       - Dispatches `HUMAN_APPROVAL_REQUIRED` notification and sets status to `READY_FOR_REVIEW`.
       - Manages candidate review decisions (`APPROVE`, `REJECT`, `EDIT`).
       - Enforces submission audit boundaries: `record_submission()` transitions status to `APPLIED` only with confirmed reference ID and evidence, dispatching `SUBMISSION_SUCCESS`. `record_submission_failure()` records failures with retry guidance without falsely claiming application was submitted.
- **Consequences**: Deterministic, auditable, ATS-compliant application pipeline providing end-to-end provenance, pristine file exports, and uncompromising candidate control.

## ADR-0017: Phase 6 Career Buddy Dashboard & Unified Career Operating System Interface
- **Status**: Accepted
- **Context**: The user requires a personal AI Career Buddy desktop interface that surfaces all backend subsystems (discovery, explainable matching, ATS resume tailoring, export validation, historical question banks, structured learning mode, multi-stage turn-by-turn simulation, 9-section pre-interview final assessments, readiness gates, preparation schedules, external scheduling proposals, manual submission audit, and transparent career analytics) within a clean, reactive Streamlit dashboard while keeping business logic strictly inside backend service classes.
- **Decision**:
  1. `Career Analytics Service` (`app/career/analytics.py`):
     - Computes transparent career metrics directly from SQLite database without fabricating statistics.
     - Calculates application conversion rate, resume ATS distribution, question topic frequency, frequently missed questions, assessment history, and weak area breakdown.
     - Gracefully reports "Insufficient data" when database records are empty.
  2. `Career Buddy Streamlit Dashboard` (`app/dashboard.py`):
     - Implements 12 comprehensive navigation views:
       1. **Dashboard**: High-level metrics, DV readiness gauge, critical weak areas, top India tech hub listings, and pending human actions.
       2. **Jobs**: Ingestion form, 7D match breakdown, required vs matching skills, truthful adjacent evidence mapping, and actions (View, Shortlist, Prepare, Ignore).
       3. **Applications**: Complete lifecycle tracking, human review gates (`APPROVE`, `REJECT`, `EDIT`), confirmed manual submission box with reference ID/proof (sets `APPLIED`), and submission failure logging (`FAILED`).
       4. **Resumes**: Tailored resume inspect view, ATS score (30/30/20/10/10 breakdown), fact integrity audit, DOCX/PDF export generation, post-export validation badges (`PASS`/`FAIL`), and validated download buttons.
       5. **Interview Preparation**: Complete 8-Category Review Pack (Must Know, Frequently Asked, Previously Missed, Job-Specific, Company-Specific, Weak Areas, Fundamentals, Advanced), 10-step Structured Learning Mode, and turn-by-turn Multi-Stage Interview Simulator.
       6. **Question Bank**: Multi-criteria search, strict visual separation of Verified Historical Questions from Generated Practice Drills, provenance badges, and YAML dataset batch ingestion.
       7. **Final Assessment**: Timed mock generator (45m), 9-section pre-interview assessment (60m) with hidden answers during execution, detailed scoring, and targeted remediation test generator for missed questions.
       8. **Readiness**: Overall readiness percentage, topic mastery progress bars, readiness level gates (`READY`, `BORDERLINE`, `NOT READY`), and weak topic alerts.
       9. **Schedule**: Adaptive interview preparation plan with customizable target dates and daily milestones.
       10. **Email & Notifications**: Staged proposal review cards (`PROPOSED`) requiring explicit human approval, and notification action center (no autonomous external communication).
       11. **Career Analytics**: Real SQLite distributions, ATS trends, topic frequencies, and missed questions.
       12. **Settings**: Candidate profile parameters and verified Fact Bank ground truth items.
  3. `Architectural Boundary`:
     - Zero business logic or raw SQL queries in UI components; all interactions invoke `ApplicationPipelineService`, `JobDiscoveryPipeline`, `HistoricalInterviewPipeline`, `QuestionBankService`, `LearningModeService`, `InterviewSimulationEngine`, `CareerAnalyticsService`, `DOCXResumeExporter`, `PDFResumeExporter`, and `ResumeExportValidator`.
- **Consequences**: Provides an intuitive, interactive, reliable personal AI Career Buddy adhering to non-negotiable safety rules and candidate factual integrity.

## ADR-0018: Fresh Job Monitoring & Alert Engine (Phase 5)
- **Status**: Accepted
- **Context**: The Career Operating System requires proactive discovery and continuous monitoring of freshly released semiconductor / VLSI opportunities ($\le 24$ hours) across India priority hubs and Overseas markets, ranking them using the authoritative 7D candidate matching engine, deduplicating cross-source listings, and proposing human-gated notifications without fabricating posting timestamps or auto-submitting applications.
- **Decision**:
  1. `Deterministic 24-Hour Freshness Engine` (`app/jobs/freshness.py`):
     - Calculates publication freshness age in hours and assigns deterministic tiers: `FRESH_0_6_HOURS`, `FRESH_6_24_HOURS`, `RECENT_1_3_DAYS`, `OLDER`, and `UNKNOWN`.
     - Zero timestamp fabrication: unverified or relative phrases without numeric evidence evaluate strictly to `UNKNOWN` (`freshness_age_hours = None`, `confidence = 0.0`).
     - Extracts workplace arrangement (`REMOTE`, `HYBRID`, `ONSITE`, `UNKNOWN`) and visa sponsorship availability (`AVAILABLE`, `NOT_AVAILABLE`, `CITIZEN_OR_PR_ONLY`, `UNKNOWN`) strictly grounded in JD text.
  2. `Modular Source-Adapter Architecture` (`app/jobs/sources/adapters.py`):
     - `JobSourceAdapter` abstract base class defining `fetch_jobs()`, `adapter_name`, `source_category`, `supports_region()`, `supports_freshness()`, and `health_status()`.
     - Implementations include `SemiconductorCareerPageAdapter`, `FeedJobSourceAdapter`, and `MockJobSourceAdapter`.
     - Complete failure isolation: adapter timeouts or remote HTTP/network errors are caught, logged, and audited in `job_source_runs` without interrupting other sources.
  3. `Cross-Source Deduplication & Alert Engine` (`app/jobs/monitoring_service.py`):
     - Canonical job fingerprinting merges multi-source postings into single records while accumulating all source references.
     - Reuses existing 7D scoring engine (`JobScoringEngine`) and role classifier (`RoleClassifier`) to evaluate candidate fit and assign priority levels:
       - **P0**: Published $< 24$h with strong candidate match ($\ge 75\%$).
       - **P1**: Published $< 24$h with reasonable candidate match ($\ge 60\%$).
       - **P2**: Published 1–3 days with strong match ($\ge 78\%$).
       - **P3**: Older or research opportunities.
     - Alert deduplication: checks `job_alerts` before creating notification proposals to prevent alert spam.
     - Creates human-reviewable proposals in `PROPOSED` status (`ScheduleNotificationService`), preserving the strict rule: zero autonomous application submissions or external dispatches.
  4. `CLI and Dashboard Integration` (`app/jobs/monitor.py`, `app/dashboard.py`):
     - CLI entrypoint supporting `--region (all|india|overseas)`, `--fresh-only`, `--dry-run`, and `--limit`.
     - Dedicated `🔥 2. Fresh Jobs` dashboard with live freshness counters, last run audit metrics, on-demand execution trigger, multi-filters, and action buttons.
- **Consequences**: Enables continuous, automated, auditable, and fact-grounded fresh opportunity monitoring across domestic and global semiconductor markets under 100% candidate control.

## ADR-0019: Fresh Job Intelligence, 24-Hour Tracking, 8D Priority Scoring & Notification Engine
- **Status**: Accepted
- **Context**: The Career Buddy requires continuous discovery of newly released jobs in India tech hubs and Overseas semiconductor markets with granular freshness tiers (<=1h, <=3h, <=6h, <=12h, <=24h, 1–3d, 3–7d, >7d, UNKNOWN), an explainable 8-dimensional ranking score (0–100), watchlist company tracking, daily job digest generation, and human-gated notification proposals with anti-duplication guards.
- **Decision**:
  1. `Granular Freshness & Timestamp Confidence` (`app/jobs/freshness.py`):
     - Calculates granular 24-hour freshness buckets (`FreshnessBucket`) and timestamp confidence (`FreshnessConfidence`: `HIGH`, `MEDIUM`, `LOW`, `UNKNOWN`).
     - Zero timestamp fabrication: unverified or relative strings yield `UNKNOWN` with `LOW` confidence and are never falsely classified as <= 24h.
  2. `International Visa Sponsorship Categorization` (`app/jobs/freshness.py`):
     - Categorizes overseas opportunities into `SPONSORSHIP_CONFIRMED`, `SPONSORSHIP_POSSIBLE`, `SPONSORSHIP_UNKNOWN`, or `SPONSORSHIP_NOT_SUPPORTED` with zero fabrication.
  3. `Explainable 8-Dimensional Fresh Job Priority Score` (`app/jobs/freshness.py`, `FreshJobPriorityScore`):
     - Itemized 0–100 score: Freshness (25%), Technical Match (25%), Role Match (15%), Project Relevance (10%), Fresher Fit (10%), Location/Eligibility (5%), Company Confidence (5%), Application Accessibility (5%).
     - Categories: `CRITICAL` (Fresh <= 24h & Score >= 88), `HIGH` (Fresh <= 24h & Score >= 75), `MEDIUM` (>= 60), `LOW` (< 60), `EXPIRED_STALE` (> 7 days).
     - Assigns the special `🚨 FRESH 24H MATCH` badge for high-priority opportunities.
  4. `Company Watchlist & Daily Digest Engine` (`app/jobs/watchlist.py`, `app/jobs/digest.py`):
     - `CompanyWatchlistService` tracks top semiconductor and EDA firms (NVIDIA, Qualcomm, AMD, Intel, Synopsys, Cadence, Apple, Arm, MediaTek, TI, etc.) with 24-hour fresh job counting.
     - `DailyJobDigestService` aggregates statistical summaries, Top 5 ranked opportunities, and separate India vs Overseas sections with CLI support (`python -m app.jobs.digest`).
  5. `Pluggable Scanner & CLI Engine` (`app/jobs/scanner.py`, `app/jobs/scan.py`):
     - `FreshJobScanner` provides resilient multi-source scanning with failure isolation, deduplication, 8D ranking, and notification proposal generation.
     - CLI command `python -m app.jobs.scan --region (all|india|overseas) --hours 24 --dry-run` runs independently of the Streamlit dashboard.
  6. `Human Approval Safety Gate`:
     - Notifications are created in `PROPOSED` status (`ScheduleNotificationService`), deduplicated by `job_id`, and NEVER submitted or dispatched autonomously.
- **Consequences**: Ensures rapid discovery of verified fresh opportunities, provides complete explainability for ranking, enforces strict zero fabrication, and maintains 100% human agency.

## ADR-0020: Production Scanner Lock & Concurrency Control (Phase 2)
- **Status**: Accepted
- **Context**: Running concurrent or overlapping job scans (e.g. multiple CLI executions or simultaneous dashboard and scheduled scans) causes duplicate ingestion attempts, redundant notification proposals, database file contention, and unnecessary load on external job sources. A deterministic, crash-resilient lock mechanism is needed to ensure single-instance scan execution.
- **Decision**:
  1. **Lock Mechanism & Schema**:
     - Dedicated SQLite table `scanner_locks` with columns:
       - `lock_name TEXT PRIMARY KEY` (e.g., `'fresh_job_scanner'`)
       - `owner TEXT NOT NULL`
       - `acquired_at TEXT NOT NULL` (ISO-8601 UTC timestamp)
       - `lease_seconds INTEGER NOT NULL`
  2. **Lock Ownership**:
     - Deterministic and traceable owner identifier formatted as `{os.getpid()}-{datetime.now(UTC).isoformat()}`.
  3. **Lease Duration**:
     - Explicit lease duration of `300 seconds` (5 minutes).
  4. **Stale Lock Recovery Policy**:
     - A lock is considered stale if and only if `now(UTC) - acquired_at > timedelta(seconds=lease_seconds)`.
     - When attempting acquisition on an existing lock:
       - If active (`age <= lease_seconds`): acquisition is rejected (`False`).
       - If expired (`age > lease_seconds`): the lock is recovered atomically by updating `owner`, `acquired_at = now(UTC)`, and `lease_seconds`, returning `True`.
  5. **Acquisition & Release Behavior**:
     - `acquire_scanner_lock(lock_name, owner, lease_seconds=300)`: Attempts atomic `INSERT`; on `IntegrityError`, inspects timestamp against lease duration.
     - `release_scanner_lock(lock_name, owner)`: Executes `DELETE FROM scanner_locks WHERE lock_name = ? AND owner = ?`. An owner mismatch guarantees that a process cannot accidentally release another active scanner's lock.
  6. **Scanner Execution Lifecycle & Exception Safety**:
     - `FreshJobScanner.scan()` acquires the lock before query execution and wraps the entire scanning, source iteration, and report generation in a `try ... finally` block.
     - The `finally` block guarantees release under all circumstances: clean completion, adapter exceptions, unexpected runtime crashes, or dry-run execution.
  7. **CLI Integration**:
     - `app/jobs/scan.py` catches `RuntimeError` on lock acquisition failure, displays a clean notice, and exits gracefully without traceback.
  8. **Production Mock Protection**:
     - `FreshJobScanner` strictly forbids `MockJobSourceAdapter` during initialization and adapter registration unless `allow_mock=True` is explicitly declared.
- **Consequences**: Deterministic single-scan execution, elimination of race conditions, robust crash recovery via bounded lease timeouts, and clean release guarantees.

## ADR-0021: Phase 3 - Continuous 24-Hour Job Monitor Scheduler
- **Status**: Accepted
- **Context**: Automated 24-hour job monitoring is required to regularly scan for newly posted semiconductor / VLSI opportunities (India hubs + overseas markets) every hour without manual CLI triggers, while adhering strictly to zero-fabrication, robust locking, network timeout safety, and human-gated approval policies.
- **Decision**:
  1. **Daemon Architecture (`app.jobs.scheduler` & `app.jobs.monitor`)**: `ScannerDaemon` orchestrates automated job monitoring by delegating execution to `FreshJobScanner`. It preserves zero duplication of scanner business logic.
  2. **Hourly Monitoring & 24-Hour Freshness**: By default, the daemon runs `FreshJobScanner` immediately upon startup and every 60 minutes thereafter (`DEFAULT_INTERVAL_MINUTES = 60`), searching within the 24-hour freshness window (`hours=24.0`).
  3. **Graceful Shutdown**: Intercepts SIGINT and SIGTERM signals, completes the current scan cycle cleanly, guarantees scanner lock cleanup via the `try ... finally` release mechanism in `FreshJobScanner`, closes database connections, and records shutdown state.
  4. **State Persistence**: A dedicated `monitor_state` key-value table in SQLite persists execution timestamps (`last_cycle_started_at`, `last_cycle_completed_at`, `last_successful_scan_at`, `last_failed_scan_at`, `next_cycle_at`), cycle statistics (`cycles_completed`, `cycles_failed`, `consecutive_failures`), PID, and latest scan discovery counts.
  5. **Network Timeout Hardening**: All external adapter operations enforce an explicit finite timeout (`FETCH_TIMEOUT_SECONDS = 30` / `timeout_seconds <= 30`), ensuring network operations cannot block the daemon indefinitely.
  6. **UI Integration**: Exposes the daemon state in the Streamlit Dashboard (Tab 6: Monitor Daemon), presenting status (`🟢 MONITOR ACTIVE` / `🔴 MONITOR STOPPED`), cycle metrics, and 'Start', 'Stop', and 'Run Once' action triggers without embedding scheduler business logic in the UI.
  7. **Failure Resilience & Lock Contention**: Scan exceptions increment failure metrics and persist error diagnostics without crashing the daemon loop. Lock contention (e.g. another concurrent scan process) skips the cycle cleanly.
  8. **Notification Deduplication & Zero Autonomous Applications**: Deterministic fingerprinting prevents spamming repeated notifications for jobs discovered on consecutive hourly runs. The monitor creates internal notification proposals in `PROPOSED` status only; autonomous submissions, resume uploads, or form autofill remain strictly forbidden.
- **Consequences**: Provides dependable, continuous background tracking of fresh semiconductor job opportunities with robust crash resilience, verified zero-fabrication metrics, and complete human-in-the-loop safety.

## ADR-0022: Phase 4 - Dynamic Career Portal Synchronization (Workday & Greenhouse)
- **Status**: Accepted
- **Context**: Semiconductor and hardware employers (e.g., Qualcomm, Micron, NXP, Synopsys, AMD, Broadcom, SiFive, Tenstorrent, Groq, Rivos) publish engineering opportunities on dynamic, JavaScript-heavy career systems such as Workday and Greenhouse. Synchronizing with these portals requires structured extraction, polite request pacing, bounded timeouts, resilient error handling, anti-bot isolation, cross-source deduplication, and zero publication date fabrication.
- **Decision**:
  1. **Dynamic Portal Adapter Architecture (`app/jobs/sources/dynamic`)**:
     - `DynamicPortalAdapter`: Abstract base adapter encapsulating configuration, retry execution, polite rate limiting, and structured health tracking.
     - `DynamicPortalConfig`: Configurable parameters (`request_timeout_sec`, `page_timeout_sec`, `max_retries`, `backoff_factor`, `request_delay_sec`, `max_jobs_per_source`, `enabled`).
     - `WorkdayCareerAdapter`: Normalizes Workday CXS API / portal payloads (requisition IDs, titles, company, locations, hybrid/onsite status, canonical URLs).
     - `GreenhouseCareerAdapter`: Normalizes Greenhouse Boards API schemas (job IDs, offices, absolute application URLs, technical content).
     - Integrates seamlessly into the existing `FreshJobScanner` pipeline without duplicating scoring, matching, or storage logic.
  2. **Timestamp Integrity & Zero-Fabrication Policy**:
     - Explicit ISO-8601 timestamps and valid machine-readable epoch dates are preserved with high confidence.
     - Ambiguous, relative, or unverified date strings (e.g., "Posted Today", "Posted Yesterday", "Active", "Just Posted", or page order) are strictly normalized to `None` / `FreshnessStatus.UNKNOWN`.
     - Non-timestamped dynamic listings are never classified as $\le 24$h fresh matches.
  3. **Browser Automation & Network Isolation**:
     - Automation is strictly isolated within the dynamic source adapters.
     - Every network request or page navigation enforces finite timeouts ($\le 30$ seconds, bounded by `FETCH_TIMEOUT_SECONDS`).
     - No scraping or browser logic is embedded within Streamlit or the user interface layer.
  4. **Polite Request Pacing & Exponential Backoff**:
     - Enforces configurable inter-request delays (`request_delay_sec`) to prevent aggressive crawling.
     - `execute_with_retry` applies bounded exponential backoff on transient network faults (`max_retries <= 3`), preventing infinite loops or portal flooding.
  5. **Anti-Bot & Blocked Source Isolation**:
     - When a career portal challenges automation (e.g., HTTP 403, Cloudflare, CAPTCHA), a `BlockedSourceError` is raised.
     - The scanner records the source failure gracefully without crashing the overall scan cycle or impacting other healthy source adapters.
     - No evasive anti-bot techniques, credentials bypass, or CAPTCHA solving are attempted.
  6. **Cross-Source Deduplication & Alert Idempotency**:
     - Employs canonical deterministic fingerprinting (`generate_job_fingerprint(company, title, location)`).
     - Opportunities discovered across multiple portals (e.g. Workday and Greenhouse) or during consecutive hourly cycles resolve to a single normalized record and do not trigger duplicate notification proposals.
  7. **Mandatory Human-in-the-Loop Approval & Zero Autonomous Applications**:
     - Discovered dynamic portal jobs generate notification proposals in `PROPOSED` status only.
     - Autonomous form submission, resume transmission, or credentialed portal interaction remains strictly forbidden.
- **Consequences**: Enables robust, rate-limited ingestion of fresh opportunities from major semiconductor career portals while preserving 100% timestamp veracity, crash isolation, and candidate governance.

## ADR-0023: Phase 5 - Smart Career Intelligence, Watchlists & Alerts
- **Status**: Accepted
- **Context**: Transforming Job-AI from a passive discovery/monitoring scanner into an active, intelligent career companion requires understanding the candidate's exact profile (2025 Electrical/Electronics graduate with VLSI/UVM training), scoring roles deterministically across multiple dimensions, managing a prioritized company watchlist, delivering actionable explainable alerts without spam, generating structured daily career digests, detecting material job updates, and maintaining strict safety gates.
- **Decision**:
  1. **Structured Candidate Profile & Role Hierarchy (`app/profile/models.py`, `profile/profile.yaml`)**:
     - Explicit candidate target definitions partitioned into:
       - **Tier 1 (Core Target)**: Design Verification Engineer, Functional Verification Engineer, ASIC Verification Engineer, SoC Verification Engineer.
       - **Tier 2 (Secondary Target)**: RTL Design Engineer, Verification Intern, RTL Design Intern, VLSI Intern.
       - **Tier 3 (Entry/Graduate)**: Graduate Engineer Trainee (GET), Semiconductor Graduate Engineer roles.
       - **Tier 4 (Generic/Adjacent)**: Generic engineering roles only when verified semiconductor/VLSI relevant.
     - Hard rejection of unrelated software, full-stack, generic web, BPO, customer support, or non-semiconductor roles.
  2. **Location Intelligence & Visa Disambiguation**:
     - **India Tier 1 Tech Hubs**: Bengaluru, Hyderabad, Chennai (scored with highest location priority).
     - **India Tier 2 Tech Hubs**: Pune, Noida, Gurugram, Ahmedabad, Mysuru, Kochi, Mumbai/NCR.
     - **Overseas Priority Markets**: USA, Canada, UK, Germany, Netherlands, Singapore, Taiwan, Japan, South Korea, Ireland, Australia, UAE, France, Sweden, Switzerland.
     - **Visa & Work Authorization Evaluation**: Overseas postings are deterministically scanned for explicit negative sponsorship indicators ("no sponsorship", "citizenship required", "must have existing authorization"). If the candidate requires visa sponsorship and the role explicitly denies it, the listing is marked `is_eligible = False`. Sponsorship is never assumed when unstated.
  3. **Configurable Company Watchlist (`app/jobs/watchlist.py`, `app/db/repository.py`)**:
     - Persistent database storage with enable/disable states, priority assignments (Tier 1 / Tier 2 / Tier 3 / Standard), and dynamic additions/removals.
     - Default seed populated with 28+ leading semiconductor employers (NVIDIA, AMD, Intel, Qualcomm, Texas Instruments, Arm, Broadcom, MediaTek, Synopsys, Cadence, Siemens EDA, Marvell, Micron, Samsung Semiconductor, Apple, Google Hardware, Microsoft Silicon, NXP, Infineon, STMicroelectronics, Renesas, Analog Devices, Microchip, Bosch, L&T Semiconductor Technologies, Tessolve, eInfochips, HCLTech, Wipro VLSI, SiFive, Tenstorrent, Groq, Rivos).
  4. **Explainable Smart Matching & Multi-Dimensional Scoring Engine (`app/matching/scorer.py`, `app/matching/filters.py`)**:
     - Deterministic 7-D fit evaluation (Role Fit, Skills Fit, Experience Fit, Location Fit, Degree Fit, Tooling Fit, Work Authorization Fit).
     - 8-D Priority Scoring combines match score, verified freshness, watchlist status, India/Overseas alignment, and direct application availability.
     - Hard filter engine disqualifies Senior/Staff/Lead/Architect roles (>2.0 yrs required) for entry-level candidates.
     - Every match generates deterministic score explanations with positive signals (`+`) and risk gaps (`-`).
  5. **Match Classification Categories (`JobPriorityCategory`)**:
     - **CRITICAL**: Exceptional role fit + verified freshness <=24h + top tier company/location (Score >= 88).
     - **HIGH**: Strong DV/VLSI match and realistic fresher eligibility (Score 75–87.9).
     - **GOOD**: Relevant but with moderate limitations (Score 60–74.9).
     - **WATCHLIST**: Promising employer listing requiring further review.
     - **LOW**: Sub-threshold matching scores (<60).
     - **REJECTED**: Failed hard eligibility filters (senior roles, unrelated software, visa mismatch).
  6. **Smart Alert Proposal Engine & Configurable Alert Modes (`AlertMode`)**:
     - Configurable modes: `CRITICAL_ONLY`, `HIGH_AND_CRITICAL` (default), `ALL_MATCHED`, `WATCHLIST_COMPANIES`, `DAILY_DIGEST`, `HOURLY_CRITICAL`.
     - Internal alert proposals are recorded in `notification_proposals` in `PROPOSED` status.
     - Repeated scans for the same listing are strictly deduplicated and suppressed.
     - **Material Change Re-Alerting**: Substantial payload updates (e.g. expanded technical description $>80$ chars and new direct application link) trigger an updated proposal with `[MATERIAL UPDATE]` prefix (capped at 3 re-alerts).
  7. **Daily Career Intelligence Digest (`app/jobs/digest.py`)**:
     - `DailyDigestService` aggregates fresh $\le 24$h jobs, breakdown by region (India/Overseas), critical/high counts, top 5 prioritized opportunities, and rejection metrics.
     - Generates structured Markdown digests and scheduled notification proposals for human candidate review.
  8. **Safety & Zero-Fabrication Enforcement**:
     - Unverified or relative timestamps remain `UNKNOWN` (never treated as $\le 24$h).
     - Autonomous job applications remain strictly prohibited.
     - Human review and manual approval gate remain mandatory across all interfaces (CLI, Scheduler, Streamlit Dashboard).
- **Consequences**: Provides comprehensive, explainable career intelligence tailored precisely to a VLSI/DV entry-level engineer with zero noise, zero spam, zero timestamp fabrication, and 100% human oversight.

## ADR-0024: Phase 6 - Interview Prep Copilot & Tailored Practice Generator
- **Status**: Accepted
- **Context**: Preparing a 2025 VLSI / Design Verification engineer for high-stakes technical interviews requires converting discovered and matched job opportunities into targeted, provenance-grounded interview preparation. The system must perform deterministic JD analysis, evaluate skill gaps truthfully without inventing experience, generate multi-level topic roadmaps, maintain a structured question bank, execute interactive mock interviews with constructive feedback, track candidate weaknesses over time, compute deterministic readiness scores, and build personalized study plans—all while strictly prohibiting autonomous applications and unverified claims.
- **Decision**:
  1. **Job-Specific Interview Profile (`InterviewPreparationProfile` in `app/career/copilot.py`)**:
     - Automatically synthesized from normalized job records, JD requirements, and candidate verified facts.
     - Tracks target skills, required skills, preferred skills, identified skill gaps, prioritized topics, question sets, readiness evaluations, and study plans.
  2. **Deterministic JD Analysis Engine (`JDAnalysisEngine`)**:
     - Extracts technical skills (SystemVerilog, UVM, Verilog, SVA, AXI, AHB/APB, CDC, FIFO, Memory, Functional Coverage, Constrained Random, Scoreboards, Python, Linux, QuestaSim, VCS), role tiers (Tier 1–4), silicon domains (CPU, GPU, SoC, Interconnect, Automotive, Networking, EDA), and interview signals (debugging, protocol semantics, coverage closure).
  3. **Truthful Skill-Gap Engine (`SkillGapEngine`)**:
     - Compares JD requirements against candidate Fact Bank facts.
     - Categorizes competencies into `STRONG`, `FAMILIAR`, `PARTIAL`, `MISSING`, or `UNKNOWN`.
     - Strictly forbids hallucinating experience or automatically inserting unverified skills into the candidate profile. Missing skills generate truthful adjacent evidence recommendations.
  4. **Categorized Question Catalog (Categories A through M)**:
     - Curated question repository with standardized difficulty levels (`EASY`, `MEDIUM`, `HARD`, `EXPERT`) and explicit evidence provenance tags (`VERIFIED_FROM_JD`, `USER_PROVIDED`, `VERIFIED_PUBLIC_SOURCE`, `GENERAL_DV_TOPIC`, `LIKELY`, `POSSIBLE`).
     - Project defense questions are strictly grounded in candidate verified projects (AXI4 UVC architecture, out-of-order write/interleaved read ID tracking, dual-clock FIFO Gray-code pointer CDC synchronization, VALID/READY concurrent SVA assertions).
  5. **Interactive Mock Interview Engine & Modes (`MockInterviewMode`)**:
     - Supports `QUICK` (10 questions), `STANDARD` (20 questions), `DEEP` (40 questions), `COMPANY` (targeted), `WEAKNESS` (gap-focused), and `PROJECT` (project-defense only) modes.
     - Implements turn-by-turn question delivery and interactive submission.
  6. **Technical Answer Evaluation & Feedback (`AnswerEvaluationEngine`)**:
     - Evaluates candidate answers based on semantic concept coverage and technical accuracy without rigid single-wording constraints.
     - Classifies responses into `CORRECT`, `PARTIALLY_CORRECT`, `INCORRECT`, `UNCLEAR`.
     - Generates structured feedback: Good Points (`+`), Missing Points (`-`), and concrete practice drills.
  7. **Weakness Tracking & Trend Monitoring (`WeaknessTrackingService`)**:
     - Persists identified gaps into SQLite `weak_areas` with confidence and severity tracking.
     - Calculates topic-level weakness scores (0–100) and improvement trends (`IMPROVING`, `STABLE`, `NEEDS_ATTENTION`).
  8. **Deterministic Interview Readiness Score (`InterviewReadinessScorer`)**:
     - 8-dimensional evaluation: JD Coverage (15), Fundamentals (10), SystemVerilog (20), UVM (20), Protocols (15), Project Defense (10), Debugging (5), Behavioral (5).
     - Outputs explainable level: `READY` ($\ge 85$), `NEAR_READY` ($70-84.9$), `NEEDS_WORK` ($50-69.9$), `NOT_READY` ($<50$).
  9. **Personalized 7-Day Study Plan (`StudyPlanGenerator`)**:
     - Day 1: Fundamentals; Day 2: SystemVerilog; Day 3: UVM; Day 4: AXI/Protocol; Day 5: FIFO CDC & SVA; Day 6: Project Defense; Day 7: Full Mock Interview.
     - Dynamically incorporates active weak areas into daily drills.
  10. **CLI & Dashboard Integration**:
     - Dedicated CLI tool (`python -m app.jobs.interview --job <fingerprint> [--mode <mode>] [--plan] [--gaps] [--readiness] [--interactive]`).
     - Integrated Streamlit tab `🤖 Phase 6: Interview Copilot & Mock Practice` with live skill gaps, study plan view, and interactive mock question viewer.
  11. **Safety & Zero-Fabrication Enforcement**:
     - No fabricated interview statistics, bug counts, or candidate claims.
     - Autonomous applications, recruiter outreach, and form submissions remain strictly forbidden.
- **Consequences**: Equips the candidate with an end-to-end, rigorous, truthful interview copilot tailored to any target semiconductor job listing.

## ADR-0025: Phase 4 Final — Application Intelligence & Human-Gated Apply Pipeline
- **Status**: Accepted
- **Context**: Transforming raw job discovery into actionable application readiness requires automating all safe, high-value pre-application intelligence (eligibility classification, work authorization analysis, deterministic 6-factor priority scoring, resume profile selection, tailored cover letter drafting, application package bundling, follow-up tracking) while strictly maintaining human gating for any external action. The candidate must explicitly approve every application package, and only manual submissions by the candidate can transition application state to `applied` / `SUBMITTED_MANUALLY`.
- **Decision**:
  1. **Deterministic Eligibility Classification (`EligibilityClassifier`)**:
     - Classifies job listings into `ENTRY_LEVEL`, `GRADUATE`, `INTERNSHIP`, `EXPERIENCED`, `SENIOR`, or `UNKNOWN`.
     - Hard eligibility gating: Detects experience mismatches (e.g. $\ge 3$ years required) and flags 2025 fresher incompatibility, clamping priority to `SKIP` (<60) and preventing misclassification as `APPLY`.
  2. **Work Authorization Classification (`WorkAuthClassifier`)**:
     - Analyzes international / overseas postings for explicit visa and sponsorship terms: `SPONSORSHIP_AVAILABLE`, `INTERNATIONAL_APPLICANTS_ACCEPTED`, `NO_SPONSORSHIP_REQUIRED`, `LOCAL_AUTHORIZATION_REQUIRED`, `SPONSORSHIP_UNCLEAR`, `UNKNOWN`.
     - Never assumes sponsorship merely because a role is overseas.
  3. **6-Factor Deterministic Application Priority Scoring (`ApplicationPriorityEngine`)**:
     - Evaluates: Technical DV Match (30%), Freshness (20%), Graduate Eligibility (15%), Location / Work Auth (15%), Company / Role Relevance (10%), Application Feasibility (10%).
     - Assigns priority tiers: `CRITICAL` (90-100), `HIGH` (80-89), `APPLY` (70-79), `WATCH` (60-69), `SKIP` (<60).
  4. **Truthful Resume Profile Selection (`ResumeProfileSelector`)**:
     - Selects from 6 truthful profiles (`DV_CORE`, `ASIC_VERIFICATION`, `RTL_DESIGN`, `VLSI_INTERN`, `GRADUATE_ENGINEER`, `OVERSEAS_DV`) based on verified match signals without hallucinating skills or experience.
  5. **Fact-Grounded Cover Letter Generation (`CoverLetterGenerator`)**:
     - Generates concise tailored drafts using only verified candidate education, SystemVerilog/UVM competencies, and verified project details from the Fact Bank. Zero fabricated metrics or phantom experience.
  6. **Unified Application Package (`ApplicationPackage`)**:
     - Bundles job identity, official/source URLs, eligibility, work authorization, priority score & tier, selected resume, cover letter draft, warnings, and lifecycle state (`DISCOVERED`, `VERIFIED`, `READY`, `REVIEW_REQUIRED`, `APPROVED`, `SUBMITTED_MANUALLY`, `REJECTED`, `EXPIRED`, `WITHDRAWN`).
  7. **Duplicate Application Prevention**:
     - Deterministic fingerprinting prevents redundant application package generation across hourly scanner runs.
     - Detects material job updates ($>80$ chars expansion + active apply link) to trigger re-review safely.
  8. **Human Review & Approval Gate**:
     - "Approve for Manual Submission" button only changes state to `APPROVED` / `shortlisted`.
     - "Mark Submitted Manually" records `SUBMITTED_MANUALLY` / `applied` with user-entered confirmation reference.
     - Autonomous external application submission is strictly disabled.
  9. **Dashboard Application Pipeline UI**:
     - 4-tab interface in Section 3 of Streamlit dashboard: Priority Application Queue, Application Review & Approvals, Follow-Up Tracker, and Overseas & Work Authorization.
- **Consequences**: Maximum pre-application automation with zero candidate hallucination, zero portal spam, and 100% human agency.

## ADR-0026: Final Notification & Career Alert Automation Layer ("Watch Once, Get Notified")
- **Status**: Accepted
- **Context**: Candidates should not need to repeatedly open the dashboard or manually inspect listings to discover fresh opportunities. When a genuinely valuable opportunity is found during the existing hourly scan, Job-AI should notify the user by email with the opportunity already analyzed, evaluated, and prepared. Final application submission remains strictly human-controlled.
- **Decision**:
  1. **Decoupled Email Notification Architecture (`app/notifications/`)**:
     - Consumes already-created `ApplicationPackage` objects and `DailyCareerDigest` objects.
     - Email adapter is fully decoupled from discovery sources.
     - Never performs external application submissions or browser automation.
  2. **Configurable Multi-Provider Transport**:
     - Supports `console` (stdout logger for dev/demo), `mock` (isolated unit test harness), and `smtp` (TLS-encrypted standard SMTP with finite $\le 30$s timeouts and bounded $\le 3$ retries).
     - Credentials managed strictly through environment variables (`JOB_AI_EMAIL_*`). Zero secret leakage in logs, audit records, or UI.
  3. **Priority Routing & Deduplication Policy**:
     - `CRITICAL` (90-100) & `HIGH` (80-89) with verified $\le 24$h freshness: Send rich HTML + text alerts immediately.
     - `APPLY` (70-79) & `WATCH` (60-69): Filtered from immediate alerts and consolidated into the daily intelligence digest.
     - `SKIP` (<60): Suppressed.
     - Deterministic fingerprint checking prevents re-sending the same listing across hourly scans (`SUPPRESSED` state). Re-alerts only occur on verified material job updates.
  4. **Daily Intelligence Digest**:
     - Integrated into the existing single-scheduler daemon (`ScannerDaemon`).
     - Triggers once daily at a configurable local hour (`JOB_AI_DIGEST_HOUR=19`, default 19:00).
     - Consolidates actionable 70-79 matches, overseas roles, and newly discovered active roles without rescanning the internet.
  5. **Audit Trail & Failure Isolation**:
     - Every delivery attempt is persisted in SQLite `email_deliveries` (`QUEUED`, `SENT`, `FAILED`, `SUPPRESSED`).
     - Email transport errors are caught and isolated safely so that scanner execution and discovery cycles never fail due to email errors.
  6. **Explicit Safety Guarantees**:
     - Mandatory human approval disclaimers prominently rendered in every email.
     - Autonomous external application submission is strictly prohibited (`DISABLED — HUMAN APPROVAL REQUIRED`).
- **Consequences**: Candidates achieve true "watch once, get notified" automation with zero portal spam and complete control over external submissions.

## ADR-0027: Long-Term Multi-Day Opportunity Alert Suppression Policy
- **Status**: Accepted
- **Context**: Hourly duplicate suppression alone is insufficient to prevent user inbox fatigue across days and weeks. The user must not be notified every day (e.g. Monday, Tuesday, Wednesday, Thursday) merely because the same opportunity remains open on corporate career portals across hourly scans. Once an opportunity has been notified on first discovery, it must remain suppressed across subsequent days unless a genuine material change occurs.
- **Decision**:
  1. **Long-Term Multi-Day Suppression**:
     - SQLite `email_deliveries` audit table persists deterministic opportunity fingerprints indefinitely.
     - Once a job has been notified (`SENT` or `SUPPRESSED`), all subsequent rediscoveries across hourly cycles, daily cycles, and beyond 72+ hours are permanently suppressed from re-alerting unless `is_material_update` is explicitly evaluated as `True`.
     - Passing a 72-hour or multi-day time window does *not* trigger automatic re-alerts for unchanged jobs.
  2. **Deterministic Opportunity Identity**:
     - Opportunity identity is derived using strongest deterministic attributes: requisition ID / employer job ID, canonical application URL, role title, company, and location (`generate_job_fingerprint(company, title, location, requisition_id)`).
     - Same company $\ne$ same opportunity: A company with multiple distinct openings (e.g. Qualcomm Bengaluru DV Engineer Req 123 vs Qualcomm Hyderabad ASIC Verification Req 456) produces distinct fingerprints and each is evaluated and alerted independently.
  3. **Material Change Re-Alert Policy**:
     - Re-alerts are permitted *only* when the material-change engine detects significant updates (e.g. description length expanded by $>80$ chars with updated canonical application portal).
     - Non-material changes (crawler timestamp, scan timestamp, repeated active status, minor formatting) are strictly ignored and remain suppressed.
     - Material updates re-alert with `[MATERIAL UPDATE]` prefix and update delivery audit records.
  4. **Application-Submitted Suppression**:
     - If candidate has already submitted an application (`ApplicationStatus.APPLIED` / `submitted_manually` in `applications` table or `ApplicationPackage`), repeated notifications are suppressed even prior to email delivery, avoiding redundant notifications for roles already under candidate action.
  5. **Safety Invariants Maintained**:
     - Zero autonomous application submissions (`DISABLED — HUMAN APPROVAL REQUIRED`).
     - Zero candidate or opportunity data fabrication.
- **Consequences**: Ensures high-signal, actionable notifications ("Tell me when there is a genuinely new opportunity, not every hour or day that the same job still exists").
