"""
live_jobs.py — pull live jobs from external APIs into the recommender
=====================================================================
  providers (job_sources/)  ->  normalise  ->  `live_jobs` table  ->  job pool

Each external ad is converted to the same schema as the dataset:
  * HTML stripped (descriptions are untrusted input)
  * skills extracted with skills.py            (so skill-gap + coverage work)
  * category predicted by the Random Forest    (so the category filter works)
  * experience / job type / salary inferred heuristically (flagged as inferred)
  * only http(s) apply links are kept

Safety valves: per-provider minimum sync interval (API terms / quota), caps on the
number of stored jobs, expiry of stale listings (jobs users saved or applied to are
kept so their history never breaks).
"""
import logging
import os
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from html import unescape
from html.parser import HTMLParser

from job_sources import PROVIDERS, ProviderError
from model import LIVE_JOB_OFFSET, predict_category
from skills import parse_skill_list

log = logging.getLogger("live_jobs")

TTL_DAYS = int(os.environ.get("LIVE_JOB_TTL_DAYS", "21"))
MAX_JOBS = int(os.environ.get("LIVE_MAX_JOBS", "2000"))
# The classifier spreads probability over 19 categories (random guess ~5%), so even a
# correct prediction on a short ad often scores only 15-45%. Below this -> "Other".
CATEGORY_MIN_CONF = 12.0
DEFAULT_QUERIES = ["python developer", "data analyst", "software engineer", "web developer"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS live_jobs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    source              TEXT NOT NULL,
    external_id         TEXT NOT NULL,
    title               TEXT NOT NULL,
    company             TEXT,
    location            TEXT,
    description         TEXT,
    skills_required     TEXT,
    category            TEXT,
    experience_required TEXT,
    education_required  TEXT,
    salary_range        TEXT,
    salary_lpa          REAL DEFAULT 0,
    job_type            TEXT,
    url                 TEXT,
    posted_at           TEXT,
    fetched_at          TEXT,
    last_seen           TEXT,
    updated_at          TEXT,
    UNIQUE(source, external_id)
);
CREATE TABLE IF NOT EXISTS sync_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source      TEXT NOT NULL,
    started_at  TEXT,
    finished_at TEXT,
    status      TEXT,
    fetched     INTEGER DEFAULT 0,
    inserted    INTEGER DEFAULT 0,
    updated     INTEGER DEFAULT 0,
    pruned      INTEGER DEFAULT 0,
    message     TEXT
);
"""


def ensure_schema(db):
    db.executescript(SCHEMA)


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


# ── text helpers ────────────────────────────────────────────────────────────
class _TextExtractor(HTMLParser):
    BLOCK = {"p", "br", "li", "div", "ul", "ol", "h1", "h2", "h3", "h4", "tr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self._skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def html_to_text(s, limit=3000):
    """Strip tags/scripts/entities. Descriptions from the internet are untrusted."""
    if not s:
        return ""
    p = _TextExtractor()
    try:
        p.feed(str(s)); p.close()
        text = "".join(p.parts)
    except Exception:  # noqa: BLE001  malformed HTML -> crude fallback
        text = re.sub(r"<[^>]*>", " ", str(s))
    text = unescape(text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\s*\n\s*", "\n", text).strip()
    return text[:limit]


def _one_line(s, limit):
    return re.sub(r"\s+", " ", html_to_text(s, limit * 2)).strip()[:limit]


def safe_url(u):
    u = (u or "").strip()
    return u if re.match(r"^https?://[^\s<>\"']+$", u) and len(u) < 2000 else ""


_EXP_RX = re.compile(r"(\d{1,2})\s*\+?\s*(?:-|–|to)?\s*(\d{1,2})?\s*\+?\s*(?:years?|yrs?)\b", re.I)


def parse_experience(text):
    """Map text to the dataset's buckets. Heuristic — 'Not specified' if unsure."""
    m = _EXP_RX.search(text or "")
    if m:
        lo = int(m.group(1))
        return ("0-1 years" if lo <= 0 else "1-3 years" if lo <= 2 else "3-5 years" if lo <= 4
                else "5-8 years" if lo <= 7 else "8+ years")
    t = (text or "").lower()
    if re.search(r"\b(intern|internship|fresher|entry[- ]level|graduate|junior|trainee)\b", t):
        return "0-1 years"
    if re.search(r"\b(senior|lead|principal|staff|architect|head of)\b", t):
        return "5-8 years"
    return "Not specified"


def infer_job_type(raw_type, location, title):
    t = f"{raw_type} {location} {title}".lower()
    if "remote" in t:
        return "Remote"
    if "hybrid" in t:
        return "Hybrid"
    if "intern" in t:
        return "Internship"
    if "part" in t and "time" in t or "part_time" in t:
        return "Part-time"
    if "contract" in t or "freelance" in t:
        return "Contract"
    return "Full-time"


def format_salary(raw):
    """-> (display string, salary in LPA or 0). LPA only for INR annual figures."""
    lo, hi, cur = raw.salary_min, raw.salary_max, raw.salary_currency
    vals = [v for v in (lo, hi) if v]
    if vals:
        est = " (est.)" if raw.salary_estimated else ""
        if cur == "₹":
            a, b = (min(vals) / 1e5, max(vals) / 1e5)
            fmt = lambda x: f"{x:.1f}".rstrip("0").rstrip(".")  # noqa: E731
            rng = fmt(a) if abs(a - b) < 0.05 else f"{fmt(a)}-{fmt(b)}"
            return f"{rng} LPA{est}", round(sum(vals) / len(vals) / 1e5, 2)
        k = lambda x: f"{cur}{x / 1000:.0f}k"  # noqa: E731
        rng = k(vals[0]) if len(set(vals)) == 1 else f"{k(min(vals))}-{k(max(vals))}"
        return rng + est, 0.0
    if raw.salary_text.strip():
        return _one_line(raw.salary_text, 60), 0.0
    return "Not disclosed", 0.0


# ── enrichment ──────────────────────────────────────────────────────────────
def enrich(raw, models):
    """RawJob -> dict of live_jobs columns (None if unusable)."""
    title = _one_line(raw.title, 200)
    if not title or not raw.external_id:
        return None
    company = _one_line(raw.company, 150) or "Not specified"
    location = _one_line(raw.location, 150) or "Not specified"
    desc = html_to_text(raw.description)

    tag_text = ", ".join(raw.tags)
    found = models["extractor"].extract(f"{title}\n{desc}\n{tag_text}")
    found |= parse_skill_list(tag_text) & models["skill_vocab"]
    disp = models["skill_display"]
    skills = ", ".join(sorted(disp.get(s, s.title()) for s in found))

    category, conf = predict_category(models, f"{title} {skills} {desc[:1000]}".lower())
    if conf < CATEGORY_MIN_CONF:
        category = "Other"
    salary_range, lpa = format_salary(raw)
    return {
        "source": raw.source, "external_id": str(raw.external_id), "title": title,
        "company": company, "location": location, "description": desc,
        "skills_required": skills, "category": category,
        "experience_required": parse_experience(f"{title} {desc}"),
        "education_required": "Not specified",
        "salary_range": salary_range, "salary_lpa": lpa,
        "job_type": infer_job_type(raw.job_type_raw, location, title),
        "url": safe_url(raw.url), "posted_at": (raw.posted_at or "")[:40],
    }


# ── persistence ─────────────────────────────────────────────────────────────
_COLS = ["title", "company", "location", "description", "skills_required", "category",
         "experience_required", "education_required", "salary_range", "salary_lpa",
         "job_type", "url", "posted_at"]


def upsert(db, job):
    """-> 'inserted' | 'updated'."""
    now = _now()
    row = db.execute("SELECT id FROM live_jobs WHERE source=? AND external_id=?",
                     (job["source"], job["external_id"])).fetchone()
    if row:
        db.execute("UPDATE live_jobs SET " + ", ".join(f"{c}=?" for c in _COLS)
                   + ", last_seen=?, updated_at=? WHERE id=?",
                   [job[c] for c in _COLS] + [now, now, row[0]])
        return "updated"
    db.execute("INSERT INTO live_jobs (source, external_id, " + ", ".join(_COLS)
               + ", fetched_at, last_seen, updated_at) VALUES (?,?," + ",".join("?" * len(_COLS))
               + ",?,?,?)", [job["source"], job["external_id"]] + [job[c] for c in _COLS]
               + [now, now, now])
    return "inserted"


_NOT_REFERENCED = ("AND (? + id) NOT IN (SELECT job_id FROM saved_jobs) "
                   "AND (? + id) NOT IN (SELECT job_id FROM applied_jobs)")


def prune(db, source=None, seen_before=None):
    """Delete expired / vanished live jobs that nobody saved or applied to."""
    n = 0
    cutoff = (datetime.now(timezone.utc) - timedelta(days=TTL_DAYS)).isoformat(timespec="microseconds")
    n += db.execute(f"DELETE FROM live_jobs WHERE last_seen < ? {_NOT_REFERENCED}",
                    (cutoff, LIVE_JOB_OFFSET, LIVE_JOB_OFFSET)).rowcount
    if source and seen_before:        # full-feed providers: not in the feed any more
        n += db.execute(f"DELETE FROM live_jobs WHERE source=? AND last_seen < ? {_NOT_REFERENCED}",
                        (source, seen_before, LIVE_JOB_OFFSET, LIVE_JOB_OFFSET)).rowcount
    total = db.execute("SELECT COUNT(*) FROM live_jobs").fetchone()[0]
    if total > MAX_JOBS:
        n += db.execute(
            f"DELETE FROM live_jobs WHERE id IN (SELECT id FROM live_jobs WHERE 1=1 "
            f"{_NOT_REFERENCED} ORDER BY last_seen ASC LIMIT ?)",
            (LIVE_JOB_OFFSET, LIVE_JOB_OFFSET, total - MAX_JOBS)).rowcount
    return n


# ── queries ─────────────────────────────────────────────────────────────────
def default_queries(db):
    """LIVE_QUERIES from the environment, else sensible defaults plus the skills
    your own users list most often (so live jobs match your actual audience)."""
    env = os.environ.get("LIVE_QUERIES", "").strip()
    if env:
        return [q.strip() for q in env.split(",") if q.strip()][:8]
    qs = list(DEFAULT_QUERIES)
    try:
        counts = Counter()
        for r in db.execute("SELECT p.skills FROM user_profiles p JOIN users u ON u.id=p.user_id "
                            "WHERE u.is_admin=0 AND p.skills IS NOT NULL"):
            counts.update(parse_skill_list(r[0]))
        for skill, _ in counts.most_common(8):
            if skill not in ("c", "r") and not any(skill in q for q in qs) and len(qs) < 6:
                qs.append(skill)
    except Exception:  # noqa: BLE001
        log.debug("could not derive queries from user skills", exc_info=True)
    return qs


# ── orchestration ───────────────────────────────────────────────────────────
def _last_run(db, source):
    # successful syncs and HTTP-level refusals (rate limit, bad key, 5xx) count as an
    # attempt; a plain connection failure does not, so a flaky network can be retried
    r = db.execute("SELECT finished_at FROM sync_log WHERE source=? AND (status='ok' OR "
                   "(status='error' AND (message LIKE '%HTTP%' OR message LIKE '%rate limit%'))) "
                   "ORDER BY id DESC LIMIT 1", (source,)).fetchone()
    return datetime.fromisoformat(r[0]) if r and r[0] else None


def sync_live_jobs(db, models, providers=None, queries=None, location="",
                   ignore_interval=False, max_per_provider=150):
    """Run a sync. `providers`: list of provider names (default: all configured).
    Returns one result dict per provider."""
    names = providers or list(PROVIDERS)
    queries = queries if queries is not None else default_queries(db)
    results = []
    for name in names:
        cls = PROVIDERS.get(name)
        if cls is None:
            continue
        p = cls()
        res = {"provider": name, "status": "ok", "fetched": 0, "inserted": 0,
               "updated": 0, "pruned": 0, "message": ""}
        started = _now()
        try:
            if not p.is_configured():
                res.update(status="skipped", message="not configured (API key missing)")
                results.append(res); continue
            last = _last_run(db, name)
            wait = timedelta(hours=p.min_interval_hours)
            if not ignore_interval and last and datetime.now(timezone.utc) - last < wait:
                nxt = (last + wait).strftime("%Y-%m-%d %H:%M UTC")
                res.update(status="skipped", message=f"rate-limit policy: next sync allowed after {nxt}")
                results.append(res); continue
            raws = p.fetch(queries, location=location, max_results=max_per_provider)
            res["fetched"] = len(raws)
            for raw in raws:
                job = enrich(raw, models)
                if job:
                    res[upsert(db, job)] += 1
            res["pruned"] = prune(db, source=name if getattr(p, "full_feed", False) else None,
                                  seen_before=started)
            res["message"] = f"queries: {', '.join(queries[:6])}" if queries else ""
        except ProviderError as e:
            res.update(status="error", message=str(e))
        except Exception as e:  # noqa: BLE001
            log.exception("sync failed for %s", name)
            res.update(status="error", message=f"unexpected error: {type(e).__name__}")
        db.execute("INSERT INTO sync_log (source, started_at, finished_at, status, fetched, "
                   "inserted, updated, pruned, message) VALUES (?,?,?,?,?,?,?,?,?)",
                   (name, started, _now(), res["status"], res["fetched"], res["inserted"],
                    res["updated"], res["pruned"], res["message"][:300]))
        db.commit()
        results.append(res)
    return results
