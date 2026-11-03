# Acceptance tests

`make test` runs the CI-safe suite (external HTTP mocked with `respx`, LLM replaced by a scripted fake).
`make test-live` runs tests against real public sources. Integrations that need your credentials
(LLM, Gmail, Outlook, paid search) are exercised against their real HTTP request/response shapes in CI;
see “Manual verification with credentials” below for the live check.

| # | Requirement | Automated test(s) | Live verification |
|---|---|---|---|
| 1 | Configure a discovery campaign | `test_phase2_discovery.py::test_T01_user_can_configure_campaign` | UI: Campaigns → New |
| 2 | Discover real companies from ≥1 source | `test_T02_discovers_companies_from_public_directory_mocked` | `test_T02_live_real_directory_discovery` (real YC directory) ✅ |
| 3 | Dedupe by normalised domain | `test_T03_dedup_by_normalized_domain`, `test_normalize_domain_variants` | Re-running a campaign on the same source creates 0 new companies |
| 4 | Retrieve & analyse an accessible website | `test_phase3_intelligence.py::test_T04_retrieve_and_analyse_site_deterministic`, `test_ai_research_output_is_validated` | `test_T08_live_public_contact` crawls basecamp.com |
| 5 | Findings include evidence URLs | `test_T05_findings_include_evidence_urls` | Research report page |
| 6 | Separate website & Company Brain scores | `test_phase4_qualification.py::test_T06_separate_scores_with_llm`, `test_heuristic_scoring_without_llm` | |
| 7 | Recommends correct service or none | `test_T07_recommends_correct_service`, `test_T07_recommendation_rules`, `test_T07_campaign_target_can_force_no_opportunity` | |
| 8 | Identify a real public business contact | `test_T08_identify_public_contact_and_T09_not_verified`, `test_testimonial_authors_are_not_contacts` | `test_T08_live_public_contact` ✅ |
| 9 | Unverified contacts not marked verified | `test_T09_only_verification_provider_can_verify`, `test_csv_import_and_export` | |
| 10 | Personalised outreach draft | `test_phase5_8_outreach_approval.py::test_T10_generates_personalised_draft` | needs LLM key |
| 11 | Quality agent catches unsupported claims | `test_T11_quality_catches_unsupported_claims`, `test_quality_catches_wrong_recipient_and_wrong_service` | |
| 12 | Draft enters approval queue | `test_T12_T13_queue_edit_and_approve` | |
| 13 | Edit and approve | `test_T12_T13_queue_edit_and_approve`, `test_needs_review_requires_override`, `test_viewer_cannot_approve` | |
| 14 | Approval creates unsent mailbox draft | `test_T14_T15_T16_gmail_unsent_draft_no_send_no_duplicates` (Gmail API over HTTP), `test_T14_outlook_draft_created_via_graph_without_send` (Graph over HTTP) | needs OAuth app + mailbox |
| 15 | Approval does not send | same + `test_T15_no_send_code_paths_exist` (static scan) | |
| 16 | No duplicate drafts | `test_T14_T15_T16_…`, `test_T16_crash_after_remote_create_does_not_duplicate` | |
| 17 | Opt-out → suppression | `test_T17_opt_out_reply_adds_suppression_via_mailbox_sync` | |
| 18 | Suppressed contacts get no drafts | `test_T18_suppressed_contacts_get_no_new_drafts` | |
| 19 | Dashboard shows real records | `test_T19_dashboard_shows_real_records` | |
| 20 | Background tasks recover from temporary failures | `test_T20_background_job_recovers_from_temporary_failure`, `test_T20_stale_running_job_is_recovered`, `test_workflow_pause_skips_scheduled_runs` | |

## Manual verification with credentials

1. **LLM** — Settings → AI configuration → Test. Then on a qualified company: *Generate draft*; check the
   draft's claims and quality report, and the AI usage page for tokens/cost.
2. **Gmail / Outlook** — connect an account, approve a draft, open the mailbox **Drafts** folder: the
   message is there, unsent. Approve again → still one draft. Send it manually, reply from another
   address with “please remove me”, press *Sync now* → the contact appears on the suppression list.
3. **Web search** — add a Brave/Tavily key, select it, run a campaign: limited-mode banner disappears and
   search history shows the generated queries.
