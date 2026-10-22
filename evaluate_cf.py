"""
evaluate_cf.py — sanity-check the collaborative filter on SIMULATED users
=========================================================================
No real interaction data exists yet, so users are generated: each prefers two job
categories and saves/applies mostly to jobs there (85%) plus some random ones (15%).
One interaction per user is hidden; we measure whether each method ranks it highly.

  Random      : shuffled jobs
  Popularity  : most-interacted jobs overall (the standard CF baseline)
  Item-KNN    : collab.py

IMPORTANT: the data comes from a taste-cluster generator, so CF is *expected* to win.
This validates the implementation (it recovers hidden structure, beats popularity); it
does NOT prove how much it will help real users. Re-run on real saves/applies later.

    python evaluate_cf.py
"""
import random
from collections import Counter

import numpy as np
import pandas as pd

from collab import CollabModel

N_USERS, SEEDS, K = 300, 5, 10


def simulate(jobs, rng):
    by_cat = {c: g["job_id"].tolist() for c, g in jobs.groupby("category") if len(g) >= 4}
    cats, all_ids = sorted(by_cat), jobs["job_id"].tolist()
    users = {}
    for u in range(N_USERS):
        pref = rng.sample(cats, 2)
        pool = by_cat[pref[0]] + by_cat[pref[1]]
        items = {}
        for _ in range(rng.randint(6, 10)):
            j = rng.choice(pool) if rng.random() < 0.85 else rng.choice(all_ids)
            items[j] = items.get(j, 0) + (2.0 if rng.random() < 0.35 else 1.0)
        users[u] = {j: min(w, 3.0) for j, w in items.items()}
    return users, all_ids


def metrics(rank):                       # rank: 1-based position of the hidden job
    return (1.0 if rank <= K else 0.0, 1.0 / np.log2(rank + 1) if rank <= K else 0.0)


def run(seed):
    rng = random.Random(seed)
    jobs = pd.read_csv("data/jobs.csv")
    users, all_ids = simulate(jobs, rng)
    train, held = {}, {}
    for u, items in users.items():
        hid = rng.choice(list(items))
        held[u] = hid
        train[u] = {j: w for j, w in items.items() if j != hid}
    model = CollabModel(train)
    pop = Counter()
    for items in train.values():
        pop.update(items.keys())
    res = {"Random": [], "Popularity": [], "Item-KNN (collab.py)": []}
    for u in train:
        cand = [j for j in all_ids if j not in train[u]]
        order = {"Random": rng.sample(cand, len(cand)),
                 "Popularity": sorted(cand, key=lambda j: -pop[j])}
        sc, _ = model.scores_for(u)
        order["Item-KNN (collab.py)"] = sorted(cand, key=lambda j: (-sc.get(j, 0.0), -pop[j]))
        for name, lst in order.items():
            res[name].append(metrics(lst.index(held[u]) + 1))
    return {n: np.mean(v, axis=0) for n, v in res.items()}


def main():
    runs = [run(s) for s in range(SEEDS)]
    print(f"{N_USERS} simulated users x {SEEDS} seeds, 1 hidden interaction each, "
          f"{len(pd.read_csv('data/jobs.csv'))} jobs\n")
    print(f"{'Method':<24}{'HitRate@10':>12}{'nDCG@10':>10}")
    print("-" * 46)
    for name in runs[0]:
        hr = np.mean([r[name][0] for r in runs]); nd = np.mean([r[name][1] for r in runs])
        print(f"{name:<24}{hr:>12.3f}{nd:>10.3f}")


if __name__ == "__main__":
    main()
