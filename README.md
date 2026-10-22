# ⚡ CareerAI — ML-Based Job Recommendation System

> Machine Learning job recommender with skill-gap analysis and **blockchain-verified credentials**  
> Built with Python · Flask · Scikit-learn · TF-IDF · Random Forest · Solidity · web3.py

---

## ✨ What's in this version

| Area | Feature |
|------|---------|
| **Matching** | Hybrid score = skill coverage + TF-IDF text similarity + RF category fit (+ optional semantic embeddings) |
| **Skills** | Skill normalisation (`JS`→`javascript`, `ML`→`machine learning`) and extraction from resume text; exact skill-gap matching |
| **Jobs** | Admin-added / CSV-uploaded jobs now actually appear in recommendations and search |
| **Live jobs** | Real listings pulled from Adzuna (free key) and Remotive (no key) into the same pipeline, with attribution and an external apply link |
| **Collaborative filtering** | "Users like you also saved/applied" — item-based CF on saves and applications, with an explanation on each card |
| **Blockchain** | Credential issuing & verification, tamper-proof application records (Solidity contract, hashes only on-chain) |
| **Security** | Salted password hashes, CSRF protection, login throttling, no hard-coded secrets, safe resume upload |
| **Accounts** | Account settings (name, password), download-my-data, delete account, forgot/reset password by email (one-time, 1-hour links) |
| **Applications** | Real tracker (Applied → Shortlisted → Interview → Offer / Rejected / Withdrawn) with notes; recruiters manage applicants and candidates are notified |
| **Discovery** | Search with 5 filters, sorting and pagination; sortable, paginated recommendations; a per-job "Your match" panel with course links for missing skills |
| **Profile help** | Profile-strength meter and skills suggested from your resume |
| **Professional shell** | Mobile menu, About / Privacy / Terms / FAQ pages, footer, favicon + SEO tags, friendly error pages, security headers, robots.txt and sitemap |
| **Quality** | Recommendation-level evaluation scripts, 141 automated tests, auto-training on first start |

---

## 📁 Project Structure

```
job_recommender/
├── app.py                     ← Flask app: routes, auth, CSRF, credentials, admin
├── model.py                   ← Hybrid recommendation engine + live job pool
├── skills.py                  ← Skill normalisation & extraction from free text
├── embeddings.py              ← OPTIONAL sentence-transformer embeddings
├── blockchain.py              ← web3 client for the smart contract (local / remote)
├── collab.py                  ← Collaborative filtering (item-based, implicit feedback)
├── live_jobs.py               ← Live job sync: normalise, enrich, store, expire
├── job_sources/               ← Provider adapters: adzuna.py, remotive.py (add your own)
├── sync_jobs.py               ← CLI for scheduled live-job syncs (cron)
├── seed_demo.py               ← Demo users with saves/applies to show collaborative filtering
├── evaluate_cf.py             ← Collaborative-filtering sanity evaluation
├── train_model.py             ← Trains TF-IDF + Random Forest (also auto-run if missing)
├── evaluate.py                ← Recommendation metrics on simulated profiles
├── generate_dataset.py        ← Dataset generator
├── database.sql               ← Schema reference
├── requirements.txt           ← Core dependencies
├── requirements-ml.txt        ← Optional: embeddings (PyTorch, large)
├── requirements-dev.txt       ← Adds pytest
├── .env.example               ← All configuration variables
│
├── contracts/
│   ├── CredentialRegistry.sol ← Smart contract (source)
│   └── CredentialRegistry.json← Compiled ABI + bytecode
├── scripts/compile_contract.js← Recompile the contract (needs `npm i solc@0.8.24`)
├── tests/                     ← pytest suite (ML, contract, app flows)
├── data/jobs.csv              ← 101 job records
├── ml_models/                 ← Generated automatically (git-ignored)
├── templates/                 ← HTML (new: credentials, verify, admin_credentials, admin_live_jobs)
└── static/                    ← CSS / JS
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
# optional, for semantic embeddings (large download):
# pip install -r requirements-ml.txt
```

### Step 5 — Configure (optional for local use)
```bash
cp .env.example .env      # then export the variables, or set them in your shell
```
For a quick local run nothing is required: a random secret key is generated and an admin
password is **printed once** in the terminal on first start.

### Step 6 — Run the Application
```bash
python app.py
```
On first start the app trains the ML models and creates the database by itself.
(`python train_model.py` still works if you want to retrain manually.)

### Step 7 — Open in Browser
```
http://127.0.0.1:5000
```

---

### Troubleshooting installation (Windows)
If `pip install` ever asks for **"Microsoft Visual C++ 14.0 or greater"**, some package is trying to compile.
This project's `requirements.txt` avoids that (checked for Python 3.10 on Windows with wheels only).
If you edited it or added packages, install with `pip install --only-binary=:all: -r requirements.txt` to see which one is the problem.

---

## 🔐 Accounts

| Role  | Login | Password |
|-------|-------|----------|
| Admin | `ADMIN_EMAIL` (default `admin@jobrec.com`) | `ADMIN_PASSWORD`, or the random one printed in the terminal on first run |
| User  | Register yourself | minimum 8 characters |

> The old public default `admin123` is **no longer accepted**: an existing database that still
> uses it is rotated on the next start.

---

## ⚙️ Configuration (environment variables)

| Variable | Purpose | Default |
|----------|---------|---------|
| `SECRET_KEY` | Flask session signing | random, saved in `instance/secret_key` |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD` | Admin account | `admin@jobrec.com`, random |
| `COOKIE_SECURE` | `1` when served over HTTPS | `0` |
| `DATABASE_PATH`, `UPLOAD_FOLDER` | Storage locations | `job_recommender.db`, `uploads` |
| `BLOCKCHAIN_MODE` | `local` / `remote` / `off` | `local` |
| `BLOCKCHAIN_RPC_URL`, `ISSUER_PRIVATE_KEY`, `CONTRACT_ADDRESS` | Real-network settings (remote mode) | — |
| `CONTACT_EMAIL` | Shown on the FAQ & contact page | — |
| `PUBLIC_BASE_URL` | Base URL used in password-reset emails (**set in production**) | request host |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_TLS`, `SMTP_SSL` | Outgoing email | — |
| `DEV_SHOW_RESET_LINK` | Development only: show the reset link when SMTP is unset | `0` |
| `USE_EMBEDDINGS` | `auto` / `1` / `0` | `auto` |
| `ADZUNA_APP_ID`, `ADZUNA_APP_KEY`, `ADZUNA_COUNTRY` | Adzuna live jobs (free key; India = `in`) | — , — , `in` |
| `ADZUNA_MAX_CALLS`, `ADZUNA_PAGES` | Quota guard: API calls / pages per sync | `10`, `1` |
| `LIVE_QUERIES` | Comma-separated searches | defaults + your users' top skills |
| `LIVE_JOB_TTL_DAYS`, `LIVE_MAX_JOBS` | Expiry and cap of stored live jobs | `21`, `2000` |

---

## 🤖 How the ML Algorithm Works

### 1. Hybrid scoring (all parts are 0..1)

For every job the final score is a weighted sum:

| Component | Meaning | Weight (no embeddings) | Weight (with embeddings) |
|-----------|---------|-----------------------|--------------------------|
| Skills | fraction of the job's required skills the user has (normalised) | 0.50 | 0.40 |
| Text | TF-IDF cosine similarity of profile vs job text (scaled ×2, capped at 1) | 0.35 | 0.20 |
| Semantic | sentence-embedding cosine similarity | — | 0.30 |
| Category | Random-Forest confidence that the job's category fits the user | 0.15 | 0.10 |

Each **blockchain-verified** skill the job requires adds +0.05 (max +0.15).
Then **collaborative filtering** may lift the score: `final = c + w × cf × (1 − c)` where `c` is the
content score above, `cf` (0..1) is the similar-users signal and `w ≤ 0.30` (see below). Jobs with no
CF signal keep exactly their content score — nobody is penalised.
The match % shown is `round(100 × score)`. The old formula floored every job at 30% and
multiplied by 120, so a job with zero overlap still displayed "30% match".
Each recommendation card shows its breakdown (Skills / Text / Meaning / Category).

### 2. TF-IDF + Cosine Similarity
Job title + skills + description + category are turned into TF-IDF vectors (unigrams and
bigrams, 5000 features). The user profile is vectorised with the same model and compared with
`cos(θ) = (A·B) / (‖A‖ ‖B‖)`.

### 3. Random Forest category classifier
200 trees predict which job category a profile fits; its confidence feeds the Category component.
Reported accuracy is now **3-fold cross-validated** (vectorizer fitted inside each fold):
**95.7% accuracy / 93.2% macro-F1** on the 93 jobs in the 13 categories that have ≥3 jobs (6 rare categories with 1–2 jobs cannot be split and are excluded).
(The previous 95.24% was 20 correct of a single 21-job split.)
This measures *job text → category*; real user profiles are written differently, so rely on the
recommendation-level metrics below.

### 4. Skill normalisation and gap analysis
`skills.py` maps aliases to one canonical name and finds skills in resume/goals text.
A job skill counts as matched only if the **normalised skill** is in the user's skill set.
Before, the check matched on *any single word* (so "machine" matched "Machine Learning").

### 5. Collaborative filtering (`collab.py`)
**Signal:** which jobs users *saved* (weight 1) and *applied to* (weight 2). People who interacted with
job A also tend to interact with job B, so B is suggested to someone who touched A — even if their profile
text never mentions B's skills. Each card then says e.g. *"Because you saved Backend Developer"*.

**Method:** item-based k-nearest-neighbours. Jobs are columns of a users × jobs matrix; similarity is cosine,
damped by co-occurrence support, `sim = cos × n / (n + 2)`, so a link seen by one user is weak and one seen by
five is strong. The 30 strongest neighbours per job are kept. Only user ids and job ids are used.

**Cold start (by design):** the blend weight is `0.30 × min(1, your interactions / 3) × min(1, active users / 5)`.
A new user, or a site with fewer than two active users, gets weight 0 — plain content-based ranking.
CF therefore stays silent until there is data worth using.

**Demo:** `python seed_demo.py` adds 24 generated demo users (`@demo.local`); `--purge` removes them.

### 6. Live job data (`live_jobs.py`, `job_sources/`)
```
Adzuna / Remotive API ──► normalise ──► live_jobs table ──► job pool ──► same ranking as every other job
                          · HTML stripped (untrusted input)
                          · skills extracted (skills.py)
                          · category predicted (Random Forest)
                          · experience / job type / salary inferred
                          · only http(s) apply links kept
```
| | Adzuna | Remotive |
|---|---|---|
| Coverage | many countries incl. India (`ADZUNA_COUNTRY=in`) | remote jobs worldwide |
| Key | free key required | none |
| Etiquette enforced by the app | quota guard `ADZUNA_MAX_CALLS`, ≥1 h gap | ≥6 h gap (they ask for ≤4 fetches/day) |
| Attribution | "Jobs by Adzuna" footer shown | "Remote jobs from Remotive" + link back to their listing |

**Run it:** admin → *Live Jobs* → *Fetch live jobs*, or schedule `python sync_jobs.py` (e.g. cron every 6 h).
Expired listings (default 21 days) are removed unless a user saved or applied to them; Remotive jobs that
disappear from its feed are removed at the next sync. The similarity vectorizer is re-fitted on the whole
pool, because live ads use vocabulary the 101-job training set never saw. Live jobs get an
**"Apply on <source> ↗"** button that opens the original ad.

**Please read each provider's terms before deploying** (rate limits, attribution, no re-publishing). Adding a
source = one class in `job_sources/` implementing `fetch()`, registered in `job_sources/__init__.py`.

### 7. Optional semantic embeddings
With `sentence-transformers` installed, profile and jobs are also compared as meaning vectors
(model `all-MiniLM-L6-v2`), which relates e.g. "backend developer" to "server-side engineer".
Without it the app silently uses the other components. Job embeddings are cached in `ml_models/`.

---

## 📈 Evaluation

`python evaluate.py` builds 404 **simulated** users (60–80% of a job's skills plus 1–2 unrelated
skills, domain left as "Any"). A result is *relevant* if it is in the same category as the job the
profile was built from.

| Method | P@5 | Hit@1 | MRR | nDCG@10 |
|--------|-----|-------|-----|---------|
| TF-IDF only | 0.450 | 0.834 | 0.906 | 0.566 |
| Legacy (original algorithm) | 0.463 | 0.814 | 0.897 | 0.586 |
| **Hybrid (this version)** | **0.519** | **0.975** | **0.987** | **0.652** |

**How to read this honestly:** the profiles are generated from the same dataset, so absolute numbers
are optimistic and the hybrid method benefits from matching on skills (as designed). P@5 is
capped because many categories contain fewer than five jobs. The comparison *between methods* is
the meaningful part; real-user evaluation (click / apply data) is future work.
The embeddings component is **not** included in these numbers.

### Collaborative filtering (`python evaluate_cf.py`)
300 simulated users per run (5 runs), each preferring two job categories; one interaction per user is hidden
and the question is whether the method ranks it in the top 10.

| Method | HitRate@10 | nDCG@10 |
|--------|-----------|---------|
| Random | 0.113 | 0.053 |
| Popularity | 0.156 | 0.071 |
| **Item-KNN (`collab.py`)** | **0.655** | **0.363** |

**Read this carefully:** the users come from a taste-cluster generator, so collaborative filtering is
*expected* to win. This shows the implementation recovers hidden structure and beats the popularity baseline;
it does **not** show how much it will help real users. Re-run on real saves and applies once you have them.

---

## ⛓️ Blockchain: Verified Credentials & Application Proofs

**Why:** anyone can claim a skill on a profile. An authorised issuer (institute, employer) can
instead issue a credential whose hash is stored on a blockchain; recruiters verify it without
contacting the issuer, and verified skills rank higher.

**What goes on-chain:** only 32-byte hashes. Names, documents and skills stay in the database.
Each hash is `sha256(canonical JSON of the record + a random 128-bit salt)`, so it cannot be
guessed from the record.

```
Admin (issuer) ──issue──► CredentialRegistry.sol ◄──verify── anyone (/verify/<hash>)
      │ stores salt + details off-chain (SQLite)                │
      └── user's verified skills ──► recommender (+score bonus)
Apply to a job ──► hash(application) anchored on-chain ──► "Recorded · block N" proof
```

**Smart contract** (`contracts/CredentialRegistry.sol`): `issue`, `revoke` (only the issuing account),
`verify`, `anchorApplication` (one-time), issuer allow-list managed by the owner. Duplicate hashes
and unauthorised callers are rejected by the contract (covered by tests).

**Pages:** `/credentials` (my credentials, live status) · `/verify` and `/verify/<hash>` (public) ·
`/admin/credentials` (issue / revoke).
The verify page also re-hashes the stored record: if someone edits the database after issuing, it
shows "stored details were altered".

### Modes
| Mode | Use | Notes |
|------|-----|-------|
| `local` (default) | development / demo | In-memory simulated chain, no setup. It resets on restart; the app replays stored hashes into it. **Not real immutability.** Run with one worker (the Procfile does). |
| `remote` | real network, e.g. Sepolia testnet | Set `BLOCKCHAIN_RPC_URL`, `ISSUER_PRIVATE_KEY` (a throw-away **testnet** key), leave `CONTRACT_ADDRESS` empty for the first run to deploy, then paste the printed address. |
| `off` | disable | The rest of the app is unaffected. |

### Recompile the contract (only if you edit the .sol file)
```bash
npm install solc@0.8.24 && node scripts/compile_contract.js
```

### Privacy
On-chain data cannot be deleted. Because only salted hashes are stored, deleting a user (which
deletes their salt and details from the database) leaves an unlinkable hash behind.
Anyone holding a user's verification link can see the credential's title, issuer and skills.

---

## 🔒 Security changes
- Passwords: salted scrypt (werkzeug) instead of unsalted SHA-256; old hashes are upgraded at next login
- CSRF token on every POST form and `fetch()` call; HttpOnly + SameSite cookies
- No hard-coded secret key or default admin password; login throttling (5 failures / 10 min)
- `apply_job` takes title/company from the server, not from the browser
- Resume files get unique names and are deleted on replacement / account deletion
- Admin users cannot be deleted through the admin screen
- **Inline-JS injection fixed:** job titles used to be pasted into `onclick="applyJob(…)"` handlers (a title ending in a backslash could break out). Live API data is untrusted, so the handlers now pass only the numeric id
- `save_job` validates that the job exists, which also stops junk ids from polluting collaborative filtering
- External data is treated as hostile: HTML stripped, `javascript:` links dropped, response size capped, timeouts, bounded retries

## 🧩 Site features

**Accounts** — click your name in the menu → *Account*: change your name, change your password (current password
required), download everything we hold as JSON, or delete your account (password + typing DELETE). Administrator
accounts can't be deleted from the UI.

**Forgot password** — *Sign in → Forgot password?* sends a link that works once and expires after 1 hour. It also dies
if the password changes. The reply is identical whether or not the email exists (no account enumeration) and requests are
rate-limited. Configure `SMTP_*` to send real email. **Set `PUBLIC_BASE_URL` in production** so links can't be built from
a spoofed `Host` header. Without SMTP the link is written to the server log; `DEV_SHOW_RESET_LINK=1` shows it on screen
for local development only.

**Application tracker** — every application can be moved through *Applied · Shortlisted · Interview · Offer · Rejected ·
Withdrawn*, with private notes. Admins (acting as recruiters) open **Applicants**: each row shows the candidate's match %
for that job, their credentials with verification links, the blockchain proof, and a status control; changes are emailed
nowhere but appear as a red badge on the candidate's *Applied* menu item. CSV export is protected against spreadsheet
formula injection.

**Search & recommendations** — search treats every word as required across title, skills, category, company, city and
description (title matches rank first) and filters by category, location, experience, type and minimum salary, sorted by
best match / newest / salary. Recommendations are paginated (10 per page) and sortable. Each job page shows *Your match*:
the skills you have, the ones to learn (with a link to find a course), and which are verified on-chain.

**Profile** — a strength meter explains what is missing; after uploading a resume the profile page lists skills found in
it so you can add them with one click.

**Site shell** — responsive menu, About / FAQ & contact / Privacy / Terms (plain-language templates: have them reviewed
before real use), favicon and meta tags, friendly 400/403/404/405/413/429/500 pages (JSON for `/api/…`), security headers
(`nosniff`, frame denial, referrer policy, HSTS when `COOKIE_SECURE=1`, `no-store` for signed-in pages),
`/robots.txt` and `/sitemap.xml`.

## 🎨 Glassmorphism theme
The whole site uses a frosted-glass design: a vivid gradient backdrop with slowly drifting colour orbs, and
translucent panels (blur + bright edge + soft shadow). It lives in **one file**, `static/css/glass.css`, loaded
after `style.css`; remove its `<link>` in `templates/base.html` to return to the original look.
- Browsers without `backdrop-filter` automatically get near-opaque panels, so text stays readable.
- Users with *reduce motion* / *reduce transparency* enabled get a static, solid version.
- On phones the blur is lighter and the orbs are static, to keep it smooth.
- Colours and strength are variables at the top of the file (`--glass-bg`, `--blur`, `--accent`, …).

## 🧭 Location filter and search behaviour
- **Preferred Location** (profile) is the default location filter on *Recommendations*: only jobs in that
  place are shown (several places can be separated by commas). Change it any time with the *Location* box on
  the page (free text, with suggestions); an empty box means *Any location*.
- **Remote jobs** are shown only when *Include remote jobs* is ticked (they used to be mixed in silently, which
  made other cities appear).
- If nothing matches, a pop-up explains why and offers *Show all locations* / *Include remote jobs*.
  The sample dataset has no Indore or Bhopal jobs — add some in the admin panel or sync live jobs for your city.
- **Search** covers title, company, skills, category and city, treats the query as plain text (a search such as
  `c++` used to crash), and shows a "No jobs found" pop-up when nothing matches.

## 🧪 Tests
```bash
pip install -r requirements-dev.txt
python -m pytest -q          # 141 tests: ML logic, collaborative filtering, live-data adapters (incl. a real local HTTP server), contract rules, security, full flows
```

## ⚠️ Known limitations
- Dataset is synthetic (101 jobs); evaluation uses simulated users, not real behaviour.
- Embeddings need PyTorch (~800 MB); too large for small free hosting tiers, so they are optional.
  The embedding code path is covered by a stub-encoder test only; the real model was not run in the build environment.
- `remote` mode was tested against a local Ganache node, **not** on a live public network.
- **Live data was not tested against the real Adzuna / Remotive servers** (no internet in the build environment). Adapters follow their published documentation and are tested against fixtures and a local HTTP server; check the first real sync from the admin page. Remotive's API behaviour has been reported inconsistent (its filters may be ignored, feed size varies), so filtering is done on our side.
- Live jobs only get skills our vocabulary knows (213 skills from the dataset), so niche roles may show few skills; experience level and category are heuristics.
- Collaborative filtering needs real users: with few users it stays quiet by design. It can be gamed by fake accounts (shilling) — rate limiting and email verification are future work.
- Applications are tracked inside CareerAI; there is no employer self-service portal — the administrator plays the recruiter. Status changes are not emailed to candidates (only shown in the app).
- The privacy policy and terms are templates, not legal advice.
- SQLite on hosts with ephemeral disks (e.g. Heroku) loses data on restart; use a persistent disk or PostgreSQL.
- Rate limiting is per worker and in memory.

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

**Q16. Why use a blockchain here at all?**  
A: To make credentials and application records tamper-evident and independently verifiable. The issuer anchors a hash once; anyone can later check that the credential exists, who issued it and whether it was revoked, without trusting our database.

**Q17. What exactly is stored on the blockchain?**  
A: Only 32-byte SHA-256 hashes (plus timestamp and issuer address). Personal data stays in the database, which keeps the system privacy-friendly because on-chain data cannot be deleted.

**Q18. Why is a random salt added before hashing?**  
A: Without a salt, anyone could guess a credential's fields (name, title, skills) and compare hashes. A 128-bit random salt makes brute-forcing infeasible.

**Q19. What happens if someone edits the database after issuing a credential?**  
A: The stored fields no longer hash to the on-chain value; the verify page recomputes the hash and reports the record as altered.

**Q20. How do verified credentials affect recommendations?**  
A: Skills backed by a non-revoked on-chain credential give a small score bonus (+0.05 per matching required skill, max +0.15) and are shown with a "verified" badge. Revoking the credential removes the bonus.

**Q21. What is the difference between `local` and `remote` blockchain mode?**  
A: Local is a simulated in-memory chain for development; it resets on restart. Remote connects to a real EVM network (e.g. Sepolia testnet) through an RPC URL and signs transactions with the issuer's private key.

**Q22. Why does the match percentage no longer start at 30%?**  
A: The old formula added a fixed 30-point floor, so unrelated jobs looked like decent matches. The new percentage is simply 100 × the hybrid score.

**Q23. What is collaborative filtering and how is it different from your content-based part?**  
A: Content-based ranking compares a user's profile with a job's text and skills. Collaborative filtering ignores the text and uses behaviour: jobs that many of the same users saved or applied to are considered related. It can recommend a job whose description shares no words with the profile.

**Q24. Which collaborative-filtering method did you use and why?**  
A: Item-based k-nearest-neighbours with cosine similarity on implicit feedback (save = 1, apply = 2). It suits small data, is easy to explain ("because you saved X") and needs no training loop.

**Q25. What is the cold-start problem and how do you handle it?**  
A: New users and new jobs have no interactions. The CF weight scales with the user's activity and the number of active users and is 0 when there is no data, so the system falls back to content-based ranking.

**Q26. Where does the live job data come from and how is it kept safe?**  
A: From the Adzuna and Remotive APIs. Responses are treated as untrusted: HTML is stripped, only http(s) links are kept, sizes and timeouts are limited, and syncs respect each provider's rate limits and attribution rules.

**Q27. How do live jobs enter the recommendation pipeline?**  
A: They are converted to the dataset schema: skills are extracted from the text, the Random Forest predicts a category, and experience, job type and salary are inferred. They then go through exactly the same scoring as every other job.

**Q28. Why do you re-fit the TF-IDF vectorizer when live jobs are added?**  
A: The original vectorizer only knows the vocabulary of the 101 training jobs, so most words in real ads would be ignored. Re-fitting on the whole pool lets similarity use the new vocabulary; the Random Forest keeps its original vectorizer because it was trained with it.

---

## 📊 Project Report

### Title
ML-Based Job Recommendation System with Hybrid Matching and Blockchain-Verified Credentials

### Abstract
This project implements a job recommendation system that ranks jobs with a hybrid of skill matching, TF-IDF text similarity and a Random Forest category model (optionally enhanced with sentence embeddings). It provides match percentages with a transparent score breakdown, normalised skill-gap analysis and resume skill extraction. A Solidity smart contract lets authorised issuers anchor credential hashes on a blockchain so that verified skills can be trusted and ranked higher, and records job applications as tamper-evident proofs. On simulated profiles the hybrid method improves nDCG@10 from 0.586 (original algorithm) to 0.652.

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
- **ML/DS**: Scikit-learn, Pandas, NumPy, SciPy, Matplotlib (optional: sentence-transformers)
- **Blockchain**: Solidity 0.8.24, web3.py, eth-tester (local chain), any EVM network (e.g. Sepolia)
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
- Random Forest (3-fold CV, job text → category): 95.7% accuracy, 93.2% macro-F1
- Recommendation quality on 404 simulated profiles (original → hybrid): P@5 0.463 → 0.519, Hit@1 0.814 → 0.975, MRR 0.897 → 0.987, nDCG@10 0.586 → 0.652
- Collaborative filtering on simulated users: HitRate@10 0.655 vs 0.156 for popularity (validates the implementation, not real-world gain)
- 141 automated tests pass (ML logic, collaborative filtering, live-data adapters, smart-contract rules, security, end-to-end flows)

### Future Scope
1. **Matrix factorisation** (ALS / SVD) on real interactions, to complement the item-based collaborative filter
2. **More live sources and scheduled sync** (the adapter interface makes this a small addition)
3. **Evaluation with real users**: click / apply logs, A/B testing, tuning the collaborative-filtering weight
4. **Public-network deployment**: Sepolia/Polygon testnet, issuer wallets per institute, optional IPFS for documents
5. **Salary prediction**, **email alerts**, **mobile app**

### Conclusion
The system successfully demonstrates how ML techniques can solve the job recommendation problem. By combining TF-IDF text representation with Cosine Similarity and Random Forest classification, we achieve accurate, explainable, and fast recommendations that are personalized to each user's unique profile.

---

## 🔧 Run Commands Summary

```bash
pip install -r requirements.txt     # 1. install
python app.py                       # 2. run (auto-trains models + creates DB on first start)
# http://127.0.0.1:5000             # 3. open
python evaluate.py                  # optional: recommendation metrics
python -m pytest -q                 # optional: run the tests
```
