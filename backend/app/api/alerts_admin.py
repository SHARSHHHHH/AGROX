import logging
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from urllib.parse import quote
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database.db import get_db
from app.models.models import (Alert, SensorReading, IrrigationEvent, User, Farm,
                               PlantDiagnosis, SoilTest, ChatMessage, PestObservation,
                               CropListing, SchemeInterest, Scheme, AdminAction,
                               MachineryListing, Expense)
from app.core.security import get_current_user, require_admin
from app.services.alerts import generate_for_user
from app.services import alerts as alerts_svc
from app.services import notifications
from app.models.models import PushSubscription, SupplyOffer
from pydantic import BaseModel

log = logging.getLogger("agri.api.alerts")
from app.services.recommendation import analyze_soil
from app.services import admin_intel

alerts_router = APIRouter(prefix="/api/alerts", tags=["alerts"])
analytics_router = APIRouter(prefix="/api/analytics", tags=["analytics"])
admin_router = APIRouter(prefix="/api/admin", tags=["admin"])


# ---------- ALERTS ----------
PRIORITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}


def _shape(a: Alert) -> dict:
    return {
        "id": a.id, "type": a.type, "category": a.category or "general",
        "priority": a.priority or "MEDIUM",
        "severity": a.severity,               # legacy clients
        "title": a.title, "message": a.message, "action": a.action or "",
        "read": a.read, "dismissed": bool(a.dismissed),
        "source": ({"name": a.source_name, "url": a.source_url,
                    "date": a.source_date.isoformat() if a.source_date else None}
                   if a.source_name or a.source_url else None),
        "payload": a.payload or {},
        "expires_at": a.expires_at.isoformat() if a.expires_at else None,
        "date": a.created_at.isoformat(),
    }


@alerts_router.get("")
async def get_alerts(category: str = "", priority: str = "",
                     unread_only: bool = False,
                     include_dismissed: bool = False,
                     limit: int = 100,
                     user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    """Alerts for this farmer, newest and most urgent first."""
    fresh = await generate_for_user(db, user)
    # Push only the newly created alerts, and only the urgent ones. Failure
    # here is swallowed: the alert is already saved and visible in-app, which
    # is the part that matters.
    try:
        notifications.dispatch(db, user.id, fresh)
    except Exception as exc:                                # noqa: BLE001
        log.warning("push dispatch failed: %s", exc)
    alerts_svc.expire_old(db, user.id)

    q = db.query(Alert).filter(Alert.user_id == user.id)
    if not include_dismissed:
        q = q.filter(Alert.dismissed == False)              # noqa: E712
    if category:
        q = q.filter(Alert.category == category)
    if priority:
        q = q.filter(Alert.priority == priority)
    if unread_only:
        q = q.filter(Alert.read == False)                   # noqa: E712

    rows = q.order_by(Alert.created_at.desc()).limit(min(limit, 200)).all()
    # A CRITICAL alert from this morning must outrank an INFO from a minute
    # ago, so priority sorts first and recency only breaks ties.
    rows.sort(key=lambda a: (PRIORITY_ORDER.get(a.priority or "MEDIUM", 2),
                             -a.created_at.timestamp()))
    return [_shape(a) for a in rows]


@alerts_router.get("/summary")
def alerts_summary(user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    """Unread counts by priority and category, for the badge and the filters."""
    alerts_svc.expire_old(db, user.id)
    rows = (db.query(Alert)
            .filter(Alert.user_id == user.id,
                    Alert.dismissed == False)               # noqa: E712
            .all())
    unread = [a for a in rows if not a.read]

    by_priority, by_category = {}, {}
    for a in unread:
        p = a.priority or "MEDIUM"
        by_priority[p] = by_priority.get(p, 0) + 1
        c = a.category or "general"
        by_category[c] = by_category.get(c, 0) + 1

    return {
        "total": len(rows), "unread": len(unread),
        "by_priority": by_priority, "by_category": by_category,
        "needs_attention": sum(1 for a in unread
                               if (a.priority or "") in ("CRITICAL", "HIGH")),
    }


@alerts_router.post("/{alert_id}/dismiss")
def dismiss_alert(alert_id: int, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    """Stop showing this alert.

    Distinct from marking it read: read means "I saw it", dismissed means
    "do not show me this again". Dismissal also suppresses regeneration,
    because the dedupe check skips dismissed rows deliberately — otherwise
    dismissing would be undone on the very next poll.
    """
    a = (db.query(Alert)
         .filter(Alert.id == alert_id, Alert.user_id == user.id).first())
    if a is None:
        raise HTTPException(404, "Alert not found.")
    a.dismissed = True
    a.dismissed_at = datetime.utcnow()
    a.read = True
    db.commit()
    return {"status": "dismissed", "id": alert_id}


@alerts_router.post("/read-all")
def mark_all_read(user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    rows = (db.query(Alert)
            .filter(Alert.user_id == user.id, Alert.read == False)  # noqa: E712
            .all())
    for r in rows:
        r.read = True
    db.commit()
    return {"status": "ok", "marked": len(rows)}


@alerts_router.post("/{alert_id}/read")
def mark_read(alert_id: int, user: User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    a = db.query(Alert).filter(Alert.id == alert_id, Alert.user_id == user.id).first()
    if a:
        a.read = True; db.commit()
    return {"status": "ok"}


# ---------- ANALYTICS ----------
@analytics_router.get("")
def analytics(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    farm = db.query(Farm).filter(Farm.user_id == user.id).first()
    device_id = farm.device_id if farm and farm.device_id else "ESP32-001"
    readings = (db.query(SensorReading).filter(SensorReading.device_id == device_id)
                .order_by(SensorReading.created_at.desc()).limit(50).all())
    readings = list(reversed(readings))

    series = [{"time": r.created_at.strftime("%H:%M"),
               "soil_moisture": r.soil_moisture, "temperature": r.temperature,
               "humidity": r.humidity, "water_level": r.water_level,
               "source": r.source} for r in readings]

    irr = (db.query(IrrigationEvent).filter(IrrigationEvent.user_id == user.id)
           .order_by(IrrigationEvent.created_at.desc()).limit(20).all())
    irrigation = [{"date": e.created_at.strftime("%m-%d %H:%M"),
                   "duration": e.duration_min} for e in reversed(irr)]

    # Simple insight
    insight = "Not enough data yet for trends."
    if len(readings) >= 6:
        recent = [r.soil_moisture for r in readings[-6:]]
        if all(m < 35 for m in recent):
            insight = "Soil moisture has remained low for the recent readings."
        elif sum(recent) / len(recent) > 55:
            insight = "Soil moisture has been healthy recently."
        else:
            insight = "Soil moisture is fluctuating within a normal range."

    # ---- Crops sowed / grown (from this farmer's marketplace listings —
    # the only place sowing and maturity are actually recorded) ----
    listings = (db.query(CropListing).filter(CropListing.farmer_id == user.id)
               .order_by(CropListing.created_at.desc()).all())
    sowed = [l for l in listings if l.sowing_date]
    grown = [l for l in listings if l.status in ("available", "sold")]
    by_crop: dict[str, dict] = {}
    for l in listings:
        if not l.crop:
            continue
        rec = by_crop.setdefault(l.crop, {"crop": l.crop, "sowed": 0, "grown": 0})
        if l.sowing_date:
            rec["sowed"] += 1
        if l.status in ("available", "sold"):
            rec["grown"] += 1
    crops_analysis = "No crops logged yet — list a crop on the Sell Produce page to start tracking."
    if sowed:
        rate = round(100 * len(grown) / len(sowed), 1)
        crops_analysis = (f"{len(sowed)} crop(s) sown, {len(grown)} reached maturity "
                          f"({rate}% matured so far). "
                          + (f"Still growing: {len(sowed) - len(grown)}." if len(sowed) > len(grown) else "All sown crops have matured."))

    # ---- Spent vs earned ----
    sold = [l for l in listings if l.status == "sold"]
    earned = sum((l.price_per_kg or 0) * (l.quantity_kg or 0) for l in sold)
    expenses = (db.query(Expense).filter(Expense.user_id == user.id)
               .order_by(Expense.created_at.desc()).all())
    spent = sum(e.amount for e in expenses)
    by_category: dict[str, float] = defaultdict(float)
    for e in expenses:
        by_category[e.category] += e.amount

    return {"series": series, "irrigation": irrigation, "insight": insight,
            "data_note": "Readings tagged 'simulated' are demo data, 'esp32' are "
                         "from real hardware.",
            "crops": {
                "sowed": len(sowed), "grown": len(grown), "growing": len(sowed) - len(grown),
                "by_crop": list(by_crop.values()), "analysis": crops_analysis,
            },
            "finance": {
                "earned": round(earned, 2), "spent": round(spent, 2),
                "net": round(earned - spent, 2),
                "sold_listings": len(sold),
                "expense_count": len(expenses),
                "by_category": [{"category": k, "amount": round(v, 2)} for k, v in by_category.items()],
                "recent_expenses": [{"id": e.id, "category": e.category, "amount": e.amount,
                                     "note": e.note, "crop": e.crop,
                                     "date": e.created_at.isoformat()} for e in expenses[:10]],
                "note": ("'Earned' is the total value of your SOLD marketplace listings. "
                        "'Spent' is only what you've logged below — log an expense to keep "
                        "this accurate; nothing is estimated automatically."),
            }}


@analytics_router.post("/expenses")
def add_expense(category: str, amount: float, note: str = "", crop: str = "",
                user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if amount < 0:
        raise HTTPException(400, "Amount must be positive")
    e = Expense(user_id=user.id, category=category, amount=amount, note=note, crop=crop)
    db.add(e); db.commit(); db.refresh(e)
    return {"id": e.id, "category": e.category, "amount": e.amount,
           "note": e.note, "crop": e.crop, "date": e.created_at.isoformat()}


@analytics_router.delete("/expenses/{expense_id}")
def delete_expense(expense_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    e = db.query(Expense).filter(Expense.id == expense_id, Expense.user_id == user.id).first()
    if e:
        db.delete(e); db.commit()
    return {"status": "ok"}


# ---------- ADMIN / GOVERNMENT DASHBOARD ----------
@admin_router.get("/overview")
def admin_overview(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Aggregate view for agriculture officers / government:
    who is using the platform, what problems dominate, soil fertility by
    location, and which schemes people actually need."""
    total_users = db.query(func.count(User.id)).scalar()
    farmers = db.query(func.count(User.id)).filter(User.role == "farmer").scalar()
    balcony = db.query(func.count(User.id)).filter(User.role == "balcony").scalar()

    # Major problems: from alerts + AI chat intents
    alert_types = Counter(a.type for a in db.query(Alert).all())
    diagnoses = db.query(PlantDiagnosis).all()
    disease_counts = Counter(d.disease for d in diagnoses
                             if d.disease not in ("Healthy", "Uncertain"))

    # Soil fertility by location (district)
    fertility_by_location = {}
    for farm in db.query(Farm).all():
        loc = farm.district or farm.state or farm.location or "Unknown"
        soil = (db.query(SoilTest).filter(SoilTest.user_id == farm.user_id)
                .order_by(SoilTest.created_at.desc()).first())
        if not soil:
            continue
        res = analyze_soil(soil.nitrogen, soil.phosphorus, soil.potassium,
                           soil.ph, farm.crop or "default")
        fertility_by_location.setdefault(loc, []).append(res["overall"])

    fertility_summary = []
    for loc, grades in fertility_by_location.items():
        c = Counter(grades)
        dominant = c.most_common(1)[0][0]
        fertility_summary.append({"location": loc, "samples": len(grades),
                                  "dominant_health": dominant,
                                  "breakdown": dict(c)})

    # Scheme demand: infer from user profiles (categories/states present)
    category_demand = Counter(f.farmer_category for f in db.query(Farm).all())
    state_demand = Counter(u.state for u in db.query(User).all() if u.state)

    return {
        "users": {"total": total_users, "farmers": farmers, "balcony": balcony},
        "major_problems": {
            "alerts": dict(alert_types.most_common()),
            "diseases_detected": dict(disease_counts.most_common()),
        },
        "soil_fertility_by_location": fertility_summary,
        "scheme_demand": {
            "by_farmer_category": dict(category_demand.most_common()),
            "by_state": dict(state_demand.most_common()),
        },
        "recommendation_for_government": _gov_reco(fertility_summary, disease_counts,
                                                   category_demand),
    }


def _gov_reco(fertility_summary, disease_counts, category_demand) -> list[str]:
    recos = []
    poor = [f["location"] for f in fertility_summary if f["dominant_health"] == "Poor"]
    if poor:
        recos.append(f"Prioritise soil-health / fertiliser subsidy outreach in: "
                     f"{', '.join(poor)}.")
    if disease_counts:
        top = disease_counts.most_common(1)[0]
        recos.append(f"Most reported crop disease is '{top[0]}' ({top[1]} cases) — "
                     f"consider advisory campaigns and input support.")
    if category_demand:
        top_cat = category_demand.most_common(1)[0][0]
        recos.append(f"Largest user group is '{top_cat}' farmers — target schemes for "
                     f"this category for maximum reach.")
    if not recos:
        recos.append("Insufficient data. Encourage more soil tests and diagnoses.")
    return recos


# ---------- COMMAND CENTER: state-wise, KPIs, health score, alerts, ----------
# ---------- predictive trend, scenarios, human-in-the-loop actions,   ----------
# ---------- and the admin AI agent's data-query endpoint              ----------
#
# The government dashboard's real job: an officer sees ecosystem-wide KPIs,
# then clicks a state (and optionally a district) to see what's actually
# happening there — never farmer-facing tools like Farm Setup or Weather,
# which have no place in an admin's view.

@admin_router.get("/kpis")
def admin_kpis(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return admin_intel.compute_kpis(db)


@admin_router.get("/states")
def admin_states(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """States with at least one registered farmer/grower, for the state
    picker. Only states with real data are listed — an empty state would
    just be a dead end."""
    return admin_intel.list_states(db)


@admin_router.get("/states/{state}/districts")
def admin_districts(state: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Districts within a state, for the state -> district drill-down."""
    return admin_intel.list_districts(db, state)


@admin_router.get("/state/{state}")
def admin_state_detail(state: str, district: str = "",
                       admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Full state (optionally district) intelligence: dominant/increasing/
    declining crops, pest & disease reports, soil conditions, water status,
    scheme adoption, machinery demand, and recent farmer activity — plus a
    transparent, weighted agricultural health score built from those same
    numbers.
    """
    detail = admin_intel.state_detail(db, state, district)

    # "Most sold crops" — completed marketplace sales, kept separate from
    # "listing volume" (which includes produce still growing).
    sq = db.query(CropListing).filter(CropListing.state == state, CropListing.status == "sold")
    if district:
        sq = sq.filter(CropListing.district == district)
    sold = sq.all()
    sold_counts = Counter(l.crop for l in sold if l.crop)
    sold_qty: dict[str, float] = defaultdict(float)
    for l in sold:
        if l.crop:
            sold_qty[l.crop] += l.quantity_kg or 0
    detail["most_sold_crops"] = [{"crop": c, "listings_sold": n, "total_kg": round(sold_qty[c], 1)}
                                 for c, n in sold_counts.most_common(10)]

    # Schemes farmers have actually chosen (separate from the eligible-vs-
    # engaged adoption number, which is aggregate).
    iq = db.query(SchemeInterest).filter(SchemeInterest.state == state)
    interests = iq.all()
    scheme_id_counts = Counter(i.scheme_id for i in interests)
    scheme_names: dict[int, str] = {}
    if scheme_id_counts:
        for s in db.query(Scheme).filter(Scheme.id.in_(scheme_id_counts.keys())).all():
            scheme_names[s.id] = s.name
    detail["schemes_chosen"] = [{"scheme": scheme_names.get(sid, f"Scheme #{sid}"), "farmers": n}
                                for sid, n in scheme_id_counts.most_common(10)]

    since = datetime.utcnow() - timedelta(days=30)
    uq = db.query(User).filter(User.state == state)
    if district:
        uq = uq.filter(User.district == district)
    user_ids = [u.id for u in uq.all()]
    alerts = ((db.query(Alert)
              .filter(Alert.user_id.in_(user_ids), Alert.created_at >= since,
                     Alert.severity.in_(("WARNING", "CRITICAL")))
              .order_by(Alert.created_at.desc()).limit(20).all())
             if user_ids else [])
    detail["immediate_alerts"] = [{"title": a.title, "message": a.message,
                                   "severity": a.severity, "date": a.created_at.isoformat()}
                                  for a in alerts]

    detail["health_score"] = admin_intel.health_score(detail)
    detail["note"] = ("Crop listing/production figures come from the marketplace — a real "
                      "signal from this platform, not an official agricultural census.")
    return detail


@admin_router.get("/priority-alerts")
def admin_priority_alerts(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Rule-based, evidence-backed early-warning alerts across all states.
    Generated only when a named threshold is actually crossed — never
    fabricated to make the dashboard look active."""
    return admin_intel.priority_alerts(db)


@admin_router.get("/predictive/{state}")
def admin_predictive(state: str, metric: str = "listings", crop: str = "",
                     admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """A plain linear-trend forecast (not an LLM) over real monthly counts.
    metric: 'listings' (marketplace activity) or 'pest_reports'."""
    monthly: dict[str, float] = defaultdict(float)
    if metric == "pest_reports":
        user_ids = [u.id for u in db.query(User).filter(User.state == state).all()]
        rows = (db.query(PestObservation).filter(PestObservation.user_id.in_(user_ids)).all()
               if user_ids else [])
        for r in rows:
            if r.created_at:
                monthly[r.created_at.strftime("%Y-%m")] += 1
    else:
        q = db.query(CropListing).filter(CropListing.state == state)
        if crop:
            q = q.filter(CropListing.crop == crop)
        for r in q.all():
            if r.created_at:
                monthly[r.created_at.strftime("%Y-%m")] += 1

    return {"state": state, "metric": metric, "crop": crop or None,
            **admin_intel.linear_trend(dict(monthly))}


@admin_router.post("/scenario/pest-advisory")
def admin_scenario_pest(state: str, district: str = "", crop: str = "",
                        admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return admin_intel.scenario_pest_advisory(db, state, district, crop)


@admin_router.post("/scenario/irrigation-support")
def admin_scenario_irrigation(state: str, district: str = "",
                              admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return admin_intel.scenario_irrigation_support(db, state, district)


# ---------- human-in-the-loop actions ----------

@admin_router.post("/actions/propose")
def propose_action(action_type: str, state: str, district: str = "", crop: str = "",
                   admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """AI proposes an action from real data; nothing happens until an admin
    explicitly approves it (see /actions/{id}/decide)."""
    if action_type == "pest_advisory":
        sim = admin_intel.scenario_pest_advisory(db, state, district, crop)
        title = f"Send pest advisory — {state}{' / ' + district if district else ''}"
        reasoning = [f"{sim['farmers_targeted']} farmer(s) match this state/district/crop filter",
                    "Proposed in response to rising pest reports (see Priority Alerts)"]
        affected = sim["farmers_targeted"]
    elif action_type == "irrigation_support":
        sim = admin_intel.scenario_irrigation_support(db, state, district)
        title = f"Prioritise irrigation support — {state}{' / ' + district if district else ''}"
        reasoning = [f"{sim['farms_targeted']} farm(s) at stressed/critical soil moisture",
                    f"{sim['monitored_farms_considered']} farm(s) have live sensor data"]
        affected = sim["farms_targeted"]
    else:
        raise HTTPException(400, "Unknown action_type")

    action = AdminAction(action_type=action_type, title=title,
                         description=f"Proposed from live platform data for {state}"
                                    + (f", {district}" if district else ""),
                         state=state, district=district, crop=crop,
                         affected_count=affected, reasoning=reasoning, status="proposed")
    db.add(action); db.commit(); db.refresh(action)
    return _action_out(action)


@admin_router.get("/actions")
def list_actions(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.query(AdminAction).order_by(AdminAction.proposed_at.desc()).limit(50).all()
    return [_action_out(a) for a in rows]


@admin_router.post("/actions/{action_id}/decide")
def decide_action(action_id: int, status: str,
                  admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    if status not in ("approved", "rejected"):
        raise HTTPException(400, "status must be approved or rejected")
    action = db.query(AdminAction).get(action_id)
    if not action:
        raise HTTPException(404, "Action not found")
    action.status = status
    action.decided_at = datetime.utcnow()
    action.decided_by_id = admin.id
    db.commit()
    note = None
    if status == "approved":
        note = ("Prototype workflow: this platform has no SMS/notification system yet, "
                "so approving this records the decision but does not send anything.")
    return {"status": "ok", "action": _action_out(action), "note": note}


def _action_out(a: AdminAction) -> dict:
    return {"id": a.id, "action_type": a.action_type, "title": a.title,
           "description": a.description, "state": a.state, "district": a.district,
           "crop": a.crop, "affected_count": a.affected_count, "reasoning": a.reasoning,
           "status": a.status, "proposed_at": a.proposed_at.isoformat(),
           "decided_at": a.decided_at.isoformat() if a.decided_at else None}


# ---------- admin AI agent: real-data Q&A + navigation ----------

@admin_router.get("/ask")
def admin_ask(q: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Answers a natural-language admin question by pattern-matching it to a
    real backend query (never an LLM guess), and returns a navigation target
    so the UI can jump straight to the relevant filtered view.

    This intentionally does NOT call an LLM to produce the numbers — only to
    (optionally, client-side) phrase them. The data in the answer always
    comes from the same functions the dashboard itself uses.
    """
    ql = q.lower()
    states = admin_intel.list_states(db)
    state_names = [s["state"] for s in states]
    matched_state = next((s for s in state_names if s.lower() in ql), None)

    def nav(tab: str, **params) -> str:
        parts = "&".join(f"{k}={quote(str(v))}" for k, v in params.items() if v)
        return f"/admin?tab={tab}" + (f"&{parts}" if parts else "")

    if "pest" in ql and ("highest" in ql or "most" in ql or "which state" in ql):
        alerts = [a for a in admin_intel.priority_alerts(db) if a["type"] == "pest"]
        if not alerts:
            return {"answer": "No state currently shows a significant rise in pest reports.",
                   "navigate_to": nav("alerts")}
        top = alerts[0]
        return {"answer": f"{top['state']} shows the most pest activity right now: {top['evidence']}",
               "evidence": [a["evidence"] + f" ({a['state']})" for a in alerts[:5]],
               "navigate_to": nav("state", state=top["state"])}

    if "water stress" in ql or ("water" in ql and "district" in ql):
        results = []
        for s in state_names:
            d = admin_intel.state_detail(db, s)
            bad = d["water"]["by_status"].get("stressed", 0) + d["water"]["by_status"].get("critical", 0)
            if bad:
                results.append((s, bad, d["water"]["monitored_farms"]))
        if not results:
            return {"answer": "No monitored farms are currently reporting water stress.",
                   "navigate_to": nav("alerts")}
        results.sort(key=lambda r: -r[1])
        lines = [f"{s}: {bad}/{mon} monitored farms stressed/critical" for s, bad, mon in results[:5]]
        return {"answer": "States with water stress: " + "; ".join(lines),
               "navigate_to": nav("state", state=results[0][0])}

    if matched_state and ("top crop" in ql or "dominant crop" in ql or
                          ("crop" in ql and "state" in ql)):
        d = admin_intel.state_detail(db, matched_state)
        top = d["crops"]["dominant"][:5]
        if not top:
            return {"answer": f"No farm crop data recorded for {matched_state} yet.",
                   "navigate_to": nav("state", state=matched_state)}
        answer = f"Top crops in {matched_state}: " + ", ".join(f"{c['crop']} ({c['farms']} farms)" for c in top)
        return {"answer": answer, "navigate_to": nav("state", state=matched_state)}

    if "market" in ql and ("concern" in ql or "trend" in ql):
        alerts = [a for a in admin_intel.priority_alerts(db) if a["type"] == "market"]
        if not alerts:
            return {"answer": "No notable marketplace trend concerns right now.", "navigate_to": nav("alerts")}
        return {"answer": "; ".join(a["title"] for a in alerts[:5]), "navigate_to": nav("alerts")}

    if "prioritize" in ql or "prioritise" in ql:
        alerts = admin_intel.priority_alerts(db)
        if not alerts:
            return {"answer": "There are no active priority alerts right now.", "navigate_to": nav("alerts")}
        lines = [f"[{a['severity']}] {a['title']}" for a in alerts[:5]]
        return {"answer": "In order of severity: " + " | ".join(lines), "navigate_to": nav("alerts")}

    if matched_state and ("why" in ql or "risk" in ql or "summarize" in ql or "summarise" in ql):
        d = admin_intel.state_detail(db, matched_state)
        d["health_score"] = admin_intel.health_score(d)
        hs = d["health_score"]
        evidence = "; ".join(f"{b['factor']}: {b['score'] if b['score'] is not None else 'no data'}"
                             for b in hs["breakdown"])
        return {"answer": f"{matched_state} health score is {hs['score']} ({hs['label']}). {evidence}.",
               "navigate_to": nav("state", state=matched_state)}

    return {"answer": ("I can answer questions about pest activity, water stress, top crops in a "
                       "state, market trends, or which alerts to prioritise — try asking one of those, "
                       "naming a state where relevant."),
           "navigate_to": None}


# =====================================================================
# Browser push subscriptions
# =====================================================================

class PushSubIn(BaseModel):
    endpoint: str
    p256dh: str = ""
    auth: str = ""
    user_agent: str = ""
    min_priority: str = "HIGH"


@alerts_router.get("/notifications/status")
def notification_status(user: User = Depends(get_current_user)):
    """Which channels work, plus the VAPID public key the browser needs."""
    return notifications.status()


@alerts_router.post("/notifications/subscribe")
def subscribe_push(data: PushSubIn, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    """Register this browser for push.

    Keyed on the endpoint so re-subscribing on the same device updates rather
    than duplicating — otherwise a farmer who reloads the page ten times gets
    ten copies of every notification.
    """
    existing = (db.query(PushSubscription)
                .filter(PushSubscription.endpoint == data.endpoint).first())
    if existing is None:
        existing = PushSubscription(user_id=user.id, endpoint=data.endpoint)
        db.add(existing)

    existing.user_id = user.id
    existing.channel = "web_push"
    existing.p256dh = data.p256dh
    existing.auth = data.auth
    existing.user_agent = data.user_agent[:200]
    existing.min_priority = (data.min_priority or "HIGH").upper()
    existing.active = True
    existing.failure_count = 0
    db.commit()
    return {"status": "subscribed", "min_priority": existing.min_priority}


@alerts_router.post("/notifications/unsubscribe")
def unsubscribe_push(data: PushSubIn, user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    row = (db.query(PushSubscription)
           .filter(PushSubscription.endpoint == data.endpoint,
                   PushSubscription.user_id == user.id).first())
    if row is not None:
        row.active = False
        db.commit()
    return {"status": "unsubscribed"}


# =====================================================================
# Fertiliser / manure offers  (alert family 8)
# =====================================================================

@alerts_router.get("/supply-offers")
def supply_offers(category: str = "",
                  user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    """Verified input offers near this farmer.

    Only `verified` rows are returned. An unverified fertiliser price shown to
    a farmer is an advertisement we cannot stand behind.
    """
    farm = db.query(Farm).filter(Farm.user_id == user.id).first()
    now = datetime.utcnow()

    q = (db.query(SupplyOffer)
         .filter(SupplyOffer.active == True,                 # noqa: E712
                 SupplyOffer.verified == True)               # noqa: E712
         .filter((SupplyOffer.expires_at.is_(None))
                 | (SupplyOffer.expires_at > now)))
    if category:
        q = q.filter(SupplyOffer.category == category)
    if farm and farm.district:
        q = q.filter(SupplyOffer.district == farm.district)

    rows = q.order_by(SupplyOffer.created_at.desc()).limit(50).all()
    return {
        "count": len(rows),
        "district": farm.district if farm else None,
        "offers": [{
            "id": o.id, "title": o.title, "category": o.category,
            "description": o.description, "brand": o.brand,
            "price": o.price, "price_unit": o.price_unit,
            "quantity_available": o.quantity_available,
            "seller_name": o.seller_name, "contact_phone": o.contact_phone,
            "location": ", ".join(x for x in (o.village, o.district, o.state) if x),
            "verified": o.verified,
        } for o in rows],
        "note": ("Only offers checked by an administrator are shown. Compare "
                 "against your soil test before buying — paying for nutrients "
                 "your soil already has is wasted money."),
    }
