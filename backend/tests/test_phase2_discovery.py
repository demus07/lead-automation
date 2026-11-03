import io
import json

import pytest
import respx
from httpx import Response

from app.discovery.normalize import company_name_from_title, normalize_domain, normalize_email
from app.discovery.providers import register_provider
from app.discovery.providers.base import DiscoveredCompany, DiscoveredSignal, DiscoveryProvider
from app.models import Company, LeadSource, LeadStatus, SearchQuery, Suppression
from app.services.state_machine import InvalidTransition, transition

CAMPAIGN = {
    "name": "UK fintech growth",
    "industries": ["fintech"],
    "geographies": ["United Kingdom"],
    "company_sizes": ["11-50", "51-200"],
    "target_roles": ["CEO", "Head of Marketing"],
    "signal_focus": ["funding", "hiring"],
    "sources": ["fake_dir"],
    "daily_company_limit": 50,
    "auto_research": False,
}


class FakeDirectory(DiscoveryProvider):
    key = "fake_dir"
    label = "Fake directory"
    kind = "directory"

    def __init__(self, items):
        self.items = items

    def search(self, q, cfg):
        return self.items[q.offset: q.offset + q.limit]


@pytest.fixture
def fake_provider():
    items = [
        DiscoveredCompany(name="Acme Pay", domain="acmepay.co.uk", website="https://www.acmepay.co.uk/",
                          source_url="https://dir.example/acme",
                          signals=[DiscoveredSignal("funding", "Acme Pay raised a seed round", "https://news.example/a")]),
        DiscoveredCompany(name="ACME PAY LTD", domain="WWW.ACMEPAY.CO.UK", website="http://acmepay.co.uk/about",
                          source_url="https://dir.example/acme2"),
        DiscoveredCompany(name="Ledgerly", domain="ledgerly.io", website="https://ledgerly.io",
                          source_url="https://dir.example/ledgerly"),
    ]
    p = FakeDirectory(items)
    register_provider(p)
    return p


# ------------------------------------------------------------------- normalisation (unit)
def test_normalize_domain_variants():
    for v in ["https://WWW.Acme.co.uk/about?x=1", "acme.co.uk", "http://shop.acme.co.uk", "hello@acme.co.uk"]:
        assert normalize_domain(v) == "acme.co.uk"
    assert normalize_domain("acme.github.io") == "acme.github.io"  # private suffix kept distinct
    assert normalize_domain("not a domain") is None
    assert normalize_domain("192.168.0.1") is None
    assert normalize_email(" Mailto:Jane.Doe@Acme.COM ") == "jane.doe@acme.com"
    assert company_name_from_title("Home | Acme — Payments for builders", "acme.com") == "Acme — Payments for builders" or \
        company_name_from_title("Acme | Payments for builders", "acme.com") == "Acme"


# ------------------------------------------------------------------- TEST 1
def test_T01_user_can_configure_campaign(operator_client):
    r = operator_client.post("/api/campaigns", json={**CAMPAIGN, "sources": ["yc_directory", "hn_hiring"]})
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    r = operator_client.patch(f"/api/campaigns/{cid}", json={"keywords": ["payments"], "daily_company_limit": 10})
    assert r.status_code == 200 and r.json()["keywords"] == ["payments"]
    q = operator_client.get(f"/api/campaigns/{cid}/preview-queries").json()["queries"]
    assert q and any("fintech" in x for x in q)
    bad = operator_client.post("/api/campaigns", json={**CAMPAIGN, "company_sizes": ["huge"]})
    assert bad.status_code == 422
    bad = operator_client.post("/api/campaigns", json={**CAMPAIGN, "sources": ["nope"]})
    assert bad.status_code == 422


def test_viewer_cannot_create_campaign(viewer_client, fake_provider):
    assert viewer_client.post("/api/campaigns", json=CAMPAIGN).status_code == 403


# ------------------------------------------------------------------- TEST 3 (+ discovery pipeline with fake source)
def test_T03_dedup_by_normalized_domain(operator_client, db, fake_provider):
    cid = operator_client.post("/api/campaigns", json=CAMPAIGN).json()["id"]
    r = operator_client.post(f"/api/campaigns/{cid}/run", json={})
    assert r.status_code == 200
    companies = db.query(Company).all()
    assert sorted(c.domain_normalized for c in companies) == ["acmepay.co.uk", "ledgerly.io"]
    # second run with the same data must not create duplicates
    fake_provider.items = list(fake_provider.items[:2])  # same Acme variants
    operator_client.post(f"/api/campaigns/{cid}/run", json={})
    db.expire_all()
    assert db.query(Company).count() == 2
    # provenance stored
    assert db.query(LeadSource).filter(LeadSource.provider == "fake_dir").count() >= 2
    assert db.query(SearchQuery).count() >= 1
    # manual create with variant domain → conflict
    r = operator_client.post("/api/companies", json={"name": "Acme", "website": "https://www.acmepay.co.uk/en"})
    assert r.status_code == 409


def test_discovery_skips_suppressed_domain(operator_client, db, fake_provider):
    db.add(Suppression(kind="domain", value="ledgerly.io", reason="opt_out"))
    db.commit()
    cid = operator_client.post("/api/campaigns", json=CAMPAIGN).json()["id"]
    operator_client.post(f"/api/campaigns/{cid}/run", json={})
    assert {c.domain_normalized for c in db.query(Company).all()} == {"acmepay.co.uk"}


def test_discovery_reports_limited_mode(operator_client, fake_provider):
    cid = operator_client.post("/api/campaigns", json=CAMPAIGN).json()["id"]
    job = operator_client.post(f"/api/campaigns/{cid}/run", json={}).json()
    j = operator_client.get(f"/api/workflows/jobs/{job['job_id']}").json()
    assert j["status"] == "succeeded"
    assert j["stats"]["limited_mode"] is True
    prov = operator_client.get("/api/discovery/providers").json()
    assert prov["limited_mode"] is True


# ------------------------------------------------------------------- TEST 2 (mocked provider HTTP, CI-safe)
@respx.mock
def test_T02_discovers_companies_from_public_directory_mocked(operator_client, db):
    from app.discovery.providers import public_sources

    public_sources._YC_CACHE.update(at=0.0, data=None)
    respx.get("https://yc-oss.github.io/api/companies/all.json").mock(return_value=Response(200, json=[
        {"id": 1, "name": "Cardamon", "website": "https://cardamon.ai", "status": "Active", "industry": "Fintech",
         "subindustry": "Fintech -> Payments", "industries": ["Fintech"], "tags": ["Payments"],
         "all_locations": "London, England, United Kingdom", "regions": ["United Kingdom"], "team_size": 20,
         "isHiring": True, "batch": "Winter 2026", "one_liner": "Payments infra", "url": "https://www.ycombinator.com/companies/cardamon"},
        {"id": 2, "name": "Dead Co", "website": "https://dead.co", "status": "Inactive", "industries": ["Fintech"]},
    ]))
    cid = operator_client.post("/api/campaigns", json={**CAMPAIGN, "sources": ["yc_directory"]}).json()["id"]
    operator_client.post(f"/api/campaigns/{cid}/run", json={})
    cos = db.query(Company).all()
    assert [c.domain_normalized for c in cos] == ["cardamon.ai"]
    assert cos[0].size_range == "11-50"
    assert {s.signal_type for s in cos[0].signals} == {"hiring", "funding"}
    assert all(s.source_url.startswith("https://") for s in cos[0].signals)


@pytest.mark.live
def test_T02_live_real_directory_discovery(operator_client, db):
    """Hits the real public YC directory mirror. Run with: pytest -m live"""
    cid = operator_client.post("/api/campaigns", json={**CAMPAIGN, "company_sizes": [],
                                                        "sources": ["yc_directory"]}).json()["id"]
    operator_client.post(f"/api/campaigns/{cid}/run", json={})
    cos = db.query(Company).all()
    assert len(cos) > 0
    assert all(c.domain_normalized for c in cos)


# ------------------------------------------------------------------- CSV import / export
def test_csv_import_and_export(operator_client, db):
    csv_data = (
        "Company,Website,Industry,Employees,Full Name,Title,Email\n"
        "Acme,https://www.acme.com,SaaS,25,Jane Doe,CEO,jane@acme.com\n"
        "Acme Inc,acme.com/about,SaaS,25,John Roe,CTO,not-an-email\n"
        "=cmd(),evil.com,,,,,\n"
        ",,,,,,\n"
    )
    r = operator_client.post("/api/discovery/import", files={"file": ("leads.csv", io.BytesIO(csv_data.encode()), "text/csv")})
    assert r.status_code == 200, r.text
    rep = r.json()
    assert rep["companies_created"] == 2 and rep["companies_matched"] == 1
    assert rep["contacts_created"] == 2 and rep["skipped"] == 1
    assert any("Invalid email" in e["error"] for e in rep["errors"])
    contacts = operator_client.get("/api/contacts").json()["items"]
    jane = next(c for c in contacts if c["full_name"] == "Jane Doe")
    assert jane["email_status"] == "unverified"  # TEST 9 (imported emails never verified)
    exp = operator_client.get("/api/companies/export")
    assert exp.status_code == 200 and "'=cmd()" in exp.text  # formula injection neutralised


# ------------------------------------------------------------------- state machine
def test_state_machine(db):
    c = Company(name="X", domain="x.com", domain_normalized="x.com")
    db.add(c)
    db.commit()
    transition(db, c, LeadStatus.RESEARCHING)
    with pytest.raises(InvalidTransition):
        transition(db, c, LeadStatus.APPROVED)
    transition(db, c, LeadStatus.DO_NOT_CONTACT)
    with pytest.raises(InvalidTransition):
        transition(db, c, LeadStatus.NEW)


def test_company_list_filters_and_bulk(operator_client, db):
    for i in range(5):
        operator_client.post("/api/companies", json={"name": f"Co {i}", "website": f"co{i}.com", "industry": "SaaS"})
    page = operator_client.get("/api/companies", params={"q": "co", "page_size": 2}).json()
    assert page["total"] == 5 and len(page["items"]) == 2
    ids = [c["id"] for c in page["items"]]
    r = operator_client.post("/api/companies/bulk", json={"ids": ids, "action": "tag", "value": "priority"})
    assert r.json()["updated"] == 2
    assert operator_client.get("/api/companies", params={"tag": "priority"}).json()["total"] == 2
    r = operator_client.post("/api/companies/bulk", json={"ids": ids, "action": "status", "value": "APPROVED"})
    assert len(r.json()["failed"]) == 2  # invalid transition rejected
