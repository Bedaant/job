"""GAPS 2.4 — an ACTIVE campaign must name at least one role.

Why this became necessary. ADR-021 stopped `FEED_KEYWORDS` gating ingest, so
discovery stores whole boards (the pool went 1,768 -> 5,119 on the first
unfiltered run). `campaigns._in_bounds` applies its title filter only
`if campaign.roles`, and `roles` defaults to `[]` — so before ADR-021 the global
keyword list was an *accidental* backstop: a roles-less campaign still only ever
saw product roles, because nothing else had been collected.

With the backstop gone, a roles-less active campaign draws candidates from the
entire pool, gated only by `min_match_score` against the résumé centroid and
`passes_hard_filters` — which `matching/filters.py` deliberately builds so that
missing data never excludes a job. With `auto_submit` on, that is an autonomous
apply path to postings nobody asked for.

Enforced at the WRITE boundary, not in `_in_bounds`. Making `_in_bounds` fail
closed would silently stop existing roles-less campaigns from matching anything,
with no error to explain why; rejecting the write says so out loud. ADR-015 §2
also lists roles as part of what the user approves once, so an active campaign
without them is incoherent on its own terms.

Two paths can produce one, and both are PATCH — creation always lands in `draft`
(`models.Campaign.status` default), so there is no third:
  1. activating a roles-less draft or paused campaign
  2. clearing `roles` on a campaign that is already active

A draft may be roles-less: that is the half-filled form, and it is only on
activation that the invariant has to hold.
"""
import models
from tests.test_campaigns import _auth, _client


def _draft(client, headers, **kwargs):
    profile = client.post("/profiles", json={"persona": "developer"}, headers=headers).json()
    body = {"profile_id": profile["id"], "name": "My search", **kwargs}
    resp = client.post("/campaigns", json=body, headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "draft", "campaigns are created as drafts"
    return resp.json()


def test_activating_a_roles_less_campaign_is_refused():
    client, _ = _client()
    headers = _auth(client, "roles1@example.com")
    campaign = _draft(client, headers, roles=[])

    resp = client.patch(f"/campaigns/{campaign['id']}", json={"status": "active"}, headers=headers)

    assert resp.status_code == 422, resp.text
    assert "role" in resp.json()["detail"].lower()


def test_activating_with_roles_is_allowed():
    client, _ = _client()
    headers = _auth(client, "roles2@example.com")
    campaign = _draft(client, headers, roles=["Product Manager"])

    resp = client.patch(f"/campaigns/{campaign['id']}", json={"status": "active"}, headers=headers)

    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "active"


def test_clearing_roles_on_an_active_campaign_is_refused():
    """The second path: already active, and the edit would widen it to the
    whole pool."""
    client, _ = _client()
    headers = _auth(client, "roles3@example.com")
    campaign = _draft(client, headers, roles=["Product Manager"])
    assert client.patch(f"/campaigns/{campaign['id']}", json={"status": "active"},
                        headers=headers).status_code == 200

    resp = client.patch(f"/campaigns/{campaign['id']}", json={"roles": []}, headers=headers)

    assert resp.status_code == 422, resp.text


def test_a_draft_may_be_roles_less():
    """A half-filled form must stay editable; the invariant binds on activation."""
    client, _ = _client()
    headers = _auth(client, "roles4@example.com")
    campaign = _draft(client, headers, roles=["Product Manager"])

    resp = client.patch(f"/campaigns/{campaign['id']}", json={"roles": []}, headers=headers)

    assert resp.status_code == 200, resp.text
    assert resp.json()["roles"] == []


def test_blank_roles_do_not_satisfy_the_requirement():
    """`_in_bounds` builds `title.ilike('%%')` for an empty string, which matches
    EVERY job — so whitespace-only roles are exactly as wide open as none, and a
    plain truthiness check on the list would have let them through."""
    client, _ = _client()
    headers = _auth(client, "roles5@example.com")
    campaign = _draft(client, headers, roles=["", "   "])

    resp = client.patch(f"/campaigns/{campaign['id']}", json={"status": "active"}, headers=headers)

    assert resp.status_code == 422, resp.text


def test_roles_and_activation_in_one_payload_is_allowed():
    client, _ = _client()
    headers = _auth(client, "roles6@example.com")
    campaign = _draft(client, headers, roles=[])

    resp = client.patch(
        f"/campaigns/{campaign['id']}",
        json={"status": "active", "roles": ["SRE"]},
        headers=headers,
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "active" and resp.json()["roles"] == ["SRE"]


def test_pausing_an_active_campaign_still_works():
    """Regression guard: the check must only bind on the ACTIVE end state, or
    pause/archive would start failing for roles-less legacy rows."""
    client, _ = _client()
    headers = _auth(client, "roles7@example.com")
    campaign = _draft(client, headers, roles=["Product Manager"])
    client.patch(f"/campaigns/{campaign['id']}", json={"status": "active"}, headers=headers)

    resp = client.patch(f"/campaigns/{campaign['id']}", json={"status": "paused"}, headers=headers)

    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "paused"


def test_an_existing_roles_less_active_row_can_still_be_paused():
    """Rows written before this check exist (the DB had four roles-less-adjacent
    campaigns). The invariant must not trap them: pausing or archiving one is
    exactly how a user would fix it, so those transitions stay open."""
    client, SessionLocal = _client()
    headers = _auth(client, "roles8@example.com")
    campaign = _draft(client, headers, roles=["Product Manager"])

    db = SessionLocal()
    row = db.query(models.Campaign).filter(models.Campaign.id == campaign["id"]).one()
    row.status = models.CampaignStatus.active
    row.roles = []          # the pre-check state this guard is about
    db.commit()
    db.close()

    resp = client.patch(f"/campaigns/{campaign['id']}", json={"status": "paused"}, headers=headers)

    assert resp.status_code == 200, resp.text
