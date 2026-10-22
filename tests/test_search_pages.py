import re
import pytest


def _ids(html):
    """Job ids of the result cards (each card links to /job/<id> twice: title + Details)."""
    seen = []
    for i in re.findall(r'href="/job/(\d+)"', html.split('class="jobs-list"')[-1]):
        if i not in seen:
            seen.append(i)
    return [int(i) for i in seen]


def _jobs(app_module):
    return app_module.MODELS["jobs_df"].set_index("job_id")


# ── paginate() ──────────────────────────────────────────────────────────────
def test_paginate_basics(app_module):
    p = app_module.paginate
    assert p(0, 1) == {**p(0, 1), "pages": 1, "start": 0, "end": 0, "has_prev": False, "has_next": False}
    pg = p(25, 1)
    assert (pg["pages"], pg["start"], pg["end"], pg["has_next"], pg["has_prev"]) == (3, 0, 10, True, False)
    assert p(25, 99)["page"] == 3 and p(25, -4)["page"] == 1          # clamped
    assert (p(25, 3)["start"], p(25, 3)["end"]) == (20, 25)


def test_paginate_numbers_use_ellipsis(app_module):
    nums = app_module.paginate(500, 25)["numbers"]           # 50 pages, on page 25
    assert nums[0] == 1 and nums[-1] == 50 and nums.count(None) == 2 and 25 in nums
    assert app_module.paginate(30, 2)["numbers"] == [1, 2, 3]


# ── search ──────────────────────────────────────────────────────────────────
def test_search_is_paginated_and_pages_differ(app_module, user):
    c, _ = user
    p1 = c.get("/search?q=a").get_data(as_text=True)
    p2 = c.get("/search?q=a&page=2").get_data(as_text=True)
    assert 0 < len(_ids(p1)) <= 10 and _ids(p1) != _ids(p2) and not set(_ids(p1)) & set(_ids(p2))
    assert 'rel="next"' in p1 and 'rel="prev"' in p2 and "Showing 1–10 of" in p1
    assert c.get("/search?q=a&page=9999").status_code == 200           # clamped, no crash
    assert c.get("/search?q=a&page=abc").status_code == 200


def test_pager_links_keep_the_filters(user):
    c, _ = user
    html = c.get("/search?q=a&sort=salary&min_salary=1").get_data(as_text=True)
    nxt = re.search(r'rel="next" href="([^"]+)"', html).group(1).replace("&amp;", "&")
    assert "q=a" in nxt and "sort=salary" in nxt and "min_salary=1" in nxt and "page=2" in nxt


def test_category_experience_and_type_filters(app_module, user):
    c, _ = user; jobs = _jobs(app_module)
    cat = jobs["category"].value_counts().index[0]
    ids = _ids(c.get("/search", query_string={"category": cat}).get_data(as_text=True))
    assert ids and all(jobs.loc[i, "category"] == cat for i in ids)
    exp = jobs["experience_required"].iloc[0]
    ids = _ids(c.get("/search", query_string={"experience": exp}).get_data(as_text=True))
    assert ids and all(jobs.loc[i, "experience_required"] == exp for i in ids)
    jt = jobs["job_type"].iloc[0]
    ids = _ids(c.get("/search", query_string={"job_type": jt}).get_data(as_text=True))
    assert ids and all(jobs.loc[i, "job_type"] == jt for i in ids)


def test_location_filter_is_case_insensitive_and_strict(app_module, user):
    c, _ = user; jobs = _jobs(app_module)
    ids = _ids(c.get("/search?location=PUNE").get_data(as_text=True))
    assert ids and all("pune" in jobs.loc[i, "location"].lower() for i in ids)


def test_min_salary_and_salary_sort(app_module, user):
    c, _ = user; jobs = _jobs(app_module)
    ids = _ids(c.get("/search?min_salary=20").get_data(as_text=True))
    assert ids and all(jobs.loc[i, "salary_lpa"] >= 20 for i in ids)
    ids = _ids(c.get("/search?q=a&sort=salary").get_data(as_text=True))
    sal = [jobs.loc[i, "salary_lpa"] for i in ids]
    assert sal == sorted(sal, reverse=True)


def test_every_word_of_the_query_must_match_somewhere(app_module, user):
    c, _ = user; jobs = _jobs(app_module)
    ids = _ids(c.get("/search?q=python+developer").get_data(as_text=True))
    assert ids
    for i in ids:
        row = jobs.loc[i]
        blob = " ".join(str(row[k]).lower() for k in ("title", "skills_required", "category", "company", "location", "description"))
        assert "python" in blob and "developer" in blob


def test_title_matches_outrank_description_only_matches(app_module, user):
    c, _ = user; jobs = _jobs(app_module)
    first = _ids(c.get("/search?q=python").get_data(as_text=True))[0]
    assert "python" in (jobs.loc[first, "title"] + jobs.loc[first, "skills_required"]).lower()


def test_active_filter_chips_can_be_removed(user):
    c, _ = user
    html = c.get("/search?q=python&category=Data+Science&location=Pune").get_data(as_text=True)
    chips = dict(re.findall(r'class="chip chip-blue" href="([^"]+)" title="Remove this filter">([^<]+)', html)[::-1][::-1] and
                 [(m[1].strip(), m[0].replace("&amp;", "&")) for m in re.findall(
                     r'class="chip chip-blue" href="([^"]+)" title="Remove this filter">([^<]+)', html)])
    cat_chip = next(v for k, v in chips.items() if k.startswith("Category"))
    assert "category=" not in cat_chip and "location=Pune" in cat_chip and "q=python" in cat_chip


def test_no_criteria_shows_browse_landing(user):
    html = user[0].get("/search").get_data(as_text=True)
    assert "Browse categories" in html and "Start your search" in html and "jobs-list" not in html


def test_no_results_with_filters_shows_popup_and_clear_link(user):
    html = user[0].get("/search?q=zzzqqq&category=Finance").get_data(as_text=True)
    assert "showPopup" in html and "Clear filters" in html and "No jobs found" in html


def test_search_form_has_all_controls(user):
    html = user[0].get("/search").get_data(as_text=True)
    for name in ('name="category"', 'name="location"', 'name="experience"', 'name="job_type"',
                 'name="min_salary"', 'name="sort"'):
        assert name in html


# ── recommendations: sort + pages ───────────────────────────────────────────
def test_recommendation_pages_and_count(user):
    c, _ = user
    p1 = c.get("/recommendations?location=").get_data(as_text=True)
    p2 = c.get("/recommendations?location=&page=2").get_data(as_text=True)
    assert 'rel="next"' in p1 and "jobs found" in p1
    ids = lambda h: set(re.findall(r'href="/job/(\d+)"', h))          # noqa: E731
    assert ids(p1) and ids(p2) and not ids(p1) & ids(p2)


def test_recommendation_salary_sort(app_module, user):
    c, _ = user; jobs = _jobs(app_module)
    html = c.get("/recommendations?location=&sort=salary").get_data(as_text=True)
    ids = []
    for i in re.findall(r'href="/job/(\d+)"', html):
        if int(i) not in ids:
            ids.append(int(i))
    sal = [jobs.loc[i, "salary_lpa"] for i in ids]
    assert len(sal) > 3 and sal == sorted(sal, reverse=True)
    assert 'value="salary" selected' in html
