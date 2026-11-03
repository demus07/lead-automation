"""Decision-maker extraction from official company pages.

Sources, in order of confidence: schema.org Person JSON-LD (0.85) → structured team-page markup
(0.7) → "Name, Title" text lines (0.6) → optional LLM extraction (0.55). Every candidate's name must
appear verbatim in the page text, otherwise it is discarded (prevents invented people).

Emails are only attached to a person when the address is *published on the official site* and its
local part matches that person's name. Such emails get status ``published`` — never ``verified``.
Generic inboxes (info@, hello@ …) are stored at company level, not attributed to people.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

from app.research.extractor import PageData
from app.services.companies import seniority_rank

ROLE_WORDS = re.compile(
    r"\b(founder|co-?founder|ceo|cto|coo|cio|cmo|cfo|cpo|chief|president|managing director|director|head of|"
    r"vp|vice president|partner|owner|lead|manager|principal|chair(man|woman|person)?)\b", re.I)
NAME_RE = re.compile(r"^[A-ZÀ-Ý][a-zà-ÿ'’\-]+(?:\s+(?:[A-ZÀ-Ý]\.|[A-ZÀ-Ý][a-zà-ÿ'’\-]+|van|de|der|von|da|di|le|la)){1,3}$")
GENERIC_LOCALS = {"info", "hello", "contact", "support", "sales", "team", "admin", "office", "press", "media",
                  "careers", "jobs", "hr", "help", "enquiries", "inquiries", "billing", "privacy", "legal",
                  "marketing", "partners", "hi", "mail", "general", "service", "noreply", "no-reply", "security"}
NOT_NAMES = {"Our Team", "Meet The Team", "Read More", "Learn More", "Contact Us", "About Us", "Get Started",
             "Privacy Policy", "Terms Of Service", "Case Studies", "Join Us", "Book Demo", "Sign Up", "Log In"}


PEOPLE_PAGE_KINDS = {"team", "about", "contact"}
TESTIMONIAL_HINT = re.compile(r"testimonial|quote|review|customer|client|logo|case-stud|endorse|praise|love", re.I)


def _other_company(title: str) -> bool:
    """'CTO at Acme', 'Founder @ Foo', 'CEO, Foo Inc' → title refers to a different employer."""
    return bool(re.search(r"\b(at|@)\s+[A-Z0-9]", title) or re.search(r",\s*[A-Z][\w&.-]+(\s+[A-Z][\w&.-]+)*$", title)
                and not re.search(r",\s*(Inc|Ltd|LLC|GmbH)\.?$", title))


def _in_testimonial(el) -> bool:
    for parent in [el, *el.parents][:7]:
        if getattr(parent, "name", None) in ("blockquote", "figure", "q"):
            return True
        attrs = " ".join([*(parent.get("class") or []), parent.get("id") or ""]) if hasattr(parent, "get") else ""
        if attrs and TESTIMONIAL_HINT.search(attrs):
            return True
    return False


@dataclass
class PersonCandidate:
    full_name: str
    job_title: str | None
    source_url: str
    method: str
    confidence: float
    email: str | None = None
    profile_url: str | None = None


LEAD_STOPWORDS = {"meet", "hi", "hello", "about", "our", "the", "contact", "with", "from", "ask", "by", "dear",
                  "join", "team", "welcome", "say", "call", "email", "follow", "read", "view", "see", "visit"}


def _is_name(s: str) -> bool:
    s = s.strip()
    if s.split()[0].lower() in LEAD_STOPWORDS if s else True:
        return False
    return bool(NAME_RE.match(s)) and s.title() not in NOT_NAMES and len(s) <= 40 and not ROLE_WORDS.search(s)


def _title_ok(s: str | None) -> bool:
    return bool(s) and len(s) <= 120 and bool(ROLE_WORDS.search(s))


def extract_people(page: PageData, html: str) -> list[PersonCandidate]:
    out: dict[str, PersonCandidate] = {}

    def add(c: PersonCandidate) -> None:
        key = c.full_name.lower()
        if c.full_name not in page.text and c.full_name not in html:
            return
        prev = out.get(key)
        if prev is None or c.confidence > prev.confidence:
            out[key] = c

    for j in page.json_ld:
        org_people = []
        if "Organization" in str(j.get("@type", "")):
            for key in ("founder", "founders", "employee", "employees"):
                v = j.get(key)
                org_people += [x for x in (v if isinstance(v, list) else [v]) if isinstance(x, dict)]
        standalone = [j] if "Person" in str(j.get("@type", "")) else []
        for it, from_org in [(x, True) for x in org_people] + [(x, False) for x in standalone]:
            if "Person" not in str(it.get("@type", "Person")) or not isinstance(it.get("name"), str):
                continue
            if not _is_name(it["name"]):
                continue
            title = it.get("jobTitle") if isinstance(it.get("jobTitle"), str) else None
            if not from_org and not _title_ok(title):
                continue  # a bare Person (e.g. review/article author) is not evidence of employment
            if title and _other_company(title):
                continue
            same = it.get("sameAs")
            profile = next((s for s in (same if isinstance(same, list) else [same]) if isinstance(s, str)
                            and "linkedin.com/in/" in s), None)
            add(PersonCandidate(it["name"].strip(), title, page.final_url, "json_ld", 0.85, profile_url=profile))

    if page.kind not in PEOPLE_PAGE_KINDS:
        people = list(out.values())
        attach_emails(people, page.emails)
        return sorted(people, key=lambda p: (seniority_rank(p.job_title), -p.confidence))

    soup = BeautifulSoup(html, "lxml")
    for t in soup(["script", "style", "noscript"]):
        t.decompose()
    for el in soup.find_all(["h2", "h3", "h4", "h5", "strong", "b", "p", "span", "div"]):
        if el.find(["h2", "h3", "h4", "h5", "p", "div"]):
            continue  # leaf-ish elements only
        name = el.get_text(" ", strip=True)
        if not _is_name(name):
            continue
        title = None
        for sib in list(el.find_next_siblings(limit=3)) + ([el.parent.find_next_sibling()] if el.parent else []):
            if sib is None:
                continue
            txt = sib.get_text(" ", strip=True)
            if _title_ok(txt):
                title = txt
                break
        if title and (_in_testimonial(el) or _other_company(title)):
            continue
        if title:
            title = re.sub(r"^(our|the|is|as)\s+", "", title, flags=re.I)
            container = el.find_parent(["li", "article", "div", "section"])
            profile = None
            if container:
                a = container.find("a", href=re.compile(r"linkedin\.com/in/"))
                profile = a["href"] if a else None
            add(PersonCandidate(name, title[:200], page.final_url, "structured", 0.7, profile_url=profile))

    for line in page.text.split("\n"):
        line = line.strip()
        m = re.match(r"^([A-ZÀ-Ý][\w'’\-]+(?: [A-ZÀ-Ý][\w'’\-]+){1,3})\s*[,–—|-]\s*(.{3,80})$", line)
        if m and _is_name(m.group(1)) and _title_ok(m.group(2)) and not _other_company(m.group(2)):
            add(PersonCandidate(m.group(1), m.group(2).strip(), page.final_url, "text_pattern", 0.6))

    people = list(out.values())
    attach_emails(people, page.emails)
    return sorted(people, key=lambda p: (seniority_rank(p.job_title), -p.confidence))


def email_matches_name(email: str, full_name: str) -> bool:
    local = email.split("@")[0].lower()
    parts = [re.sub(r"[^a-z]", "", p.lower()) for p in full_name.split() if p]
    if len(parts) < 2:
        return False
    first, last = parts[0], parts[-1]
    patterns = {first, f"{first}.{last}", f"{first}{last}", f"{first[0]}{last}", f"{first[0]}.{last}",
                f"{first}_{last}", f"{first}-{last}", f"{last}.{first}", f"{first}{last[0]}"}
    return local in patterns


def attach_emails(people: list[PersonCandidate], emails: list[str]) -> None:
    for e in emails:
        if e.split("@")[0] in GENERIC_LOCALS:
            continue
        matches = [p for p in people if email_matches_name(e, p.full_name)]
        if len(matches) == 1 and not matches[0].email:
            matches[0].email = e


def generic_emails(emails: list[str]) -> list[str]:
    return sorted({e for e in emails if e.split("@")[0] in GENERIC_LOCALS})
