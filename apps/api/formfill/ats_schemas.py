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
or a two-word full_name split by map_fields.build_profile_summary); missing -> flagged.

Verified but deliberately absent (no truthful profile value): greenhouse country and ashby _systemfield_location (typeahead comboboxes),
lever location (typeahead) and org (no current-company column). Lever
urls[LinkedIn]/urls[GitHub] are left to deterministic.py's network rule.
File inputs (resume, cover_letter) are attached client-side, never mapped here.

workday is the exception to "read off a live form": its keys are Workday
`data-automation-id` values (the extension sends them as `automation_id`, a
wrapper's "formField-" prefix stripped) RECONSTRUCTED from public knowledge of
Workday's DOM, both the older `legalNameSection_*` and the newer `legalName--*`
conventions, NOT captured (no live access, NEXT-WORK-PLAN 4.2). Verify on a live
tenant before trusting. NEVER = a field the generic rules would mis-map: flagged.
"""

NEVER = "never"  # recognised, but no profile value may ever go here

ATS_FIELD_SCHEMAS: dict[str, dict[str, str]] = {
    "greenhouse": {"first_name": "given_name", "last_name": "family_name", "email": "email", "phone": "phone"},
    "lever": {"name": "full_name", "email": "email", "phone": "phone", "urls[Portfolio]": "website_url"},
    "ashby": {"_systemfield_name": "full_name", "_systemfield_email": "email"},
    "workday": {
        "legalNameSection_firstName": "given_name", "legalName--firstName": "given_name",
        "legalNameSection_lastName": "family_name", "legalName--lastName": "family_name",
        "email": "email", "emailAddress--emailAddress": "email",
        "phone-number": "phone", "phoneNumber--phoneNumber": "phone",
        "addressSection_addressLine1": "street_address", "address--addressLine1": "street_address",
        "addressSection_city": "city", "address--city": "city",
        "addressSection_postalCode": "postal_code", "address--postalCode": "postal_code",
        # "Country Phone Code" / extension / middle name: the label rules would put the phone
        # number or a name part here.
        "countryPhoneCode": NEVER, "phoneNumber--countryPhoneCode": NEVER,
        "phone-extension": NEVER, "phoneNumber--extension": NEVER,
        "legalNameSection_middleName": NEVER, "legalName--middleName": NEVER,
    },
}
