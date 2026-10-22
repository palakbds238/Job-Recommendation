import os, re, sys, tempfile, uuid
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

_tmp = tempfile.mkdtemp()
os.environ.update({
    "DATABASE_PATH": os.path.join(_tmp, "test.db"),
    "UPLOAD_FOLDER": os.path.join(_tmp, "uploads"),
    "SECRET_KEY": "test-secret", "ADMIN_EMAIL": "admin@test.com",
    "ADMIN_PASSWORD": "AdminPass123", "BLOCKCHAIN_MODE": "local",
    "USE_EMBEDDINGS": "0",
})


@pytest.fixture(scope="session")
def app_module():
    import app as app_module
    app_module.app.config["TESTING"] = True
    return app_module


def token(client, path="/login"):
    html = client.get(path).get_data(as_text=True)
    return re.search(r'name="csrf-token" content="([^"]+)"', html).group(1)


def post(client, url, data=None, path_for_token="/login", **kw):
    data = dict(data or {})
    data["csrf_token"] = token(client, path_for_token)
    return client.post(url, data=data, **kw)


@pytest.fixture()
def admin(app_module):
    c = app_module.app.test_client()
    post(c, "/login", {"email": "admin@test.com", "password": "AdminPass123"})
    return c


@pytest.fixture()
def user(app_module):
    """A registered, logged-in normal user with a profile. Returns (client, id)."""
    c = app_module.app.test_client()
    email = f"u{uuid.uuid4().hex[:8]}@test.com"
    post(c, "/register", {"name": "Test User", "email": email, "password": "password123"},
         path_for_token="/register")
    post(c, "/login", {"email": email, "password": "password123"})
    post(c, "/profile", {"skills": "Python, SQL, Flask", "experience": "1-3 years",
                         "education": "B.Tech", "domain": "Any", "location": "Indore",
                         "goals": "backend developer"}, path_for_token="/profile")
    import sqlite3
    uid = sqlite3.connect(os.environ["DATABASE_PATH"]).execute(
        "SELECT id FROM users WHERE email=?", (email,)).fetchone()[0]
    return c, uid
