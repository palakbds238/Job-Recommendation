"""
app.py
------
ML-Based Job Recommendation System — Complete Flask Application
All routes in correct order. No missing endpoints.
"""

from flask import (Flask, render_template, request, redirect,
                   url_for, session, jsonify, flash, g, Response)
import sqlite3, hashlib, os, json, io, csv as csv_mod
from werkzeug.utils import secure_filename
from model import (load_models, build_user_profile_text,
                   get_recommendations, predict_category,
                   get_category_stats, get_location_stats,
                   get_experience_stats)

# ══════════════════════════════════════════════════════════════
#  APP CONFIG
# ══════════════════════════════════════════════════════════════
app = Flask(__name__)
app.secret_key = "jobrecsys_secret_2024_college_project"
app.config["UPLOAD_FOLDER"] = "uploads"
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024
ALLOWED_EXTENSIONS = {"pdf", "txt"}
os.makedirs("uploads", exist_ok=True)

print("Loading ML models...")
MODELS = load_models()

# ══════════════════════════════════════════════════════════════
#  DATABASE
# ══════════════════════════════════════════════════════════════
DB_PATH = "job_recommender.db"

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
        """)
        admin_pw = hash_password("admin123")
        db.execute(
            "INSERT OR IGNORE INTO users (name, email, password, is_admin) VALUES (?,?,?,?)",
            ("Administrator", "admin@jobrec.com", admin_pw, 1)
        )
        db.commit()
        db.close()
    print("Database initialized")

# ══════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════
def hash_password(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

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
        except ImportError:
            return ""
    return ""

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
        user     = db.execute(
            "SELECT * FROM users WHERE email=? AND password=?",
            (email, hash_password(password))
        ).fetchone()
        if not user:
            flash("Invalid email or password.", "danger")
            return redirect(url_for("login"))
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
    return render_template("dashboard.html",
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
                filename        = secure_filename(file.filename)
                filepath        = os.path.join(app.config["UPLOAD_FOLDER"], filename)
                file.save(filepath)
                resume_text     = extract_resume_text(filepath)
                resume_filename = filename
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
    return render_template("profile.html", profile=current)


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
    f_location = request.args.get("location", "")
    f_exp      = request.args.get("experience", "")
    f_cat      = request.args.get("category", "")
    f_salary   = request.args.get("min_salary", "")
    recs = get_recommendations(
        MODELS, profile_text, top_n=30,
        filter_location=f_location,
        filter_experience=f_exp,
        filter_category=f_cat,
        min_salary=f_salary if f_salary else None
    )
    saved_ids = set(
        r["job_id"] for r in db.execute(
            "SELECT job_id FROM saved_jobs WHERE user_id=?", (user_id,)
        ).fetchall()
    )
    jobs_df  = MODELS["jobs_df"]
    cats     = sorted(jobs_df["category"].unique().tolist())
    locs     = sorted(jobs_df["location"].unique().tolist())
    exp_lvls = sorted(jobs_df["experience_required"].unique().tolist())
    return render_template("recommendations.html",
                           recommendations=recs,
                           saved_ids=saved_ids,
                           profile=profile,
                           categories=cats,
                           locations=locs,
                           experience_levels=exp_lvls,
                           filters={
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
                           is_applied=is_applied, similar_jobs=similar)


@app.route("/save_job", methods=["POST"])
@login_required
def save_job():
    data    = request.get_json()
    job_id  = data.get("job_id")
    user_id = session["user_id"]
    db      = get_db()
    try:
        db.execute(
            "INSERT OR IGNORE INTO saved_jobs (user_id, job_id) VALUES (?,?)",
            (user_id, job_id)
        )
        db.commit()
        return jsonify({"status": "saved"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/unsave_job", methods=["POST"])
@login_required
def unsave_job():
    data    = request.get_json()
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
    data    = request.get_json()
    job_id  = data.get("job_id")
    title   = data.get("title", "")
    company = data.get("company", "")
    user_id = session["user_id"]
    db      = get_db()
    existing = db.execute(
        "SELECT id FROM applied_jobs WHERE user_id=? AND job_id=?", (user_id, job_id)
    ).fetchone()
    if not existing:
        db.execute(
            "INSERT INTO applied_jobs (user_id, job_id, job_title, company) VALUES (?,?,?,?)",
            (user_id, job_id, title, company)
        )
        db.commit()
        return jsonify({"status": "applied",
                        "message": f"Applied to {title} at {company}!"})
    return jsonify({"status": "already_applied",
                    "message": "You already applied to this job."})


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


@app.route("/applied_jobs")
@login_required
def applied_jobs():
    db      = get_db()
    user_id = session["user_id"]
    applied = db.execute(
        "SELECT * FROM applied_jobs WHERE user_id=? ORDER BY applied_at DESC",
        (user_id,)
    ).fetchall()
    return render_template("applied_jobs.html", applied_jobs=applied)


@app.route("/search")
@login_required
def search():
    query   = request.args.get("q", "").strip()
    jobs_df = MODELS["jobs_df"]
    results = []
    if query:
        mask = (
            jobs_df["title"].str.lower().str.contains(query.lower(), na=False) |
            jobs_df["company"].str.lower().str.contains(query.lower(), na=False) |
            jobs_df["skills_required"].str.lower().str.contains(query.lower(), na=False) |
            jobs_df["category"].str.lower().str.contains(query.lower(), na=False)
        )
        results = jobs_df[mask].head(20).to_dict("records")
    return render_template("search.html", results=results, query=query)


@app.route("/profile/delete", methods=["POST"])
@login_required
def delete_account():
    db      = get_db()
    user_id = session["user_id"]
    db.execute("DELETE FROM users WHERE id=?", (user_id,))
    db.execute("DELETE FROM user_profiles WHERE user_id=?", (user_id,))
    db.execute("DELETE FROM saved_jobs WHERE user_id=?", (user_id,))
    db.execute("DELETE FROM applied_jobs WHERE user_id=?", (user_id,))
    db.commit()
    session.clear()
    flash("Your account has been deleted.", "info")
    return redirect(url_for("home"))

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
    return render_template("admin_analytics.html",
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
                           dataset_jobs=jobs_df.to_dict("records"),
                           custom_jobs=custom)


@app.route("/admin/add_job", methods=["POST"])
@admin_required
def admin_add_job():
    db = get_db()
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
    db.execute("DELETE FROM users WHERE id=?", (user_id,))
    db.execute("DELETE FROM user_profiles WHERE user_id=?", (user_id,))
    db.execute("DELETE FROM saved_jobs WHERE user_id=?", (user_id,))
    db.execute("DELETE FROM applied_jobs WHERE user_id=?", (user_id,))
    db.commit()
    flash("User deleted.", "info")
    return redirect(url_for("admin_users"))


@app.route("/admin/upload_csv", methods=["POST"])
@admin_required
def admin_upload_csv():
    file = request.files.get("csv_file")
    if not file or not file.filename.endswith(".csv"):
        flash("Please upload a valid CSV file.", "danger")
        return redirect(url_for("admin_jobs"))
    db      = get_db()
    content = file.read().decode("utf-8")
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
    data         = request.get_json()
    profile_text = build_user_profile_text(
        data.get("skills",""), data.get("experience",""),
        data.get("education",""), data.get("domain",""),
        data.get("location",""), data.get("goals","")
    )
    recs = get_recommendations(MODELS, profile_text,
                               top_n=int(data.get("top_n", 10)))
    return jsonify({"recommendations": recs, "count": len(recs)})

# ══════════════════════════════════════════════════════════════
#  ERROR HANDLERS
# ══════════════════════════════════════════════════════════════

@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", code=404,
                           msg="Page not found."), 404

@app.errorhandler(500)
def server_error(e):
    return render_template("error.html", code=500,
                           msg="Internal server error. Please try again."), 500

# ══════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    init_db()
    print("\n" + "="*50)
    print("  Job Recommendation System is RUNNING!")
    print("  URL: http://127.0.0.1:5000")
    print("  Admin: admin@jobrec.com / admin123")
    print("="*50 + "\n")
    app.run(debug=True, port=5000)