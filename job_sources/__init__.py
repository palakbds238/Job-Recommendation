"""Pluggable live job-data providers.

Add a new source by writing a class with the `Provider` interface (see base.py)
and registering it in PROVIDERS below.
"""
from .adzuna import AdzunaProvider
from .base import Provider, ProviderError, RawJob  # noqa: F401
from .remotive import RemotiveProvider

PROVIDERS = {p.name: p for p in (AdzunaProvider, RemotiveProvider)}


def get_providers(only=None):
    """Instantiate providers (optionally only the named ones)."""
    names = only or list(PROVIDERS)
    return [PROVIDERS[n]() for n in names if n in PROVIDERS]
