"""Per-ATS system fields (ADR-015 Phase 2): ats_type -> exact DOM name/id ->
profile_summary key. Consulted before the generic rules in deterministic.py,
so a verified system field fills whatever its label says.

Every entry was read off a live public form on 2026-09-27, never guessed:
- greenhouse: job-boards.greenhouse.io/anthropic/jobs/4461450008 (input ids) and
  boards-api.greenhouse.io/v1/boards/airbnb/jobs/8232207?questions=true (names).
- lever: jobs.lever.co/palantir/6ed76ce8-4156-4b60-b120-403538bd66cd/apply (input names).
- ashby: jobs.ashbyhq.com/ashby/7458d4e9-da2e-47bd-98cb-adfda43d42b2/application
  (rendered input name+id) and its public non-user-graphql ApiJobPosting form.

Greenhouse first_name/last_name fill from given_name/family_name (migration 0018,
or split from full_name by map_fields.build_profile_summary); missing -> flagged.

Verified but deliberately absent (no truthful profile value): greenhouse country and ashby _systemfield_location (typeahead comboboxes),
lever location (typeahead) and org (no current-company column). Lever
urls[LinkedIn]/urls[GitHub] are left to deterministic.py's network rule.
File inputs (resume, cover_letter) are attached client-side, never mapped here.
"""

ATS_FIELD_SCHEMAS: dict[str, dict[str, str]] = {
    "greenhouse": {"first_name": "given_name", "last_name": "family_name", "email": "email", "phone": "phone"},
    "lever": {"name": "full_name", "email": "email", "phone": "phone", "urls[Portfolio]": "website_url"},
    "ashby": {"_systemfield_name": "full_name", "_systemfield_email": "email"},
}
