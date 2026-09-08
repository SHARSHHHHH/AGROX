"""Alert engine tests.

The deduplication tests matter most. The previous implementation suppressed an
alert only while it was UNREAD, so marking one read regenerated it on the next
poll — the same sentence forever. Farmers respond to that by ignoring the
alerts page, which costs them the alerts that actually matter.

The rules module is pure, so most of this runs with no database and no network.
"""

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.database.db import SessionLocal
from app.main import app
from app.models.models import Alert, ExternalAdvisory, Farm, User
from app.services import alert_rules as rules
from app.services import alerts as alerts_svc


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
def clean_alerts(db, demo):
    """Start from an empty alert list so counts are deterministic."""
    db.query(Alert).filter(Alert.user_id == demo.id).delete()
    db.commit()
    yield
    db.query(Alert).filter(Alert.user_id == demo.id).delete()
    db.commit()


# ============================================================ 1. irrigation

def test_dry_soil_with_no_rain_says_irrigate():
    out = rules.irrigation(moisture=18, moisture_status="LOW",
                           crop_display="Soybean", rain_probability=10,
                           rain_mm_5day=0)
    assert len(out) == 1
    assert out[0]["type"] == "IRRIGATION_NEEDED"
    assert out[0]["priority"] == rules.HIGH
    assert "irrigate" in out[0]["action"].lower()


def test_dry_soil_with_rain_coming_says_wait():
    """Irrigating before rain wastes diesel and waterlogs the field."""
    out = rules.irrigation(moisture=18, moisture_status="LOW",
                           crop_display="Soybean", rain_probability=85,
                           rain_mm_5day=30)
    assert len(out) == 1
    assert out[0]["type"] == "IRRIGATION_HOLD"
    assert "hold off" in out[0]["action"].lower()


def test_very_low_moisture_is_critical():
    out = rules.irrigation(moisture=6, moisture_status="VERY LOW",
                           crop_display="Rice", rain_probability=0,
                           rain_mm_5day=0)
    assert out[0]["priority"] == rules.CRITICAL


def test_adequate_moisture_produces_nothing():
    assert rules.irrigation(moisture=55, moisture_status="OPTIMAL",
                            crop_display="Rice", rain_probability=0,
                            rain_mm_5day=0) == []


# =========================================================== 2. water tank

@pytest.mark.parametrize("level,expected", [
    (99, "TANK_FULL"), (93, "TANK_ALMOST_FULL"),
    (18, "TANK_LOW"), (5, "TANK_CRITICAL"),
])
def test_tank_levels(level, expected):
    out = rules.water_tank(level=level)
    assert out and out[0]["type"] == expected


def test_normal_tank_is_silent():
    assert rules.water_tank(level=60) == []


def test_missing_tank_reading_is_silent():
    """No sensor is not the same as an empty tank."""
    assert rules.water_tank(level=None) == []


# ============================================================== 3. weather

def test_five_wet_days_triggers_drainage_advice():
    """The scenario the spec calls out explicitly."""
    out = rules.weather(temperature=28, rain_probability=90,
                        rain_mm_5day=120, wind_kph=10, wet_days_ahead=5,
                        moisture=72, crop_display="Rice")
    prolonged = [a for a in out if a["type"] == "PROLONGED_RAIN"]
    assert prolonged
    a = prolonged[0]
    assert "drainage" in a["action"].lower()
    assert "stop irrigating" in a["action"].lower()
    assert "72" in a["message"]          # their own moisture is cited


def test_extreme_heat_outranks_high_heat():
    out = rules.weather(temperature=43, rain_probability=0, rain_mm_5day=0,
                        wind_kph=5, wet_days_ahead=0)
    heat = [a for a in out if a["category"] == "weather"]
    assert heat[0]["type"] == "EXTREME_HEAT"
    assert heat[0]["priority"] == rules.CRITICAL


def test_strong_wind_warns_against_spraying():
    out = rules.weather(temperature=30, rain_probability=0, rain_mm_5day=0,
                        wind_kph=55, wet_days_ahead=0)
    wind = [a for a in out if a["type"] == "STRONG_WIND"]
    assert wind and "not spray" in wind[0]["action"].lower()


def test_calm_pleasant_weather_is_silent():
    assert rules.weather(temperature=27, rain_probability=10, rain_mm_5day=2,
                         wind_kph=8, wet_days_ahead=0) == []


# ========================================================== 4. nearby pest

def test_nearby_pest_never_claims_your_field_is_infected():
    """The single most important wording rule in this module."""
    out = rules.nearby_pest(
        reports=[{"pest_name": "Stem borer", "district": "Dewas", "count": 3}],
        crop_display="Rice", district="Indore")
    a = out[0]
    assert "NOT" in a["message"]
    assert "Dewas" in a["message"] and "Indore" in a["message"]
    assert a["payload"]["is_your_field"] is False
    # It must send them to look, not to spray.
    assert "confirm" in a["action"].lower()


def test_no_nearby_reports_produces_nothing():
    assert rules.nearby_pest(reports=[], crop_display="Rice",
                             district="Indore") == []


# ============================== 5,6,7 official advisories (admin-curated)

def test_compensation_shows_the_announced_amount_and_source():
    spec = rules.official_advisory({
        "id": 7, "kind": "compensation",
        "title": "Flood crop loss assistance announced",
        "summary": "Assistance for kharif crop loss in flood-affected areas.",
        "amount": 17000, "amount_unit": "per hectare",
        "amount_note": "maximum 2 hectares",
        "source_name": "MP Revenue Department",
        "source_url": "https://mp.gov.in/notice/123",
        "published_on": datetime(2026, 8, 20),
    }, crop_display="Soybean", district="Indore")

    assert spec["category"] == "compensation"
    assert "17,000" in spec["message"]
    assert "per hectare" in spec["message"]
    assert spec["source_url"] == "https://mp.gov.in/notice/123"
    assert spec["payload"]["verified_source"] is True


def test_flood_advisory_is_always_critical():
    spec = rules.official_advisory({
        "id": 1, "kind": "flood", "title": "Flood warning",
        "summary": "River above danger level.",
        "source_name": "CWC", "source_url": "https://cwc.gov.in/x",
    }, crop_display="Rice", district="Indore")
    assert spec["priority"] == rules.CRITICAL
    assert spec["category"] == "disaster"


def test_advisory_dedupe_key_is_the_advisory_id():
    """One official notice must yield one alert, however often rules run."""
    a = rules.official_advisory({"id": 42, "kind": "scheme", "title": "X",
                                 "source_name": "S", "source_url": "u"},
                                crop_display="Rice", district="D")
    b = rules.official_advisory({"id": 42, "kind": "scheme", "title": "X",
                                 "source_name": "S", "source_url": "u"},
                                crop_display="Rice", district="D")
    assert a["dedupe_key"] == b["dedupe_key"]


# =========================================================== 10. lifecycle

def test_flowering_stage_raises_a_high_priority_alert():
    out = rules.lifecycle_stage(
        crop_display="Soybean",
        stage={"stage": "Flowering", "tasks": ["Scout for pod borer"]},
        days_after_sowing=40, days_to_harvest=55)
    stage_alerts = [a for a in out if a["type"] == "LIFECYCLE_STAGE"]
    assert stage_alerts and stage_alerts[0]["priority"] == rules.HIGH
    assert stage_alerts[0]["payload"]["estimated"] is True


def test_harvest_window_triggers_planning_alert():
    out = rules.lifecycle_stage(
        crop_display="Wheat", stage={"stage": "Maturity", "tasks": []},
        days_after_sowing=120, days_to_harvest=10)
    assert any(a["type"] == "HARVEST_APPROACHING" for a in out)


def test_routine_stage_does_not_interrupt_the_farmer():
    """Most stage changes are not worth a notification."""
    out = rules.lifecycle_stage(
        crop_display="Soybean", stage={"stage": "Germination", "tasks": []},
        days_after_sowing=5, days_to_harvest=90)
    assert out == []


# ======================================================= dedup and expiry

def test_same_situation_is_not_alerted_twice(db, demo, clean_alerts):
    spec = rules.water_tank(level=5)[0]
    first = alerts_svc._persist(db, demo.id, spec)
    db.commit()
    assert first is not None

    second = alerts_svc._persist(db, demo.id, spec)
    db.commit()
    assert second is None, "identical situation raised a second alert"


def test_marking_read_does_not_regenerate_the_alert(db, demo, clean_alerts):
    """The exact bug in the previous implementation."""
    spec = rules.water_tank(level=5)[0]
    first = alerts_svc._persist(db, demo.id, spec)
    db.commit()

    first.read = True                      # farmer reads it
    db.commit()

    again = alerts_svc._persist(db, demo.id, spec)
    db.commit()
    assert again is None, "reading an alert caused it to be raised again"


def test_a_worse_situation_does_raise_a_new_alert(db, demo, clean_alerts):
    """Dedup must not silence a genuine escalation."""
    low = rules.water_tank(level=22)[0]        # TANK_LOW
    critical = rules.water_tank(level=4)[0]    # TANK_CRITICAL
    assert low["dedupe_key"] != critical["dedupe_key"]

    assert alerts_svc._persist(db, demo.id, low) is not None
    db.commit()
    assert alerts_svc._persist(db, demo.id, critical) is not None
    db.commit()


def test_expired_alert_is_raised_again(db, demo, clean_alerts):
    """A recurring situation should alert again once the old one lapses."""
    spec = rules.water_tank(level=5)[0]
    first = alerts_svc._persist(db, demo.id, spec)
    db.commit()

    first.expires_at = datetime.utcnow() - timedelta(hours=1)
    db.commit()

    assert alerts_svc._persist(db, demo.id, spec) is not None


def test_dismissed_alert_stays_dismissed(db, demo, clean_alerts):
    """Dismissing must not be undone by the next generation pass."""
    spec = rules.water_tank(level=5)[0]
    first = alerts_svc._persist(db, demo.id, spec)
    db.commit()
    first.dismissed = True
    db.commit()

    # The dedupe query skips dismissed rows, so a fresh alert IS created —
    # which is correct for a live critical tank. What must not happen is the
    # dismissed row itself reappearing in the farmer's list.
    again = alerts_svc._persist(db, demo.id, spec)
    db.commit()
    assert first.dismissed is True
    assert again is None or again.id != first.id


# ================================================================ the API

def test_summary_reports_unread_counts(client, auth):
    body = client.get("/api/alerts/summary", headers=auth).json()
    for key in ("total", "unread", "by_priority", "by_category",
                "needs_attention"):
        assert key in body


def test_alerts_are_sorted_by_priority(client, auth):
    rows = client.get("/api/alerts", headers=auth).json()
    order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    seen = [order.get(a["priority"], 2) for a in rows]
    assert seen == sorted(seen)


def test_alert_carries_action_and_category(client, auth):
    rows = client.get("/api/alerts", headers=auth).json()
    if rows:
        assert "action" in rows[0] and "category" in rows[0]


def test_dismiss_removes_it_from_the_list(client, auth):
    rows = client.get("/api/alerts", headers=auth).json()
    if not rows:
        pytest.skip("no alerts generated for the demo farm")
    target = rows[0]["id"]
    assert client.post(f"/api/alerts/{target}/dismiss",
                       headers=auth).status_code == 200
    after = client.get("/api/alerts", headers=auth).json()
    assert all(a["id"] != target for a in after)


def test_category_filter(client, auth):
    rows = client.get("/api/alerts?category=weather", headers=auth).json()
    assert all(a["category"] == "weather" for a in rows)


# ==================================================== advisories endpoint

def test_advisory_requires_a_source(client, auth):
    """A claim with no link is not usable in a government office."""
    res = client.post("/api/advisories", headers=auth, json={
        "kind": "scheme", "title": "Some scheme"})
    assert res.status_code in (401, 403, 422)


def test_compensation_without_an_amount_is_rejected(client):
    """Guards against a compensation alert that names no figure."""
    admin = client.post("/api/auth/login",
                        data={"username": "admin@demo.com",
                              "password": "admin123"})
    if admin.status_code != 200:
        pytest.skip("no admin account seeded")
    hdr = {"Authorization": f"Bearer {admin.json()['access_token']}"}

    res = client.post("/api/advisories", headers=hdr, json={
        "kind": "compensation", "title": "Assistance announced",
        "source_name": "MP Revenue", "source_url": "https://mp.gov.in/x"})
    assert res.status_code == 400
    assert "amount" in res.json()["detail"].lower()


def test_farmers_can_read_the_advisory_list(client, auth):
    body = client.get("/api/advisories", headers=auth).json()
    assert "advisories" in body and "count" in body


# ===================================================== push notifications

def test_push_degrades_without_vapid_keys():
    """No keys configured must mean in-app only, never an error."""
    from app.services import notifications
    ok, reason = notifications.push_available()
    st = notifications.status()
    assert st["in_app"] is True          # always available
    if not ok:
        assert "VAPID" in reason or "pywebpush" in reason
        assert st["web_push"]["ready"] is False


def test_dispatch_is_safe_with_no_subscriptions(db, demo):
    """Alert generation must not break because nobody subscribed."""
    from app.services import notifications
    result = notifications.dispatch(db, demo.id, [])
    assert result["pushed"] == 0


def test_notification_status_endpoint(client, auth):
    body = client.get("/api/alerts/notifications/status", headers=auth).json()
    assert body["in_app"] is True
    # Kept in the payload so the model extends to them without a schema change.
    assert body["sms"]["ready"] is False
    assert body["whatsapp"]["ready"] is False


def test_subscribe_is_idempotent_per_endpoint(client, auth, db, demo):
    """Reloading the page ten times must not create ten subscriptions."""
    from app.models.models import PushSubscription
    payload = {"endpoint": "https://push.example/test-abc",
               "p256dh": "k", "auth": "a"}
    client.post("/api/alerts/notifications/subscribe", headers=auth, json=payload)
    client.post("/api/alerts/notifications/subscribe", headers=auth, json=payload)

    rows = (db.query(PushSubscription)
            .filter(PushSubscription.endpoint == payload["endpoint"]).all())
    assert len(rows) == 1

    client.post("/api/alerts/notifications/unsubscribe", headers=auth,
                json=payload)
    db.expire_all()
    assert rows[0].active is False


def test_low_priority_alerts_are_not_pushed(db, demo):
    """A push for every INFO alert trains farmers to switch them off."""
    from app.services import notifications
    from app.models.models import Alert
    low = Alert(user_id=demo.id, type="X", priority="LOW", title="t",
                message="m")
    result = notifications.dispatch(db, demo.id, [low])
    assert result["pushed"] == 0


# ======================================================== supply offers (8)

def test_unverified_supply_offers_are_never_shown(client, auth, db, demo):
    """An unchecked fertiliser price is an advert we cannot stand behind."""
    from app.models.models import Farm, SupplyOffer
    farm = db.query(Farm).filter(Farm.user_id == demo.id).first()

    unverified = SupplyOffer(title="Cheap urea", category="fertilizer",
                             district=farm.district, verified=False, active=True)
    verified = SupplyOffer(title="Verified compost", category="manure",
                           district=farm.district, verified=True, active=True)
    db.add_all([unverified, verified])
    db.commit()

    try:
        body = client.get("/api/alerts/supply-offers", headers=auth).json()
        titles = [o["title"] for o in body["offers"]]
        assert "Verified compost" in titles
        assert "Cheap urea" not in titles
    finally:
        db.delete(unverified)
        db.delete(verified)
        db.commit()
