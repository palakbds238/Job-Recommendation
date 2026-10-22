-- ============================================================
--  CareerAI — Database Schema
--  ML-Based Job Recommendation System
--  Run in any SQLite browser to inspect or reset the database
-- ============================================================

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    email       TEXT    UNIQUE NOT NULL,
    password    TEXT    NOT NULL,           -- SHA-256 hashed
    is_admin    INTEGER DEFAULT 0,          -- 1 = admin, 0 = user
    created_at  TEXT    DEFAULT (datetime('now'))
);

-- User profiles (one per user)
CREATE TABLE IF NOT EXISTS user_profiles (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER UNIQUE,
    skills          TEXT,                   -- Comma-separated skills
    experience      TEXT,                   -- e.g. "1-3 years"
    education       TEXT,                   -- e.g. "B.Tech"
    location        TEXT,                   -- Preferred city
    domain          TEXT,                   -- Preferred domain
    expected_salary TEXT,                   -- e.g. "10-15 LPA"
    goals           TEXT,                   -- Career goals text
    resume_text     TEXT,                   -- Extracted resume text
    resume_filename TEXT,                   -- Original filename
    updated_at      TEXT DEFAULT (datetime('now')),
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Jobs saved by users
CREATE TABLE IF NOT EXISTS saved_jobs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    job_id     INTEGER NOT NULL,
    saved_at   TEXT DEFAULT (datetime('now')),
    UNIQUE(user_id, job_id),
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Jobs applied to by users
CREATE TABLE IF NOT EXISTS applied_jobs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    job_id     INTEGER NOT NULL,
    job_title  TEXT,
    company    TEXT,
    applied_at TEXT DEFAULT (datetime('now')),
    app_hash     TEXT,      -- sha256 of the application record (anchored on-chain)
    salt         TEXT,
    tx_hash      TEXT,      -- blockchain transaction that recorded the hash
    block_number INTEGER,
    status            TEXT DEFAULT 'Applied',  -- Applied | Shortlisted | Interview | Offer | Rejected | Withdrawn
    notes             TEXT,                    -- the candidate's private notes
    status_updated_at TEXT,
    status_by         TEXT,                    -- 'user' or 'recruiter'
    user_notified     INTEGER DEFAULT 1,       -- 0 = recruiter changed it and the candidate hasn't seen it yet
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_applied ON applied_jobs(user_id, job_id);

-- Blockchain-verified credentials (only the hash is on-chain; details stay here)
CREATE TABLE IF NOT EXISTS credentials (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL,
    title        TEXT    NOT NULL,
    issuer_name  TEXT    NOT NULL,
    skills       TEXT,                  -- comma separated skills this credential verifies
    issued_on    TEXT,
    salt         TEXT    NOT NULL,      -- random, makes the hash unguessable
    cred_hash    TEXT    UNIQUE NOT NULL,
    tx_hash      TEXT,
    block_number INTEGER,
    status       TEXT    DEFAULT 'issued',   -- issued | revoked
    revoke_tx    TEXT,
    issued_by    INTEGER,
    created_at   TEXT    DEFAULT (datetime('now')),
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Custom jobs added by admin (in addition to CSV dataset)
CREATE TABLE IF NOT EXISTS custom_jobs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    title               TEXT NOT NULL,
    company             TEXT NOT NULL,
    skills_required     TEXT,
    category            TEXT,
    description         TEXT,
    location            TEXT,
    experience_required TEXT,
    education_required  TEXT,
    salary_range        TEXT,
    salary_lpa          REAL,
    job_type            TEXT DEFAULT 'Full-time',
    openings            INTEGER DEFAULT 1,
    added_by_admin      INTEGER,
    created_at          TEXT DEFAULT (datetime('now')),
    FOREIGN KEY(added_by_admin) REFERENCES users(id)
);

-- Default admin account (password: admin123 → SHA-256)
INSERT OR IGNORE INTO users (name, email, password, is_admin)
VALUES (
    'Administrator',
    'admin@jobrec.com',
    -- SHA-256 of 'admin123':
    '240be518fabd2724ddb6f04eeb1da5967448d7e831c08c8fa822809f74c720a9',
    1
);

-- Sample queries for reference:

-- Get all users with profile info:
-- SELECT u.name, u.email, p.skills, p.experience FROM users u
-- LEFT JOIN user_profiles p ON p.user_id = u.id WHERE u.is_admin = 0;

-- Get top saved job IDs:
-- SELECT job_id, COUNT(*) as saves FROM saved_jobs GROUP BY job_id ORDER BY saves DESC;

-- Get all applications:
-- SELECT u.name, a.job_title, a.company, a.applied_at
-- FROM applied_jobs a JOIN users u ON u.id = a.user_id ORDER BY a.applied_at DESC;

-- Live jobs pulled from external APIs (Adzuna, Remotive) by sync_jobs.py / admin page
CREATE TABLE IF NOT EXISTS live_jobs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    source              TEXT NOT NULL,          -- adzuna | remotive
    external_id         TEXT NOT NULL,          -- id at the provider
    title               TEXT NOT NULL,
    company             TEXT,
    location            TEXT,
    description         TEXT,                   -- HTML stripped
    skills_required     TEXT,                   -- extracted with skills.py
    category            TEXT,                   -- predicted by the Random Forest
    experience_required TEXT,                   -- inferred (or 'Not specified')
    education_required  TEXT,
    salary_range        TEXT,
    salary_lpa          REAL DEFAULT 0,
    job_type            TEXT,
    url                 TEXT,                   -- external apply link (http/https only)
    posted_at           TEXT,
    fetched_at          TEXT,
    last_seen           TEXT,
    updated_at          TEXT,
    UNIQUE(source, external_id)
);
CREATE TABLE IF NOT EXISTS sync_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source      TEXT NOT NULL,
    started_at  TEXT,
    finished_at TEXT,
    status      TEXT,                           -- ok | error | skipped
    fetched     INTEGER DEFAULT 0,
    inserted    INTEGER DEFAULT 0,
    updated     INTEGER DEFAULT 0,
    pruned      INTEGER DEFAULT 0,
    message     TEXT
);
