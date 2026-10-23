import os
import sqlite3
import secrets
from datetime import datetime, date
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, session, abort
from cohorts import COHORTS

app = Flask(__name__,template_folder='templates',static_folder='static')
app.secret_key = os.environ.get("SECRET_KEY")
if not app.secret_key:
    raise RuntimeError("Set the SECRET_KEY environment variable in Render.")

DB_PATH = os.environ.get(
    "DATABASE_PATH",
    os.path.join(os.path.dirname(__file__), "classrooms.db")
)

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")
if not ADMIN_PASSWORD:
    raise RuntimeError("Set the ADMIN_PASSWORD environment variable in Render.")

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
                block TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1
            )
        """)
        # Migrate existing databases safely: add an active flag without deleting
        # old room rows, so historical bookings remain linked to their room records.
        room_columns = {row[1] for row in db.execute("PRAGMA table_info(rooms)").fetchall()}
        if "active" not in room_columns:
            db.execute("ALTER TABLE rooms ADD COLUMN active INTEGER NOT NULL DEFAULT 1")
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
        db.execute("""
            CREATE TABLE IF NOT EXISTS user_queries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender_name TEXT NOT NULL,
                registration_number TEXT NOT NULL DEFAULT '',
                contact_email TEXT NOT NULL DEFAULT '',
                subject TEXT NOT NULL,
                message TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'New',
                created_at TEXT NOT NULL
            )
        """)
        # Current selectable classroom list:
        # Blocks A and B exclude rooms 01, 03 and 05; Block C remains unchanged.
        desired_rooms = []
        for block in ("A", "B"):
            for i in range(1, 16):
                if i not in (1, 3, 5):
                    desired_rooms.append((f"{block}{i:02d}", block))
        for i in range(1, 11):
            desired_rooms.append((f"C{i:02d}", "C"))

        # Additional venues supplied by the user.
        extra_venues = ["UC1", "UC2", "UC3", "CL", "L47", "L57", "L48", "L59", "H27", "H37", "H48", "WS"]
        desired_rooms.extend((name, "Venues") for name in extra_venues)

        desired_names = {name for name, _ in desired_rooms}
        removed_names = ["A01", "A03", "A05", "B01", "B03", "B05"]
        # Keep historical room rows for any old bookings, but hide removed rooms
        # from availability and prevent new bookings against them.
        db.executemany("UPDATE rooms SET active=0 WHERE name=?", [(name,) for name in removed_names])
        for name, block in desired_rooms:
            db.execute(
                "INSERT INTO rooms(name, block, active) VALUES (?, ?, 1) "
                "ON CONFLICT(name) DO UPDATE SET block=excluded.block, active=1",
                (name, block),
            )

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
        rooms = db.execute("SELECT * FROM rooms WHERE active=1 ORDER BY CASE block WHEN 'A' THEN 1 WHEN 'B' THEN 2 WHEN 'C' THEN 3 ELSE 4 END, name").fetchall()
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
                           booked_room_ids=booked_room_ids, cohorts=COHORTS)

@app.route("/book", methods=["POST"])
def book():
    registration = request.form.get("registration_number", "").strip().upper()
    year = request.form.get("year_of_study", "").strip()
    cohort_code = request.form.get("programme", "").strip().upper()
    programme_name = COHORTS.get(cohort_code, "")
    programme = f"{cohort_code} — {programme_name}" if programme_name else ""
    module = request.form.get("module_code", "").strip().upper()
    room_name = request.form.get("room_name", "").strip().upper()
    booking_date = request.form.get("booking_date", "").strip()
    start = request.form.get("start_time", "").strip()
    end = request.form.get("end_time", "").strip()

    if not cohort_code or cohort_code not in COHORTS:
        flash("Please select a valid MUST cohort from the dropdown.", "error")
        return redirect(url_for("index", date=booking_date or date.today().isoformat()))

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
            room = db.execute("SELECT * FROM rooms WHERE name=? AND active=1", (room_name,)).fetchone()
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

@app.route("/query", methods=["POST"])
def send_query():
    sender_name = request.form.get("sender_name", "").strip()[:100]
    registration = request.form.get("registration_number", "").strip().upper()[:60]
    contact_email = request.form.get("contact_email", "").strip()[:254]
    subject = request.form.get("subject", "").strip()[:150]
    message = request.form.get("message", "").strip()[:5000]

    if not all([sender_name, subject, message]):
        flash("Please provide your name, subject and message.", "error")
        return redirect(url_for("index") + "#contact-admin")
    if contact_email and ("@" not in contact_email or " " in contact_email):
        flash("Please enter a valid email address or leave it blank.", "error")
        return redirect(url_for("index") + "#contact-admin")

    try:
        with get_db() as db:
            db.execute(
                "INSERT INTO user_queries "
                "(sender_name, registration_number, contact_email, subject, message, status, created_at) "
                "VALUES (?, ?, ?, ?, ?, 'New', ?)",
                (sender_name, registration, contact_email, subject, message,
                 datetime.now().isoformat(timespec="seconds"))
            )
        flash("Your message has been sent to the administrator. Please check back or provide an email address for follow-up.", "success")
    except sqlite3.Error:
        flash("Your message could not be saved. Please try again later.", "error")
    return redirect(url_for("index") + "#contact-admin")


@app.route("/admin/queries")
@admin_required
def admin_queries():
    with get_db() as db:
        queries = db.execute(
            "SELECT * FROM user_queries ORDER BY CASE status WHEN 'New' THEN 0 WHEN 'In progress' THEN 1 ELSE 2 END, created_at DESC"
        ).fetchall()
        new_count = db.execute("SELECT COUNT(*) FROM user_queries WHERE status='New'").fetchone()[0]
    return render_template("admin_queries.html", queries=queries, new_count=new_count)


@app.route("/admin/queries/<int:query_id>/status", methods=["POST"])
@admin_required
def update_query_status(query_id):
    status = request.form.get("status", "").strip()
    if status not in {"New", "In progress", "Resolved"}:
        abort(400)
    with get_db() as db:
        result = db.execute("UPDATE user_queries SET status=? WHERE id=?", (status, query_id))
        if result.rowcount == 0:
            abort(404)
    flash("Message status updated.", "success")
    return redirect(url_for("admin_queries"))


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
