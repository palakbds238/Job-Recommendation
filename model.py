"""
model.py
--------
Recommendation engine used by the Flask routes.

Hybrid score for every job (all components in 0..1):

  skills   : fraction of the job's required skills the user has   (normalised)
  text     : TF-IDF cosine similarity between profile and job text
  semantic : embedding cosine similarity (only if embeddings are available)
  category : Random-Forest confidence that the job's category fits the user

  final = weighted sum  (+ a small bonus for blockchain-VERIFIED skills)

The displayed match % is simply round(100 * final) — no artificial floor.
"""
import hashlib
import logging
import os
import pickle
import re
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

import embeddings
from skills import SkillExtractor, normalize_skill, parse_skill_list

log = logging.getLogger("model")

MODEL_DIR = "ml_models"
CUSTOM_JOB_OFFSET = 100000          # custom (admin) job ids start here
LIVE_JOB_OFFSET = 1000000           # live (API) job ids start here

_TEXT_COLS = ["title", "company", "skills_required", "category", "description",
              "location", "experience_required", "education_required",
              "salary_range", "job_type", "source", "url", "combined_features"]
_NUM_COLS = ["salary_lpa", "openings", "posted_days_ago"]

W_WITH_EMB = {"skills": 0.40, "text": 0.20, "semantic": 0.30, "category": 0.10}
W_NO_EMB   = {"skills": 0.50, "text": 0.35, "semantic": 0.00, "category": 0.15}
TEXT_SCALE = 2.0                    # tf-idf cosine rarely exceeds 0.5
VERIFIED_BONUS, VERIFIED_CAP = 0.05, 0.15


# ── Loading ─────────────────────────────────────────────────────────────────
def _required_files():
    return [f"{MODEL_DIR}/{n}" for n in (
        "tfidf_vectorizer.pkl", "tfidf_matrix.pkl", "rf_classifier.pkl",
        "label_encoder.pkl", "jobs_processed.csv")]


def load_models(auto_train=True):
    """Load saved models. If they are missing (fresh clone / fresh deploy),
    train them automatically so the app can start without a manual step."""
    if auto_train and not all(os.path.exists(p) for p in _required_files()):
        log.warning("Model files missing — training now (one-off)…")
        import train_model
        train_model.train(verbose=False)

    models = {}
    with open(f"{MODEL_DIR}/tfidf_vectorizer.pkl", "rb") as f:
        models["tfidf"] = pickle.load(f)
    with open(f"{MODEL_DIR}/tfidf_matrix.pkl", "rb") as f:
        models["base_matrix"] = pickle.load(f)
    with open(f"{MODEL_DIR}/rf_classifier.pkl", "rb") as f:
        models["rf"] = pickle.load(f)
    with open(f"{MODEL_DIR}/label_encoder.pkl", "rb") as f:
        models["le"] = pickle.load(f)
    models["base_df"] = pd.read_csv(f"{MODEL_DIR}/jobs_processed.csv")
    models["base_df"]["source"] = "dataset"
    models["base_df"]["url"] = ""
    models["base_emb"] = _load_base_embeddings(models["base_df"])
    models["pool_sig"] = None
    refresh_job_pool(models, [])
    log.info("ML models loaded (%d jobs, embeddings=%s).",
             len(models["jobs_df"]), models["emb"] is not None)
    return models


def _load_base_embeddings(df):
    if not embeddings.available():
        return None
    path = f"{MODEL_DIR}/job_embeddings.npy"
    meta = f"{MODEL_DIR}/job_embeddings.txt"
    name = embeddings.model_name()
    if os.path.exists(path) and os.path.exists(meta):
        try:
            arr = np.load(path)
            if arr.shape[0] == len(df) and open(meta).read().strip() == name:
                return arr
        except Exception:  # noqa: BLE001
            pass
    arr = embeddings.encode(df["combined_features"].fillna("").tolist())
    np.save(path, arr)
    open(meta, "w").write(name)
    return arr


# ── Job pool = CSV jobs + admin-added jobs + live (API) jobs ────────────────
def _combined_text(r):
    c = lambda x: "" if pd.isna(x) else str(x).lower().strip()  # noqa: E731
    return " ".join([c(r["title"]), c(r["skills_required"]), c(r["description"]),
                     c(r["category"]), c(r["experience_required"])])


def _custom_df(rows):
    df = pd.DataFrame([{
        "job_id": CUSTOM_JOB_OFFSET + int(r["id"]),
        "title": r["title"], "company": r["company"],
        "skills_required": r["skills_required"], "category": r["category"],
        "description": r["description"], "location": r["location"],
        "experience_required": r["experience_required"],
        "education_required": r["education_required"],
        "salary_range": r["salary_range"], "salary_lpa": r["salary_lpa"] or 0,
        "job_type": r["job_type"], "openings": r["openings"] or 1,
        "posted_days_ago": 0, "source": "admin", "url": "",
    } for r in rows])
    df["combined_features"] = df.apply(_combined_text, axis=1)
    return df


def _days_since(iso):
    try:
        d = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return max(0, (datetime.now(timezone.utc) - d).days)
    except (ValueError, TypeError):
        return 0


def _live_df(rows):
    df = pd.DataFrame([{
        "job_id": LIVE_JOB_OFFSET + int(r["id"]),
        "title": r["title"], "company": r["company"],
        "skills_required": r["skills_required"], "category": r["category"],
        "description": r["description"], "location": r["location"],
        "experience_required": r["experience_required"],
        "education_required": r["education_required"],
        "salary_range": r["salary_range"], "salary_lpa": r["salary_lpa"] or 0,
        "job_type": r["job_type"], "openings": 1,
        "posted_days_ago": _days_since(r["posted_at"] or r["fetched_at"]),
        "source": r["source"], "url": r["url"] or "",
    } for r in rows])
    df["combined_features"] = df.apply(_combined_text, axis=1)
    return df


def _new_pool_vectorizer():
    return TfidfVectorizer(ngram_range=(1, 2), stop_words="english",
                           max_features=5000, sublinear_tf=True)


def refresh_job_pool(models, custom_rows, live_rows=()):
    """(Re)build the live job pool: dataset + admin jobs + live API jobs.

    The similarity vectorizer is re-fitted on the whole pool, because live jobs use
    vocabulary the 101-job training set has never seen. The Random-Forest keeps its
    own original vectorizer (models['tfidf']) since it was trained with it."""
    base_df = models["base_df"]
    cols = [c for c in base_df.columns if c != "category_encoded"]
    parts = [base_df[cols]]
    if custom_rows:
        parts.append(_custom_df(custom_rows)[cols])
    if live_rows:
        parts.append(_live_df(live_rows)[cols])
    jobs_df = pd.concat(parts, ignore_index=True)
    jobs_df = jobs_df.fillna({**{c: "" for c in _TEXT_COLS if c in jobs_df},
                              **{c: 0 for c in _NUM_COLS if c in jobs_df}})

    if len(parts) > 1:
        pool_vec = _new_pool_vectorizer()
        matrix = pool_vec.fit_transform(jobs_df["combined_features"]).tocsr()
    else:
        pool_vec, matrix = models["tfidf"], models["base_matrix"]

    emb = None
    if models.get("base_emb") is not None and embeddings.available():
        texts = jobs_df["combined_features"].tolist()
        cache = models.setdefault("_emb_cache", {})
        n0 = len(base_df)
        key = lambda t: hashlib.md5(t.encode("utf-8")).hexdigest()  # noqa: E731
        missing = [t for t in texts[n0:] if key(t) not in cache]
        if missing:
            for t, v in zip(missing, embeddings.encode(missing)):
                cache[key(t)] = v
        extra = [cache[key(t)] for t in texts[n0:]]
        emb = np.vstack([models["base_emb"]] + [np.array(extra)]) if extra else models["base_emb"]

    skill_sets = [parse_skill_list(s) for s in jobs_df["skills_required"]]
    display = {}
    for s in base_df["skills_required"]:
        for raw in str(s).split(","):
            display.setdefault(normalize_skill(raw), raw.strip())
    vocab = set().union(*[parse_skill_list(s) for s in base_df["skills_required"]]) | \
        set().union(*skill_sets)
    # one dict.update() call = the swap is atomic for other request threads
    models.update({"jobs_df": jobs_df, "pool_tfidf": pool_vec, "tfidf_matrix": matrix,
                   "emb": emb, "job_skill_sets": skill_sets, "skill_vocab": vocab,
                   "skill_display": display, "extractor": SkillExtractor(vocab)})
    return models


def custom_jobs_signature(rows):
    """Cheap fingerprint so every gunicorn worker notices admin changes."""
    ids = [int(r["id"]) for r in rows]
    return hashlib.md5(f"{len(ids)}:{sum(ids)}:{max(ids, default=0)}".encode()).hexdigest()


# ── Profile helpers ─────────────────────────────────────────────────────────
def build_user_profile_text(skills, experience, education, domain,
                            location="", goals="", resume_text=""):
    """Single text string for TF-IDF / embeddings (skills repeated for weight)."""
    parts = []
    if skills:
        parts.extend([skills] * 3)
    if domain and domain != "Any":
        parts.append(domain)
    if experience:
        parts.append(experience)
    if education:
        parts.append(education)
    if goals:
        parts.append(goals)
    if resume_text:
        parts.append(resume_text[:1000])
    return " ".join(parts).lower()


def collect_user_skills(models, skills_field, goals="", resume_text=""):
    """Normalised skill set = typed skills + skills found in goals/resume text."""
    s = parse_skill_list(skills_field)
    s |= models["extractor"].extract(f"{goals}\n{resume_text}")
    return s


# ── Scoring ─────────────────────────────────────────────────────────────────
def score_jobs(models, profile_text, user_skills=None, verified_skills=None,
               use_embeddings=True, cf_scores=None, cf_weight=0.0):
    """Return a DataFrame (aligned with models['jobs_df']) with every score
    component plus 'final'. Also returns (predicted_category, confidence).

    cf_scores / cf_weight: optional collaborative-filtering signal
    ({job_id: 0..1}, blend weight). It lifts a job's content score by up to
    cf_weight of the remaining gap to 1:   final = c + w * cf * (1 - c)."""
    jobs_df = models["jobs_df"]
    n = len(jobs_df)
    user_vec = models["tfidf"].transform([profile_text])          # for the RF
    pool_vec = models["pool_tfidf"].transform([profile_text])     # for similarity

    text = np.clip(cosine_similarity(pool_vec, models["tfidf_matrix"]).ravel(), 0, 1)
    text_n = np.clip(text * TEXT_SCALE, 0, 1)

    if user_skills is None:
        user_skills = models["extractor"].extract(profile_text)
    user_skills = set(user_skills)
    verified = set(verified_skills or ())

    coverage = np.zeros(n)
    bonus = np.zeros(n)
    for i, req in enumerate(models["job_skill_sets"]):
        if req:
            hit = req & user_skills
            coverage[i] = len(hit) / len(req)
            bonus[i] = min(VERIFIED_CAP, VERIFIED_BONUS * len(hit & verified))

    semantic = np.zeros(n)
    sem_on = bool(use_embeddings and models.get("emb") is not None
                  and embeddings.available())
    if sem_on:
        u = embeddings.encode([profile_text])[0]
        semantic = np.clip(models["emb"] @ u, 0, 1)

    pred_cat, conf = None, 0.0
    cat = np.zeros(n)
    try:
        proba = models["rf"].predict_proba(user_vec)[0]
        k = int(np.argmax(proba))
        pred_cat = models["le"].inverse_transform([models["rf"].classes_[k]])[0]
        conf = float(proba[k])
        cat = np.where(jobs_df["category"].values == pred_cat, conf, 0.0)
    except Exception:  # noqa: BLE001
        pass

    w = W_WITH_EMB if sem_on else W_NO_EMB
    final = (w["skills"] * coverage + w["text"] * text_n
             + w["semantic"] * semantic + w["category"] * cat + bonus)
    final = np.minimum(final, 0.99)
    collab = np.zeros(n)
    if cf_scores and cf_weight > 0:
        collab = jobs_df["job_id"].map(cf_scores).fillna(0.0).values.astype(float)
        final = np.minimum(final + cf_weight * collab * (1.0 - final), 0.99)
    out = pd.DataFrame({"coverage": coverage, "text": text, "semantic": semantic,
                        "category_score": cat, "verified_bonus": bonus,
                        "collab": collab, "final": final}, index=jobs_df.index)
    return out, pred_cat, conf, sem_on


def location_terms(text):
    """'Indore, Bhopal / Remote' -> ['indore', 'bhopal', 'remote'] ('any' = no filter)."""
    terms = [t.strip().lower() for t in re.split(r"[,/;|]+", str(text or ""))]
    return [t for t in terms if t and t != "any" and t != "any location"]


def get_recommendations(models, user_profile_text, top_n=20,
                        filter_location=None, filter_experience=None,
                        filter_category=None, min_salary=None,
                        user_skills=None, verified_skills=None,
                        cf_scores=None, cf_weight=0.0, cf_explain=None,
                        include_remote=False):
    """Rank jobs for a profile. See module docstring for the scoring formula.
    cf_explain(job_id) -> short text such as 'Because you saved X' (optional)."""
    if not user_profile_text.strip():
        return []
    scores, pred_cat, _conf, sem_on = score_jobs(
        models, user_profile_text, user_skills, verified_skills,
        cf_scores=cf_scores, cf_weight=cf_weight)
    jobs_df = models["jobs_df"].join(scores)

    terms = location_terms(filter_location)
    if terms:
        # Strict: only jobs in the requested place(s). Remote jobs are added only when
        # the user asks for them (they used to be mixed in silently, so typing "Indore"
        # also showed Bangalore / Pune jobs that happened to be remote).
        loc = jobs_df["location"].str.lower()
        keep = pd.Series(False, index=jobs_df.index)
        for t in terms:
            keep |= loc.str.contains(t, regex=False, na=False)
        if include_remote:
            keep |= loc.str.contains("remote", regex=False, na=False) | (jobs_df["job_type"] == "Remote")
        jobs_df = jobs_df[keep]
    if filter_experience and filter_experience not in ("Any", ""):
        jobs_df = jobs_df[jobs_df["experience_required"] == filter_experience]
    if filter_category and filter_category not in ("Any", ""):
        jobs_df = jobs_df[jobs_df["category"] == filter_category]
    if min_salary:
        try:
            jobs_df = jobs_df[jobs_df["salary_lpa"] >= float(min_salary)]
        except (ValueError, TypeError):
            pass
    if jobs_df.empty:
        return []

    jobs_df = jobs_df.sort_values("final", ascending=False).head(top_n)
    verified = set(verified_skills or ())
    have = set(user_skills) if user_skills is not None \
        else models["extractor"].extract(user_profile_text)

    recs = []
    for idx, row in jobs_df.iterrows():
        match_pct = int(round(100 * float(row["final"])))
        matched, missing, ver = [], [], []
        for raw in str(row["skills_required"]).split(","):
            disp = raw.strip()
            if not disp:
                continue
            norm = normalize_skill(disp)
            if norm in have:
                matched.append(disp)
                if norm in verified:
                    ver.append(disp)
            else:
                missing.append(disp)
        total = len(matched) + len(missing)
        if matched:
            why = f"You have {len(matched)} of {total} required skills: {', '.join(matched[:3])}"
            if len(matched) > 3:
                why += f" and {len(matched) - 3} more."
            if ver:
                why += f" ({len(ver)} verified on-chain)"
        else:
            why = f"This role aligns with your {pred_cat or 'target'} domain interest."
        cf_reason = None
        if cf_explain and cf_weight > 0 and float(row["collab"]) > 0.05:
            cf_reason = cf_explain(int(row["job_id"]))
            if cf_reason:
                why = f"{cf_reason}. {why}"
        recs.append({
            "job_id": int(row["job_id"]), "title": row["title"],
            "source": row.get("source", "dataset"), "url": row.get("url", ""),
            "posted_days_ago": int(row.get("posted_days_ago", 0) or 0),
            "cf_reason": cf_reason,
            "company": row["company"], "location": row["location"],
            "category": row["category"], "experience": row["experience_required"],
            "salary_range": row["salary_range"],
            "salary_lpa": round(float(row["salary_lpa"]), 1),
            "job_type": row["job_type"], "description": row["description"],
            "skills_required": row["skills_required"],
            "matched_skills": matched, "missing_skills": missing[:5],
            "verified_skills": ver,
            "match_pct": match_pct, "why_recommended": why,
            "is_top_pick": match_pct >= 70,
            "openings": int(row.get("openings", 1) or 1),
            "score_breakdown": {
                "skills": round(float(row["coverage"]), 2),
                "text": round(float(row["text"]), 2),
                "semantic": round(float(row["semantic"]), 2) if sem_on else None,
                "category": round(float(row["category_score"]), 2),
                "collaborative": round(float(row["collab"]), 2) if cf_weight > 0 else None,
            },
        })
    return recs


def predict_category(models, text):
    """Most likely job category for a text profile (dashboard 'Best fit')."""
    try:
        vec = models["tfidf"].transform([text])
        pred = models["rf"].predict(vec)[0]
        proba = models["rf"].predict_proba(vec)[0].max()
        return models["le"].inverse_transform([pred])[0], round(proba * 100, 1)
    except Exception:  # noqa: BLE001
        return "Unknown", 0.0


def get_category_stats(models):
    return models["jobs_df"]["category"].value_counts().to_dict()


def get_location_stats(models):
    return models["jobs_df"]["location"].value_counts().head(10).to_dict()


def get_experience_stats(models):
    return models["jobs_df"]["experience_required"].value_counts().to_dict()
