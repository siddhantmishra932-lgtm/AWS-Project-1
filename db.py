"""SQLite data layer for TAF (replaces storage.js / localStorage)."""
import csv
import io
import json
import math
import random
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

from flask import current_app, g

BASE_DIR = Path(__file__).resolve().parent

SCHEMA = """
CREATE TABLE IF NOT EXISTS treks (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    location TEXT NOT NULL,
    district TEXT NOT NULL,
    difficulty TEXT NOT NULL,
    elevation INTEGER NOT NULL,
    distance REAL NOT NULL,
    duration TEXT NOT NULL,
    meeting_point TEXT NOT NULL,
    reporting_time TEXT NOT NULL,
    expected_return_time TEXT NOT NULL,
    price INTEGER NOT NULL,
    description TEXT NOT NULL,
    image TEXT NOT NULL,
    itinerary TEXT NOT NULL DEFAULT '[]',
    included TEXT NOT NULL DEFAULT '[]',
    excluded TEXT NOT NULL DEFAULT '[]',
    things_to_carry TEXT NOT NULL DEFAULT '[]',
    safety_rules TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS trek_dates (
    id TEXT PRIMARY KEY,
    trek_id TEXT NOT NULL REFERENCES treks(id) ON DELETE CASCADE,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    reporting_time TEXT NOT NULL DEFAULT '05:00',
    total_seats INTEGER NOT NULL,
    available_seats INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS bookings (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    trek_id TEXT NOT NULL,
    date_id TEXT NOT NULL,
    num_participants INTEGER NOT NULL,
    total_amount INTEGER NOT NULL,
    payment_status TEXT NOT NULL,
    booking_status TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS participants (
    id TEXT PRIMARY KEY,
    booking_id TEXT NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
    name TEXT, gender TEXT, contact TEXT, whatsapp TEXT, email TEXT,
    dob TEXT, age INTEGER, blood_group TEXT, food_pref TEXT, tshirt_size TEXT,
    id_type TEXT, id_number TEXT,
    emergency_name TEXT, emergency_rel TEXT, emergency_num TEXT,
    experience TEXT, fitness TEXT, limitations TEXT,
    address TEXT, city TEXT, state TEXT, pincode TEXT
);
"""

JSON_FIELDS = ("itinerary", "included", "excluded", "things_to_carry", "safety_rules")


# ---------------------------------------------------------------- connection
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"], isolation_level=None)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db(app):
    app.teardown_appcontext(close_db)
    with app.app_context():
        db = get_db()
        db.executescript(SCHEMA)
        if db.execute("SELECT COUNT(*) FROM treks").fetchone()[0] == 0:
            seed(db)


def seed(db):
    """Load the original DEFAULT_TREKS / DEFAULT_DATES.

    The original sample dates (Sep-Oct 2026) can be in the past, which would make
    every trek show 'No upcoming dates'. Seed dates are therefore shifted forward
    by whole weeks (weekday preserved) so the earliest one is at least a week away.
    """
    data = json.loads((BASE_DIR / "data" / "seed.json").read_text(encoding="utf-8"))
    for t in data["treks"]:
        db.execute(
            """INSERT INTO treks (id, name, location, district, difficulty, elevation,
               distance, duration, meeting_point, reporting_time, expected_return_time,
               price, description, image, itinerary, included, excluded,
               things_to_carry, safety_rules)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (t["id"], t["name"].strip(), t["location"], t["district"], t["difficulty"],
             t["elevation"], t["distance"], t["duration"], t["meetingPoint"],
             t["reportingTime"], t["expectedReturnTime"], t["price"], t["description"],
             t["image"], json.dumps(t["itinerary"]), json.dumps(t["included"]),
             json.dumps(t["excluded"]), json.dumps(t["thingsToCarry"]),
             json.dumps(t["safetyRules"])),
        )

    earliest = min(date.fromisoformat(d["startDate"]) for d in data["dates"])
    target = date.today() + timedelta(days=7)
    shift = 0
    if earliest < target:
        shift = math.ceil((target - earliest).days / 7) * 7
    for d in data["dates"]:
        s = date.fromisoformat(d["startDate"]) + timedelta(days=shift)
        e = date.fromisoformat(d["endDate"]) + timedelta(days=shift)
        db.execute(
            """INSERT INTO trek_dates (id, trek_id, start_date, end_date, reporting_time,
               total_seats, available_seats) VALUES (?,?,?,?,?,?,?)""",
            (d["id"], d["trekId"], s.isoformat(), e.isoformat(), d["reportingTime"],
             d["totalSeats"], d["availableSeats"]),
        )


# ------------------------------------------------------------------- helpers
def seat_status(available):
    """Status is derived from seats (it was a stored, easily-stale field in JS)."""
    if available <= 0:
        return "Full"
    if available <= 5:
        return "Almost Full"
    return "Available"


def _normalize_itinerary(itinerary):
    """Some seed treks use `timeSlots` instead of `items` (the JS crashed on those)."""
    out = []
    for day in itinerary:
        items = list(day.get("items") or [])
        for slot in day.get("timeSlots") or []:
            items.append(f"{slot['time']} - {slot['description']}")
        out.append({"day": day.get("day"), "title": day.get("title", ""), "items": items})
    return out


def _trek(row):
    if row is None:
        return None
    t = dict(row)
    for f in JSON_FIELDS:
        t[f] = json.loads(t[f] or "[]")
    t["itinerary"] = _normalize_itinerary(t["itinerary"])
    return t


def _date(row):
    if row is None:
        return None
    d = dict(row)
    d["status"] = seat_status(d["available_seats"])
    return d


def today_str():
    return date.today().isoformat()


# --------------------------------------------------------------------- treks
def get_treks():
    return [_trek(r) for r in get_db().execute("SELECT * FROM treks ORDER BY rowid")]


def get_trek(trek_id):
    return _trek(get_db().execute("SELECT * FROM treks WHERE id=?", (trek_id,)).fetchone())


def save_trek(data, trek_id=None):
    db = get_db()
    vals = (data["name"], data["location"], data["district"], data["difficulty"],
            data["elevation"], data["distance"], data["duration"], data["meeting_point"],
            data["reporting_time"], data["expected_return_time"], data["price"],
            data["description"], data["image"],
            json.dumps(data["included"]), json.dumps(data["excluded"]),
            json.dumps(data["things_to_carry"]))
    if trek_id:  # edit keeps the existing itinerary / safety rules
        db.execute(
            """UPDATE treks SET name=?, location=?, district=?, difficulty=?, elevation=?,
               distance=?, duration=?, meeting_point=?, reporting_time=?,
               expected_return_time=?, price=?, description=?, image=?, included=?,
               excluded=?, things_to_carry=? WHERE id=?""", vals + (trek_id,))
        return trek_id
    new_id = f"trek-{int(datetime.now().timestamp() * 1000)}"
    itinerary = [
        {"day": 1, "title": "Trek Begins",
         "items": ["Reporting at meeting point", "Reach base village, breakfast", "Ascent begins"]},
        {"day": 2, "title": "Descent & Return",
         "items": ["Sunrise view, breakfast", "Descent back to base village", "Lunch & return travel"]},
    ]
    rules = ["Always listen to trek leaders.", "Littering is strictly banned.",
             "No consumption of alcohol or toxic drugs."]
    db.execute(
        """INSERT INTO treks (name, location, district, difficulty, elevation, distance,
           duration, meeting_point, reporting_time, expected_return_time, price,
           description, image, included, excluded, things_to_carry, id, itinerary,
           safety_rules) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        vals + (new_id, json.dumps(itinerary), json.dumps(rules)))
    return new_id


def delete_trek(trek_id):
    # dates are removed by ON DELETE CASCADE (same as the JS behaviour)
    get_db().execute("DELETE FROM treks WHERE id=?", (trek_id,))


# --------------------------------------------------------------------- dates
def get_dates(trek_id=None, upcoming_only=False):
    sql, args = "SELECT * FROM trek_dates WHERE 1=1", []
    if trek_id:
        sql += " AND trek_id=?"
        args.append(trek_id)
    if upcoming_only:
        sql += " AND start_date >= ?"
        args.append(today_str())
    sql += " ORDER BY start_date"
    return [_date(r) for r in get_db().execute(sql, args)]


def get_date(date_id):
    return _date(get_db().execute("SELECT * FROM trek_dates WHERE id=?", (date_id,)).fetchone())


def add_date(trek_id, start, end, seats):
    new_id = f"date-{int(datetime.now().timestamp() * 1000)}"
    get_db().execute(
        """INSERT INTO trek_dates (id, trek_id, start_date, end_date, reporting_time,
           total_seats, available_seats) VALUES (?,?,?,?,?,?,?)""",
        (new_id, trek_id, start, end, "05:00", seats, seats))


def delete_date(date_id):
    get_db().execute("DELETE FROM trek_dates WHERE id=?", (date_id,))


# ------------------------------------------------------------------ bookings
def _booking(row):
    return dict(row) if row else None


def get_bookings(user_id=None):
    sql, args = "SELECT * FROM bookings", []
    if user_id:
        sql += " WHERE user_id=?"
        args.append(user_id)
    sql += " ORDER BY created_at DESC"
    return [_booking(r) for r in get_db().execute(sql, args)]


def get_booking(booking_id):
    return _booking(get_db().execute("SELECT * FROM bookings WHERE id=?", (booking_id,)).fetchone())


def get_participants(booking_id=None):
    if booking_id:
        rows = get_db().execute("SELECT * FROM participants WHERE booking_id=? ORDER BY rowid", (booking_id,))
    else:
        rows = get_db().execute("SELECT * FROM participants ORDER BY rowid")
    return [dict(r) for r in rows]


def create_booking(user_id, trek_id, date_id, participants, total_amount):
    """Atomic: re-checks seats inside a write transaction (prevents overbooking)."""
    db = get_db()
    qty = len(participants)
    db.execute("BEGIN IMMEDIATE")
    try:
        row = db.execute("SELECT * FROM trek_dates WHERE id=? AND trek_id=?", (date_id, trek_id)).fetchone()
        if row is None:
            db.execute("ROLLBACK")
            return {"success": False, "message": "Selected trek date not found."}
        if row["available_seats"] < qty:
            db.execute("ROLLBACK")
            return {"success": False,
                    "message": f"Overbooking prevented! Only {row['available_seats']} seats are "
                               f"available for this date, but you requested {qty}."}
        db.execute("UPDATE trek_dates SET available_seats = available_seats - ? WHERE id=?", (qty, date_id))

        booking_id = None
        for _ in range(20):
            cand = f"TAF-{date.today().year}-{random.randint(1000, 9999)}"
            if not db.execute("SELECT 1 FROM bookings WHERE id=?", (cand,)).fetchone():
                booking_id = cand
                break
        if booking_id is None:
            db.execute("ROLLBACK")
            return {"success": False, "message": "Could not allocate a booking ID. Please retry."}

        db.execute(
            "INSERT INTO bookings VALUES (?,?,?,?,?,?,?,?,?)",
            (booking_id, user_id, trek_id, date_id, qty, total_amount, "Paid", "Confirmed",
             datetime.now().isoformat(timespec="seconds")))
        cols = ["name", "gender", "contact", "whatsapp", "email", "dob", "age", "blood_group",
                "food_pref", "tshirt_size", "id_type", "id_number", "emergency_name",
                "emergency_rel", "emergency_num", "experience", "fitness", "limitations",
                "address", "city", "state", "pincode"]
        sql = (f"INSERT INTO participants (id, booking_id, {', '.join(cols)}) "
               f"VALUES ({', '.join('?' * (len(cols) + 2))})")
        for i, p in enumerate(participants):
            db.execute(sql, (f"part-{booking_id}-{i}", booking_id, *[p[c] for c in cols]))
        db.execute("COMMIT")
        return {"success": True, "booking_id": booking_id}
    except Exception:
        db.execute("ROLLBACK")
        raise


def cancel_booking(booking_id):
    db = get_db()
    db.execute("BEGIN IMMEDIATE")
    try:
        b = db.execute("SELECT * FROM bookings WHERE id=?", (booking_id,)).fetchone()
        if b is None:
            db.execute("ROLLBACK")
            return {"success": False, "message": "Booking not found."}
        if b["booking_status"] == "Cancelled":
            db.execute("ROLLBACK")
            return {"success": False, "message": "Booking is already cancelled."}
        db.execute("UPDATE bookings SET booking_status='Cancelled', payment_status='Refunded' WHERE id=?",
                   (booking_id,))
        db.execute(
            """UPDATE trek_dates SET available_seats = MIN(total_seats, available_seats + ?)
               WHERE id=?""", (b["num_participants"], b["date_id"]))
        db.execute("COMMIT")
        return {"success": True, "message": "Booking cancelled successfully, seats restored."}
    except Exception:
        db.execute("ROLLBACK")
        raise


# --------------------------------------------------------------------- admin
def admin_stats():
    db = get_db()
    confirmed = [dict(r) for r in db.execute("SELECT * FROM bookings WHERE booking_status='Confirmed'")]
    per_trek = {}
    for b in confirmed:
        per_trek[b["trek_id"]] = per_trek.get(b["trek_id"], 0) + b["num_participants"]
    popular = "N/A"
    if per_trek:
        best = max(per_trek, key=per_trek.get)
        trek = get_trek(best)
        if trek:
            popular = trek["name"]
    upcoming = get_dates(upcoming_only=True)
    return {
        "total_bookings": len(confirmed),
        "total_revenue": sum(b["total_amount"] for b in confirmed),
        "total_participants": sum(b["num_participants"] for b in confirmed),
        "popular_trek": popular,
        "upcoming_sessions": len(upcoming),
        "available_seats": sum(d["available_seats"] for d in upcoming),
    }


def search_bookings(q="", trek_id=""):
    bookings = get_bookings()
    parts = get_participants()
    q = q.strip().lower()
    out = []
    for b in bookings:
        if trek_id and b["trek_id"] != trek_id:
            continue
        mine = [p for p in parts if p["booking_id"] == b["id"]]
        if q and not (q in b["id"].lower() or any(q in (p["name"] or "").lower() for p in mine)):
            continue
        out.append((b, mine))
    return out


def _safe(v):
    """Neutralise spreadsheet formula injection (=, +, -, @ at the start of a cell)."""
    s = "" if v is None else str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


def export_bookings_csv():
    bookings = {b["id"]: b for b in get_bookings()}
    treks = {t["id"]: t for t in get_treks()}
    dates = {d["id"]: d for d in get_dates()}
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Booking ID", "Trek", "Date", "Price", "Participant Name", "Gender", "Age",
                "Contact", "Whatsapp", "Email", "Emergency Contact", "Emergency Number",
                "Food Preference", "T-Shirt Size", "Blood Group", "ID Type", "ID Number",
                "Payment Status", "Booking Status"])
    for p in get_participants():
        b = bookings.get(p["booking_id"], {})
        t = treks.get(b.get("trek_id"), {})
        d = dates.get(b.get("date_id"))
        row = [
            p["booking_id"], t.get("name", "Unknown Trek"),
            f"{d['start_date']} to {d['end_date']}" if d else "Unknown Date",
            t.get("price", 0), p["name"], p["gender"], p["age"], p["contact"], p["whatsapp"],
            p["email"], f"{p['emergency_name']} ({p['emergency_rel']})", p["emergency_num"],
            p["food_pref"], p["tshirt_size"], p["blood_group"] or "N/A", p["id_type"],
            p["id_number"], b.get("payment_status", "N/A"), b.get("booking_status", "N/A")]
        w.writerow([_safe(c) for c in row])
    return buf.getvalue()
