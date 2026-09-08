"""Admin / government command-center analytics.

GROUND RULES (matches the rest of this app's honesty policy):
  - Every number here comes from a real query. Nothing is invented.
  - Anything derived (a score, a trend, a forecast) is clearly computed from
    named inputs, with the inputs shown alongside it — never a bare number.
  - Forecasts use a plain linear-trend calculation on real monthly counts,
    not an LLM and not a fabricated curve. Below a minimum data threshold
    they say so explicitly instead of guessing.
  - "Scenario" outputs (what-if simulations) are always labelled as such —
    they describe what a real query against current data would look like,
    not a guaranteed real-world outcome.
"""

from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.models import (
    User, Farm, SensorReading, SoilTest, PlantDiagnosis, PestObservation,
    CropListing, ProduceOrder, SchemeInterest, Scheme, Alert, MachineryListing,
    AdminAction,
)
from app.services.recommendation import analyze_soil
from app.services.schemes import evaluate as evaluate_scheme

MOISTURE_CRITICAL = 20
MOISTURE_STRESSED = 35
MOISTURE_WATCH = 45


# ---------------------------------------------------------------- helpers

def _farm_profile(farm: Farm) -> dict:
    """A Farm row, shaped the way schemes.evaluate() expects a profile."""
    return {
        "state": farm.state or "",
        "farmer_category": farm.farmer_category or "",
        "land_size_acres": farm.land_size_acres,
        "crop": farm.crop or "",
    }


def water_status_for_moisture(moisture: Optional[float]) -> str:
    if moisture is None:
        return "unknown"
    if moisture < MOISTURE_CRITICAL:
        return "critical"
    if moisture < MOISTURE_STRESSED:
        return "stressed"
    if moisture < MOISTURE_WATCH:
        return "watch"
    return "normal"


def latest_moisture_by_farm(db: Session, farms: list[Farm]) -> dict[int, Optional[float]]:
    """farm.id -> latest soil_moisture reading for that farm's device, or
    None if the farm has no device / no readings yet."""
    out: dict[int, Optional[float]] = {}
    for f in farms:
        if not f.device_id:
            out[f.id] = None
            continue
        r = (db.query(SensorReading)
             .filter(SensorReading.device_id == f.device_id)
             .order_by(SensorReading.created_at.desc()).first())
        out[f.id] = r.soil_moisture if r else None
    return out


def linear_trend(monthly: dict[str, float], min_points: int = 3) -> dict:
    """A plain least-squares trend line over sorted (month -> value) pairs.

    Not an LLM, not a black box — this is `slope, intercept` from ordinary
    linear regression on the index (0, 1, 2, ...) vs the value. Returns an
    explicit "insufficient data" result below `min_points`, per the
    requirement to never fake a forecast.
    """
    months = sorted(monthly.keys())
    if len(months) < min_points:
        return {"available": False,
                "reason": f"Only {len(months)} period(s) of data — need at least "
                         f"{min_points} for a reliable trend.",
                "history": [{"period": m, "value": monthly[m]} for m in months]}

    xs = list(range(len(months)))
    ys = [monthly[m] for m in months]
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    den = sum((x - mean_x) ** 2 for x in xs) or 1
    slope = num / den
    intercept = mean_y - slope * mean_x
    next_x = n
    forecast = slope * next_x + intercept

    direction = "increasing" if slope > 0.5 else "declining" if slope < -0.5 else "stable"
    return {
        "available": True,
        "direction": direction,
        "slope_per_period": round(slope, 2),
        "forecast_next_period": round(max(0, forecast), 1),
        "history": [{"period": m, "value": monthly[m]} for m in months],
        "method": "Ordinary least-squares linear regression over observed monthly totals.",
    }


# ---------------------------------------------------------------- KPIs

def compute_kpis(db: Session) -> dict:
    total_farmers = db.query(func.count(User.id)).filter(User.role.in_(("farmer", "balcony"))).scalar()
    active_farms = db.query(func.count(Farm.id)).scalar()
    active_listings = (db.query(func.count(CropListing.id))
                       .filter(CropListing.status.in_(("growing", "available"))).scalar())
    buyers = db.query(func.count(User.id)).filter(User.role == "buyer").scalar()
    active_crop_types = (db.query(func.count(func.distinct(Farm.crop)))
                         .filter(Farm.crop != "").scalar())
    pest_reports = db.query(func.count(PestObservation.id)).scalar()
    disease_reports = (db.query(func.count(PlantDiagnosis.id))
                       .filter(PlantDiagnosis.disease.notin_(("Healthy", "Uncertain"))).scalar())
    active_alerts = (db.query(func.count(Alert.id))
                     .filter(Alert.severity.in_(("WARNING", "CRITICAL")), Alert.read == False)  # noqa: E712
                     .scalar())
    iot_farms = db.query(func.count(func.distinct(SensorReading.device_id))).scalar()
    scheme_engagement = db.query(func.count(SchemeInterest.id)).scalar()
    machinery_listings = db.query(func.count(MachineryListing.id)).scalar()

    return {
        "total_farmers": total_farmers or 0,
        "active_farms": active_farms or 0,
        "active_crop_listings": active_listings or 0,
        "buyers": buyers or 0,
        "active_crop_types": active_crop_types or 0,
        "pest_disease_reports": (pest_reports or 0) + (disease_reports or 0),
        "active_alerts": active_alerts or 0,
        "iot_monitored_devices": iot_farms or 0,
        "scheme_engagement": scheme_engagement or 0,
        "machinery_listings": machinery_listings or 0,
    }


# ---------------------------------------------------------------- state / district

def list_states(db: Session) -> list[dict]:
    counts: dict[str, int] = {}
    for u in db.query(User).filter(User.state != "", User.role.in_(("farmer", "balcony"))).all():
        counts[u.state] = counts.get(u.state, 0) + 1
    return sorted([{"state": s, "farmer_count": n} for s, n in counts.items()],
                  key=lambda r: -r["farmer_count"])


def list_districts(db: Session, state: str) -> list[dict]:
    counts: dict[str, int] = {}
    for u in (db.query(User).filter(User.state == state, User.district != "",
                                    User.role.in_(("farmer", "balcony"))).all()):
        counts[u.district] = counts.get(u.district, 0) + 1
    return sorted([{"district": d, "farmer_count": n} for d, n in counts.items()],
                  key=lambda r: -r["farmer_count"])


def state_detail(db: Session, state: str, district: str = "") -> dict:
    """Everything for one state (optionally narrowed to one district)."""
    uq = db.query(User).filter(User.state == state)
    if district:
        uq = uq.filter(User.district == district)
    users = uq.all()
    user_ids = [u.id for u in users]

    fq = db.query(Farm).join(User, Farm.user_id == User.id).filter(User.state == state)
    if district:
        fq = fq.filter(User.district == district)
    farms = fq.all()

    # --- crops: dominant, listing volume, trend (increasing/declining) ---
    dominant_crops = Counter(f.crop for f in farms if f.crop)

    lq = db.query(CropListing).filter(CropListing.state == state)
    if district:
        lq = lq.filter(CropListing.district == district)
    listings = lq.all()
    listing_volume = Counter(l.crop for l in listings if l.crop)

    by_month_crop: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for l in listings:
        if l.created_at and l.crop:
            by_month_crop[l.created_at.strftime("%Y-%m")][l.crop] += 1
    months_sorted = sorted(by_month_crop.keys())
    increasing, declining = [], []
    if len(months_sorted) >= 2:
        prev, curr = by_month_crop[months_sorted[-2]], by_month_crop[months_sorted[-1]]
        crops_seen = set(prev) | set(curr)
        for c in crops_seen:
            p, cnow = prev.get(c, 0), curr.get(c, 0)
            if cnow > p:
                increasing.append(c)
            elif cnow < p:
                declining.append(c)

    # --- pest / disease ---
    pest_obs = db.query(PestObservation).filter(PestObservation.user_id.in_(user_ids)).all() if user_ids else []
    pest_counts = Counter(p.pest_name for p in pest_obs if p.pest_name and p.result_type == "pest")
    disease_counts = Counter(p.pest_name for p in pest_obs if p.pest_name and p.result_type == "disease")
    diag = db.query(PlantDiagnosis).filter(PlantDiagnosis.user_id.in_(user_ids)).all() if user_ids else []
    disease_counts.update(Counter(d.disease for d in diag if d.disease not in ("Healthy", "Uncertain")))
    severity_counts = Counter((p.severity or "UNKNOWN") for p in pest_obs)

    # --- soil ---
    soil_grades = []
    for f in farms:
        soil = (db.query(SoilTest).filter(SoilTest.user_id == f.user_id)
                .order_by(SoilTest.created_at.desc()).first())
        if soil:
            res = analyze_soil(soil.nitrogen, soil.phosphorus, soil.potassium, soil.ph, f.crop or "default")
            soil_grades.append(res["overall"])
    soil_summary = dict(Counter(soil_grades))

    # --- water ---
    moisture_by_farm = latest_moisture_by_farm(db, farms)
    water_statuses = Counter(water_status_for_moisture(m) for m in moisture_by_farm.values())
    monitored = sum(1 for m in moisture_by_farm.values() if m is not None)

    # --- schemes: eligible vs engaged ---
    schemes = db.query(Scheme).all()
    eligible_farmers = set()
    for f in farms:
        profile = _farm_profile(f)
        if any(evaluate_scheme(s, profile)["verdict"] == "Likely eligible" for s in schemes):
            eligible_farmers.add(f.user_id)
    engaged_ids = {i.user_id for i in
                  db.query(SchemeInterest).filter(SchemeInterest.state == state).all()}
    adoption_pct = (round(100 * len(engaged_ids & eligible_farmers) / len(eligible_farmers), 1)
                    if eligible_farmers else None)

    # --- machinery demand (views + contact requests = interest signal) ---
    mq = db.query(MachineryListing).filter(MachineryListing.state == state)
    if district:
        mq = mq.filter(MachineryListing.district == district)
    machinery = mq.all()
    demand = Counter()
    for m in machinery:
        demand[m.machine_key] += (m.views or 0) + 3 * (m.contact_requests or 0)
    machinery_demand = [{"machine": k, "demand_score": v} for k, v in demand.most_common(5)]

    # --- farmer activity (recent platform activity, last 30 days) ---
    since = datetime.utcnow() - timedelta(days=30)
    recent_activity = (
        (db.query(SoilTest).filter(SoilTest.user_id.in_(user_ids), SoilTest.created_at >= since).count()
         if user_ids else 0)
        + (db.query(PlantDiagnosis).filter(PlantDiagnosis.user_id.in_(user_ids),
                                           PlantDiagnosis.created_at >= since).count() if user_ids else 0)
        + (db.query(PestObservation).filter(PestObservation.user_id.in_(user_ids),
                                            PestObservation.created_at >= since).count() if user_ids else 0)
        + lq.filter(CropListing.created_at >= since).count()
    )

    return {
        "state": state, "district": district or None,
        "farmer_count": len(user_ids),
        "crops": {
            "dominant": [{"crop": c, "farms": n} for c, n in dominant_crops.most_common(10)],
            "listing_volume": [{"crop": c, "listings": n} for c, n in listing_volume.most_common(10)],
            "increasing": sorted(increasing), "declining": sorted(declining),
            "trend_basis": ("Compares the two most recent months of marketplace listings — "
                            "observed platform data, not official production statistics."),
        },
        "pest_disease": {
            "pest_reports": [{"pest": p, "reports": n} for p, n in pest_counts.most_common(10)],
            "disease_reports": [{"disease": d, "reports": n} for d, n in disease_counts.most_common(10)],
            "by_severity": dict(severity_counts),
        },
        "soil": {"samples": len(soil_grades), "breakdown": soil_summary},
        "water": {
            "monitored_farms": monitored, "total_farms": len(farms),
            "by_status": dict(water_statuses),
            "note": ("No live sensor data available for this area." if monitored == 0 else
                     "Status is based on the most recent soil-moisture reading per monitored farm."),
        },
        "schemes": {
            "eligible_farmers": len(eligible_farmers),
            "engaged_farmers": len(engaged_ids & eligible_farmers),
            "adoption_pct": adoption_pct,
        },
        "machinery_demand": machinery_demand,
        "farmer_activity_30d": recent_activity,
    }


# ---------------------------------------------------------------- health score

def health_score(state_data: dict) -> dict:
    """A transparent, weighted 0-100 score from signals already shown
    elsewhere on the dashboard — never a random or hidden number.

    Weights (documented, not hidden):
      30% soil health, 25% pest/disease pressure (inverse), 20% water
      status, 15% scheme adoption, 10% recent farmer activity.
    A component with no data contributes nothing and is flagged as such,
    rather than silently pulling the score toward a default.
    """
    components = []

    soil = state_data["soil"]["breakdown"]
    soil_total = sum(soil.values())
    if soil_total:
        good_ratio = (soil.get("Good", 0) + 0.5 * soil.get("Fair", 0)) / soil_total
        components.append(("soil_health", 30, good_ratio * 100,
                           f"{soil_total} soil test(s): {soil}"))
    else:
        components.append(("soil_health", 30, None, "No soil test data yet."))

    pd = state_data["pest_disease"]
    total_reports = sum(r["reports"] for r in pd["pest_reports"]) + sum(r["reports"] for r in pd["disease_reports"])
    farmers = max(state_data["farmer_count"], 1)
    reports_per_farmer = total_reports / farmers
    # 0 reports/farmer -> 100; 2+ reports/farmer -> 0 (linear in between)
    pest_score = max(0, 100 - reports_per_farmer * 50)
    components.append(("pest_disease_pressure", 25, pest_score,
                       f"{total_reports} pest/disease report(s) across {farmers} farmer(s)."))

    water = state_data["water"]["by_status"]
    water_total = sum(water.values())
    if water_total:
        w_score = (water.get("normal", 0) * 100 + water.get("watch", 0) * 65
                  + water.get("stressed", 0) * 30 + water.get("critical", 0) * 0) / water_total
        components.append(("water_status", 20, w_score,
                           f"{state_data['water']['monitored_farms']} monitored farm(s): {water}"))
    else:
        components.append(("water_status", 20, None, "No live sensor data available."))

    adoption = state_data["schemes"]["adoption_pct"]
    if adoption is not None:
        components.append(("scheme_adoption", 15, adoption,
                           f"{state_data['schemes']['engaged_farmers']}/"
                           f"{state_data['schemes']['eligible_farmers']} eligible farmers engaged."))
    else:
        components.append(("scheme_adoption", 15, None, "No farmers currently eligible for a tracked scheme."))

    activity = state_data["farmer_activity_30d"]
    act_score = min(100, activity * 10)  # 10+ actions/30d across the state -> full marks
    components.append(("farmer_activity", 10, act_score,
                       f"{activity} platform action(s) in the last 30 days."))

    scored = [(w, s) for _, w, s, _ in components if s is not None]
    total_weight = sum(w for w, _ in scored) or 1
    score = round(sum(w * s for w, s in scored) / total_weight, 0) if scored else None

    label = ("No data yet" if score is None else
             "GOOD" if score >= 70 else "FAIR" if score >= 45 else "NEEDS ATTENTION")

    return {
        "score": score, "label": label,
        "breakdown": [{"factor": name, "weight_pct": w,
                       "score": (round(s, 1) if s is not None else None),
                       "evidence": ev} for name, w, s, ev in components],
        "methodology": ("Weighted average of five factors (soil health 30%, pest/disease "
                        "pressure 25%, water status 20%, scheme adoption 15%, recent farmer "
                        "activity 10%). A factor with no data is excluded and the remaining "
                        "weights are renormalised — it is never defaulted to a fixed value."),
    }


# ---------------------------------------------------------------- priority alerts

def priority_alerts(db: Session) -> list[dict]:
    """Rule-based, evidence-backed early-warning alerts across all states.

    Every alert here is generated from an explicit, named threshold applied
    to real counts — never invented to make the dashboard look active. If a
    threshold isn't crossed anywhere, this returns an empty list.
    """
    alerts = []
    since_recent = datetime.utcnow() - timedelta(days=30)
    since_prior = datetime.utcnow() - timedelta(days=60)

    states = [s["state"] for s in list_states(db)]
    for state in states:
        user_ids = [u.id for u in db.query(User).filter(User.state == state).all()]
        if not user_ids:
            continue

        # Pest alert: recent reports vs. the prior 30-day period.
        recent = (db.query(PestObservation)
                  .filter(PestObservation.user_id.in_(user_ids),
                         PestObservation.created_at >= since_recent).count())
        prior = (db.query(PestObservation)
                .filter(PestObservation.user_id.in_(user_ids),
                       PestObservation.created_at >= since_prior,
                       PestObservation.created_at < since_recent).count())
        if recent >= 3 and (prior == 0 or recent >= prior * 1.5):
            alerts.append({
                "type": "pest", "severity": "CRITICAL" if recent >= 6 else "WARNING",
                "state": state, "title": f"Pest reports rising in {state}",
                "evidence": f"{recent} report(s) in the last 30 days vs {prior} in the prior 30 days.",
                "why": ["Recent-period report count", "Comparison to prior 30-day period",
                       "Threshold: >=3 reports and >=1.5x prior period"],
                "recommended_action": "Review affected districts and consider a pest advisory.",
                "date": datetime.utcnow().isoformat(),
            })

        # Water alert: share of monitored farms in stressed/critical.
        farms = db.query(Farm).join(User, Farm.user_id == User.id).filter(User.state == state).all()
        moisture = latest_moisture_by_farm(db, farms)
        monitored = [m for m in moisture.values() if m is not None]
        if monitored:
            bad = sum(1 for m in monitored if water_status_for_moisture(m) in ("stressed", "critical"))
            if bad and bad / len(monitored) >= 0.4:
                alerts.append({
                    "type": "water", "severity": "WARNING",
                    "state": state, "title": f"Multiple farms below optimal soil moisture in {state}",
                    "evidence": f"{bad}/{len(monitored)} monitored farm(s) at stressed or critical moisture.",
                    "why": [f"{len(monitored)} farm(s) with live sensor data",
                           f"{bad} below the stressed threshold ({MOISTURE_STRESSED}%)",
                           "Threshold: >=40% of monitored farms affected"],
                    "recommended_action": "Prioritise irrigation support outreach in this state.",
                    "date": datetime.utcnow().isoformat(),
                })

        # Scheme alert: low adoption among eligible farmers (needs enough eligible farmers to be meaningful).
        detail = state_detail(db, state)
        adoption = detail["schemes"]["adoption_pct"]
        eligible = detail["schemes"]["eligible_farmers"]
        if adoption is not None and eligible >= 5 and adoption < 20:
            alerts.append({
                "type": "scheme", "severity": "INFO",
                "state": state, "title": f"Low scheme engagement in {state}",
                "evidence": f"Only {adoption}% of {eligible} eligible farmer(s) have marked a scheme as chosen.",
                "why": [f"{eligible} farmer(s) eligible for at least one scheme",
                       f"{detail['schemes']['engaged_farmers']} have marked interest",
                       "Threshold: <20% adoption with >=5 eligible farmers"],
                "recommended_action": "Consider awareness outreach for high-value schemes in this state.",
                "date": datetime.utcnow().isoformat(),
            })

        # Crop/marketplace alert: rapidly increasing listing activity.
        if detail["crops"]["increasing"]:
            alerts.append({
                "type": "market", "severity": "INFO",
                "state": state, "title": f"Marketplace activity rising for {', '.join(detail['crops']['increasing'][:3])} in {state}",
                "evidence": "Listing counts for these crops increased month-over-month.",
                "why": ["Compared the two most recent months of marketplace listings"],
                "recommended_action": "Monitor for potential oversupply if prices soften.",
                "date": datetime.utcnow().isoformat(),
            })

    order = {"CRITICAL": 0, "WARNING": 1, "INFO": 2}
    alerts.sort(key=lambda a: order.get(a["severity"], 9))
    return alerts


# ---------------------------------------------------------------- scenarios

def scenario_pest_advisory(db: Session, state: str, district: str = "", crop: str = "") -> dict:
    """SCENARIO SIMULATION — not a guaranteed outcome. Estimates who a pest
    advisory would reach, based on real farmer records matching the filters,
    and how the platform would notify them."""
    q = db.query(Farm).join(User, Farm.user_id == User.id).filter(User.state == state)
    if district:
        q = q.filter(User.district == district)
    if crop:
        q = q.filter(Farm.crop.ilike(f"%{crop}%"))
    farms = q.all()
    districts_covered = sorted({f.district for f in farms if f.district})
    crops_covered = sorted({f.crop for f in farms if f.crop})
    return {
        "scenario": True,
        "action": "pest_advisory",
        "farmers_targeted": len(farms),
        "districts_affected": districts_covered,
        "crops_affected": crops_covered,
        "expected_coverage": (f"{len(farms)} farmer(s) with a registered farm matching the filters "
                              f"would be reachable — the platform has no SMS/notification system yet, "
                              f"so this describes reach if one existed, not a message actually sent."),
        "resources_required": "One advisory message per farmer; no infrastructure currently exists to send it automatically.",
    }


def scenario_irrigation_support(db: Session, state: str, district: str = "") -> dict:
    """SCENARIO SIMULATION — estimates which monitored farms would benefit
    from additional irrigation resources, from real sensor readings."""
    q = db.query(Farm).join(User, Farm.user_id == User.id).filter(User.state == state)
    if district:
        q = q.filter(User.district == district)
    farms = q.all()
    moisture = latest_moisture_by_farm(db, farms)
    affected = [f for f in farms if water_status_for_moisture(moisture.get(f.id)) in ("stressed", "critical")]
    return {
        "scenario": True,
        "action": "irrigation_support",
        "farms_targeted": len(affected),
        "districts_affected": sorted({f.district for f in affected if f.district}),
        "monitored_farms_considered": sum(1 for v in moisture.values() if v is not None),
        "expected_coverage": (f"{len(affected)} farm(s) currently reporting stressed or critical soil "
                              f"moisture would be prioritised."),
    }
