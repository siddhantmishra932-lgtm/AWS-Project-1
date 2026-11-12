"""Treks, Adventure and Fun (TAF) - Flask version of the Maharashtra trekking booking site."""
import hmac
import math
import os
import secrets
from datetime import date, datetime
from functools import wraps
from pathlib import Path

from flask import (Flask, Response, abort, flash, jsonify, redirect, render_template,
                   request, session, url_for)

import db

BASE_DIR = Path(__file__).resolve().parent

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("TAF_SECRET_KEY", "dev-only-change-me"),
    DATABASE=os.environ.get("TAF_DATABASE", str(BASE_DIR / "taf.db")),
    ADMIN_USER=os.environ.get("TAF_ADMIN_USER", "admin"),
    ADMIN_PASSWORD=os.environ.get("TAF_ADMIN_PASSWORD", "trekadmin2026"),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)
db.init_db(app)

COUPONS = {"TAF10": 0.10}
GST_RATE = 0.05
MAX_QTY = 10
PARTICIPANT_FIELDS = [
    "name", "gender", "contact", "whatsapp", "email", "dob", "blood_group", "food_pref",
    "tshirt_size", "id_type", "id_number", "emergency_name", "emergency_rel", "emergency_num",
    "experience", "fitness", "limitations", "address", "city", "state", "pincode",
]
OPTIONAL_FIELDS = {"limitations", "experience", "fitness"}


# ----------------------------------------------------------------- helpers
def rnd(x):
    """JS-style Math.round (half up) so totals match the original site."""
    return int(math.floor(x + 0.5))


def price_breakdown(unit_price, qty, coupon=""):
    base = unit_price * qty
    discount = 0
    code = (coupon or "").strip().upper()
    if code in COUPONS:
        discount = rnd(base * COUPONS[code])
    tax = rnd((base - discount) * GST_RATE)
    return {"base": base, "discount": discount, "tax": tax,
            "total": base - discount + tax, "coupon": code if discount else ""}


def calc_age(dob_str):
    born = date.fromisoformat(dob_str)
    today = date.today()
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def current_user():
    return session.get("user")


def is_admin():
    return bool(session.get("is_admin"))


def admin_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if not is_admin():
            flash("Please sign in as admin.", "error")
            return redirect(url_for("admin"))
        return fn(*a, **kw)
    return wrapper


def parse_int(value, default, lo=None, hi=None):
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    if lo is not None:
        n = max(lo, n)
    if hi is not None:
        n = min(hi, n)
    return n


# -------------------------------------------------------------------- CSRF
@app.before_request
def csrf_protect():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_urlsafe(32)
    if request.method == "POST":
        sent = request.form.get("_csrf") or request.headers.get("X-CSRF-Token", "")
        if not hmac.compare_digest(sent, session["_csrf"]):
            abort(400, "Invalid or missing CSRF token.")


# ---------------------------------------------------- template environment
@app.context_processor
def inject_globals():
    return {"session_user": current_user(), "session_admin": is_admin(),
            "csrf_token": session.get("_csrf", ""), "today": date.today().isoformat(),
            "current_year": date.today().year}


def _d(s):
    return date.fromisoformat(s)


@app.template_filter("short_date")
def short_date(s):
    d = _d(s)
    return f"{d.strftime('%b')} {d.day}"


@app.template_filter("long_date")
def long_date(s):
    d = _d(s)
    return f"{d.strftime('%b')} {d.day}, {d.year}"


@app.template_filter("full_date")
def full_date(s):
    d = _d(s)
    return f"{d.strftime('%A, %b')} {d.day}, {d.year}"


@app.template_filter("date_range")
def date_range(d):
    if d["start_date"] == d["end_date"]:
        return short_date(d["start_date"])
    return f"{short_date(d['start_date'])} - {short_date(d['end_date'])}"


@app.template_filter("inr")
def inr(n):
    """Indian digit grouping, e.g. 1234567 -> 12,34,567"""
    s = str(int(n))
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ",".join(parts + [tail])


@app.template_filter("mask_id")
def mask_id(s):
    s = s or ""
    return "*" * max(0, len(s) - 4) + s[-4:]


def next_dates_by_trek():
    out = {}
    for d in db.get_dates(upcoming_only=True):
        out.setdefault(d["trek_id"], []).append(d)
    return out


# ------------------------------------------------------------------ public
@app.route("/")
def home():
    treks = db.get_treks()
    upcoming = next_dates_by_trek()
    trek_map = {t["id"]: t for t in treks}
    calendar = [(d, trek_map[d["trek_id"]]) for d in db.get_dates(upcoming_only=True)
                if d["trek_id"] in trek_map][:16]
    return render_template("home.html", featured=treks[:3], upcoming=upcoming, calendar=calendar)


@app.route("/treks")
def treks():
    q = request.args.get("search", "").strip()
    diff = request.args.get("diff", "").strip()
    price = parse_int(request.args.get("price"), 2500)
    sort = request.args.get("sort", "date")
    upcoming = next_dates_by_trek()

    term = q.lower()
    result = []
    for t in db.get_treks():
        hay = [t["name"], t["location"], t["district"], t["difficulty"], t["description"]]
        if term and not any(term in h.lower() for h in hay):
            continue
        if diff and t["difficulty"].lower() != diff.lower():
            continue
        if t["price"] > price:
            continue
        result.append(t)

    if sort == "price-asc":
        result.sort(key=lambda t: t["price"])
    elif sort == "price-desc":
        result.sort(key=lambda t: -t["price"])
    elif sort == "popularity":
        result.sort(key=lambda t: -t["elevation"])
    else:
        result.sort(key=lambda t: upcoming[t["id"]][0]["start_date"] if t["id"] in upcoming else "9999-12-31")

    return render_template("treks.html", treks=result, upcoming=upcoming,
                           q=q, diff=diff, price=price, sort=sort)


@app.route("/trek/<trek_id>")
def trek_detail(trek_id):
    trek = db.get_trek(trek_id)
    if not trek:
        return render_template("not_found.html", title="Trek Not Found", back="treks",
                               back_label="Back to All Treks"), 404
    dates = db.get_dates(trek_id, upcoming_only=True)
    bookable = [d for d in dates if d["available_seats"] > 0]
    return render_template("trek_detail.html", trek=trek, dates=dates, active_date=bookable[0] if bookable else None)


@app.route("/about")
def about():
    return render_template("about.html", forts=COMPLETED_FORTS)


@app.route("/faqs")
def faqs():
    return render_template("faqs.html", faqs=FAQS)


@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        flash("Message sent successfully! Our trek coordinator will revert shortly.")
        return redirect(url_for("contact"))
    return render_template("contact.html")


# ----------------------------------------------------------------- booking
@app.route("/booking/<trek_id>", methods=["GET", "POST"])
def booking(trek_id):
    trek = db.get_trek(trek_id)
    date_id = request.values.get("date", "")
    qty = parse_int(request.values.get("qty"), 1, 1, MAX_QTY)
    date_obj = db.get_date(date_id)
    if not trek or not date_obj or date_obj["trek_id"] != trek_id:
        return render_template("not_found.html", title="Invalid Booking Parameters", back="treks",
                               back_label="Return to Treks"), 400

    if request.method == "GET":
        if date_obj["available_seats"] < qty:
            flash(f"Insufficient seats. Selected date only has {date_obj['available_seats']} remaining seats.", "error")
            return redirect(url_for("trek_detail", trek_id=trek_id))
        return render_template("booking.html", trek=trek, date=date_obj, qty=qty,
                               pricing=price_breakdown(trek["price"], qty))

    columns = {f: request.form.getlist(f) for f in PARTICIPANT_FIELDS}
    if any(len(v) != qty for v in columns.values()):
        flash("Participant details were incomplete. Please try again.", "error")
        return redirect(url_for("booking", trek_id=trek_id, date=date_id, qty=qty))
    if request.form.get("agree") != "on":
        flash("You must accept the trekking rules & emergency disclaimer to proceed.", "error")
        return redirect(url_for("booking", trek_id=trek_id, date=date_id, qty=qty))

    participants = []
    for i in range(qty):
        p = {f: columns[f][i].strip() for f in PARTICIPANT_FIELDS}
        missing = [f for f in PARTICIPANT_FIELDS if not p[f] and f not in OPTIONAL_FIELDS]
        if missing:
            flash(f"Participant #{i + 1}: please fill in all required fields.", "error")
            return redirect(url_for("booking", trek_id=trek_id, date=date_id, qty=qty))
        try:
            p["age"] = calc_age(p["dob"])
        except ValueError:
            flash(f"Participant #{i + 1}: invalid date of birth.", "error")
            return redirect(url_for("booking", trek_id=trek_id, date=date_id, qty=qty))
        if not 0 <= p["age"] <= 110:
            flash(f"Participant #{i + 1}: invalid date of birth.", "error")
            return redirect(url_for("booking", trek_id=trek_id, date=date_id, qty=qty))
        participants.append(p)

    pricing = price_breakdown(trek["price"], qty, request.form.get("coupon", ""))
    primary_email = participants[0]["email"]
    user_id = current_user() or primary_email

    res = db.create_booking(user_id, trek_id, date_id, participants, pricing["total"])
    if not res["success"]:
        flash(res["message"], "error")
        return redirect(url_for("trek_detail", trek_id=trek_id))

    if not current_user():
        session["user"] = primary_email
    flash("Booking Successful! Payment Processed.")
    return redirect(url_for("confirmation", booking_id=res["booking_id"]))


@app.post("/api/coupon")
def api_coupon():
    data = request.get_json(silent=True) or {}
    trek = db.get_trek(data.get("trek_id", ""))
    if not trek:
        return jsonify(ok=False, message="Unknown trek."), 404
    qty = parse_int(data.get("qty"), 1, 1, MAX_QTY)
    p = price_breakdown(trek["price"], qty, data.get("code", ""))
    if not p["coupon"]:
        return jsonify(ok=False, message="Invalid coupon code.")
    return jsonify(ok=True, message="Coupon TAF10 applied! 10% discount subtracted.", **p)


def _can_view(booking):
    return is_admin() or (current_user() and booking["user_id"] == current_user())


@app.route("/confirmation/<booking_id>")
def confirmation(booking_id):
    b = db.get_booking(booking_id)
    if not b or not _can_view(b):
        return render_template("not_found.html", title="Booking ID Not Found", back="home",
                               back_label="Back to Home"), 404
    return render_template("confirmation.html", b=b, trek=db.get_trek(b["trek_id"]),
                           date=db.get_date(b["date_id"]), attendees=db.get_participants(booking_id))


@app.route("/confirmation/<booking_id>/download")
def download_ticket(booking_id):
    b = db.get_booking(booking_id)
    if not b or not _can_view(b):
        abort(404)
    trek, d = db.get_trek(b["trek_id"]) or {}, db.get_date(b["date_id"]) or {}
    lines = [
        "TAF TREK TRAVEL PASS VOUCHER", "=" * 28,
        f"Booking ID: {b['id']}", f"Status: {b['booking_status']}",
        f"Total Amount Paid: Rs. {b['total_amount']}", f"Timestamp: {b['created_at']}", "=" * 28,
        f"Trek: {trek.get('name', '-')}", f"Date: {d.get('start_date', '-')} to {d.get('end_date', '-')}",
        f"Meeting Point: {trek.get('meeting_point', '-')}", f"Reporting Time: {trek.get('reporting_time', '-')}",
        "", "Trekkers:",
    ]
    for i, p in enumerate(db.get_participants(booking_id), 1):
        lines.append(f"  {i}. {p['name']} ({p['gender']}, Age {p['age']})")
    lines += ["", "Support: +91 8104799308", "Emergency: +91 7083019308"]
    return Response("\n".join(lines), mimetype="text/plain; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename=TAF-Ticket-{b['id']}.txt"})


# --------------------------------------------------------------- user area
@app.route("/dashboard")
def dashboard():
    user = current_user()
    if not user:
        return render_template("dashboard.html", rows=None)
    treks = {t["id"]: t for t in db.get_treks()}
    dates = {d["id"]: d for d in db.get_dates()}
    rows = []
    for b in db.get_bookings(user):
        d = dates.get(b["date_id"])
        can_cancel = b["booking_status"] == "Confirmed" and d is not None and d["start_date"] > date.today().isoformat()
        rows.append({"b": b, "trek": treks.get(b["trek_id"]), "date": d, "can_cancel": can_cancel})
    return render_template("dashboard.html", rows=rows)


@app.post("/login")
def login():
    email = request.form.get("email", "").strip()
    if not email or "@" not in email:
        flash("Please enter a valid email address.", "error")
    else:
        session["user"] = email
        flash(f"Logged in successfully as {email}.")
    return redirect(url_for("dashboard"))


@app.post("/logout")
def logout():
    session.pop("user", None)
    session.pop("is_admin", None)
    flash("Logged out successfully.")
    return redirect(url_for("home"))


@app.post("/booking/<booking_id>/cancel")
def cancel(booking_id):
    b = db.get_booking(booking_id)
    if not b or not _can_view(b):
        abort(404)
    res = db.cancel_booking(booking_id)
    flash("Booking cancelled. Seat inventory restored." if res["success"] else res["message"],
          "message" if res["success"] else "error")
    nxt = request.form.get("next")
    return redirect(url_for("admin", tab="bookings") if nxt == "admin" and is_admin() else url_for("dashboard"))


# -------------------------------------------------------------------- admin
@app.route("/admin")
def admin():
    if not is_admin():
        return render_template("admin_login.html")
    tab = request.args.get("tab", "stats")
    if tab not in ("stats", "treks", "dates", "bookings"):
        tab = "stats"
    q = request.args.get("q", "")
    trek_filter = request.args.get("trek", "")
    treks = db.get_treks()
    trek_map = {t["id"]: t for t in treks}
    edit = db.get_trek(request.args["edit"]) if request.args.get("edit") else None
    dates = db.get_dates()
    return render_template(
        "admin.html", tab=tab, stats=db.admin_stats(), treks=treks, trek_map=trek_map, dates=dates,
        date_map={d["id"]: d for d in dates}, bookings=db.search_bookings(q, trek_filter),
        q=q, trek_filter=trek_filter, edit=edit)


@app.post("/admin/login")
def admin_login():
    user_ok = hmac.compare_digest(request.form.get("username", "").strip(), app.config["ADMIN_USER"])
    pass_ok = hmac.compare_digest(request.form.get("password", "").strip(), app.config["ADMIN_PASSWORD"])
    if user_ok and pass_ok:
        session["is_admin"] = True
        session["user"] = "Admin Mode"
        flash("Access granted. Admin panel unlocked.")
    else:
        flash("Invalid credentials.", "error")
    return redirect(url_for("admin"))


def _lines(text):
    return [ln.strip() for ln in (text or "").splitlines() if ln.strip()]


@app.post("/admin/trek/save")
@admin_required
def admin_trek_save():
    f = request.form
    try:
        data = {
            "name": f["name"].strip(), "location": f["location"].strip(), "district": f["district"].strip(),
            "difficulty": f["difficulty"] if f["difficulty"] in ("Easy", "Moderate", "Difficult") else "Easy",
            "elevation": int(f["elevation"]), "distance": float(f["distance"]),
            "duration": f["duration"].strip(), "meeting_point": f["meeting_point"].strip(),
            "reporting_time": f["reporting_time"].strip(),
            "expected_return_time": f["expected_return_time"].strip(),
            "price": int(f["price"]), "image": f["image"].strip(), "description": f["description"].strip(),
            "included": _lines(f.get("included")), "excluded": _lines(f.get("excluded")),
            "things_to_carry": _lines(f.get("things_to_carry")),
        }
    except (KeyError, ValueError):
        flash("Please fill in all trek fields with valid values.", "error")
        return redirect(url_for("admin", tab="treks"))

    # Allow both full URLs and local paths under /static/
    img = data["image"]
    if not (img.lower().startswith(("http://", "https://")) or img.startswith("/static/")):
        flash("Image must be a full URL (https://...) or a local path starting with /static/", "error")
        return redirect(url_for("admin", tab="treks"))
    data["image"] = img

    trek_id = f.get("trek_id") or None
    if trek_id and not db.get_trek(trek_id):
        abort(404)
    db.save_trek(data, trek_id)
    flash("Trek profile updated successfully." if trek_id else "Trek profile created successfully.")
    return redirect(url_for("admin", tab="treks"))


@app.post("/admin/trek/<trek_id>/delete")
@admin_required
def admin_trek_delete(trek_id):
    db.delete_trek(trek_id)
    flash("Trek profile deleted.")
    return redirect(url_for("admin", tab="treks"))


@app.post("/admin/date/add")
@admin_required
def admin_date_add():
    f = request.form
    try:
        start, end = date.fromisoformat(f["start"]), date.fromisoformat(f["end"])
        seats = int(f["seats"])
    except (KeyError, ValueError):
        flash("Please enter valid dates and seat count.", "error")
        return redirect(url_for("admin", tab="dates"))
    if end < start or not 5 <= seats <= 60 or not db.get_trek(f.get("trek_id", "")):
        flash("Check the date range (end must be on/after start), seats (5-60) and trek.", "error")
        return redirect(url_for("admin", tab="dates"))
    db.add_date(f["trek_id"], start.isoformat(), end.isoformat(), seats)
    flash("Trek date scheduled successfully.")
    return redirect(url_for("admin", tab="dates"))


@app.post("/admin/date/<date_id>/delete")
@admin_required
def admin_date_delete(date_id):
    db.delete_date(date_id)
    flash("Scheduled date deleted.")
    return redirect(url_for("admin", tab="dates"))


@app.route("/admin/export.csv")
@admin_required
def admin_export():
    return Response(db.export_bookings_csv(), mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=TAF-Trekkers-Registrations.csv"})


# ------------------------------------------------------------ static content
FAQS = [
    ("What should I carry for a weekend trek in Maharashtra?",
     "You must carry trekking shoes with rubber grip, double strap backpack, at least 2-3 Litres of water, personal medication, torch (compulsory for night treks), change of clothes, raincoat (during monsoons), identity card (Aadhar Card copy), and snacks like energy bars or glucose."),
    ("Is trekking experience required for beginners?",
     "No, many treks like Devkund Waterfall or Rajmachi Flat Walk are beginner-friendly. For technical or difficult canyon descent treks like Sandhan Valley, reasonable physical endurance is expected."),
    ("What happens if there are warnings of heavy rains or landslides?",
     "Your safety is paramount. If local authorities or weather departments issue orange/red alerts, treks are rescheduled or cancelled. In case of cancellation by TAF, a full refund or future credit voucher is offered."),
    ("Are village meals and private transportation included?",
     "Yes! Most of our packages include private transport from standard assembly stations (Mumbai/Pune) to base villages, and delicious hot Maharashtrian breakfast, lunch, and dinner prepared in clean village homestays."),
    ("Can I register as a group, and how is pricing calculated?",
     "Yes. In the booking registry panel, you can select the number of seats. The system dynamically generates registration form inputs for each participant and calculates the net amount accordingly."),
    ("How do I cancel my booking and request a refund?",
     "Log in to your User Dashboard using your booking email. Select 'Cancel' next to your upcoming bookings. If cancelled 48 hours prior to start, seats are returned and refunds are processed automatically."),
    ("Are first aid and emergency support available?",
     "Absolutely. Every trek is led by certified Trek leaders carrying fully stocked first-aid equipment. We have continuous networks with local village responders and emergency coordinate help desks."),
]

_W = "https://upload.wikimedia.org/wikipedia/commons/"
COMPLETED_FORTS = [
    ("Rajgad Fort", "4,514 ft", "January 2024", _W + "8/8e/Padmavati_Machi%2C_Rajgad.jpg",
     "The historic capital of the Maratha Empire under Chatrapati Shivaji Maharaj. Explored Sanjeevani Machi and Suvela Machi. A steep climb with rich ruins."),
    ("Torna Fort", "4,603 ft", "March 2024", _W + "f/f6/Torna_Fort_Bini_Darwaza.jpg",
     "The first fort captured by Chatrapati Shivaji Maharaj. Challenging ridge walk from Rajgad. Known for its massive structures and Bini Darwaza."),
    ("Purandar Fort", "4,472 ft", "May 2024", _W + "0/0a/Purandhar_fort.jpg",
     "Birthplace of Sambhaji Maharaj. Famous for its military history, double fortification layers, and panoramic plateau vistas."),
    ("Sinhagad Fort", "4,320 ft", "August 2024", _W + "b/b3/Sinhagad_fort_Pune.jpg",
     "Site of the legendary battle led by Tanaji Malusare. A classic climb through scenic valleys, rewarded with spicy local pitla bhakri."),
    ("Kalavantin Durg", "2,250 ft", "October 2024", _W + "2/25/Kalavantin_Durg_pinnacle.jpg",
     "World-famous steep pinnacle climb. Features hand-cut steps in vertical rock faces. One of the most thrilling climbs in Maharashtra."),
    ("Sondai Fort", "1,200 ft", "November 2024", _W + "b/b8/Sondai_Hill.jpg",
     "A beautiful watchtower fort near Karjat. Beginners-friendly trek offering a scenic view of Morbe Dam reservoir from the summit."),
    ("Irshalgad Fort", "3,700 ft", "December 2024", _W + "d/de/Irshalgad_pinnacle_view.jpg",
     "Famous for its massive natural needle-eye hole (Nedhe) in the ridge rock. A steep and thrilling climb across narrow ravines."),
    ("Malangad Fort", "2,590 ft", "February 2025", _W + "3/30/Malangad.jpg",
     "A three-layered fort near Kalyan. Requires crossing a thrilling suspension bridge and scaling steep rock patches to reach the topmost peak."),
    ("Raireshwar Fort", "4,510 ft", "April 2025", _W + "3/33/Raireshwar.jpg",
     "Where Chatrapati Shivaji Maharaj took the oath of Swarajya. Known for its massive colored-soil plateau and historic temple."),
    ("Raigad Fort", "2,700 ft", "June 2025", _W + "d/db/Raigad_Fort_Maha_Darwaja.jpg",
     "The crowning capital of the Maratha Empire. Explored the bazaar, Takmak Tok cliff, and the samadhi of Chatrapati Shivaji Maharaj."),
]

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1", port=int(os.environ.get("PORT", 5000)))