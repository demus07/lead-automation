"""Measurable, deterministic website checks. Each check is a *direct observation* with the page URL
as evidence. No subjective design judgements here — those come from the research agent and are
labelled as hypotheses."""
from __future__ import annotations

from typing import Any

from app.research.extractor import PageData


def _check(cid: str, area: str, label: str, passed: bool | None, value: Any, url: str, detail: str = "") -> dict:
    return {"id": cid, "area": area, "label": label, "passed": passed, "value": value, "evidence_url": url,
            "detail": detail, "category": "direct_observation"}


def audit_site(pages: list[PageData], fetch_meta: dict[str, Any]) -> dict[str, Any]:
    if not pages:
        return {"checks": [], "summary": {}, "pages_analyzed": 0}
    home = pages[0]
    u = home.final_url
    checks: list[dict] = []
    checks.append(_check("https", "security", "Served over HTTPS", home.has_https, home.has_https, u))
    checks.append(_check("title", "seo", "Homepage has a title (10–70 chars)", 10 <= len(home.title) <= 70,
                         home.title, u))
    checks.append(_check("meta_description", "seo", "Homepage meta description (50–160 chars)",
                         50 <= len(home.meta_description) <= 160, home.meta_description, u))
    h1s = [h["text"] for h in home.headings if h["level"] == "h1"]
    checks.append(_check("single_h1", "content", "Exactly one H1 on homepage", len(h1s) == 1, h1s[:3], u))
    checks.append(_check("viewport", "mobile", "Responsive viewport meta tag present", home.has_viewport,
                         home.has_viewport, u, "Indicates mobile-aware layout; not a full mobile usability test."))
    checks.append(_check("lang", "accessibility", "Document language declared", bool(home.lang), home.lang, u))
    total_imgs = sum(p.images for p in pages)
    missing = sum(p.images_missing_alt for p in pages)
    ratio = round(1 - missing / total_imgs, 2) if total_imgs else None
    checks.append(_check("img_alt", "accessibility", "Images have alt attributes (≥90%)",
                         None if ratio is None else ratio >= 0.9, ratio, u, f"{missing}/{total_imgs} missing alt"))
    checks.append(_check("primary_cta", "conversion", "Homepage has a clear call to action", bool(home.ctas),
                         home.ctas[:5], u))
    has_contact_path = any(p.kind == "contact" for p in pages) or any(
        lk.get("kind") == "contact" for lk in home.internal_links) or bool(home.forms)
    checks.append(_check("contact_path", "conversion", "Contact / demo path discoverable", has_contact_path,
                         has_contact_path, u))
    checks.append(_check("og_tags", "brand", "Open Graph tags for link previews", bool(home.og.get("title")),
                         home.og.get("title"), u))
    checks.append(_check("structured_data", "seo", "Organization structured data (JSON-LD)",
                         any("Organization" in str(j.get("@type", "")) for p in pages for j in p.json_ld), None, u))
    checks.append(_check("social_proof", "conversion", "Customer / case study page present",
                         any(p.kind == "customers" for p in pages) or any(
                             lk.get("kind") == "customers" for lk in home.internal_links), None, u))
    checks.append(_check("nav_size", "information_architecture", "Primary navigation has 3–9 items",
                         3 <= len(home.nav_items) <= 9 if home.nav_items else None, len(home.nav_items), u,
                         ", ".join(home.nav_items[:12])))
    checks.append(_check("content_depth", "content", "Homepage has substantive copy (≥250 words)",
                         home.word_count >= 250, home.word_count, u))
    weight_kb = round(home.html_bytes / 1024)
    checks.append(_check("html_weight", "performance", "Homepage HTML under 300 KB", weight_kb < 300, weight_kb, u,
                         "HTML document only; assets not measured."))
    checks.append(_check("script_count", "performance", "Fewer than 40 script tags", home.scripts < 40, home.scripts, u))
    if fetch_meta.get("home_elapsed_ms") is not None:
        ms = fetch_meta["home_elapsed_ms"]
        checks.append(_check("ttfb", "performance", "Homepage HTML fetched in under 1.5s", ms < 1500, ms, u,
                             "Single measurement from our crawler location."))
    big_forms = [n for p in pages for n in p.form_fields if n > 8]
    checks.append(_check("form_length", "conversion", "Forms are short (≤8 fields)", not big_forms if any(
        p.forms for p in pages) else None, big_forms, u))
    measurable = [c for c in checks if c["passed"] is not None]
    passed = sum(1 for c in measurable if c["passed"])
    by_area: dict[str, list[bool]] = {}
    for c in measurable:
        by_area.setdefault(c["area"], []).append(bool(c["passed"]))
    return {
        "checks": checks,
        "summary": {"passed": passed, "measured": len(measurable),
                    "score": round(100 * passed / len(measurable)) if measurable else None,
                    "by_area": {a: round(100 * sum(v) / len(v)) for a, v in by_area.items()}},
        "pages_analyzed": len(pages),
        "tech": sorted({t for p in pages for t in p.tech}),
        "tools_mentioned": sorted({t for p in pages for t in p.tools_mentioned}),
        "not_measured": ["visual consistency (requires visual review)", "real-device mobile usability",
                         "full accessibility audit (WCAG)", "page speed incl. assets (Core Web Vitals)"],
    }
