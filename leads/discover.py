"""Finding companies from free, key-less public sources.

* OpenStreetMap — local and small businesses by category and city, with their website (Overpass API).
* YC directory — public JSON mirror (yc-oss.github.io): website, one-liner, team size, hiring flag.
* Hacker News "Who is hiring?" — official Algolia HN API: companies hiring this month.
"""
import html
import random
import re
import time

from . import db
from .fetch import client, normalize_domain

YC_URL = "https://yc-oss.github.io/api/companies/all.json"
HN_API = "https://hn.algolia.com/api/v1"
NOMINATIM = "https://nominatim.openstreetmap.org/search"
OVERPASS = "https://overpass-api.de/api/interpreter"
_yc_cache = {"at": 0.0, "data": []}

# Links in HN posts that point at job boards, not the company itself.
JOB_BOARDS = {"greenhouse.io", "lever.co", "jobs.lever.co", "ashbyhq.com", "jobs.ashbyhq.com", "workable.com",
              "apply.workable.com", "ycombinator.com", "workatastartup.com", "bamboohr.com", "notion.site",
              "google.com", "docs.google.com", "forms.gle", "linkedin.com", "github.com", "wellfound.com",
              "calendly.com", "teamtailor.com", "smartrecruiters.com", "recruitee.com", "rippling.com"}


def _matches(text: str, keywords: list[str]) -> bool:
    text = text.lower()
    return not keywords or any(k.lower() in text for k in keywords)


# Friendly names for the Settings page. Any raw OSM tag such as "office=accountant" also works.
CATEGORIES = {
    "dentists": "amenity=dentist", "doctors": "amenity=doctors", "clinics": "amenity=clinic",
    "physiotherapists": "healthcare=physiotherapist", "vets": "amenity=veterinary",
    "lawyers": "office=lawyer", "accountants": "office=accountant", "estate agents": "office=estate_agent",
    "architects": "office=architect", "financial advisors": "office=financial_advisor",
    "insurance": "office=insurance", "consultants": "office=consulting", "it companies": "office=it",
    "hotels": "tourism=hotel", "restaurants": "amenity=restaurant", "cafes": "amenity=cafe",
    "gyms": "leisure=fitness_centre", "beauty salons": "shop=beauty", "hairdressers": "shop=hairdresser",
    "schools": "amenity=school", "car repair": "shop=car_repair", "florists": "shop=florist",
    "furniture shops": "shop=furniture", "jewellers": "shop=jewelry",
}
# Not a site of their own, so there's nothing to research.
NOT_A_WEBSITE = ("facebook.com", "instagram.com", "linktr.ee", "yell.com", "google.com", "yelp.com", "wa.me",
                 "nhs.uk", "gov.uk")


def _osm_area(http, city: str) -> int | None:
    r = http.get(NOMINATIM, params={"q": city, "format": "json", "limit": 5})
    time.sleep(1)  # Nominatim's usage policy: one request per second
    rel = next((p for p in r.json() if p.get("osm_type") == "relation"), None)
    return 3600000000 + rel["osm_id"] if rel else None


def from_osm(s: dict, limit: int) -> list[dict]:
    cities = db.csv_setting(s, "cities")
    tags = [(c, CATEGORIES.get(c.lower(), c)) for c in db.csv_setting(s, "categories")]
    out, seen = [], set()
    with client(90) as http:
        for city in cities:
            area = _osm_area(http, city)
            if not area:
                continue
            for label, tag in tags:
                if tag.count("=") != 1:
                    continue
                key, value = tag.split("=")
                query = (f'[out:json][timeout:60];area({area})->.a;'
                         f'(nwr["{key}"="{value}"]["website"](area.a);nwr["{key}"="{value}"]["contact:website"](area.a););'
                         'out tags center 500;')
                r = None
                for attempt in range(3):
                    r = http.post(OVERPASS, data={"data": query})
                    if r.status_code == 200:
                        break
                    time.sleep(15 * (attempt + 1))  # busy server: wait and try again
                if r.status_code != 200:
                    raise RuntimeError(f"OpenStreetMap is busy (HTTP {r.status_code}); try again later")
                for e in r.json()["elements"]:
                    t = e.get("tags", {})
                    website = t.get("website") or t.get("contact:website")
                    domain = normalize_domain(website)
                    # A `brand` tag means a chain, whose site is run by a head office.
                    if (not domain or not t.get("name") or t.get("brand") or t.get("brand:wikidata") or domain in seen
                            or any(domain == d or domain.endswith("." + d) for d in NOT_A_WEBSITE)):
                        continue
                    seen.add(domain)
                    if "://" not in website:
                        website = "https://" + website
                    out.append(dict(name=t["name"], domain=domain, website=website, location=city,
                                    description=label, source="OpenStreetMap", email=t.get("email") or t.get("contact:email"),
                                    source_url=f"https://www.openstreetmap.org/{e['type']}/{e['id']}", signals=[]))
            time.sleep(1)
    random.shuffle(out)  # so each run isn't just the same corner of the map
    return out[:limit]


def from_yc(s: dict, limit: int) -> list[dict]:
    keywords, locations = db.csv_setting(s, "keywords"), db.csv_setting(s, "locations")
    min_team, max_team = int(s.get("min_team") or 0), int(s.get("max_team") or 1_000_000)
    if time.time() - _yc_cache["at"] > 6 * 3600:
        with client(60) as http:
            _yc_cache.update(at=time.time(), data=http.get(YC_URL).json())
    out = []
    # Most recent batches first: they are the ones still shaping their site and tooling.
    for c in sorted(_yc_cache["data"], key=lambda c: -int((re.findall(r"\d{4}", c.get("batch") or "") or [0])[0])):
        if c.get("status") != "Active" or not c.get("website"):
            continue
        if not min_team <= (c.get("team_size") or 0) <= max_team:
            continue
        hay = " ".join([c.get("industry") or "", c.get("subindustry") or "", " ".join(c.get("tags") or []),
                        c.get("one_liner") or ""])
        if not _matches(hay, keywords) or not _matches(c.get("all_locations") or "", locations):
            continue
        domain = normalize_domain(c["website"])
        if not domain:
            continue
        signals = [f"YC {c['batch']}"] if c.get("batch") else []
        if c.get("isHiring"):
            signals.append("Hiring (YC profile)")
        if c.get("team_size"):
            signals.append(f"Team of {c['team_size']}")
        out.append(dict(name=c["name"], domain=domain, website=c["website"], description=c.get("one_liner"),
                        location=c.get("all_locations"), source="YC directory", source_url=c.get("url"),
                        signals=signals))
        if len(out) >= limit:
            break
    return out


def from_hn(s: dict, limit: int) -> list[dict]:
    keywords, locations = db.csv_setting(s, "keywords"), db.csv_setting(s, "locations")
    with client(30) as http:
        threads = http.get(f"{HN_API}/search_by_date", params={"tags": "story,author_whoishiring"}).json()["hits"]
        thread = next((t for t in threads if "who is hiring" in (t.get("title") or "").lower()), None)
        if not thread:
            return []
        out, seen = [], set()
        for page in range(5):
            hits = http.get(f"{HN_API}/search", params={"tags": f"comment,story_{thread['objectID']}",
                                                       "hitsPerPage": 100, "page": page}).json()["hits"]
            if not hits:
                break
            for h in hits:
                if h.get("parent_id") != int(thread["objectID"]):
                    continue  # replies to posts, not posts
                raw = html.unescape(h.get("comment_text") or "")
                text = re.sub(r"<[^>]+>", "\n", raw)
                first = text.strip().split("\n")[0][:200]
                if not _matches(text, keywords) or not (_matches(text, locations) or "remote" in text.lower()):
                    continue
                domain = next((d for d in (normalize_domain(u) for u in re.findall(r"https?://[^\s<>\"')]+", raw))
                               if d and d not in JOB_BOARDS and not any(d.endswith("." + j) for j in JOB_BOARDS)),
                              None)
                name = re.sub(r"\(.*?\)", "", first.split("|")[0]).strip()
                if not domain or not name or len(name) > 60 or domain in seen:
                    continue
                seen.add(domain)
                out.append(dict(name=name, domain=domain, website=f"https://{domain}", description=first,
                                location=(first.split("|")[1].strip() if "|" in first else None),
                                source="HN Who is hiring",
                                source_url=f"https://news.ycombinator.com/item?id={h['objectID']}",
                                signals=[f"Hiring ({thread['title']})"]))
                if len(out) >= limit:
                    return out
    return out


SOURCES = {"osm": from_osm, "yc": from_yc, "hn": from_hn}


def discover(limit: int) -> list[int]:
    """Pull new companies from the configured sources until `limit` new leads are saved."""
    s = db.settings()
    new_ids = []
    for key in db.csv_setting(s, "sources"):
        fn = SOURCES.get(key)
        if not fn:
            continue
        # Ask for more than we need: many will already be known.
        for c in fn(s, limit * 5):
            lead_id = db.add_lead(**c)
            if lead_id:
                new_ids.append(lead_id)
            if len(new_ids) >= limit:
                return new_ids
    return new_ids


def add_manual(urls: str) -> int:
    added = 0
    for u in re.split(r"[\s,]+", urls):
        domain = normalize_domain(u)
        if domain and db.add_lead(domain.split(".")[0].title(), domain, f"https://{domain}", source="Manual"):
            added += 1
    return added
