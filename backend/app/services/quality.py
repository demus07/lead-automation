"""Outreach quality control: deterministic checks + Quality Agent → quality score and report.

Passing quality only moves a draft into the human approval queue. It never sends anything."""
from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Company, Contact, KnowledgeItem, OutreachDraft
from app.research.evidence import EvidenceSet, norm
from app.services import settings_service
from app.services.suppression import contact_suppressed

log = logging.getLogger(__name__)
NUMERIC_CLAIM = re.compile(
    r"(?:[$€£]\s?\d[\d,.]*\s?(?:k|m|bn|million|billion)?|\d[\d,.]*\s?(?:%|percent|employees|people|customers|clients|"
    r"offices|countries|users|million|billion|bn|m\b|x\b)|\bseries [a-f]\b|\b(?:19|20)\d{2}\b)", re.I)
PLACEHOLDER = re.compile(r"\[[^\]]{1,40}\]|\{[^}]{1,40}\}|<[A-Z_ ]{2,30}>|lorem ipsum", re.I)
CTA_HINTS = ("?", "call", "chat", "worth", "open to", "interested", "reply", "would it", "happy to")
URL_RE = re.compile(r"https?://[^\s)>\]]+", re.I)
SEVERITY_PENALTY = {"high": 30, "medium": 12, "low": 4}


def word_count(body: str, signature_lines: int = 3) -> int:
    lines = [l for l in body.strip().split("\n")]
    # exclude short trailing sign-off lines ("Best,", "Sam") from the count
    while lines and len(lines[-1].split()) <= 3 and signature_lines > 0:
        lines.pop()
        signature_lines -= 1
    return len(" ".join(lines).split())


def deterministic_checks(db: Session, draft: OutreachDraft, company: Company, contact: Contact | None,
                         ev: EvidenceSet, claims: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    q = settings_service.get_section(db, "quality")
    profile = settings_service.get_section(db, "agency_profile")
    issues: list[dict[str, Any]] = []

    def issue(check: str, severity: str, text: str) -> None:
        issues.append({"check": check, "severity": severity, "text": text, "source": "deterministic"})

    body, subject = draft.body or "", draft.subject or ""
    full = f"{subject}\n{body}\n{draft.linkedin_connection_note or ''}\n{draft.linkedin_message or ''}"

    # recipient & company names
    if contact is None or not contact.email_normalized:
        issue("recipient", "high", "No recipient with a business email")
    else:
        first = (contact.first_name or contact.full_name.split()[0]).strip()
        greeting = "\n".join(body.strip().split("\n")[:2])
        if first.lower() not in greeting.lower():
            issue("recipient_name", "high", f"Greeting does not address the recipient by name ({first})")
    other_contacts = db.scalars(select(Contact).where(Contact.company_id == company.id, Contact.deleted_at.is_(None))).all()
    for oc in other_contacts:
        if contact and oc.id != contact.id and oc.first_name and len(oc.first_name) > 2 and \
                re.search(rf"\b(hi|hello|dear|hey)\s+{re.escape(oc.first_name)}\b", body, re.I):
            issue("recipient_name", "high", f"Message greets {oc.first_name}, not the selected recipient")
    if PLACEHOLDER.search(full):
        issue("placeholder", "high", f"Unfilled placeholder: {PLACEHOLDER.search(full).group(0)}")

    # correct service only
    services = {s["key"]: s for s in profile.get("services", [])}
    other = "company_brain" if draft.service == "website" else "website"
    other_name = (services.get(other) or {}).get("name") or ""
    other_markers = {"company_brain": ["company brain"], "website": ["website redesign", "new website", "bespoke website"]}[other]
    if other_name and other_name.lower() in full.lower():
        other_markers.append(other_name.lower())
    if any(m in full.lower() for m in other_markers):
        issue("service", "high", f"Message pitches the {other.replace('_', ' ')} service; draft is for {draft.service}")

    # length
    wc = word_count(body)
    if wc < int(q["min_words"]) or wc > int(q["max_words"]):
        issue("length", "medium", f"Body is {wc} words (allowed {q['min_words']}–{q['max_words']})")
    elif not int(q["target_min_words"]) <= wc <= int(q["target_max_words"]):
        issue("length", "low", f"Body is {wc} words (target {q['target_min_words']}–{q['target_max_words']})")
    if draft.linkedin_connection_note and len(draft.linkedin_connection_note) > 300:
        issue("linkedin_length", "medium", "LinkedIn connection note exceeds 300 characters")

    # banned / generic phrases
    for phrase in q.get("banned_phrases", []):
        if phrase.lower() in full.lower():
            issue("generic_language", "medium", f"Contains discouraged phrase: “{phrase}”")

    # unsupported specifics: numbers, amounts, years, funding rounds must appear in evidence or agency material
    agency_text = norm(" ".join([str(profile.get(k, "")) for k in ("description", "case_studies", "testimonials",
                                                                    "call_to_action", "opt_out_line")]))
    ev_text = norm(" ".join(it["text"] for it in ev.items.values()))
    for m in NUMERIC_CLAIM.finditer(f"{subject}\n{body}"):
        token = norm(m.group(0)).strip(" .,")
        digits = re.sub(r"[^\d]", "", token)
        if token in ev_text or token in agency_text or (digits and len(digits) >= 2 and digits in re.sub(r"[^\d ]", "", ev_text)):
            continue
        if re.fullmatch(r"\d{1,2}", digits or "") and re.search(r"\d+\s?-?\s?min", body[m.start():m.end() + 8], re.I):
            continue
        issue("unsupported_claim", "high", f"Specific claim not found in evidence: “{m.group(0)}”")

    # claims list must cite valid evidence
    for c in claims or draft.evidence or []:
        ids = c.get("evidence_ids") or []
        valid = ev.valid_ids(ids)
        if not valid:
            issue("unsupported_claim", "high", f"Claim has no valid evidence: “{c.get('text', '')[:120]}”")
            continue
        cited = norm(ev.text_of(valid))
        key_terms = [w for w in re.findall(r"[A-Za-z][A-Za-z0-9&'-]{3,}", c.get("text", ""))
                     if w[0].isupper() or any(ch.isdigit() for ch in w)]
        missing = [w for w in key_terms if norm(w) not in cited and norm(w) not in norm(company.name)]
        if key_terms and len(missing) > len(key_terms) / 2:
            issue("unsupported_claim", "medium", f"Claim terms not in cited evidence: {', '.join(missing[:5])}")

    # links only to agency-approved destinations
    allowed = [profile.get("website") or ""] + list(profile.get("portfolio_links", [])) + [
        c.get("url", "") for c in profile.get("case_studies", [])]
    allowed = [a for a in allowed if a]
    for u in URL_RE.findall(full):
        if not any(u.startswith(a.rstrip("/")) for a in allowed):
            issue("link", "medium", f"Link not in approved agency material: {u}")

    # confidential material must never appear
    conf_items = db.scalars(select(KnowledgeItem).where(KnowledgeItem.confidential.is_(True),
                                                        KnowledgeItem.deleted_at.is_(None))).all()
    for k in conf_items:
        if k.title and len(k.title) > 4 and k.title.lower() in full.lower():
            issue("sensitive_info", "high", f"References confidential material: {k.title}")
    for e in re.findall(r"[\w.+-]+@[\w-]+\.[\w.]+", body):
        if contact is None or e.lower() != (contact.email_normalized or ""):
            if not (profile.get("website") and e.split("@")[1] in profile["website"]):
                issue("sensitive_info", "medium", f"Body contains an email address: {e}")

    # call to action
    tail = " ".join(body.strip().split("\n")[-6:]).lower()
    if not any(h in tail for h in CTA_HINTS):
        issue("cta", "medium", "No clear call to action near the end")
    if body.count("?") > 3:
        issue("cta", "low", "Too many questions; keep a single clear ask")

    # opt-out line
    if profile.get("include_opt_out_line") and profile.get("opt_out_line"):
        if norm(profile["opt_out_line"])[:30] not in norm(body):
            issue("compliance", "low", "Opt-out line missing")

    # suppression
    if contact_suppressed(db, contact, company):
        issue("suppression", "high", "Recipient or domain is suppressed / do-not-contact")
    return issues


def evaluate(db: Session, draft: OutreachDraft, company: Company, contact: Contact | None, ev: EvidenceSet,
             claims: list[dict] | None = None, use_ai: bool = True, job_id=None) -> tuple[int, dict[str, Any]]:
    from app.ai.agents.context import agency_context
    from app.ai.agents.schemas import QualityOutput
    from app.ai.llm.providers import llm_available
    from app.ai.runtime import AgentFailed, AgentUnavailable, BudgetExceeded, load_prompt, run_agent
    from app.ai.sanitize import wrap_untrusted

    q = settings_service.get_section(db, "quality")
    issues = deterministic_checks(db, draft, company, contact, ev, claims)
    det_score = max(0, 100 - sum(SEVERITY_PENALTY[i["severity"]] for i in issues))
    report: dict[str, Any] = {"deterministic_score": det_score, "issues": issues, "threshold": int(q["threshold"])}
    final = det_score
    if use_ai and llm_available(settings_service.get_section(db, "llm")):
        evidence_txt = "\n".join(f"[{i}] {wrap_untrusted(it['text'][:1500], source=it.get('url') or i)}"
                                 if it["kind"] == "page" else f"[{i}] {it['text'][:500]}" for i, it in ev.items.items())
        user = (f"Recipient: {contact.full_name if contact else 'NONE'} ({contact.job_title if contact else ''}) at "
                f"{company.name}\nService being pitched: {draft.service}\n\nDRAFT\nSubject: {draft.subject}\n\n"
                f"{draft.body}\n\nLinkedIn note: {draft.linkedin_connection_note}\n\nClaims declared by the writer: "
                f"{claims or draft.evidence}\n\nEVIDENCE:\n{evidence_txt}")
        try:
            res = run_agent(db, agent="outreach_quality",
                            system=load_prompt("outreach_quality") + "\n\n" + agency_context(db, draft.service),
                            user=user, schema=QualityOutput, tier="smart", company_id=company.id, job_id=job_id,
                            use_cache=False)
            o = res.output
            ai_avg = round((o.accuracy * 2 + o.relevance + o.personalisation + o.tone + o.call_to_action) / 6)
            for i in o.issues:
                issues.append({"check": i.type, "severity": i.severity, "text": i.text, "source": "ai"})
            ai_pen = sum(SEVERITY_PENALTY[i.severity] for i in o.issues if i.severity == "high")
            report.update(ai_scores=o.model_dump(exclude={"issues"}), ai_run_id=str(res.run_id))
            final = round(0.5 * det_score + 0.5 * max(0, ai_avg - ai_pen))
        except (AgentUnavailable, AgentFailed, BudgetExceeded) as e:
            report["ai_note"] = f"AI quality review unavailable: {e}"
    if any(i["severity"] == "high" for i in issues):
        final = min(final, int(q["threshold"]) - 1)  # high-severity issues always fail the gate
    report["score"] = final
    report["passed"] = final >= int(q["threshold"])
    return final, report
