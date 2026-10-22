"""
collab.py — item-based collaborative filtering on implicit feedback
===================================================================
Signal: which jobs users SAVED (weight 1) and APPLIED to (weight 2). People who
interacted with job A also tended to interact with job B  ->  B is recommended to
someone who interacted with A, even if their profile text never mentions B's skills.

Method (classic item-KNN)
  R      : users x jobs matrix of interaction weights
  sim    : cosine similarity between job columns, damped by co-occurrence support
           sim_ij = cos_ij * n_ij / (n_ij + SHRINK)       (few co-occurrences -> weak)
  score  : score_j = sum_i  w_ui * sim_ij                  for the jobs i user u touched
  output : scores scaled to 0..1, plus a human-readable reason ("Because you saved X")

Cold start (important, honest behaviour)
  The blend weight is scaled by how much data exists, so CF stays silent until it
  has something to say:
      weight = MAX_WEIGHT * min(1, interactions_of_this_user / 3)
                          * min(1, users_with_interactions / MIN_USERS)
  A brand-new user, or a platform with fewer than 2 active users, gets weight 0 and
  the content-based ranking is used unchanged.

Only user ids / job ids are used — no names, profiles or resume text.
"""
from collections import defaultdict

import numpy as np
from scipy.sparse import csr_matrix

SAVE_W, APPLY_W, PAIR_CAP = 1.0, 2.0, 3.0
SHRINK = 2.0            # support damping
TOP_K = 30              # neighbours kept per job
MAX_WEIGHT = 0.30       # CF may lift a score by up to 30% of the gap to 100%
MIN_USERS = 5           # users with interactions needed for full confidence
MIN_USERS_ANY = 2       # below this CF is switched off entirely


def interactions_from_db(db):
    """Rows -> {user_id: {job_id: weight}} (admins excluded)."""
    out = defaultdict(lambda: defaultdict(float))
    q_saved = ("SELECT s.user_id, s.job_id FROM saved_jobs s "
               "JOIN users u ON u.id = s.user_id WHERE u.is_admin = 0")
    q_applied = ("SELECT a.user_id, a.job_id FROM applied_jobs a "
                 "JOIN users u ON u.id = a.user_id WHERE u.is_admin = 0")
    for r in db.execute(q_saved):
        out[r[0]][r[1]] += SAVE_W
    for r in db.execute(q_applied):
        out[r[0]][r[1]] += APPLY_W
    return {u: {j: min(w, PAIR_CAP) for j, w in jobs.items()} for u, jobs in out.items()}


def interactions_signature(db):
    """Cheap fingerprint of the interaction tables (for cache invalidation)."""
    a = db.execute("SELECT COUNT(*), COALESCE(MAX(id),0) FROM saved_jobs").fetchone()
    b = db.execute("SELECT COUNT(*), COALESCE(MAX(id),0) FROM applied_jobs").fetchone()
    return (a[0], a[1], b[0], b[1])


class CollabModel:
    def __init__(self, interactions):
        """interactions: {user_id: {job_id: weight}}"""
        self.interactions = {u: dict(j) for u, j in interactions.items() if j}
        self.n_users = len(self.interactions)
        self.jobs = sorted({j for js in self.interactions.values() for j in js})
        self.jidx = {j: i for i, j in enumerate(self.jobs)}
        self.sim = None
        if self.n_users >= MIN_USERS_ANY and self.jobs:
            self._fit()

    def _fit(self):
        users = list(self.interactions)
        rows, cols, vals = [], [], []
        for ui, u in enumerate(users):
            for j, w in self.interactions[u].items():
                rows.append(ui); cols.append(self.jidx[j]); vals.append(w)
        R = csr_matrix((vals, (rows, cols)), shape=(len(users), len(self.jobs)))
        norms = np.sqrt(np.asarray(R.multiply(R).sum(axis=0)).ravel())
        norms[norms == 0] = 1.0
        Rn = R.multiply(1.0 / norms).tocsr()
        S = (Rn.T @ Rn).tocsr()                                   # cosine
        B = R.copy(); B.data[:] = 1.0
        C = (B.T @ B).tocsr()                                     # co-occurrence counts
        D = C.copy(); D.data = 1.0 / (D.data + SHRINK)
        S = S.multiply(C).multiply(D).tocsr()                     # support damping
        S.setdiag(0); S.eliminate_zeros()
        self.sim = self._top_k(S)

    @staticmethod
    def _top_k(S):
        S = S.tocsr()
        data, idx, ptr = [], [], [0]
        for i in range(S.shape[0]):
            a, b = S.indptr[i], S.indptr[i + 1]
            d, c = S.data[a:b], S.indices[a:b]
            if len(d) > TOP_K:
                keep = np.argpartition(-d, TOP_K)[:TOP_K]
                d, c = d[keep], c[keep]
            data.extend(d); idx.extend(c); ptr.append(len(data))
        return csr_matrix((data, idx, ptr), shape=S.shape)

    # ── per-user API ────────────────────────────────────────────────────────
    def confidence(self, user_id):
        n = len(self.interactions.get(user_id, {}))
        if self.sim is None or n == 0 or self.n_users < MIN_USERS_ANY:
            return 0.0
        return MAX_WEIGHT * min(1.0, n / 3.0) * min(1.0, self.n_users / MIN_USERS)

    def scores_for(self, user_id):
        """-> ({job_id: score 0..1}, blend_weight)."""
        w = self.confidence(user_id)
        if w == 0.0:
            return {}, 0.0
        vec = np.zeros(len(self.jobs))
        for j, wt in self.interactions[user_id].items():
            vec[self.jidx[j]] = wt
        s = self.sim.T @ vec            # sim is directional after top-k; use transpose
        s = np.asarray(s).ravel()
        mx = s.max()
        if mx <= 0:
            return {}, 0.0
        s = s / mx
        return {self.jobs[i]: float(s[i]) for i in np.nonzero(s)[0]}, w

    def explain(self, user_id, job_id):
        """Which of the user's own jobs most strongly links to `job_id`?
        -> (source_job_id, 'saved'|'applied') or None."""
        if self.sim is None or job_id not in self.jidx:
            return None
        j = self.jidx[job_id]
        col = self.sim.getcol(j).toarray().ravel()
        row = self.sim.getrow(j).toarray().ravel()
        link = np.maximum(col, row)
        best, best_score = None, 0.0
        for src, wt in self.interactions.get(user_id, {}).items():
            sc = wt * link[self.jidx[src]]
            if src != job_id and sc > best_score:
                best, best_score = src, sc
        if best is None:
            return None
        return best, ("applied" if self.interactions[user_id][best] >= APPLY_W else "saved")
