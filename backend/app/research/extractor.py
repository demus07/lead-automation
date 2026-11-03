"""Deterministic HTML extraction."""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Comment

from app.ai.sanitize import clean_text, detect_injection
from app.discovery.normalize import normalize_domain, normalize_email

LINK_KINDS: list[tuple[str, tuple[str, ...]]] = [
    ("about", ("about", "about-us", "company", "who-we-are", "our-story", "mission")),
    ("team", ("team", "people", "leadership", "management", "founders", "our-team", "meet-the-team")),
    ("services", ("services", "products", "product", "solutions", "platform", "features", "what-we-do", "how-it-works")),
    ("pricing", ("pricing", "plans", "price")),
    ("careers", ("careers", "jobs", "join-us", "work-with-us", "hiring", "join")),
    ("contact", ("contact", "contact-us", "get-in-touch", "demo", "book-a-demo")),
    ("news", ("news", "press", "blog", "newsroom", "media", "announcements", "updates", "changelog")),
    ("customers", ("customers", "case-studies", "case-study", "clients", "testimonials", "work", "portfolio")),
]
CTA_WORDS = ("get started", "book a demo", "request a demo", "contact", "sign up", "start free", "try", "talk to",
             "get in touch", "schedule", "buy", "subscribe", "join", "free trial", "learn more", "get a quote")
TECH_HINTS = {
    "wordpress": ("wp-content", "wp-includes"), "webflow": ("webflow",), "shopify": ("cdn.shopify", "shopify"),
    "squarespace": ("squarespace",), "wix": ("wix.com", "wixstatic"), "framer": ("framer.com", "framerusercontent"),
    "hubspot": ("hs-scripts", "hubspot"), "intercom": ("intercom",), "google_analytics": ("googletagmanager", "gtag("),
    "nextjs": ("__next", "_next/static"), "react": ("react",), "drift": ("drift.com",), "hotjar": ("hotjar",),
    "segment": ("segment.com/analytics",), "zendesk": ("zendesk",),
}
COLLAB_TOOLS = ("slack", "microsoft teams", "notion", "confluence", "jira", "google workspace", "sharepoint",
                "asana", "monday.com", "clickup", "linear", "miro", "zoom", "gmail", "outlook", "salesforce",
                "hubspot", "zendesk", "intercom", "guru", "coda", "dropbox", "box.com")
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+'-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
SOCIAL = ("linkedin.com", "twitter.com", "x.com", "facebook.com", "instagram.com", "youtube.com", "github.com",
          "tiktok.com", "medium.com")


@dataclass
class PageData:
    url: str
    final_url: str
    kind: str = "home"
    title: str = ""
    meta_description: str = ""
    lang: str | None = None
    has_viewport: bool = False
    canonical: str | None = None
    og: dict[str, str] = field(default_factory=dict)
    headings: list[dict[str, str]] = field(default_factory=list)
    text: str = ""
    word_count: int = 0
    internal_links: list[dict[str, str]] = field(default_factory=list)
    external_links: list[str] = field(default_factory=list)
    nav_items: list[str] = field(default_factory=list)
    ctas: list[str] = field(default_factory=list)
    forms: int = 0
    form_fields: list[int] = field(default_factory=list)
    images: int = 0
    images_missing_alt: int = 0
    emails: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)
    social_links: list[str] = field(default_factory=list)
    json_ld: list[dict[str, Any]] = field(default_factory=list)
    tech: list[str] = field(default_factory=list)
    tools_mentioned: list[str] = field(default_factory=list)
    injection_flags: list[str] = field(default_factory=list)
    html_bytes: int = 0
    scripts: int = 0
    stylesheets: int = 0
    has_https: bool = False
    rendered: bool = False

    def to_json(self, text_limit: int = 15_000) -> dict[str, Any]:
        d = asdict(self)
        d["text"] = self.text[:text_limit]
        return d


def classify_link(url: str, text: str) -> str | None:
    path = urlparse(url).path.lower().strip("/")
    segs = path.split("/")
    first = segs[0] if segs else ""
    t = (text or "").lower().strip()
    for kind, keys in LINK_KINDS:
        if first in keys or any(path == k or path.startswith(k + "/") for k in keys):
            return kind
        if t and any(t == k.replace("-", " ") for k in keys):
            return kind
    return None


def extract(html: str, url: str, final_url: str | None = None) -> PageData:
    final_url = final_url or url
    soup = BeautifulSoup(html, "lxml")
    raw_lower = html.lower()
    pd = PageData(url=url, final_url=final_url, html_bytes=len(html.encode()), has_https=final_url.startswith("https://"))
    for c in soup.find_all(string=lambda s: isinstance(s, Comment)):
        c.extract()
    pd.title = clean_text(soup.title.get_text() if soup.title else "", 300)
    md = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
    pd.meta_description = clean_text(md.get("content", "") if md else "", 500)
    html_tag = soup.find("html")
    pd.lang = html_tag.get("lang") if html_tag else None
    pd.has_viewport = bool(soup.find("meta", attrs={"name": re.compile("^viewport$", re.I)}))
    can = soup.find("link", rel=lambda v: v and "canonical" in v)
    pd.canonical = can.get("href") if can else None
    for m in soup.find_all("meta", attrs={"property": re.compile("^og:")}):
        pd.og[m["property"][3:]] = clean_text(m.get("content", ""), 300)
    pd.scripts = len(soup.find_all("script"))
    pd.stylesheets = len(soup.find_all("link", rel=lambda v: v and "stylesheet" in v))
    for s in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(s.string or "")
            items = data if isinstance(data, list) else data.get("@graph", [data]) if isinstance(data, dict) else []
            for it in items[:10]:
                if isinstance(it, dict):
                    pd.json_ld.append({k: it[k] for k in list(it)[:25]})
        except (json.JSONDecodeError, AttributeError, TypeError):
            pass
    pd.tech = sorted(k for k, sigs in TECH_HINTS.items() if any(s in raw_lower for s in sigs))
    gen = soup.find("meta", attrs={"name": "generator"})
    if gen and gen.get("content"):
        pd.tech.append("generator:" + gen["content"][:40])

    imgs = soup.find_all("img")
    pd.images = len(imgs)
    pd.images_missing_alt = sum(1 for i in imgs if i.get("alt") is None)
    pd.forms = len(soup.find_all("form"))
    pd.form_fields = [len(f.find_all(["input", "select", "textarea"])) for f in soup.find_all("form")][:10]

    # hidden elements are dropped from text (common injection carrier) but counted
    for t in soup.find_all(style=re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden", re.I)):
        t.decompose()
    for t in soup.find_all(attrs={"aria-hidden": "true"}):
        t.decompose()
    for t in soup(["script", "style", "noscript", "template", "svg", "iframe"]):
        t.decompose()

    for h in soup.find_all(["h1", "h2", "h3"])[:60]:
        txt = clean_text(h.get_text(" "), 200)
        if txt:
            pd.headings.append({"level": h.name, "text": txt})
    nav = soup.find("nav") or soup.find("header")
    if nav:
        pd.nav_items = list(dict.fromkeys(clean_text(a.get_text(" "), 60) for a in nav.find_all("a")
                                          if clean_text(a.get_text(" "), 60)))[:30]
    base_domain = normalize_domain(final_url)
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith("mailto:"):
            e = normalize_email(href)
            if e:
                pd.emails.append(e)
            continue
        if href.startswith("tel:"):
            pd.phones.append(href[4:][:40])
            continue
        if href.startswith(("#", "javascript:")):
            continue
        absu = urljoin(final_url, href).split("#")[0]
        if absu in seen:
            continue
        seen.add(absu)
        text = clean_text(a.get_text(" "), 120)
        d = normalize_domain(absu)
        if d == base_domain:
            pd.internal_links.append({"url": absu, "text": text, "kind": classify_link(absu, text) or ""})
        elif d:
            if any(s in absu for s in SOCIAL):
                pd.social_links.append(absu)
            else:
                pd.external_links.append(absu)
        low = text.lower()
        if text and len(text) < 40 and any(w in low for w in CTA_WORDS):
            pd.ctas.append(text)
    for b in soup.find_all("button"):
        t = clean_text(b.get_text(" "), 40)
        if t and any(w in t.lower() for w in CTA_WORDS):
            pd.ctas.append(t)
    pd.ctas = list(dict.fromkeys(pd.ctas))[:20]
    pd.internal_links = pd.internal_links[:300]
    pd.external_links = pd.external_links[:100]
    pd.social_links = list(dict.fromkeys(pd.social_links))[:20]

    main = soup.find("main") or soup.body or soup
    pd.text = clean_text(main.get_text("\n"), 60_000)
    pd.word_count = len(pd.text.split())
    for e in EMAIL_RE.findall(pd.text):
        ne = normalize_email(e)
        if ne and not ne.endswith((".png", ".jpg", ".svg", ".webp")):
            pd.emails.append(ne)
    pd.emails = sorted(set(pd.emails))[:30]
    pd.phones = list(dict.fromkeys(pd.phones))[:10]
    low_text = pd.text.lower()
    pd.tools_mentioned = sorted(t for t in COLLAB_TOOLS if re.search(r"\b" + re.escape(t) + r"\b", low_text))
    pd.injection_flags = detect_injection(pd.text)
    return pd
