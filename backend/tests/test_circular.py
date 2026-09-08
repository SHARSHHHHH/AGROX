"""Circular farming module tests.

The important ones guard three claims the spec makes explicitly:

  * estimates are never presented as measured production
  * the same digestate is NOT recommended equally for every crop
  * residue is not all pushed into the digester

Those are the three places where a plausible-looking shortcut would give a
farmer wrong advice, so each has a test that would fail if someone later
"simplified" the logic.
"""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.database.db import SessionLocal
from app.main import app
from app.models.models import (BiogasAssessment, BiogasLog, BiogasPlant,
                               CircularChoice,
                               CropResidueRecord,
                               DigestateAllocation, Farm, Livestock, User)
from app.services import biogas as bg
from app.services import manure as mn


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def auth(client):
    r = client.post("/api/auth/login",
                    data={"username": "farmer@demo.com", "password": "demo123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def demo(db):
    return db.query(User).filter(User.email == "farmer@demo.com").first()


@pytest.fixture
def clean(db, demo):
    """Start from no livestock/allocations so counts are deterministic."""
    # Logs before plants: the log rows reference the plant.
    #
    # BiogasPlant and CircularChoice are reset here because both now PERSIST
    # per farmer by design. That persistence is the feature — the page must
    # stop re-asking questions it has already been told the answer to — but it
    # also means one test's registered plant would otherwise still be there
    # for the next one.
    for model in (BiogasLog, Livestock, DigestateAllocation, BiogasAssessment,
                  CropResidueRecord, CircularChoice, BiogasPlant):
        db.query(model).filter(model.user_id == demo.id).delete()
    db.commit()
    yield
    for model in (BiogasLog, Livestock, DigestateAllocation, BiogasAssessment,
                  CropResidueRecord, CircularChoice, BiogasPlant):
        db.query(model).filter(model.user_id == demo.id).delete()
    db.commit()


# ============================================================ estimation

def test_dung_scales_with_herd_size():
    one = bg.dung_from_livestock([{"animal_type": "cow", "count": 1}])
    four = bg.dung_from_livestock([{"animal_type": "cow", "count": 4}])
    assert four["total_kg_per_day"]["mid"] == pytest.approx(
        one["total_kg_per_day"]["mid"] * 4)


def test_farmer_figure_beats_the_typical_range():
    """They can see their own shed; we cannot."""
    out = bg.dung_from_livestock(
        [{"animal_type": "cow", "count": 3, "dung_kg_per_day": 45}])
    assert out["used_farmer_figure"] is True
    assert out["total_kg_per_day"]["mid"] == 45


def test_every_estimate_is_a_range_not_a_point():
    """A single figure invites a farmer to spend money against it."""
    e = bg.estimate(dung_kg_per_day=60)
    for field in ("biogas_m3_per_day", "digestate_kg_per_day",
                  "digestate_kg_per_month"):
        assert set(e[field]) == {"low", "high", "mid"}
        assert e[field]["low"] < e[field]["high"]


def test_estimates_are_labelled_estimated():
    e = bg.estimate(dung_kg_per_day=60)
    assert e["confidence"] == "ESTIMATED"
    assert "not guaranteed production" in e["caveat"]


def test_residue_is_capped_in_a_small_digester():
    """Too much fibrous material mats and blocks the outlet."""
    e = bg.estimate(dung_kg_per_day=40, residue_kg_per_day=500)
    assert e["residue_capped"] is True
    assert e["residue_used_kg_per_day"] < 500


# =========================================================== feasibility

def test_too_few_cattle_is_not_yet():
    out = bg.assess(dung_kg_per_day=10, water_availability="adequate")
    assert out["verdict"] in (bg.VERDICT_NOT_YET, bg.VERDICT_POSSIBLE)
    assert any("below" in b for b in out["blockers"])


def test_scarce_water_is_a_blocker():
    out = bg.assess(dung_kg_per_day=80, water_availability="scarce")
    assert any("water" in b.lower() for b in out["blockers"])


def test_good_farm_is_suitable_but_still_qualified():
    out = bg.assess(dung_kg_per_day=80, water_availability="adequate")
    assert out["verdict"] == bg.VERDICT_SUITABLE
    # Never a guarantee, always "appears suitable for considering".
    assert "appears suitable" in out["reason"]
    assert "not an engineering assessment" in out["caveat"]


def test_irregular_collection_downgrades_the_verdict():
    out = bg.assess(dung_kg_per_day=80, water_availability="adequate",
                    collection_regular=False)
    assert out["verdict"] == bg.VERDICT_POSSIBLE


def test_plant_is_sized_from_dung_not_from_gas():
    """Regression: sizing used to be derived from the GAS estimate.

    That double-counted, because the gas figure is itself derived from the
    dung — 78 kg/day produced a "10 m3" plant when the design norm of ~25 kg
    per m3 gives 3 m3. Selling a farmer three times the capacity they can feed
    is expensive, and an underfed digester runs badly.
    """
    assert bg._plant_size_from_dung(25) == 1.0
    assert bg._plant_size_from_dung(50) == 2.0
    assert bg._plant_size_from_dung(78) == 3.0      # the MNRE worked example
    assert bg._plant_size_from_dung(200) == 8.0


def test_plant_size_ignores_residue_in_the_gas_figure():
    """Adding residue raises gas, but must not inflate the plant size."""
    without = bg.estimate(dung_kg_per_day=78)
    withres = bg.estimate(dung_kg_per_day=78, residue_kg_per_day=26)
    assert withres["biogas_m3_per_day"]["mid"] > without["biogas_m3_per_day"]["mid"]
    assert withres["suggested_plant_size_m3"] == without["suggested_plant_size_m3"]


def test_sizing_states_it_needs_professional_confirmation():
    e = bg.estimate(dung_kg_per_day=78)
    assert "technician" in e["plant_size_basis"].lower()


# ================================================== crop-specific manure

def test_legume_gets_far_less_than_a_cereal():
    """The spec's central rule: not the same quantity for every crop."""
    rice = mn.recommend_for_crop(crop="rice", area_acres=1)
    soy = mn.recommend_for_crop(crop="soybean", area_acres=1)
    assert soy["rate_kg_per_acre"]["mid"] < rice["rate_kg_per_acre"]["mid"] / 2
    assert "legume" in " ".join(soy["why"]).lower()


def test_root_crop_is_flagged_for_excess_nitrogen():
    r = mn.recommend_for_crop(crop="potato", area_acres=1)
    assert r["group"] == "root_careful"
    assert "tops" in " ".join(r["why"]).lower()


def test_high_soil_nitrogen_reduces_the_rate():
    plain = mn.recommend_for_crop(crop="rice", area_acres=1)
    rich = mn.recommend_for_crop(crop="rice", area_acres=1,
                                 soil={"nitrogen": 60})
    assert rich["rate_kg_per_acre"]["mid"] < plain["rate_kg_per_acre"]["mid"]


def test_manure_advice_carries_a_food_safety_note():
    r = mn.recommend_for_crop(crop="tomato", area_acres=1)
    assert "raw" in r["food_safety_note"].lower()


def test_unknown_crop_is_not_given_a_confident_rate():
    r = mn.recommend_for_crop(crop="dragonfruit", area_acres=1)
    assert r["available"] is False


# ======================================================= residue routing

def test_wheat_straw_goes_to_fodder_not_biogas():
    """It is worth more fed than digested."""
    r = mn.route_residue(crop="wheat", has_biogas=True, has_cattle=True)
    assert r["recommended_route"] == "fodder"


def test_diseased_residue_is_composted():
    r = mn.route_residue(crop="tomato", has_biogas=True, has_cattle=True)
    assert r["recommended_route"] == "compost"
    assert "wilt" in r["why"].lower() or "blight" in r["why"].lower()


def test_biogas_is_not_offered_without_a_digester():
    r = mn.route_residue(crop="rice", has_biogas=False, has_cattle=False)
    routes = [r["recommended_route"]] + [o["route"] for o in r["other_options"]]
    assert "biogas" not in routes


def test_burning_is_always_discouraged():
    r = mn.route_residue(crop="rice", has_biogas=True, has_cattle=True)
    assert "burn" in r["never"].lower()


# ================================================================== API

def test_assessment_without_cattle_asks_for_them(client, auth, clean):
    body = client.get("/api/circular/assessment", headers=auth).json()
    assert body["has_livestock"] is False
    assert "cattle" in body["message"].lower()


def test_full_flow_livestock_to_surplus(client, auth, clean):
    r = client.post("/api/circular/livestock", headers=auth, json=[
        {"animal_type": "cow", "count": 4},
        {"animal_type": "buffalo", "count": 2}])
    assert r.status_code == 200
    assert r.json()["dung"]["total_kg_per_day"]["mid"] > 0

    a = client.get("/api/circular/assessment", headers=auth).json()
    assert a["has_livestock"] is True
    assert a["confidence"] == "ESTIMATED"
    assert a["estimates"]["biogas_m3_per_day"]["mid"] > 0

    inv = client.get("/api/circular/digestate", headers=auth).json()
    total = inv["total_available_kg"]
    assert total > 0
    assert inv["potential_surplus_kg"] == total       # nothing reserved yet

    keep = round(total * 0.6)
    alloc = client.post("/api/circular/digestate/allocate", headers=auth,
                        json={"reserved_own_farm_kg": keep}).json()
    assert alloc["reserved_own_farm_kg"] == keep
    # Surplus is derived, never stored, so it must always reconcile.
    assert (alloc["reserved_own_farm_kg"]
            + alloc["potential_surplus_kg"]) == pytest.approx(total, abs=2)


def test_cannot_reserve_more_than_available(client, auth, clean):
    client.post("/api/circular/livestock", headers=auth,
                json=[{"animal_type": "cow", "count": 3}])
    res = client.post("/api/circular/digestate/allocate", headers=auth,
                      json={"reserved_own_farm_kg": 9_999_999})
    assert res.status_code == 400


def test_cannot_list_more_surplus_than_exists(client, auth, clean):
    client.post("/api/circular/livestock", headers=auth,
                json=[{"animal_type": "cow", "count": 3}])
    inv = client.get("/api/circular/digestate", headers=auth).json()
    res = client.post("/api/circular/surplus/list", headers=auth, json={
        "quantity_kg": inv["total_available_kg"] + 10_000})
    assert res.status_code == 400


def test_surplus_listing_starts_unverified(client, auth, clean, db):
    """Farmer-to-farmer listings are checked before reaching other farmers."""
    from app.models.models import SupplyOffer
    client.post("/api/circular/livestock", headers=auth,
                json=[{"animal_type": "cow", "count": 5}])
    inv = client.get("/api/circular/digestate", headers=auth).json()
    res = client.post("/api/circular/surplus/list", headers=auth, json={
        "quantity_kg": min(100, inv["potential_surplus_kg"]),
        "suitable_crops": ["rice"]})
    assert res.status_code == 200
    assert res.json()["verified"] is False
    db.query(SupplyOffer).filter(SupplyOffer.id == res.json()["id"]).delete()
    db.commit()


def test_manure_compare_shows_different_rates(client, auth):
    body = client.get("/api/circular/manure/compare?area_acres=1",
                      headers=auth).json()
    rates = {c["crop"]: c["rate_kg_per_acre"]["mid"] for c in body["crops"]}
    assert len(set(rates.values())) > 1, "every crop got the same rate"
    assert rates["soybean"] < rates["rice"]


def test_plan_returns_the_whole_cycle(client, auth, clean):
    client.post("/api/circular/livestock", headers=auth,
                json=[{"animal_type": "cow", "count": 4}])
    body = client.get("/api/circular/plan", headers=auth).json()
    for step in ("1_feasibility", "2_biogas_potential", "3_preparation",
                 "4_digestate", "5_crop_use", "8_residue", "9_sensors"):
        assert step in body["steps"], f"missing {step}"
    assert body["steps"]["9_sensors"]["required"] is False
    assert len(body["cycle"]) >= 7
    assert body["confidence"] == "ESTIMATED"


def test_plan_works_with_no_sensors_at_all(client, auth, clean):
    """Spec 12: sensors must never block this module."""
    client.post("/api/circular/livestock", headers=auth,
                json=[{"animal_type": "cow", "count": 4}])
    body = client.get("/api/circular/plan", headers=auth).json()
    assert body["has_livestock"] is True
    assert body["steps"]["2_biogas_potential"] is not None


def test_every_response_carries_the_disclaimer(client, auth):
    for path in ("/api/circular/assessment", "/api/circular/plan",
                 "/api/circular/manure/compare"):
        body = client.get(path, headers=auth).json()
        assert "disclaimer" in body
        assert "not guaranteed" in body["disclaimer"].lower() \
            or "not an engineering" in body["disclaimer"].lower()


# ======================================================= manure methods (7-10)

def test_no_shade_rules_out_vermicompost():
    """Worms die in direct sun — this is not a preference."""
    r = mn.choose_method(dung_kg_per_day=40, residue_kg=1500, has_shade=False)
    assert r["recommended"] != "vermicompost"


def test_low_labour_does_not_recommend_daily_watering():
    """Regression: low labour used to return vermicompost.

    Vermicompost needs watering every few days and the worms die if the bed
    dries out — MORE day-to-day work than a heap, not less. Recommending it
    to someone with no spare labour sets them up to lose the worms.
    """
    r = mn.choose_method(dung_kg_per_day=60, residue_kg=200, labour="low")
    assert r["recommended"] == "fym"


def test_urgent_need_gets_the_fast_method():
    r = mn.choose_method(dung_kg_per_day=3, residue_kg=0, urgent=True)
    assert r["recommended"] == "liquid"
    assert r["weeks"]["high"] <= 2


def test_bulky_residue_goes_to_a_compost_heap():
    r = mn.choose_method(dung_kg_per_day=40, residue_kg=1500, has_shade=True)
    assert r["recommended"] == "compost"


def test_every_method_explains_why_the_others_were_not_chosen():
    r = mn.choose_method(dung_kg_per_day=40, residue_kg=100)
    assert len(r["alternatives"]) == 3
    assert all(a["why_not"] for a in r["alternatives"])


def test_composting_reports_realistic_mass_loss():
    """A farmer expecting 1:1 will think something has gone wrong."""
    out = mn.estimate_output(1000, "compost")
    assert out["output_kg"]["high"] < 1000
    assert out["output_kg"]["low"] >= 300
    assert "lost as water" in out["loss_note"]


def test_no_universal_composting_time_is_promised():
    for method in mn.COMPOST_METHODS:
        out = mn.estimate_output(500, method)
        assert out["ready_in_weeks"]["low"] < out["ready_in_weeks"]["high"]
        assert "depends on" in out["time_note"]


def test_materials_split_adds_up():
    m = mn.materials_for("compost", 2000)
    assert sum(x["share_pct"] for x in m["materials"]) == 100
    assert abs(sum(x["approx_kg"] for x in m["materials"]) - 2000) < 20


def test_manure_plan_endpoint(client, auth, clean):
    client.post("/api/circular/livestock", headers=auth,
                json=[{"animal_type": "cow", "count": 4}])
    body = client.get("/api/circular/manure/plan?has_shade=true",
                      headers=auth).json()
    assert body["has_livestock"] is True
    assert body["method"]["recommended"] in mn.COMPOST_METHODS
    assert body["materials"]["available"] is True
    assert body["output"]["confidence"] == "ESTIMATED"


def test_manure_plan_changes_with_the_answers(client, auth, clean):
    """The three questions must actually change the recommendation.

    Every answer is sent explicitly. Omitted answers are no longer neutral
    defaults — they fall back to whatever this farmer said last time, which
    is the whole point of remembering them — so a test that leaves one out is
    testing the persistence layer rather than the recommendation logic.
    """
    client.post("/api/circular/livestock", headers=auth,
                json=[{"animal_type": "cow", "count": 4}])
    shade = client.get(
        "/api/circular/manure/plan?has_shade=true&labour=normal&urgent=false",
        headers=auth).json()["method"]["recommended"]
    lowlab = client.get(
        "/api/circular/manure/plan?has_shade=true&labour=low&urgent=false",
        headers=auth).json()["method"]["recommended"]
    assert shade != lowlab


def test_answers_persist_so_the_farmer_is_not_asked_twice(client, auth, clean):
    """A plan requested with NO parameters uses the answers already given.

    This is the fix for the page asking the same three questions on every
    visit: the answers belong to the farm record, not to the query string.
    """
    client.post("/api/circular/livestock", headers=auth,
                json=[{"animal_type": "cow", "count": 4}])
    first = client.get("/api/circular/manure/plan?has_shade=true&labour=low",
                       headers=auth).json()

    # No query string at all — the server must supply the saved answers.
    again = client.get("/api/circular/manure/plan", headers=auth).json()
    assert again["inputs"]["answered"] == first["inputs"]["answered"]
    assert again["method"]["recommended"] == first["method"]["recommended"]

    saved = client.get("/api/circular/choice", headers=auth).json()
    assert saved["labour"] == "low"
    assert saved["has_shade"] is True


def test_registering_a_plant_twice_does_not_create_a_second_one(
        client, auth, clean, db, demo):
    """Registration is idempotent: one farmer, one plant, however often the
    form is submitted from either branch of the page."""
    client.post("/api/circular/plant", headers=auth,
                json={"size_m3": 4, "plant_type": "fixed_dome"})
    client.post("/api/circular/plant", headers=auth, json={"size_m3": 4})
    client.post("/api/circular/plant", headers=auth, json={})

    rows = db.query(BiogasPlant).filter(BiogasPlant.user_id == demo.id).all()
    assert len(rows) == 1
    # A blank re-save must not wipe details already on record.
    assert rows[0].size_m3 == 4
    assert rows[0].plant_type == "fixed_dome"


def test_manure_plan_uses_a_registered_biogas_plant(client, auth, clean):
    """Choosing Manure after registering a digester must USE the digester.

    Its slurry is already manure, so a farmer who built a plant must not be
    shown a composting figure that ignores it — nor be asked to register the
    plant a second time.
    """
    client.post("/api/circular/livestock", headers=auth,
                json=[{"animal_type": "cow", "count": 6}])

    before = client.get("/api/circular/manure/plan", headers=auth).json()
    assert before["biogas"]["registered"] is False
    assert before["sources"]["from_biogas"] is False

    client.post("/api/circular/plant", headers=auth, json={"size_m3": 4})

    after = client.get("/api/circular/manure/plan", headers=auth).json()
    assert after["biogas"]["registered"] is True
    assert after["sources"]["from_biogas"] is True
    assert after["sources"]["digestate_kg"] > 0
    # The total is the two sources added, and both are reported separately.
    assert (after["sources"]["total_kg"]
            == after["sources"]["compost_kg"] + after["sources"]["digestate_kg"])


def test_food_safety_warning_is_not_shown_for_every_crop(client, auth, clean, db, demo):
    """The disclaimer appears only where raw consumption is a real risk.

    A warning printed on every crop stops being read, so wheat and cotton get
    nothing and tomato gets a warning naming the part actually eaten.
    """
    farm = db.query(Farm).filter(Farm.user_id == demo.id).first()
    original_crop = farm.crop
    client.post("/api/circular/livestock", headers=auth,
                json=[{"animal_type": "cow", "count": 4}])
    try:
        farm.crop = "tomato"; db.commit()
        note = client.get("/api/circular/manure/plan", headers=auth).json()[
            "farm_use"]["recommendation"]["food_safety_note"]
        assert note and "raw" in note.lower()

        for quiet_crop in ("wheat", "cotton"):
            farm.crop = quiet_crop; db.commit()
            assert client.get("/api/circular/manure/plan", headers=auth).json()[
                "farm_use"]["recommendation"]["food_safety_note"] is None
    finally:
        # The demo farm is shared across the whole suite. Leaving it set to
        # cotton silently broke an unrelated farm-profile test that expects
        # the fixture's crop.
        farm.crop = original_crop
        db.commit()


# ================================================ existing plant (spec 6)

def test_status_explains_in_words_not_numbers():
    from app.services import biogas as _bg
    st = _bg.plant_status([{"gas_level": "low", "smell": "sour",
                            "logged_on": "2026-09-06"}])
    assert st["status"] == _bg.STATUS_PROBLEM
    # The classic overfeeding signature must be named, and an action given.
    assert "sour" in st["headline"].lower()
    assert "stop feeding" in st["action"].lower()


def test_healthy_plant_says_so_plainly():
    from app.services import biogas as _bg
    st = _bg.plant_status([{"gas_level": "good", "flame_quality": "strong",
                            "smell": "normal", "logged_on": "2026-09-06"}])
    assert st["status"] == _bg.STATUS_HEALTHY
    assert "normally" in st["headline"].lower()


def test_cold_weather_is_explained_as_normal():
    """A farmer must not think winter is a fault."""
    from app.services import biogas as _bg
    st = _bg.plant_status([{"gas_level": "low", "temperature_c": 14,
                            "logged_on": "2026-09-06"}])
    cold = [i for i in st["issues"] if "cold" in i["what"].lower()]
    assert cold and "normal" in cold[0]["why"].lower()


def test_manual_log_alone_is_enough_to_diagnose():
    """Almost no small plant has instruments; words must be sufficient."""
    from app.services import biogas as _bg
    st = _bg.plant_status([{"gas_level": "low", "flame_quality": "weak",
                            "logged_on": "2026-09-06"}])
    assert st["status"] != _bg.STATUS_UNKNOWN
    assert st["action"]


def test_no_logs_is_not_an_error():
    from app.services import biogas as _bg
    assert _bg.plant_status([])["status"] == _bg.STATUS_UNKNOWN


def test_register_plant_and_log(client, auth, db, demo):
    from app.models.models import BiogasPlant, BiogasLog
    db.query(BiogasLog).filter(BiogasLog.user_id == demo.id).delete()
    db.query(BiogasPlant).filter(BiogasPlant.user_id == demo.id).delete()
    db.commit()

    assert client.get("/api/circular/plant",
                      headers=auth).json()["has_plant"] is False

    r = client.post("/api/circular/plant", headers=auth,
                    json={"size_m3": 3, "monitoring_mode": "manual"})
    assert r.status_code == 200 and r.json()["has_plant"] is True

    r = client.post("/api/circular/plant/log", headers=auth,
                    json={"feed_kg": 75, "gas_level": "good",
                          "flame_quality": "strong", "smell": "normal"})
    body = r.json()
    assert body["status"]["status"] == "HEALTHY"
    assert body["logged_today"] is True

    db.query(BiogasLog).filter(BiogasLog.user_id == demo.id).delete()
    db.query(BiogasPlant).filter(BiogasPlant.user_id == demo.id).delete()
    db.commit()


def test_logging_twice_a_day_updates_rather_than_duplicates(client, auth, db, demo):
    from app.models.models import BiogasPlant, BiogasLog
    client.post("/api/circular/plant", headers=auth, json={"size_m3": 2})
    client.post("/api/circular/plant/log", headers=auth,
                json={"gas_level": "low"})
    client.post("/api/circular/plant/log", headers=auth,
                json={"gas_level": "good"})
    rows = db.query(BiogasLog).filter(BiogasLog.user_id == demo.id).all()
    assert len(rows) == 1
    db.query(BiogasLog).filter(BiogasLog.user_id == demo.id).delete()
    db.query(BiogasPlant).filter(BiogasPlant.user_id == demo.id).delete()
    db.commit()
