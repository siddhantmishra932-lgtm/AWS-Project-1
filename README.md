# Treks, Adventure and Fun (TAF) - Python / Flask version

The original HTML/CSS/JS single-page app, rebuilt as a server-rendered **Flask + SQLite** app.
`style.css` is reused unchanged, so the look is the same.

## Run it

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py                      # http://127.0.0.1:5000
```

The SQLite file `taf.db` is created and seeded with the 9 treks / 16 dates on first run.
Delete `taf.db` to reset.

## Configuration (environment variables)

| Variable | Default | Notes |
|---|---|---|
| `TAF_SECRET_KEY` | `dev-only-change-me` | **Set this** in production (signs the session cookie) |
| `TAF_ADMIN_USER` | `admin` | |
| `TAF_ADMIN_PASSWORD` | `trekadmin2026` | **Change this** in production |
| `TAF_DATABASE` | `./taf.db` | |
| `PORT` / `FLASK_DEBUG` | `5000` / off | |

Production: `gunicorn app:app`.

## Layout

```
app.py            routes, auth, pricing, booking rules   (was app.js + logic in views.js)
db.py             SQLite schema + queries                (was storage.js / localStorage)
data/seed.json    the original DEFAULT_TREKS/DATES, extracted from storage.js
templates/        Jinja2 pages                           (was views.js / components.js / index.html)
static/css        style.css (unchanged)
static/js/main.js small UI helpers: accordions, wizard steps, coupon call
tests/smoke_test.py   end-to-end check:  python tests/smoke_test.py
```

## What changed vs. the JS version

* **Data is real now**: SQLite instead of per-browser localStorage, so bookings are shared and seat counts are global.
* **Server-side rules**: price, GST, the `TAF10` coupon, age, and seat availability are computed/validated
  on the server. Seat check + decrement + booking insert happen in one transaction (no overbooking).
* **Admin is actually protected**: `/admin*` routes require the admin session; credentials come from env vars.
* **Escaping**: Jinja autoescape removes the XSS risk from the old `innerHTML` templates.
* **CSRF tokens** on every POST; CSV export neutralises spreadsheet formula injection.
* Voucher / cancel are limited to the booking's owner (or admin).

## Fixes to bugs in the original

* Treks with `timeSlots` itineraries (Prabalgad, Harihar, Pratapgad, Sindhudurg) made the JS detail page throw
  (`day.items` was undefined). Both formats are handled now.
* All sample dates were Sep-Oct 2026, so on later dates every page said "No upcoming dates". Seed dates are
  shifted forward in whole weeks (weekday preserved) at first run.
* Stray "湖畔" in the Sandhan Day 3 title; hard-coded "2026" in dates and booking IDs.
* Seat status is derived from seats left rather than a stored field that could go stale.

## Known limitations (same as the original, worth fixing before going live)

* User login is **email only, no password** - anyone who knows an email can see its bookings.
* Payment is simulated; no gateway is integrated (card fields are never sent to the server).
* The contact form only shows a confirmation; it does not send an email.
* Editing a trek keeps its itinerary/safety rules; there is no UI to edit those (same as before).
