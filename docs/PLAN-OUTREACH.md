# Plan: referral outreach (REACH-B…E)

**Status:** not started, and **blocked on `docs/PLAN-GMAIL-CREDENTIALS.md` (REACH-A)** —
nothing here can run without a stored, decryptable Gmail credential.

**Stage prefix.** `REACH-*`, per the naming convention in `PLAN-JOB-COLLECTION.md`. Never
write a bare "Phase N": two other plans already use numbers for unrelated work.

This is stage 8 of the nine in `README.md` — the last unbuilt one, and the one the README
calls *"designed but **not built**"*.

---

## Why this is the stage worth building

The product thesis in `README.md` is *"The goal is to get you interviews, not just
applications."* Stages 1–7 reduce the cost of applying. Only stage 8 changes the
probability that a human at the company sees it. Autofill is commoditised — several
products do tailoring and form-filling, some free. Getting an application in front of a
person is the part that is both hard and differentiating.

---

## Decisions already made, and where they come from

| Decision | Source |
|---|---|
| Sends from the user's own Gmail, not a platform domain | ADR-003 |
| 10 outreach emails/day/user ceiling | ADR-003 |
| Every claim traces to a confirmed fact, verified by a second model pass | `PRD.md` §1, ADR-006 |
| **The user reviews and approves each email in the ApplyScout dashboard; the app sends it** | owner, 2026-10-08 |
| **Auto-send is available as an opt-in once the user trusts the output** | owner, 2026-10-08 |
| Recipients ranked by warm signal (shared employer/school/city) before cold | owner, 2026-10-08 |
| Contact sourcing is pluggable; the owner picks the source | owner, 2026-10-08 |

### The PRD tension on auto-send, and how it is resolved

`PRD.md` §2 says *"Human approves, machine executes… Fully autonomous spraying is what
makes existing tools useless, and it's what gets accounts banned."* Auto-send is in
tension with the first clause, so the resolution needs to be explicit rather than
assumed:

- **It is opt-in and off by default.** The default path is review-and-approve.
- **The cap is the real control.** ADR-003's 10/day ceiling is what separates this from
  spraying. 10 personalised emails a day is not the behaviour that gets accounts flagged;
  500 is.
- **Auto-send has stricter preconditions than manual send** (below). A human approving
  can override a warning; auto-send cannot.
- **Earned, not configured.** Auto-send unlocks only after the user has manually approved
  **10 emails**. The point is that they have seen what the system actually writes before
  delegating it. A user who enables it on day one has no basis for the trust.

This keeps a human in the loop for every *kind* of email before any email of that kind
goes out unattended, which is the substance of §2 rather than its letter.

### What reinstating direct send costs

An earlier revision of this spec had the app write a Gmail draft for the user to send by
hand. Sending from the dashboard is a better product and it brings back three things
that draft mode avoided. They are one feature, not three, and all must be correct:

1. **An at-most-once guarantee** — a `with_for_update()` lock on the
   `approved → sending` transition. See below; this is the single most important
   correctness property in the stage.
2. **Daily-cap enforcement** at send time, not draft time.
3. **Responsibility for the user's Gmail reputation.** A bounce or a complaint now lands
   on their personal address with no human having read the message. This is why email
   verification gates auto-send strictly.

---

## Stages

- **REACH-B** — models, migration, `ContactSource` interface, `ManualContactSource`.
- **REACH-C** — warm-signal ranking, email verification, suppression checks.
- **REACH-D** — drafting through the existing truth-check, review queue, approve, the
  send lock, the daily cap, sending.
- **REACH-E** — opt-out endpoint, auto-send opt-in, and `ApifyContactSource`.

---

## Flow

```
application reaches `submitted`
        │  enqueue draft_outreach_task(application_id)
        ▼
ContactSource.find(company, profile_facts)   → candidate contacts
        │  rank by warm signal, take top N (default 2)
        ▼
for each contact:
    suppressed?        → Outreach(status=skipped, reason)
    email `invalid`    → Outreach(status=skipped, reason)
        │
        ▼
    draft from the Facts KB  →  TRUTH-CHECK (same pass as resumes, ADR-006)
        │
        ├─ flagged  → status=ready_for_review, blocked from approval until edited
        └─ clean    → status=ready_for_review
                          │
            ┌─────────────┴──────────────┐
            │                            │
      auto_send off                 auto_send on
      (default)                     AND preconditions met
            │                            │
   user approves in dashboard      auto-approve
            │                            │
            └─────────────┬──────────────┘
                          ▼
        with_for_update(): approved → sending     ← at-most-once
                          │  daily cap checked here
                          ▼
              send via user's Gmail  →  status=sent
```

The trigger is `submitted` rather than `approved`, matching `README.md`: *"After you
apply, the app finds a suitable person at the company…"*. Drafting outreach for an
application that never went out would waste tokens and confuse the user.

### Auto-send preconditions

Every one must hold, or the row falls back to `ready_for_review` for a human:

| precondition | why |
|---|---|
| `profile.outreach_auto_send` is on | opt-in |
| ≥10 emails previously approved by hand on this profile | earned, not configured |
| `flagged_unsupported_claims` is empty | the truth-check is the only remaining gate |
| `email_verification_status == "valid"` | **stricter than manual.** `accept_all` and `unknown` are allowed for a human who can judge; auto-send will not guess at an address |
| contact not suppressed | |
| today's sent count < 10 | ADR-003 |

---

## Models

### `Contact`

A person at a company, **scoped to one profile**.

| column | notes |
|---|---|
| `id` | uuid pk |
| `profile_id` | FK. Contacts are never shared between users — one user's contact list must not leak into another's |
| `company` | as matched against `Job.company` |
| `full_name`, `title` | |
| `email` | nullable: a contact can be known before an address is |
| `email_verification_status` | `valid` / `invalid` / `accept_all` / `unknown` |
| `email_verified_at` | |
| `source` | `manual`, or the adapter name |
| `source_ref` | the adapter's own id, for re-fetching |
| `warm_signal` | JSON, e.g. `{"kind": "former_employer", "value": "Flipkart"}`, or NULL |

`UNIQUE(profile_id, email)` where email is non-NULL.

**Why profile-scoped and not global:** a shared contact table is tempting for dedupe,
but it means user A can infer who user B is talking to. At 6–8 users the dedupe saves
nothing and the privacy exposure is real.

### `Outreach`

One email, to one contact, about one application.

| column | notes |
|---|---|
| `id` | uuid pk |
| `profile_id`, `application_id`, `contact_id` | FKs |
| `status` | `ready_for_review` / `approved` / `sending` / `sent` / `skipped` / `failed` |
| `skip_reason` | populated for `skipped`, so a silent no-op is impossible |
| `subject`, `body` | |
| `flagged_unsupported_claims` | JSON, same shape as `Application` |
| `warm_signal_used` | JSON — what the email actually claimed as the connection |
| `approved_by` | `user` or `auto`, so the auto-send unlock count is computable and auditable |
| `gmail_message_id`, `gmail_thread_id` | set on `sent` |
| `sent_at`, `error` | |
| `created_at`, `updated_at` | |

`UNIQUE(application_id, contact_id)` — one email per person per application, enforced in
the schema rather than in application code.

### `Suppression`

| column | notes |
|---|---|
| `id` | uuid pk |
| `profile_id` | nullable; **NULL = global**, applies to every user |
| `email` or `domain` | one of the two |
| `reason` | `opt_out` / `bounced` / `manual` |
| `created_at` | |

Checked before every draft **and again immediately before send** — a suppression written
between drafting and approval must still take effect.

An opt-out from the public endpoint writes a **global** row: someone who asks not to be
contacted should not have to ask each user separately.

### `Profile` additions

| column | notes |
|---|---|
| `outreach_auto_send` | bool, default **false** |
| `outreach_contacts_per_application` | int, default **2** |

---

## The send lock (REACH-D)

The `approved → sending` transition takes a `with_for_update()` row lock, exactly as
`main.py::claim_submission` does for application submission. The reasoning is identical
and is recorded in `GAPS.md` §2: that endpoint is *"the at-most-once guarantee for an
irreversible outward-facing action"*, pinned by
`test_claim_submission_still_cannot_fire_twice`.

Sending email is irreversible and outward-facing. Two workers picking up the same
`approved` row, or a double-click on Approve, must not produce two emails to the same
person. **Copy the existing pattern rather than inventing a second one** — and note that
`GAPS.md` §2 records a near-miss where a reviewer proposed deleting the application-side
lock because its comments framed it in superseded terms. Comment this one in terms of
what it guarantees, not which ADR motivated it.

The daily cap is checked **inside** the lock, against `sent_at >= utc_day_start()`,
following the `campaigns.applied_today` pattern. Checking it outside the lock would let
two concurrent sends both observe 9.

---

## Warm-signal ranking (REACH-C)

Candidates are ordered by the strongest shared signal found between the contact and the
user's own `ResumeFact` rows:

1. **Same former employer** — strongest. Verifiable and specific.
2. **Same role as the one being applied for** — owner's addition, 2026-10-09, and a better
   signal than the ranking originally had. A PM asking another PM about a PM opening is a
   natural approach in a way that asking a recruiter is not: the recipient can speak to fit
   from experience, has an incentive to want good teammates, and is not fielding a hundred
   cold asks a day. This is the **default target** for the Apify adapter's query — it
   searches the company for the job's own title.
3. **Same university**
4. **Same city**
5. **No link** — a member of the relevant team. Cold, and ranked last.

Signals 1, 3 and 4 are claims about the *user* and must trace to a `ResumeFact`. Signal 2
is a claim about the *recipient* and traces to the contact's own title plus `Job.title`, so
it is verifiable from data the system already holds — no fact needed, and nothing asserted
about the user that the truth-check could not check.

The chosen signal is written to `Outreach.warm_signal_used`, because the email asserts
it ("we overlapped at Flipkart", "I saw you're a PM on the payments team") and an assertion
the user cannot verify is exactly what the truth-check exists to stop. **A signal about the
user that cannot be traced to a `ResumeFact` must not be used.**

**Ordering must be deterministic.** `GAPS.md` 6.6 records a real nondeterminism bug from
ordering by score with no tiebreaker: which job a capped run applied to was undefined
whenever two rows tied. Rank by `(signal_rank, contact.created_at, contact.id)` so ties
resolve the same way every run. This matters more here than it did there, because with
auto-send on, the tiebreaker decides who receives mail.

---

## `ContactSource` interface (REACH-B)

```
find(company: str, facts: list[ResumeFact], limit: int) -> list[ContactCandidate]
```

**First implementation is `ManualContactSource`** — the user enters a name, company and
optionally an email. No vendor, no cost, no legal question, and it exercises the entire
engine end to end. It is also the permanent fallback for any company an automated source
cannot cover.

**Why manual first rather than integrating a provider immediately:** the engine holds all
the correctness properties — the send lock, the cap, suppression, dedupe, verification
gating. Wiring a paid provider into an unproven engine means debugging both at once. Manual
also stays permanently useful, because the automated adapter's coverage is partial (below).

### `ApifyContactSource` (REACH-E) — decided 2026-10-09

The owner's choice is Apify's `harvestapi/linkedin-profile-search` actor. It searches a
company for people matching a title and returns profile data.

**Why this adapter is a plain HTTP integration and not an infrastructure project:**

- **No LinkedIn credential of any kind.** The actor runs on Apify's own infrastructure. It
  needs no cookie, no session, no account from the user — so no user's LinkedIn account is
  exposed, which was the deciding objection against every other route considered.
- **Nothing is installed or vendored.** One authenticated POST to Apify's API, one poll for
  the run result. No browser, no Patchright, no proxy configuration, no anti-detection
  layer — none of that is in this design and none of it should be added to it.
- **The query is narrow by construction:** one company, one title, `limit` 2 by default.
  It is a lookup, not a harvest.

**Query:** company from `Job.company`, title from `Job.title` — which is what makes warm
signal #2 the default rather than an afterthought.

**Cost**, from the actor's own pricing: **$0.10 per search page** (up to 25 results) plus
**$0.01 per profile** in email mode. At the default 2 contacts per application that is
roughly **$0.12 per application**.

**Coverage is partial, and the spec must not pretend otherwise.** Email addresses are not on
LinkedIn profiles — the actor states the data *"is not publicly available on the platform"*
and performs *"independent email searches"*, with results *"not guaranteed to find an email
for every profile."* So expect a real miss rate. Three consequences:

1. `ManualContactSource` is a **permanent fallback**, not scaffolding.
2. A company with no result produces `Outreach(status=skipped,
   skip_reason="no_contact_found")` — visible, never a silent no-op.
3. Returned addresses carry the actor's own uncertainty, so they go through the same
   verification gate as any other source and are **never** auto-sent on `accept_all` or
   `unknown`.

**Failure handling.** An Apify run can be slow, rate-limited, or return nothing. Treat it as
an untrusted network dependency: a bounded timeout, no retry storm, and on failure fall
through to `ManualContactSource` rather than blocking the application. The Apify token lives
in the environment and is never logged — same discipline as every other credential here.

**Residual items that belong to the owner, not to this spec:** a privacy notice and a
lawful-basis position for processing contact data under DPDP/GDPR, and the fact that Apify's
terms place responsibility on the account holder running the actor. Recorded so the next
session does not have to rediscover that they were considered.

---

## Email verification (REACH-C)

Verification gates whether a draft is created, and more strictly whether it can
auto-send. Measured reality to design around:

- **`valid`** → eligible for manual approval and for auto-send.
- **`invalid`** → `skipped`, reason recorded. Never sent.
- **`accept_all`** → the domain accepts every address, so mailbox existence is unknowable.
  Most corporate Google Workspace and Microsoft 365 tenants behave this way, so this will
  be the *common* case, not the edge case. Eligible for **manual** approval with the
  uncertainty shown in the UI; **never** auto-sent.
- **`unknown`** → same handling as `accept_all`.

**On running verification ourselves:** `AfterShip/email-verifier` (Go, MIT — licence
verified 2026-10-08 via the GitHub API, so it carries none of the copyleft obligations
that rule out the GPL/AGPL alternatives in this space) performs syntax, MX, disposable,
role-account and catch-all checks for free. But its own README notes SMTP checking is
**off by default** because *"most ISPs block outgoing SMTP requests through port 25"*.
The mailbox-existence check — the only layer that prevents a bounce — needs outbound
port 25, a PTR record and a reputable `MAIL FROM` domain. Most cloud hosts block port 25
outright. It is also Go, while this API is Python, so it would be a sidecar service
rather than an import.

**Implication:** verification is best-effort metadata, not a guarantee. That is precisely
why `accept_all` cannot auto-send: with a human sending, a bounce costs one bad address;
with auto-send, a run of bounces damages the user's own Gmail reputation unattended.

---

## Drafting (REACH-D)

Reuses the existing two-pass tailoring engine rather than introducing a second
generation path:

1. **Pass 1** writes a short note from the user's confirmed facts, the job, and the
   chosen warm signal.
2. **Pass 2** is the existing truth-check. A referral note claiming an unsupported
   achievement is the same failure as a fabricated resume bullet, and gets the same gate.

Note the known tension recorded in `GAPS.md` 6.7: the model half of the checker flags
titles, scope and praise adjectives, which is why 9 of 30 golden rows still block. Prose
asking for a favour is *more* likely to carry evaluative framing than a resume bullet, so
expect a higher flag rate here than on bullets, and treat the review queue as a normal
path rather than a rare one.

**This matters directly for auto-send:** with no human reading the email, the truth-check
is the only remaining gate. Its flag rate on favour-asking prose has never been measured.
Measure it on ~10 real drafts before auto-send is offered to anyone.

Every body ends with a plain opt-out line and a link to the unsubscribe endpoint.

---

## Opt-out (REACH-E)

`GET /outreach/unsubscribe/{signed_token}` — unauthenticated, signed, idempotent. Writes
a **global** `Suppression` row and returns a plain confirmation page.

Unauthenticated by necessity: the recipient has no account. Signed so the endpoint cannot
be used to enumerate addresses or mass-suppress. No Gmail read scope is involved, which
is the reason to use a link rather than reply-parsing.

---

## Endpoints

- `GET /outreach/review-queue` — drafts awaiting approval, each with the recipient, the
  warm signal used, the verification status, and any flags.
- `PATCH /outreach/{id}` — edit subject/body, or dismiss a flag. An edit re-runs the
  truth-check; an edited email must not bypass the gate.
- `POST /outreach/{id}/approve` — takes the lock, transitions, enqueues the send.
- `POST /outreach/{id}/skip` — user declines this one; records a reason.
- `GET /outreach` — history, for the tracker.

---

## Error handling

| case | behaviour |
|---|---|
| No contacts found for the company | One `Outreach(status=skipped, skip_reason="no_contact_found")`. Visible, never a silent no-op |
| Contact suppressed | `skipped`, reason recorded; no draft, no Gmail call |
| Truth-check flags the draft | `ready_for_review`, approval blocked until edited or the flag is dismissed |
| Daily cap reached | Row stays `approved`; sends on the next day's first pass. Not an error |
| Gmail credential missing or revoked | Stop before drafting; write a `Notification` asking the user to reconnect. Do not retry-loop |
| Send fails | `failed`, with the error **type** only — never the body, which can echo the credential. `digest.smtp_sender` sets this precedent |
| Send succeeded but the commit failed | The lock plus `gmail_message_id` makes this detectable: a `sending` row older than the task timeout is reconciled by querying Gmail for the message id, never by blindly resending |
| Enqueue fails | Rows persist, return `503` with a "saved, try again" message, mirroring `main.py:1672` |

---

## Tests

| test | pins |
|---|---|
| `test_outreach_cannot_send_twice` | The lock. Mirrors `test_claim_submission_still_cannot_fire_twice` |
| `test_daily_cap_is_enforced_inside_the_lock` | Two concurrent sends cannot both see 9 |
| `test_outreach_is_unique_per_application_and_contact` | The schema-level duplicate guarantee |
| `test_outreach_respects_suppression_list` | Including global (`profile_id IS NULL`) rows |
| `test_suppression_written_after_drafting_still_blocks_send` | The re-check at send time |
| `test_truth_check_flag_blocks_approval` | |
| `test_editing_a_draft_reruns_the_truth_check` | An edit cannot bypass the gate |
| `test_auto_send_requires_all_preconditions` | One case per row of the preconditions table |
| `test_auto_send_refuses_accept_all_email` | The stricter-than-manual rule |
| `test_auto_send_locked_until_ten_manual_approvals` | The earned-trust rule |
| `test_warm_signal_ranking_prefers_former_employer` | Ordering, including the deterministic tiebreaker |
| `test_same_role_signal_traces_to_job_title_not_a_fact` | Signal 2 is a claim about the recipient, so it must verify against `Job.title` + the contact title, not require a `ResumeFact` |
| `test_apify_failure_falls_through_to_manual_source` | A vendor outage must not block the application |
| `test_apify_no_result_skips_with_reason` | Partial coverage is visible, never silent |
| `test_warm_signal_must_trace_to_a_resume_fact` | No asserted connection without a backing fact |
| `test_invalid_email_is_skipped_with_reason` | |
| `test_unsubscribe_token_adds_global_suppression` | |
| `test_unsubscribe_rejects_unsigned_token` | No enumeration |
| `test_contacts_are_not_visible_across_profiles` | The privacy property of profile scoping |

---

## Deliberately not building

- **Reply polling.** Needs `gmail.readonly`, a second restricted scope, to tell the user
  something their own inbox already shows them. Replies are marked in the tracker by
  hand until there is a reason to spend another restricted scope on it.
- **Follow-up sequences.** One ask per contact. Drip follow-ups are the single clearest
  thing that turns referral outreach into spam, and they multiply the cap problem.
- **A contact CRM.** Contacts exist to support an application, not as a managed list.
- **Cross-user contact dedupe.** See the privacy note under `Contact`.
- **Per-user sending domains or a platform fallback domain.** ADR-003 decided against
  this and the reasoning (distributed reputation risk) still holds.

---

## Open items for the owner

1. ~~Which automated `ContactSource`~~ **Decided 2026-10-09: Apify
   `harvestapi/linkedin-profile-search`.** What remains is an `APIFY_TOKEN` in the
   environment and the privacy-notice/lawful-basis item noted in that section.
2. **Measure the truth-check flag rate on outreach prose** before auto-send ships.
   `GAPS.md` 6.7's 9-of-30 was measured on resumes; favour-asking prose is expected to be
   worse, and auto-send makes that gate load-bearing. ~10 real drafts is enough to know.
3. **Confirm the auto-send unlock threshold.** 10 manual approvals is a chosen number,
   not a measured one.
