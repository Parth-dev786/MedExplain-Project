# MedExplain — Multi-page Health Report Interpreter

A hackathon educational prototype that extracts supported laboratory parameters from **all pages** of a PDF or from a report image, then presents plain-language educational explanations.

## What's improved in this build

- Reads every page of a PDF (up to 100 pages), rather than relying on a single page.
- Handles mixed PDFs: pages with embedded text are extracted directly; pages with little/no embedded text are sent through optional Tesseract OCR.
- Detects a broader set of common CBC, glucose, kidney, lipid, liver and thyroid labels.
- Searches nearby lines for values and attempts to read the laboratory's printed reference interval.
- Shows the page number, extracted source snippet and an approximate extraction-confidence indicator for each result.
- Uses **Needs review** when a printed reference interval was not detected. It no longer silently applies generic demo ranges to uploaded patient reports.
- Includes a synthetic 5-page demo to demonstrate multi-page processing.
- Uploads are deleted from the server after processing; the app does not save patient reports.

## Run on Windows PowerShell

```powershell
py -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000` on the same computer. For QR scanning from a phone on the same Wi-Fi, open the app using the computer’s LAN IP (for example `http://192.168.x.x:5000`) and allow the port through the local firewall.

If you do not want to activate the environment, run:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe app.py
```

## OCR setup for scanned reports

Text-based PDFs can be read without Tesseract. Scanned PDFs and image uploads require Tesseract OCR installed separately on the computer. After installing Tesseract, ensure it is available on PATH, then restart the terminal and app.

If OCR is not installed, digital-text pages may still work, but scanned pages may be skipped or yield incomplete extraction.

## Supported parameter groups

The prototype includes common labels from:
- CBC: hemoglobin, RBC, hematocrit/PCV, MCV, MCH, MCHC, RDW, WBC, neutrophils, lymphocytes, eosinophils, platelets
- Glucose: fasting and random glucose
- Kidney: creatinine, urea, BUN, uric acid, eGFR
- Lipid: total cholesterol, LDL, HDL, triglycerides
- Liver: ALT/SGPT, AST/SGOT, bilirubin, ALP, albumin
- Thyroid: TSH, T3, T4

This is not exhaustive. Unsupported tests, unusual abbreviations, non-English labels, handwritten values, complex multi-column layouts and low-quality scans may not be detected correctly.

## Important safety and limitations

- **Not a medical device. Not for diagnosis, treatment or medication decisions.**
- This prototype uses text/OCR extraction and educational descriptions; it is not a validated medical AI model.
- It compares a value only when it can read a reference interval near that result. A missing interval is shown as **Needs review**.
- OCR can misread digits, decimal points, units and table columns. Always verify every extracted value against the original report.
- A laboratory's own range may depend on age, sex, pregnancy, method and other context. Even a correctly extracted range does not make this tool a clinical interpreter.
- The confidence percentage is a heuristic based on extraction pattern, not a calibrated probability of correctness.
- Use synthetic reports for hackathon demonstrations. Do not use real patient records in public demos.

## Project structure

```text
health_report_interpreter/
├── app.py
├── report_engine.py
├── requirements.txt
├── README.md
├── templates/index.html
├── static/app.js
├── static/style.css
├── sample_data/sample_report.txt
└── uploads/.gitkeep
```

## Demo for judges

1. Run the app.
2. Click **View sample health report**. The synthetic sample has five pages and multiple parameter groups.
3. Confirm the page count and detected parameter count.
4. Select parameters from different pages and inspect the source snippet and printed interval.
5. Upload a synthetic multi-page PDF to demonstrate page-by-page extraction.

## Further work before real-world use

A production system would need robust document-layout parsing, unit normalization, report-type classification, user confirmation of every extracted value, calibrated OCR confidence, reviewed translations, secure consent and retention controls, and clinical validation with qualified professionals.

## 3D-inspired interface update

This version includes a redesigned responsive healthcare dashboard with CSS-based 3D depth effects, layered glass-style cards, a dimensional medical emblem, subtle hover tilt, animated upload feedback, report-history view and expanded health-library view. The visual effects are CSS-based (not a WebGL/Three.js 3D scene), so the app remains lightweight and does not require a separate frontend build step.

The existing Flask routes (`/`, `/api/analyze`, `/api/demo`) and report extraction engine are retained. The report history is kept in the current browser page session only and is not persisted to a database. The language selector is still a placeholder; the current explanations are in English.


## MedExplain 2.0 additions

- SQLite persistence for patient workspace IDs and analysed report summaries/results (`instance/medexplain.sqlite3`).
- Medical history page that loads saved report records across server restarts.
- Secure random QR bearer tokens stored as SHA-256 hashes; generating a new token revokes the previous token. QR links show a consent confirmation before displaying report history.
- QR PNG/PDF download endpoints and browser camera scanner using the native `BarcodeDetector` API (supported browsers only).
- Health insurance comparison screen backed by clearly labelled fictional demo entries. It does not quote real premiums or recommend a real policy.
- Medicine information search with a small educational catalogue and explicit no-prescribing safety notices.
- English/Hindi/Punjabi language preference persistence and a small translated navigation subset. **Important limitation:** the underlying medical explanations and insurance/medicine content are not fully translated in this build; a reviewed translation provider/service is required for complete multilingual output. The interface warns users rather than pretending the entire app is translated.

## Updated installation

```powershell
py -m venv .venv
.venv\\Scripts\\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000` on the same computer. For QR scanning from a phone on the same Wi-Fi, open the app using the computer’s LAN IP (for example `http://192.168.x.x:5000`) and allow the port through the local firewall. The SQLite database is created automatically. Set a strong `FLASK_SECRET_KEY` environment variable before any non-local deployment. Use HTTPS for camera access on deployed sites. The QR URL is a bearer link: anyone with an active link can view the shared report history after confirming they have patient permission. Revoke access from the QR Passport screen.

## Data and safety notes

This is a demonstration application, not a certified medical device, insurer marketplace, prescription system or production patient portal. Do not upload real patient information to a public demo. Production use requires authenticated patient accounts, consent/audit logging, encryption at rest and in transit, data retention controls, security review, clinician validation and verified insurer/medicine data sources. Insurance entries are fictional demo records; medicine catalogue entries are educational and incomplete.

Run smoke checks after installation with `python smoke_test.py`.


## MedExplain 3.0 prototype additions

- **Health progress tracker:** compares the two most recent analysed reports for matching parameter names and displays numerical changes. It does not label changes as improvement because clinical interpretation depends on units, methods, reference ranges and patient context.
- **Prescription reader:** accepts a PDF or image and extracts readable text using the existing document extraction pipeline. OCR output must be checked against the original by the patient and a clinician/pharmacist. It does not generate prescriptions.
- **Medicine timer:** lets the user manually enter a schedule only after confirming the details against a doctor's prescription. It stores schedules and taken/skipped logs in SQLite. Browser notifications work only while the app/browser is running and permission is granted; they are not guaranteed alarms.
- **X-ray records:** stores uploaded X-ray image files and their metadata for later review. **No X-ray diagnosis or AI image interpretation is implemented.** A validated imaging model and radiologist oversight would be needed for that feature.

New database tables are created automatically: `prescriptions`, `medicine_schedules`, `medicine_logs`, and `xray_uploads`. Existing QR, report analysis, insurance demo and medicine-information features remain in the project.

### Medical and privacy limitations
This is a student/demo prototype, not a certified medical device. Do not use it to decide treatment or dosage. Account login, password hashing, CSRF checks and patient-workspace scoping are included in this version, but a public deployment still needs a professional security review, verified email, rate limiting, audit controls, encryption at rest, secure file access and retention/deletion policies. Uploaded X-rays are retained in the local `uploads` folder. Browser reminders may not fire if the browser is closed or the device suspends the page.


### Windows one-command setup

Open this `health_report_interpreter` folder in VS Code. In the PowerShell terminal run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\setup_and_run_windows.ps1
```

The script creates/uses this project's own `venv`, installs dependencies and starts Flask. For tests, open a second terminal in this folder and run `.env\Scripts\python.exe smoke_test.py`.


### Prescription reader: medicine-name explanations
The prescription reader displays the raw OCR text and a separate list of medicine names only when an exact generic-name phrase from its small built-in reference is present. It does not use fuzzy matching to guess a drug name. For each exact match it provides a general common-use explanation, not a patient diagnosis. The local reference is intentionally limited; brand names, abbreviations, and medicines not in the list will be marked as not identified rather than guessed. Strength, dose, timing, and duration are never inferred from OCR. A clinician/pharmacist must verify the original prescription before any medicine is taken or entered into the timer.

## Medicine timer alarm (browser-based)

The Medicine Timer now checks saved schedules every five seconds while the MedExplain page remains open, including when the user navigates to another section. At a matching local browser time it displays a medicine alarm dialog and plays a repeating buzzer generated with the Web Audio API. The dialog includes Stop and Snooze (5 minutes), and the timer section includes Enable alarm sound, Test buzzer, and a volume slider. Food instructions (before/after/with food) are saved with each schedule.

To use it:
1. Open MedExplain and visit **Medicine timer**.
2. Click **Enable alarm sound** once (browser audio autoplay restrictions require a user gesture).
3. Use **Test buzzer** to verify the sound and adjust volume.
4. Add each medicine/time as a separate schedule entry. This supports multiple medicines and multiple daily reminder times by creating multiple entries.
5. Keep the browser tab open for reminders. Browser-based alarms do not run after the browser is closed or the device is powered off.

Reminder times use the browser/device's local timezone. This is a reminder utility only; enter schedules exactly as confirmed by the prescribing clinician.


## Account login and privacy (3.2 upgrade)

- Open `/signup` to create an account, then sign in at `/login`.
- Passwords are stored using Werkzeug's password hashing, never as plain text.
- Each account is linked to its own patient workspace; existing anonymous session records are attached to the account when that browser session signs up. Existing SQLite records are preserved.
- All dashboard and `/api/*` routes require authentication. Public QR history remains accessible only through its existing high-entropy token; QR revocation remains available from the signed-in dashboard.
- Profile details and password can be changed at `/profile`.
- Password reset email requires SMTP configuration in the environment. Copy `.env.example` settings into your local environment; without SMTP, the app will display a generic confirmation but cannot deliver a reset link.
- Set a long random `FLASK_SECRET_KEY` before deployment. Set `COOKIE_SECURE=1` only behind HTTPS. Do not deploy with Flask debug mode enabled.
- CSRF tokens protect state-changing form and fetch requests.

### Windows run

```powershell
cd health_report_interpreter
python -m pip install -r requirements.txt
$env:FLASK_SECRET_KEY = "replace-with-a-long-random-secret"
python app.py
```

Then visit `http://127.0.0.1:5000/signup`.
