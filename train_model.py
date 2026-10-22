"""
train_model.py
--------------
Trains the ML models used by the Job Recommendation System.

  1. TF-IDF vectorizer   -> text -> numeric vectors
  2. Random Forest       -> predicts the best-fit job category for a profile
  3. (optional) job embeddings via sentence-transformers

Run manually:   python train_model.py
The app also calls train() automatically when ml_models/ is missing, so a fresh
clone or fresh deployment starts without any manual step.
"""
import os
import pickle

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import LabelEncoder

DATA_PATH = "data/jobs.csv"
MODEL_DIR = "ml_models"


def _clean(text):
    return "" if pd.isna(text) else str(text).lower().strip()


def _new_tfidf():
    return TfidfVectorizer(ngram_range=(1, 2), stop_words="english",
                           max_features=5000, sublinear_tf=True)


def _new_rf():
    return RandomForestClassifier(n_estimators=200, max_depth=20, random_state=42,
                                  class_weight="balanced", n_jobs=-1)


def cross_validate_classifier(df, folds=3):
    """Honest estimate: the TF-IDF vectorizer is fitted INSIDE each fold (the old
    script fitted it on all jobs before splitting) and categories with fewer than
    `folds` jobs are excluded because they cannot be split."""
    counts = df["category"].value_counts()
    keep = df[df["category"].isin(counts[counts >= folds].index)].reset_index(drop=True)
    skf = StratifiedKFold(n_splits=folds, shuffle=True, random_state=42)
    accs, f1s = [], []
    for tr, te in skf.split(keep, keep["category"]):
        vec = _new_tfidf()
        Xtr = vec.fit_transform(keep.loc[tr, "combined_features"])
        Xte = vec.transform(keep.loc[te, "combined_features"])
        rf = _new_rf().fit(Xtr, keep.loc[tr, "category"])
        pred = rf.predict(Xte)
        accs.append(accuracy_score(keep.loc[te, "category"], pred))
        f1s.append(f1_score(keep.loc[te, "category"], pred, average="macro",
                            zero_division=0))
    return {"accuracy": float(np.mean(accs)), "macro_f1": float(np.mean(f1s)),
            "n_jobs": len(keep), "n_classes": int(keep["category"].nunique()),
            "excluded_classes": int((counts < folds).sum())}


def train(verbose=True):
    log = print if verbose else (lambda *a, **k: None)
    os.makedirs(MODEL_DIR, exist_ok=True)
    log("=" * 60, "\n  Job Recommendation System — Model Trainer\n", "=" * 60)

    log("\n[1/5] Loading dataset...")
    df = pd.read_csv(DATA_PATH)
    log(f"      {len(df)} jobs loaded from {DATA_PATH}")

    log("[2/5] Engineering features...")
    df["combined_features"] = (
        df["title"].apply(_clean) + " " + df["skills_required"].apply(_clean) + " " +
        df["description"].apply(_clean) + " " + df["category"].apply(_clean) + " " +
        df["experience_required"].apply(_clean))

    log("[3/5] Training TF-IDF vectorizer...")
    tfidf = _new_tfidf()
    tfidf_matrix = tfidf.fit_transform(df["combined_features"])
    log(f"      matrix shape: {tfidf_matrix.shape}")

    log("[4/5] Training Random Forest + cross-validation...")
    le = LabelEncoder()
    df["category_encoded"] = le.fit_transform(df["category"])
    rf = _new_rf().fit(tfidf_matrix, df["category_encoded"].values)
    cv = cross_validate_classifier(df)
    log(f"      3-fold CV accuracy : {cv['accuracy']:.1%}  (macro-F1 {cv['macro_f1']:.1%})")
    log(f"      evaluated on {cv['n_jobs']} jobs / {cv['n_classes']} categories "
        f"({cv['excluded_classes']} rare categories excluded)")
    log("      NOTE: this scores job text -> category. Real user profiles are written "
        "differently, so use evaluate.py for recommendation-level metrics.")

    log("[5/5] Saving...")
    for name, obj in (("tfidf_vectorizer", tfidf), ("tfidf_matrix", tfidf_matrix),
                      ("rf_classifier", rf), ("label_encoder", le)):
        with open(f"{MODEL_DIR}/{name}.pkl", "wb") as f:
            pickle.dump(obj, f)
    df.to_csv(f"{MODEL_DIR}/jobs_processed.csv", index=False)
    with open(f"{MODEL_DIR}/cv_metrics.txt", "w") as f:
        f.write(f"cv_accuracy={cv['accuracy']:.4f}\ncv_macro_f1={cv['macro_f1']:.4f}\n")

    try:                                   # optional semantic embeddings
        import embeddings
        if embeddings.available():
            arr = embeddings.encode(df["combined_features"].tolist())
            np.save(f"{MODEL_DIR}/job_embeddings.npy", arr)
            open(f"{MODEL_DIR}/job_embeddings.txt", "w").write(embeddings.model_name())
            log(f"      job embeddings saved {arr.shape} ({embeddings.model_name()})")
        else:
            log("      embeddings not available — skipped (TF-IDF + skills only)")
    except Exception as e:  # noqa: BLE001
        log(f"      embeddings skipped: {e}")
    log("\nTraining complete.")
    return cv


if __name__ == "__main__":
    train()
