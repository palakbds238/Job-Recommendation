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
