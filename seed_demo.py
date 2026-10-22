"""
seed_demo.py — create DEMO users with saved/applied jobs so collaborative filtering
has data to show during a demonstration.

    python seed_demo.py            # add 24 demo users (idempotent)
    python seed_demo.py --purge    # remove them again

Demo users are tagged by an @demo.local e-mail, have an unusable random password and
never appear as real accounts. Interests are generated (each user prefers 1-2 job
categories) — this is SIMULATED behaviour, not real data.
"""
import argparse
import os
import random
import secrets
import sqlite3

import pandas as pd
from werkzeug.security import generate_password_hash


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--purge", action="store_true")
    ap.add_argument("--users", type=int, default=24)
    a = ap.parse_args()
    db = sqlite3.connect(os.environ.get("DATABASE_PATH", "job_recommender.db"))
    ids = [r[0] for r in db.execute("SELECT id FROM users WHERE email LIKE '%@demo.local'")]
    if ids:
        q = ",".join("?" * len(ids))
        for t in ("saved_jobs", "applied_jobs", "user_profiles", "credentials"):
            db.execute(f"DELETE FROM {t} WHERE user_id IN ({q})", ids)
        db.execute(f"DELETE FROM users WHERE id IN ({q})", ids)
        print(f"removed {len(ids)} demo users")
    if a.purge:
        db.commit(); return

    jobs = pd.read_csv("data/jobs.csv")
    info = {int(r.job_id): (r.title, r.company) for r in jobs.itertuples()}   # real titles for the Applied lists
    by_cat = {c: g["job_id"].tolist() for c, g in jobs.groupby("category") if len(g) >= 3}
    cats, rng = sorted(by_cat), random.Random(42)
    for i in range(a.users):
        pref = rng.sample(cats, 2)
        cur = db.execute("INSERT INTO users (name, email, password) VALUES (?,?,?)",
                         (f"Demo User {i + 1}", f"demo{i + 1}@demo.local",
                          generate_password_hash(secrets.token_hex(16))))
        uid = cur.lastrowid
        pool = by_cat[pref[0]] + by_cat[pref[1]]
        for jid in rng.sample(pool, min(len(pool), rng.randint(4, 8))):
            db.execute("INSERT OR IGNORE INTO saved_jobs (user_id, job_id) VALUES (?,?)", (uid, jid))
            if rng.random() < 0.35:
                db.execute("INSERT OR IGNORE INTO applied_jobs (user_id, job_id, job_title, company) "
                           "VALUES (?,?,?,?)", (uid, int(jid), *info[int(jid)]))
    db.commit()
    print(f"added {a.users} demo users (preferences span {len(cats)} categories)")


if __name__ == "__main__":
    main()
