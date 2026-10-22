import io
import xml.etree.ElementTree as ET

import pytest
from tests.conftest import post, token


@pytest.fixture()
def anon(app_module):
    return app_module.app.test_client()


@pytest.mark.parametrize("path,title", [("/about", "About CareerAI"), ("/faq", "FAQ"),
                                        ("/privacy", "Privacy policy"), ("/terms", "Terms of use")])
def test_content_pages_render(anon, path, title):
    r = anon.get(path)
    assert r.status_code == 200 and title in r.get_data(as_text=True)


def test_shell_has_mobile_menu_skip_link_seo_and_footer(anon):
    html = anon.get("/").get_data(as_text=True)
    assert 'id="navToggle"' in html and 'aria-controls="navLinks"' in html and 'id="navLinks"' in html
    assert 'class="skip-link"' in html and '<main id="main">' in html
    assert '<meta name="description"' in html and 'property="og:title"' in html and 'rel="icon"' in html
    for href in ("/about", "/faq", "/privacy", "/terms"):
        assert f'href="{href}"' in html                                  # footer links
    assert "css/site.css" in html and "js/site.js" in html


def test_each_page_has_its_own_description(anon):
    a = anon.get("/about").get_data(as_text=True)
    assert "collaborative filtering" in a.split('name="description"')[1][:250]


def test_robots_and_sitemap(anon):
    r = anon.get("/robots.txt").get_data(as_text=True)
    assert "Disallow: /admin" in r and "Disallow: /account" in r and "Sitemap:" in r
    root = ET.fromstring(anon.get("/sitemap.xml").data)
    locs = [e.text for e in root.iter("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")]
    assert any(l.endswith("/about") for l in locs) and any(l.endswith("/privacy") for l in locs)
    assert not any("/admin" in l or "/account" in l for l in locs)


def test_security_headers_and_no_store_for_signed_in_pages(anon, user):
    h = anon.get("/").headers
    assert h["X-Content-Type-Options"] == "nosniff" and h["X-Frame-Options"] == "DENY"
    assert "Referrer-Policy" in h and "Permissions-Policy" in h
    assert "no-store" not in h.get("Cache-Control", "")
    assert user[0].get("/dashboard").headers["Cache-Control"] == "no-store"


def test_error_pages_are_friendly(anon):
    r = anon.get("/definitely-not-a-page")
    html = r.get_data(as_text=True)
    assert r.status_code == 404 and "Page not found" in html and 'class="error-code">404' in html
    r = anon.post("/login", data={"email": "a", "password": "b"})        # no CSRF token
    assert r.status_code == 400 and "Security token" in r.get_data(as_text=True)


def test_method_not_allowed_page(anon):
    r = post(anon, "/about", {})
    assert r.status_code == 405 and "Method not allowed" in r.get_data(as_text=True)


def test_api_errors_are_json(anon):
    r = anon.get("/api/nothing-here")
    assert r.status_code == 404 and r.is_json and r.get_json()["code"] == 404


def test_oversized_upload_shows_413_page(user):
    c, _ = user
    big = (io.BytesIO(b"x" * (6 * 1024 * 1024)), "resume.txt")
    r = c.post("/profile", data={"csrf_token": token(c, "/profile"), "skills": "x", "resume": big},
               content_type="multipart/form-data")
    assert r.status_code == 413 and "File too large" in r.get_data(as_text=True)
