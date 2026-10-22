import hashlib, os, re, sqlite3
from tests.conftest import post, token

DB = lambda: sqlite3.connect(os.environ["DATABASE_PATH"])  # noqa: E731


def test_post_without_csrf_token_is_rejected(app_module):
    c = app_module.app.test_client()
    assert c.post("/login", data={"email": "a@b.c", "password": "x"}).status_code == 400


def test_short_password_rejected(app_module):
    c = app_module.app.test_client()
    r = post(c, "/register", {"name": "X", "email": "short@test.com", "password": "abc"},
             path_for_token="/register", follow_redirects=True)
    assert b"at least 8" in r.data
    assert DB().execute("SELECT 1 FROM users WHERE email='short@test.com'").fetchone() is None


def test_passwords_are_salted_hashes(user):
    pw = DB().execute("SELECT password FROM users WHERE id=?", (user[1],)).fetchone()[0]
    assert "$" in pw and len(pw) != 64


def test_legacy_sha256_password_is_upgraded_on_login(app_module):
    legacy = hashlib.sha256(b"oldpassword1").hexdigest()
    db = DB()
    db.execute("INSERT INTO users (name,email,password) VALUES ('Old','old@test.com',?)", (legacy,))
    db.commit()
    c = app_module.app.test_client()
    r = post(c, "/login", {"email": "old@test.com", "password": "oldpassword1"})
    assert r.status_code == 302
    new = DB().execute("SELECT password FROM users WHERE email='old@test.com'").fetchone()[0]
    assert new != legacy and "$" in new


def test_public_default_admin_password_is_rotated(app_module):
    db = DB()
    db.execute("UPDATE users SET password=? WHERE is_admin=1", (app_module.LEGACY_DEFAULT_ADMIN_HASH,))
    db.commit()
    app_module.init_db()
    c = app_module.app.test_client()
    r = post(c, "/login", {"email": "admin@test.com", "password": "admin123"}, follow_redirects=True)
    assert b"Invalid email or password" in r.data
    r = post(c, "/login", {"email": "admin@test.com", "password": "AdminPass123"})
    assert r.status_code == 302


def test_login_is_throttled(app_module):
    c = app_module.app.test_client()
    for _ in range(6):
        r = post(c, "/login", {"email": "victim@test.com", "password": "wrongwrong"},
                 follow_redirects=True)
    assert b"Too many failed attempts" in r.data


def test_apply_ignores_client_supplied_title(user):
    c, uid = user
    r = c.post("/apply_job", json={"job_id": 1, "title": "HACKED", "company": "EVIL"},
               headers={"X-CSRFToken": token(c, "/dashboard")})
    assert r.get_json()["status"] == "applied"
    title = DB().execute("SELECT job_title, company FROM applied_jobs WHERE user_id=?", (uid,)).fetchone()
    assert title[0] != "HACKED" and title[1] != "EVIL"


def test_apply_is_anchored_on_chain(user, app_module):
    c, uid = user
    c.post("/apply_job", json={"job_id": 2}, headers={"X-CSRFToken": token(c, "/dashboard")})
    h, tx = DB().execute("SELECT app_hash, tx_hash FROM applied_jobs WHERE user_id=?", (uid,)).fetchone()
    assert tx and app_module.chain.application_time(h) > 0
    assert b"Proof recorded" in c.get("/applied_jobs").data


def test_admin_added_job_is_recommended(admin, user):
    post(admin, "/admin/add_job", {
        "title": "Zebra Wrangler Deluxe", "company": "SafariCorp", "skills": "Python, SQL, Flask",
        "category": "Software Engineering", "location": "Indore", "experience": "1-3 years",
        "education": "B.Tech", "salary_range": "9-12 LPA", "salary_lpa": "10", "job_type": "Full-time",
        "openings": "1", "description": "backend python flask sql work"}, path_for_token="/admin")
    c, _ = user
    assert b"Zebra Wrangler Deluxe" in c.get("/recommendations?location=").data


def test_unique_resume_filenames(user, app_module):
    import io
    c, uid = user
    for _ in range(2):
        post(c, "/profile", {"skills": "Python", "resume": (io.BytesIO(b"I know Flask"), "resume.txt")},
             path_for_token="/profile", content_type="multipart/form-data")
    name = DB().execute("SELECT resume_filename FROM user_profiles WHERE user_id=?", (uid,)).fetchone()[0]
    assert name.startswith(f"{uid}_") and name != "resume.txt"
    assert len(os.listdir(app_module.app.config["UPLOAD_FOLDER"])) >= 1


def _issue(admin, uid, skills="Python, SQL", title="Python Certified"):
    return post(admin, "/admin/issue_credential",
                {"user_id": uid, "title": title, "issuer_name": "SVVV Indore",
                 "skills": skills, "issued_on": "2026-10-01"}, path_for_token="/admin")


def test_credential_lifecycle(admin, user, app_module):
    c, uid = user
    _issue(admin, uid)
    h, status = DB().execute("SELECT cred_hash, status FROM credentials WHERE user_id=?", (uid,)).fetchone()
    assert status == "issued"

    page = c.get("/credentials").data
    assert b"Valid on-chain" in page

    public = app_module.app.test_client()                       # no login
    html = public.get(f"/verify/{h}").get_data(as_text=True)
    assert "Authentic" in html and "Python Certified" in html and "still hash" in html

    recs = c.get("/recommendations?location=").get_data(as_text=True)
    assert "· verified" in recs                                  # verified-skill chip

    # tampering with the database record is detected
    db = DB(); db.execute("UPDATE credentials SET title='Forged PhD' WHERE cred_hash=?", (h,)); db.commit()
    assert "altered after issuing" in public.get(f"/verify/{h}").get_data(as_text=True)
    db.execute("UPDATE credentials SET title='Python Certified' WHERE cred_hash=?", (h,)); db.commit()

    cid = DB().execute("SELECT id FROM credentials WHERE cred_hash=?", (h,)).fetchone()[0]
    post(admin, f"/admin/revoke_credential/{cid}", path_for_token="/admin")
    assert "Revoked" in public.get(f"/verify/{h}").get_data(as_text=True)
    assert "· verified" not in c.get("/recommendations?location=").get_data(as_text=True)


def test_unknown_hash_not_authentic(app_module):
    c = app_module.app.test_client()
    assert "Not found" in c.get("/verify/" + "00" * 32).get_data(as_text=True)
    assert c.get("/verify/not-a-hash").status_code == 404


def test_normal_user_cannot_issue(user):
    c, uid = user
    r = c.post("/admin/issue_credential", data={"csrf_token": token(c, "/dashboard")})
    assert r.status_code == 302 and "/login" in r.headers["Location"]
