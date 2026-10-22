"""
sync_jobs.py — fetch live jobs from the configured providers (cron / scheduler friendly)

    python sync_jobs.py                       # all configured providers, default queries
    python sync_jobs.py --provider adzuna --queries "python developer, data analyst"
    python sync_jobs.py --location Indore

Environment: ADZUNA_APP_ID, ADZUNA_APP_KEY (see .env.example), DATABASE_PATH.
Run it e.g. every 6 hours:   0 */6 * * *  cd /path/to/project && python sync_jobs.py
"""
import argparse
import os
import sqlite3

import live_jobs as live
from model import load_models


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--provider", action="append", choices=list(live.PROVIDERS),
                    help="limit to one provider (repeatable)")
    ap.add_argument("--queries", help="comma separated search queries")
    ap.add_argument("--location", default="")
    ap.add_argument("--ignore-interval", action="store_true",
                    help="skip the minimum-gap safeguard (at your own risk: API terms/quota)")
    a = ap.parse_args()

    db = sqlite3.connect(os.environ.get("DATABASE_PATH", "job_recommender.db"))
    db.row_factory = sqlite3.Row
    live.ensure_schema(db)
    models = load_models()
    queries = [q.strip() for q in a.queries.split(",") if q.strip()] if a.queries else None
    results = live.sync_live_jobs(db, models, providers=a.provider, queries=queries,
                                  location=a.location, ignore_interval=a.ignore_interval)
    print(f"{'provider':<10}{'status':<9}{'fetched':>8}{'new':>6}{'upd':>6}{'removed':>9}  note")
    for r in results:
        print(f"{r['provider']:<10}{r['status']:<9}{r['fetched']:>8}{r['inserted']:>6}"
              f"{r['updated']:>6}{r['pruned']:>9}  {r['message']}")


if __name__ == "__main__":
    main()
