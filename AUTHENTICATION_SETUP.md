# MedExplain 3.2 — Account authentication setup

## First run

1. Extract the project folder and open `health_report_interpreter` in VS Code.
2. Run `python -m pip install -r requirements.txt`.
3. Set a unique Flask secret before starting the app:

```powershell
$env:FLASK_SECRET_KEY = [Convert]::ToBase64String([Security.Cryptography.RandomNumberGenerator]::GetBytes(48))
python app.py
```

4. Open `http://127.0.0.1:5000/signup`, create an account, and then sign in.

The SQLite schema is migrated safely at startup: `users` and `password_reset_tokens` tables are added, and a nullable `patients.user_id` column is added to an older database when needed. Existing patient/report/schedule/QR rows are not deleted. If a browser already has an anonymous `patient_id` session from an earlier version, signup attaches that unclaimed patient workspace to the new account.

## Authentication and privacy

- Passwords use Werkzeug's password hashing helpers. Plain-text passwords are never stored.
- Dashboard pages and private `/api/*` endpoints require a signed-in account.
- Reports, prescriptions, medicine schedules/logs, X-ray uploads and QR tokens continue to be scoped through the account's patient workspace.
- The existing public QR share remains available only through its random, token-based `/history/<token>` link and can be revoked by the signed-in owner.
- POST/PUT/PATCH/DELETE requests require a CSRF token. The dashboard's fetch wrapper sends the token automatically; HTML forms include a hidden token.
- `Remember me` enables a 14-day permanent session. Without it, the session cookie is a browser-session cookie.
- `/profile` allows name/phone edits and password changes.

## Password reset email

Password reset links are sent only when SMTP settings are configured. Set these environment variables before launching Flask:

```powershell
$env:SMTP_HOST = "smtp.example.com"
$env:SMTP_PORT = "587"
$env:SMTP_SSL = "0"
$env:SMTP_USER = "your-smtp-user"
$env:SMTP_PASSWORD = "your-smtp-app-password"
$env:MAIL_FROM = "MedExplain <no-reply@example.com>"
```

Use an email provider's app password or SMTP credential; do not hard-code credentials in source files. Reset links expire after 30 minutes and are stored as SHA-256 token hashes. If SMTP is not configured, the app returns a generic response but cannot deliver a reset link.

## Deployment security

- Use a long random `FLASK_SECRET_KEY` and keep it private.
- Run behind HTTPS and set `$env:COOKIE_SECURE = "1"` only when HTTPS is active.
- Keep `FLASK_DEBUG=0` in deployment.
- Use a production WSGI server; Flask's development server is for local testing only.
- Configure rate limiting and verified email delivery before public internet deployment.

## Tests

After installing the requirements, run:

```powershell
python -m py_compile app.py report_engine.py smoke_test.py
python smoke_test.py
```

The smoke test uses a temporary SQLite database and checks signup/login, private-route protection, CSRF, language preferences, medicine schedules, QR sharing/revocation, account isolation and logout. It does not modify the app's real `instance/medexplain.sqlite3` database.
