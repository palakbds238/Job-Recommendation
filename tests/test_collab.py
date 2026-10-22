import sqlite3
import numpy as np
import pytest

import collab
import model as M
from collab import CollabModel
from tests.conftest import token, post


def _groups():
    inter = {}
    for u in range(1, 6):
        inter[u] = {1: 1.0, 2: 2.0, 3: 1.0}          # group A likes jobs 1,2,3
    for u in range(6, 11):
        inter[u] = {10: 1.0, 11: 2.0, 12: 1.0}       # group B likes jobs 10,11,12
    return inter


def test_similar_taste_jobs_are_recommended_and_others_are_not():
    inter = _groups(); inter[99] = {1: 1.0}
    scores, w = CollabModel(inter).scores_for(99)
    assert w > 0
    assert scores.get(2, 0) > 0 and scores.get(3, 0) > 0
    assert not any(j in scores for j in (10, 11, 12))      # other taste group untouched


def test_cold_start_gives_zero_weight():
    m = CollabModel(_groups())
    assert m.scores_for(12345) == ({}, 0.0)                # user with no interactions
    assert CollabModel({1: {1: 1.0}}).scores_for(1) == ({}, 0.0)   # fewer than 2 users
    assert CollabModel({}).scores_for(1) == ({}, 0.0)


def test_confidence_grows_with_user_activity_and_is_capped():
    inter = _groups()
    inter[50] = {1: 1.0}
    inter[51] = {1: 1.0, 2: 1.0, 3: 1.0, 4: 1.0}
    m = CollabModel(inter)
    assert 0 < m.confidence(50) < m.confidence(51) <= collab.MAX_WEIGHT


def test_explanation_points_to_the_users_own_job():
    inter = _groups(); inter[99] = {1: 2.0}
    m = CollabModel(inter)
    assert m.explain(99, 2) == (1, "applied")
    assert m.explain(99, 10) is None


def test_support_damping_weak_links_score_lower():
    inter = _groups()
    inter[20] = {1: 1.0, 77: 1.0}                          # a single user links 1 and 77
    s = CollabModel({**inter, 99: {1: 1.0}}).scores_for(99)[0]
    assert s[2] > s.get(77, 0)                             # 5 co-savers beat 1 co-saver


def test_interactions_from_db_ignores_admins_and_caps_weights():
    db = sqlite3.connect(":memory:")
    db.executescript("""CREATE TABLE users(id INTEGER PRIMARY KEY, is_admin INTEGER);
        CREATE TABLE saved_jobs(id INTEGER PRIMARY KEY, user_id INT, job_id INT);
        CREATE TABLE applied_jobs(id INTEGER PRIMARY KEY, user_id INT, job_id INT);
        INSERT INTO users VALUES (1,0),(2,1);
        INSERT INTO saved_jobs(user_id,job_id) VALUES (1,5),(2,5);
        INSERT INTO applied_jobs(user_id,job_id) VALUES (1,5),(1,6);""")
    inter = collab.interactions_from_db(db)
    assert 2 not in inter
    assert inter[1][5] == 3.0 and inter[1][6] == 2.0       # save(1)+apply(2), apply only
    assert collab.interactions_signature(db) == (2, 2, 2, 2)


@pytest.fixture(scope="module")
def models():
    return M.load_models()


def test_cf_lifts_score_and_adds_reason(models):
    txt = "python sql"
    base = {r["job_id"]: r for r in M.get_recommendations(models, txt, top_n=200, user_skills={"python"})}
    target = [j for j, r in base.items() if r["match_pct"] < 60][-1]
    with_cf = {r["job_id"]: r for r in M.get_recommendations(
        models, txt, top_n=200, user_skills={"python"}, cf_scores={target: 1.0}, cf_weight=0.3,
        cf_explain=lambda jid: "Because you saved X")}
    assert with_cf[target]["match_pct"] > base[target]["match_pct"]
    assert with_cf[target]["cf_reason"] == "Because you saved X"
    assert with_cf[target]["match_pct"] < 100
    others = [j for j in base if j != target]
    assert all(with_cf[j]["match_pct"] == base[j]["match_pct"] for j in others)   # nobody penalised


def test_end_to_end_cf_in_the_app(app_module, user):
    c, uid = user
    db = sqlite3.connect(__import__("os").environ["DATABASE_PATH"])
    # six other users who all saved jobs 1, 2 and 3 together
    for i in range(6):
        cur = db.execute("INSERT INTO users (name,email,password) VALUES (?,?,?)",
                         (f"cf{i}", f"cf{i}@t.com", "x"))
        for j in (1, 2, 3):
            db.execute("INSERT OR IGNORE INTO saved_jobs (user_id, job_id) VALUES (?,?)", (cur.lastrowid, j))
    db.commit()
    r = c.post("/save_job", json={"job_id": 1}, headers={"X-CSRFToken": token(c, "/dashboard")})
    assert r.get_json()["status"] == "saved"
    html = ""
    for page in range(1, 12):                         # results are paginated (10 per page)
        html = c.get(f"/recommendations?location=&page={page}").get_data(as_text=True)
        if "Because you saved" in html:
            break
    assert "Because you saved" in html
    assert "Similar users" in html


def test_save_job_rejects_unknown_or_malformed_ids(user):
    c, _ = user
    h = {"X-CSRFToken": token(c, "/dashboard")}
    assert c.post("/save_job", json={"job_id": 99999999}, headers=h).status_code == 404
    assert c.post("/save_job", json={"job_id": "abc"}, headers=h).status_code == 400
    assert c.post("/save_job", data="not json", headers=h).status_code == 400
