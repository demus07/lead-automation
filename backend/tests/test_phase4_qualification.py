import pytest
import respx

from app.ai.llm.providers import FakeProvider, set_provider_override
from app.models import Campaign, LeadScore, LeadStatus
from app.research import email_verify
from app.research.fetcher import reset_caches
from app.research.service import research_company
from app.services.scoring import ServiceScore, recommend, score_company
from app.services.companies import upsert_company
from tests.helpers import SITE, ScriptedLLM, mock_site

SCFG = {"qualification_threshold": 60, "service_margin": 10, "min_confidence": 0.35}


@pytest.fixture(autouse=True)
def _env(monkeypatch, db):
    reset_caches()
    monkeypatch.setattr(email_verify, "mx_records", lambda d: ["mx"])
    from app.services import settings_service as ss

    ss.update_section(db, "research", {"request_delay_seconds": 0})
    db.commit()
    yield
    set_provider_override(None)


def _researched(db, campaign_id=None):
    c = upsert_company(db, name="Acme Robotics", domain="acme-test.example", website=SITE, campaign_id=campaign_id,
                       fields={"size_range": "51-200"}).company
    db.commit()
    research_company(db, c, force=True)
    db.commit()
    return c


@respx.mock
def test_T06_separate_scores_with_llm(db):
    mock_site(respx.mock)
    set_provider_override(FakeProvider(ScriptedLLM()))
    c = _researched(db)
    opp = score_company(db, c)
    db.commit()
    assert 0 <= opp.website_score <= 100 and 0 <= opp.brain_score <= 100
    assert opp.website_score != opp.brain_score
    rows = db.query(LeadScore).filter_by(company_id=c.id).all()
    assert {r.service for r in rows} == {"website", "company_brain"} and all(r.method == "llm" for r in rows)
    web = next(r for r in rows if r.service == "website")
    growth = next(f for f in web.factors if f["factor"] == "growth_signals")
    assert growth["rating"] is None and "discarded" in growth["validation"]  # hallucinated evidence id
    ux = next(f for f in web.factors if f["factor"] == "ux")
    assert ux["rating"] is None
    assert all(e["url"] for e in opp.evidence)


@respx.mock
def test_T07_recommends_correct_service(db):
    mock_site(respx.mock)
    set_provider_override(FakeProvider(ScriptedLLM()))
    c = _researched(db)
    opp = score_company(db, c)
    db.commit()
    assert opp.brain_score >= 80 and opp.website_score < 60
    assert opp.recommended_service == "company_brain"
    assert c.status == LeadStatus.QUALIFIED
    assert opp.sales_angle and "Slack" in opp.sales_angle


@respx.mock
def test_T07_campaign_target_can_force_no_opportunity(db):
    mock_site(respx.mock)
    set_provider_override(FakeProvider(ScriptedLLM()))
    camp = Campaign(name="Websites only", target_service="website")
    db.add(camp)
    db.commit()
    c = _researched(db, camp.id)
    opp = score_company(db, c)
    assert opp.recommended_service == "none" and "website only" in opp.recommendation_reason
    assert c.status == LeadStatus.RESEARCHED  # not qualified


def _s(svc, score, conf=0.8):
    return ServiceScore(svc, score, conf, [], "", None)


def test_T07_recommendation_rules():
    assert recommend(_s("website", 40), _s("company_brain", 30), SCFG)[0] == "none"
    assert recommend(_s("website", 75), _s("company_brain", 30), SCFG)[0] == "website"
    assert recommend(_s("website", 62), _s("company_brain", 90), SCFG)[0] == "company_brain"
    assert recommend(_s("website", 70, 0.9), _s("company_brain", 72, 0.5), SCFG)[0] == "website"  # close → evidence
    assert recommend(_s("website", 90, 0.1), _s("company_brain", 20), SCFG)[0] == "none"  # low confidence
    rec, _ = recommend(_s("website", 80), _s("company_brain", 85), SCFG, target_service="website")
    assert rec == "website"


@respx.mock
def test_heuristic_scoring_without_llm(db):
    mock_site(respx.mock)
    c = _researched(db)
    opp = score_company(db, c)
    assert opp.method == "heuristic"
    rows = db.query(LeadScore).filter_by(company_id=c.id).all()
    brain = next(r for r in rows if r.service == "company_brain")
    collab = next(f for f in brain.factors if f["factor"] == "collaboration_software")
    assert collab["rating"] and collab["evidence_ids"]  # Slack/Notion mentioned on careers page
    km = next(f for f in brain.factors if f["factor"] == "knowledge_management_signals")
    assert km["rating"] == 4  # hiring Knowledge Manager / Head of Operations
    assert all(f["rating"] is None or f["evidence_ids"] for r in rows for f in r.factors)
