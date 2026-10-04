"""Database schema definitions and initialization."""

import sqlite3

CREATE_RAW_JOBS_TABLE = """
CREATE TABLE IF NOT EXISTS raw_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    source_url TEXT,
    discovered_at TEXT NOT NULL,
    raw_payload TEXT NOT NULL,
    content_hash TEXT NOT NULL
);
"""

CREATE_NORMALIZED_JOBS_TABLE = """
CREATE TABLE IF NOT EXISTS normalized_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    raw_job_id INTEGER,
    company TEXT NOT NULL,
    title TEXT NOT NULL,
    location TEXT,
    country TEXT,
    employment_type TEXT,
    experience_min REAL,
    experience_max REAL,
    graduation_year_min INTEGER,
    graduation_year_max INTEGER,
    description TEXT,
    requirements TEXT,
    skills TEXT,
    application_url TEXT,
    source TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    fingerprint TEXT NOT NULL UNIQUE,
    FOREIGN KEY (raw_job_id) REFERENCES raw_jobs (id) ON DELETE SET NULL
);
"""

CREATE_APPLICATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'discovered',
    notes TEXT,
    tailored_resume_path TEXT,
    cover_letter_path TEXT,
    applied_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (job_id) REFERENCES normalized_jobs (id) ON DELETE CASCADE
);
"""

CREATE_APPLICATION_EVENTS_TABLE = """
CREATE TABLE IF NOT EXISTS application_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id INTEGER NOT NULL,
    job_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    company TEXT NOT NULL,
    role_title TEXT NOT NULL,
    location TEXT,
    source TEXT NOT NULL,
    official_application_url TEXT,
    timestamp TEXT NOT NULL,
    resume_version TEXT,
    cover_letter_version TEXT,
    application_status TEXT NOT NULL,
    reference_id TEXT,
    submission_evidence TEXT,
    notes TEXT,
    FOREIGN KEY (application_id) REFERENCES applications (id) ON DELETE CASCADE,
    FOREIGN KEY (job_id) REFERENCES normalized_jobs (id) ON DELETE CASCADE
);
"""

CREATE_NOTIFICATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id INTEGER,
    job_id INTEGER,
    notification_type TEXT NOT NULL,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL,
    is_read INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (application_id) REFERENCES applications (id) ON DELETE CASCADE,
    FOREIGN KEY (job_id) REFERENCES normalized_jobs (id) ON DELETE CASCADE
);
"""

CREATE_INTERVIEW_SESSIONS_TABLE = """
CREATE TABLE IF NOT EXISTS interview_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company TEXT NOT NULL,
    role TEXT NOT NULL,
    date TEXT NOT NULL,
    round TEXT NOT NULL,
    outcome TEXT,
    notes TEXT,
    created_at TEXT NOT NULL
);
"""

CREATE_INTERVIEW_QUESTIONS_TABLE = """
CREATE TABLE IF NOT EXISTS interview_questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER,
    job_id INTEGER,
    company TEXT,
    role TEXT,
    question TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'technical',
    topic TEXT NOT NULL,
    user_answer TEXT,
    expected_answer TEXT,
    feedback TEXT,
    was_correct INTEGER,
    difficulty TEXT,
    source TEXT NOT NULL,
    verified INTEGER NOT NULL DEFAULT 0,
    times_asked INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES interview_sessions (id) ON DELETE SET NULL,
    FOREIGN KEY (job_id) REFERENCES normalized_jobs (id) ON DELETE SET NULL
);
"""

CREATE_WEAK_AREAS_TABLE = """
CREATE TABLE IF NOT EXISTS weak_areas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic TEXT NOT NULL,
    description TEXT NOT NULL,
    evidence_source TEXT,
    severity TEXT NOT NULL DEFAULT 'medium',
    confidence REAL NOT NULL DEFAULT 0.5,
    last_reviewed TEXT,
    review_count INTEGER NOT NULL DEFAULT 0,
    resolved INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
"""

CREATE_PREPARATION_SESSIONS_TABLE = """
CREATE TABLE IF NOT EXISTS preparation_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER,
    date TEXT NOT NULL,
    topics TEXT NOT NULL,
    questions_attempted INTEGER NOT NULL DEFAULT 0,
    performance_summary TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (job_id) REFERENCES normalized_jobs (id) ON DELETE SET NULL
);
"""

CREATE_KNOWLEDGE_ITEMS_TABLE = """
CREATE TABLE IF NOT EXISTS knowledge_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic TEXT NOT NULL,
    concept TEXT NOT NULL,
    explanation TEXT NOT NULL,
    source TEXT NOT NULL,
    verified INTEGER NOT NULL DEFAULT 0,
    related_question_ids TEXT,
    created_at TEXT NOT NULL
);
"""

CREATE_ASSESSMENTS_TABLE = """
CREATE TABLE IF NOT EXISTS assessments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER,
    company TEXT,
    role TEXT,
    assessment_type TEXT NOT NULL,
    title TEXT NOT NULL,
    time_limit_minutes INTEGER NOT NULL DEFAULT 45,
    questions TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'created',
    score REAL,
    total_questions INTEGER NOT NULL DEFAULT 0,
    correct_count INTEGER NOT NULL DEFAULT 0,
    incorrect_count INTEGER NOT NULL DEFAULT 0,
    topic_breakdown TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    FOREIGN KEY (job_id) REFERENCES normalized_jobs (id) ON DELETE SET NULL
);
"""

CREATE_PREPARATION_SCHEDULES_TABLE = """
CREATE TABLE IF NOT EXISTS preparation_schedules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    company TEXT NOT NULL,
    title TEXT NOT NULL,
    target_interview_date TEXT,
    milestones TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (job_id) REFERENCES normalized_jobs (id) ON DELETE CASCADE
);
"""

CREATE_TAILORED_RESUMES_TABLE = """
CREATE TABLE IF NOT EXISTS tailored_resumes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    resume_id TEXT NOT NULL UNIQUE,
    target_job_id INTEGER NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    candidate_name TEXT NOT NULL,
    contact_info TEXT NOT NULL,
    professional_summary TEXT NOT NULL,
    technical_skills TEXT NOT NULL,
    projects TEXT NOT NULL,
    experience TEXT NOT NULL,
    education TEXT NOT NULL,
    certifications TEXT,
    ats_score REAL NOT NULL,
    ats_breakdown TEXT NOT NULL,
    fact_integrity_status TEXT NOT NULL,
    source_fact_ids TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    plain_text_content TEXT,
    markdown_content TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (target_job_id) REFERENCES normalized_jobs (id) ON DELETE CASCADE
);
"""

CREATE_PROPOSED_SCHEDULE_NOTIFICATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS proposed_schedule_notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    notification_type TEXT NOT NULL,
    destination TEXT NOT NULL,
    target_company TEXT NOT NULL,
    target_role TEXT NOT NULL,
    scheduled_time TEXT NOT NULL,
    action_type TEXT NOT NULL,
    subject TEXT NOT NULL,
    body_content TEXT NOT NULL,
    rationale TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'proposed',
    created_at TEXT NOT NULL,
    approved_at TEXT,
    dispatched_at TEXT
);
"""

CREATE_INDEXES = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_normalized_jobs_fingerprint ON normalized_jobs (fingerprint);
CREATE INDEX IF NOT EXISTS idx_normalized_jobs_company ON normalized_jobs (company);
CREATE INDEX IF NOT EXISTS idx_normalized_jobs_status ON normalized_jobs (status);
CREATE INDEX IF NOT EXISTS idx_normalized_jobs_location ON normalized_jobs (location);
CREATE INDEX IF NOT EXISTS idx_normalized_jobs_first_seen ON normalized_jobs (first_seen);
CREATE INDEX IF NOT EXISTS idx_raw_jobs_content_hash ON raw_jobs (content_hash);
CREATE INDEX IF NOT EXISTS idx_applications_status ON applications (status);
CREATE INDEX IF NOT EXISTS idx_applications_job_id ON applications (job_id);
CREATE INDEX IF NOT EXISTS idx_application_events_application_id ON application_events (application_id);
CREATE INDEX IF NOT EXISTS idx_application_events_job_id ON application_events (job_id);
CREATE INDEX IF NOT EXISTS idx_application_events_event_type ON application_events (event_type);
CREATE INDEX IF NOT EXISTS idx_application_events_timestamp ON application_events (timestamp);
CREATE INDEX IF NOT EXISTS idx_notifications_unread ON notifications (is_read);
CREATE INDEX IF NOT EXISTS idx_notifications_type ON notifications (notification_type);
CREATE INDEX IF NOT EXISTS idx_interview_questions_topic ON interview_questions (topic);
CREATE INDEX IF NOT EXISTS idx_interview_questions_company ON interview_questions (company);
CREATE INDEX IF NOT EXISTS idx_interview_questions_category ON interview_questions (category);
CREATE INDEX IF NOT EXISTS idx_interview_questions_session_id ON interview_questions (session_id);
CREATE INDEX IF NOT EXISTS idx_interview_questions_job_id ON interview_questions (job_id);
CREATE INDEX IF NOT EXISTS idx_weak_areas_topic ON weak_areas (topic);
CREATE INDEX IF NOT EXISTS idx_weak_areas_resolved ON weak_areas (resolved);
CREATE INDEX IF NOT EXISTS idx_preparation_sessions_job_id ON preparation_sessions (job_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_items_topic ON knowledge_items (topic);
CREATE INDEX IF NOT EXISTS idx_assessments_job_id ON assessments (job_id);
CREATE INDEX IF NOT EXISTS idx_assessments_type ON assessments (assessment_type);
CREATE INDEX IF NOT EXISTS idx_assessments_status ON assessments (status);
CREATE INDEX IF NOT EXISTS idx_preparation_schedules_job_id ON preparation_schedules (job_id);
CREATE INDEX IF NOT EXISTS idx_tailored_resumes_job_id ON tailored_resumes (target_job_id);
CREATE INDEX IF NOT EXISTS idx_tailored_resumes_status ON tailored_resumes (status);
CREATE INDEX IF NOT EXISTS idx_proposed_schedule_notifications_status ON proposed_schedule_notifications (status);
"""


def create_schema(conn: sqlite3.Connection) -> None:
    """Execute DDL statements to set up tables and indexes."""
    with conn:
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute(CREATE_RAW_JOBS_TABLE)
        conn.execute(CREATE_NORMALIZED_JOBS_TABLE)
        conn.execute(CREATE_APPLICATIONS_TABLE)
        conn.execute(CREATE_APPLICATION_EVENTS_TABLE)
        conn.execute(CREATE_NOTIFICATIONS_TABLE)
        conn.execute(CREATE_INTERVIEW_SESSIONS_TABLE)
        conn.execute(CREATE_INTERVIEW_QUESTIONS_TABLE)
        conn.execute(CREATE_WEAK_AREAS_TABLE)
        conn.execute(CREATE_PREPARATION_SESSIONS_TABLE)
        conn.execute(CREATE_KNOWLEDGE_ITEMS_TABLE)
        conn.execute(CREATE_ASSESSMENTS_TABLE)
        conn.execute(CREATE_PREPARATION_SCHEDULES_TABLE)
        conn.execute(CREATE_TAILORED_RESUMES_TABLE)
        conn.execute(CREATE_PROPOSED_SCHEDULE_NOTIFICATIONS_TABLE)
        conn.executescript(CREATE_INDEXES)

