<<<<<<< HEAD
# ⚡ CareerAI — ML-Based Job Recommendation System

> A complete Machine Learning project for College Submission  
> Built with Python · Flask · Scikit-learn · TF-IDF · Cosine Similarity · Random Forest

---

## 📁 Project Structure

```
job_recommender/
├── app.py                    ← Main Flask application (all routes)
├── model.py                  ← ML recommendation engine
├── train_model.py            ← Model training script (run once)
├── generate_dataset.py       ← Dataset generation script (run once)
├── requirements.txt          ← Python dependencies
├── README.md                 ← This file
│
├── data/
│   └── jobs.csv              ← 100+ job records dataset
│
├── ml_models/                ← Saved trained models (auto-created)
│   ├── tfidf_vectorizer.pkl  ← TF-IDF vectorizer
│   ├── tfidf_matrix.pkl      ← Job TF-IDF matrix
│   ├── rf_classifier.pkl     ← Random Forest classifier
│   ├── label_encoder.pkl     ← Category label encoder
│   └── jobs_processed.csv    ← Preprocessed job data
│
├── uploads/                  ← User uploaded resumes
│
├── templates/
│   ├── base.html             ← Base layout (navbar, footer, flash)
│   ├── home.html             ← Landing page
│   ├── login.html            ← Login page
│   ├── register.html         ← Registration page
│   ├── dashboard.html        ← User dashboard
│   ├── profile.html          ← Profile builder
│   ├── recommendations.html  ← AI job recommendations
│   ├── saved_jobs.html       ← Saved jobs page
│   ├── search.html           ← Job search page
│   ├── admin_dashboard.html  ← Admin analytics dashboard
│   ├── admin_jobs.html       ← Admin job management
│   └── admin_users.html      ← Admin user management
│
└── static/
    ├── css/style.css         ← Complete UI stylesheet
    └── js/main.js            ← Frontend JavaScript
```

---

## ⚙️ Setup Instructions (VS Code)

### Step 1 — Prerequisites
Make sure you have **Python 3.9+** installed.  
Download from: https://www.python.org/downloads/

### Step 2 — Open Project in VS Code
```bash
# Open the folder
File → Open Folder → select job_recommender/
```

### Step 3 — Create Virtual Environment
```bash
# In VS Code terminal (Ctrl + `)
python -m venv venv

# Activate (Windows)
venv\Scripts\activate

# Activate (Mac/Linux)
source venv/bin/activate
```

### Step 4 — Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 5 — Generate Dataset
```bash
python generate_dataset.py
```
This creates `data/jobs.csv` with 100+ job records.

### Step 6 — Train ML Models
```bash
python train_model.py
```
This trains TF-IDF + Random Forest and saves models to `ml_models/`.  
**Expected output:** `Accuracy: 95.24%`

### Step 7 — Run the Application
```bash
python app.py
```

### Step 8 — Open in Browser
```
http://127.0.0.1:5000
```

---

## 🔐 Default Accounts

| Role  | Email             | Password |
|-------|-------------------|----------|
| Admin | admin@jobrec.com  | admin123 |
| User  | Register yourself | Any      |

---

## 🤖 How the ML Algorithm Works

### 1. Content-Based Filtering (TF-IDF + Cosine Similarity)

**TF-IDF (Term Frequency–Inverse Document Frequency)**
- Every job's title + skills + description + category is combined into one text string
- This text is converted to a numeric vector using TF-IDF
- TF = how often a word appears in one job
- IDF = how rare that word is across all jobs
- Words like "Python" in a "Python Developer" role get high TF-IDF scores
- Common words like "the", "and" are filtered out (stopwords)

**Cosine Similarity**
- Your profile (skills, experience, goals) is also vectorized using the same TF-IDF model
- Cosine similarity measures the angle between two vectors:
  - Score = 1.0 → perfect match (same direction)
  - Score = 0.0 → no match (perpendicular)
- All 100+ jobs are ranked by cosine similarity to your profile
- Top N jobs are returned as recommendations

**Formula:**
```
cos(θ) = (A · B) / (||A|| × ||B||)
```
Where A = user vector, B = job vector

### 2. Random Forest Classifier

- Trained on job descriptions → predicts job category
- 200 decision trees vote on the category
- Category with most votes wins (majority voting)
- 95.24% accuracy on test data
- Jobs matching predicted category get a 15% score boost

### 3. Skill Gap Analysis

- User's skills are extracted and compared to each job's required skills
- Matched skills shown in green (✓)
- Missing skills shown in red (+)
- "Why Recommended" explanation generated automatically

---

## 🎓 Viva Questions & Answers

**Q1. What is the main ML algorithm used?**  
A: We use Content-Based Filtering with TF-IDF Vectorization and Cosine Similarity as the primary algorithm. A Random Forest Classifier is used to predict the best job category.

**Q2. What is TF-IDF?**  
A: TF-IDF stands for Term Frequency–Inverse Document Frequency. TF measures how often a word appears in a document. IDF measures how rare that word is across all documents. TF × IDF gives the importance of a word — common words get low scores, rare but relevant words get high scores.

**Q3. What is Cosine Similarity?**  
A: Cosine Similarity measures the angle between two vectors in high-dimensional space. If the cosine of the angle is 1.0, vectors are identical (perfect match). If 0.0, they're completely different. We use it to compare the user's profile vector with each job vector.

**Q4. What is a Random Forest?**  
A: Random Forest is an ensemble machine learning algorithm that builds multiple decision trees and aggregates their predictions. Each tree is trained on a random subset of data and features. Final prediction is the majority vote across all trees. It's robust to overfitting and achieves high accuracy.

**Q5. What is Content-Based Filtering?**  
A: Content-Based Filtering recommends items similar to what a user has shown interest in, based on item features. In our system, we recommend jobs with features (skills, description, category) similar to the user's profile features, without needing other users' data.

**Q6. What is Collaborative Filtering?**  
A: Collaborative Filtering recommends items based on what similar users liked. Unlike content-based filtering, it uses user behavior (saves, applies) to find users with similar tastes and recommend what they liked. Our system uses save/apply data to support this.

**Q7. What is the difference between classification and recommendation?**  
A: Classification assigns a label to input data (e.g., predicting job category = Data Science). Recommendation ranks items by relevance score for a specific user. We use both: classification to predict best category, recommendation to rank all jobs by match score.

**Q8. How is match percentage calculated?**  
A: Raw cosine similarity (0 to 1) is scaled to a human-friendly 30–98% range using: `match_pct = min(98, max(30, int(similarity × 120 + 30)))`. Jobs in the predicted category receive a 15% boost before scaling.

**Q9. What is Flask?**  
A: Flask is a lightweight Python web framework. It handles HTTP requests/responses, URL routing, session management, and template rendering using Jinja2. We use it to build the backend REST API and serve HTML pages.

**Q10. What is SQLite?**  
A: SQLite is a lightweight, file-based relational database that stores data in a single `.db` file. We use it to store users, profiles, saved jobs, and applied jobs. No separate database server is required.

**Q11. Why use TF-IDF instead of simple word count (Bag of Words)?**  
A: Simple word count gives equal importance to all words. "the" would score high just because it's common. TF-IDF solves this — it downweights common words across all documents (high IDF denominator) and highlights domain-specific terms that are unique to a job.

**Q12. What accuracy did your model achieve?**  
A: Our Random Forest classifier achieved 95.24% accuracy on the test set, classifying jobs into 19 categories. The TF-IDF + Cosine Similarity recommendation model consistently produces relevant results validated manually.

**Q13. How do you handle the cold start problem?**  
A: New users with no history can still get recommendations because we use content-based filtering (profile → skills → TF-IDF), which doesn't require prior interaction history. Only collaborative filtering suffers from cold start, which is why content-based is our primary method.

**Q14. What are the limitations of your system?**  
A: (1) Dataset is static; real-world systems scrape live job boards. (2) Cosine similarity doesn't capture semantic meaning — "Java" and "JavaScript" may seem unrelated. (3) Small dataset of 100+ jobs; real systems have millions. Future work: use word embeddings (Word2Vec, BERT) for semantic similarity.

**Q15. What is the purpose of ngram_range=(1,2) in TF-IDF?**  
A: It tells TF-IDF to consider both single words (unigrams) and two-word combinations (bigrams). For example, "machine learning" as a bigram is more meaningful than just "machine" and "learning" separately. This improves matching accuracy for compound skill names.

---

## 📊 Project Report

### Title
ML-Based Job Recommendation System using Content-Based Filtering and Random Forest

### Abstract
This project implements a Machine Learning-based Job Recommendation System that matches users with relevant jobs using TF-IDF vectorization, Cosine Similarity, and a Random Forest classifier. The system achieves 95.24% classification accuracy and provides personalized recommendations with match percentages, skill gap analysis, and explanations.

### Problem Statement
Job seekers face information overload on job portals. Finding relevant positions is time-consuming and inefficient. Traditional keyword search fails to capture semantic relevance between a candidate's profile and job requirements.

### Objectives
1. Build a content-based recommendation engine using ML
2. Implement TF-IDF for text vectorization
3. Use Cosine Similarity for user-job matching
4. Train a Random Forest classifier for category prediction
5. Provide a user-friendly web interface with real-time recommendations

### Technology Stack
- **Backend**: Python 3.x, Flask
- **ML/DS**: Scikit-learn, Pandas, NumPy, Matplotlib
- **Database**: SQLite
- **Frontend**: HTML5, CSS3, JavaScript, Chart.js
- **File Handling**: Werkzeug, pdfplumber

### Dataset
- 101 job records across 19 categories
- Fields: title, company, skills_required, description, location, experience, education, salary, job_type
- Generated synthetically using real company names and realistic skill sets

### ML Models
1. **TF-IDF Vectorizer**: max_features=5000, ngram_range=(1,2), sublinear_tf=True
2. **Cosine Similarity**: computed at query time (dynamic, not precomputed)
3. **Random Forest**: 200 trees, max_depth=20, balanced class weights

### Results
- Model Accuracy: 95.24%
- Average recommendation relevance: High (manually validated)
- Response time: <500ms per recommendation query

### Future Scope
1. **BERT/Sentence Transformers**: Replace TF-IDF with semantic embeddings
2. **Collaborative Filtering**: Matrix Factorization (SVD) on user-job interaction data
3. **Real-time Job Scraping**: Integrate with LinkedIn/Naukri APIs
4. **Resume Parsing**: Named Entity Recognition for automatic skill extraction
5. **Salary Prediction**: Regression model to predict fair salary
6. **Mobile App**: React Native or Flutter frontend
7. **Email Alerts**: Notify users when new matching jobs are posted

### Conclusion
The system successfully demonstrates how ML techniques can solve the job recommendation problem. By combining TF-IDF text representation with Cosine Similarity and Random Forest classification, we achieve accurate, explainable, and fast recommendations that are personalized to each user's unique profile.

---

## 🔧 Run Commands Summary

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Generate dataset
python generate_dataset.py

# 3. Train ML models
python train_model.py

# 4. Start the server
python app.py

# 5. Open browser
# http://127.0.0.1:5000
```

---

*Built for college project submission — Computer Science / Data Science Department*
=======
# Job-Recommendation
>>>>>>> bc1bca8369c554a3be9b656cdc65531366ba301b
