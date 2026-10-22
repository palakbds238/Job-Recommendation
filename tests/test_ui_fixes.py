import pytest
import model as M
from tests.conftest import post


@pytest.fixture(scope="module")
def models():
    return M.load_models()


# ── password hint ───────────────────────────────────────────────────────────
def test_password_hint_matches_the_real_rule(app_module):
    html = app_module.app.test_client().get("/register").get_data(as_text=True)
    assert 'minlength="8"' in html and "Minimum 8 characters" in html
    assert "6 characters" not in html


# ── accuracy figures removed ────────────────────────────────────────────────
def test_model_accuracy_is_not_shown(app_module, admin):
    home = app_module.app.test_client().get("/").get_data(as_text=True)
    assert "ML Accuracy" not in home and "95.24" not in home and "95%" not in home
    page = admin.get("/admin/analytics")
    html = page.get_data(as_text=True)
    assert page.status_code == 200
    assert "Model Accuracy" not in html and "95.24" not in html
    assert "Jobs in Pool" in html and "Live Jobs" in html


# ── strict location filtering ───────────────────────────────────────────────
def _locs(recs):
    return {r["location"] for r in recs}


def test_location_filter_returns_only_that_location(models):
    recs = M.get_recommendations(models, "python sql", top_n=200, filter_location="pune",
                                 user_skills={"python"})
    assert recs and _locs(recs) == {"Pune"}


def test_location_with_no_jobs_returns_nothing_not_other_cities(models):
    assert M.get_recommendations(models, "python sql", top_n=200, filter_location="indore",
                                 user_skills={"python"}) == []


def test_several_locations_and_case_insensitivity(models):
    recs = M.get_recommendations(models, "python sql", top_n=200,
                                 filter_location=" PUNE , chennai / Kochi",
                                 user_skills={"python"})
    assert _locs(recs) <= {"Pune", "Chennai", "Kochi"} and len(_locs(recs)) >= 2


def test_remote_jobs_only_when_asked(models):
    kw = dict(top_n=200, filter_location="indore", user_skills={"python"})
    assert M.get_recommendations(models, "python sql", **kw) == []
    remote = M.get_recommendations(models, "python sql", include_remote=True, **kw)
    assert remote and all("remote" in (r["location"].lower()) or r["job_type"] == "Remote" for r in remote)


def test_any_or_empty_location_means_no_filter(models):
    base = len(M.get_recommendations(models, "python sql", top_n=500, user_skills={"python"}))
    for v in ("", "any", "Any Location", None):
        assert len(M.get_recommendations(models, "python sql", top_n=500, filter_location=v,
                                         user_skills={"python"})) == base


def _cards(html):
    """Locations of the job cards ('Company · Location' lines), ignoring the datalist."""
    import re
    return set(re.findall(r'jc-company">[^<]*· ([^<]+)<', html))


def test_profile_location_filters_recommendations_by_default(user):
    c, _ = user                                   # fixture profile says "Indore"
    html = c.get("/recommendations").get_data(as_text=True)
    cards = _cards(html)
    assert all("indore" in loc.lower() for loc in cards)          # nothing from other cities
    assert "Bangalore" not in cards and "Pune" not in cards
    assert "your preferred location" in html and "Show all locations" in html


def test_city_without_jobs_shows_not_found_popup(user):
    c, _ = user
    post(c, "/profile", {"skills": "Python, SQL", "experience": "1-3 years", "education": "B.Tech",
                         "domain": "Any", "location": "Atlantis", "goals": "x"},
         path_for_token="/profile")
    html = c.get("/recommendations").get_data(as_text=True)
    assert "No jobs found in Atlantis" in html and "showPopup" in html
    assert not _cards(html)                                       # and no jobs from other cities
    assert "Include remote jobs" in html


def test_explicit_location_overrides_profile(user):
    c, _ = user
    assert _cards(c.get("/recommendations?location=Pune").get_data(as_text=True)) == {"Pune"}
    everything = _cards(c.get("/recommendations?location=").get_data(as_text=True))
    assert {"Bangalore", "Mumbai"} <= everything          # empty value = any location


def test_location_can_be_typed_freely(user):
    c, _ = user
    html = c.get("/recommendations?location=Indore").get_data(as_text=True)
    assert 'value="Indore"' in html and 'list="loc-list"' in html     # text box, not a fixed list


# ── search: robustness + "not found" pop-up ─────────────────────────────────
def test_search_with_regex_characters_does_not_crash(user):
    c, _ = user
    for q in ("c++", "(", "[", "a.b*", "\\"):
        assert c.get("/search", query_string={"q": q}).status_code == 200


def test_unrelated_search_shows_not_found_popup(user):
    c, _ = user
    html = c.get("/search?q=pizza").get_data(as_text=True)
    assert "No jobs found" in html and "showPopup" in html and "pizza" in html
    ok = c.get("/search?q=python").get_data(as_text=True)
    assert "We could not find anything" not in ok


def test_search_popup_cannot_be_used_for_script_injection(user):
    c, _ = user
    evil = "</script><script>alert(1)</script>"
    html = c.get("/search", query_string={"q": evil}).get_data(as_text=True)
    assert evil not in html
    assert "<script>alert(1)" not in html


def test_search_matches_cities(user):
    c, _ = user
    html = c.get("/search?q=pune").get_data(as_text=True)
    assert "· Pune" in html and "We could not find anything" not in html


# ── glass theme + login page hygiene ────────────────────────────────────────
def test_login_page_does_not_advertise_admin_credentials(app_module):
    html = app_module.app.test_client().get("/login").get_data(as_text=True)
    assert "admin123" not in html and "Demo Admin" not in html


def test_glass_theme_is_loaded_after_the_base_stylesheet(app_module):
    html = app_module.app.test_client().get("/").get_data(as_text=True)
    assert html.index("css/style.css") < html.index("css/glass.css")
    css = app_module.app.test_client().get("/static/css/glass.css").get_data(as_text=True)
    assert "backdrop-filter" in css and "prefers-reduced-transparency" in css
