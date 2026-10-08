# Plan: Gmail credentials (REACH-A)

**Status:** not started. This is the prerequisite for `docs/PLAN-OUTREACH.md` — no
outreach work can begin until it lands, because ADR-003 requires the OAuth refresh
token encrypted at rest and there is currently no working encryption key.

**Stage prefix.** This plan and `PLAN-OUTREACH.md` share the `REACH-*` prefix. Per the
naming convention in `PLAN-JOB-COLLECTION.md`, never write a bare "Phase N" — two other
plans already use numbers for unrelated work. This doc is **REACH-A**; the outreach
engine is **REACH-B…E**.

---

## Why this exists

ADR-003 (Accepted, 2026-08-15) decided that referral outreach sends from the user's own
Gmail via OAuth rather than from a platform domain. It is explicit about what that
obliges us to build:

> We hold a credential that can send mail as the user. This is the highest-value secret
> in the system: KMS-backed encryption, never logged, never returned by any endpoint,
> revocable from the settings page in one click.

None of that exists yet. `GAPS.md` 5.6 records the blocking half: **`ENCRYPTION_KEY` is
reserved but unset**, and real KMS was deferred. So today there is nowhere safe to put a
Gmail refresh token, which is why this is a separate, independently-shippable stage
rather than step one of a larger outreach PR.

## What this blocks

Everything in `PLAN-OUTREACH.md`. A draft cannot be written into a user's Gmail without
a stored, decryptable credential for that user.

---

## The scope decision, stated honestly

REACH-B creates **drafts** in the user's Gmail; the user presses send themselves. The
narrowest Google scope that can create a draft is
`https://www.googleapis.com/auth/gmail.compose`.

Two things about that are worth writing down rather than discovering later:

1. **`gmail.compose` also permits sending.** There is no "drafts but never send" Gmail
   scope. So even though the product will not call `messages.send`, the credential we
   hold *could*. ADR-003's "highest-value secret" framing therefore applies in full —
   draft-only mode reduces product risk, not credential risk.
2. **It is a Google *restricted* scope**, like every meaningful Gmail scope. Restricted
   scopes require Google's verification process, which can require a third-party
   security assessment on a multi-week timeline. ADR-003 anticipated this: *"that is
   real work and a real review timeline. Start it early."*

**How we ship anyway, now:** keep the OAuth consent screen in **Testing** mode. Testing
mode allows up to **100 explicitly-listed test users** with no verification at all. The
product currently targets the owner plus 5–7 friends (`README.md`), so verification is
not on the critical path and only becomes blocking past 100 users. Record that ceiling
somewhere a future session will see it, because hitting it looks like "OAuth suddenly
broke" rather than "we outgrew Testing mode".

---

## Design

### Encryption helper

A single module with `encrypt(plaintext) -> str` and `decrypt(ciphertext) -> str`,
reading a key from the existing `ENCRYPTION_KEY` setting in `core/config.py`.

- **Fail closed at import/boot, not at first use.** A missing or malformed key must stop
  the process with a clear error. The failure mode to avoid is a credential written with
  a silently-empty key.
- Symmetric authenticated encryption via `cryptography`'s Fernet. `cryptography` is
  already an indirect dependency of the existing stack; confirm before adding it to
  `requirements.txt`, and if it needs adding, that is a dependency change requiring the
  owner's approval per `DEPENDENCIES.md`.
- **Not KMS.** ADR-003 says KMS-backed, and a real KMS is still deferred. A local key
  from the environment is the deliberate interim, and it is strictly better than the
  current state (no encryption at all). Mark it with a `ponytail:` comment naming the
  ceiling and the upgrade path, so it is a tracked shortcut rather than a silent one.

### `GmailCredential` model

| column | notes |
|---|---|
| `id` | uuid pk |
| `user_id` | FK to `users`, **unique** — one Gmail connection per user |
| `refresh_token_encrypted` | ciphertext only; the plaintext never touches a column |
| `email_address` | which Gmail account is connected, so the UI can show it |
| `scopes` | what was actually granted, as granted (not what was requested) |
| `connected_at` | |
| `revoked_at` | NULL = live. Soft revoke, so a revoke is auditable |

One migration. No relationship exposed on `User` that a response model could
accidentally serialise — see the test below.

### Endpoints

- `GET /gmail/authorize` — returns the Google consent URL with a signed state parameter.
- `GET /gmail/callback` — exchanges the code, encrypts and stores the refresh token,
  records the granted scopes.
- `GET /gmail/status` — returns `{connected, email_address, connected_at}` and nothing
  more. Never the token, never the ciphertext.
- `DELETE /gmail/connection` — ADR-003's "revocable in one click": calls Google's token
  revocation endpoint, then sets `revoked_at`. Revoking at Google matters — clearing our
  row alone would leave a live grant the user believes is gone.

### Error handling

- **User denies consent** → callback returns cleanly to the settings page with a
  message. Not an error state to retry.
- **Granted scopes are narrower than requested** → store what was granted and mark the
  connection unusable for drafting, with a message naming the missing scope. Google
  allows partial grants; discovering that at draft time would surface as a confusing
  500.
- **Refresh token rejected later** (user revoked at Google, or password change) → set
  `revoked_at`, write a `Notification` telling the user to reconnect, and stop. Never
  retry-loop on an invalid grant.
- **Google returns no refresh token** (happens when the user has already granted and
  `prompt=consent` is omitted) → request with `access_type=offline` and
  `prompt=consent`, and treat a missing refresh token as a hard failure with a clear
  message rather than storing a credential that expires in an hour.

---

## Tests

| test | pins |
|---|---|
| `test_gmail_token_never_returned_by_any_endpoint` | Walks every route in `app.routes`, calls the ones that touch Gmail, and asserts no response body contains the token or its ciphertext. ADR-003 says "never returned by any endpoint" — that is a property worth enforcing mechanically, because the regression is a one-line response-model change by someone who has not read ADR-003. |
| `test_token_is_encrypted_at_rest` | Reads the raw column and asserts it does not contain the plaintext. |
| `test_missing_encryption_key_fails_closed` | A missing/garbage key raises at boot rather than writing an unencrypted credential. |
| `test_revoke_calls_google_then_marks_revoked` | Revocation reaches Google, not just our row. |
| `test_partial_scope_grant_is_marked_unusable` | A narrowed grant is detected at connect time. |
| `test_token_is_never_logged` | Captures log output across connect and refresh and asserts the secret does not appear. The existing `digest.smtp_sender` has the same discipline for the SMTP password (`apps/api/digest.py`) and is worth copying. |

---

## Deliberately not building

- **Real KMS.** Deferred by ADR-003 and still deferred. The local key is the interim and
  is marked as such.
- **Multiple Gmail accounts per user.** `user_id` is unique. One account covers the
  stated use case; a second one is YAGNI at 6–8 users.
- **Any read scope.** No `gmail.readonly`, no `gmail.metadata`. REACH-B deliberately
  does not poll for replies — the user sees replies in their own inbox.
- **Google verification submission.** Testing mode covers the current user count. Revisit
  at ~80 users, not before.

---

## Open items for the owner

1. **Google Cloud project + OAuth client.** Requires a Google account and consent-screen
   configuration in the Cloud console. Cannot be done from code; the owner creates the
   client and provides `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`.
2. **Test-user list.** Testing mode requires each user's Google address be listed
   explicitly in the consent screen. Adding a friend means adding them there too.
3. **`cryptography` in `requirements.txt`** if it is not already a direct dependency —
   a dependency change, so the owner approves it.
