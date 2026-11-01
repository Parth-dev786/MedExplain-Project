from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_file
from werkzeug.utils import secure_filename
from pathlib import Path
import uuid, sqlite3, json, secrets, io, os, re, urllib.request, urllib.error
from functools import lru_cache
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse
from email.message import EmailMessage
import smtplib, hashlib, hmac
from report_engine import extract_document, extract_prescription_text, analyze_report

BASE_DIR = Path(__file__).resolve().parent
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "development-only-change-this-secret")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "0") == "1",
    PERMANENT_SESSION_LIFETIME=timedelta(days=14),
)
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024
app.config["UPLOAD_FOLDER"] = BASE_DIR / "uploads"
app.config["UPLOAD_FOLDER"].mkdir(exist_ok=True)
DB_PATH = Path(os.environ.get("MEDEX_DB_PATH", str(BASE_DIR / "instance" / "medexplain.sqlite3"))).resolve()
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
ALLOWED = {".pdf", ".png", ".jpg", ".jpeg", ".webp"}

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          full_name TEXT NOT NULL,
          email TEXT NOT NULL COLLATE NOCASE UNIQUE,
          phone TEXT NOT NULL DEFAULT '',
          password_hash TEXT NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
          token_hash TEXT PRIMARY KEY,
          user_id INTEGER NOT NULL,
          expires_at TEXT NOT NULL,
          used INTEGER NOT NULL DEFAULT 0,
          FOREIGN KEY(user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS patients (
          id TEXT PRIMARY KEY, created_at TEXT NOT NULL, preferred_language TEXT NOT NULL DEFAULT 'en',
          user_id INTEGER UNIQUE REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS reports (
          id TEXT PRIMARY KEY, patient_id TEXT NOT NULL, filename TEXT NOT NULL,
          created_at TEXT NOT NULL, summary_json TEXT NOT NULL, results_json TEXT NOT NULL,
          FOREIGN KEY(patient_id) REFERENCES patients(id)
        );
        CREATE INDEX IF NOT EXISTS idx_reports_patient ON reports(patient_id, created_at DESC);
        CREATE TABLE IF NOT EXISTS qr_tokens (
          token_hash TEXT PRIMARY KEY, patient_id TEXT NOT NULL, created_at TEXT NOT NULL,
          revoked INTEGER NOT NULL DEFAULT 0, FOREIGN KEY(patient_id) REFERENCES patients(id)
        );
        
        CREATE TABLE IF NOT EXISTS insurance_plans (
          id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, provider TEXT NOT NULL,
          coverage TEXT NOT NULL, notes TEXT NOT NULL, is_demo INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS medicine_information (
          id INTEGER PRIMARY KEY AUTOINCREMENT, generic_name TEXT NOT NULL UNIQUE,
          purpose TEXT NOT NULL, cautions TEXT NOT NULL, category TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS prescriptions (
          id TEXT PRIMARY KEY, patient_id TEXT NOT NULL, filename TEXT NOT NULL,
          extracted_text TEXT NOT NULL, confirmed INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS medicine_schedules (
          id TEXT PRIMARY KEY, patient_id TEXT NOT NULL, prescription_id TEXT,
          medicine_name TEXT NOT NULL, strength TEXT NOT NULL DEFAULT '',
          tablets REAL NOT NULL, dose_unit TEXT NOT NULL DEFAULT 'tablet',
          dose_time TEXT NOT NULL, start_date TEXT NOT NULL, end_date TEXT NOT NULL,
          instructions TEXT NOT NULL DEFAULT '', active INTEGER NOT NULL DEFAULT 1,
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS medicine_logs (
          id TEXT PRIMARY KEY, schedule_id TEXT NOT NULL, patient_id TEXT NOT NULL,
          scheduled_date TEXT NOT NULL, scheduled_time TEXT NOT NULL,
          status TEXT NOT NULL, logged_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS xray_uploads (
          id TEXT PRIMARY KEY, patient_id TEXT NOT NULL, filename TEXT NOT NULL,
          stored_filename TEXT NOT NULL, image_type TEXT NOT NULL,
          created_at TEXT NOT NULL, review_status TEXT NOT NULL DEFAULT 'Awaiting clinician review'
        );
        """)
        # Backward-compatible QR Passport migration: scope each share token to one report
        # and preserve the language selected when the QR link is created.
        qr_columns = {row["name"] for row in c.execute("PRAGMA table_info(qr_tokens)").fetchall()}
        if "report_id" not in qr_columns:
            c.execute("ALTER TABLE qr_tokens ADD COLUMN report_id TEXT")
        if "language" not in qr_columns:
            c.execute("ALTER TABLE qr_tokens ADD COLUMN language TEXT NOT NULL DEFAULT 'en'")

        patient_columns = {row[1] for row in c.execute("PRAGMA table_info(patients)").fetchall()}
        if "user_id" not in patient_columns:
            c.execute("ALTER TABLE patients ADD COLUMN user_id INTEGER REFERENCES users(id)")
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_patients_user_id ON patients(user_id) WHERE user_id IS NOT NULL")
        if c.execute("SELECT COUNT(*) FROM insurance_plans").fetchone()[0] == 0:
            for p in [
                ("Illustrative Individual Plan A","DEMO PROVIDER A","₹5 lakh","Illustrative only; not a real insurance product."),
                ("Illustrative Family Floater Plan B","DEMO PROVIDER B","₹10 lakh","Illustrative only; not a real insurance product."),
                ("Illustrative Individual Plan C","DEMO PROVIDER C","₹15 lakh","Illustrative only; not a real insurance product.")
            ]:
                c.execute("INSERT INTO insurance_plans(name,provider,coverage,notes,is_demo) VALUES(?,?,?,?,1)", p)
        if c.execute("SELECT COUNT(*) FROM medicine_information").fetchone()[0] == 0:
            for m in [
                ("Paracetamol","Commonly used for temporary relief of pain and fever.","Can harm the liver in overdose; check combination products and seek pharmacist/doctor advice.","pain/fever"),
                ("Metformin","A prescription medicine used in some people with type 2 diabetes as part of an individualized treatment plan.","Requires clinician assessment; kidney function, other medicines and side effects matter. Do not start or change it yourself.","diabetes"),
                ("Atorvastatin","A prescription statin used to lower LDL cholesterol and reduce cardiovascular risk in selected patients.","Requires clinician assessment; discuss muscle symptoms, liver considerations, pregnancy and interactions.","cholesterol"),
                ("Amoxicillin","A prescription antibiotic used for certain bacterial infections when clinically appropriate.","Not for viral infections; allergy and antibiotic resistance matter. Use only when prescribed by a clinician.","infection")
            ]:
                c.execute("INSERT INTO medicine_information(generic_name,purpose,cautions,category) VALUES(?,?,?,?)", m)


# Conservative, curated generic-name reference. OCR text is matched only to these
# exact names; fuzzy guessing is deliberately avoided for medication safety.
PRESCRIPTION_MEDICINE_REFERENCE = {
    "paracetamol": ("Pain and fever relief", "Commonly used for temporary relief of mild-to-moderate pain and fever. This does not identify the patient's diagnosis."),
    "acetaminophen": ("Pain and fever relief", "Another name for paracetamol; commonly used for temporary relief of pain and fever."),
    "metformin": ("Blood glucose management", "Used to help manage blood glucose in people with type 2 diabetes. Its presence does not prove the patient has diabetes."),
    "atorvastatin": ("Cholesterol and cardiovascular risk management", "Used to lower LDL cholesterol and reduce cardiovascular risk in selected patients."),
    "rosuvastatin": ("Cholesterol and cardiovascular risk management", "Used to lower LDL cholesterol and reduce cardiovascular risk in selected patients."),
    "amlodipine": ("Blood pressure / angina", "A calcium-channel blocker used for high blood pressure and, in some patients, angina."),
    "telmisartan": ("Blood pressure management", "An angiotensin-receptor blocker used to treat high blood pressure; other indications may apply."),
    "losartan": ("Blood pressure management", "An angiotensin-receptor blocker used for high blood pressure and certain other cardiovascular or kidney-related indications."),
    "olmesartan": ("Blood pressure management", "An angiotensin-receptor blocker used to treat high blood pressure."),
    "pantoprazole": ("Acid-related stomach conditions", "A proton-pump inhibitor used for conditions involving excess stomach acid, such as reflux."),
    "omeprazole": ("Acid-related stomach conditions", "A proton-pump inhibitor used for conditions involving excess stomach acid, such as reflux."),
    "rabeprazole": ("Acid-related stomach conditions", "A proton-pump inhibitor used for conditions involving excess stomach acid, such as reflux."),
    "amoxicillin": ("Certain bacterial infections", "An antibiotic used for selected bacterial infections. It does not treat viral infections."),
    "azithromycin": ("Certain bacterial infections", "An antibiotic used for selected bacterial infections. The correct indication depends on clinician assessment."),
    "doxycycline": ("Certain bacterial infections", "An antibiotic used for selected bacterial infections and some other clinician-directed indications."),
    "cetirizine": ("Allergy symptoms", "An antihistamine commonly used for allergic rhinitis, itching and hives."),
    "levocetirizine": ("Allergy symptoms", "An antihistamine commonly used for allergic rhinitis, itching and hives."),
    "montelukast": ("Asthma/allergy management", "Used in selected patients for asthma prevention/control or allergic rhinitis; it is not a rescue medicine for an acute asthma attack."),
    "ibuprofen": ("Pain, fever and inflammation", "An anti-inflammatory medicine used for pain, fever and inflammation. It may be unsuitable for some people."),
    "diclofenac": ("Pain and inflammation", "An anti-inflammatory medicine used for pain and inflammation; cardiovascular, kidney and stomach risks need consideration."),
    "aspirin": ("Pain/fever or antiplatelet use", "Depending on the dose and clinical context, aspirin may be used for pain/fever or to reduce clotting risk. The purpose cannot be inferred from the name alone."),
    "clopidogrel": ("Prevention of blood clots", "An antiplatelet medicine used to reduce clot-related events in selected cardiovascular conditions."),
    "furosemide": ("Fluid reduction / blood pressure", "A diuretic used for fluid retention and sometimes high blood pressure; monitoring is important."),
    "levothyroxine": ("Thyroid hormone replacement", "Used as thyroid hormone replacement in people with an underactive thyroid."),
    "cholecalciferol": ("Vitamin D supplementation", "Vitamin D3 used to prevent or treat vitamin D deficiency."),
    "vitamin d3": ("Vitamin D supplementation", "Vitamin D3 used to prevent or treat vitamin D deficiency."),
    "calcium carbonate": ("Calcium supplementation / antacid", "Can be used as a calcium supplement or as an antacid; the purpose depends on the prescribed product and dose."),
}

def explain_prescription_text(text):
    import re
    normalized = re.sub(r"[^a-z0-9+ ]+", " ", (text or "").lower())
    normalized = re.sub(r"\s+", " ", normalized).strip()
    found = []
    for name, (category, purpose) in PRESCRIPTION_MEDICINE_REFERENCE.items():
        pattern = r"(?<![a-z0-9])" + re.escape(name) + r"(?![a-z0-9])"
        if re.search(pattern, normalized):
            found.append({"name": name.title(), "purpose": purpose, "category": category,
                          "match_type": "Exact generic-name text match",
                          "warning": "Confirm the spelling against the original prescription. This common use is not a diagnosis."})
    found.sort(key=lambda item: normalized.find(item["name"].lower()))
    return found

def patient_id():
    """Return the authenticated user's patient workspace, preserving legacy session data."""
    pid = session.get("patient_id")
    if pid:
        return pid
    uid = session.get("user_id")
    with db() as c:
        if uid:
            row = c.execute("SELECT id FROM patients WHERE user_id=?", (uid,)).fetchone()
            if row:
                pid = row["id"]
            else:
                pid = uuid.uuid4().hex
                c.execute("INSERT INTO patients(id,created_at,preferred_language,user_id) VALUES(?,?,?,?)",
                          (pid, datetime.now(timezone.utc).isoformat(), current_language(), uid))
        else:
            pid = uuid.uuid4().hex
            c.execute("INSERT OR IGNORE INTO patients(id,created_at) VALUES(?,?)",
                      (pid, datetime.now(timezone.utc).isoformat()))
    session["patient_id"] = pid
    return pid


def _csrf_token():
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def _safe_local_redirect(candidate, fallback):
    if not candidate:
        return fallback
    parsed = urlparse(candidate)
    if parsed.scheme or parsed.netloc or not candidate.startswith("/") or candidate.startswith("//"):
        return fallback
    return candidate


@app.before_request
def enforce_authentication_and_csrf():
    public_endpoints = {
        "static", "login", "login_post", "signup", "signup_post", "forgot_password", "forgot_password_post", "reset_password", "reset_password_post",
        "set_auth_language", "translations", "health", "shared_history", "qr_png", "qr_pdf"
    }
    if request.endpoint in public_endpoints or request.endpoint is None:
        # 404s are handled normally; static/QR token routes remain public by design.
        if request.endpoint is None:
            return None
    elif not session.get("user_id"):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Please sign in to continue.", "login_required": True}), 401
        return redirect(url_for("login"))

    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        expected = session.get("csrf_token", "")
        supplied = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token", "")
        if not expected or not supplied or not hmac.compare_digest(expected, supplied):
            if request.path.startswith("/api/"):
                return jsonify({"error": "Security token expired. Refresh the page and try again."}), 400
            return "Your form security token expired. Please go back, refresh and try again.", 400


@app.context_processor
def inject_template_context():
    _csrf_token()
    user_name = session.get("user_name", "")
    def tr(key):
        lang = current_language()
        try:
            with (BASE_DIR / "translations" / f"{lang}.json").open("r", encoding="utf-8") as f:
                dictionary = json.load(f)
            return dictionary.get(key, key)
        except (OSError, json.JSONDecodeError):
            return key
    return {"csrf_token": _csrf_token, "current_user_name": user_name, "tr": tr}


@app.get("/login")
def login():
    if session.get("user_id"):
        return redirect(url_for("home"))
    return render_template("login.html", initial_language=current_language())


@app.post("/login")
def login_post():
    email = (request.form.get("email") or "").strip().lower()
    password = request.form.get("password") or ""
    remember = request.form.get("remember") == "on"
    from werkzeug.security import check_password_hash
    with db() as c:
        user = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    if not user or not check_password_hash(user["password_hash"], password):
        return render_template("login.html", error="Email or password is incorrect.", email=email,
                               initial_language=current_language()), 401
    language = current_language()
    old_pid = session.get("patient_id")
    session.clear()
    session.permanent = remember
    session["user_id"] = user["id"]
    session["user_name"] = user["full_name"]
    session["language"] = language
    _csrf_token()
    with db() as c:
        patient = c.execute("SELECT id,preferred_language FROM patients WHERE user_id=?", (user["id"],)).fetchone()
        if patient:
            pid = patient["id"]
            if patient["preferred_language"] in SUPPORTED_LANGUAGES:
                language = patient["preferred_language"]
                session["language"] = language
        elif old_pid:
            existing = c.execute("SELECT id,user_id FROM patients WHERE id=?", (old_pid,)).fetchone()
            if existing and existing["user_id"] is None:
                pid = old_pid
                c.execute("UPDATE patients SET user_id=?,preferred_language=? WHERE id=?", (user["id"], language, pid))
            else:
                pid = uuid.uuid4().hex
                c.execute("INSERT INTO patients(id,created_at,preferred_language,user_id) VALUES(?,?,?,?)",
                          (pid, datetime.now(timezone.utc).isoformat(), language, user["id"]))
        else:
            pid = uuid.uuid4().hex
            c.execute("INSERT INTO patients(id,created_at,preferred_language,user_id) VALUES(?,?,?,?)",
                      (pid, datetime.now(timezone.utc).isoformat(), language, user["id"]))
    session["patient_id"] = pid
    return redirect(url_for("home"))


@app.get("/signup")
def signup():
    if session.get("user_id"):
        return redirect(url_for("home"))
    return render_template("signup.html", initial_language=current_language())


@app.post("/signup")
def signup_post():
    full_name = (request.form.get("full_name") or "").strip()
    email = (request.form.get("email") or "").strip().lower()
    phone = (request.form.get("phone") or "").strip()
    password = request.form.get("password") or ""
    confirm = request.form.get("confirm_password") or ""
    error = None
    if len(full_name) < 2 or len(full_name) > 100:
        error = "Enter your full name (2–100 characters)."
    elif not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        error = "Enter a valid email address."
    elif len(phone) > 30:
        error = "Phone number is too long."
    elif len(password) < 10 or not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        error = "Use at least 10 characters with at least one letter and one number."
    elif password != confirm:
        error = "Passwords do not match."
    if error:
        return render_template("signup.html", error=error, full_name=full_name, email=email,
                               phone=phone, initial_language=current_language()), 400
    from werkzeug.security import generate_password_hash
    now = datetime.now(timezone.utc).isoformat()
    try:
        with db() as c:
            cur = c.execute("INSERT INTO users(full_name,email,phone,password_hash,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                            (full_name, email, phone, generate_password_hash(password), now, now))
            uid = cur.lastrowid
            old_pid = session.get("patient_id")
            if old_pid:
                old = c.execute("SELECT user_id FROM patients WHERE id=?", (old_pid,)).fetchone()
            else:
                old = None
            if old and old["user_id"] is None:
                c.execute("UPDATE patients SET user_id=?,preferred_language=? WHERE id=?", (uid, current_language(), old_pid))
            else:
                c.execute("INSERT INTO patients(id,created_at,preferred_language,user_id) VALUES(?,?,?,?)",
                          (uuid.uuid4().hex, now, current_language(), uid))
    except sqlite3.IntegrityError:
        return render_template("signup.html", error="An account with this email already exists.",
                               full_name=full_name, email=email, phone=phone,
                               initial_language=current_language()), 409
    return redirect(url_for("login", registered="1"))


@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.get("/set-language/<lang>")
def set_auth_language(lang):
    if lang in SUPPORTED_LANGUAGES:
        session["language"] = lang
        if session.get("user_id") and session.get("patient_id"):
            with db() as c:
                c.execute("UPDATE patients SET preferred_language=? WHERE id=? AND user_id=?",
                          (lang, session["patient_id"], session["user_id"]))
    fallback = url_for("login")
    return redirect(_safe_local_redirect(request.args.get("next"), fallback))


@app.get("/forgot-password")
def forgot_password():
    return render_template("forgot_password.html", initial_language=current_language())


@app.post("/forgot-password")
def forgot_password_post():
    email = (request.form.get("email") or "").strip().lower()
    # Always return the same message to avoid revealing whether an account exists.
    generic_message = "If an account matches that email and email delivery is configured, a reset link will be sent."
    with db() as c:
        user = c.execute("SELECT id,email,full_name FROM users WHERE email=?", (email,)).fetchone()
        if user:
            raw_token = secrets.token_urlsafe(36)
            token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
            expires = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
            c.execute("INSERT INTO password_reset_tokens(token_hash,user_id,expires_at) VALUES(?,?,?)",
                      (token_hash, user["id"], expires))
    if user and os.environ.get("SMTP_HOST") and os.environ.get("MAIL_FROM"):
        try:
            reset_url = url_for("reset_password", token=raw_token, _external=True)
            msg = EmailMessage()
            msg["Subject"] = "Reset your MedExplain password"
            msg["From"] = os.environ["MAIL_FROM"]
            msg["To"] = user["email"]
            msg.set_content(f"Hello {user['full_name']},\n\nUse this link within 30 minutes to reset your MedExplain password:\n{reset_url}\n\nIf you did not request this, ignore this email.")
            host = os.environ["SMTP_HOST"]
            port = int(os.environ.get("SMTP_PORT", "587"))
            if os.environ.get("SMTP_SSL", "0") == "1":
                with smtplib.SMTP_SSL(host, port, timeout=15) as server:
                    if os.environ.get("SMTP_USER"): server.login(os.environ["SMTP_USER"], os.environ.get("SMTP_PASSWORD", ""))
                    server.send_message(msg)
            else:
                with smtplib.SMTP(host, port, timeout=15) as server:
                    server.starttls()
                    if os.environ.get("SMTP_USER"): server.login(os.environ["SMTP_USER"], os.environ.get("SMTP_PASSWORD", ""))
                    server.send_message(msg)
        except Exception:
            app.logger.exception("Password reset email could not be sent")
    return render_template("forgot_password.html", message=generic_message,
                           initial_language=current_language())


@app.get("/reset-password/<token>")
def reset_password(token):
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with db() as c:
        row = c.execute("SELECT user_id,expires_at,used FROM password_reset_tokens WHERE token_hash=?", (token_hash,)).fetchone()
    if not row or row["used"] or datetime.fromisoformat(row["expires_at"]) < datetime.now(timezone.utc):
        return render_template("reset_password.html", error="This reset link is invalid or expired.", token=""), 400
    return render_template("reset_password.html", token=token, initial_language=current_language())


@app.post("/reset-password/<token>")
def reset_password_post(token):
    password = request.form.get("password") or ""
    confirm = request.form.get("confirm_password") or ""
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with db() as c:
        row = c.execute("SELECT user_id,expires_at,used FROM password_reset_tokens WHERE token_hash=?", (token_hash,)).fetchone()
        if not row or row["used"] or datetime.fromisoformat(row["expires_at"]) < datetime.now(timezone.utc):
            return render_template("reset_password.html", error="This reset link is invalid or expired.", token=""), 400
        if len(password) < 10 or not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password) or password != confirm:
            return render_template("reset_password.html", error="Use 10+ characters with a letter and number; both fields must match.", token=token), 400
        from werkzeug.security import generate_password_hash
        now = datetime.now(timezone.utc).isoformat()
        c.execute("UPDATE users SET password_hash=?,updated_at=? WHERE id=?", (generate_password_hash(password), now, row["user_id"]))
        c.execute("UPDATE password_reset_tokens SET used=1 WHERE token_hash=?", (token_hash,))
        c.execute("UPDATE password_reset_tokens SET used=1 WHERE user_id=?", (row["user_id"],))
    return redirect(url_for("login", reset="1"))


@app.get("/profile")
def profile():
    with db() as c:
        user = c.execute("SELECT full_name,email,phone,created_at FROM users WHERE id=?", (session["user_id"],)).fetchone()
    return render_template("profile.html", user=dict(user), initial_language=current_language())


@app.post("/profile")
def update_profile():
    full_name = (request.form.get("full_name") or "").strip()
    phone = (request.form.get("phone") or "").strip()
    if len(full_name) < 2 or len(full_name) > 100 or len(phone) > 30:
        with db() as c:
            user = dict(c.execute("SELECT full_name,email,phone,created_at FROM users WHERE id=?", (session["user_id"],)).fetchone())
        return render_template("profile.html", user=user, error="Check your name and phone number.", initial_language=current_language()), 400
    with db() as c:
        c.execute("UPDATE users SET full_name=?,phone=?,updated_at=? WHERE id=?",
                  (full_name, phone, datetime.now(timezone.utc).isoformat(), session["user_id"]))
    session["user_name"] = full_name
    return redirect(url_for("profile", updated="1"))


@app.post("/profile/password")
def change_password():
    current = request.form.get("current_password") or ""
    new = request.form.get("new_password") or ""
    confirm = request.form.get("confirm_password") or ""
    from werkzeug.security import check_password_hash, generate_password_hash
    with db() as c:
        user = c.execute("SELECT password_hash FROM users WHERE id=?", (session["user_id"],)).fetchone()
        if not user or not check_password_hash(user["password_hash"], current):
            error = "Current password is incorrect."
        elif len(new) < 10 or not re.search(r"[A-Za-z]", new) or not re.search(r"\d", new) or new != confirm:
            error = "Use 10+ characters with a letter and number; both new password fields must match."
        else:
            c.execute("UPDATE users SET password_hash=?,updated_at=? WHERE id=?",
                      (generate_password_hash(new), datetime.now(timezone.utc).isoformat(), session["user_id"]))
            error = None
    with db() as c:
        user_row = dict(c.execute("SELECT full_name,email,phone,created_at FROM users WHERE id=?", (session["user_id"],)).fetchone())
    return render_template("profile.html", user=user_row, password_message="Password updated." if not error else None,
                           password_error=error, initial_language=current_language()), 400 if error else 200


@app.get("/")
def home():
    patient_id()
    return render_template("index.html", initial_language=current_language(), user_name=session.get("user_name", "Patient"), current_date=datetime.now().astimezone().strftime("%d-%m-%Y"))


SUPPORTED_LANGUAGES = {"en", "hi", "pa"}


def current_language():
    lang = session.get("language", "en")
    return lang if lang in SUPPORTED_LANGUAGES else "en"


@app.get("/api/translations/<lang>")
def translations(lang):
    """Serve the reviewed UI dictionary for the selected language."""
    if lang not in SUPPORTED_LANGUAGES:
        return jsonify({"error": "Unsupported language"}), 404
    path = BASE_DIR / "translations" / f"{lang}.json"
    try:
        with path.open("r", encoding="utf-8") as handle:
            return jsonify(json.load(handle))
    except (OSError, json.JSONDecodeError):
        app.logger.exception("Translation dictionary could not be loaded: %s", lang)
        return jsonify({"error": "Translation dictionary unavailable"}), 500


@lru_cache(maxsize=2048)
def translate_ui_copy(text: str, target_language: str) -> str:
    """Translate generic explanatory copy through a configured trusted translator.

    Only generic explanatory strings are passed here. Patient values, units,
    medicine names, source OCR text and identifiers are deliberately excluded.
    Configure LIBRETRANSLATE_URL to a trusted/self-hosted LibreTranslate endpoint.
    """
    if target_language == "en" or not text:
        return text
    endpoint = os.environ.get("LIBRETRANSLATE_URL", "").strip().rstrip("/")
    if not endpoint:
        return text
    payload = {"q": text, "source": "en", "target": target_language, "format": "text"}
    api_key = os.environ.get("LIBRETRANSLATE_API_KEY", "").strip()
    if api_key:
        payload["api_key"] = api_key
    request_obj = urllib.request.Request(
        endpoint + "/translate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request_obj, timeout=5) as response:
            translated = json.loads(response.read().decode("utf-8")).get("translatedText")
        return translated.strip() if isinstance(translated, str) and translated.strip() else text
    except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError):
        app.logger.warning("Configured translation service unavailable; showing English source copy.")
        return text


def localize_report_copy(result: dict, lang: str) -> dict:
    """Translate only explanatory prose; leave every clinical datum untouched."""
    localized = json.loads(json.dumps(result, ensure_ascii=False))
    localized["source_copy"] = {
        "notice": result.get("notice", ""),
        "results": [{field: item.get(field, "") for field in ("organ", "about", "explanation", "lifestyle")}
                    for item in result.get("results", [])]
    }
    if lang == "en":
        localized["translation_status"] = "translated"
        return localized
    did_translate = False
    for field in ("notice",):
        if isinstance(localized.get(field), str):
            source_text = localized[field]
            localized[field] = translate_ui_copy(source_text, lang)
            did_translate = did_translate or localized[field] != source_text
    for item in localized.get("results", []):
        for field in ("organ", "about", "explanation", "lifestyle"):
            if isinstance(item.get(field), str):
                source_text = item[field]
                item[field] = translate_ui_copy(source_text, lang)
                did_translate = did_translate or item[field] != source_text
    localized["translation_status"] = "translated" if did_translate else "english_fallback"
    return localized


def localize_medicine_copy(data: dict, lang: str) -> dict:
    localized = json.loads(json.dumps(data, ensure_ascii=False))
    if lang == "en":
        return localized
    for field in ("message", "notice"):
        if isinstance(localized.get(field), str):
            localized[field] = translate_ui_copy(localized[field], lang)
    for item in localized.get("items", localized.get("medicines", [])):
        if not isinstance(item, dict):
            continue
        for field in ("purpose", "cautions", "category", "warning"):
            if isinstance(item.get(field), str):
                item[field] = translate_ui_copy(item[field], lang)
    return localized

@app.errorhandler(413)
def too_large(_error):
    return jsonify({"error": "File is too large. Please upload a file smaller than 25 MB."}), 413

def persist_report(result):
    pid = patient_id()
    rid = uuid.uuid4().hex
    created = datetime.now(timezone.utc).isoformat()
    with db() as c:
        c.execute("""INSERT INTO reports(id,patient_id,filename,created_at,summary_json,results_json)
                     VALUES(?,?,?,?,?,?)""",
                  (rid, pid, result.get("filename","Report"), created,
                   json.dumps(result.get("summary",{})), json.dumps(result.get("results",[]))))
    result["report_id"] = rid
    result["created_at"] = created
    return result

@app.post("/api/analyze")
def analyze():
    if "report" not in request.files:
        return jsonify({"error": "Please choose a PDF or image report."}), 400
    file = request.files["report"]
    filename = secure_filename(file.filename or "")
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED:
        return jsonify({"error": "Supported formats: PDF, PNG, JPG and WEBP."}), 400
    if not filename:
        return jsonify({"error": "The selected file has no valid filename."}), 400
    path = app.config["UPLOAD_FOLDER"] / f"{uuid.uuid4().hex}{suffix}"
    file.save(path)
    try:
        document = extract_document(path)
        text = document["text"]
        if not text.strip():
            return jsonify({"error": "No readable text was found. For scanned files, install Tesseract OCR and try again."}), 422
        result = analyze_report(text, page_count=document["page_count"], pages_with_ocr=document["pages_with_ocr"])
        result["filename"] = filename
        result["extracted_preview"] = text[:3500]
        result["extraction"] = {"pages_processed":document["page_count"],"pages_with_text":document["pages_with_text"],"pages_with_ocr":document["pages_with_ocr"]}
        return jsonify(localize_report_copy(persist_report(result), current_language()))
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 422
    except Exception:
        app.logger.exception("Report processing failed")
        return jsonify({"error": "Could not process this report. Inspect the server terminal for details."}), 500
    finally:
        path.unlink(missing_ok=True)

@app.get("/api/demo")
def demo():
    sample = """[[PAGE:1]]
COMPLETE BLOOD COUNT
Hemoglobin 13.8 g/dL 12.0 - 16.0
RBC Count 4.7 million/cumm 4.0 - 5.5
Hematocrit 41 % 36 - 46
MCV 87 fL 80 - 100
MCH 29 pg 27 - 33
MCHC 33 g/dL 31 - 36
WBC 7.2 10^3/uL 4.0 - 11.0
Neutrophils 60 % 40 - 75
Lymphocytes 32 % 20 - 45
Platelet Count 250 10^3/uL 150 - 450
[[PAGE:2]]
KIDNEY FUNCTION TEST
Blood Urea 25 mg/dL 15 - 40
Creatinine 0.9 mg/dL 0.6 - 1.2
Uric Acid 5.1 mg/dL 3.5 - 7.2
eGFR 98 mL/min 90 - 120
[[PAGE:3]]
LIPID PROFILE
Total Cholesterol 218 mg/dL 0 - 200
HDL Cholesterol 48 mg/dL 40 - 60
LDL Cholesterol 142 mg/dL 0 - 130
Triglycerides 150 mg/dL 0 - 150
[[PAGE:4]]
LIVER FUNCTION TEST
ALT (SGPT) 32 U/L 0 - 45
AST (SGOT) 28 U/L 0 - 40
Total Bilirubin 0.8 mg/dL 0.2 - 1.2
Albumin 4.2 g/dL 3.5 - 5.0
[[PAGE:5]]
THYROID PROFILE
TSH 2.1 uIU/mL 0.4 - 4.5
Total T3 1.2 ng/mL 0.8 - 2.0
Total T4 8.5 ug/dL 5.0 - 12.0
"""
    result = analyze_report(sample, page_count=5, pages_with_ocr=[])
    result.update({"filename":"synthetic_multi_page_demo.txt","extracted_preview":sample[:3500],
                   "extraction":{"pages_processed":5,"pages_with_text":[1,2,3,4,5],"pages_with_ocr":[]}})
    return jsonify(localize_report_copy(persist_report(result), current_language()))

@app.get("/api/history")
def history_api():
    pid = patient_id()
    with db() as c:
        rows = c.execute("SELECT id,filename,created_at,summary_json,results_json FROM reports WHERE patient_id=? ORDER BY created_at DESC",(pid,)).fetchall()
    reports = []
    for r in rows:
        report = {"id":r["id"],"filename":r["filename"],"created_at":r["created_at"],
                  "summary":json.loads(r["summary_json"]),"results":json.loads(r["results_json"])}
        reports.append(localize_report_copy(report, current_language()))
    return jsonify({"patient_id":pid,"reports":reports})

@app.post("/api/qr")
def create_qr():
    """Create a private QR Passport link for one saved report."""
    pid = patient_id()
    payload = request.get_json(silent=True) or {}
    report_id = str(payload.get("report_id", "")).strip()
    if not report_id:
        return jsonify({"error": "Choose a report before generating its QR Passport."}), 400
    with db() as c:
        report = c.execute(
            "SELECT id FROM reports WHERE id=? AND patient_id=?", (report_id, pid)
        ).fetchone()
        if not report:
            return jsonify({"error": "The selected report was not found in your account."}), 404
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        # Revoke only the previous link for this report, not links to other reports.
        c.execute("UPDATE qr_tokens SET revoked=1 WHERE patient_id=? AND (report_id=? OR report_id IS NULL)", (pid, report_id))
        c.execute(
            "INSERT INTO qr_tokens(token_hash,patient_id,created_at,revoked,report_id,language) VALUES(?,?,?,?,?,?)",
            (token_hash, pid, datetime.now(timezone.utc).isoformat(), 0, report_id, current_language())
        )
    return jsonify({"url": url_for("shared_history", token=token, _external=True), "token": token})


@app.get("/qr/<token>.png")
def qr_png(token):
    import hashlib
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with db() as c:
        valid = c.execute("SELECT 1 FROM qr_tokens WHERE token_hash=? AND revoked=0",(token_hash,)).fetchone()
    if not valid:
        return jsonify({"error":"QR access is invalid or revoked."}),404
    try:
        import qrcode
        image = qrcode.make(url_for("shared_history",token=token,_external=True))
        buf=io.BytesIO(); image.save(buf,format="PNG"); buf.seek(0)
        return send_file(buf,mimetype="image/png",download_name="MedExplain_Medical_History_QR.png")
    except ImportError:
        return jsonify({"error":"QR generation dependency missing. Install requirements.txt."}),500

@app.get("/qr/<token>.pdf")
def qr_pdf(token):
    import hashlib
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with db() as c:
        valid = c.execute("SELECT 1 FROM qr_tokens WHERE token_hash=? AND revoked=0",(token_hash,)).fetchone()
    if not valid:
        return jsonify({"error":"QR access is invalid or revoked."}),404
    try:
        import qrcode
        image = qrcode.make(url_for("shared_history",token=token,_external=True)).convert("RGB")
        buf=io.BytesIO(); image.save(buf,format="PDF",resolution=150); buf.seek(0)
        return send_file(buf,mimetype="application/pdf",download_name="MedExplain_Medical_History_QR.pdf")
    except ImportError:
        return jsonify({"error":"QR generation dependency missing. Install requirements.txt."}),500

@app.get("/history/<token>")
def shared_history(token):
    """Render only the report explicitly associated with this QR Passport."""
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with db() as c:
        row = c.execute(
            "SELECT patient_id,report_id,language FROM qr_tokens WHERE token_hash=? AND revoked=0",
            (token_hash,)
        ).fetchone()
        if not row:
            return render_template("shared_history.html", reports=[], invalid=True), 404
        if row["report_id"]:
            reports = c.execute(
                "SELECT id,filename,created_at,summary_json,results_json FROM reports WHERE id=? AND patient_id=?",
                (row["report_id"], row["patient_id"])
            ).fetchall()
        else:
            # Compatibility for QR links created by earlier app versions.
            reports = c.execute(
                "SELECT id,filename,created_at,summary_json,results_json FROM reports WHERE patient_id=? ORDER BY created_at DESC",
                (row["patient_id"],)
            ).fetchall()
        language = row["language"] or "en"
    report_data = []
    for r in reports:
        item = {
            "id": r["id"], "filename": r["filename"], "created_at": r["created_at"],
            "summary": json.loads(r["summary_json"]), "results": json.loads(r["results_json"])
        }
        report_data.append(localize_report_copy(item, language))
    return render_template("shared_history.html", reports=report_data, invalid=False, language=language)


@app.post("/api/qr/revoke")
def revoke_qr():
    pid = patient_id()
    payload = request.get_json(silent=True) or {}
    report_id = str(payload.get("report_id", "")).strip()
    with db() as c:
        if report_id:
            c.execute("UPDATE qr_tokens SET revoked=1 WHERE patient_id=? AND (report_id=? OR report_id IS NULL)", (pid, report_id))
        else:
            c.execute("UPDATE qr_tokens SET revoked=1 WHERE patient_id=?", (pid,))
    return jsonify({"success": True, "message": "QR access revoked."})


@app.post("/api/translate-copy")
def translate_copy_api():
    """Translate generic report explanation strings without sending report values."""
    data = request.get_json(silent=True) or {}
    texts = data.get("texts", [])
    if not isinstance(texts, list) or len(texts) > 250:
        return jsonify({"error": "Invalid translation request"}), 400
    safe_texts = [str(value)[:3000] for value in texts]
    lang = current_language()
    translated = [translate_ui_copy(value, lang) for value in safe_texts]
    did_translate = lang == "en" or any(a != b for a, b in zip(safe_texts, translated))
    return jsonify({"translations": translated,
                    "translation_status": "translated" if did_translate else "english_fallback"})


@app.post("/api/language")
def set_language():
    data = request.get_json(silent=True) or {}
    lang = data.get("language", "en")
    if lang not in SUPPORTED_LANGUAGES:
        return jsonify({"error":"Unsupported language"}),400
    session["language"] = lang
    with db() as c:
        c.execute("UPDATE patients SET preferred_language=? WHERE id=?",(lang,patient_id()))
    return jsonify({"language":lang})

@app.get("/api/insurance")
def insurance():
    with db() as c:
        rows=c.execute("SELECT name,provider,coverage,notes FROM insurance_plans ORDER BY id").fetchall()
    return jsonify({"plans":[dict(r) for r in rows],"notice":"DEMO DATA ONLY. These are fictional illustrative entries, not purchasable policies or quotes. Verify real policy wording and premiums with licensed insurers."})

@app.get("/api/medicines")
def medicines():
    q=request.args.get("q","").strip().lower()
    with db() as c:
        rows=c.execute("SELECT generic_name,purpose,cautions,category FROM medicine_information WHERE lower(generic_name) LIKE ? OR lower(category) LIKE ? ORDER BY generic_name", (f"%{q}%",f"%{q}%")).fetchall()
    payload = {"items":[dict(r) for r in rows],"notice":"Educational medicine information only. This is not a prescription or a recommendation to start, stop or change treatment."}
    return jsonify(localize_medicine_copy(payload, current_language()))


@app.get("/api/progress")
def progress_api():
    pid=patient_id()
    with db() as c:
        rows=c.execute("SELECT id,filename,created_at,results_json FROM reports WHERE patient_id=? ORDER BY created_at ASC",(pid,)).fetchall()
    by_name={}
    for row in rows:
        for item in json.loads(row["results_json"]):
            name=item.get("name")
            if name:
                by_name.setdefault(name,[]).append({"report_id":row["id"],"filename":row["filename"],
                    "date":row["created_at"],"value":item.get("value"),"unit":item.get("unit"),
                    "status":item.get("status"),"low":item.get("low"),"high":item.get("high")})
    trends=[]
    for name,items in by_name.items():
        if len(items)<2: continue
        old,new=items[-2],items[-1]
        delta=None
        if isinstance(old["value"],(int,float)) and isinstance(new["value"],(int,float)):
            delta=round(new["value"]-old["value"],4)
        trends.append({"name":name,"previous":old,"current":new,"change":delta,
                       "same_unit":old.get("unit")==new.get("unit")})
    payload = {"reports_count":len(rows),"trends":trends,
               "notice":"A numerical change is not automatically an improvement. Interpret only comparable tests with matching units, methods and clinical context; discuss results with a clinician."}
    return jsonify(localize_medicine_copy(payload, current_language()))

@app.post("/api/prescriptions")
def upload_prescription():
    if "prescription" not in request.files: return jsonify({"error":"Choose a prescription PDF or image."}),400
    f=request.files["prescription"]; filename=secure_filename(f.filename or "")
    ext=Path(filename).suffix.lower()
    if ext not in ALLOWED: return jsonify({"error":"Supported formats: PDF, PNG, JPG and WEBP."}),400
    temp=app.config["UPLOAD_FOLDER"]/f"{uuid.uuid4().hex}{ext}"; f.save(temp)
    try:
        extracted=extract_prescription_text(temp).strip()
        if not extracted: return jsonify({"error":"Could not read text. Try a clearer scan; handwritten prescriptions may need manual entry."}),422
        rid=uuid.uuid4().hex; created=datetime.now(timezone.utc).isoformat()
        with db() as c:
            c.execute("INSERT INTO prescriptions(id,patient_id,filename,extracted_text,created_at) VALUES(?,?,?,?,?)",
                      (rid,patient_id(),filename,extracted[:12000],created))
        medicines = explain_prescription_text(extracted)
        payload = {"id":rid,"filename":filename,"text":extracted[:12000],
                   "medicines": medicines,
                   "message":"Prescription text extracted. Only exact matches to the built-in generic-name reference are listed; unclear names are not guessed. No medicine schedule has been created."}
        return jsonify(localize_medicine_copy(payload, current_language()))
    except RuntimeError as exc:
        return jsonify({"error":str(exc)}),422
    except Exception:
        app.logger.exception("Prescription extraction failed")
        return jsonify({"error":"Prescription OCR failed unexpectedly. Check the server terminal for details."}),500
    finally: temp.unlink(missing_ok=True)

@app.post("/api/schedules")
def add_schedule():
    data=request.get_json(silent=True) or {}
    required=["medicine_name","tablets","dose_time","start_date","end_date"]
    if any(not str(data.get(k,"")).strip() for k in required):
        return jsonify({"error":"Medicine, quantity, time, start date and end date are required."}),400
    try:
        tablets=float(data["tablets"])
        if tablets<=0 or tablets>50: raise ValueError()
        from datetime import date
        start=date.fromisoformat(data["start_date"]); end=date.fromisoformat(data["end_date"])
        if end<start: raise ValueError()
        datetime.strptime(data["dose_time"],"%H:%M")
    except Exception:
        return jsonify({"error":"Check quantity, dates and time. End date must not be before start date."}),400
    sid=uuid.uuid4().hex
    with db() as c:
        c.execute("""INSERT INTO medicine_schedules
        (id,patient_id,prescription_id,medicine_name,strength,tablets,dose_unit,dose_time,start_date,end_date,instructions,created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
        (sid,patient_id(),data.get("prescription_id"),str(data["medicine_name"])[:120],
         str(data.get("strength",""))[:80],tablets,str(data.get("dose_unit","tablet"))[:30],
         data["dose_time"],data["start_date"],data["end_date"],str(data.get("instructions",""))[:500],
         datetime.now(timezone.utc).isoformat()))
    return jsonify({"success":True,"id":sid})

@app.get("/api/schedules")
def list_schedules():
    with db() as c:
        rows=c.execute("SELECT * FROM medicine_schedules WHERE patient_id=? AND active=1 ORDER BY dose_time",(patient_id(),)).fetchall()
        logs=c.execute("SELECT schedule_id,scheduled_date,scheduled_time,status FROM medicine_logs WHERE patient_id=?",(patient_id(),)).fetchall()
    return jsonify({"schedules":[dict(r) for r in rows],"logs":[dict(r) for r in logs]})

@app.post("/api/schedules/<sid>/log")
def log_dose(sid):
    data=request.get_json(silent=True) or {}; status=data.get("status")
    if status not in {"taken","skipped"}: return jsonify({"error":"Status must be taken or skipped."}),400
    with db() as c:
        row=c.execute("SELECT id,dose_time FROM medicine_schedules WHERE id=? AND patient_id=? AND active=1",(sid,patient_id())).fetchone()
        if not row:return jsonify({"error":"Schedule not found."}),404
        # Prefer the browser's local calendar date so logs align with the
        # reminder clock shown to the patient; validate both values strictly.
        from datetime import date
        today=data.get("scheduled_date") or datetime.now().astimezone().date().isoformat()
        scheduled_time=row["dose_time"]
        try:
            date.fromisoformat(today)
            if data.get("scheduled_time"):
                datetime.strptime(data["scheduled_time"], "%H:%M")
        except Exception:
            return jsonify({"error":"Invalid local date or time."}),400
        c.execute("INSERT INTO medicine_logs(id,schedule_id,patient_id,scheduled_date,scheduled_time,status,logged_at) VALUES(?,?,?,?,?,?,?)",
                  (uuid.uuid4().hex,sid,patient_id(),today,scheduled_time,status,datetime.now(timezone.utc).isoformat()))
    return jsonify({"success":True})

@app.post("/api/xray")
def upload_xray():
    if "xray" not in request.files:return jsonify({"error":"Choose an X-ray image."}),400
    f=request.files["xray"]; filename=secure_filename(f.filename or "")
    ext=Path(filename).suffix.lower()
    if ext not in {".png",".jpg",".jpeg",".webp"}:return jsonify({"error":"Upload an X-ray image as PNG, JPG or WEBP."}),400
    image_type=(request.form.get("image_type") or "Unspecified").strip()[:50]
    stored=f"xray_{uuid.uuid4().hex}{ext}"; f.save(app.config["UPLOAD_FOLDER"]/stored)
    xid=uuid.uuid4().hex
    with db() as c:
        c.execute("INSERT INTO xray_uploads(id,patient_id,filename,stored_filename,image_type,created_at) VALUES(?,?,?,?,?,?)",
                  (xid,patient_id(),filename,stored,image_type,datetime.now(timezone.utc).isoformat()))
    return jsonify({"id":xid,"filename":filename,"image_type":image_type,
                    "status":"Uploaded — awaiting clinician/radiologist review",
                    "notice":"This version stores and organizes X-ray images only. It does not diagnose or interpret X-rays. A validated imaging model and radiologist review are required for image findings."})

@app.get("/api/xrays")
def list_xrays():
    with db() as c:
        rows=c.execute("SELECT id,filename,image_type,created_at,review_status FROM xray_uploads WHERE patient_id=? ORDER BY created_at DESC",(patient_id(),)).fetchall()
    return jsonify({"items":[dict(r) for r in rows]})

@app.get("/health")
def health():
    return jsonify({"status":"ok","database":"sqlite"})

init_db()
if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG","0")=="1", host="0.0.0.0", port=5000)
