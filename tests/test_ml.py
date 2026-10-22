import numpy as np
import pytest
import embeddings
import model as M
from skills import normalize_skill, parse_skill_list


@pytest.fixture(scope="module")
def models():
    return M.load_models()


def test_aliases_are_normalised():
    assert normalize_skill("JS") == "javascript"
    assert parse_skill_list("Python, ML, Reactjs, CI/CD") == {
        "python", "machine learning", "react", "ci/cd"}


def test_partial_word_no_longer_counts_as_a_skill(models):
    """Old behaviour: 'machine' alone matched the skill 'Machine Learning'."""
    recs = M.get_recommendations(
        models, "machine operator factory", top_n=50,
        user_skills=M.collect_user_skills(models, "machine operator"))
    for r in recs:
        assert "Machine Learning" not in r["matched_skills"]


def test_extraction_from_resume_text(models):
    found = models["extractor"].extract("Built REST APIs in Flask with PostgreSQL and k8s. Can go far.")
    assert {"flask", "postgresql", "kubernetes", "rest apis"} <= found
    assert "go" not in found and "can" not in found       # ambiguous words ignored


def test_no_artificial_30_percent_floor(models):
    recs = M.get_recommendations(models, "zzz qqq", top_n=5, user_skills=set())
    assert all(r["match_pct"] < 30 for r in recs)


def test_verified_skills_boost_score(models):
    txt, have = "python sql flask", {"python", "sql", "flask"}
    base = {r["job_id"]: r for r in M.get_recommendations(models, txt, top_n=200, user_skills=have)}
    boosted = {r["job_id"]: r for r in M.get_recommendations(
        models, txt, top_n=200, user_skills=have, verified_skills={"python"})}
    has_py = lambda r: any(normalize_skill(s) == "python" for s in r["matched_skills"])  # noqa: E731
    with_python = [j for j, r in base.items() if has_py(r)]
    assert with_python, "dataset should contain Python jobs"
    assert all(boosted[j]["match_pct"] >= base[j]["match_pct"] for j in with_python)
    assert any(boosted[j]["match_pct"] > base[j]["match_pct"] for j in with_python)
    assert all(boosted[j]["verified_skills"] for j in with_python)
    no_python = [j for j, r in base.items() if not has_py(r)]
    assert all(boosted[j]["match_pct"] == base[j]["match_pct"] for j in no_python)


def test_custom_jobs_enter_the_pool(models):
    row = {"id": 1, "title": "Quantum Basket Weaver", "company": "Acme",
           "skills_required": "Python, Basket Weaving", "category": "Software Engineering",
           "description": "weave baskets with python", "location": "Indore",
           "experience_required": "0-1 years", "education_required": "B.Tech",
           "salary_range": "5-8 LPA", "salary_lpa": 6.0, "job_type": "Full-time", "openings": 2}
    n = len(models["jobs_df"])
    M.refresh_job_pool(models, [row])
    assert len(models["jobs_df"]) == n + 1
    assert models["tfidf_matrix"].shape[0] == n + 1
    recs = M.get_recommendations(models, "quantum basket weaving python", top_n=3,
                                 user_skills={"python", "basket weaving"})
    assert recs[0]["title"] == "Quantum Basket Weaver"
    assert recs[0]["job_id"] == M.CUSTOM_JOB_OFFSET + 1
    M.refresh_job_pool(models, [])
    assert len(models["jobs_df"]) == n


def test_embedding_plumbing_with_stub_encoder(models):
    """Verifies the wiring only (a real sentence-transformer is not available in CI)."""
    rng = np.random.RandomState(0)
    table = {}

    def stub(texts):
        out = []
        for t in texts:
            v = table.setdefault(t, rng.randn(16))
            out.append(v / np.linalg.norm(v))
        return np.array(out, dtype=np.float32)

    embeddings.set_encoder(stub, "stub")
    try:
        models["base_emb"] = stub(models["base_df"]["combined_features"].tolist())
        M.refresh_job_pool(models, [])
        recs = M.get_recommendations(models, "python sql", top_n=3, user_skills={"python"})
        assert all(r["score_breakdown"]["semantic"] is not None for r in recs)
    finally:
        embeddings.set_encoder(None, None)
        embeddings._tried = False
        models["base_emb"] = None
        M.refresh_job_pool(models, [])
