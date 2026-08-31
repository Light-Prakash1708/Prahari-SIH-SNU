"""
PRAHARI · more than one photograph of the same problem

The rule this file defends: an extra photograph can only help by giving the
engine a BETTER picture to read. It must never become a way to keep uploading
until the engine says something the farmer wanted to hear.
"""
from __future__ import annotations

from tests.conftest import leaf_image


def _observe(client, headers, plot_id, kind="blight"):
    return client.post("/api/observations", headers=headers,
                       data={"plot_id": plot_id, "kind": "leaf", "image_role": "affected"},
                       files={"image": ("leaf.jpg", leaf_image(kind), "image/jpeg")})


def _add(client, headers, oid, kind="blight", role="underside"):
    return client.post(f"/api/observations/{oid}/images", headers=headers,
                       data={"image_role": role},
                       files={"image": ("leaf2.jpg", leaf_image(kind), "image/jpeg")})


def test_a_second_photograph_is_stored_with_its_role(client, farmer, plot):
    oid = _observe(client, farmer["headers"], plot["id"]).json()["observation"]["id"]

    r = _add(client, farmer["headers"], oid, role="underside")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["added_image"]["role"] == "underside"

    roles = [i["role"] for i in body["images"]]
    assert "affected" in roles and "underside" in roles
    assert len(body["images"]) == 2


def test_every_extra_photograph_passes_the_same_quality_gate(client, farmer, plot):
    """The gate is not relaxed for the second image. A blurred close-up is
    saved as the farmer's record but never fed to the engine."""
    oid = _observe(client, farmer["headers"], plot["id"]).json()["observation"]["id"]

    r = _add(client, farmer["headers"], oid, kind="bad", role="closeup")
    assert r.status_code == 201, r.text
    added = r.json()["added_image"]

    if not added["quality"]["ok"]:
        assert added["used_for_diagnosis"] is False
        assert "not used for the diagnosis" in r.json()["note"]
        # a failing check must carry the instruction that fixes it
        assert added["quality"]["failures"]
        for f in added["quality"]["failures"]:
            assert f["msg"] and f["mr"]
    else:
        assert added["used_for_diagnosis"] is True

    # either way the photograph is kept — it is the farmer's own record
    assert len(r.json()["images"]) == 2


def test_the_quality_gate_reports_its_numbers_not_just_a_verdict(client, farmer, plot):
    """An agronomist must be able to argue with the gate. Every check carries
    the measured value, the threshold it was compared against, and the unit."""
    oid = _observe(client, farmer["headers"], plot["id"]).json()["observation"]["id"]
    q = _add(client, farmer["headers"], oid).json()["added_image"]["quality"]

    for name in ("framing", "focus", "exposure"):
        check = q["checks"][name]
        assert isinstance(check["pass"], bool)
        assert check["value"] is not None
        assert check["needed"] is not None
        assert check["unit"]


def test_an_unknown_role_is_refused(client, farmer, plot):
    oid = _observe(client, farmer["headers"], plot["id"]).json()["observation"]["id"]
    r = client.post(f"/api/observations/{oid}/images", headers=farmer["headers"],
                    data={"image_role": "selfie"},
                    files={"image": ("x.jpg", leaf_image("blight"), "image/jpeg")})
    assert r.status_code == 400
    assert r.json()["error"] == "unknown_role"


def test_another_farmer_cannot_add_to_someone_elses_observation(
        client, farmer, farmer_b, plot):
    oid = _observe(client, farmer["headers"], plot["id"]).json()["observation"]["id"]
    r = _add(client, farmer_b["headers"], oid)
    assert r.status_code in (403, 404)


def test_adding_a_photograph_never_manufactures_confidence(client, farmer, plot):
    """Upload the same leaf four times. If the engine abstained on the first,
    it must still abstain — repetition is not evidence.

    This is the failure mode that matters: a farmer who keeps photographing
    until the app names something has been given a diagnosis by persistence.
    """
    first = _observe(client, farmer["headers"], plot["id"], kind="healthy").json()
    oid = first["observation"]["id"]
    abstained_first = first["diagnosis"]["abstain"]

    last = None
    for role in ("whole_plant", "underside", "closeup", "stem"):
        last = _add(client, farmer["headers"], oid, kind="healthy", role=role).json()

    if abstained_first:
        assert last["diagnosis"]["abstain"] is True, (
            "the engine abstained on the first photograph and was talked out of it "
            "by repetition of the same leaf")
    # confidence must not have been inflated by the extra copies
    if not abstained_first and last["diagnosis"].get("differential"):
        top_first = first["diagnosis"]["differential"][0]["confidence"]
        top_last = last["diagnosis"]["differential"][0]["confidence"]
        assert top_last <= top_first + 1e-6, (
            "posterior rose merely because the same leaf was uploaded again")


def test_the_roles_are_documented_where_the_farmer_can_act_on_them(client, farmer, plot):
    """The roles exist to tell a farmer WHAT to photograph next. If the list
    ever loses its instructions, the feature is just five opaque strings."""
    from app.routers.observations import IMAGE_ROLES
    assert set(IMAGE_ROLES) == {"whole_plant", "affected", "closeup", "underside", "stem"}
    for text in IMAGE_ROLES.values():
        assert len(text) > 20
