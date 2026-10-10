# MUST Examination Classroom Booking System (Version 2)

## Included
- 40 rooms: A01-A15, B01-B15, C01-C10
- Classroom availability by date and optional time window
- Booking form: registration number, year, programme, module abbreviation, room, date and times
- Server-side validation and overlap detection
- SQLite database that persists bookings
- Admin login and cancellation dashboard

## Run on Windows in Visual Studio Code

1. Install Python 3.10 or newer.
2. Extract this ZIP file and open the `must_classroom_booking` folder in VS Code.
3. Open Terminal > New Terminal.
4. Create a virtual environment:
   ```powershell
   py -m venv .venv
   .venv\Scripts\Activate.ps1
   ```
   If PowerShell blocks activation, use Command Prompt terminal and run:
   ```bat
   .venv\Scripts\activate.bat
   ```
5. Install Flask:
   ```powershell
   python -m pip install -r requirements.txt
   ```
6. Set an admin password for this terminal session (choose your own password):
   ```powershell
   $env:ADMIN_PASSWORD = "choose-a-strong-password"
   $env:SECRET_KEY = "replace-with-a-long-random-secret"
   ```
7. Start the website:
   ```powershell
   python app.py
   ```
8. Open the local address shown in the terminal, normally http://127.0.0.1:5000

## Admin
Open `/admin/login` and use the password you set in `ADMIN_PASSWORD`.
Do not deploy using the default password. Use HTTPS and a production WSGI server for public deployment.

## Before real use at MUST
- This is a starter implementation, not an officially approved MUST system.
- It starts with an empty booking database. It does NOT know about bookings already made in official exam timetables. An authorized person must enter/import those bookings before the availability display can be trusted.
- The admin password is a simple shared password for this rapid prototype; add individual staff accounts and stronger access controls before institutional deployment.
- Back up `classrooms.db` regularly.
- For public use by multiple representatives, deploy to a reliable host so everyone connects to the same database. Running this on a laptop only makes it accessible on that laptop unless networking is deliberately configured.
- Confirm official room labels; these defaults use A01-A15, B01-B15 and C01-C10.
