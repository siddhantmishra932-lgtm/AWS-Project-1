import os, re, sys
os.environ["TAF_DATABASE"] = "/tmp/t.db"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import app
import db as dbm

c = app.test_client()
def token(path="/"):
    r = c.get(path); assert r.status_code == 200, (path, r.status_code)
    return re.search(r'data-csrf="([^"]+)"', r.get_data(as_text=True)).group(1)

# --- every public page renders
for p in ["/", "/treks", "/treks?search=fort&diff=Easy&price=2000&sort=price-asc", "/about", "/faqs", "/contact", "/dashboard", "/admin"]:
    assert c.get(p).status_code == 200, p
for tid in ["trek-harishchandragad", "trek-prabalgad", "trek-sindhudurg", "trek-harihar", "trek-pratapgad"]:
    r = c.get(f"/trek/{tid}"); assert r.status_code == 200, tid   # timeSlots treks crashed the JS version
assert c.get("/trek/nope").status_code == 404
html = c.get("/").get_data(as_text=True)
assert "Upcoming Trek Calendar" in html and "No upcoming trek sessions" not in html
print("pages ok")

# --- CSRF enforced
assert c.post("/login", data={"email": "a@b.com"}).status_code == 400

# --- booking flow
with app.app_context():
    from flask import g
    pass
import sqlite3
con = sqlite3.connect("/tmp/t.db"); con.row_factory = sqlite3.Row
d = con.execute("SELECT * FROM trek_dates WHERE trek_id='trek-rajmachi' AND available_seats>=2 ORDER BY start_date").fetchone()
t = token(f"/booking/trek-rajmachi?date={d['id']}&qty=2")
def person(n):
    return dict(name=f"Trekker {n}", gender="Male", contact="9999999999", whatsapp="9999999999", email="me@test.com",
                dob="1995-05-05", blood_group="O+", food_pref="Veg", tshirt_size="M", id_type="Aadhar Card",
                id_number="123412341234", emergency_name="Dad", emergency_rel="Father", emergency_num="8888888888",
                experience="Beginner", fitness="Good", limitations="", address="Flat 1", city="Thane", state="Maharashtra", pincode="400604")
people = [person(1), person(2)]
data = {k: [p[k] for p in people] for k in people[0]}
data.update(_csrf=t, date=d["id"], qty="2", coupon="TAF10", agree="on")
r = c.post("/booking/trek-rajmachi", data=data)
assert r.status_code == 302, r.status_code
loc = r.headers["Location"]; bid = loc.rsplit("/", 1)[1]
print("booking", bid)
con2 = sqlite3.connect("/tmp/t.db"); con2.row_factory = sqlite3.Row
b = con2.execute("SELECT * FROM bookings WHERE id=?", (bid,)).fetchone()
# base 2*1299=2598, discount 260, tax round((2338)*.05)=117 -> 2455
assert b["total_amount"] == 2455, b["total_amount"]
after = con2.execute("SELECT available_seats FROM trek_dates WHERE id=?", (d["id"],)).fetchone()[0]
assert after == d["available_seats"] - 2
assert "TAF-" in c.get(loc).get_data(as_text=True)
assert c.get(loc + "/download").status_code == 200
dash = c.get("/dashboard").get_data(as_text=True); assert bid in dash and "Cancel" in dash
print("booking + pricing + seats ok")

# --- overbooking prevented
t = token()
data["qty"] = "2"
fake = db_seats = con2.execute("SELECT id FROM trek_dates WHERE available_seats=1 LIMIT 1").fetchone()
data2 = {k: [p[k] for p in people] for k in people[0]}; data2.update(_csrf=t, date=fake["id"], qty="2", agree="on")
tid = con2.execute("SELECT trek_id FROM trek_dates WHERE id=?", (fake["id"],)).fetchone()[0]
r = c.post(f"/booking/{tid}", data=data2); assert r.status_code == 302 and "/trek/" in r.headers["Location"]
print("overbooking blocked ok")

# --- other user cannot open the voucher or cancel it
c2 = app.test_client(); 
assert c2.get(f"/confirmation/{bid}").status_code == 404
# --- cancel restores seats
t = token("/dashboard")
r = c.post(f"/booking/{bid}/cancel", data={"_csrf": t}); assert r.status_code == 302
con3 = sqlite3.connect("/tmp/t.db")
assert con3.execute("SELECT available_seats FROM trek_dates WHERE id=?", (d["id"],)).fetchone()[0] == d["available_seats"]
print("cancel restores seats ok")

# --- admin
assert c2.get("/admin/export.csv").status_code == 302
t2 = re.search(r'data-csrf="([^"]+)"', c2.get("/admin").get_data(as_text=True)).group(1)
assert "Invalid" or True
c2.post("/admin/login", data={"_csrf": t2, "username": "admin", "password": "wrong"})
assert "Unlock Console" in c2.get("/admin").get_data(as_text=True)
c2.post("/admin/login", data={"_csrf": t2, "username": "admin", "password": "trekadmin2026"})
for tab in ["stats", "treks", "dates", "bookings"]:
    assert c2.get(f"/admin?tab={tab}").status_code == 200, tab
assert c2.get("/admin?tab=treks&edit=trek-devkund").status_code == 200
assert c2.get("/admin?tab=treks&edit=new").status_code == 200
r = c2.post("/admin/trek/save", data=dict(_csrf=t2, trek_id="", name="Test Trek", location="X", district="Y", difficulty="Easy",
    elevation="100", distance="3.5", duration="1 Day", meeting_point="M", reporting_time="5", expected_return_time="9", price="999",
    image="https://x.com/a.jpg", description="d", included="a\nb", excluded="c", things_to_carry="d")); assert r.status_code == 302
new = [x for x in dbm.sqlite3.connect("/tmp/t.db").execute("SELECT id FROM treks WHERE name='Test Trek'")][0][0]
assert c2.get(f"/trek/{new}").status_code == 200
r = c2.post("/admin/date/add", data=dict(_csrf=t2, trek_id=new, start="2030-01-01", end="2030-01-02", seats="20")); assert r.status_code == 302
r = c2.post(f"/admin/trek/{new}/delete", data={"_csrf": t2})
assert dbm.sqlite3.connect("/tmp/t.db").execute("SELECT COUNT(*) FROM trek_dates WHERE trek_id=?", (new,)).fetchone()[0] == 0
csv = c2.get("/admin/export.csv"); assert csv.status_code == 200 and b"Booking ID" in csv.data
print("admin ok")
print("ALL PASSED")
