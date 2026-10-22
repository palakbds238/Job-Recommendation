"""Shared types and a hardened HTTP helper for job providers."""
import json
import logging
from dataclasses import dataclass, field
from typing import List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger("job_sources")

USER_AGENT = "CareerAI-JobSync/1.0 (college project; contact: set CONTACT_EMAIL)"
CONNECT_TIMEOUT, READ_TIMEOUT = 5, 20
MAX_BYTES = 8 * 1024 * 1024          # refuse absurdly large responses


class ProviderError(Exception):
    """A provider call failed (bad credentials, network, malformed response…)."""


@dataclass
class RawJob:
    """What a provider hands back, before our own enrichment."""
    source: str
    external_id: str
    title: str
    company: str = ""
    location: str = ""
    description: str = ""             # may contain HTML; cleaned later
    url: str = ""
    posted_at: str = ""               # ISO-8601 if available
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    salary_currency: str = ""         # symbol or ISO code
    salary_text: str = ""             # free-form salary (e.g. Remotive)
    salary_estimated: bool = False
    job_type_raw: str = ""
    tags: List[str] = field(default_factory=list)
    country: str = ""


def _session():
    s = requests.Session()
    retry = Retry(total=2, backoff_factor=1.0, status_forcelist=(429, 500, 502, 503, 504),
                  allowed_methods=("GET",), respect_retry_after_header=True,
                  raise_on_status=False)   # let http_get_json map 429/5xx to clear messages
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
    return s


def http_get_json(url, params=None):
    """GET -> parsed JSON dict. Raises ProviderError on any problem."""
    try:
        with _session().get(url, params=params, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
                            stream=True) as r:
            if r.status_code in (401, 403):
                raise ProviderError(f"{_host(url)} rejected the credentials (HTTP {r.status_code})")
            if r.status_code == 429:
                raise ProviderError(f"{_host(url)} rate limit reached (HTTP 429)")
            if r.status_code != 200:
                raise ProviderError(f"{_host(url)} returned HTTP {r.status_code}")
            body = r.raw.read(MAX_BYTES + 1, decode_content=True)
            if len(body) > MAX_BYTES:
                raise ProviderError(f"{_host(url)} response too large")
            return json.loads(body.decode("utf-8", errors="replace"))
    except ProviderError:
        raise
    except (requests.RequestException, ValueError) as e:
        raise ProviderError(f"{_host(url)} request failed: {type(e).__name__}") from e


def _host(url):
    return url.split("/")[2] if "//" in url else url


class Provider:
    """Interface every live source implements."""
    name = "base"
    label = "Base"
    attribution_text = ""
    attribution_url = ""
    min_interval_hours = 0            # politeness: minimum gap between syncs
    needs_key = False

    def is_configured(self) -> bool:
        return True

    def fetch(self, queries, location="", max_results=100) -> List[RawJob]:
        raise NotImplementedError
