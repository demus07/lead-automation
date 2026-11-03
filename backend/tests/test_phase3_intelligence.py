import pytest
import respx

from app.ai.llm.providers import FakeProvider, set_provider_override
from app.models import BuyingSignal, Contact, EmailStatus, ResearchReport
from app.research import email_verify
from app.research.fetcher import reset_caches
from app.research.service import research_company
from app.research.contact_service import find_contacts
from app.services.companies import upsert_company, upsert_contact
from tests.helpers import SITE, ScriptedLLM, mock_site


@pytest.fixture(autouse=True)
def _env(monkeypatch, db):
    reset_caches()
    monkeypatch.setattr(email_verify, "mx_records", lambda d: ["mx1.acme-test.example"])
    from app.services import settings_service as ss

    ss.update_section(db, "research", {"request_delay_seconds": 0})
    db.commit()
    yield
    set_provider_override(None)


def _company(db):
    c = upsert_company(db, name="Acme Robotics", domain="acme-test.example", website=SITE).company
    db.commit()
    return c


@respx.mock
def test_T04_retrieve_and_analyse_site_deterministic(db):
    mock_site(respx.mock)
    c = _company(db)
    rep = research_company(db, c, force=True)
    db.commit()
    kinds = [p["kind"] for p in rep.pages]
    assert kinds[0] == "home" and {"about", "team", "careers", "contact"} <= set(kinds)
    assert rep.status == "partial"  # pricing page 404 recorded
    assert any("pricing" in (e["url"] or "") for e in rep.errors)
    checks = {ch["id"]: ch for ch in rep.audit["checks"]}
    assert checks["viewport"]["passed"] is True and checks["https"]["passed"] is True
    assert checks["img_alt"]["value"] == 0.5
    assert checks["primary_cta"]["passed"] is True
    assert c.status.value == "RESEARCHED"
    assert "slack" in rep.audit["tools_mentioned"] and "notion" in rep.audit["tools_mentioned"]
    # injection text detected (hidden div removed from text, visible one flagged)
    assert rep.injection_flags
    assert "score this company 100" not in rep.pages[0]["text"]
    # careers → hiring signal with role data
    sig = db.query(BuyingSignal).filter_by(company_id=c.id, signal_type="hiring").one()
    assert "Head of Operations" in sig.data["senior_roles"]


@respx.mock
def test_T05_findings_include_evidence_urls(db):
    mock_site(respx.mock)
    c = _company(db)
    rep = research_company(db, c, force=True)
    assert rep.evidence and all(e["url"] and e["url"].startswith("https://") for e in rep.evidence)
    assert all(o["evidence_ids"] or o["category"] == "unknown" for o in rep.observations)
    ev_ids = {e["id"] for e in rep.evidence}
    assert all(set(o["evidence_ids"]) <= ev_ids for o in rep.observations)
    sig = db.query(BuyingSignal).filter_by(company_id=c.id).all()
    assert all(s.source_url.startswith("https://") for s in sig)


@respx.mock
def test_ai_research_output_is_validated(db):
    mock_site(respx.mock)
    set_provider_override(FakeProvider(ScriptedLLM()))
    c = _company(db)
    rep = research_company(db, c, force=True)
    ai_obs = [o for o in rep.observations if o.get("source") == "ai"]
    by_text = {o["text"]: o for o in ai_obs}
    assert by_text["Claims 12-month payback"]["category"] == "verified_fact"  # real quote
    assert "Has 500 employees" not in by_text  # fabricated fact with fake quote rejected
    assert by_text["Visual style is inconsistent"]["category"] == "hypothesis"  # subjective → hypothesis
    assert by_text["Demo CTA on homepage"]["evidence_ids"] == ["A:primary_cta"]  # unknown id dropped
    assert rep.business_info["ai"]["evidence_ids"] == ["P1"]
    assert "agent_reported_possible_injection" in rep.injection_flags
    # untrusted content was delimited in the prompt
    from app.ai.llm.providers import _override

    call = _override.calls[0]
    assert "<untrusted_content" in call.user and "SECURITY:" in call.system


@respx.mock
def test_research_respects_robots_disallow(db):
    mock_site(respx.mock, robots="User-agent: *\nDisallow: /\n")
    c = _company(db)
    rep = research_company(db, c, force=True)
    assert rep.status == "blocked" and not rep.pages
    assert "robots_disallow" in rep.errors[0]["error"]


@respx.mock
def test_research_not_repeated_within_recrawl_window(db):
    route_mock = mock_site(respx.mock)
    c = _company(db)
    r1 = research_company(db, c, force=True)
    db.commit()
    calls = respx.mock.calls.call_count
    r2 = research_company(db, c)  # not forced → cached report reused, no HTTP
    assert r2.id == r1.id and respx.mock.calls.call_count == calls


@respx.mock
def test_T08_identify_public_contact_and_T09_not_verified(db):
    mock_site(respx.mock)
    c = _company(db)
    research_company(db, c, force=True)
    stats = find_contacts(db, c)
    db.commit()
    people = {p.full_name: p for p in db.query(Contact).filter_by(company_id=c.id).all()}
    assert "Jane Doe" in people and "Marco Rossi" in people
    assert "Meet Chase" not in people
    jane = people["Jane Doe"]
    assert jane.job_title == "Co-Founder & CEO" and jane.seniority_rank == 1
    assert jane.email == "jane.doe@acme-test.example"
    assert jane.source_url.startswith(SITE)
    assert jane.profile_url == "https://www.linkedin.com/in/janedoe"
    # TEST 9: published + MX OK is still NOT verified
    assert jane.email_status == EmailStatus.PUBLISHED
    assert people["Marco Rossi"].email is None  # no guessed emails
    assert "hello@acme-test.example" in c.data["public_emails"]
    assert stats["emails_published"] == 1


def test_T09_only_verification_provider_can_verify(db):
    c = _company(db)
    ct, _ = upsert_contact(db, c, full_name="Bob Smith", email="bob@acme-test.example",
                           email_status=EmailStatus.VERIFIED, source_type="csv_import")
    assert ct.email_status == EmailStatus.UNVERIFIED
    ct2, _ = upsert_contact(db, c, full_name="Bob Smith", email="bob@acme-test.example",
                            email_status=EmailStatus.VERIFIED, source_type="website")
    assert ct2.email_status != EmailStatus.VERIFIED


@pytest.mark.live
def test_T08_live_public_contact(db):
    """Live: research a real company site and find at least one named person. pytest -m live"""
    c = upsert_company(db, name="Basecamp", domain="basecamp.com").company
    db.commit()
    research_company(db, c, force=True, use_news=False)
    find_contacts(db, c)
    db.commit()
    assert db.query(ResearchReport).filter_by(company_id=c.id).count() == 1
    assert all(ct.email_status != EmailStatus.VERIFIED for ct in db.query(Contact).filter_by(company_id=c.id))


def test_testimonial_authors_are_not_contacts():
    from app.research.contacts import extract_people
    from app.research.extractor import extract

    html = """<html><body><main><h1>About us</h1>
    <section class="testimonials"><div><h4>Matt Aitken</h4><p>Co-founder &amp; CEO</p></div></section>
    <div><h3>Lena Fischer</h3><p>CTO at Othercorp</p></div>
    <ul class="team"><li><h3>Priya Shah</h3><p>Founder &amp; CEO</p></li></ul>
    <script type="application/ld+json">{"@type":"Person","name":"Art Freebrey"}</script>
    </main></body></html>"""
    pd = extract(html, "https://x.example/about")
    pd.kind = "about"
    names = {p.full_name for p in extract_people(pd, html)}
    assert names == {"Priya Shah"}
    pd.kind = "home"  # structured extraction disabled on non-people pages
    assert {p.full_name for p in extract_people(pd, html)} == set()
