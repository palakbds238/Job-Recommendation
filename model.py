"""
model.py
--------
Recommendation Engine — loads trained ML models and
provides job recommendation functions used by Flask routes.
"""

import pickle
import numpy as np
import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity
import os

# ── Load Pre-trained Models ────────────────────────────────────────────────────
MODEL_DIR = "ml_models"

def load_models():
    """Load all saved ML models from disk."""
    models = {}
    try:
        with open(f"{MODEL_DIR}/tfidf_vectorizer.pkl", "rb") as f:
            models["tfidf"] = pickle.load(f)
        with open(f"{MODEL_DIR}/tfidf_matrix.pkl", "rb") as f:
            models["tfidf_matrix"] = pickle.load(f)
        with open(f"{MODEL_DIR}/rf_classifier.pkl", "rb") as f:
            models["rf"] = pickle.load(f)
        with open(f"{MODEL_DIR}/label_encoder.pkl", "rb") as f:
            models["le"] = pickle.load(f)
        models["jobs_df"] = pd.read_csv(f"{MODEL_DIR}/jobs_processed.csv")
        print("✅ All ML models loaded successfully.")
    except FileNotFoundError as e:
        print(f"❌ Model file not found: {e}")
        print("   Run: python train_model.py")
    return models


def build_user_profile_text(skills, experience, education, domain,
                             location="", goals="", resume_text=""):
    """
    Converts user inputs into a single text string for TF-IDF vectorization.
    This mirrors how job features are combined during training.
    """
    parts = []
    if skills:
        # Repeat skills 3x to increase their weight in the vector
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
        # Truncate resume to first 1000 chars (most relevant part)
        parts.append(resume_text[:1000])
    return " ".join(parts).lower()


def get_recommendations(models, user_profile_text, top_n=20,
                         filter_location=None, filter_experience=None,
                         filter_category=None, min_salary=None):
    """
    MAIN RECOMMENDATION FUNCTION
    
    Algorithm:
    1. Transform user profile text using trained TF-IDF vectorizer
    2. Compute cosine similarity between user vector and all job vectors
    3. Rank jobs by similarity score (= match percentage)
    4. Apply optional filters (location, experience, category)
    5. Return top_n recommendations with match details

    Parameters:
        models            : dict of loaded ML models
        user_profile_text : combined user skills/goals string
        top_n             : number of jobs to return
        filter_location   : filter by city name (optional)
        filter_experience : filter by exp level (optional)
        filter_category   : filter by job category (optional)
        min_salary        : minimum salary in LPA (optional)

    Returns:
        list of dicts, each representing a recommended job
    """
    if not user_profile_text.strip():
        return []

    tfidf       = models["tfidf"]
    job_matrix  = models["tfidf_matrix"]
    jobs_df     = models["jobs_df"].copy()
    rf          = models["rf"]
    le          = models["le"]

    # ── Step A: Vectorize user profile ────────────────────────────────────────
    user_vector = tfidf.transform([user_profile_text])

    # ── Step B: Compute cosine similarity ─────────────────────────────────────
    # Shape: (1, n_jobs) — one similarity score per job
    similarities = cosine_similarity(user_vector, job_matrix).flatten()
    jobs_df["raw_similarity"] = similarities

    # ── Step C: Predict best category using Random Forest ─────────────────────
    try:
        pred_encoded = rf.predict(user_vector)[0]
        pred_proba   = rf.predict_proba(user_vector)[0]
        predicted_category = le.inverse_transform([pred_encoded])[0]
        category_confidence = float(pred_proba.max())

        # Boost jobs matching predicted category by 15%
        mask = jobs_df["category"] == predicted_category
        jobs_df.loc[mask, "raw_similarity"] *= 1.15
    except Exception:
        predicted_category  = None
        category_confidence = 0.0

    # ── Step D: Apply Filters ─────────────────────────────────────────────────
    if filter_location and filter_location.lower() not in ("any", ""):
        loc_mask = jobs_df["location"].str.lower().str.contains(
            filter_location.lower(), na=False
        ) | jobs_df["location"].str.lower().str.contains("remote", na=False)
        jobs_df = jobs_df[loc_mask]

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

    # ── Step E: Sort and select top N ─────────────────────────────────────────
    jobs_df = jobs_df.sort_values("raw_similarity", ascending=False).head(top_n)

    # ── Step F: Build result dicts ────────────────────────────────────────────
    recommendations = []
    user_skills_set = set(
        s.strip().lower()
        for s in user_profile_text.replace(",", " ").split()
        if len(s) > 2
    )

    for _, row in jobs_df.iterrows():
        raw_score = float(row["raw_similarity"])
        # Scale to realistic 30-98% match range
        match_pct = min(98, max(30, int(raw_score * 120 + 30)))

        # ── Skill gap analysis ────────────────────────────────────────────────
        job_skills_list  = [s.strip() for s in str(row["skills_required"]).split(",")]
        matched_skills   = []
        missing_skills   = []

        for skill in job_skills_list:
            skill_words = set(skill.lower().split())
            if skill_words & user_skills_set:
                matched_skills.append(skill.strip())
            else:
                missing_skills.append(skill.strip())

        # ── Why recommended explanation ───────────────────────────────────────
        if matched_skills:
            why = f"You have {len(matched_skills)} of {len(job_skills_list)} required skills: {', '.join(matched_skills[:3])}"
            if len(matched_skills) > 3:
                why += f" and {len(matched_skills)-3} more."
        else:
            why = f"This role aligns with your {predicted_category or 'target'} domain interest."

        recommendations.append({
            "job_id"           : int(row["job_id"]),
            "title"            : row["title"],
            "company"          : row["company"],
            "location"         : row["location"],
            "category"         : row["category"],
            "experience"       : row["experience_required"],
            "salary_range"     : row["salary_range"],
            "salary_lpa"       : round(float(row["salary_lpa"]), 1),
            "job_type"         : row["job_type"],
            "description"      : row["description"],
            "skills_required"  : row["skills_required"],
            "matched_skills"   : matched_skills,
            "missing_skills"   : missing_skills[:5],
            "match_pct"        : match_pct,
            "why_recommended"  : why,
            "is_top_pick"      : match_pct >= 70,
            "openings"         : int(row.get("openings", 1)),
        })

    return recommendations


def predict_category(models, text):
    """
    Predict the most likely job category for a given text profile.
    Used on the dashboard to show 'Best fit category'.
    """
    try:
        tfidf = models["tfidf"]
        rf    = models["rf"]
        le    = models["le"]
        vec   = tfidf.transform([text])
        pred  = rf.predict(vec)[0]
        proba = rf.predict_proba(vec)[0].max()
        return le.inverse_transform([pred])[0], round(proba * 100, 1)
    except Exception:
        return "Unknown", 0.0


def get_category_stats(models):
    """Return job counts per category for admin analytics charts."""
    jobs_df = models["jobs_df"]
    return jobs_df["category"].value_counts().to_dict()


def get_location_stats(models):
    """Return job counts per location for analytics charts."""
    jobs_df = models["jobs_df"]
    return jobs_df["location"].value_counts().head(10).to_dict()


def get_experience_stats(models):
    """Return job counts per experience level."""
    jobs_df = models["jobs_df"]
    return jobs_df["experience_required"].value_counts().to_dict()
