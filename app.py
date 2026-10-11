import os
import sqlite3
import secrets
from datetime import datetime, date
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, session, abort

app = Flask(__name__,template_folder='templates',static_folder='static')
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-12345")
if not app.secret_key:
    raise RuntimeError("Set the SECRET_KEY environment variable.")

DB_PATH = os.environ.get(
    "DATABASE_PATH",
    os.path.join(os.path.dirname(__file__), "classrooms.db")
)

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "i to deh cent")
if not ADMIN_PASSWORD:
    raise RuntimeError("Set the ADMIN_PASSWORD environment variable.")

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 15000")
    return conn

def init_db():
    with get_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS rooms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                block TEXT NOT NULL
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reference TEXT NOT NULL UNIQUE,
                registration_number TEXT NOT NULL,
                year_of_study TEXT NOT NULL,
                programme TEXT NOT NULL,
                module_code TEXT NOT NULL,
                room_id INTEGER NOT NULL,
                booking_date TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(room_id) REFERENCES rooms(id)
            )
        """)
        count = db.execute("SELECT COUNT(*) FROM rooms").fetchone()[0]
        if count == 0:
            for block, n in [("A", 15), ("B", 15), ("C", 10)]:
                for i in range(1, n + 1):
                    db.execute("INSERT INTO rooms(name, block) VALUES (?, ?)", (f"{block}{i:02d}", block))

def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("admin_login"))
        return view(*args, **kwargs)
    return wrapped

@app.route("/")
def index():
    chosen_date = request.args.get("date") or date.today().isoformat()
    start = request.args.get("start", "")
    end = request.args.get("end", "")
    with get_db() as db:
        rooms = db.execute("SELECT * FROM rooms ORDER BY block, id").fetchall()
        bookings = db.execute("""
            SELECT b.*, r.name AS room_name, r.block
            FROM bookings b JOIN rooms r ON r.id=b.room_id
            WHERE b.booking_date=?
            ORDER BY b.start_time, r.block, r.name
        """, (chosen_date,)).fetchall()
        booked_room_ids = set()
        if start and end and start < end:
            booked_room_ids = {
                row["room_id"] for row in db.execute("""
                    SELECT DISTINCT room_id FROM bookings
                    WHERE booking_date=? AND start_time < ? AND end_time > ?
                """, (chosen_date, end, start)).fetchall()
            }
        elif not start and not end:
            # With no time filter, mark rooms with any booking on this date.
            booked_room_ids = {row["room_id"] for row in bookings}
    return render_template("index.html", rooms=rooms, bookings=bookings,
                           chosen_date=chosen_date, start=start, end=end,
                           booked_room_ids=booked_room_ids)

@app.route("/book", methods=["POST"])
def book():
    registration = request.form.get("registration_number", "").strip().upper()
    year = request.form.get("year_of_study", "").strip()
    programme = request.form.get("programme", "").strip()
    module = request.form.get("module_code", "").strip().upper()
    room_name = request.form.get("room_name", "").strip().upper()
    booking_date = request.form.get("booking_date", "").strip()
    start = request.form.get("start_time", "").strip()
    end = request.form.get("end_time", "").strip()

    if not all([registration, year, programme, module, room_name, booking_date, start, end]):
        flash("Please complete every field.", "error")
        return redirect(url_for("index", date=booking_date or date.today().isoformat()))
    try:
        datetime.strptime(booking_date, "%Y-%m-%d")
        datetime.strptime(start, "%H:%M")
        datetime.strptime(end, "%H:%M")
    except ValueError:
        flash("Please enter a valid date and time.", "error")
        return redirect(url_for("index", date=booking_date))
    if start >= end:
        flash("End time must be later than start time.", "error")
        return redirect(url_for("index", date=booking_date))

    try:
        with get_db() as db:
            room = db.execute("SELECT * FROM rooms WHERE name=?", (room_name,)).fetchone()
            if not room:
                flash("That classroom does not exist. Please choose one from the list.", "error")
                return redirect(url_for("index", date=booking_date))
            # BEGIN IMMEDIATE serializes booking writes, preventing two simultaneous
            # requests from both passing the availability check.
            db.execute("BEGIN IMMEDIATE")
            conflict = db.execute("""
                SELECT reference, start_time, end_time FROM bookings
                WHERE room_id=? AND booking_date=? AND start_time < ? AND end_time > ?
                LIMIT 1
            """, (room["id"], booking_date, end, start)).fetchone()
            if conflict:
                db.rollback()
                flash(f"{room_name} is already booked from {conflict['start_time']} to {conflict['end_time']} for that date. Please choose another room or time.", "error")
                return redirect(url_for("index", date=booking_date, start=start, end=end))
            reference = "MUST-" + secrets.token_hex(4).upper()
            db.execute("""
                INSERT INTO bookings
                (reference, registration_number, year_of_study, programme, module_code,
                 room_id, booking_date, start_time, end_time, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (reference, registration, year, programme, module, room["id"],
                  booking_date, start, end, datetime.now().isoformat(timespec="seconds")))
            db.commit()
        return render_template("confirmation.html", reference=reference, room_name=room_name,
                               booking_date=booking_date, start=start, end=end,
                               module=module, registration=registration)
    except sqlite3.Error:
        flash("The booking could not be saved due to a database error. Please try again.", "error")
        return redirect(url_for("index", date=booking_date))

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if secrets.compare_digest(request.form.get("password", ""), ADMIN_PASSWORD):
            session["is_admin"] = True
            return redirect(url_for("admin"))
        flash("Incorrect admin password.", "error")
    return render_template("admin_login.html")

@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("index"))

@app.route("/admin")
@admin_required
def admin():
    with get_db() as db:
        bookings = db.execute("""
            SELECT b.*, r.name AS room_name, r.block
            FROM bookings b JOIN rooms r ON r.id=b.room_id
            ORDER BY b.booking_date DESC, b.start_time
        """).fetchall()
    return render_template("admin.html", bookings=bookings)

@app.route("/admin/cancel/<int:booking_id>", methods=["POST"])
@admin_required
def cancel_booking(booking_id):
    with get_db() as db:
        db.execute("DELETE FROM bookings WHERE id=?", (booking_id,))
    flash("Booking cancelled.", "success")
    return redirect(url_for("admin"))

init_db()


if __name__ == "__main__":
    # Local development only. For public deployment, use a production WSGI server.
    app.run(debug=True)
