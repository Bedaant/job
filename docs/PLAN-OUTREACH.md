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
| Human approves; the machine does not send autonomously | `PRD.md` §2 |
| Every claim traces to a confirmed fact, verified by a second model pass | `PRD.md` §1, ADR-006 |
| **v1 creates a Gmail draft; the user presses send** | owner, 2026-10-08 |
| Recipients ranked by warm signal (shared employer/school/city) before cold | owner, 2026-10-08 |
| Contact sourcing is pluggable; the owner picks the source | owner, 2026-10-08 |

### Reconciling two of those — read this before implementing

The owner chose **both** "draft queue, user approves each" **and** "write a Gmail draft
the user sends themselves". Taken literally that is two approval steps for one email.
The resolution, which needs a sanity check before coding:

- **Truth-check passes** → the draft is written straight to the user's Gmail drafts.
  Reviewing it in Gmail *is* the approval, and pressing send is the act of approving.
  No ApplyScout review step.
- **Truth-check flags an unsupported claim** → the draft is **not** written to Gmail. It
  waits in `/outreach/review-queue` until the user edits or dismisses the flag.

So the in-app queue exists only as the exception path. That is less code and exactly one
approval per email.

### What draft mode buys, precisely

Writing a draft instead of sending removes three things from the build:

- **The at-most-once send lock.** `main.py::claim_submission` needs a
  `with_for_update()` lock because submitting an application is irreversible. Creating a
  duplicate *draft* is untidy, not irreversible, so a `UNIQUE(application_id,
  contact_id)` constraint is sufficient. No row lock, no `sending` state.
- **Daily-cap enforcement.** ADR-003's 10/day cap governs *sending*. With a human
  sending, Gmail's own quotas are the ceiling. The cap becomes relevant again only if
  direct send is added later.
- **Deliverability risk to the user's Gmail reputation.** A human reads every email
  before it leaves. This was the strongest argument against automated outreach.

It does **not** reduce credential risk — see REACH-A on `gmail.compose` also permitting
send.

---

## Stages

- **REACH-B** — models, migration, `ContactSource` interface, `ManualContactSource`.
- **REACH-C** — warm-signal ranking, email verification, suppression checks.
- **REACH-D** — drafting through the existing truth-check, Gmail draft creation.
- **REACH-E** — opt-out endpoint, and whichever automated `ContactSource` the owner picks.

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
    email unverifiable → Outreach(status=skipped, reason) and surface it
        │
        ▼
    draft from the Facts KB  →  TRUTH-CHECK (same pass as resumes, ADR-006)
        │
        ├─ flagged     → status=ready_for_review   (waits in /outreach/review-queue)
        └─ clean       → write to user's Gmail drafts → status=draft_created
                                  │
                                  ▼
                     user reviews in their own inbox and sends
```

The trigger is `submitted` rather than `approved`, matching `README.md`: *"After you
apply, the app finds a suitable person at the company…"*. Drafting outreach for an
application that never went out would waste tokens and confuse the user.

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
| `status` | `ready_for_review` / `draft_created` / `skipped` / `failed` |
| `skip_reason` | populated for `skipped`, so a silent no-op is impossible |
| `subject`, `body` | |
| `flagged_unsupported_claims` | JSON, same shape as `Application` |
| `warm_signal_used` | JSON — what the email actually claimed as the connection |
| `gmail_draft_id` | set on `draft_created` |
| `created_at`, `updated_at` | |

`UNIQUE(application_id, contact_id)` — the whole duplicate guarantee in draft mode.

### `Suppression`

| column | notes |
|---|---|
| `id` | uuid pk |
| `profile_id` | nullable; **NULL = global**, applies to every user |
| `email` or `domain` | one of the two |
| `reason` | `opt_out` / `bounced` / `manual` |
| `created_at` | |

Checked before every draft. An opt-out from the public endpoint writes a **global** row:
someone who asks not to be contacted should not have to ask each user separately.

---

## Warm-signal ranking (REACH-C)

Candidates are ordered by the strongest shared signal found between the contact and the
user's own `ResumeFact` rows:

1. **Same former employer** — strongest. Verifiable and specific.
2. **Same university**
3. **Same city**
4. **No link** — a member of the relevant team. Cold, and ranked last.

The chosen signal is written to `Outreach.warm_signal_used`, because the email asserts
it ("we overlapped at Flipkart") and an assertion the user cannot verify is exactly what
the truth-check exists to stop. A signal that cannot be traced to a `ResumeFact` must not
be used.

**Ordering must be deterministic.** `GAPS.md` 6.6 records a real nondeterminism bug from
ordering by score with no tiebreaker: which job a capped run applied to was undefined
whenever two rows tied. Rank by `(signal_rank, contact.created_at, contact.id)` so ties
resolve the same way every run.

---

## `ContactSource` interface (REACH-B)

```
find(company: str, facts: list[ResumeFact], limit: int) -> list[ContactCandidate]
```

**First implementation is `ManualContactSource`** — the user enters a name, company and
optionally an email. No vendor, no cost, no legal question, and it exercises the entire
engine end to end. It is also the permanent fallback for any company an automated source
cannot cover.

**Why manual first rather than integrating a provider immediately:** the engine is the
part with the correctness properties (truth-check, suppression, dedupe, verification
gating). Wiring a paid provider into an unproven engine means debugging both at once.

The automated adapter is **REACH-E and the owner's decision** — it is a cost,
data-protection and vendor choice, not a technical one. Whatever is chosen implements the
same interface, so adding it is small.

---

## Email verification (REACH-C)

Verification gates whether a draft is created at all. Measured reality to design around:

- **`valid`** → draft.
- **`invalid`** → `skipped`, reason recorded.
- **`accept_all`** → the domain accepts every address, so mailbox existence is unknowable.
  Most corporate Google Workspace and Microsoft 365 tenants behave this way, so this will
  be the *common* case, not the edge case. Create the draft but mark the uncertainty in
  the review UI. The user is sending by hand and can judge.
- **`unknown`** → same handling as `accept_all`.

**On running verification ourselves:** `AfterShip/email-verifier` (Go, MIT — licence
verified 2026-10-08, so it carries none of the copyleft obligations that rule out
AGPL-licensed alternatives in this space) performs syntax, MX, disposable, role-account
and catch-all checks for free, but its own
README notes SMTP checking is **off by default** because *"most ISPs block outgoing SMTP
requests through port 25"*. The mailbox-existence check — the only layer that prevents a
bounce — needs outbound port 25, a PTR record and a reputable `MAIL FROM` domain. Most
cloud hosts block port 25 outright. It is also Go, while this API is Python, so it would
be a sidecar service rather than an import.

**Implication:** treat verification as best-effort metadata shown to the user, not as a
gate that can be trusted to prevent bounces. Since a human sends each email, a bounce
costs that user one bad address rather than a domain reputation.

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
expect a higher flag rate here than on bullets and treat the review-queue exception path
as a normal case rather than a rare one.

Every body ends with a plain opt-out line and a link to the unsubscribe endpoint.

---

## Opt-out (REACH-E)

`GET /outreach/unsubscribe/{signed_token}` — unauthenticated, signed, idempotent. Writes
a **global** `Suppression` row and returns a plain confirmation page.

Unauthenticated by necessity: the recipient has no account. Signed so the endpoint cannot
be used to enumerate or mass-suppress addresses. No Gmail read scope is involved, which
is the reason to use a link rather than reply-parsing.

---

## Error handling

| case | behaviour |
|---|---|
| No contacts found for the company | One `Outreach(status=skipped, skip_reason="no_contact_found")`. Visible, never a silent no-op |
| Contact suppressed | `skipped`, reason recorded; no draft, no Gmail call |
| Truth-check flags the draft | `ready_for_review`; **not** written to Gmail until resolved |
| Gmail credential missing or revoked | Stop before drafting; write a `Notification` asking the user to reconnect. Do not retry-loop |
| Gmail draft write fails | `failed` with the error type only — never the error body, which can echo the credential. `digest.smtp_sender` sets this precedent |
| Enqueue fails | Rows persist, return `503` with a "saved, try again" message, mirroring `main.py:1672` |

---

## Tests

| test | pins |
|---|---|
| `test_outreach_is_unique_per_application_and_contact` | The duplicate guarantee |
| `test_outreach_respects_suppression_list` | Including global (`profile_id IS NULL`) rows |
| `test_truth_check_flag_blocks_gmail_draft_creation` | A flagged draft never reaches Gmail |
| `test_warm_signal_ranking_prefers_former_employer` | Ordering, including the deterministic tiebreaker |
| `test_warm_signal_must_trace_to_a_resume_fact` | No asserted connection without a backing fact |
| `test_invalid_email_is_skipped_with_reason` | |
| `test_accept_all_email_still_drafts_but_marks_uncertainty` | The common case is handled, not treated as an error |
| `test_unsubscribe_token_adds_global_suppression` | |
| `test_unsubscribe_rejects_unsigned_token` | No enumeration |
| `test_contacts_are_not_visible_across_profiles` | The privacy property of profile scoping |

---

## Deliberately not building

- **Reply polling.** Needs `gmail.readonly`, a second restricted scope, to tell the user
  something their own inbox already shows them.
- **Follow-up sequences.** One ask per contact. Drip follow-ups are the single clearest
  thing that turns referral outreach into spam.
- **Direct send, the 10/day cap, and the at-most-once send lock.** Deferred with draft
  mode. If direct send is added later, all three come back together — they are one
  feature, not three.
- **A contact CRM.** Contacts exist to support an application, not as a managed list.
- **Cross-user contact dedupe.** See the privacy note under `Contact`.

---

## Open items for the owner

1. **Which automated `ContactSource`** (REACH-E), or whether manual entry is enough for
   v1. This is a cost and data-protection decision. `ManualContactSource` makes it
   deferrable without blocking anything.
2. **Expected flag rate.** `GAPS.md` 6.7's measurement was on resumes. Nobody has
   measured the truth-check against favour-asking prose. Worth one measured run on ~10
   real drafts before assuming the exception path is rare.
3. **Whether "draft created" should notify.** A draft silently appearing in Gmail may go
   unnoticed. An in-app `Notification` already exists as a mechanism; using it here is a
   one-line decision, not a design.
