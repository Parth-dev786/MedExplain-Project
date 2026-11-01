"""Isolated authentication + existing-feature smoke test. Run: python smoke_test.py"""
from datetime import date, timedelta
from pathlib import Path
import tempfile, os

# Set the disposable DB path before importing app (app initializes its DB at import time).
tmp = tempfile.TemporaryDirectory(prefix="medex-smoke-")
os.environ["MEDEX_DB_PATH"] = str(Path(tmp.name) / "smoke.sqlite3")
import app
app.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)


def csrf(client, path):
    client.get(path)
    with client.session_transaction() as sess:
        return sess["csrf_token"]


def register_and_login(client, name, email):
    token = csrf(client, "/signup")
    response = client.post("/signup", data={
        "csrf_token": token, "full_name": name, "email": email,
        "phone": "", "password": "MedExplain2026", "confirm_password": "MedExplain2026"
    }, follow_redirects=True)
    assert response.status_code == 200, response.status_code
    token = csrf(client, "/login")
    response = client.post("/login", data={"csrf_token": token, "email": email,
        "password": "MedExplain2026", "remember": "on"}, follow_redirects=True)
    assert response.status_code == 200, response.status_code
    with client.session_transaction() as sess:
        return sess["csrf_token"]

# Public pages and translations remain accessible before sign-in.
client = app.app.test_client()
for path in ["/health", "/api/translations/en", "/api/translations/hi", "/api/translations/pa", "/login", "/signup", "/forgot-password"]:
    response = client.get(path)
    assert response.status_code == 200, (path, response.status_code)
    print("PASS public", path)

# Private dashboard and APIs require authentication.
assert client.get("/").status_code == 302
assert client.get("/api/history").status_code == 401
print("PASS unauthenticated access blocked")

csrf_token = register_and_login(client, "Test Patient", "patient-one@example.test")
assert client.get("/").status_code == 200
assert client.get("/profile").status_code == 200
print("PASS signup, login, dashboard and profile")
with app.db() as c:
    stored = c.execute("SELECT password_hash FROM users WHERE email=?", ("patient-one@example.test",)).fetchone()
    assert stored and stored["password_hash"] != "MedExplain2026"
print("PASS password is hashed, not stored in plain text")

for path in ["/api/history", "/api/progress", "/api/schedules", "/api/xrays", "/api/insurance", "/api/medicines?q=para"]:
    response = client.get(path)
    assert response.status_code == 200, (path, response.status_code)
    print("PASS authenticated API", path)

# CSRF protection is enforced for mutations.
assert client.post("/api/language", json={"language": "hi"}).status_code == 400
for language in ("en", "hi", "pa"):
    response = client.post("/api/language", json={"language": language}, headers={"X-CSRF-Token": csrf_token})
    assert response.status_code == 200, response.get_data(as_text=True)
    print("PASS language preference", language)

headers = {"X-CSRF-Token": csrf_token}
response = client.post("/api/translate-copy", json={"texts": ["Sample explanation"]}, headers=headers)
assert response.status_code == 200
print("PASS translation API")

# The report demo remains functional and is scoped to the signed-in account.
response = client.get("/api/demo")
assert response.status_code == 200, response.get_data(as_text=True)
assert client.get("/api/history").get_json()["reports"]
print("PASS report demo and saved medical history")

# Existing medicine schedule and QR workflows remain available.
today = date.today()
payload = {"medicine_name": "TEST ONLY - do not take", "tablets": 1, "dose_time": "08:00",
           "start_date": today.isoformat(), "end_date": (today + timedelta(days=1)).isoformat(),
           "instructions": "Automated smoke test only"}
response = client.post("/api/schedules", json=payload, headers=headers)
assert response.status_code == 200, response.get_data(as_text=True)
schedule_id = response.get_json()["id"]
response = client.post(f"/api/schedules/{schedule_id}/log", json={"status": "taken"}, headers=headers)
assert response.status_code == 200
response = client.post("/api/qr", headers=headers)
assert response.status_code == 200
qr_token = response.get_json()["token"]
assert client.get(f"/history/{qr_token}").status_code == 200
assert client.post("/api/qr/revoke", headers=headers).status_code == 200
assert client.get(f"/history/{qr_token}").status_code == 404
print("PASS medicine schedule and token-based QR create/access/revoke")

# A second account gets a different patient workspace and cannot see account one's schedules.
second = app.app.test_client()
register_and_login(second, "Second Patient", "patient-two@example.test")
other = second.get("/api/schedules").get_json()
assert not other["schedules"], other
print("PASS account data isolation")

# Profile edits are authenticated and CSRF protected.
response = client.post("/profile", data={"csrf_token": csrf_token, "full_name": "Test Patient Updated", "phone": "1234567890"}, follow_redirects=True)
assert response.status_code == 200
assert b"Test Patient Updated" in response.data
print("PASS profile update")

# Logout invalidates access.
with client.session_transaction() as sess:
    logout_csrf = sess["csrf_token"]
assert client.post("/logout", data={"csrf_token": logout_csrf}).status_code == 302
assert client.get("/").status_code == 302
print("PASS logout and session protection")

tmp.cleanup()
print("ALL SMOKE TESTS PASSED")
