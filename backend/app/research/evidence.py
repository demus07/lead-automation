"""Evidence registry + validation of AI output against stored sources."""
from __future__ import annotations

import re
from typing import Any


def norm(s: str) -> str:
    s = s.lower().replace("’", "'").replace("“", '"').replace("”", '"').replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", s).strip()


def quote_in(quote: str | None, text: str) -> bool:
    if not quote:
        return False
    q = norm(quote).strip(" .\"'")
    return len(q) >= 4 and q in norm(text)


class EvidenceSet:
    """Holds evidence items the agents may cite: {id, kind, url, title, text}."""

    def __init__(self, items: list[dict[str, Any]] | None = None):
        self.items: dict[str, dict[str, Any]] = {}
        for it in items or []:
            self.items[it["id"]] = it

    def add(self, id_: str, kind: str, url: str | None, text: str, title: str | None = None, **extra: Any) -> None:
        self.items[id_] = {"id": id_, "kind": kind, "url": url, "title": title, "text": text, **extra}

    def valid_ids(self, ids: list[str]) -> list[str]:
        return [i for i in ids if i in self.items]

    def text_of(self, ids: list[str]) -> str:
        return "\n".join(self.items[i]["text"] for i in ids if i in self.items)

    def any_quote(self, quote: str | None, ids: list[str] | None = None) -> bool:
        pool = ids if ids else list(self.items)
        return any(quote_in(quote, self.items[i]["text"]) for i in pool if i in self.items)

    def public(self, text_chars: int = 400) -> list[dict[str, Any]]:
        """Serializable evidence for storage/UI (truncated text)."""
        out = []
        for it in self.items.values():
            d = {k: v for k, v in it.items() if k != "text"}
            d["excerpt"] = (it.get("text") or "")[:text_chars]
            out.append(d)
        return out
