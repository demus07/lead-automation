from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


class ProviderError(Exception):
    pass


class ProviderNotConfigured(ProviderError):
    pass


@dataclass
class DiscoveryQuery:
    text: str = ""
    industries: list[str] = field(default_factory=list)
    geographies: list[str] = field(default_factory=list)
    company_sizes: list[str] = field(default_factory=list)  # e.g. "11-50"
    keywords: list[str] = field(default_factory=list)
    signal_focus: list[str] = field(default_factory=list)
    limit: int = 10
    offset: int = 0
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class DiscoveredSignal:
    signal_type: str
    description: str
    source_url: str
    published_at: datetime | None = None
    evidence: str | None = None
    confidence: float = 0.6


@dataclass
class DiscoveredCompany:
    name: str
    domain: str | None = None
    website: str | None = None
    industry: str | None = None
    location: str | None = None
    country: str | None = None
    size_range: str | None = None
    description: str | None = None
    source_url: str | None = None
    source_title: str | None = None
    snippet: str | None = None
    signals: list[DiscoveredSignal] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        d = asdict(self)
        for s in d["signals"]:
            if s.get("published_at"):
                s["published_at"] = s["published_at"].isoformat()
        return d


@dataclass
class ProviderStatus:
    key: str
    label: str
    kind: str
    status: str  # available | connected | not_configured | error
    requires_auth: bool
    description: str
    detail: str = ""


class DiscoveryProvider(ABC):
    key: str = ""
    label: str = ""
    kind: str = "directory"  # web_search | directory | news | hiring | rss | crm
    requires_auth: bool = False
    description: str = ""
    # Whether the provider consumes the configurable daily *web search* quota.
    counts_against_search_quota: bool = False

    def is_configured(self, cfg: dict[str, Any]) -> bool:
        return True

    def status(self, cfg: dict[str, Any]) -> ProviderStatus:
        configured = self.is_configured(cfg)
        return ProviderStatus(
            key=self.key,
            label=self.label,
            kind=self.kind,
            status=("connected" if self.requires_auth else "available") if configured else "not_configured",
            requires_auth=self.requires_auth,
            description=self.description,
        )

    @abstractmethod
    def search(self, q: DiscoveryQuery, cfg: dict[str, Any]) -> list[DiscoveredCompany]:
        ...

    def describe_query(self, q: DiscoveryQuery) -> str:
        bits = [q.text] if q.text else []
        if q.industries:
            bits.append("industries=" + ",".join(q.industries))
        if q.geographies:
            bits.append("geo=" + ",".join(q.geographies))
        if q.company_sizes:
            bits.append("sizes=" + ",".join(q.company_sizes))
        return "; ".join(bits) or "(all)"


SIZE_BUCKETS = [(1, 10, "1-10"), (11, 50, "11-50"), (51, 200, "51-200"), (201, 500, "201-500"),
                (501, 1000, "501-1000"), (1001, 5000, "1001-5000"), (5001, 10**9, "5001+")]


def size_bucket(employees: int | float | None) -> str | None:
    if employees is None:
        return None
    try:
        n = int(employees)
    except (TypeError, ValueError):
        return None
    for lo, hi, label in SIZE_BUCKETS:
        if lo <= n <= hi:
            return label
    return None


def size_matches(employees: int | None, sizes: list[str]) -> bool:
    if not sizes:
        return True
    b = size_bucket(employees)
    return b is None or b in sizes  # unknown size is not excluded
