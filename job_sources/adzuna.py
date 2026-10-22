"""Adzuna jobs API  (https://developer.adzuna.com)

  GET https://api.adzuna.com/v1/api/jobs/{country}/search/{page}
      ?app_id=..&app_key=..&results_per_page=..&what=..&where=..&max_days_old=..

Needs a free key (ADZUNA_APP_ID / ADZUNA_APP_KEY). The free tier is limited
(roughly 1,000 calls/month at the time of writing — check your account), so a sync
makes at most ADZUNA_MAX_CALLS requests. Terms require showing "Jobs by Adzuna".
Search descriptions are truncated by Adzuna; redirect_url leads to the full ad.
"""
import os

from .base import Provider, ProviderError, RawJob, http_get_json

CURRENCY = {"in": "₹", "gb": "£", "us": "$", "au": "A$", "ca": "C$", "sg": "S$",
            "de": "€", "fr": "€", "nl": "€", "es": "€", "it": "€", "at": "€", "be": "€",
            "pl": "zł", "br": "R$", "mx": "MX$", "nz": "NZ$", "za": "R", "ch": "CHF"}


class AdzunaProvider(Provider):
    name = "adzuna"
    label = "Adzuna"
    attribution_text = "Jobs by Adzuna"
    attribution_url = "https://www.adzuna.com"
    needs_key = True
    min_interval_hours = 1

    def __init__(self):
        self.app_id = os.environ.get("ADZUNA_APP_ID", "")
        self.app_key = os.environ.get("ADZUNA_APP_KEY", "")
        # ADZUNA_BASE_URL exists for tests / corporate proxies; leave unset in production
        self.base_url = os.environ.get("ADZUNA_BASE_URL", "https://api.adzuna.com/v1/api/jobs").rstrip("/")
        self.country = os.environ.get("ADZUNA_COUNTRY", "in").lower()
        self.per_page = min(50, int(os.environ.get("ADZUNA_PER_PAGE", "20")))
        self.pages = max(1, int(os.environ.get("ADZUNA_PAGES", "1")))
        self.max_calls = max(1, int(os.environ.get("ADZUNA_MAX_CALLS", "10")))
        self.max_days_old = int(os.environ.get("ADZUNA_MAX_DAYS_OLD", "30"))

    def is_configured(self):
        return bool(self.app_id and self.app_key)

    def fetch(self, queries, location="", max_results=100):
        if not self.is_configured():
            raise ProviderError("Adzuna is not configured (set ADZUNA_APP_ID and ADZUNA_APP_KEY).")
        out, seen, calls = [], set(), 0
        for q in queries or [""]:
            for page in range(1, self.pages + 1):
                if calls >= self.max_calls or len(out) >= max_results:
                    return out
                params = {"app_id": self.app_id, "app_key": self.app_key,
                          "results_per_page": self.per_page, "sort_by": "date",
                          "max_days_old": self.max_days_old}
                if q:
                    params["what"] = q
                if location:
                    params["where"] = location
                data = http_get_json(f"{self.base_url}/{self.country}/search/{page}", params)
                calls += 1
                results = data.get("results") if isinstance(data, dict) else None
                if not isinstance(results, list):
                    raise ProviderError("Adzuna returned an unexpected response shape.")
                for r in results:
                    job = self._parse(r)
                    if job and job.external_id not in seen:
                        seen.add(job.external_id)
                        out.append(job)
                if len(results) < self.per_page:
                    break
        return out

    def _parse(self, r):
        if not isinstance(r, dict) or not r.get("id") or not r.get("title"):
            return None
        g = lambda d, *ks: _dig(d, *ks)  # noqa: E731
        contract = " ".join(str(x) for x in (r.get("contract_time"), r.get("contract_type")) if x)
        return RawJob(
            source=self.name, external_id=str(r["id"]), title=str(r["title"]),
            company=str(g(r, "company", "display_name") or ""),
            location=str(g(r, "location", "display_name") or ""),
            description=str(r.get("description") or ""),
            url=str(r.get("redirect_url") or ""), posted_at=str(r.get("created") or ""),
            salary_min=_num(r.get("salary_min")), salary_max=_num(r.get("salary_max")),
            salary_currency=CURRENCY.get(self.country, ""),
            salary_estimated=str(r.get("salary_is_predicted", "0")) == "1",
            job_type_raw=contract,
            tags=[t for t in [g(r, "category", "label")] if t], country=self.country)


def _dig(d, *keys):
    for k in keys:
        d = d.get(k) if isinstance(d, dict) else None
    return d


def _num(v):
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None
