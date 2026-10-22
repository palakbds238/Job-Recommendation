"""
evaluate.py — recommendation-level evaluation on SIMULATED profiles
===================================================================
There is no real user-interaction data yet, so this builds pseudo-users from the
job dataset itself:

  for each job J (several random draws each):
     user skills = 60-80% of J's skills + 1-2 distractor skills from other fields
     experience / education copied from J, domain left as "Any"
  A recommended job counts as RELEVANT if it is in the same category as J.

Metrics (higher is better):  P@5, Hit@1, MRR, nDCG@10.

It compares:  tfidf-only | legacy (the original algorithm) | hybrid (new).
Caveat: simulated profiles share vocabulary with the dataset, so absolute numbers
are optimistic; the *comparison between methods* is the useful part.

    python evaluate.py
"""
import random

import numpy as np

import model as M
from skills import normalize_skill

SEED, DRAWS = 7, 4


def make_profiles(models):
    rng = random.Random(SEED)
    df = models["jobs_df"]
    all_skills = sorted(models["skill_vocab"])
    profiles = []
    for i, row in df.iterrows():
        req = [s.strip() for s in str(row["skills_required"]).split(",") if s.strip()]
        for _ in range(DRAWS):
            k = max(1, round(len(req) * rng.uniform(0.6, 0.8)))
            mine = rng.sample(req, k)
            mine += rng.sample(all_skills, rng.randint(1, 2))
            skills_text = ", ".join(mine)
            profiles.append({
                "category": row["category"], "job_id": int(row["job_id"]),
                "skills": skills_text,
                "text": M.build_user_profile_text(skills_text, row["experience_required"],
                                                  row["education_required"], "Any"),
            })
    return profiles


# ── rankers: each returns an array of job scores aligned with jobs_df ───────
def rank_tfidf(models, p):
    v = models["pool_tfidf"].transform([p["text"]])
    return (v @ models["tfidf_matrix"].T).toarray().ravel()


def rank_legacy(models, p):
    """Re-implementation of the ORIGINAL algorithm: cosine, x1.15 boost for the
    RF-predicted category."""
    v = models["pool_tfidf"].transform([p["text"]])
    s = (v @ models["tfidf_matrix"].T).toarray().ravel()
    cat = models["le"].inverse_transform([models["rf"].predict(v)[0]])[0]
    return np.where(models["jobs_df"]["category"].values == cat, s * 1.15, s)


def rank_hybrid(models, p, use_embeddings=False):
    skills = M.collect_user_skills(models, p["skills"])
    sc, *_ = M.score_jobs(models, p["text"], skills, use_embeddings=use_embeddings)
    return sc["final"].values


def metrics(models, profiles, ranker):
    cats = models["jobs_df"]["category"].values
    p5, h1, mrr, ndcg = [], [], [], []
    for p in profiles:
        order = np.argsort(-ranker(models, p), kind="stable")
        rel = (cats[order] == p["category"]).astype(float)
        p5.append(rel[:5].mean())
        h1.append(rel[0])
        first = np.argmax(rel) if rel.any() else None
        mrr.append(1 / (first + 1) if first is not None else 0)
        disc = 1 / np.log2(np.arange(2, 12))
        dcg = (rel[:10] * disc).sum()
        ideal = (np.sort(rel)[::-1][:10] * disc).sum()
        ndcg.append(dcg / ideal if ideal else 0)
    return [np.mean(x) for x in (p5, h1, mrr, ndcg)]


def main():
    models = M.load_models()
    profiles = make_profiles(models)
    print(f"{len(profiles)} simulated profiles over {len(models['jobs_df'])} jobs\n")
    rows = [("TF-IDF only", rank_tfidf), ("Legacy (original)", rank_legacy),
            ("Hybrid (new)", rank_hybrid)]
    print(f"{'Method':<20}{'P@5':>8}{'Hit@1':>8}{'MRR':>8}{'nDCG@10':>10}")
    print("-" * 54)
    for name, fn in rows:
        m = metrics(models, profiles, fn)
        print(f"{name:<20}" + "".join(f"{x:>8.3f}" for x in m[:3]) + f"{m[3]:>10.3f}")
    return models


if __name__ == "__main__":
    main()
