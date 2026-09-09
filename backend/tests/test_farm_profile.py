"""Farm Profile / crop intelligence tests.

Covers setup gating, profile assembly, confidence labelling, the
current-vs-explored crop distinction, and rotation-aware next-crop advice.

Follows this project's existing pattern: a module-scoped TestClient logged in
as the seeded demo farmer, with direct SessionLocal access when a test needs to
change farm state. Farm state is restored afterwards so tests stay independent.

The graceful-degradation tests matter most. Weather and satellite are external
and fail routinely; a farmer whose dashboard breaks because Earth Engine timed
out has lost the whole app rather than one card.
"""

import asyncio
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.database.db import SessionLocal
from app.main import app
from app.models.models import Farm, SoilTest, User
from app.services import farm_profile as fp


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
def farm(db, demo):
    """The demo farm, with every column restored after the test."""
    f = db.query(Farm).filter(Farm.user_id == demo.id).first()
    saved = {c.name: getattr(f, c.name) for c in Farm.__table__.columns}
    yield f
    for k, v in saved.items():
        if k != "id":
            setattr(f, k, v)
    db.commit()


def _run(coro):
    """Run one coroutine. build_profile is async; these tests are not."""
    return asyncio.new_event_loop().run_until_complete(coro)


# ------------------------------------------------------------ setup status

def test_complete_farm_passes_the_guard(db, demo, farm):
    status = fp.setup_status(db, demo)
    assert status["completed"] is True
    assert status["missing_required"] == []
    assert status["next_step"] is None


def test_missing_location_fails_the_guard(db, demo, farm):
    """Without a district nothing personalised can be computed at all."""
    farm.district = ""
    db.commit()
    status = fp.setup_status(db, demo)
    assert status["completed"] is False
    assert "district" in status["missing_required"]
    assert status["next_step"] == "/farm-setup"


def test_optional_field_never_blocks_access(db, demo, farm):
    """Regression: soil type used to be REQUIRED.

    A farmer who skipped it during the wizard was bounced back to setup on
    every navigation, forever, with no way out — the worst possible failure
    for a gate, because it punishes them for an optional answer. Soil type is
    now prompted for on the page that needs it, not enforced at the door.
    """
    farm.soil_type = ""
    farm.land_size_acres = None
    farm.previous_crop = ""
    db.commit()
    status = fp.setup_status(db, demo)
    assert status["completed"] is True, "an optional field is blocking access"
    assert "soil_type" in status["missing_recommended"]


def test_completed_setup_echoes_the_entered_data(db, demo, farm):
    """Once done, the app must SHOW what was entered, not re-ask for it."""
    status = fp.setup_status(db, demo)
    assert status["completed"] is True
    summary = status["summary"]
    assert summary["state"] and summary["district"]
    assert "crop" in summary and "soil_type" in summary


def test_onboarded_flag_alone_is_not_enough(db, demo, farm):
    """onboarded=True with no location must still fail.

    Otherwise someone who skipped the wizard reaches modules that then have
    nothing to compute from.
    """
    farm.onboarded = True
    farm.state = ""
    db.commit()
    assert fp.setup_status(db, demo)["completed"] is False


def test_setup_status_endpoint(client, auth):
    body = client.get("/api/farm/setup/status", headers=auth).json()
    assert "completed" in body and "completeness" in body


def test_setup_status_requires_auth(client):
    assert client.get("/api/farm/setup/status").status_code == 401


# -------------------------------------------------------- profile assembly

def test_profile_has_every_section(db, demo, farm):
    profile = _run(fp.build_profile(db, demo))
    for section in ("location", "land", "soil", "sensors", "weather",
                    "satellite", "current_crop", "previous_crop",
                    "data_confidence"):
        assert section in profile, f"missing section: {section}"


def test_missing_soil_test_is_unavailable_not_invented(db, demo, farm):
    """Absent data must read UNAVAILABLE, never a plausible zero."""
    db.query(SoilTest).filter(SoilTest.user_id == demo.id).delete()
    db.commit()
    profile = _run(fp.build_profile(db, demo))
    assert profile["soil"]["available"] is False
    assert profile["soil"]["ph"]["value"] is None
    assert profile["soil"]["ph"]["confidence"] == fp.UNAVAILABLE


def test_crop_stage_is_labelled_estimated(db, demo, farm):
    """Stage is derived from the sowing date, so it must never look confirmed."""
    farm.crop = "soybean"
    farm.sowing_date = datetime.utcnow() - timedelta(days=30)
    # Cleared explicitly so this test exercises the derived paths, not a
    # value another test happened to leave behind.
    farm.growth_stage = ""
    farm.expected_harvest_date = None
    db.commit()

    crop = _run(fp.build_profile(db, demo))["current_crop"]
    assert crop["growing"] is True
    assert crop["days_after_sowing"]["value"] == 30
    assert crop["stage"]["value"] is not None
    assert crop["stage"]["confidence"] == fp.ESTIMATED
    assert crop["expected_harvest_date"]["confidence"] == fp.ESTIMATED


def test_derived_stage_beats_a_stored_growth_stage(db, demo, farm):
    """A typed growth_stage goes stale; a sowing date does not.

    "Flowering" entered at onboarding is still "flowering" in the database
    two months later, when the crop is actually at maturity. So whenever a
    sowing date exists, the computed stage wins.
    """
    farm.crop = "soybean"
    farm.sowing_date = datetime.utcnow() - timedelta(days=30)
    farm.growth_stage = "maturity"          # stale, contradicts day 30
    db.commit()

    stage = _run(fp.build_profile(db, demo))["current_crop"]["stage"]
    assert stage["value"] == "Vegetative"    # from the lifecycle, not the field
    assert stage["confidence"] == fp.ESTIMATED


def test_stored_stage_is_used_when_there_is_no_sowing_date(db, demo, farm):
    """Without a date there is nothing to compute from, so their answer stands."""
    farm.crop = "soybean"
    farm.sowing_date = None
    farm.growth_stage = "flowering"
    db.commit()

    stage = _run(fp.build_profile(db, demo))["current_crop"]["stage"]
    assert stage["value"] == "flowering"
    assert stage["confidence"] == fp.CONFIRMED


def test_no_crop_is_not_an_error(db, demo, farm):
    farm.crop = ""
    farm.sowing_date = None
    db.commit()
    assert _run(fp.build_profile(db, demo))["current_crop"]["growing"] is False


def test_profile_endpoint(client, auth):
    body = client.get("/api/farm/profile", headers=auth).json()
    assert body["has_farm"] is True
    assert "data_confidence" in body


# ------------------------------------------- current crop vs explored crop

def test_current_crop_is_labelled_current(client, auth, db, farm):
    farm.crop = "soybean"
    db.commit()
    body = client.get("/api/farm/crop/soybean/lifecycle", headers=auth).json()
    assert body["is_current_crop"] is True
    assert body["label"] == "CURRENT CROP"
    assert body["warning"] is None


def test_other_crop_warns_it_is_not_yours(client, auth, db, farm):
    """The core UX rule: an explored crop must never look like the current one."""
    farm.crop = "rice"
    db.commit()
    body = client.get("/api/farm/crop/cotton/lifecycle", headers=auth).json()

    assert body["is_current_crop"] is False
    assert body["label"] == "EXPLORED CROP"
    assert body["warning"]["type"] == "NOT_YOUR_CURRENT_CROP"
    assert "Rice" in body["warning"]["message"]
    assert "Cotton" in body["warning"]["message"]


def test_explored_crop_highlights_no_stage(client, auth, db, farm):
    """There is no cotton in the field, so no cotton stage may be highlighted."""
    farm.crop = "rice"
    farm.sowing_date = datetime.utcnow() - timedelta(days=40)
    db.commit()
    body = client.get("/api/farm/crop/cotton/lifecycle", headers=auth).json()
    assert all(st["is_current"] is False for st in body["stages"])


def test_current_crop_highlights_exactly_one_stage(client, auth, db, farm):
    farm.crop = "soybean"
    farm.sowing_date = datetime.utcnow() - timedelta(days=30)
    db.commit()
    body = client.get("/api/farm/crop/soybean/lifecycle", headers=auth).json()
    assert sum(1 for st in body["stages"] if st["is_current"]) == 1


def test_explored_crop_still_gets_a_suitability_verdict(client, auth, db, farm):
    """'Not your crop' should be followed by 'but could you grow it here?'"""
    farm.crop = "rice"
    db.commit()
    body = client.get("/api/farm/crop/cotton/lifecycle", headers=auth).json()
    assert body["suitability"]["available"] is True
    assert "verdict" in body["suitability"]


def test_crop_aliases_resolve(client, auth, db, farm):
    """'moong' and 'greengram' must reach the same lifecycle."""
    farm.crop = "greengram"
    db.commit()
    body = client.get("/api/farm/crop/moong/lifecycle", headers=auth).json()
    assert body["crop"] == "greengram"
    assert body["is_current_crop"] is True


def test_unknown_crop_returns_404(client, auth):
    assert client.get("/api/farm/crop/banana/lifecycle",
                      headers=auth).status_code == 404


def test_every_dropdown_crop_has_a_lifecycle(client, auth):
    """Guards the original bug: 10 of 15 dropdown crops had no lifecycle."""
    from app.services.crop_suitability import MP_CROPS
    for key in MP_CROPS:
        res = client.get(f"/api/farm/crop/{key}/lifecycle", headers=auth)
        assert res.status_code == 200, f"{key} has no lifecycle"
        assert res.json()["stages"], f"{key} has empty stages"


def test_current_crop_lifecycle_endpoint(client, auth, db, farm):
    farm.crop = "soybean"
    farm.sowing_date = datetime.utcnow() - timedelta(days=30)
    db.commit()
    body = client.get("/api/farm/current-crop/lifecycle", headers=auth).json()
    assert body["growing"] is True
    assert body["is_current_crop"] is True
    assert body["current_stage"]["confidence"] == fp.ESTIMATED


# ---------------------------------------------------------------- rotation

def test_next_crops_never_repeat_the_current_crop(client, auth, db, farm):
    farm.crop = "rice"
    farm.previous_crop = "maize"
    db.commit()
    body = client.get("/api/farm/next-crops", headers=auth).json()

    assert body["available"] is True
    recs = body["recommendations"]
    assert len(recs) >= 3
    # Sowing the same crop again is exactly what rotation prevents.
    assert all(r["crop"] != "rice" for r in recs)


def test_next_crops_are_ranked_with_reasons(client, auth, db, farm):
    farm.crop = "rice"
    db.commit()
    recs = client.get("/api/farm/next-crops",
                      headers=auth).json()["recommendations"]
    scores = [r["score"] for r in recs]
    assert scores == sorted(scores, reverse=True)
    assert all(r["why"] for r in recs)


def test_next_crops_favour_a_different_family(client, auth, db, farm):
    """After a cereal, the top pick should not be another cereal."""
    farm.crop = "rice"
    farm.previous_crop = "wheat"
    db.commit()
    top = client.get("/api/farm/next-crops",
                     headers=auth).json()["recommendations"][0]
    assert top["rotation_score"] >= 60, (
        f"top pick {top['crop']} has weak rotation score "
        f"{top['rotation_score']}")


def test_next_crops_needs_a_current_crop(client, auth, db, farm):
    farm.crop = ""
    db.commit()
    assert client.get("/api/farm/next-crops",
                      headers=auth).json()["available"] is False


# ------------------------------------------------- graceful degradation

def test_weather_failure_does_not_break_the_profile(db, demo, farm, monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("weather API down")
    monkeypatch.setattr("app.services.weather.get_weather", boom)

    profile = _run(fp.build_profile(db, demo))
    assert profile["weather"]["available"] is False
    assert profile["has_farm"] is True          # everything else survived


def test_satellite_failure_does_not_break_the_profile(db, demo, farm, monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("earth engine down")
    monkeypatch.setattr("app.services.satellite.get_ndvi", boom)

    profile = _run(fp.build_profile(db, demo))
    assert profile["satellite"]["available"] is False
    assert profile["current_crop"]["growing"] is True


def test_profile_survives_all_external_services_failing(db, demo, farm,
                                                        monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("down")
    monkeypatch.setattr("app.services.weather.get_weather", boom)
    monkeypatch.setattr("app.services.satellite.get_ndvi", boom)

    profile = _run(fp.build_profile(db, demo))
    assert profile["data_confidence"]["weather"] == fp.UNAVAILABLE
    assert profile["data_confidence"]["satellite"] == fp.UNAVAILABLE
    assert profile["location"]["state"]["value"]      # local data intact


# --------------------------------------------------------------- flattening

def test_flatten_unwraps_for_the_scoring_engine(db, demo, farm):
    """score_crop() wants bare numbers, not confidence wrappers."""
    db.add(SoilTest(user_id=demo.id, ph=6.5, nitrogen=25, phosphorus=35,
                    potassium=50, source="manual"))
    db.commit()

    flat = fp.flatten_for_scoring(_run(fp.build_profile(db, demo)))
    assert flat["ph"] == 6.5
    assert not isinstance(flat["ph"], dict)
    assert flat["soil_type"] == "black"
    assert flat["current_crop"] == "soybean"


# ------------------------------------------------- wizard fields (spec 2)

def test_previous_crop_detail_is_saved_and_surfaced(client, auth, db, demo, farm):
    """Rotation advice needs more than a crop name and a season label."""
    res = client.post("/api/onboarding/save", headers=auth, json={
        "previous_crop": "maize",
        "previous_variety": "Pioneer 3396",
        "previous_sowing_date": "2025-06-15",
        "previous_harvest_date": "2025-10-02",
        "previous_yield_qtl": 42.5,
        "previous_problems": "stem borer in patches near the canal",
    })
    assert res.status_code == 200

    db.expire_all()
    profile = _run(fp.build_profile(db, demo))
    prev = profile["previous_crop"]

    assert prev["variety"]["value"] == "Pioneer 3396"
    assert prev["harvest_date"]["value"] == "2025-10-02"
    assert prev["yield_qtl"]["value"] == 42.5
    assert "stem borer" in prev["problems"]["value"]
    assert prev["days_since_harvest"] > 0


def test_crop_area_is_separate_from_total_holding(client, auth, db, demo, farm):
    """4 acres owned but 1.5 sown: fertiliser must use 1.5, not 4."""
    res = client.post("/api/onboarding/save", headers=auth, json={
        "land_size_acres": 4.0, "crop": "soybean", "crop_area_acres": 1.5,
    })
    assert res.status_code == 200

    db.expire_all()
    profile = _run(fp.build_profile(db, demo))
    assert profile["land"]["area_acres"]["value"] == 4.0
    assert profile["current_crop"]["crop_area_acres"]["value"] == 1.5


def test_harvest_date_is_derived_on_read_not_stored(client, auth, db, demo, farm):
    """A blank harvest date is knowable from crop duration — don't re-ask.

    But it must be derived on READ, never written into the column that means
    "the farmer told us". Storing it there would make a calculation
    indistinguishable from their own answer, and the profile would then label
    it CONFIRMED.
    """
    farm.expected_harvest_date = None
    db.commit()
    client.post("/api/onboarding/save", headers=auth, json={
        "crop": "soybean", "sowing_date": "2026-07-01",
    })
    db.expire_all()

    assert farm.expected_harvest_date is None      # nothing written

    harvest = _run(fp.build_profile(db, demo))["current_crop"]["expected_harvest_date"]
    assert harvest["value"] == "2026-10-04"        # 2026-07-01 + 95 days
    assert harvest["confidence"] == fp.ESTIMATED


def test_farmer_supplied_harvest_date_is_not_overwritten(client, auth, db,
                                                         demo, farm):
    """Their own answer outranks our arithmetic, and is labelled CONFIRMED."""
    client.post("/api/onboarding/save", headers=auth, json={
        "crop": "soybean", "sowing_date": "2026-07-01",
        "expected_harvest_date": "2026-10-20",
    })
    db.expire_all()
    profile = _run(fp.build_profile(db, demo))
    harvest = profile["current_crop"]["expected_harvest_date"]
    assert harvest["value"] == "2026-10-20"
    assert harvest["confidence"] == fp.CONFIRMED


def test_area_shown_back_in_the_unit_entered(client, auth, db, demo, farm):
    """A farmer who typed hectares must not be shown acres back."""
    client.post("/api/onboarding/save", headers=auth, json={
        "land_size_acres": 4.94, "area_unit": "hectare",
    })
    db.expire_all()
    land = _run(fp.build_profile(db, demo))["land"]
    assert land["area_unit"]["value"] == "hectare"
    assert abs(land["area_as_entered"]["value"] - 12.21) < 0.05


def test_bad_date_is_rejected_by_name(client, auth, farm):
    """One malformed field should say which one, not fail the whole save."""
    res = client.post("/api/onboarding/save", headers=auth, json={
        "previous_harvest_date": "15-06-2025",
    })
    assert res.status_code == 400
    assert "previous_harvest_date" in res.json()["detail"]


def test_partial_save_still_works(client, auth, farm):
    """The wizard is resumable — a save with two fields must not error."""
    assert client.post("/api/onboarding/save", headers=auth,
                       json={"water_availability": "limited"}).status_code == 200


def test_saving_setup_actually_marks_it_complete(client, auth, db, demo, farm):
    """Regression: the wizard saved but never flipped `onboarded`.

    The save endpoint hardcoded its own idea of "complete" (state AND
    land_size_acres AND soil_type) while REQUIRED_FIELDS said (state,
    district). Once those drifted, onboarded stayed False forever and the
    guard bounced the farmer back to setup on every single navigation.
    """
    farm.onboarded = False
    farm.soil_type = ""
    farm.land_size_acres = None
    db.commit()

    res = client.post("/api/onboarding/save", headers=auth,
                      json={"state": "Madhya Pradesh", "district": "Indore"})
    assert res.status_code == 200

    db.expire_all()
    assert farm.onboarded is True, "wizard saved but did not mark setup done"
    assert fp.setup_status(db, demo)["completed"] is True


def test_onboarded_uses_the_shared_constant(db, demo, farm):
    """The save path and the guard must read the same list of fields."""
    from app.services.farm_profile import REQUIRED_FIELDS
    assert set(REQUIRED_FIELDS) == {"state", "district"}


def test_future_sowing_date_is_planned_not_missing(db, demo, farm):
    """A date the farmer just typed must not come back as "Not available"."""
    farm.crop = "maize"
    farm.sowing_date = datetime.utcnow() + timedelta(days=5)
    db.commit()

    crop = _run(fp.build_profile(db, demo))["current_crop"]
    assert crop["not_yet_sown"] is True
    assert crop["days_until_sowing"]["value"] == 5


def test_contradictory_harvest_date_is_flagged(db, demo, farm):
    """A 100-day crop harvested 11 days after sowing is a typo, not data.

    Showing the entered date on one card and the derived date on the next,
    with no comment, is how a farmer plans against the wrong one.
    """
    farm.crop = "maize"                                   # 100-day duration
    farm.sowing_date = datetime(2026, 9, 7)
    farm.expected_harvest_date = datetime(2026, 9, 18)    # 11 days later
    db.commit()

    crop = _run(fp.build_profile(db, demo))["current_crop"]
    assert crop["harvest_date_conflict"] is not None
    assert "check the sowing and harvest dates" in crop["harvest_date_conflict"].lower()


def test_sensible_harvest_date_is_not_flagged(db, demo, farm):
    farm.crop = "maize"
    farm.sowing_date = datetime(2026, 9, 7)
    farm.expected_harvest_date = datetime(2026, 12, 16)   # ~100 days
    db.commit()
    crop = _run(fp.build_profile(db, demo))["current_crop"]
    assert crop["harvest_date_conflict"] is None


# ------------------------------------------ next-crops-for-previous

def test_next_crops_for_previous_needs_a_previous_crop(client, auth, db, farm):
    farm.previous_crop = ""
    db.commit()
    assert client.get("/api/farm/next-crops-for-previous",
                      headers=auth).json()["available"] is False


def test_next_crops_for_previous_never_repeats_it(client, auth, db, farm):
    farm.previous_crop = "wheat"
    db.commit()
    body = client.get("/api/farm/next-crops-for-previous", headers=auth).json()
    assert body["available"] is True
    recs = body["recommendations"]
    assert len(recs) >= 3
    assert all(r["crop"] != "wheat" for r in recs)


def test_next_crops_for_previous_ranked_with_reasons(client, auth, db, farm):
    farm.previous_crop = "rice"
    db.commit()
    recs = client.get("/api/farm/next-crops-for-previous",
                      headers=auth).json()["recommendations"]
    scores = [r["score"] for r in recs]
    assert scores == sorted(scores, reverse=True)
    assert all(r["why"] for r in recs)
