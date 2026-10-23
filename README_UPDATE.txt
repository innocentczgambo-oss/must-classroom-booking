MUST Classroom Booking System — classroom list update

Files to replace in your existing project:
- app.py
- requirements.txt
- templates/index.html

Keep cohorts.py in the same folder as app.py. Keep all your other existing files,
including templates/base.html, templates/admin.html, templates/admin_login.html,
templates/confirmation.html, static/, and your database file.

Changes:
- Removes A01, A03, A05, B01, B03, B05 from the selectable room list.
- Keeps the remaining A and B rooms and all C01-C10 rooms.
- Adds UC1, UC2, UC3, CL, L47, L57, L48, L59, H27, H37, H48, WS.
- Migrates an active flag into an existing SQLite database without deleting old room
  records, preserving historic bookings while preventing new bookings for removed rooms.
- Corrects gunicorn spelling in requirements.txt.

Safe update steps:
1. Back up the entire existing project folder and classrooms.db.
2. Replace only the three files listed above.
3. Keep cohorts.py alongside app.py and keep the existing templates/static folders.
4. Test locally, then commit the three changed files to GitHub and redeploy Render.

The database migration adds a column to rooms and marks the six removed rooms inactive;
it does not delete existing bookings. Ensure Render's SECRET_KEY and ADMIN_PASSWORD
environment variables remain configured.
