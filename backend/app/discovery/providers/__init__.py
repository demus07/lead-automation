from __future__ import annotations

from app.discovery.providers.base import DiscoveryProvider
from app.discovery.providers.company_brain import CompanyBrainProvider
from app.discovery.providers.public_sources import (
    HNHiringProvider,
    RSSProvider,
    WikidataProvider,
    YCDirectoryProvider,
)
from app.discovery.providers.web_search import (
    BraveSearchProvider,
    SearXNGProvider,
    SerpAPIProvider,
    TavilyProvider,
)

_PROVIDERS: dict[str, DiscoveryProvider] = {
    p.key: p
    for p in [
        YCDirectoryProvider(),
        WikidataProvider(),
        HNHiringProvider(),
        RSSProvider(),
        BraveSearchProvider(),
        TavilyProvider(),
        SerpAPIProvider(),
        SearXNGProvider(),
        CompanyBrainProvider(),
    ]
}

WEB_SEARCH_KEYS = ["brave", "tavily", "serpapi", "searxng"]


def get_provider(key: str) -> DiscoveryProvider:
    if key not in _PROVIDERS:
        raise KeyError(f"Unknown discovery provider '{key}'")
    return _PROVIDERS[key]


def all_providers() -> list[DiscoveryProvider]:
    return list(_PROVIDERS.values())


def register_provider(p: DiscoveryProvider) -> None:
    """Extension point (also used by tests to register fakes)."""
    _PROVIDERS[p.key] = p
