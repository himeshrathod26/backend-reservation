import hashlib, json, logging, time, uuid
from fastapi import FastAPI, Depends, Header, HTTPException, Request, Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from sqlalchemy import text, select, func
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session
from .db import get_db, engine
from .models import Base, Show, Seat, Reservation, ReservationSeat
from .schemas import ShowCreate, ReserveRequest
from .metrics import RES_CONFIRMED, RES_DECLINED, REQS, LATENCY, SEATS_AVAILABLE

logging.basicConfig(level=logging.INFO, format='%(message)s')
log = logging.getLogger("seat-service")
app = FastAPI(title="Seat Reservation at Scale", version="1.0.0")

@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)

@app.middleware("http")
async def request_metrics(request: Request, call_next):
    start = time.perf_counter()
    rid = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    try:
        response = await call_next(request)
    except Exception:
        REQS.labels(request.method, request.url.path, "500").inc()
        raise
    duration = time.perf_counter() - start
    response.headers["X-Request-ID"] = rid
    REQS.labels(request.method, request.url.path, str(response.status_code)).inc()
    LATENCY.labels(request.method, request.url.path).observe(duration)
    log.info(json.dumps({"request_id": rid, "method": request.method, "path": request.url.path, "status": response.status_code, "duration_ms": round(duration*1000, 2)}))
    return response

def auth_user(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "missing bearer token")
    user_id = authorization[7:].strip()
    if not user_id:
        raise HTTPException(401, "invalid bearer token")
    return user_id

def response_reservation(db: Session, r: Reservation):
    seats = db.execute(select(Seat.seat_number).join(ReservationSeat, ReservationSeat.seat_id == Seat.id).where(ReservationSeat.reservation_id == r.id).order_by(Seat.seat_number)).scalars().all()
    return {"reservation_id": str(r.id), "show_id": str(r.show_id), "user_id": r.user_id, "seats": seats, "amount_paise": r.amount_paise, "status": r.status}

def request_hash(seats: list[str], idem: str) -> str:
    raw = json.dumps({"seats": sorted(seats), "idempotency_key": idem}, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()

@app.get("/health/live")
def live():
    return {"status": "ok"}

@app.get("/health/ready")
def ready(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception:
        raise HTTPException(503, "database unavailable")

@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

@app.post("/shows", status_code=201)
def create_show(payload: ShowCreate, db: Session = Depends(get_db)):
    show = Show(name=payload.name, price_paise=payload.price_paise, per_user_limit=payload.per_user_limit)
    db.add(show); db.flush()
    db.add_all([Seat(show_id=show.id, seat_number=s, status="available") for s in payload.seats])
    db.commit()
    return {"id": str(show.id), "name": show.name, "price_paise": show.price_paise, "per_user_limit": show.per_user_limit, "seats": [{"seat": s, "status": "available"} for s in payload.seats]}

@app.get("/shows/{show_id}")
def update_available_gauge(db: Session, show_id: uuid.UUID):
    n = db.execute(select(func.count(Seat.id)).where(Seat.show_id == show_id, Seat.status == "available")).scalar_one()
    SEATS_AVAILABLE.labels(str(show_id)).set(n)

@app.get("/shows/{show_id}")
def get_show(show_id: uuid.UUID, db: Session = Depends(get_db)):
    show = db.get(Show, show_id)
    if not show: raise HTTPException(404, "show not found")
    rows = db.execute(select(Seat.seat_number, Seat.status).where(Seat.show_id == show_id).order_by(Seat.seat_number)).all()
    counts = {"available": 0, "held": 0, "confirmed": 0}
    seats = []
    for n, status in rows:
        counts[status] += 1; seats.append({"seat": n, "status": status})
    SEATS_AVAILABLE.labels(str(show_id)).set(counts["available"])
    return {"id": str(show.id), "name": show.name, "price_paise": show.price_paise, "per_user_limit": show.per_user_limit, "total_seats": len(seats), "counts": counts, "seats": seats}

@app.post("/shows/{show_id}/reserve", status_code=201)
def reserve(show_id: uuid.UUID, payload: ReserveRequest, user_id: str = Depends(auth_user), db: Session = Depends(get_db)):
    h = request_hash(payload.seats, payload.idempotency_key)
    try:
        with db.begin():
            show = db.execute(select(Show).where(Show.id == show_id).with_for_update()).scalar_one_or_none()
            if not show: raise HTTPException(404, "show not found")

            existing = db.execute(select(Reservation).where(Reservation.show_id == show_id, Reservation.user_id == user_id, Reservation.idempotency_key == payload.idempotency_key).with_for_update()).scalar_one_or_none()
            if existing:
                if existing.request_hash != h:
                    RES_DECLINED.labels("idempotency_key_reuse").inc()
                    raise HTTPException(409, "idempotency key already used with a different request")
                RES_DECLINED.labels("idempotent_replay").inc()
                # FastAPI still returns 201 for the replay; body is identical to original.
                return response_reservation(db, existing)

            wanted = sorted(payload.seats)
            seats = db.execute(select(Seat).where(Seat.show_id == show_id, Seat.seat_number.in_(wanted)).order_by(Seat.seat_number).with_for_update()).scalars().all()
            if len(seats) != len(wanted):
                RES_DECLINED.labels("seat_not_found").inc(); raise HTTPException(409, "one or more seats do not exist")
            if any(s.status != "available" for s in seats):
                RES_DECLINED.labels("seat_taken").inc(); raise HTTPException(409, "one or more seats are already taken")

            existing_count = db.execute(select(func.count(ReservationSeat.seat_id)).join(Reservation, Reservation.id == ReservationSeat.reservation_id).where(Reservation.show_id == show_id, Reservation.user_id == user_id, Reservation.status == "confirmed")).scalar_one()
            if existing_count + len(seats) > show.per_user_limit:
                RES_DECLINED.labels("per_user_limit").inc(); raise HTTPException(409, "per-user seat limit exceeded")

            r = Reservation(show_id=show_id, user_id=user_id, idempotency_key=payload.idempotency_key, request_hash=h, amount_paise=show.price_paise * len(seats), status="confirmed")
            db.add(r); db.flush()
            for seat in seats:
                seat.status = "confirmed"; seat.reservation_id = r.id
                db.add(ReservationSeat(reservation_id=r.id, seat_id=seat.id))
            RES_CONFIRMED.inc()
            update_available_gauge(db, show_id)
            return response_reservation(db, r)
    except HTTPException:
        raise
    except IntegrityError:
        db.rollback()
        RES_DECLINED.labels("conflict").inc()
        raise HTTPException(409, "reservation conflict; retry with the same idempotency key")
    except OperationalError:
        db.rollback()
        raise HTTPException(503, "database temporarily unavailable")

@app.post("/reservations/{reservation_id}/cancel")
def cancel(reservation_id: uuid.UUID, user_id: str = Depends(auth_user), db: Session = Depends(get_db)):
    with db.begin():
        r = db.execute(select(Reservation).where(Reservation.id == reservation_id).with_for_update()).scalar_one_or_none()
        if not r: raise HTTPException(404, "reservation not found")
        if r.user_id != user_id: raise HTTPException(403, "not reservation owner")
        if r.status == "cancelled": return response_reservation(db, r)
        seats = db.execute(select(Seat).where(Seat.reservation_id == r.id).with_for_update()).scalars().all()
        for seat in seats:
            seat.status = "available"; seat.reservation_id = None
        r.status = "cancelled"
        update_available_gauge(db, r.show_id)
        return response_reservation(db, r)
