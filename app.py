"""
app.py
------
ML-Based Job Recommendation System — Complete Flask Application
All routes in correct order. No missing endpoints.
"""

from flask import (Flask, render_template, request, redirect,
                   url_for, session, jsonify, flash, g, Response, abort)
import sqlite3, hashlib, hmac, os, json, io, re, secrets, uuid, time, threading
import logging, csv as csv_mod
from datetime import datetime, timezone
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from model import (load_models, build_user_profile_text,
                   get_recommendations, predict_category,
                   get_category_stats, get_location_stats,
                   get_experience_stats, refresh_job_pool,
                   custom_jobs_signature, collect_user_skills, location_terms, score_jobs)
from blockchain import chain, ChainError, credential_hash, application_hash
from skills import parse_skill_list, normalize_skill
from collections import Counter
from urllib.parse import quote_plus
import mailer
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
import math
import pandas as pd
from collab import CollabModel, interactions_from_db, interactions_signature
import live_jobs as live

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("app")

# ══════════════════════════════════════════════════════════════
#  APP CONFIG
# ══════════════════════════════════════════════════════════════
app = Flask(__name__)


def _load_secret_key():
    """SECRET_KEY from the environment (production). In development a random key
    is generated once and kept in instance/secret_key (git-ignored) so sessions
    survive restarts. The old hard-coded key was public in the repository."""
    key = os.environ.get("SECRET_KEY")
    if key:
        return key
    os.makedirs("instance", exist_ok=True)
    path = os.path.join("instance", "secret_key")
    if not os.path.exists(path):
        with open(path, "w") as f:
            f.write(secrets.token_hex(32))
    return open(path).read().strip()


app.secret_key = _load_secret_key()
app.config.update(
    UPLOAD_FOLDER=os.environ.get("UPLOAD_FOLDER", "uploads"),
    MAX_CONTENT_LENGTH=5 * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "0") == "1",
)
ALLOWED_EXTENSIONS = {"pdf", "txt"}
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

print("Loading ML models...")
MODELS = load_models()

# ══════════════════════════════════════════════════════════════
#  DATABASE
# ══════════════════════════════════════════════════════════════
DB_PATH = os.environ.get("DATABASE_PATH", "job_recommender.db")

def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_db(exception):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()

def init_db():
    with app.app_context():
        db = sqlite3.connect(DB_PATH)
        db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT    NOT NULL,
                email       TEXT    UNIQUE NOT NULL,
                password    TEXT    NOT NULL,
                is_admin    INTEGER DEFAULT 0,
                created_at  TEXT    DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS user_profiles (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id         INTEGER UNIQUE,
                skills          TEXT,
                experience      TEXT,
                education       TEXT,
                location        TEXT,
                domain          TEXT,
                expected_salary TEXT,
                goals           TEXT,
                resume_text     TEXT,
                resume_filename TEXT,
                updated_at      TEXT DEFAULT (datetime('now')),
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS saved_jobs (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id  INTEGER,
                job_id   INTEGER,
                saved_at TEXT DEFAULT (datetime('now')),
                UNIQUE(user_id, job_id)
            );
            CREATE TABLE IF NOT EXISTS applied_jobs (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER,
                job_id     INTEGER,
                job_title  TEXT,
                company    TEXT,
                applied_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS custom_jobs (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                title               TEXT,
                company             TEXT,
                skills_required     TEXT,
                category            TEXT,
                description         TEXT,
                location            TEXT,
                experience_required TEXT,
                education_required  TEXT,
                salary_range        TEXT,
                salary_lpa          REAL,
                job_type            TEXT,
                openings            INTEGER DEFAULT 1,
                added_by_admin      INTEGER,
                created_at          TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS credentials (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      INTEGER NOT NULL,
                title        TEXT    NOT NULL,
                issuer_name  TEXT    NOT NULL,
                skills       TEXT,
                issued_on    TEXT,
                salt         TEXT    NOT NULL,
                cred_hash    TEXT    UNIQUE NOT NULL,
                tx_hash      TEXT,
                block_number INTEGER,
                status       TEXT    DEFAULT 'issued',
                revoke_tx    TEXT,
                issued_by    INTEGER,
                created_at   TEXT    DEFAULT (datetime('now'))
            );
        """)
        live.ensure_schema(db)                      # live_jobs + sync_log tables
        # upgrade databases created by the previous version
        _add_column(db, "applied_jobs", "app_hash", "TEXT")
        _add_column(db, "applied_jobs", "salt", "TEXT")
        _add_column(db, "applied_jobs", "tx_hash", "TEXT")
        _add_column(db, "applied_jobs", "block_number", "INTEGER")
        _add_column(db, "applied_jobs", "status", "TEXT DEFAULT 'Applied'")
        _add_column(db, "applied_jobs", "notes", "TEXT")
        _add_column(db, "applied_jobs", "status_updated_at", "TEXT")
        _add_column(db, "applied_jobs", "status_by", "TEXT")
        _add_column(db, "applied_jobs", "user_notified", "INTEGER DEFAULT 1")
        try:
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_applied "
                       "ON applied_jobs(user_id, job_id)")
        except sqlite3.IntegrityError:
            log.warning("Duplicate applications exist; unique index skipped.")
        _ensure_admin(db)
        db.commit()
        db.close()
    log.info("Database initialized")


def _add_column(db, table, column, decl):
    cols = [r[1] for r in db.execute(f"PRAGMA table_info({table})")]
    if column not in cols:
        db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


def _ensure_admin(db):
    """Admin credentials come from ADMIN_EMAIL / ADMIN_PASSWORD. If no password is
    configured a random one is generated and printed ONCE. A database that still
    holds the old public default (admin123, unsalted SHA-256) is rotated."""
    email = os.environ.get("ADMIN_EMAIL", "admin@jobrec.com").lower()
    given = os.environ.get("ADMIN_PASSWORD")
    row = db.execute("SELECT id, password FROM users WHERE is_admin=1 LIMIT 1").fetchone()
    if row is None:
        pw = given or secrets.token_urlsafe(10)
        db.execute("INSERT INTO users (name, email, password, is_admin) VALUES (?,?,?,1)",
                   ("Administrator", email, hash_password(pw)))
        if not given:
            print(f"\n  >> Admin account created: {email} / {pw}   (shown once)\n")
    elif row[1] == LEGACY_DEFAULT_ADMIN_HASH:
        pw = given or secrets.token_urlsafe(10)
        db.execute("UPDATE users SET password=? WHERE id=?", (hash_password(pw), row[0]))
        print(f"\n  >> Default admin password was rotated. New login: {email} / {pw}\n"
              if not given else "  >> Default admin password replaced from ADMIN_PASSWORD.")

# ══════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════
LEGACY_DEFAULT_ADMIN_HASH = hashlib.sha256(b"admin123").hexdigest()


def hash_password(pw):
    """Salted, slow hash (werkzeug scrypt). Replaces unsalted SHA-256."""
    return generate_password_hash(pw)


def _is_legacy_hash(stored):
    return bool(stored) and "$" not in stored and ":" not in stored


def verify_password(stored, pw):
    if _is_legacy_hash(stored):          # accounts created before this upgrade
        return hmac.compare_digest(stored, hashlib.sha256(pw.encode()).hexdigest())
    return check_password_hash(stored, pw)


# ── CSRF protection (token in session, sent as form field or X-CSRFToken) ──
def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_hex(16)
    return session["_csrf"]


app.jinja_env.globals["csrf_token"] = csrf_token


@app.before_request
def csrf_protect():
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        sent = request.form.get("csrf_token") or request.headers.get("X-CSRFToken", "")
        want = session.get("_csrf", "")
        if not want or not hmac.compare_digest(want, sent):
            abort(400, "Security token missing or expired. Reload the page and try again.")


# ── simple in-memory login throttle (per worker) ───────────────────────────
_FAILS, _FAIL_LOCK = {}, threading.Lock()
MAX_FAILS, FAIL_WINDOW = 5, 600


def _throttled(key):
    now = time.time()
    with _FAIL_LOCK:
        _FAILS[key] = [t for t in _FAILS.get(key, []) if now - t < FAIL_WINDOW]
        return len(_FAILS[key]) >= MAX_FAILS


def _record_fail(key):
    with _FAIL_LOCK:
        _FAILS.setdefault(key, []).append(time.time())

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("is_admin"):
            flash("Admin access required.", "danger")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def extract_resume_text(filepath):
    ext = filepath.rsplit(".", 1)[-1].lower()
    if ext == "txt":
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    elif ext == "pdf":
        try:
            import pdfplumber
            with pdfplumber.open(filepath) as pdf:
                return "\n".join(p.extract_text() or "" for p in pdf.pages)
        except Exception as e:  # noqa: BLE001  (missing lib, corrupt/scanned PDF…)
            log.warning("Resume PDF could not be read: %s", e)
            return ""
    return ""


def _remove_upload(filename):
    if not filename:
        return
    path = os.path.join(app.config["UPLOAD_FOLDER"], os.path.basename(filename))
    try:
        os.remove(path)
    except OSError:
        pass

# ══════════════════════════════════════════════════════════════
#  PUBLIC ROUTES
# ══════════════════════════════════════════════════════════════

@app.route("/")
def home():
    try:
        df         = MODELS["jobs_df"]
        total_jobs = len(df)
        categories = df["category"].nunique()
    except Exception:
        total_jobs, categories = 100, 19
    return render_template("home.html", total_jobs=total_jobs, categories=categories)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name     = request.form["name"].strip()
        email    = request.form["email"].strip().lower()
        password = request.form["password"]
        if not all([name, email, password]):
            flash("All fields are required.", "danger")
            return redirect(url_for("register"))
        if len(password) < 8:
            flash("Password must be at least 8 characters.", "danger")
            return redirect(url_for("register"))
        db = get_db()
        if db.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone():
            flash("Email already registered. Please login.", "warning")
            return redirect(url_for("login"))
        db.execute("INSERT INTO users (name, email, password) VALUES (?,?,?)",
                   (name, email, hash_password(password)))
        db.commit()
        flash("Account created! Please log in.", "success")
        return redirect(url_for("login"))
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email    = request.form["email"].strip().lower()
        password = request.form["password"]
        db       = get_db()
        throttle = f"{request.remote_addr}|{email}"
        if _throttled(throttle):
            flash("Too many failed attempts. Try again in a few minutes.", "danger")
            return redirect(url_for("login"))
        user = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if not user or not verify_password(user["password"], password):
            _record_fail(throttle)
            flash("Invalid email or password.", "danger")
            return redirect(url_for("login"))
        if _is_legacy_hash(user["password"]):      # upgrade old SHA-256 hash
            db.execute("UPDATE users SET password=? WHERE id=?",
                       (hash_password(password), user["id"]))
            db.commit()
        session.clear()                            # fresh session after login
        session["user_id"]   = user["id"]
        session["user_name"] = user["name"]
        session["is_admin"]  = bool(user["is_admin"])
        if user["is_admin"]:
            return redirect(url_for("admin_dashboard"))
        return redirect(url_for("dashboard"))
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully.", "info")
    return redirect(url_for("home"))

# ══════════════════════════════════════════════════════════════
#  USER ROUTES
# ══════════════════════════════════════════════════════════════

@app.route("/dashboard")
@login_required
def dashboard():
    db      = get_db()
    user_id = session["user_id"]
    profile = db.execute(
        "SELECT * FROM user_profiles WHERE user_id=?", (user_id,)
    ).fetchone()
    saved = db.execute(
        "SELECT COUNT(*) as c FROM saved_jobs WHERE user_id=?", (user_id,)
    ).fetchone()["c"]
    applied = db.execute(
        "SELECT COUNT(*) as c FROM applied_jobs WHERE user_id=?", (user_id,)
    ).fetchone()["c"]
    predicted_cat = confidence = None
    if profile and profile["skills"]:
        text = build_user_profile_text(
            profile["skills"], profile["experience"], profile["education"],
            profile["domain"], profile["location"], profile["goals"],
            profile["resume_text"] or ""
        )
        predicted_cat, confidence = predict_category(MODELS, text)
    pct, tips = profile_completeness(profile)
    pipeline = Counter((r["status"] or "Applied") for r in db.execute(
        "SELECT status FROM applied_jobs WHERE user_id=?", (user_id,)))
    return render_template("dashboard.html",
                           strength={"pct": pct, "tips": tips[:3]},
                           pipeline=[(st, pipeline.get(st, 0)) for st in APP_STATUSES[:5]],
                           profile=profile,
                           saved_count=saved,
                           applied_count=applied,
                           predicted_category=predicted_cat,
                           category_confidence=confidence)


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    db      = get_db()
    user_id = session["user_id"]
    if request.method == "POST":
        skills    = request.form.get("skills", "").strip()
        experience= request.form.get("experience", "")
        education = request.form.get("education", "")
        location  = request.form.get("location", "")
        domain    = request.form.get("domain", "Any")
        exp_sal   = request.form.get("expected_salary", "")
        goals     = request.form.get("goals", "")
        resume_text     = ""
        resume_filename = ""
        if "resume" in request.files:
            file = request.files["resume"]
            if file and file.filename and allowed_file(file.filename):
                old = db.execute("SELECT resume_filename FROM user_profiles "
                                 "WHERE user_id=?", (user_id,)).fetchone()
                # unique name: two users uploading "resume.pdf" no longer collide
                filename        = f"{user_id}_{uuid.uuid4().hex[:8]}_{secure_filename(file.filename)}"
                filepath        = os.path.join(app.config["UPLOAD_FOLDER"], filename)
                file.save(filepath)
                resume_text     = extract_resume_text(filepath)
                resume_filename = filename
                if old and old["resume_filename"]:
                    _remove_upload(old["resume_filename"])
                if not resume_text.strip():
                    flash("We couldn't read any text from that resume (scanned "
                          "image PDF?). Your other profile details were saved.",
                          "warning")
            elif file and file.filename:
                flash("Unsupported resume type — upload a PDF or TXT file.", "warning")
        existing = db.execute(
            "SELECT id FROM user_profiles WHERE user_id=?", (user_id,)
        ).fetchone()
        if existing:
            if resume_text:
                db.execute("""
                    UPDATE user_profiles SET
                        skills=?, experience=?, education=?, location=?, domain=?,
                        expected_salary=?, goals=?, resume_text=?, resume_filename=?,
                        updated_at=datetime('now')
                    WHERE user_id=?
                """, (skills, experience, education, location, domain,
                      exp_sal, goals, resume_text, resume_filename, user_id))
            else:
                db.execute("""
                    UPDATE user_profiles SET
                        skills=?, experience=?, education=?, location=?, domain=?,
                        expected_salary=?, goals=?, updated_at=datetime('now')
                    WHERE user_id=?
                """, (skills, experience, education, location, domain,
                      exp_sal, goals, user_id))
        else:
            db.execute("""
                INSERT INTO user_profiles
                    (user_id, skills, experience, education, location, domain,
                     expected_salary, goals, resume_text, resume_filename)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (user_id, skills, experience, education, location, domain,
                  exp_sal, goals, resume_text, resume_filename))
        db.commit()
        flash("Profile updated successfully!", "success")
        return redirect(url_for("recommendations"))
    current = db.execute(
        "SELECT * FROM user_profiles WHERE user_id=?", (user_id,)
    ).fetchone()
    pct, tips = profile_completeness(current)
    return render_template("profile.html", profile=current, suggestions=resume_suggestions(current),
                           strength={"pct": pct, "tips": tips[:3]})


@app.route("/profile/add_skills", methods=["POST"])
@login_required
def profile_add_skills():
    db, uid = get_db(), session["user_id"]
    p = db.execute("SELECT skills FROM user_profiles WHERE user_id=?", (uid,)).fetchone()
    if not p:
        return redirect(url_for("profile"))
    current = [x.strip() for x in (p["skills"] or "").split(",") if x.strip()]
    have    = {normalize_skill(x) for x in current}
    chosen  = [x.strip()[:40] for x in request.form.getlist("skill") if x.strip()][:20]
    added   = []
    for x in chosen:                                         # only skills our vocabulary knows
        n = normalize_skill(x)
        if n in MODELS["skill_vocab"] and n not in have:
            added.append(x); have.add(n)
    if added:
        db.execute("UPDATE user_profiles SET skills=?, updated_at=datetime('now') WHERE user_id=?",
                   (", ".join(current + added), uid))
        db.commit()
        flash(f"Added {len(added)} skill{'s' if len(added) != 1 else ''} to your profile.", "success")
    return redirect(url_for("profile"))


@app.route("/recommendations")
@login_required
def recommendations():
    db      = get_db()
    user_id = session["user_id"]
    profile = db.execute(
        "SELECT * FROM user_profiles WHERE user_id=?", (user_id,)
    ).fetchone()
    if not profile:
        flash("Please build your profile first to get recommendations.", "warning")
        return redirect(url_for("profile"))
    profile_text = build_user_profile_text(
        profile["skills"]      or "",
        profile["experience"]  or "",
        profile["education"]   or "",
        profile["domain"]      or "",
        profile["location"]    or "",
        profile["goals"]       or "",
        profile["resume_text"] or ""
    )
    # Location: an explicit filter wins (an empty value means "any location").
    # Without one, the user's Preferred Location from the profile is used.
    if "location" in request.args:
        f_location, from_profile = request.args.get("location", "").strip(), False
    else:
        f_location = (profile["location"] or "").strip()
        from_profile = bool(f_location)
    f_remote = request.args.get("remote") == "1"
    f_exp      = request.args.get("experience", "")
    f_cat      = request.args.get("category", "")
    f_salary   = request.args.get("min_salary", "")
    verified = verified_skills_for_user(db, user_id)
    have     = collect_user_skills(MODELS, profile["skills"] or "",
                                   profile["goals"] or "",
                                   profile["resume_text"] or "") | verified
    collab = get_collab(db)
    cf_scores, cf_weight = collab.scores_for(user_id)
    recs = get_recommendations(
        MODELS, profile_text, top_n=200,
        filter_location=f_location,
        filter_experience=f_exp,
        filter_category=f_cat,
        min_salary=f_salary if f_salary else None,
        user_skills=have, verified_skills=verified,
        cf_scores=cf_scores, cf_weight=cf_weight,
        cf_explain=_cf_explainer(collab, user_id),
        include_remote=f_remote
    )
    saved_ids = set(
        r["job_id"] for r in db.execute(
            "SELECT job_id FROM saved_jobs WHERE user_id=?", (user_id,)
        ).fetchall()
    )
    jobs_df  = MODELS["jobs_df"]
    cats     = sorted(jobs_df["category"].unique().tolist())
    sort = request.args.get("sort", "match")
    if sort == "salary":
        recs.sort(key=lambda r: r["salary_lpa"], reverse=True)
    elif sort == "newest":
        recs.sort(key=lambda r: (r["posted_days_ago"], -r["match_pct"]))
    else:
        sort = "match"
    pg   = paginate(len(recs), _to_int(request.args.get("page")))
    recs = recs[pg["start"]:pg["end"]]
    qargs = {a: b for a, b in request.args.items() if a != "page"}
    locs     = sorted(l for l in jobs_df["location"].unique().tolist()
                      if l and l != "Not specified")
    top_locs = [l for l in jobs_df["location"].value_counts().index.tolist()
                if l and l != "Not specified"][:5]
    exp_lvls = sorted(jobs_df["experience_required"].unique().tolist())
    return render_template("recommendations.html",
                           recommendations=recs,
                           saved_ids=saved_ids,
                           profile=profile,
                           categories=cats,
                           locations=locs,
                           top_locations=top_locs,
                           from_profile=from_profile,
                           pg=pg, qargs=qargs, sort=sort,
                           experience_levels=exp_lvls,
                           filters={
                               "remote": f_remote,
                               "location": f_location,
                               "experience": f_exp,
                               "category": f_cat,
                               "min_salary": f_salary
                           })


@app.route("/job/<int:job_id>")
@login_required
def job_detail(job_id):
    db      = get_db()
    user_id = session["user_id"]
    jobs_df = MODELS["jobs_df"]
    row     = jobs_df[jobs_df["job_id"] == job_id]
    if row.empty:
        flash("Job not found.", "warning")
        return redirect(url_for("recommendations"))
    job        = row.iloc[0].to_dict()
    is_saved   = bool(db.execute(
        "SELECT 1 FROM saved_jobs WHERE user_id=? AND job_id=?", (user_id, job_id)
    ).fetchone())
    is_applied = bool(db.execute(
        "SELECT 1 FROM applied_jobs WHERE user_id=? AND job_id=?", (user_id, job_id)
    ).fetchone())
    similar = jobs_df[
        (jobs_df["category"] == job["category"]) & (jobs_df["job_id"] != job_id)
    ].head(4).to_dict("records")
    return render_template("job_detail.html",
                           job=job, is_saved=is_saved,
                           is_applied=is_applied, similar_jobs=similar,
                           match=_match_for(_user_ctx(db, user_id), job_id))


@app.route("/save_job", methods=["POST"])
@login_required
def save_job():
    data = request.get_json(silent=True) or {}
    try:
        job_id = int(data.get("job_id"))
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "Invalid job."}), 400
    # only real jobs: stops junk ids from polluting saved lists / collaborative filtering
    if MODELS["jobs_df"][MODELS["jobs_df"]["job_id"] == job_id].empty:
        return jsonify({"status": "error", "message": "Job not found."}), 404
    db = get_db()
    db.execute("INSERT OR IGNORE INTO saved_jobs (user_id, job_id) VALUES (?,?)",
               (session["user_id"], job_id))
    db.commit()
    return jsonify({"status": "saved"})


@app.route("/unsave_job", methods=["POST"])
@login_required
def unsave_job():
    data    = request.get_json(silent=True) or {}
    job_id  = data.get("job_id")
    user_id = session["user_id"]
    db      = get_db()
    db.execute(
        "DELETE FROM saved_jobs WHERE user_id=? AND job_id=?", (user_id, job_id)
    )
    db.commit()
    return jsonify({"status": "unsaved"})


@app.route("/apply_job", methods=["POST"])
@login_required
def apply_job():
    data    = request.get_json(silent=True) or {}
    try:
        job_id = int(data.get("job_id"))
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "Invalid job."}), 400
    jobs_df = MODELS["jobs_df"]
    row     = jobs_df[jobs_df["job_id"] == job_id]
    if row.empty:
        return jsonify({"status": "error", "message": "Job not found."}), 404
    # title / company come from our own data — never from the client
    title, company = str(row.iloc[0]["title"]), str(row.iloc[0]["company"])
    user_id = session["user_id"]
    db      = get_db()
    if db.execute("SELECT 1 FROM applied_jobs WHERE user_id=? AND job_id=?",
                  (user_id, job_id)).fetchone():
        return jsonify({"status": "already_applied",
                        "message": "You already applied to this job."})
    applied_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    salt       = secrets.token_hex(16)
    app_hash   = application_hash(user_id, job_id, title, company, applied_at, salt)
    tx_hash = block = None
    chain_msg = ""
    if chain.enabled:
        try:
            res = chain.anchor_application(app_hash)
            tx_hash, block = res["tx_hash"], res["block"]
            chain_msg = " Proof recorded on the blockchain."
        except ChainError as e:                 # never block the application itself
            log.warning("Anchoring failed: %s", e)
            chain_msg = " (Blockchain proof unavailable right now.)"
    db.execute("""INSERT INTO applied_jobs
                  (user_id, job_id, job_title, company, applied_at,
                   app_hash, salt, tx_hash, block_number)
                  VALUES (?,?,?,?,?,?,?,?,?)""",
               (user_id, job_id, title, company, applied_at,
                app_hash, salt, tx_hash, block))
    db.commit()
    return jsonify({"status": "applied",
                    "message": f"Applied to {title} at {company}!{chain_msg}"})


@app.route("/saved_jobs")
@login_required
def saved_jobs():
    db      = get_db()
    user_id = session["user_id"]
    saved   = db.execute(
        "SELECT job_id, saved_at FROM saved_jobs WHERE user_id=? ORDER BY saved_at DESC",
        (user_id,)
    ).fetchall()
    jobs_df    = MODELS["jobs_df"]
    saved_list = []
    for row in saved:
        jid = row["job_id"]
        job = jobs_df[jobs_df["job_id"] == jid]
        if not job.empty:
            j             = job.iloc[0].to_dict()
            j["saved_at"] = row["saved_at"]
            saved_list.append(j)
    return render_template("saved_jobs.html", saved_jobs=saved_list)


# ══════════════════════════════════════════════════════════════
#  APPLICATION TRACKER + RECRUITER VIEW
# ══════════════════════════════════════════════════════════════
APP_STATUSES = ["Applied", "Shortlisted", "Interview", "Offer", "Rejected", "Withdrawn"]


def _now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


app.jinja_env.filters["learn_url"] = lambda skill: "https://www.google.com/search?q=" + quote_plus(f"learn {skill} course")


def profile_completeness(p):
    """-> (percent, [tips for the missing parts])"""
    if not p:
        return 0, ["Create your profile"]
    parts = [("skills", 25, "Add your skills"), ("experience", 10, "Choose your experience level"),
             ("education", 10, "Add your education"), ("domain", 10, "Pick a domain"),
             ("location", 10, "Set a preferred location"), ("goals", 10, "Describe your career goals"),
             ("expected_salary", 5, "Add an expected salary"), ("resume_filename", 20, "Upload your resume")]
    got, tips = 0, []
    for key, pts, tip in parts:
        if str(p[key] or "").strip():
            got += pts
        else:
            tips.append(f"{tip} (+{pts}%)")
    return got, tips


def resume_suggestions(p, limit=12):
    """Skills found in the resume text that are not in the profile's skills yet."""
    if not p or not (p["resume_text"] or "").strip():
        return []
    found = MODELS["extractor"].extract(p["resume_text"]) - parse_skill_list(p["skills"] or "")
    disp = MODELS["skill_display"]
    return sorted(disp.get(x, x.title()) for x in found)[:limit]


def _user_ctx(db, user_id):
    """Everything needed to score jobs for one user (None if they have no skills yet)."""
    p = db.execute("SELECT * FROM user_profiles WHERE user_id=?", (user_id,)).fetchone()
    if not p or not (p["skills"] or "").strip():
        return None
    verified = verified_skills_for_user(db, user_id)
    have = collect_user_skills(MODELS, p["skills"] or "", p["goals"] or "", p["resume_text"] or "") | verified
    text = build_user_profile_text(p["skills"] or "", p["experience"] or "", p["education"] or "",
                                   p["domain"] or "", p["location"] or "", p["goals"] or "",
                                   p["resume_text"] or "")
    return {"have": have, "verified": verified, "text": text}


def _match_for(ctx, job_id):
    """-> {pct, matched, missing, verified} for one job, or None."""
    df  = MODELS["jobs_df"]
    idx = df.index[df["job_id"] == job_id]
    if ctx is None or len(idx) == 0:
        return None
    if "_scores" not in ctx:                                  # one scoring pass per user, reused per row
        ctx["_scores"] = score_jobs(MODELS, ctx["text"], ctx["have"], ctx["verified"])[0]
    i   = idx[0]
    req = [x.strip() for x in str(df.loc[i, "skills_required"]).split(",") if x.strip()]
    matched = [x for x in req if normalize_skill(x) in ctx["have"]]
    return {"pct": int(round(100 * float(ctx["_scores"].loc[i, "final"]))), "matched": matched,
            "missing": [x for x in req if x not in matched],
            "verified": [x for x in matched if normalize_skill(x) in ctx["verified"]]}


@app.route("/applied_jobs")
@login_required
def applied_jobs():
    db, uid = get_db(), session["user_id"]
    status  = request.args.get("status", "")
    rows    = db.execute("SELECT * FROM applied_jobs WHERE user_id=? ORDER BY applied_at DESC", (uid,)).fetchall()
    counts  = Counter((r["status"] or "Applied") for r in rows)
    unseen  = {r["id"] for r in rows if r["user_notified"] == 0}
    if unseen:                                                # opening the page marks updates as seen
        db.execute("UPDATE applied_jobs SET user_notified=1 WHERE user_id=?", (uid,))
        db.commit()
    shown = [r for r in rows if not status or (r["status"] or "Applied") == status]
    pg    = paginate(len(shown), _to_int(request.args.get("page")))
    shown = shown[pg["start"]:pg["end"]]
    df, info = MODELS["jobs_df"], {}
    for r in shown:
        j = df[df["job_id"] == r["job_id"]]
        if not j.empty:
            info[r["id"]] = {"url": j.iloc[0]["url"], "source": j.iloc[0]["source"]}
    return render_template("applied_jobs.html", apps=shown, info=info, unseen=unseen, statuses=APP_STATUSES,
                           counts=counts, total=len(rows), status=status, pg=pg,
                           qargs={a: b for a, b in request.args.items() if a != "page" and b})


@app.route("/application/<int:app_id>/update", methods=["POST"])
@login_required
def application_update(app_id):
    data = request.get_json(silent=True) or request.form
    db   = get_db()
    row  = db.execute("SELECT * FROM applied_jobs WHERE id=? AND user_id=?", (app_id, session["user_id"])).fetchone()
    if not row:
        return jsonify({"status": "error", "message": "Application not found."}), 404
    sets, params = [], []
    status, notes = data.get("status"), data.get("notes")
    if status is not None:
        if status not in APP_STATUSES:
            return jsonify({"status": "error", "message": "Unknown status."}), 400
        if status != (row["status"] or "Applied"):
            sets += ["status=?", "status_updated_at=?", "status_by='user'", "user_notified=1"]
            params += [status, _now_iso()]
    if notes is not None:
        sets.append("notes=?"); params.append(str(notes).strip()[:1000])
    if sets:
        db.execute("UPDATE applied_jobs SET " + ", ".join(sets) + " WHERE id=?", params + [app_id])
        db.commit()
    return jsonify({"status": "ok", "label": status or (row["status"] or "Applied")})


def _admin_app_query():
    """Shared by the applicants page and its CSV export."""
    status = request.args.get("status", "")
    q      = request.args.get("q", "").strip()[:80]
    where, params = [], []
    if status in APP_STATUSES:
        where.append("COALESCE(a.status,'Applied')=?"); params.append(status)
    if q:
        where.append("(LOWER(a.job_title) LIKE ? OR LOWER(a.company) LIKE ? OR LOWER(u.name) LIKE ? OR LOWER(u.email) LIKE ?)")
        params += [f"%{q.lower()}%"] * 4
    frm = "FROM applied_jobs a JOIN users u ON u.id=a.user_id" + (" WHERE " + " AND ".join(where) if where else "")
    return status if status in APP_STATUSES else "", q, frm, params


@app.route("/admin/applications")
@admin_required
def admin_applications():
    db = get_db()
    status, q, frm, params = _admin_app_query()
    pg   = paginate(db.execute("SELECT COUNT(*) " + frm, params).fetchone()[0], _to_int(request.args.get("page")), per_page=20)
    rows = db.execute("SELECT a.*, u.name AS cand_name, u.email AS cand_email " + frm +
                      " ORDER BY a.applied_at DESC LIMIT ? OFFSET ?", params + [pg["per_page"], pg["start"]]).fetchall()
    ctxs, items = {}, []
    for r in rows:
        ctxs.setdefault(r["user_id"], _user_ctx(db, r["user_id"]))
        creds = db.execute("SELECT title, cred_hash, status FROM credentials WHERE user_id=? ORDER BY id DESC LIMIT 4",
                           (r["user_id"],)).fetchall()
        items.append({"row": r, "match": _match_for(ctxs[r["user_id"]], r["job_id"]), "creds": creds})
    counts = {s: db.execute("SELECT COUNT(*) FROM applied_jobs WHERE COALESCE(status,'Applied')=?", (s,)).fetchone()[0]
              for s in APP_STATUSES}
    return render_template("admin_applications.html", items=items, pg=pg, statuses=APP_STATUSES, status=status, q=q,
                           counts=counts, total=sum(counts.values()),
                           qargs={a: b for a, b in request.args.items() if a != "page" and b})


@app.route("/admin/applications/<int:app_id>/status", methods=["POST"])
@admin_required
def admin_application_status(app_id):
    db, status = get_db(), request.form.get("status", "")
    row = db.execute("SELECT * FROM applied_jobs WHERE id=?", (app_id,)).fetchone()
    back = {k: request.form.get(f"f_{k}", "") for k in ("status", "q", "page")}
    back = url_for("admin_applications", **{k: v for k, v in back.items() if v})
    if not row or status not in APP_STATUSES:
        flash("Couldn't update that application.", "danger")
        return redirect(back)
    if status != (row["status"] or "Applied"):
        db.execute("UPDATE applied_jobs SET status=?, status_updated_at=?, status_by='recruiter', user_notified=0 "
                   "WHERE id=?", (status, _now_iso(), app_id))
        db.commit()
        flash(f"Marked as {status}. The candidate will see the update.", "success")
    return redirect(back)


def _csv_safe(v):
    v = "" if v is None else str(v)
    return "'" + v if v[:1] in ("=", "+", "-", "@", "\t", "\r") else v        # CSV/Excel formula injection


@app.route("/admin/applications/export")
@admin_required
def admin_applications_export():
    db = get_db()
    _, _, frm, params = _admin_app_query()
    rows = db.execute("SELECT a.*, u.name AS cand_name, u.email AS cand_email " + frm + " ORDER BY a.applied_at DESC", params).fetchall()
    buf = io.StringIO()
    w = csv_mod.writer(buf)
    w.writerow(["applied_at", "candidate", "email", "job_title", "company", "status", "status_updated_by", "blockchain_tx"])
    for r in rows:
        w.writerow([_csv_safe(x) for x in (r["applied_at"], r["cand_name"], r["cand_email"], r["job_title"], r["company"],
                                           r["status"] or "Applied", r["status_by"] or "", r["tx_hash"] or "")])
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=applications.csv"})


# ══════════════════════════════════════════════════════════════
#  PAGINATION + SEARCH
# ══════════════════════════════════════════════════════════════
PAGE_SIZE = 10


def _to_int(v, default=1):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _to_float(v):
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def paginate(total, page, per_page=PAGE_SIZE):
    """-> dict used by templates/_pagination.html (page numbers with None = ellipsis)."""
    pages = max(1, math.ceil(total / per_page))
    page  = min(max(1, page), pages)
    keep  = sorted({1, pages} | set(range(page - 2, page + 3)))
    nums, prev = [], 0
    for n in (k for k in keep if 1 <= k <= pages):
        if n - prev > 1:
            nums.append(None)
        nums.append(n); prev = n
    start = (page - 1) * per_page
    return {"page": page, "pages": pages, "total": total, "per_page": per_page, "numbers": nums,
            "start": start, "end": min(start + per_page, total), "has_prev": page > 1, "has_next": page < pages}


SEARCH_COLS = (("title", 3.0), ("skills_required", 2.0), ("category", 1.5),
               ("company", 1.0), ("location", 1.0), ("description", 0.4))
SORTS = {"relevance": "Best match", "newest": "Newest", "salary": "Highest salary"}


@app.route("/search")
@login_required
def search():
    df    = MODELS["jobs_df"]
    q     = request.args.get("q", "").strip()[:100]
    f     = {k: request.args.get(k, "").strip()[:60] for k in ("category", "location", "experience", "job_type")}
    f["min_salary"] = request.args.get("min_salary", "").strip()[:8]
    sort  = request.args.get("sort", "relevance")
    sort  = sort if sort in SORTS else "relevance"
    terms = [t for t in q.lower().split() if t][:6]
    searched = bool(terms or any(f.values()))

    results, pg, active = [], paginate(0, 1), []
    if searched:
        mask  = pd.Series(True, index=df.index)
        score = pd.Series(0.0, index=df.index)
        low   = {c: df[c].astype(str).str.lower() for c, _ in SEARCH_COLS}
        for t in terms:                       # every word must appear somewhere (any field)
            hit_any = pd.Series(False, index=df.index)
            for col, w in SEARCH_COLS:
                hit = low[col].str.contains(t, regex=False, na=False)   # plain text: "c++" or "(" are safe
                hit_any |= hit
                score += hit * w
            mask &= hit_any
        if f["category"]:
            mask &= df["category"].str.lower() == f["category"].lower()
        if f["experience"]:
            mask &= df["experience_required"] == f["experience"]
        if f["job_type"]:
            mask &= df["job_type"] == f["job_type"]
        locs = location_terms(f["location"])
        if locs:
            ll = df["location"].str.lower()
            keep = pd.Series(False, index=df.index)
            for t in locs:
                keep |= ll.str.contains(t, regex=False, na=False)
            mask &= keep
        ms = _to_float(f["min_salary"])
        if ms is not None:
            mask &= df["salary_lpa"] >= ms
        d = df[mask].assign(_score=score[mask])
        if sort == "salary":
            d = d.sort_values(["salary_lpa", "_score"], ascending=[False, False])
        elif sort == "newest" or not terms:
            d = d.sort_values(["posted_days_ago", "_score"], ascending=[True, False])
        else:
            d = d.sort_values(["_score", "posted_days_ago"], ascending=[False, True])
        pg = paginate(len(d), _to_int(request.args.get("page")))
        results = d.iloc[pg["start"]:pg["end"]].drop(columns=["_score"]).to_dict("records")
        labels = {"category": "Category", "location": "Location", "experience": "Experience",
                  "job_type": "Type", "min_salary": "Min salary"}
        for k, label in labels.items():
            if f[k]:
                rest = {a: b for a, b in request.args.items() if a not in (k, "page") and b}
                active.append({"label": f"{label}: {f[k]}" + (" LPA" if k == "min_salary" else ""),
                               "url": url_for("search", **rest)})
    top_cats = df["category"].value_counts().head(8)
    return render_template(
        "search.html", results=results, query=q, f=f, sort=sort, sorts=SORTS, searched=searched,
        pg=pg, active=active, total_jobs=len(df),
        qargs={a: b for a, b in request.args.items() if a != "page" and b},
        categories=sorted(c for c in df["category"].unique() if c),
        experience_levels=sorted(e for e in df["experience_required"].unique() if e),
        job_types=sorted(j for j in df["job_type"].unique() if j),
        locations=sorted(l for l in df["location"].unique() if l and l != "Not specified"),
        top_categories=list(top_cats.items()),
        top_locations=[l for l in df["location"].value_counts().index.tolist() if l and l != "Not specified"][:5])



# ══════════════════════════════════════════════════════════════
#  ACCOUNT: settings, password change, export, delete, reset
# ══════════════════════════════════════════════════════════════
def _check_new_password(pw, confirm):
    if len(pw) < 8:
        return "Password must be at least 8 characters."
    if pw != confirm:
        return "The two passwords don't match."
    return None


def _purge_user(db, user_id):
    files = [r["resume_filename"] for r in db.execute(
        "SELECT resume_filename FROM user_profiles WHERE user_id=?", (user_id,))]
    for t in ("saved_jobs", "applied_jobs", "credentials", "user_profiles"):
        db.execute(f"DELETE FROM {t} WHERE user_id=?", (user_id,))
    db.execute("DELETE FROM users WHERE id=?", (user_id,))
    db.commit()
    for f in files:
        _remove_upload(f)


@app.route("/account")
@login_required
def account():
    db   = get_db()
    user = db.execute("SELECT id, name, email, created_at, is_admin FROM users WHERE id=?",
                      (session["user_id"],)).fetchone()
    counts = {t: db.execute(f"SELECT COUNT(*) FROM {t} WHERE user_id=?", (user["id"],)).fetchone()[0]
              for t in ("saved_jobs", "applied_jobs", "credentials")}
    return render_template("account.html", user=user, counts=counts)


@app.route("/account/name", methods=["POST"])
@login_required
def account_name():
    name = " ".join(request.form.get("name", "").split())
    if not 2 <= len(name) <= 60:
        flash("Please enter a name between 2 and 60 characters.", "danger")
        return redirect(url_for("account"))
    db = get_db()
    db.execute("UPDATE users SET name=? WHERE id=?", (name, session["user_id"]))
    db.commit()
    session["user_name"] = name
    flash("Your name was updated.", "success")
    return redirect(url_for("account"))


@app.route("/account/password", methods=["POST"])
@login_required
def account_password():
    key = f"pwchange|{session['user_id']}"
    if _throttled(key):
        flash("Too many attempts. Please wait a few minutes.", "danger")
        return redirect(url_for("account"))
    db   = get_db()
    user = db.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
    cur, new, conf = (request.form.get(k, "") for k in ("current_password", "new_password", "confirm_password"))
    if not verify_password(user["password"], cur):
        _record_fail(key)
        flash("Your current password is incorrect.", "danger")
        return redirect(url_for("account"))
    err = _check_new_password(new, conf) or ("Choose a password different from your current one." if new == cur else None)
    if err:
        flash(err, "danger")
        return redirect(url_for("account"))
    db.execute("UPDATE users SET password=? WHERE id=?", (hash_password(new), user["id"]))
    db.commit()
    flash("Password changed. Any password-reset links sent earlier are now invalid.", "success")
    return redirect(url_for("account"))


@app.route("/account/export")
@login_required
def account_export():
    db, uid = get_db(), session["user_id"]
    rows = lambda q: [dict(r) for r in db.execute(q, (uid,)).fetchall()]  # noqa: E731
    data = {
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "account": rows("SELECT id, name, email, created_at FROM users WHERE id=?")[0],
        "profile": (rows("SELECT * FROM user_profiles WHERE user_id=?") or [None])[0],
        "saved_jobs": rows("SELECT job_id, saved_at FROM saved_jobs WHERE user_id=?"),
        "applications": rows("SELECT job_id, job_title, company, applied_at, status, notes, app_hash, tx_hash, "
                             "block_number FROM applied_jobs WHERE user_id=?"),
        "credentials": rows("SELECT title, issuer_name, skills, issued_on, status, cred_hash, tx_hash, salt "
                            "FROM credentials WHERE user_id=?"),
    }
    return Response(json.dumps(data, indent=2, default=str), mimetype="application/json",
                    headers={"Content-Disposition": "attachment; filename=careerai-my-data.json"})


@app.route("/account/delete", methods=["POST"])
@login_required
def account_delete():
    db   = get_db()
    user = db.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
    if user["is_admin"]:
        flash("Administrator accounts can't be deleted here.", "warning")
        return redirect(url_for("account"))
    key = f"acctdel|{user['id']}"
    if _throttled(key) or not verify_password(user["password"], request.form.get("password", "")) \
            or request.form.get("confirm") != "DELETE":
        _record_fail(key)
        flash("To delete your account, enter your password and type DELETE.", "danger")
        return redirect(url_for("account"))
    _purge_user(db, user["id"])
    session.clear()
    flash("Your account and data were permanently deleted.", "info")
    return redirect(url_for("home"))


# ── forgot / reset password ──────────────────────────────────
def _reset_serializer():
    return URLSafeTimedSerializer(app.secret_key, salt="password-reset")


def _fingerprint(user):
    return hashlib.sha256((user["password"] or "").encode()).hexdigest()[:16]


def _reset_link(user):
    token = _reset_serializer().dumps({"uid": user["id"], "fp": _fingerprint(user)})
    path  = url_for("reset_password", token=token)
    base  = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")     # set in production (Host-header safety)
    return (base + path) if base else url_for("reset_password", token=token, _external=True)


def _user_from_token(token, max_age=3600):
    """-> user row, or None if the link is invalid, expired, or already used."""
    try:
        data = _reset_serializer().loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None
    user = get_db().execute("SELECT * FROM users WHERE id=?", (data.get("uid"),)).fetchone()
    return user if user and hmac.compare_digest(data.get("fp", ""), _fingerprint(user)) else None


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        key = f"reset|{request.remote_addr}"
        if _throttled(key):
            flash("Too many requests. Please try again in a few minutes.", "danger")
            return redirect(url_for("forgot_password"))
        _record_fail(key)                         # counts every request, not only failures
        user = get_db().execute("SELECT * FROM users WHERE email=?", (email,)).fetchone() if email else None
        if user:
            link = _reset_link(user)
            body = (f"Hi {user['name']},\n\nUse this link to choose a new CareerAI password. "
                    f"It works once and expires in 1 hour:\n\n{link}\n\n"
                    "If you didn't ask for this, ignore this email — your password stays the same.\n")
            if not mailer.send_mail(user["email"], "Reset your CareerAI password", body):
                log.warning("Email not sent (SMTP not configured or failing). Reset link for %s: %s", email, link)
                if os.environ.get("DEV_SHOW_RESET_LINK") == "1" and not mailer.is_configured():
                    flash(f"Development mode — reset link: {link}", "info")
        # same answer whether or not the address exists (no account enumeration)
        flash("If an account exists for that email, a reset link is on its way. It expires in 1 hour.", "info")
        return redirect(url_for("login"))
    return render_template("forgot_password.html")


@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    user = _user_from_token(token)
    if not user:
        return render_template("reset_password.html", valid=False), 400
    if request.method == "POST":
        err = _check_new_password(request.form.get("new_password", ""), request.form.get("confirm_password", ""))
        if err:
            flash(err, "danger")
            return render_template("reset_password.html", valid=True, token=token), 400
        db = get_db()
        db.execute("UPDATE users SET password=? WHERE id=?",
                   (hash_password(request.form["new_password"]), user["id"]))
        db.commit()
        flash("Password updated — you can sign in now.", "success")
        return redirect(url_for("login"))
    return render_template("reset_password.html", valid=True, token=token)

# ══════════════════════════════════════════════════════════════
#  ADMIN ROUTES
# ══════════════════════════════════════════════════════════════

@app.route("/admin")
@admin_required
def admin_dashboard():
    db            = get_db()
    total_users   = db.execute("SELECT COUNT(*) as c FROM users WHERE is_admin=0").fetchone()["c"]
    total_jobs    = len(MODELS["jobs_df"])
    total_saved   = db.execute("SELECT COUNT(*) as c FROM saved_jobs").fetchone()["c"]
    total_applied = db.execute("SELECT COUNT(*) as c FROM applied_jobs").fetchone()["c"]
    recent_users  = db.execute(
        "SELECT name, email, created_at FROM users WHERE is_admin=0 ORDER BY created_at DESC LIMIT 8"
    ).fetchall()
    cat_stats = get_category_stats(MODELS)
    loc_stats = get_location_stats(MODELS)
    exp_stats = get_experience_stats(MODELS)
    return render_template("admin_dashboard.html",
                           total_users=total_users,
                           total_jobs=total_jobs,
                           total_saved=total_saved,
                           total_applied=total_applied,
                           recent_users=recent_users,
                           cat_stats=json.dumps(cat_stats),
                           loc_stats=json.dumps(loc_stats),
                           exp_stats=json.dumps(exp_stats))


@app.route("/admin/analytics")
@admin_required
def admin_analytics():
    db          = get_db()
    top_saved   = db.execute("""
        SELECT job_id, COUNT(*) as cnt FROM saved_jobs
        GROUP BY job_id ORDER BY cnt DESC LIMIT 10
    """).fetchall()
    top_applied = db.execute("""
        SELECT job_title, company, COUNT(*) as cnt FROM applied_jobs
        GROUP BY job_title, company ORDER BY cnt DESC LIMIT 10
    """).fetchall()
    signups     = db.execute("""
        SELECT DATE(created_at) as day, COUNT(*) as cnt
        FROM users WHERE is_admin=0
        GROUP BY day ORDER BY day DESC LIMIT 7
    """).fetchall()
    cat_stats = get_category_stats(MODELS)
    loc_stats = get_location_stats(MODELS)
    exp_stats = get_experience_stats(MODELS)
    df = MODELS["jobs_df"]
    model_stats = [
        ("Jobs in Pool", f"{len(df):,}", "Dataset + admin + live jobs"),
        ("Categories", str(df["category"].nunique()), "Job categories"),
        ("Live Jobs", f"{int((~df['source'].isin(['dataset', 'admin'])).sum()):,}", "From external APIs"),
        ("Skills Known", str(len(MODELS["skill_vocab"])), "Normalised skill vocabulary"),
    ]
    return render_template("admin_analytics.html", model_stats=model_stats,
                           top_saved=top_saved,
                           top_applied=top_applied,
                           signups=signups,
                           cat_stats=json.dumps(cat_stats),
                           loc_stats=json.dumps(loc_stats),
                           exp_stats=json.dumps(exp_stats))


@app.route("/admin/jobs")
@admin_required
def admin_jobs():
    jobs_df = MODELS["jobs_df"]
    db      = get_db()
    custom  = db.execute("SELECT * FROM custom_jobs ORDER BY created_at DESC").fetchall()
    return render_template("admin_jobs.html",
                           dataset_jobs=jobs_df[jobs_df["source"] == "dataset"].to_dict("records"),
                           custom_jobs=custom)


@app.route("/admin/add_job", methods=["POST"])
@admin_required
def admin_add_job():
    db = get_db()
    if not all(request.form.get(k, "").strip() for k in ("title", "company", "skills")):
        flash("Title, company and skills are required.", "danger")
        return redirect(url_for("admin_jobs"))
    db.execute("""
        INSERT INTO custom_jobs
            (title, company, skills_required, category, description,
             location, experience_required, education_required,
             salary_range, salary_lpa, job_type, openings, added_by_admin)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        request.form["title"], request.form["company"],
        request.form["skills"], request.form["category"],
        request.form["description"], request.form["location"],
        request.form["experience"], request.form["education"],
        request.form["salary_range"],
        float(request.form.get("salary_lpa", 0) or 0),
        request.form.get("job_type", "Full-time"),
        int(request.form.get("openings", 1) or 1),
        session["user_id"]
    ))
    db.commit()
    flash("Job added successfully!", "success")
    return redirect(url_for("admin_jobs"))


@app.route("/admin/delete_job/<int:job_id>", methods=["POST"])
@admin_required
def admin_delete_job(job_id):
    db = get_db()
    db.execute("DELETE FROM custom_jobs WHERE id=?", (job_id,))
    db.commit()
    flash("Job deleted.", "info")
    return redirect(url_for("admin_jobs"))


@app.route("/admin/users")
@admin_required
def admin_users():
    db    = get_db()
    users = db.execute("""
        SELECT u.id, u.name, u.email, u.created_at,
               p.skills, p.experience, p.domain,
               (SELECT COUNT(*) FROM saved_jobs s WHERE s.user_id=u.id) as saved,
               (SELECT COUNT(*) FROM applied_jobs a WHERE a.user_id=u.id) as applied
        FROM users u
        LEFT JOIN user_profiles p ON p.user_id=u.id
        WHERE u.is_admin=0
        ORDER BY u.created_at DESC
    """).fetchall()
    return render_template("admin_users.html", users=users)


@app.route("/admin/delete_user/<int:user_id>", methods=["POST"])
@admin_required
def admin_delete_user(user_id):
    db = get_db()
    resume_files = [r["resume_filename"] for r in db.execute(
        "SELECT resume_filename FROM user_profiles WHERE user_id=?", (user_id,))]
    target = db.execute("SELECT is_admin FROM users WHERE id=?", (user_id,)).fetchone()
    if target is None:
        abort(404)
    if target["is_admin"]:
        abort(403)
    db.execute("DELETE FROM users WHERE id=?", (user_id,))
    db.execute("DELETE FROM user_profiles WHERE user_id=?", (user_id,))
    db.execute("DELETE FROM saved_jobs WHERE user_id=?", (user_id,))
    db.execute("DELETE FROM applied_jobs WHERE user_id=?", (user_id,))
    db.execute("DELETE FROM credentials WHERE user_id=?", (user_id,))
    db.commit()
    for f in resume_files:
        _remove_upload(f)
    flash("User deleted.", "info")
    return redirect(url_for("admin_users"))


@app.route("/admin/upload_csv", methods=["POST"])
@admin_required
def admin_upload_csv():
    file = request.files.get("csv_file")
    if not file or not file.filename.lower().endswith(".csv"):
        flash("Please upload a valid CSV file.", "danger")
        return redirect(url_for("admin_jobs"))
    db      = get_db()
    content = file.read().decode("utf-8-sig", errors="replace")
    reader  = csv_mod.DictReader(io.StringIO(content))
    count   = 0
    for row in reader:
        try:
            db.execute("""
                INSERT INTO custom_jobs
                    (title, company, skills_required, category, description,
                     location, experience_required, education_required,
                     salary_range, salary_lpa, job_type, openings, added_by_admin)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                row.get("title",""), row.get("company",""),
                row.get("skills_required",""), row.get("category",""),
                row.get("description",""), row.get("location",""),
                row.get("experience_required",""), row.get("education_required",""),
                row.get("salary_range",""),
                float(row.get("salary_lpa", 0) or 0),
                row.get("job_type","Full-time"),
                int(row.get("openings", 1) or 1),
                session["user_id"]
            ))
            count += 1
        except Exception:
            continue
    db.commit()
    flash(f"Imported {count} jobs from CSV.", "success")
    return redirect(url_for("admin_jobs"))


@app.route("/admin/export_users")
@admin_required
def admin_export_users():
    db    = get_db()
    users = db.execute("""
        SELECT u.id, u.name, u.email, u.created_at,
               p.skills, p.experience, p.education, p.domain, p.location
        FROM users u LEFT JOIN user_profiles p ON p.user_id=u.id
        WHERE u.is_admin=0
    """).fetchall()
    output = io.StringIO()
    writer = csv_mod.writer(output)
    writer.writerow(["ID","Name","Email","Joined","Skills",
                     "Experience","Education","Domain","Location"])
    for u in users:
        writer.writerow([u["id"], u["name"], u["email"], u["created_at"],
                         u["skills"], u["experience"], u["education"],
                         u["domain"], u["location"]])
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=users_export.csv"}
    )

# ══════════════════════════════════════════════════════════════
#  API ENDPOINTS
# ══════════════════════════════════════════════════════════════

@app.route("/api/stats")
def api_stats():
    jobs_df = MODELS["jobs_df"]
    return jsonify({
        "total_jobs": len(jobs_df),
        "categories": int(jobs_df["category"].nunique()),
        "locations":  int(jobs_df["location"].nunique()),
    })


@app.route("/api/job/<int:job_id>")
def api_job_detail(job_id):
    jobs_df = MODELS["jobs_df"]
    row     = jobs_df[jobs_df["job_id"] == job_id]
    if row.empty:
        return jsonify({"error": "Not found"}), 404
    return jsonify(row.iloc[0].to_dict())


@app.route("/api/recommend", methods=["POST"])
@login_required
def api_recommend():
    data         = request.get_json(silent=True) or {}
    profile_text = build_user_profile_text(
        data.get("skills",""), data.get("experience",""),
        data.get("education",""), data.get("domain",""),
        data.get("location",""), data.get("goals","")
    )
    have = collect_user_skills(MODELS, data.get("skills", ""),
                               data.get("goals", ""))
    recs = get_recommendations(MODELS, profile_text,
                               top_n=int(data.get("top_n", 10)), user_skills=have)
    return jsonify({"recommendations": recs, "count": len(recs)})


# ══════════════════════════════════════════════════════════════
#  LIVE JOB POOL  (CSV jobs + jobs added by the admin)
# ══════════════════════════════════════════════════════════════
_POOL_LOCK = threading.Lock()


@app.before_request
def keep_pool_fresh():
    """Admin-added jobs and live API jobs are merged into the recommendation pool.
    Every request does two tiny fingerprint queries; the pool is rebuilt only when
    something changed (so every gunicorn worker picks up changes made elsewhere)."""
    if request.endpoint in (None, "static"):
        return
    try:
        db  = get_db()
        c   = db.execute("SELECT COUNT(*), COALESCE(SUM(id),0), COALESCE(MAX(id),0) "
                         "FROM custom_jobs").fetchone()
        lv  = db.execute("SELECT COUNT(*), COALESCE(SUM(id),0), COALESCE(MAX(updated_at),'') "
                         "FROM live_jobs").fetchone()
        sig = f"{tuple(c)}|{tuple(lv)}"
        if sig != MODELS.get("pool_sig"):
            with _POOL_LOCK:
                if sig != MODELS.get("pool_sig"):
                    custom = db.execute("SELECT * FROM custom_jobs ORDER BY id").fetchall()
                    livers = db.execute("SELECT * FROM live_jobs ORDER BY id").fetchall()
                    refresh_job_pool(MODELS, custom, livers)
                    MODELS["pool_sig"] = sig
                    log.info("Job pool refreshed: %d jobs (%d admin, %d live)",
                             len(MODELS["jobs_df"]), len(custom), len(livers))
    except Exception:  # noqa: BLE001 - never take the site down over this
        log.exception("Could not refresh job pool")


@app.context_processor
def inject_live_sources():
    """Which live providers currently have jobs in the pool (for attribution)."""
    try:
        return {"live_sources": set(MODELS["jobs_df"]["source"].unique()) - {"dataset", "admin"}}
    except Exception:  # noqa: BLE001
        return {"live_sources": set()}


# ══════════════════════════════════════════════════════════════
#  COLLABORATIVE FILTERING  (rebuilt only when saves/applies change)
# ══════════════════════════════════════════════════════════════
_COLLAB = {"sig": None, "model": None}
_COLLAB_LOCK = threading.Lock()


def get_collab(db):
    sig = interactions_signature(db)
    if sig != _COLLAB["sig"]:
        with _COLLAB_LOCK:
            if sig != _COLLAB["sig"]:
                _COLLAB["model"] = CollabModel(interactions_from_db(db))
                _COLLAB["sig"] = sig
    return _COLLAB["model"]


def _cf_explainer(collab, user_id):
    def explain(job_id):
        ex = collab.explain(user_id, job_id)
        if not ex:
            return "Popular with users like you"
        src, kind = ex
        df = MODELS["jobs_df"]
        r  = df[df["job_id"] == src]
        title = str(r.iloc[0]["title"])[:40] if not r.empty else "a job you viewed"
        return f"Because you {kind} {title}"
    return explain


# ══════════════════════════════════════════════════════════════
#  LIVE JOB DATA  (admin)
# ══════════════════════════════════════════════════════════════
@app.route("/admin/live_jobs")
@admin_required
def admin_live_jobs():
    db, providers = get_db(), []
    for name, cls in live.PROVIDERS.items():
        p = cls()
        providers.append({
            "name": name, "label": p.label, "configured": p.is_configured(),
            "needs_key": p.needs_key, "interval": p.min_interval_hours,
            "attribution": p.attribution_text,
            "count": db.execute("SELECT COUNT(*) FROM live_jobs WHERE source=?", (name,)).fetchone()[0],
            "last": db.execute("SELECT * FROM sync_log WHERE source=? ORDER BY id DESC LIMIT 1",
                               (name,)).fetchone()})
    logs = db.execute("SELECT * FROM sync_log ORDER BY id DESC LIMIT 15").fetchall()
    return render_template("admin_live_jobs.html", providers=providers, logs=logs,
                           queries=", ".join(live.default_queries(db)),
                           total=sum(p["count"] for p in providers),
                           ttl=live.TTL_DAYS, max_jobs=live.MAX_JOBS)


@app.route("/admin/live_jobs/sync", methods=["POST"])
@admin_required
def admin_live_sync():
    names    = [n for n in request.form.getlist("provider") if n in live.PROVIDERS] or None
    queries  = [q.strip() for q in request.form.get("queries", "").split(",") if q.strip()][:8] or None
    location = request.form.get("location", "").strip()[:80]
    results  = live.sync_live_jobs(get_db(), MODELS, providers=names, queries=queries,
                                   location=location)
    for r in results:
        label = live.PROVIDERS[r["provider"]].label
        if r["status"] == "ok":
            flash(f"{label}: fetched {r['fetched']} · new {r['inserted']} · updated "
                  f"{r['updated']} · removed {r['pruned']}", "success")
        else:
            flash(f"{label}: {r['status']} — {r['message']}", "warning")
    return redirect(url_for("admin_live_jobs"))


@app.route("/admin/live_jobs/purge", methods=["POST"])
@admin_required
def admin_live_purge():
    source = request.form.get("provider", "")
    if source not in live.PROVIDERS:
        abort(400)
    db = get_db()
    n = db.execute(f"DELETE FROM live_jobs WHERE source=? {live._NOT_REFERENCED}",
                   (source, live.LIVE_JOB_OFFSET, live.LIVE_JOB_OFFSET)).rowcount
    db.commit()
    flash(f"Removed {n} {live.PROVIDERS[source].label} jobs (jobs users saved or applied to are kept).", "info")
    return redirect(url_for("admin_live_jobs"))


# ══════════════════════════════════════════════════════════════
#  BLOCKCHAIN CREDENTIALS  (hashes only on-chain, data off-chain)
# ══════════════════════════════════════════════════════════════
HASH_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def verified_skills_for_user(db, user_id):
    """Skills backed by a non-revoked, on-chain credential."""
    out = set()
    for r in db.execute("SELECT skills FROM credentials WHERE user_id=? "
                        "AND status='issued'", (user_id,)):
        out |= parse_skill_list(r["skills"])
    return out


def _live_status(h):
    if not chain.enabled:
        return {"error": "Blockchain is disabled on this server."}
    try:
        return chain.verify_credential(h)
    except ChainError as e:
        return {"error": str(e)}


def _fmt_ts(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC") if ts else "—"


app.jinja_env.filters["fmt_ts"] = _fmt_ts


def _record_integrity(row):
    """Re-hash the stored fields; True if they still produce the anchored hash
    (i.e. the database record was not edited after issuing)."""
    skills = [x.strip() for x in (row["skills"] or "").split(",") if x.strip()]
    return credential_hash(row["user_id"], row["title"], row["issuer_name"],
                           skills, row["issued_on"], row["salt"]) == row["cred_hash"]


@app.route("/credentials")
@login_required
def my_credentials():
    db   = get_db()
    rows = db.execute("SELECT * FROM credentials WHERE user_id=? ORDER BY id DESC",
                      (session["user_id"],)).fetchall()
    items = []
    for r in rows:
        live = _live_status(r["cred_hash"])
        items.append({"row": r, "live": live,
                      "valid": bool(live.get("exists")) and not live.get("revoked"),
                      "intact": _record_integrity(r)})
    return render_template("credentials.html", items=items, chain_info=chain.status())


@app.route("/verify")
def verify_form():
    h = request.args.get("hash", "").strip().lower()
    if h:
        if HASH_RE.match(h):
            return redirect(url_for("verify_credential", cred_hash=h))
        flash("A credential hash is 64 hexadecimal characters.", "warning")
    return render_template("verify.html", cred_hash="", result=None, row=None,
                           chain_info=chain.status())


@app.route("/verify/<cred_hash>")
def verify_credential(cred_hash):
    h = cred_hash.lower()
    if not HASH_RE.match(h):
        abort(404)
    row = get_db().execute(
        "SELECT c.*, u.name AS holder FROM credentials c JOIN users u ON u.id=c.user_id "
        "WHERE c.cred_hash=?", (h,)).fetchone()
    return render_template("verify.html", cred_hash=h, result=_live_status(h), row=row,
                           intact=_record_integrity(row) if row else None,
                           chain_info=chain.status())


@app.route("/admin/credentials")
@admin_required
def admin_credentials():
    db    = get_db()
    users = db.execute("SELECT id, name, email FROM users WHERE is_admin=0 "
                       "ORDER BY name").fetchall()
    creds = db.execute("SELECT c.*, u.name AS holder, u.email FROM credentials c "
                       "JOIN users u ON u.id=c.user_id ORDER BY c.id DESC").fetchall()
    return render_template("admin_credentials.html", users=users, creds=creds,
                           chain_info=chain.status(),
                           today=datetime.now(timezone.utc).strftime("%Y-%m-%d"))


@app.route("/admin/issue_credential", methods=["POST"])
@admin_required
def admin_issue_credential():
    db = get_db()
    title  = request.form.get("title", "").strip()
    issuer = request.form.get("issuer_name", "").strip()
    skills = [x.strip() for x in request.form.get("skills", "").split(",") if x.strip()]
    on     = request.form.get("issued_on", "").strip() or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        user_id = int(request.form.get("user_id", ""))
    except ValueError:
        user_id = None
    holder = db.execute("SELECT id FROM users WHERE id=? AND is_admin=0",
                        (user_id,)).fetchone() if user_id else None
    if not (holder and title and issuer and skills):
        flash("Choose a user and fill in title, issuer and at least one skill.", "danger")
        return redirect(url_for("admin_credentials"))
    if not chain.enabled:
        flash("Blockchain is disabled (BLOCKCHAIN_MODE=off).", "danger")
        return redirect(url_for("admin_credentials"))
    salt = secrets.token_hex(16)
    h    = credential_hash(user_id, title, issuer, skills, on, salt)
    try:
        res = chain.issue_credential(h)
    except ChainError as e:
        flash(f"Blockchain error — credential NOT issued: {e}", "danger")
        return redirect(url_for("admin_credentials"))
    db.execute("""INSERT INTO credentials (user_id, title, issuer_name, skills, issued_on,
                  salt, cred_hash, tx_hash, block_number, status, issued_by)
                  VALUES (?,?,?,?,?,?,?,?,?,'issued',?)""",
               (user_id, title, issuer, ", ".join(skills), on, salt, h,
                res["tx_hash"], res["block"], session["user_id"]))
    db.commit()
    flash("Credential issued and anchored on the blockchain.", "success")
    return redirect(url_for("admin_credentials"))


@app.route("/admin/revoke_credential/<int:cred_id>", methods=["POST"])
@admin_required
def admin_revoke_credential(cred_id):
    db  = get_db()
    row = db.execute("SELECT * FROM credentials WHERE id=?", (cred_id,)).fetchone()
    if not row or row["status"] != "issued":
        flash("Credential not found or already revoked.", "warning")
        return redirect(url_for("admin_credentials"))
    try:
        res = chain.revoke_credential(row["cred_hash"])
    except ChainError as e:
        flash(f"Blockchain error — NOT revoked: {e}", "danger")
        return redirect(url_for("admin_credentials"))
    db.execute("UPDATE credentials SET status='revoked', revoke_tx=? WHERE id=?",
               (res["tx_hash"], cred_id))
    db.commit()
    flash("Credential revoked on-chain.", "info")
    return redirect(url_for("admin_credentials"))


def sync_local_chain():
    """The local test chain lives in memory and starts empty on every restart.
    Replay recorded hashes into it so the demo stays consistent. (On a real
    network — BLOCKCHAIN_MODE=remote — nothing is replayed: the chain IS the
    source of truth.)"""
    if chain.mode != "local":
        return
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    try:
        for r in db.execute("SELECT * FROM credentials WHERE status IN ('issued','revoked')").fetchall():
            res = chain.issue_credential(r["cred_hash"])
            if r["status"] == "revoked":
                chain.revoke_credential(r["cred_hash"])
            db.execute("UPDATE credentials SET tx_hash=?, block_number=? WHERE id=?",
                       (res["tx_hash"], res["block"], r["id"]))
        for r in db.execute("SELECT * FROM applied_jobs WHERE app_hash IS NOT NULL").fetchall():
            res = chain.anchor_application(r["app_hash"])
            db.execute("UPDATE applied_jobs SET tx_hash=?, block_number=? WHERE id=?",
                       (res["tx_hash"], res["block"], r["id"]))
        db.commit()
    except ChainError as e:
        log.warning("Local chain replay skipped: %s", e)
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════
#  SITE SHELL: content pages, SEO files, security headers, errors
# ══════════════════════════════════════════════════════════════
@app.context_processor
def inject_site():
    return {"current_year": datetime.now(timezone.utc).year,
            "site_contact_email": os.environ.get("CONTACT_EMAIL", ""),
            "nav_updates": _nav_updates()}


def _nav_updates():
    """Number of unseen recruiter updates on the signed-in user's applications."""
    uid = session.get("user_id")
    if not uid or session.get("is_admin"):
        return 0
    try:
        return get_db().execute("SELECT COUNT(*) FROM applied_jobs WHERE user_id=? AND user_notified=0",
                                (uid,)).fetchone()[0]
    except Exception:  # noqa: BLE001
        return 0


@app.route("/about")
def about():
    return render_template("page_about.html")


@app.route("/faq")
def faq():
    return render_template("page_faq.html")


@app.route("/privacy")
def privacy():
    return render_template("page_privacy.html")


@app.route("/terms")
def terms():
    return render_template("page_terms.html")


@app.route("/robots.txt")
def robots_txt():
    body = ("User-agent: *\nDisallow: /admin\nDisallow: /api/\nDisallow: /account\n"
            f"Sitemap: {url_for('sitemap_xml', _external=True)}\n")
    return Response(body, mimetype="text/plain")


@app.route("/sitemap.xml")
def sitemap_xml():
    pages = ["home", "about", "faq", "privacy", "terms", "login", "register", "verify_form"]
    urls = "".join(f"<url><loc>{url_for(p, _external=True)}</loc></url>" for p in pages)
    return Response('<?xml version="1.0" encoding="UTF-8"?>'
                    f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>',
                    mimetype="application/xml")


@app.after_request
def security_headers(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    resp.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if app.config.get("SESSION_COOKIE_SECURE"):
        resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    if session.get("user_id") and resp.mimetype == "text/html":
        resp.headers["Cache-Control"] = "no-store"      # signed-in pages must not sit in shared caches
    return resp


_ERRORS = {
    400: ("Request couldn't be processed", "Something about that request wasn't valid. Please go back and try again."),
    403: ("Access denied", "You don't have permission to view this page."),
    404: ("Page not found", "The page you're looking for doesn't exist or has moved."),
    405: ("Method not allowed", "That action isn't available from this page."),
    413: ("File too large", "That upload is too big. The limit is 5 MB."),
    429: ("Too many requests", "Please slow down and try again in a moment."),
    500: ("Something went wrong", "An unexpected error occurred on our side. Please try again."),
}


def _wants_json():
    return (request.path.startswith("/api/") or request.is_json
            or request.accept_mimetypes.best == "application/json")


def _handle_error(e):
    code = getattr(e, "code", 500) or 500
    title, msg = _ERRORS.get(code, _ERRORS[500])
    if code == 400 and isinstance(getattr(e, "description", None), str) and "token" in e.description.lower():
        msg = e.description                              # the CSRF message is already user-friendly
    if _wants_json():
        return jsonify({"status": "error", "code": code, "message": msg}), code
    return render_template("error.html", code=code, title=title, msg=msg), code


for _code in _ERRORS:
    app.register_error_handler(_code, _handle_error)

# Runs on import so it also works under gunicorn (previously only `python app.py`)
init_db()
sync_local_chain()

# ══════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("\n" + "="*50)
    print("  Job Recommendation System is RUNNING!")
    print("  URL: http://127.0.0.1:5000")
    print("  Admin login: see ADMIN_EMAIL / ADMIN_PASSWORD (or the one-time")
    print("  password printed above on first run)")
    print("="*50 + "\n")
    app.run(debug=os.environ.get("FLASK_DEBUG", "0") == "1", port=5000)