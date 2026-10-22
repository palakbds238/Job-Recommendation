import itsdangerous
import pytest
import sqlite3, os

import mailer
from tests.conftest import post, token

DB = lambda: sqlite3.connect(os.environ["DATABASE_PATH"])  # noqa: E731


@pytest.fixture(autouse=True)
def _reset_throttles(app_module):
    app_module._FAILS.clear()
    yield
    app_module._FAILS.clear()


def _email(uid):
    return DB().execute("SELECT email FROM users WHERE id=?", (uid,)).fetchone()[0]


def _login(app_module, email, pw):
    c = app_module.app.test_client()
    r = post(c, "/login", {"email": email, "password": pw})
    # a failed login ALSO redirects (back to /login), so judge by where it goes
    return c, r.status_code == 302 and "/login" not in r.headers["Location"]


# ── settings ────────────────────────────────────────────────────────────────
def test_account_requires_login(app_module):
    r = app_module.app.test_client().get("/account")
    assert r.status_code == 302 and "/login" in r.headers["Location"]


def test_account_page_and_name_change(user):
    c, uid = user
    html = c.get("/account").get_data(as_text=True)
    assert "Account settings" in html and _email(uid) in html and "disabled" in html
    post(c, "/account/name", {"name": "  New   Name "}, path_for_token="/account")
    assert DB().execute("SELECT name FROM users WHERE id=?", (uid,)).fetchone()[0] == "New Name"
    assert "New Name" in c.get("/dashboard").get_data(as_text=True)
    post(c, "/account/name", {"name": "x"}, path_for_token="/account")          # too short
    assert DB().execute("SELECT name FROM users WHERE id=?", (uid,)).fetchone()[0] == "New Name"


def test_password_change_rules(app_module, user):
    c, uid = user; email = _email(uid)
    def attempt(cur, new, conf):
        post(c, "/account/password", {"current_password": cur, "new_password": new, "confirm_password": conf},
             path_for_token="/account")
    attempt("wrong-password", "newpassword1", "newpassword1")
    attempt("password123", "short", "short")
    attempt("password123", "newpassword1", "different1")
    attempt("password123", "password123", "password123")
    assert _login(app_module, email, "password123")[1]                         # nothing changed yet
    attempt("password123", "newpassword1", "newpassword1")
    assert _login(app_module, email, "newpassword1")[1]
    assert not _login(app_module, email, "password123")[1]


def test_password_change_is_throttled(user):
    c, _ = user
    for _ in range(6):
        r = post(c, "/account/password", {"current_password": "bad", "new_password": "newpassword1",
                                          "confirm_password": "newpassword1"}, path_for_token="/account",
                 follow_redirects=True)
    assert "Too many attempts" in r.get_data(as_text=True)


def test_export_contains_my_data_but_no_password(user):
    c, uid = user
    c.post("/save_job", json={"job_id": 1}, headers={"X-CSRFToken": token(c, "/dashboard")})
    r = c.get("/account/export")
    assert r.status_code == 200 and "attachment" in r.headers["Content-Disposition"]
    data = r.get_json()
    assert data["account"]["email"] == _email(uid) and data["profile"]["skills"]
    assert {s["job_id"] for s in data["saved_jobs"]} == {1}
    assert "password" not in r.get_data(as_text=True).lower().replace("password123", "")


def test_delete_requires_password_and_confirmation(app_module, user):
    c, uid = user; email = _email(uid)
    post(c, "/account/delete", {"password": "wrong", "confirm": "DELETE"}, path_for_token="/account")
    post(c, "/account/delete", {"password": "password123", "confirm": "nope"}, path_for_token="/account")
    assert DB().execute("SELECT 1 FROM users WHERE id=?", (uid,)).fetchone()
    post(c, "/account/delete", {"password": "password123", "confirm": "DELETE"}, path_for_token="/account")
    assert DB().execute("SELECT 1 FROM users WHERE id=?", (uid,)).fetchone() is None
    assert DB().execute("SELECT COUNT(*) FROM user_profiles WHERE user_id=?", (uid,)).fetchone()[0] == 0
    assert not _login(app_module, email, "password123")[1]


def test_admin_cannot_delete_own_account(admin, app_module):
    post(admin, "/account/delete", {"password": "AdminPass123", "confirm": "DELETE"}, path_for_token="/account")
    assert DB().execute("SELECT 1 FROM users WHERE is_admin=1").fetchone()
    assert "Delete account" not in admin.get("/account").get_data(as_text=True)


# ── forgot / reset password ─────────────────────────────────────────────────
@pytest.fixture()
def outbox(monkeypatch):
    sent = []
    monkeypatch.setattr(mailer, "send_mail", lambda to, subject, body: sent.append((to, subject, body)) or True)
    return sent


def _link(body):
    return "/reset-password/" + body.split("/reset-password/")[1].split()[0]


def test_login_links_to_forgot_password(app_module):
    assert "/forgot-password" in app_module.app.test_client().get("/login").get_data(as_text=True)


def test_unknown_and_known_emails_get_the_same_answer(app_module, user, outbox):
    c = app_module.app.test_client()
    a = post(c, "/forgot-password", {"email": "nobody@nowhere.com"}, path_for_token="/forgot-password", follow_redirects=True)
    b = post(c, "/forgot-password", {"email": _email(user[1])}, path_for_token="/forgot-password", follow_redirects=True)
    msg = "If an account exists for that email"
    assert msg in a.get_data(as_text=True) and msg in b.get_data(as_text=True)
    assert len(outbox) == 1 and outbox[0][0] == _email(user[1])             # only the real user got mail


def test_full_reset_flow_and_one_time_use(app_module, user, outbox):
    email = _email(user[1]); c = app_module.app.test_client()
    post(c, "/forgot-password", {"email": email}, path_for_token="/forgot-password")
    link = _link(outbox[0][2])
    assert c.get(link).status_code == 200
    r = post(c, link, {"new_password": "brandnew123", "confirm_password": "mismatch1"}, path_for_token=link)
    assert r.status_code == 400
    r = post(c, link, {"new_password": "brandnew123", "confirm_password": "brandnew123"}, path_for_token=link)
    assert r.status_code == 302
    assert _login(app_module, email, "brandnew123")[1] and not _login(app_module, email, "password123")[1]
    assert c.get(link).status_code == 400                                    # used once, now dead


def test_reset_link_dies_when_password_changes(app_module, user, outbox):
    c, uid = user; email = _email(uid)
    post(app_module.app.test_client(), "/forgot-password", {"email": email}, path_for_token="/forgot-password")
    link = _link(outbox[0][2])
    post(c, "/account/password", {"current_password": "password123", "new_password": "changed1234",
                                  "confirm_password": "changed1234"}, path_for_token="/account")
    assert app_module.app.test_client().get(link).status_code == 400


def test_tampered_and_expired_tokens_are_rejected(app_module, user):
    with app_module.app.test_request_context():
        row = app_module.get_db().execute("SELECT * FROM users WHERE id=?", (user[1],)).fetchone()
        tok = app_module._reset_serializer().dumps({"uid": row["id"], "fp": app_module._fingerprint(row)})
        assert app_module._user_from_token(tok)["id"] == user[1]
        assert app_module._user_from_token(tok, max_age=-1) is None          # expired
        assert app_module._user_from_token(tok[:-3] + "xyz") is None         # tampered
        forged = itsdangerous.URLSafeTimedSerializer("another-secret", salt="password-reset").dumps(
            {"uid": row["id"], "fp": app_module._fingerprint(row)})
        assert app_module._user_from_token(forged) is None                   # signed with the wrong key
    assert app_module.app.test_client().get("/reset-password/garbage").status_code == 400


def test_reset_requests_are_rate_limited(app_module, outbox):
    c = app_module.app.test_client()
    for _ in range(6):
        r = post(c, "/forgot-password", {"email": "x@y.com"}, path_for_token="/forgot-password", follow_redirects=True)
    assert "Too many requests" in r.get_data(as_text=True)


def test_dev_mode_shows_link_only_without_smtp(app_module, user, monkeypatch):
    monkeypatch.setattr(mailer, "send_mail", lambda *a: False)
    monkeypatch.setenv("DEV_SHOW_RESET_LINK", "1"); monkeypatch.delenv("SMTP_HOST", raising=False)
    c = app_module.app.test_client()
    r = post(c, "/forgot-password", {"email": _email(user[1])}, path_for_token="/forgot-password", follow_redirects=True)
    assert "/reset-password/" in r.get_data(as_text=True)
    app_module._FAILS.clear()
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")                      # configured but failing: never leak the link
    r = post(c, "/forgot-password", {"email": _email(user[1])}, path_for_token="/forgot-password", follow_redirects=True)
    assert "/reset-password/" not in r.get_data(as_text=True)


def test_public_base_url_beats_a_spoofed_host_header(app_module, user, monkeypatch):
    with app_module.app.test_request_context("/forgot-password", headers={"Host": "evil.example"}):
        row = app_module.get_db().execute("SELECT * FROM users WHERE id=?", (user[1],)).fetchone()
        monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
        assert app_module._reset_link(row).startswith("http://evil.example/reset-password/")   # why it must be set
        monkeypatch.setenv("PUBLIC_BASE_URL", "https://careers.example.org/")
        link = app_module._reset_link(row)
        assert link.startswith("https://careers.example.org/reset-password/") and "evil" not in link


# ── mailer ──────────────────────────────────────────────────────────────────
def test_mailer_sends_via_smtp_and_never_raises(monkeypatch):
    assert mailer.send_mail("a@b.c", "s", "b") is False                      # not configured
    log = []
    class FakeSMTP:
        def __init__(self, host, port, timeout=None): log.append(("connect", host, port))
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def starttls(self): log.append("tls")
        def login(self, u, p): log.append(("login", u))
        def send_message(self, m): log.append(("send", m["To"], m["Subject"]))
    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com"); monkeypatch.setenv("SMTP_USER", "u"); monkeypatch.setenv("SMTP_PASSWORD", "p")
    assert mailer.send_mail("a@b.c", "Hello", "body") is True
    assert log == [("connect", "smtp.example.com", 587), "tls", ("login", "u"), ("send", "a@b.c", "Hello")]
    class Boom(FakeSMTP):
        def send_message(self, m): raise OSError("down")
    monkeypatch.setattr(mailer.smtplib, "SMTP", Boom)
    assert mailer.send_mail("a@b.c", "Hello", "body") is False
