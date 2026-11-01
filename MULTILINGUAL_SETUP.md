# MedExplain 3.2 — Multilingual setup

This patch adds a centralized English/Hindi/Punjabi UI dictionary to the existing Flask app. It does not replace the project or alter the database schema.

## Supported UI languages

- English (`en`)
- Hindi (`hi`)
- Punjabi (`pa`)

The selector is in the existing top navigation. The selection is saved in Flask session and browser localStorage.

## Install and run (Windows PowerShell)

Run commands from the folder containing `app.py`:

```powershell
python -m pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5001`, choose हिन्दी or ਪੰਜਾਬੀ, then refresh to verify that the selection persists. Use `Ctrl+Shift+R` after applying this patch to clear stale static files.

## Translating generated medical explanations

The reviewed UI labels are translated locally from `translations/hi.json` and `translations/pa.json`. Report-specific explanatory paragraphs and the general medicine-library prose are translated only when a trusted LibreTranslate endpoint is configured. The app deliberately does not send uploaded report text, OCR text, medicine names, measured values, units, patient identifiers or dosage data to a translation service. Only generic explanatory copy is submitted.

For privacy, use a self-hosted LibreTranslate instance on a trusted network. Set these environment variables in PowerShell before starting Flask:

```powershell
$env:LIBRETRANSLATE_URL = "http://127.0.0.1:5001"
# Set only if your LibreTranslate server requires a key:
$env:LIBRETRANSLATE_API_KEY = "your-local-service-key"
python app.py
```

If the endpoint is not configured or is unavailable, the app keeps the clinical explanation text in English and shows a notice rather than presenting untranslated text as Hindi/Punjabi. Original OCR content and medicine names remain unchanged by design.

## Files changed

- `app.py` — translation dictionary endpoint, session preference, safe generic-copy translation hook, localized API responses.
- `templates/index.html` — loads the multilingual layer and removes a stray duplicate HTML fragment that was visible on the Medicine Information screen.
- `static/language.js` — central language switching and dynamic DOM translation; saves preference to Flask.
- `static/app.js` — removes the older competing language selector handler, re-localizes current report explanation copy after a language change, and localizes browser alarm title.
- `static/style.css` — Devanagari and Gurmukhi font fallbacks.
- `translations/hi.json`, `translations/pa.json` — existing reviewed dictionaries plus a translation-service fallback message.
- `smoke_test.py` — checks translation endpoints and language persistence in addition to existing application routes.

## Verification

```powershell
python -m py_compile app.py report_engine.py
python smoke_test.py
```

The smoke test requires dependencies from `requirements.txt`.
