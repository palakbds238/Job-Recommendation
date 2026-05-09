"""
train_model.py
--------------
Trains all ML models used by the Job Recommendation System.

Models trained:
1. TF-IDF Vectorizer  → converts skill text to numeric vectors
2. Cosine Similarity  → content-based job matching
3. Random Forest      → job category prediction classifier

Run this script ONCE before starting the Flask app:
    python train_model.py
"""

import pandas as pd
import numpy as np
import pickle
import os
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score
from sklearn.metrics.pairwise import cosine_similarity

# ── Paths ──────────────────────────────────────────────────────────────────────
DATA_PATH   = "data/jobs.csv"
MODEL_DIR   = "ml_models"
os.makedirs(MODEL_DIR, exist_ok=True)

print("=" * 60)
print("  ML-Based Job Recommendation System — Model Trainer")
print("=" * 60)

# ── Step 1: Load Dataset ───────────────────────────────────────────────────────
print("\n[1/6] Loading dataset...")
df = pd.read_csv(DATA_PATH)
print(f"      Loaded {len(df)} jobs from {DATA_PATH}")

# ── Step 2: Feature Engineering ───────────────────────────────────────────────
print("\n[2/6] Engineering features...")

def clean_text(text):
    """Lowercase and strip extra whitespace."""
    if pd.isna(text):
        return ""
    return str(text).lower().strip()

# Combine all textual features into one rich feature string
df["combined_features"] = (
    df["title"].apply(clean_text) + " " +
    df["skills_required"].apply(clean_text) + " " +
    df["description"].apply(clean_text) + " " +
    df["category"].apply(clean_text) + " " +
    df["experience_required"].apply(clean_text)
)

print(f"      Combined feature column created. Sample:")
print(f"      '{df['combined_features'].iloc[0][:80]}...'")

# ── Step 3: TF-IDF Vectorizer ─────────────────────────────────────────────────
print("\n[3/6] Training TF-IDF Vectorizer...")
"""
TF-IDF (Term Frequency-Inverse Document Frequency):
- TF  = how often a word appears in a document
- IDF = how rare that word is across all documents
- High TF-IDF = important word for that specific document
This converts text like "Python, Machine Learning, SQL" into
a numeric vector that can be compared mathematically.
"""
tfidf = TfidfVectorizer(
    ngram_range=(1, 2),   # Use single words AND two-word phrases
    stop_words="english", # Remove common words (the, is, at...)
    max_features=5000,    # Use top 5000 most important terms
    sublinear_tf=True,    # Smooth TF scores (log scale)
)
tfidf_matrix = tfidf.fit_transform(df["combined_features"])
print(f"      TF-IDF matrix shape: {tfidf_matrix.shape}")
print(f"      (rows=jobs, cols=unique terms)")

# Save vectorizer and matrix
with open(f"{MODEL_DIR}/tfidf_vectorizer.pkl", "wb") as f:
    pickle.dump(tfidf, f)
with open(f"{MODEL_DIR}/tfidf_matrix.pkl", "wb") as f:
    pickle.dump(tfidf_matrix, f)
print(f"      ✅ TF-IDF model saved")

# ── Step 4: Cosine Similarity ─────────────────────────────────────────────────
print("\n[4/6] Computing Cosine Similarity matrix...")
"""
Cosine Similarity:
- Measures the angle between two vectors
- 1.0 = identical direction (perfect match)
- 0.0 = perpendicular (no match)
- For recommending jobs, we compute: 
  cos_sim(user_profile_vector, each_job_vector)
  and return the top N jobs with highest scores.
"""
# We save the job TF-IDF matrix; at runtime we compute
# cosine_similarity(user_vec, job_matrix) dynamically
print(f"      Cosine similarity will be computed at query time")
print(f"      (avoids storing O(n²) matrix; faster for new users)")

# ── Step 5: Random Forest Classifier ─────────────────────────────────────────
print("\n[5/6] Training Random Forest Classifier...")
"""
Random Forest:
- Ensemble of decision trees (100 trees by default)
- Each tree votes on the job category
- Final prediction = majority vote
- Used to PREDICT what job category best fits a user's profile
"""

# Encode target (job category) as integers
le = LabelEncoder()
df["category_encoded"] = le.fit_transform(df["category"])

X = tfidf_matrix                        # Features: TF-IDF of job text
y = df["category_encoded"].values       # Target: job category

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42
)
print(f"      Train: {X_train.shape[0]} | Test: {X_test.shape[0]}")

rf_model = RandomForestClassifier(
    n_estimators=200,      # 200 decision trees
    max_depth=20,          # Prevent overfitting
    random_state=42,
    class_weight="balanced",
    n_jobs=-1              # Use all CPU cores
)
rf_model.fit(X_train, y_train)

# Evaluate
y_pred = rf_model.predict(X_test)
acc = accuracy_score(y_test, y_pred)
print(f"      Accuracy: {acc:.2%}")

classes = le.classes_
print("\n      Classification Report:")
print(classification_report(
    y_test, y_pred,
    target_names=classes[np.unique(np.concatenate([y_test, y_pred]))],
    zero_division=0
))

# Save classifier and label encoder
with open(f"{MODEL_DIR}/rf_classifier.pkl", "wb") as f:
    pickle.dump(rf_model, f)
with open(f"{MODEL_DIR}/label_encoder.pkl", "wb") as f:
    pickle.dump(le, f)
print(f"      ✅ Random Forest model saved (accuracy: {acc:.2%})")

# ── Step 6: Save Preprocessed Dataset ────────────────────────────────────────
print("\n[6/6] Saving preprocessed dataset...")
df.to_csv(f"{MODEL_DIR}/jobs_processed.csv", index=False)
print(f"      ✅ Processed dataset saved")

# ── Summary ───────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("  Training Complete! Files saved in ml_models/")
print("=" * 60)
print("""
  Files generated:
    ml_models/tfidf_vectorizer.pkl   ← Text vectorizer
    ml_models/tfidf_matrix.pkl       ← Job TF-IDF vectors  
    ml_models/rf_classifier.pkl      ← Category predictor
    ml_models/label_encoder.pkl      ← Category name mapper
    ml_models/jobs_processed.csv     ← Cleaned job dataset

  How recommendations work:
    1. User enters skills, experience, domain, goals
    2. Text is vectorized using TF-IDF vectorizer
    3. Cosine similarity computed against all job vectors
    4. Jobs sorted by similarity score (= match %)
    5. RF classifier predicts best category for user
    6. Results combined and returned to frontend
""")
