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










