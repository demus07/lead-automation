"""Site / company intelligence: read a few pages in a real browser, run checks, and turn failures into
plain-English problems for one of the two services:

* website — the site itself is costing them customers (Digital Experiences)
* systems — signs their team's knowledge and workflows are getting heavy (Intelligent Systems)

Each problem has a weight (0–10 scale, summed into the score). Only `hook` problems are good enough to
mention to a prospect; hygiene like a missing meta description is recorded but never pitched.
"""
import re
from datetime import datetime
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .fetch import client, get_page
from .render import render

# Internal pages worth visiting, by the words in their link.
PAGE_KINDS = {
    "about": ("about", "company", "who-we-are", "our-story", "meet"),
    "team": ("team", "people", "leadership", "founders", "staff"),
    "contact": ("contact", "get-in-touch", "talk-to", "enquir", "book", "demo"),
    "careers": ("careers", "jobs", "join-us", "hiring", "work-with-us", "vacancies"),
}
PLATFORMS = {"wix.com": "Wix", "wixstatic": "Wix", "squarespace": "Squarespace", "godaddy": "GoDaddy's site builder",
             "weebly": "Weebly", "jimdo": "Jimdo"}
PLACEHOLDER = re.compile(r"\b(lorem ipsum|coming soon|under construction|sample page|hello world!|website is being)\b", re.I)
BLOCKED = re.compile(r"(just a moment|attention required|access denied|verify you are human|forbidden|not found)", re.I)
CTA_WORDS = ("book", "contact", "call", "enquir", "quote", "get started", "get in touch", "demo", "appointment",
             "reserve", "buy", "shop", "order", "request", "sign up", "try", "talk to", "start")
PROOF_WORDS = re.compile(r"\b(testimonial|reviews?|case stud|what our (clients|customers|patients)|trusted by|"
                         r"happy (clients|customers)|success stor)", re.I)
# Matched against short lines on a careers page (job titles), never against running text.
OPS_TITLE = re.compile(r"\b(operations (manager|lead|coordinator|associate)|head of operations|chief of staff|"
                       r"executive assistant|office manager|knowledge manager|(program|project) manager|"
                       r"customer (success|support) (manager|specialist|associate|lead)|support (specialist|agent))\b", re.I)
REMOTE = re.compile(r"[^.\n]{0,80}\b(remote[- ]first|fully remote|distributed team|across time zones|offices in)\b[^.\n]{0,80}", re.I)
JOB_TITLE = re.compile(r"\b(manager|engineer|developer|designer|specialist|associate|lead|director|analyst|coordinator)\b", re.I)


def parse(html: str, url: str, ms: int, kb: int) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    links = [(a.get_text(" ", strip=True), urljoin(url, a["href"])) for a in soup.find_all("a", href=True)]
    table_layout = len(soup.find_all("table")) >= 3 and not soup.find(["nav", "main", "section", "article", "header"])
    old_tags = len(soup.find_all(["font", "center", "marquee", "frameset"]))
    jquery_old = bool(re.search(r"jquery[-.]?(1\.\d+|1\.)", html, re.I))
    for t in soup(["script", "style", "noscript", "svg"]):
        t.decompose()
    text = soup.get_text("\n", strip=True)
    meta = lambda name: (soup.find("meta", attrs={"name": name}) or soup.find("meta", attrs={"property": name}) or {})
    imgs = soup.find_all("img")
    years = [int(y) for y in re.findall(r"(?:©|&copy;|copyright)\s*(?:\d{4}\s*[-–]\s*)?(\d{4})", html, re.I)]
    return {
        "url": url, "ms": ms, "kb": kb, "text": text, "links": links, "html": html,
        "title": (soup.title.get_text(strip=True) if soup.title else ""),
        "description": meta("description").get("content", "").strip(),
        "og_title": meta("og:title").get("content", ""),
        "h1": [h.get_text(" ", strip=True) for h in soup.find_all("h1")],
        "viewport": bool(soup.find("meta", attrs={"name": "viewport"})),
        "imgs": len(imgs),
        "imgs_no_alt": sum(1 for i in imgs if not i.get("alt")),
        "words": len(text.split()),
        "forms": len(soup.find_all("form")),
        "copyright_year": max(years) if years else None,
        "platform": next((v for k, v in PLATFORMS.items() if k in html.lower()), None),
        "dated_markup": table_layout or old_tags >= 3 or jquery_old,
        "tel_link": any(u.startswith("tel:") for _, u in links),
    }


def _kind(label: str, url: str) -> str | None:
    path = urlparse(url).path.lower()
    for kind, words in PAGE_KINDS.items():
        if any(w in path or w in label.lower() for w in words):
            return kind
    return None


def crawl(website: str, max_pages: int = 6) -> list[dict]:
    """Homepage (rendered at phone size) plus up to one page of each useful kind on the same site."""
    with client() as http:
        raw = get_page(http, website)
        if not raw:
            return []
        shown = render(raw["final_url"])
        home = {**parse((shown or raw)["html"], raw["final_url"], (shown or raw)["ms"], round(raw["bytes"] / 1024)),
                "kind": "home", "rendered": shown}
        pages, host = [home], urlparse(home["url"]).hostname
        wanted = {}
        for label, url in home["links"]:
            if urlparse(url).hostname == host and (k := _kind(label, url)) and k not in wanted:
                wanted[k] = url.split("#")[0]
        for kind, url in list(wanted.items())[: max_pages - 1]:
            p = get_page(http, url)
            if not p:
                continue
            parsed = parse(p["html"], p["final_url"], p["ms"], round(p["bytes"] / 1024))
            if parsed["words"] < 50 and (r := render(p["final_url"])):  # a JavaScript page
                parsed = parse(r["html"], p["final_url"], r["ms"], parsed["kb"])
            pages.append({**parsed, "kind": kind})
        return pages


def readable(pages: list[dict]) -> bool:
    """False when we got a bot wall or an empty shell: any 'problem' we found would be our failure, not theirs."""
    home = pages[0]
    return home["words"] >= 25 and not (BLOCKED.search(home["title"]) and home["words"] < 120)


def analyse(pages: list[dict], signals: list[str]) -> dict:
    """Checks → problems → two scores → one recommendation."""
    home, u = pages[0], pages[0]["url"]
    by_kind = {p["kind"]: p for p in pages}
    shown = home.get("rendered")
    all_text = "\n".join(p["text"] for p in pages)
    problems = []

    def problem(service, text, weight, url=u, hook=True):
        problems.append({"service": service, "problem": text, "url": url, "weight": weight, "hook": hook})

    # --- website: what a customer actually runs into
    if not u.startswith("https://"):
        problem("website", "The site isn't on HTTPS, so browsers label it “Not secure”.", 3)
    if PLACEHOLDER.search(home["text"]):
        problem("website", f"The homepage still shows “{PLACEHOLDER.search(home['text']).group(0)}”.", 4)
    if shown and shown["overflow"] > 20:
        problem("website", "On a phone-sized screen the homepage is wider than the display, so it scrolls sideways.", 3)
    elif not home["viewport"]:
        problem("website", "The homepage isn't set up for phones (no mobile viewport), so it shows as a shrunken desktop page.", 3)
    if shown and shown["small_text"] >= 3:
        problem("website", "Body text on the homepage renders too small to read comfortably on a phone.", 1)
    if shown and shown["ms"] > 6000:
        problem("website", f"The homepage took {shown['ms'] / 1000:.0f} seconds to load at phone size when we tried it.", 2)
    if shown and not any(any(w in a for w in CTA_WORDS) for a in shown["fold_actions"]):
        problem("website", "On a phone, nothing on the first screen tells a visitor what to do next (no book, call or contact button).", 3)
    contact_link = any(l.startswith("mailto:") or l.startswith("tel:")
                       or any(b in l for b in ("calendly.com", "cal.com", "typeform.com")) for _, l in home["links"])
    if not ("contact" in by_kind or home["forms"] or contact_link):
        problem("website", "There's no clear way to get in touch from the homepage.", 3)
    year = home["copyright_year"]
    if year and year <= datetime.now().year - 2:
        problem("website", f"The footer still says © {year}, which makes the business look less active than it is.", 2)
    if home["platform"]:
        problem("website", f"The site is built on {home['platform']}, so it shares its look with many others.", 2)
    if home["dated_markup"]:
        problem("website", "The site is built on old web technology, which usually shows in how dated it feels.", 2)
    if not PROOF_WORDS.search(all_text):
        problem("website", "None of the pages we read show reviews, testimonials or case studies.", 2)
    if home["words"] < 80:
        problem("website", f"The homepage has only about {home['words']} words, so it says little about what they do.", 2)

    # Hygiene: recorded, slightly scored, never mentioned in outreach.
    if not 50 <= len(home["description"]) <= 160:
        problem("website", "No usable meta description for search results.", 0.5, hook=False)
    if not home["og_title"]:
        problem("website", "No Open Graph tags, so shared links have no preview card.", 0.5, hook=False)
    if len(home["h1"]) != 1:
        problem("website", f"Homepage has {len(home['h1'])} H1 headings.", 0.5, hook=False)

    # --- systems: only things stated on their pages or in the source listing
    careers = by_kind.get("careers")
    if careers:
        lines = [ln.strip() for ln in careers["text"].split("\n") if 2 <= len(ln.split()) <= 8]
        titles = sorted({ln for ln in lines if OPS_TITLE.search(ln)})
        if titles:
            problem("systems", f"They're hiring for: {'; '.join(titles[:3])}.", 4, careers["url"])
        openings = sum(1 for ln in lines if JOB_TITLE.search(ln))
        if openings >= 5:
            problem("systems", f"Their careers page lists around {openings} open roles, so onboarding is a live concern.", 2, careers["url"])
    for p in pages:
        if m := REMOTE.search(p["text"]):
            problem("systems", f"Their site says: “{m.group(0).strip()}”.", 2, p["url"])
            break
    hiring = next((s for s in signals if s.lower().startswith("hiring")), None)
    if hiring:
        problem("systems", f"They're publicly hiring ({hiring}).", 2)
    team = next((s for s in signals if s.startswith("Team of ")), None)
    if team and int(team.split()[-1]) >= 15:
        problem("systems", f"{team} people, large enough that information stops travelling by itself.", 2)

    scores = {svc: min(100, round(10 * sum(p["weight"] for p in problems if p["service"] == svc)))
              for svc in ("website", "systems")}
    return {
        "pages": [{"kind": p["kind"], "url": p["url"], "title": p["title"]} for p in pages],
        "problems": sorted(problems, key=lambda p: -p["weight"]),
        "scores": scores,
        "recommended": max(scores, key=scores.get),
        "summary": (home["description"] or home["title"])[:300],
        # What the draft is allowed to draw on. Untrusted: it's written by the prospect.
        "excerpt": "\n".join(p["text"][:1800] for p in pages if p["kind"] in ("home", "about", "team"))[:4000],
    }
