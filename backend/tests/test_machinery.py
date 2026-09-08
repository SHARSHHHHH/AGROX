"""Machinery rental marketplace tests."""

import io

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.ml import machinery_knowledge as kb
from app.services import machinery as svc


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def auth(client):
    r = client.post("/api/auth/login",
                    data={"username": "farmer@demo.com", "password": "demo123"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="module")
def other_auth(client):
    r = client.post("/api/auth/login",
                    data={"username": "balcony@demo.com", "password": "demo123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# ---------------------------------------------------------------- knowledge


def test_catalog_is_complete():
    for key, m in kb.MACHINERY_KB.items():
        for field in ("name", "category", "stage", "what_it_does",
                      "when_needed", "suits_land", "typical_daily_rate",
                      "crops", "tip"):
            assert field in m, f"{key} missing {field}"
        low, high = m["typical_daily_rate"]
        assert 0 < low < high, f"{key} has a nonsensical price band"
        assert m["stage"] in kb.STAGE_ORDER


def test_catalog_endpoint(client):
    body = client.get("/api/machinery/catalog").json()
    assert len(body["machines"]) >= 14
    assert "power" in body["categories"]


def test_guide_orders_by_season_stage(client, auth):
    body = client.get("/api/machinery/guide", headers=auth,
                      params={"crop": "wheat", "land_size_acres": 5,
                              "use_my_farm": False}).json()
    stages = [kb.STAGE_ORDER.index(m["stage"]) for m in body["recommended"]]
    assert stages == sorted(stages), "machines must follow the season order"


def test_guide_excludes_machines_too_big_for_the_land(client, auth):
    """A 1-acre farmer should not be told to hire a combine harvester."""
    small = client.get("/api/machinery/guide", headers=auth,
                       params={"crop": "wheat", "land_size_acres": 1,
                               "use_my_farm": False}).json()
    keys = {m["key"] for m in small["recommended"]}
    assert "harvester" not in keys
    assert any(m["key"] == "harvester" for m in small["not_suitable"])


def test_guide_includes_harvester_for_larger_land(client, auth):
    big = client.get("/api/machinery/guide", headers=auth,
                     params={"crop": "wheat", "land_size_acres": 10,
                             "use_my_farm": False}).json()
    assert "harvester" in {m["key"] for m in big["recommended"]}


def test_guide_carries_price_disclaimer(client, auth):
    body = client.get("/api/machinery/guide", headers=auth,
                      params={"use_my_farm": False}).json()
    assert "indicative" in body["disclaimer"].lower()


# ---------------------------------------------------------------- phone handling


@pytest.mark.parametrize("raw,expected", [
    ("9876543210", "9876543210"),
    ("+91 9876543210", "9876543210"),
    ("+919876543210", "9876543210"),
    ("09876543210", "9876543210"),
    ("98765-43210", "9876543210"),
    ("98765 43210", "9876543210"),
])
def test_valid_indian_mobiles_accepted(raw, expected):
    assert svc.normalise_phone(raw) == expected


@pytest.mark.parametrize("raw", [
    "1234567890",     # cannot start with 1
    "5876543210",     # cannot start with 5
    "98765",          # too short
    "98765432101",    # too long
    "abcdefghij", "",
])
def test_invalid_numbers_rejected(raw):
    assert svc.normalise_phone(raw) is None


def test_phone_masking_hides_the_middle():
    masked = svc.mask_phone("9876543210")
    assert masked == "98xxxxx210"
    assert "76543" not in masked


# ---------------------------------------------------------------- search


def test_search_requires_auth(client):
    assert client.get("/api/machinery/search").status_code == 401


def test_search_returns_seeded_listings(client, auth):
    body = client.get("/api/machinery/search", headers=auth).json()
    assert body["total_matching"] >= 14


def test_browse_never_exposes_the_phone_number(client, auth):
    """The whole listing feed must not be a phone-number scrape."""
    body = client.get("/api/machinery/search", headers=auth).json()
    for item in body["items"]:
        assert "contact_phone" not in item
        assert "x" in item["contact_preview"]


def test_filter_by_machine_type(client, auth):
    body = client.get("/api/machinery/search", headers=auth,
                      params={"machine_key": "tractor"}).json()
    assert body["total_matching"] >= 1
    assert all(i["machine_key"] == "tractor" for i in body["items"])


def test_filter_by_state(client, auth):
    body = client.get("/api/machinery/search", headers=auth,
                      params={"state": "Punjab"}).json()
    assert all(i["state"] == "Punjab" for i in body["items"])
    assert body["total_matching"] >= 2


def test_filter_by_max_rate(client, auth):
    body = client.get("/api/machinery/search", headers=auth,
                      params={"max_rate": 1000}).json()
    assert all(i["daily_rate"] <= 1000 for i in body["items"])


def test_distance_sorting_puts_nearest_first(client, auth):
    body = client.get("/api/machinery/search", headers=auth,
                      params={"lat": 22.72, "lon": 75.86,
                              "sort": "distance"}).json()
    distances = [i["distance_km"] for i in body["items"] if i["distance_km"]]
    assert distances == sorted(distances)


def test_radius_filter_excludes_far_listings(client, auth):
    near = client.get("/api/machinery/search", headers=auth,
                      params={"lat": 22.72, "lon": 75.86,
                              "radius_km": 100}).json()
    far = client.get("/api/machinery/search", headers=auth,
                     params={"lat": 22.72, "lon": 75.86,
                             "radius_km": 2000}).json()
    assert near["total_matching"] < far["total_matching"]
    assert all(i["distance_km"] <= 100 for i in near["items"]
               if i["distance_km"] is not None)


def test_nearby_also_resolves_the_place_name(client, auth):
    body = client.get("/api/machinery/nearby", headers=auth,
                      params={"lat": 22.72, "lon": 75.86,
                              "radius_km": 150}).json()
    assert body["location"]["district"] == "Indore"
    assert body["total_matching"] >= 1


def test_price_sorting(client, auth):
    body = client.get("/api/machinery/search", headers=auth,
                      params={"sort": "price_low"}).json()
    rates = [i["daily_rate"] for i in body["items"]]
    assert rates == sorted(rates)


# ---------------------------------------------------------------- create


def _form(**over):
    data = {"machine_key": "tractor", "daily_rate": "1500",
            "contact_phone": "9876543210", "state": "Madhya Pradesh",
            "district": "Indore", "title": "Test tractor",
            "condition": "good"}
    data.update(over)
    return data


def test_create_listing(client, auth):
    r = client.post("/api/machinery/listing", headers=auth, data=_form())
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    assert r.json()["listing"]["daily_rate"] == 1500


def test_create_with_photo(client, auth):
    png = (b"\x89PNG\r\n\x1a\n" + b"\x00" * 80)
    r = client.post("/api/machinery/listing", headers=auth,
                    data=_form(title="With photo"),
                    files={"photo": ("t.png", io.BytesIO(png), "image/png")})
    assert r.status_code == 200
    assert r.json()["listing"]["image_path"].startswith("/uploads/")


def test_bad_phone_rejected_with_a_useful_message(client, auth):
    r = client.post("/api/machinery/listing", headers=auth,
                    data=_form(contact_phone="12345"))
    assert r.status_code == 422
    assert any("mobile" in e.lower() for e in r.json()["detail"]["errors"])


def test_zero_rate_rejected(client, auth):
    r = client.post("/api/machinery/listing", headers=auth,
                    data=_form(daily_rate="0"))
    assert r.status_code == 422


def test_unknown_machine_rejected(client, auth):
    r = client.post("/api/machinery/listing", headers=auth,
                    data=_form(machine_key="spaceship"))
    assert r.status_code == 422


def test_absurd_rate_rejected(client, auth):
    r = client.post("/api/machinery/listing", headers=auth,
                    data=_form(daily_rate="99999999"))
    assert r.status_code == 422


def test_unsupported_photo_type_rejected(client, auth):
    r = client.post("/api/machinery/listing", headers=auth, data=_form(),
                    files={"photo": ("x.exe", io.BytesIO(b"MZ"),
                                     "application/octet-stream")})
    assert r.status_code == 400


# ---------------------------------------------------------------- contact


def test_contact_reveals_number_with_a_safety_note(client, auth):
    listings = client.get("/api/machinery/search", headers=auth).json()["items"]
    lid = listings[0]["id"]
    body = client.post(f"/api/machinery/listing/{lid}/contact", headers=auth).json()

    assert body["ok"] is True
    assert len(body["contact_phone"]) == 10
    assert "BEFORE any payment" in body["safety_note"]
    assert "does not verify" in body["safety_note"]


def test_contact_on_missing_listing_404s(client, auth):
    assert client.post("/api/machinery/listing/999999/contact",
                       headers=auth).status_code == 404


# ---------------------------------------------------------------- ownership


def test_my_listings_shows_own_full_number(client, auth):
    body = client.get("/api/machinery/my-listings", headers=auth).json()
    assert body["count"] >= 1
    assert len(body["items"][0]["contact_phone"]) == 10


def test_cannot_delete_someone_elses_listing(client, auth, other_auth):
    mine = client.get("/api/machinery/my-listings", headers=auth).json()
    lid = mine["items"][0]["id"]
    assert client.delete(f"/api/machinery/listing/{lid}",
                         headers=other_auth).status_code == 403


def test_cannot_toggle_someone_elses_availability(client, auth, other_auth):
    mine = client.get("/api/machinery/my-listings", headers=auth).json()
    lid = mine["items"][0]["id"]
    r = client.patch(f"/api/machinery/listing/{lid}/availability",
                     headers=other_auth, params={"available": False})
    assert r.status_code == 403


def test_owner_can_toggle_and_unavailable_drops_out_of_search(client, auth):
    mine = client.get("/api/machinery/my-listings", headers=auth).json()
    lid = mine["items"][0]["id"]

    client.patch(f"/api/machinery/listing/{lid}/availability",
                 headers=auth, params={"available": False})
    ids = {i["id"] for i in
           client.get("/api/machinery/search", headers=auth).json()["items"]}
    assert lid not in ids

    client.patch(f"/api/machinery/listing/{lid}/availability",
                 headers=auth, params={"available": True})
    ids = {i["id"] for i in
           client.get("/api/machinery/search", headers=auth).json()["items"]}
    assert lid in ids


def test_owner_can_delete(client, auth):
    client.post("/api/machinery/listing", headers=auth,
                data=_form(title="Delete me"))
    mine = client.get("/api/machinery/my-listings", headers=auth).json()
    lid = next(i["id"] for i in mine["items"] if i["title"] == "Delete me")

    assert client.delete(f"/api/machinery/listing/{lid}",
                         headers=auth).status_code == 200
    remaining = {i["title"] for i in
                 client.get("/api/machinery/my-listings", headers=auth).json()["items"]}
    assert "Delete me" not in remaining


def test_states_list_covers_india(client, auth):
    body = client.get("/api/machinery/states").json()
    assert len(body["states"]) >= 30
    for s in ("Madhya Pradesh", "Punjab", "Tamil Nadu", "Kerala".replace("Kerala", "Keralam")):
        assert s in body["states"]
