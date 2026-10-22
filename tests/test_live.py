import os
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

import job_sources
import live_jobs as live
import model as M
from job_sources import ProviderError
from job_sources.adzuna import AdzunaProvider
from job_sources.remotive import RemotiveProvider
from tests.conftest import token

# Fixtures mirror the documented response shapes (Adzuna: results[], redirect_url,
# company.display_name, location.display_name, category.label; Remotive: jobs[]).
ADZUNA = {"count": 3, "results": [
    {"id": "4001", "title": "Python Developer",
     "description": "We need <b>Python</b>, Flask and SQL skills. 2-4 years experience. "
                    "<script>alert('xss')</script>",
     "created": "2026-10-05T08:00:00Z", "redirect_url": "https://www.adzuna.in/jobs/land/ad/4001",
     "salary_min": 800000, "salary_max": 1200000, "salary_is_predicted": "0",
     "company": {"display_name": "Acme Tech"},
     "location": {"display_name": "Indore, Madhya Pradesh", "area": ["India"]},
     "category": {"label": "IT Jobs", "tag": "it-jobs"}, "contract_time": "full_time"},
    {"id": "4002", "title": "Senior Data Analyst \\", "description": "SQL, Excel and Tableau reporting",
     "created": "2026-10-06T08:00:00Z", "redirect_url": "javascript:alert(1)",
     "company": {"display_name": "Data'Co"}, "location": {"display_name": "Bhopal"},
     "category": {"label": "IT Jobs"}, "contract_time": "full_time", "salary_is_predicted": "1",
     "salary_min": 600000, "salary_max": 600000},
    {"id": None, "title": "broken row"},            # must be ignored, not crash
]}
REMOTIVE = {"job-count": 2, "jobs": [
    {"id": 7001, "url": "https://remotive.com/remote-jobs/software-dev/backend-7001",
     "title": "Backend Engineer (Python)", "company_name": "RemoteCo",
     "category": "Software Development", "tags": ["python", "django"], "job_type": "full_time",
     "publication_date": "2026-10-06T10:00:00", "candidate_required_location": "Worldwide",
     "salary": "$80k - $100k", "description": "<p>Build APIs with Python and Django</p>"},
    {"id": 7002, "url": "https://remotive.com/remote-jobs/marketing/lead-7002",
     "title": "Marketing Lead", "company_name": "AdCo", "category": "Marketing", "tags": [],
     "job_type": "full_time", "publication_date": "2026-10-06T10:00:00",
     "candidate_required_location": "USA", "salary": "", "description": "<p>Run campaigns</p>"},
]}


@pytest.fixture(scope="module")
def models():
    return M.load_models()


@pytest.fixture()
def db():
    d = sqlite3.connect(":memory:")
    d.row_factory = sqlite3.Row
    d.executescript("""CREATE TABLE saved_jobs(id INTEGER PRIMARY KEY, user_id INT, job_id INT);
        CREATE TABLE applied_jobs(id INTEGER PRIMARY KEY, user_id INT, job_id INT);
        CREATE TABLE users(id INTEGER PRIMARY KEY, is_admin INT);
        CREATE TABLE user_profiles(user_id INT, skills TEXT);""")
    live.ensure_schema(d)
    return d


@pytest.fixture()
def adzuna_env(monkeypatch):
    monkeypatch.setenv("ADZUNA_APP_ID", "id"); monkeypatch.setenv("ADZUNA_APP_KEY", "key")


# ── text helpers ────────────────────────────────────────────────────────────
def test_html_is_stripped_and_scripts_removed():
    t = live.html_to_text("<p>Hi <b>there</b></p><script>alert(1)</script>&amp; more<br>line2")
    assert "<" not in t and "alert" not in t and "& more" in t and "line2" in t


def test_experience_buckets():
    assert live.parse_experience("5+ years of Python") == "5-8 years"
    assert live.parse_experience("2-4 years") == "1-3 years"
    assert live.parse_experience("Junior developer") == "0-1 years"
    assert live.parse_experience("Senior engineer") == "5-8 years"
    assert live.parse_experience("We build things") == "Not specified"


def test_salary_formatting():
    from job_sources.base import RawJob
    inr = RawJob("adzuna", "1", "t", salary_min=800000, salary_max=1200000, salary_currency="₹")
    assert live.format_salary(inr) == ("8-12 LPA", 10.0)
    gbp = RawJob("adzuna", "1", "t", salary_min=40000, salary_max=55000, salary_currency="£",
                 salary_estimated=True)
    assert live.format_salary(gbp) == ("£40k-£55k (est.)", 0.0)
    assert live.format_salary(RawJob("r", "1", "t", salary_text="$80k - $100k"))[0] == "$80k - $100k"
    assert live.format_salary(RawJob("r", "1", "t"))[0] == "Not disclosed"


def test_only_http_urls_are_kept():
    assert live.safe_url("https://a.com/x") == "https://a.com/x"
    for bad in ("javascript:alert(1)", "data:text/html,x", "ftp://a.com", "", "https://a.com/<x>"):
        assert live.safe_url(bad) == ""


# ── providers ───────────────────────────────────────────────────────────────
def test_adzuna_requires_credentials(monkeypatch):
    monkeypatch.delenv("ADZUNA_APP_ID", raising=False)
    p = AdzunaProvider()
    assert not p.is_configured()
    with pytest.raises(ProviderError):
        p.fetch(["python"])


def test_adzuna_request_shape_and_parsing(monkeypatch, adzuna_env):
    calls = []
    monkeypatch.setattr("job_sources.adzuna.http_get_json",
                        lambda url, params=None: calls.append((url, params)) or ADZUNA)
    jobs = AdzunaProvider().fetch(["python developer"], location="Indore")
    url, params = calls[0]
    assert url == "https://api.adzuna.com/v1/api/jobs/in/search/1"
    assert params["what"] == "python developer" and params["where"] == "Indore"
    assert params["app_id"] == "id" and params["app_key"] == "key"
    assert [j.external_id for j in jobs] == ["4001", "4002"]       # broken row skipped
    assert jobs[0].salary_currency == "₹" and jobs[0].company == "Acme Tech"
    assert jobs[1].salary_estimated is True


def test_adzuna_respects_call_budget(monkeypatch, adzuna_env):
    monkeypatch.setenv("ADZUNA_MAX_CALLS", "2"); monkeypatch.setenv("ADZUNA_PER_PAGE", "2")
    n = []
    def fake(url, params=None):
        n.append(1)
        return {"results": [{"id": f"{len(n)}{i}", "title": "t"} for i in range(2)]}
    monkeypatch.setattr("job_sources.adzuna.http_get_json", fake)
    AdzunaProvider().fetch(["a", "b", "c", "d"])
    assert len(n) == 2


def test_adzuna_rejects_unexpected_shape(monkeypatch, adzuna_env):
    monkeypatch.setattr("job_sources.adzuna.http_get_json", lambda *a, **k: {"oops": 1})
    with pytest.raises(ProviderError):
        AdzunaProvider().fetch(["x"])


def test_remotive_filters_client_side(monkeypatch):
    monkeypatch.setattr("job_sources.remotive.http_get_json", lambda *a, **k: REMOTIVE)
    jobs = RemotiveProvider().fetch(["python developer"])
    assert [j.external_id for j in jobs] == ["7001"]
    assert jobs[0].location == "Remote - Worldwide"
    assert len(RemotiveProvider().fetch([])) == 2


def test_http_helper_maps_failures_to_provider_error(monkeypatch):
    from job_sources import base
    class R:
        status_code = 403
        def __enter__(self): return self
        def __exit__(self, *a): return False
    monkeypatch.setattr(base._session().__class__, "get", lambda *a, **k: R())
    with pytest.raises(ProviderError, match="credentials"):
        base.http_get_json("https://api.adzuna.com/x")


# ── sync pipeline ───────────────────────────────────────────────────────────
@pytest.fixture()
def patched_adzuna(monkeypatch, adzuna_env):
    monkeypatch.setattr("job_sources.adzuna.http_get_json", lambda *a, **k: ADZUNA)


def test_sync_enriches_and_upserts(db, models, patched_adzuna):
    r = live.sync_live_jobs(db, models, providers=["adzuna"], queries=["python"])[0]
    assert (r["status"], r["fetched"], r["inserted"], r["updated"]) == ("ok", 2, 2, 0)
    j = db.execute("SELECT * FROM live_jobs WHERE external_id='4001'").fetchone()
    assert "Python" in j["skills_required"] and "SQL" in j["skills_required"]
    assert "<script" not in j["description"] and "alert" not in j["description"]
    assert j["salary_range"] == "8-12 LPA" and j["salary_lpa"] == 10.0
    assert j["experience_required"] == "1-3 years" and j["category"]
    assert j["url"].startswith("https://www.adzuna.in/")
    assert db.execute("SELECT url FROM live_jobs WHERE external_id='4002'").fetchone()[0] == ""
    r2 = live.sync_live_jobs(db, models, providers=["adzuna"], queries=["python"],
                             ignore_interval=True)[0]
    assert (r2["inserted"], r2["updated"]) == (0, 2)
    assert db.execute("SELECT COUNT(*) FROM live_jobs").fetchone()[0] == 2


def test_min_interval_protects_api_quota(db, models, patched_adzuna):
    live.sync_live_jobs(db, models, providers=["adzuna"], queries=["python"])
    r = live.sync_live_jobs(db, models, providers=["adzuna"], queries=["python"])[0]
    assert r["status"] == "skipped" and "rate-limit" in r["message"]


def test_unconfigured_provider_is_skipped_not_fatal(db, models, monkeypatch):
    monkeypatch.delenv("ADZUNA_APP_ID", raising=False)
    r = live.sync_live_jobs(db, models, providers=["adzuna"])[0]
    assert r["status"] == "skipped"


def test_provider_failure_is_logged_not_raised(db, models, monkeypatch, adzuna_env):
    def boom(*a, **k): raise ProviderError("api.adzuna.com returned HTTP 500")
    monkeypatch.setattr("job_sources.adzuna.http_get_json", boom)
    r = live.sync_live_jobs(db, models, providers=["adzuna"], queries=["x"])[0]
    assert r["status"] == "error" and "500" in r["message"]
    assert db.execute("SELECT status FROM sync_log").fetchone()[0] == "error"


def test_expired_jobs_are_pruned_but_saved_or_applied_are_kept(db, models, patched_adzuna):
    live.sync_live_jobs(db, models, providers=["adzuna"], queries=["python"])
    old = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat(timespec="seconds")
    db.execute("UPDATE live_jobs SET last_seen=?", (old,))
    keep_id = db.execute("SELECT id FROM live_jobs WHERE external_id='4001'").fetchone()[0]
    db.execute("INSERT INTO saved_jobs(user_id, job_id) VALUES (1, ?)", (M.LIVE_JOB_OFFSET + keep_id,))
    assert live.prune(db) == 1
    assert [r[0] for r in db.execute("SELECT external_id FROM live_jobs")] == ["4001"]


def test_full_feed_provider_drops_vanished_jobs(db, models, monkeypatch):
    feed = {"jobs": list(REMOTIVE["jobs"])}
    monkeypatch.setattr("job_sources.remotive.http_get_json", lambda *a, **k: feed)
    live.sync_live_jobs(db, models, providers=["remotive"], queries=[])
    assert db.execute("SELECT COUNT(*) FROM live_jobs").fetchone()[0] == 2
    feed["jobs"] = [REMOTIVE["jobs"][0]]
    live.sync_live_jobs(db, models, providers=["remotive"], queries=[], ignore_interval=True)
    assert [r[0] for r in db.execute("SELECT external_id FROM live_jobs")] == ["7001"]


def test_default_queries_use_user_skills(db):
    db.execute("INSERT INTO users VALUES (1, 0)")
    db.execute("INSERT INTO user_profiles VALUES (1, 'Rust, Rust, Kubernetes')")
    assert "kubernetes" in live.default_queries(db)


# ── pool + app integration ──────────────────────────────────────────────────
def test_live_jobs_join_the_pool_and_use_a_refitted_vectorizer(db, models, patched_adzuna):
    live.sync_live_jobs(db, models, providers=["adzuna"], queries=["python"])
    n = len(models["jobs_df"])
    M.refresh_job_pool(models, [], db.execute("SELECT * FROM live_jobs").fetchall())
    try:
        df = models["jobs_df"]
        assert len(df) == n + 2 and models["tfidf_matrix"].shape[0] == n + 2
        row = df[df["source"] == "adzuna"].iloc[0]
        assert row["job_id"] > M.LIVE_JOB_OFFSET and row["url"].startswith("https://")
        assert not df.isna().any().any()
        recs = M.get_recommendations(models, "python flask sql developer", top_n=3,
                                     user_skills={"python", "flask", "sql"})
        assert any(r["source"] == "adzuna" for r in recs)
    finally:
        M.refresh_job_pool(models, [])


def test_live_jobs_in_the_app_are_safe_and_attributed(app_module, user, admin, adzuna_env, monkeypatch):
    monkeypatch.setattr("job_sources.adzuna.http_get_json", lambda *a, **k: ADZUNA)
    c, uid = user
    d = sqlite3.connect(os.environ["DATABASE_PATH"]); d.row_factory = sqlite3.Row
    live.ensure_schema(d)
    d.execute("DELETE FROM sync_log")
    live.sync_live_jobs(d, app_module.MODELS, providers=["adzuna"], queries=["python"])
    jid = M.LIVE_JOB_OFFSET + d.execute("SELECT id FROM live_jobs WHERE external_id='4001'").fetchone()[0]
    jid2 = M.LIVE_JOB_OFFSET + d.execute("SELECT id FROM live_jobs WHERE external_id='4002'").fetchone()[0]

    detail = c.get(f"/job/{jid}").get_data(as_text=True)
    assert "Apply on Adzuna" in detail and "https://www.adzuna.in/jobs/land/ad/4001" in detail
    assert 'rel="noopener noreferrer nofollow"' in detail
    assert "<script>alert('xss')" not in detail
    detail2 = c.get(f"/job/{jid2}").get_data(as_text=True)          # javascript: link dropped
    assert "javascript:alert" not in detail2 and "Apply on Adzuna" not in detail2
    assert "applyJob(" in detail2 and "Data'Co" not in detail2.split("onclick")[1][:120]

    assert "Jobs by Adzuna" in c.get("/search?q=python").get_data(as_text=True)
    assert c.post("/apply_job", json={"job_id": jid}, headers={"X-CSRFToken": token(c, "/dashboard")}
                  ).get_json()["status"] == "applied"
    page = admin.get("/admin/live_jobs").get_data(as_text=True)
    assert "Live Job Data" in page and "adzuna" in page.lower()


def test_admin_live_page_requires_admin(user):
    c, _ = user
    r = c.get("/admin/live_jobs")
    assert r.status_code == 302


# ── real HTTP layer, against a local server ─────────────────────────────────
import json as _json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


@pytest.fixture()
def fake_api():
    state = {"status": 200, "body": _json.dumps(ADZUNA).encode(), "hits": []}

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            state["hits"].append(self.path)
            self.send_response(state["status"])
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(state["body"])

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    state["url"] = f"http://127.0.0.1:{srv.server_port}"
    yield state
    srv.shutdown()


def test_real_http_roundtrip_adzuna(fake_api, adzuna_env, monkeypatch):
    monkeypatch.setenv("ADZUNA_BASE_URL", fake_api["url"] + "/v1/api/jobs")
    jobs = AdzunaProvider().fetch(["python developer"], location="Indore")
    assert [j.external_id for j in jobs] == ["4001", "4002"]
    path = fake_api["hits"][0]
    assert path.startswith("/v1/api/jobs/in/search/1?") and "what=python+developer" in path
    assert "where=Indore" in path and "app_key=key" in path


def test_real_http_error_statuses_become_provider_errors(fake_api, adzuna_env, monkeypatch):
    monkeypatch.setenv("ADZUNA_BASE_URL", fake_api["url"])
    for status, text in ((403, "credentials"), (429, "rate limit")):
        fake_api["status"] = status
        with pytest.raises(ProviderError, match=text):
            AdzunaProvider().fetch(["x"])


def test_real_http_oversized_and_invalid_bodies_are_rejected(fake_api, adzuna_env, monkeypatch):
    monkeypatch.setenv("ADZUNA_BASE_URL", fake_api["url"])
    from job_sources import base
    monkeypatch.setattr(base, "MAX_BYTES", 100)
    with pytest.raises(ProviderError, match="too large"):
        AdzunaProvider().fetch(["x"])
    monkeypatch.setattr(base, "MAX_BYTES", 8 * 1024 * 1024)
    fake_api["body"] = b"<html>not json</html>"
    with pytest.raises(ProviderError, match="request failed"):
        AdzunaProvider().fetch(["x"])


def test_unreachable_server_is_a_provider_error(adzuna_env, monkeypatch):
    monkeypatch.setenv("ADZUNA_BASE_URL", "http://127.0.0.1:9")     # nothing listens here
    with pytest.raises(ProviderError):
        AdzunaProvider().fetch(["x"])


def test_real_http_roundtrip_remotive(fake_api, monkeypatch):
    fake_api["body"] = _json.dumps(REMOTIVE).encode()
    monkeypatch.setenv("REMOTIVE_URL", fake_api["url"] + "/api/remote-jobs")
    assert len(RemotiveProvider().fetch([])) == 2


def test_network_failure_can_be_retried_but_http_refusals_cannot(db, models, monkeypatch, adzuna_env):
    def conn(*a, **k): raise ProviderError("api.adzuna.com request failed: ConnectionError")
    monkeypatch.setattr("job_sources.adzuna.http_get_json", conn)
    assert live.sync_live_jobs(db, models, providers=["adzuna"], queries=["x"])[0]["status"] == "error"
    assert live.sync_live_jobs(db, models, providers=["adzuna"], queries=["x"])[0]["status"] == "error"  # retried

    def http(*a, **k): raise ProviderError("api.adzuna.com returned HTTP 500")
    monkeypatch.setattr("job_sources.adzuna.http_get_json", http)
    assert live.sync_live_jobs(db, models, providers=["adzuna"], queries=["x"])[0]["status"] == "error"
    assert live.sync_live_jobs(db, models, providers=["adzuna"], queries=["x"])[0]["status"] == "skipped"


def test_category_threshold_accepts_correct_low_confidence_predictions(models):
    from job_sources.base import RawJob
    raw = RawJob("adzuna", "1", "Python Developer", description="Python, Django, SQL and REST APIs")
    assert live.enrich(raw, models)["category"] != "Other"
