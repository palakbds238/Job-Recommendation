import csv
import io
import os
import re
import sqlite3

import pytest
from tests.conftest import post, token

DB = lambda: sqlite3.connect(os.environ["DATABASE_PATH"])  # noqa: E731


def _apply(c, job_id):
    return c.post("/apply_job", json={"job_id": job_id}, headers={"X-CSRFToken": token(c, "/dashboard")}).get_json()


def _app_id(uid, job_id):
    return DB().execute("SELECT id FROM applied_jobs WHERE user_id=? AND job_id=?", (uid, job_id)).fetchone()[0]


def _update(c, app_id, body):
    return c.post(f"/application/{app_id}/update", json=body, headers={"X-CSRFToken": token(c, "/dashboard")})


# ── candidate tracker ───────────────────────────────────────────────────────
def test_applied_page_shows_tabs_and_controls(user):
    c, uid = user
    _apply(c, 3)
    html = c.get("/applied_jobs").get_data(as_text=True)
    for s in ("Applied", "Shortlisted", "Interview", "Offer", "Rejected", "Withdrawn"):
        assert s in html
    assert "app-card" in html and "Save notes" in html and "Proof recorded" in html


def test_user_can_change_status_and_save_notes(user):
    c, uid = user
    _apply(c, 4); aid = _app_id(uid, 4)
    assert _update(c, aid, {"status": "Interview"}).get_json()["status"] == "ok"
    assert _update(c, aid, {"notes": "  Call on Monday  "}).get_json()["status"] == "ok"
    st, notes, by, notified = DB().execute("SELECT status, notes, status_by, user_notified FROM applied_jobs WHERE id=?", (aid,)).fetchone()
    assert (st, notes, by, notified) == ("Interview", "Call on Monday", "user", 1)
    assert "Call on Monday" in c.get("/applied_jobs?status=Interview").get_data(as_text=True)
    assert "Call on Monday" not in c.get("/applied_jobs?status=Offer").get_data(as_text=True)


def test_invalid_status_unknown_id_and_other_users_rows_are_rejected(app_module, user):
    c, uid = user
    _apply(c, 5); aid = _app_id(uid, 5)
    assert _update(c, aid, {"status": "Hired!"}).status_code == 400
    assert _update(c, 99999999, {"status": "Offer"}).status_code == 404
    other = app_module.app.test_client()                         # a second user cannot touch it
    post(other, "/register", {"name": "Eve", "email": "eve@t.com", "password": "password123"}, path_for_token="/register")
    post(other, "/login", {"email": "eve@t.com", "password": "password123"})
    assert _update(other, aid, {"status": "Offer"}).status_code == 404
    assert DB().execute("SELECT status FROM applied_jobs WHERE id=?", (aid,)).fetchone()[0] in (None, "Applied")


def test_notes_are_length_capped(user):
    c, uid = user
    _apply(c, 6); aid = _app_id(uid, 6)
    _update(c, aid, {"notes": "x" * 5000})
    assert len(DB().execute("SELECT notes FROM applied_jobs WHERE id=?", (aid,)).fetchone()[0]) == 1000


def test_update_requires_login_and_csrf(app_module, user):
    c, uid = user
    _apply(c, 7); aid = _app_id(uid, 7)
    assert app_module.app.test_client().post(f"/application/{aid}/update", json={"status": "Offer"}).status_code == 400
    assert c.post(f"/application/{aid}/update", json={"status": "Offer"}).status_code == 400   # no CSRF header


# ── recruiter (admin) side + notifications ──────────────────────────────────
def test_non_admin_cannot_reach_applicant_pages(user):
    c, _ = user
    for path in ("/admin/applications", "/admin/applications/export"):
        r = c.get(path)
        assert r.status_code == 302 and "/login" in r.headers["Location"]
    r = c.post("/admin/applications/1/status", data={"status": "Offer", "csrf_token": token(c, "/dashboard")})
    assert r.status_code == 302 and "/login" in r.headers["Location"]


def test_recruiter_status_change_notifies_the_candidate_once(admin, user):
    c, uid = user
    _apply(c, 8); aid = _app_id(uid, 8)
    assert "nav-badge" not in c.get("/dashboard").get_data(as_text=True)
    post(admin, f"/admin/applications/{aid}/status", {"status": "Shortlisted"}, path_for_token="/admin/applications")
    assert DB().execute("SELECT status, status_by, user_notified FROM applied_jobs WHERE id=?", (aid,)).fetchone() == ("Shortlisted", "recruiter", 0)
    assert "nav-badge" in c.get("/dashboard").get_data(as_text=True)               # bell/badge on the nav
    page = c.get("/applied_jobs").get_data(as_text=True)
    assert "New update" in page and "Set by the recruiter" in page
    assert "nav-badge" not in c.get("/dashboard").get_data(as_text=True)           # seen -> cleared


def test_candidate_changing_their_own_status_does_not_notify(admin, user):
    c, uid = user
    _apply(c, 9); aid = _app_id(uid, 9)
    _update(c, aid, {"status": "Withdrawn"})
    assert "nav-badge" not in c.get("/dashboard").get_data(as_text=True)


def test_admin_status_validation(admin, user):
    c, uid = user
    _apply(c, 10); aid = _app_id(uid, 10)
    post(admin, f"/admin/applications/{aid}/status", {"status": "Hired!"}, path_for_token="/admin/applications")
    assert DB().execute("SELECT status FROM applied_jobs WHERE id=?", (aid,)).fetchone()[0] in (None, "Applied")


def test_applicants_page_shows_match_credentials_and_filters(admin, user):
    c, uid = user
    _apply(c, 11); aid = _app_id(uid, 11)
    post(admin, "/admin/issue_credential", {"user_id": uid, "title": "Python Pro", "issuer_name": "SVVV", "skills": "Python",
                                           "issued_on": "2026-10-01"}, path_for_token="/admin")
    post(admin, f"/admin/applications/{aid}/status", {"status": "Interview"}, path_for_token="/admin/applications")
    html = admin.get("/admin/applications").get_data(as_text=True)
    assert "Applicants" in html and "Python Pro" in html and re.search(r'chip-(green|blue|gray)"[^>]*>\d+%', html)
    interview = admin.get("/admin/applications?status=Interview").get_data(as_text=True)
    assert "Test User" in interview
    assert "Test User" not in admin.get("/admin/applications?status=Offer").get_data(as_text=True)
    assert "Test User" in admin.get("/admin/applications?q=" + DB().execute("SELECT email FROM users WHERE id=?", (uid,)).fetchone()[0]).get_data(as_text=True)


def test_applicants_pagination(admin, user):
    c, uid = user
    db = DB()
    for j in range(200, 245):
        db.execute("INSERT OR IGNORE INTO applied_jobs (user_id, job_id, job_title, company) VALUES (?,?,?,?)", (uid, j, f"Bulk {j}", "Co"))
    db.commit()
    p1 = admin.get("/admin/applications").get_data(as_text=True)
    assert 'rel="next"' in p1 and p1.count("<tr>") <= 22
    assert "Showing 1–20 of" in p1


def test_csv_export_is_safe_from_formula_injection(admin, user, app_module):
    c, uid = user
    _apply(c, 12)
    db = DB(); db.execute("UPDATE users SET name=? WHERE id=?", ("=HYPERLINK(\"http://evil\")", uid)); db.commit()
    r = admin.get("/admin/applications/export")
    assert r.status_code == 200 and "text/csv" in r.mimetype and "attachment" in r.headers["Content-Disposition"]
    rows = list(csv.reader(io.StringIO(r.get_data(as_text=True))))
    assert rows[0][:3] == ["applied_at", "candidate", "email"]
    assert any(row[1].startswith("'=HYPERLINK") for row in rows[1:]) and not any(row[1].startswith("=") for row in rows[1:])


# ── dashboard, profile strength, suggestions, match panel ───────────────────
def test_profile_completeness_scoring(app_module):
    pc = app_module.profile_completeness
    assert pc(None)[0] == 0
    full = {k: "x" for k in ("skills", "experience", "education", "domain", "location", "goals", "expected_salary", "resume_filename")}
    assert pc(full) == (100, [])
    part = dict(full, resume_filename="", goals="")
    pct, tips = pc(part)
    assert pct == 70 and any("resume" in t.lower() for t in tips) and any("goals" in t.lower() for t in tips)


def test_dashboard_shows_strength_and_pipeline(user):
    c, uid = user
    _apply(c, 13); aid = _app_id(uid, 13); _update(c, aid, {"status": "Offer"})
    html = c.get("/dashboard").get_data(as_text=True)
    assert "Profile strength" in html and "Application pipeline" in html
    assert re.search(r'st-offer"[^>]*><strong>1</strong>', html)


def test_resume_suggestions_and_adding_skills(app_module, user):
    c, uid = user
    db = DB()
    db.execute("UPDATE user_profiles SET resume_text=?, skills=? WHERE user_id=?",
               ("Deployed services on Kubernetes and Docker with PostgreSQL. Built Python and Flask APIs.", "Python, Flask", uid))
    db.commit()
    html = c.get("/profile").get_data(as_text=True)
    assert "Skills found in your resume" in html
    sugg = re.findall(r'name="skill" value="([^"]+)"', html)
    assert {"Kubernetes", "Docker"} <= set(sugg) and "Python" not in sugg and "Flask" not in sugg
    post(c, "/profile/add_skills", {"skill": ["Kubernetes", "kubernetes", "Hacked <b>Skill</b>", "Docker", "python"]},
         path_for_token="/profile")
    skills = DB().execute("SELECT skills FROM user_profiles WHERE user_id=?", (uid,)).fetchone()[0]
    assert skills == "Python, Flask, Kubernetes, Docker"                    # deduped, unknown skill ignored
    again = c.get("/profile").get_data(as_text=True)
    assert "Kubernetes" not in re.findall(r'name="skill" value="([^"]+)"', again)   # no longer suggested


def test_job_detail_shows_real_match_with_learn_links(app_module, user):
    c, uid = user                                              # fixture skills: Python, SQL, Flask
    df = app_module.MODELS["jobs_df"]
    have = {"python", "sql", "flask"}
    pick = next(r for r in df.itertuples()
                if any(app_module.normalize_skill(s) not in have for s in r.skills_required.split(",") if s.strip())
                and any(app_module.normalize_skill(s) in have for s in r.skills_required.split(",")))
    html = c.get(f"/job/{pick.job_id}").get_data(as_text=True)
    assert "Your match" in html and "match-big" in html and "You have" in html and "To learn" in html
    assert 'href="https://www.google.com/search?q=learn+' in html and 'rel="noopener noreferrer"' in html
    assert "Get your Match Score" not in html


def test_job_detail_without_profile_keeps_the_call_to_action(app_module):
    c = app_module.app.test_client()
    post(c, "/register", {"name": "Nia", "email": "nia@t.com", "password": "password123"}, path_for_token="/register")
    post(c, "/login", {"email": "nia@t.com", "password": "password123"})
    assert "Get your Match Score" in c.get("/job/1").get_data(as_text=True)


def test_recommendations_have_one_pager_and_learn_links(user):
    c, _ = user
    html = c.get("/recommendations?location=").get_data(as_text=True)
    assert html.count('<nav class="pager"') == 1                              # was repeated inside every card
    assert 'href="https://www.google.com/search?q=learn+' in html
