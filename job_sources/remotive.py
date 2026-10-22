"""Remotive remote-jobs API  (https://github.com/remotive-com/remote-jobs-api)

  GET https://remotive.com/api/remote-jobs      (no key)

Terms (summarised from their documentation — read them yourself before deploying):
  * fetch infrequently (they ask for at most ~4 requests/day, 2 requests/minute)
  * listings are delayed ~24 h
  * you MUST name Remotive as the source and link back to the listing URL
  * do not re-publish the jobs to other job boards / aggregators

Reports differ on whether their `search` / `category` parameters actually filter, so we
download the (small) full feed once and filter on OUR side.
"""
import os

from .base import Provider, ProviderError, RawJob, http_get_json


class RemotiveProvider(Provider):
    name = "remotive"
    label = "Remotive"
    attribution_text = "Remote jobs from Remotive"
    attribution_url = "https://remotive.com"
    min_interval_hours = 6            # keeps us at <= 4 fetches/day
    full_feed = True                  # one call returns the whole board

    def fetch(self, queries, location="", max_results=100):
        # REMOTIVE_URL exists for tests / proxies; leave unset in production
        data = http_get_json(os.environ.get("REMOTIVE_URL", "https://remotive.com/api/remote-jobs"))
        jobs = data.get("jobs") if isinstance(data, dict) else None
        if not isinstance(jobs, list):
            raise ProviderError("Remotive returned an unexpected response shape.")
        terms = [q.lower() for q in (queries or []) if q]
        out = []
        for r in jobs:
            job = self._parse(r)
            if not job:
                continue
            head = " ".join([job.title, " ".join(job.tags)]).lower()
            full = (head + " " + job.description).lower()
            if terms and not any(_matches(t, head, full) for t in terms):
                continue
            out.append(job)
            if len(out) >= max_results:
                break
        return out

    def _parse(self, r):
        if not isinstance(r, dict) or not r.get("id") or not r.get("title"):
            return None
        tags = r.get("tags") if isinstance(r.get("tags"), list) else []
        tags = [str(t) for t in tags]
        if r.get("category"):
            tags.append(str(r["category"]))
        region = str(r.get("candidate_required_location") or "").strip()
        return RawJob(
            source=self.name, external_id=str(r["id"]), title=str(r["title"]),
            company=str(r.get("company_name") or ""),
            location=("Remote - " + region) if region else "Remote",
            description=str(r.get("description") or ""), url=str(r.get("url") or ""),
            posted_at=str(r.get("publication_date") or ""),
            salary_text=str(r.get("salary") or ""),
            job_type_raw=str(r.get("job_type") or "") + " remote", tags=tags)


_GENERIC = {"developer", "engineer", "manager", "analyst", "senior", "junior", "lead",
            "jobs", "job", "remote", "specialist", "associate", "executive"}


def _matches(term, title_part, full_text):
    """Heuristic relevance filter (we filter on our side, see module docstring).
    A query like 'python developer' should also find 'Backend Engineer (Python)':
      * match if any DISTINCTIVE word (not 'developer', 'engineer', ...) is in the
        title / tags / category, or
      * if every word of the query appears somewhere in the full text."""
    words = term.split()
    key = [w for w in words if w not in _GENERIC] or words
    return any(w in title_part for w in key) or all(w in full_text for w in words)
