"""Multi-page educational lab-report extraction and explanation engine.

This is a hackathon prototype, not a clinical interpretation system.
It extracts readable text page-by-page, optionally OCRs pages with little text,
then looks for supported parameter labels and their nearby result values.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# Educational descriptions only. No generic interval is treated as a clinical standard.
# Printed report ranges take precedence. If no printed range is found, status is Needs review.
PARAMETERS: dict[str, dict[str, Any]] = {
    "Hemoglobin": {
        "aliases": ["hemoglobin", "haemoglobin", "hb"],
        "units": ["g/dl", "gm/dl"],
        "organ": "Blood and bone marrow",
        "about": "Hemoglobin is the protein in red blood cells that carries oxygen around the body.",
        "low_note": "This result is below the reference interval printed on the report. A clinician can interpret it alongside symptoms and other blood counts.",
        "high_note": "This result is above the reference interval printed on the report. A clinician can interpret it alongside hydration and other health information.",
        "normal_note": "This result falls within the reference interval printed on the report. That alone does not guarantee that everything is healthy.",
        "lifestyle": "Eat a balanced diet with iron-containing foods such as lentils, beans and leafy greens. Do not start supplements without medical advice.",
    },
    "RBC Count": {
        "aliases": ["red blood cell count", "rbc count", "total rbc", "rbc"],
        "units": ["million/cumm", "10^6/ul", "10^6/µl", "mill/cumm"],
        "organ": "Blood and bone marrow",
        "about": "Red blood cells carry oxygen from the lungs to body tissues.",
        "low_note": "This result is below the report's interval. It should be interpreted with hemoglobin, hematocrit and clinical context.",
        "high_note": "This result is above the report's interval. Hydration and other factors can affect the result.",
        "normal_note": "This result falls within the report's printed interval.",
        "lifestyle": "Follow a balanced diet and discuss persistent changes with a healthcare professional.",
    },
    "Hematocrit (PCV)": {
        "aliases": ["hematocrit", "haematocrit", "packed cell volume", "pcv"],
        "units": ["%"],
        "organ": "Blood and bone marrow",
        "about": "Hematocrit, also called packed cell volume, is the proportion of blood volume made up by red blood cells.",
        "low_note": "A result below the report's interval can have several explanations and is interpreted with other blood counts.",
        "high_note": "A result above the report's interval can be influenced by hydration and other factors.",
        "normal_note": "This result falls within the report's printed interval.",
        "lifestyle": "Maintain balanced nutrition and discuss unusual or persistent results with a clinician.",
    },
    "MCV": {
        "aliases": ["mean corpuscular volume", "mcv"],
        "units": ["fl", "fL"],
        "organ": "Red blood cells",
        "about": "MCV describes the average size of red blood cells.",
        "low_note": "A lower MCV can be seen in several types of anemia; it is not diagnostic by itself.",
        "high_note": "A higher MCV can have several causes and needs interpretation with other blood results.",
        "normal_note": "This result falls within the report's printed interval.",
        "lifestyle": "Ask your clinician how this result fits with hemoglobin and other blood-count values.",
    },
    "MCH": {
        "aliases": ["mean corpuscular hemoglobin", "mch"],
        "units": ["pg"],
        "organ": "Red blood cells",
        "about": "MCH estimates the average amount of hemoglobin in each red blood cell.",
        "low_note": "A lower result can occur with some forms of anemia and should be read with MCV and hemoglobin.",
        "high_note": "A higher result should be interpreted with the rest of the blood count.",
        "normal_note": "This result falls within the report's printed interval.",
        "lifestyle": "Discuss the complete blood count with a healthcare professional.",
    },
    "MCHC": {
        "aliases": ["mean corpuscular hemoglobin concentration", "mchc"],
        "units": ["g/dl", "gm/dl"],
        "organ": "Red blood cells",
        "about": "MCHC describes the average concentration of hemoglobin inside red blood cells.",
        "low_note": "A lower result is interpreted with MCV, MCH and hemoglobin.",
        "high_note": "A higher result can have several explanations and needs clinical context.",
        "normal_note": "This result falls within the report's printed interval.",
        "lifestyle": "Use this as one part of the full blood count discussion with your clinician.",
    },
    "RDW": {
        "aliases": ["red cell distribution width", "rdw-cv", "rdw"],
        "units": ["%"],
        "organ": "Red blood cells",
        "about": "RDW describes variation in the size of red blood cells.",
        "low_note": "A lower RDW is usually interpreted with the other red-cell indices.",
        "high_note": "A higher RDW means red-cell sizes vary more; it is interpreted with other blood-count results.",
        "normal_note": "This result falls within the report's printed interval.",
        "lifestyle": "Ask how this value relates to the rest of your blood count.",
    },
    "WBC": {
        "aliases": ["total leucocyte count", "total leukocyte count", "white blood cell count", "white blood cells", "wbc"],
        "units": ["10^3/ul", "10^3/µl", "thousand/cumm", "cells/cumm"],
        "organ": "Immune system and bone marrow",
        "about": "White blood cells help the immune system respond to infections and other threats.",
        "low_note": "A lower count can have several causes and should be interpreted with symptoms and the differential count.",
        "high_note": "A higher count can occur with infection, inflammation, stress and other conditions.",
        "normal_note": "This result falls within the report's printed interval.",
        "lifestyle": "Prioritise sleep, food safety and routine preventive care. Seek clinical advice if you have fever or feel unwell.",
    },
    "Neutrophils": {
        "aliases": ["neutrophils", "neutrophil"],
        "units": ["%"],
        "organ": "Immune system",
        "about": "Neutrophils are white blood cells that help respond to many bacterial and fungal infections.",
        "low_note": "A lower percentage should be interpreted with the absolute neutrophil count and total WBC.",
        "high_note": "A higher percentage can occur for several reasons and needs the full blood-count context.",
        "normal_note": "This result falls within the report's printed interval.",
        "lifestyle": "Discuss the differential count with a clinician rather than interpreting one percentage alone.",
    },
    "Lymphocytes": {
        "aliases": ["lymphocytes", "lymphocyte"],
        "units": ["%"],
        "organ": "Immune system",
        "about": "Lymphocytes are white blood cells involved in immune responses.",
        "low_note": "A lower percentage is interpreted with the absolute lymphocyte count and total WBC.",
        "high_note": "A higher percentage can occur with different immune responses and needs context.",
        "normal_note": "This result falls within the report's printed interval.",
        "lifestyle": "Review the full differential count with a healthcare professional.",
    },
    "Eosinophils": {
        "aliases": ["eosinophils", "eosinophil"],
        "units": ["%"],
        "organ": "Immune system",
        "about": "Eosinophils are white blood cells involved in some allergic and parasite-related responses.",
        "low_note": "A lower percentage is generally interpreted in the context of the full blood count.",
        "high_note": "A higher percentage can be associated with allergies, some infections and other causes.",
        "normal_note": "This result falls within the report's printed interval.",
        "lifestyle": "Discuss persistent abnormalities or symptoms with a clinician.",
    },
    "Platelets": {
        "aliases": ["platelet count", "platelets", "platelet"],
        "units": ["10^3/ul", "10^3/µl", "thousand/cumm", "lakhs/cumm"],
        "organ": "Bone marrow and blood clotting",
        "about": "Platelets are small blood components that help form clots and stop bleeding.",
        "low_note": "A lower count can increase bleeding risk depending on the level and cause.",
        "high_note": "A higher count can be temporary or related to other conditions; follow-up may be needed.",
        "normal_note": "This result falls within the report's printed interval.",
        "lifestyle": "Discuss unusual bruising, bleeding or persistent abnormalities with a healthcare professional.",
    },
    "Fasting Glucose": {
        "aliases": ["fasting blood glucose", "fasting glucose", "glucose fasting", "fasting blood sugar", "fbs"],
        "units": ["mg/dl", "mmol/l"],
        "organ": "Pancreas and metabolism",
        "about": "Glucose is a major energy source. Insulin, made by the pancreas, helps move glucose from blood into cells.",
        "low_note": "This result is below the report's interval. Low glucose can need prompt attention, especially with sweating, shakiness, confusion or faintness.",
        "high_note": "A result above the report's interval can be associated with altered glucose regulation, but one result alone does not establish a diagnosis.",
        "normal_note": "This result falls within the report's printed interval.",
        "lifestyle": "Choose balanced, fibre-rich meals and stay active. Discuss follow-up testing with a clinician if advised.",
    },
    "Random Glucose": {
        "aliases": ["random blood sugar", "random glucose", "rbs"],
        "units": ["mg/dl", "mmol/l"],
        "organ": "Pancreas and metabolism",
        "about": "Glucose is a major energy source and its level changes with meals and other factors.",
        "low_note": "This result is below the report's interval and should be interpreted with symptoms and timing.",
        "high_note": "A higher random glucose result needs interpretation with meal timing and other clinical information.",
        "normal_note": "This result falls within the report's printed interval.",
        "lifestyle": "Discuss the result and whether any follow-up test is appropriate with a clinician.",
    },
    "Creatinine": {
        "aliases": ["serum creatinine", "creatinine"],
        "units": ["mg/dl", "µmol/l", "umol/l"],
        "organ": "Kidneys",
        "about": "Creatinine is a waste product from normal muscle activity. The kidneys filter it from the blood.",
        "low_note": "A lower value can relate to muscle mass and other factors; interpretation depends on the person.",
        "high_note": "A higher value can occur when kidney filtration is reduced, but hydration, medicines and muscle mass can affect it.",
        "normal_note": "This result falls within the report's printed interval.",
        "lifestyle": "Stay appropriately hydrated unless a clinician has advised fluid restriction. Ask about eGFR and urine tests when relevant.",
    },
    "Blood Urea": {
        "aliases": ["blood urea", "serum urea", "urea"],
        "units": ["mg/dl", "mmol/l"],
        "organ": "Kidneys and liver",
        "about": "Urea is a waste product formed when the body processes protein; the kidneys remove it from blood.",
        "low_note": "A lower result can have several explanations and is interpreted with other tests.",
        "high_note": "A higher result can be influenced by kidney function, hydration, protein intake and other factors.",
        "normal_note": "This result falls within the report's printed interval.",
        "lifestyle": "Discuss the result with creatinine, eGFR and clinical context.",
    },
    "BUN": {
        "aliases": ["blood urea nitrogen", "bun"],
        "units": ["mg/dl", "mmol/l"],
        "organ": "Kidneys",
        "about": "BUN measures nitrogen in the blood that comes from urea, a waste product of protein metabolism.",
        "low_note": "A lower result can have several explanations and is interpreted in context.",
        "high_note": "A higher result can be influenced by kidney function, hydration and other factors.",
        "normal_note": "This result falls within the report's printed interval.",
        "lifestyle": "Review it alongside creatinine and eGFR with a healthcare professional.",
    },
    "Uric Acid": {
        "aliases": ["serum uric acid", "uric acid"],
        "units": ["mg/dl", "µmol/l", "umol/l"],
        "organ": "Kidneys and metabolism",
        "about": "Uric acid is produced when the body breaks down purines and is removed mainly through the kidneys.",
        "low_note": "A lower result is interpreted with personal context and other findings.",
        "high_note": "A higher result may be associated with gout or other factors, but does not diagnose a condition by itself.",
        "normal_note": "This result falls within the report's printed interval.",
        "lifestyle": "Discuss symptoms and the result with a clinician; avoid making major diet changes based on one number.",
    },
    "eGFR": {
        "aliases": ["estimated glomerular filtration rate", "egfr", "gfr"],
        "units": ["ml/min/1.73", "ml/min"],
        "organ": "Kidneys",
        "about": "eGFR is an estimate of how well the kidneys filter blood. It is usually interpreted with urine tests and trends over time.",
        "low_note": "A lower eGFR can indicate reduced filtration, but interpretation depends on age, trends and other findings.",
        "high_note": "A higher eGFR is not usually interpreted as a problem in isolation.",
        "normal_note": "This result is within the report's printed interval; kidney assessment may still require other information.",
        "lifestyle": "Discuss kidney health, blood pressure, medicines and urine testing with a clinician.",
    },
    "Total Cholesterol": {
        "aliases": ["total cholesterol", "cholesterol total"],
        "units": ["mg/dl", "mmol/l"],
        "organ": "Liver and cardiovascular system",
        "about": "Cholesterol is a waxy substance used to build cells and hormones. The liver makes it and blood carries it.",
        "low_note": "A low total cholesterol result is interpreted with the full lipid profile and clinical context.",
        "high_note": "A higher total cholesterol result may be one factor in cardiovascular risk. LDL, HDL and other factors matter too.",
        "normal_note": "This result falls within the report's printed interval.",
        "lifestyle": "Prefer fibre-rich foods, nuts in suitable portions and regular physical activity. Discuss overall cardiovascular risk with a clinician.",
    },
    "LDL Cholesterol": {
        "aliases": ["ldl cholesterol", "ldl-c", "ldl"],
        "units": ["mg/dl", "mmol/l"],
        "organ": "Blood vessels and cardiovascular system",
        "about": "LDL particles carry cholesterol through the bloodstream. Persistently high LDL can contribute to plaque in arteries.",
        "low_note": "Lower LDL is often desirable, but targets depend on personal cardiovascular risk.",
        "high_note": "A higher LDL result can increase cardiovascular risk. The appropriate target depends on medical history and risk factors.",
        "normal_note": "This result falls within the report's printed interval.",
        "lifestyle": "Limit trans fats, choose unsaturated fats and soluble-fibre foods, and discuss an individual target with your clinician.",
    },
    "HDL Cholesterol": {
        "aliases": ["hdl cholesterol", "hdl-c", "hdl"],
        "units": ["mg/dl", "mmol/l"],
        "organ": "Liver and cardiovascular system",
        "about": "HDL participates in moving cholesterol back toward the liver for processing.",
        "low_note": "A lower HDL result can be one part of a broader cardiovascular risk picture.",
        "high_note": "This result should be interpreted with the full lipid profile and clinical context.",
        "normal_note": "This result falls within the report's printed interval.",
        "lifestyle": "Regular activity, avoiding tobacco and balanced nutrition support overall heart health.",
    },
    "Triglycerides": {
        "aliases": ["triglycerides", "triglyceride", "tg"],
        "units": ["mg/dl", "mmol/l"],
        "organ": "Liver and cardiovascular system",
        "about": "Triglycerides are a type of fat in the blood used by the body for energy.",
        "low_note": "A lower result is interpreted with the full lipid profile and clinical context.",
        "high_note": "A higher result can be influenced by meals, alcohol, metabolic health and other factors.",
        "normal_note": "This result falls within the report's printed interval.",
        "lifestyle": "Discuss fasting status and the complete lipid profile with a healthcare professional.",
    },
    "ALT (SGPT)": {
        "aliases": ["alanine aminotransferase", "sgpt", "alt"],
        "units": ["u/l", "iu/l"],
        "organ": "Liver",
        "about": "ALT is an enzyme found mainly in liver cells. Blood levels can rise when liver cells are irritated or injured.",
        "low_note": "A low ALT result is generally not concerning on its own.",
        "high_note": "An elevated ALT can have many causes, including medicines, infections or fatty liver. It is not a diagnosis by itself.",
        "normal_note": "This result falls within the report's printed interval.",
        "lifestyle": "Review medicines or supplements with a clinician. Never stop prescribed medicine on your own.",
    },
    "AST (SGOT)": {
        "aliases": ["aspartate aminotransferase", "sgot", "ast"],
        "units": ["u/l", "iu/l"],
        "organ": "Liver and muscles",
        "about": "AST is an enzyme found in the liver and several other tissues, including muscle.",
        "low_note": "A low AST result is usually interpreted with the full liver panel.",
        "high_note": "A higher AST can come from liver or other tissues and needs interpretation with other tests.",
        "normal_note": "This result falls within the report's printed interval.",
        "lifestyle": "Discuss the full liver panel and any medicines or supplements with a clinician.",
    },
    "Bilirubin Total": {
        "aliases": ["total bilirubin", "bilirubin total", "serum bilirubin", "bilirubin"],
        "units": ["mg/dl", "µmol/l", "umol/l"],
        "organ": "Liver and bile ducts",
        "about": "Bilirubin is a yellow pigment formed when red blood cells are broken down; the liver processes it.",
        "low_note": "A low result is usually interpreted in context with the other liver tests.",
        "high_note": "A higher result can have several causes and should be interpreted with direct bilirubin and other findings.",
        "normal_note": "This result falls within the report's printed interval.",
        "lifestyle": "Seek medical advice for yellowing of the eyes or skin, dark urine or other concerning symptoms.",
    },
    "Alkaline Phosphatase (ALP)": {
        "aliases": ["alkaline phosphatase", "alp"],
        "units": ["u/l", "iu/l"],
        "organ": "Liver, bile ducts and bones",
        "about": "ALP is an enzyme found mainly in the liver, bile ducts and bones.",
        "low_note": "A lower result is interpreted with age, nutrition and other clinical information.",
        "high_note": "A higher result can come from liver, bile-duct or bone-related causes.",
        "normal_note": "This result falls within the report's printed interval.",
        "lifestyle": "Discuss this value with the rest of the liver panel and your clinician.",
    },
    "Albumin": {
        "aliases": ["serum albumin", "albumin"],
        "units": ["g/dl", "gm/dl"],
        "organ": "Liver, kidneys and blood",
        "about": "Albumin is a protein made by the liver that helps keep fluid in blood vessels and transports substances.",
        "low_note": "A lower result can have multiple causes, including liver, kidney, nutrition and inflammation-related factors.",
        "high_note": "A higher result can be associated with dehydration and needs context.",
        "normal_note": "This result falls within the report's printed interval.",
        "lifestyle": "Discuss persistent changes with a clinician rather than relying on diet advice alone.",
    },
    "TSH": {
        "aliases": ["thyroid stimulating hormone", "thyrotropin", "tsh"],
        "units": ["µiu/ml", "uiu/ml", "miu/l", "µiu/l"],
        "organ": "Thyroid gland",
        "about": "TSH is a hormone from the pituitary gland that signals the thyroid to make thyroid hormones.",
        "low_note": "A result below the report's interval is interpreted with free T4, symptoms and medical context.",
        "high_note": "A result above the report's interval is interpreted with free T4, symptoms and medical context.",
        "normal_note": "This result falls within the report's printed interval.",
        "lifestyle": "Do not start or change thyroid medication based on this explanation; discuss results with a clinician.",
    },
    "T3": {
        "aliases": ["free t3", "total t3", "triiodothyronine", "t3"],
        "units": ["pg/ml", "ng/dl", "nmol/l"],
        "organ": "Thyroid gland",
        "about": "T3 is a thyroid hormone that helps regulate metabolism.",
        "low_note": "A lower result needs interpretation with TSH, T4 and clinical context.",
        "high_note": "A higher result needs interpretation with TSH, T4 and clinical context.",
        "normal_note": "This result falls within the report's printed interval.",
        "lifestyle": "Review thyroid results together with a healthcare professional.",
    },
    "T4": {
        "aliases": ["free t4", "total t4", "thyroxine", "t4"],
        "units": ["ng/dl", "µg/dl", "ug/dl", "pmol/l"],
        "organ": "Thyroid gland",
        "about": "T4 is a thyroid hormone that helps regulate metabolism and can be converted into T3.",
        "low_note": "A lower result needs interpretation with TSH, T3 and clinical context.",
        "high_note": "A higher result needs interpretation with TSH, T3 and clinical context.",
        "normal_note": "This result falls within the report's printed interval.",
        "lifestyle": "Review thyroid results together with a healthcare professional.",
    },
}

# Longest aliases first prevents a short label (e.g. "alt") matching inside a longer label.
ALIAS_LOOKUP = sorted(
    [(alias.lower(), name) for name, info in PARAMETERS.items() for alias in info["aliases"]],
    key=lambda item: len(item[0]),
    reverse=True,
)
NUMBER_RE = re.compile(r"(?<![A-Za-z])[-+]?\d+(?:[.,]\d+)?")
RANGE_RE = re.compile(r"[-+]?\d+(?:[.,]\d+)?\s*(?:-|–|to)\s*[-+]?\d+(?:[.,]\d+)?", re.I)


def _clean_number(raw: str) -> float | None:
    try:
        return float(raw.replace(",", "."))
    except (TypeError, ValueError):
        return None


def extract_document(path: Path) -> dict[str, Any]:
    """Extract every page, OCRing only pages with little/no embedded text."""
    suffix = path.suffix.lower()
    pages: list[str] = []
    ocr_pages: list[int] = []
    if suffix == ".pdf":
        try:
            import fitz
        except ImportError as exc:
            raise RuntimeError("PDF support is missing. Run: pip install -r requirements.txt") from exc
        with fitz.open(path) as doc:
            if len(doc) > 100:
                raise RuntimeError("This prototype accepts PDFs up to 100 pages. Please split this document.")
            for index, page in enumerate(doc, start=1):
                page_text = page.get_text("text", sort=True) or ""
                # Mixed PDFs often contain both digital and scanned pages.
                if len(re.sub(r"\s+", "", page_text)) < 35:
                    try:
                        import io
                        import pytesseract
                        from PIL import Image
                        pix = page.get_pixmap(matrix=fitz.Matrix(2.2, 2.2), alpha=False)
                        image = Image.open(io.BytesIO(pix.tobytes("png")))
                        ocr_text = pytesseract.image_to_string(image, config="--psm 6")
                        if len(ocr_text.strip()) > len(page_text.strip()):
                            page_text = ocr_text
                            ocr_pages.append(index)
                    except Exception:
                        # Keep embedded text, if any. The UI reports pages processed.
                        pass
                pages.append(page_text)
    else:
        try:
            from PIL import Image
            import pytesseract
            page_text = pytesseract.image_to_string(Image.open(path), config="--psm 6")
            pages.append(page_text)
            ocr_pages.append(1)
        except ImportError as exc:
            raise RuntimeError("Image OCR requires Pillow and Tesseract. Install Tesseract and run pip install -r requirements.txt.") from exc
        except Exception as exc:
            raise RuntimeError("Could not read this image. Try a clearer PNG or JPG file.") from exc

    combined = "\n".join(f"\n[[PAGE:{i}]]\n{text}" for i, text in enumerate(pages, start=1))
    return {
        "text": combined,
        "page_count": len(pages),
        "pages_with_ocr": ocr_pages,
        "pages_with_text": [i for i, p in enumerate(pages, start=1) if p.strip()],
    }




def extract_prescription_text(path: Path) -> str:
    """Extract prescription text using several OCR-friendly image variants.

    Tesseract is designed mainly for printed text. Multiple preprocessing passes
    improve scans/photos, but cannot reliably decode poor or handwritten writing.
    """
    import os
    import shutil

    def configure_tesseract():
        try:
            import pytesseract
        except ImportError as exc:
            raise RuntimeError("Prescription OCR Python package is missing. Run the setup script again.") from exc
        candidates = [
            shutil.which("tesseract"),
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            str(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/Tesseract-OCR/tesseract.exe"),
        ]
        for candidate in candidates:
            if candidate and Path(candidate).is_file():
                pytesseract.pytesseract.tesseract_cmd = candidate
                return pytesseract
        raise RuntimeError(
            "Tesseract OCR is not installed or not on PATH. Install Tesseract OCR, restart the terminal, "
            "and restart MedExplain."
        )

    pytesseract = configure_tesseract()

    def ocr_score(data):
        words = [str(w).strip() for w in data.get("text", []) if str(w).strip()]
        confidences = []
        for value, word in zip(data.get("conf", []), data.get("text", [])):
            if str(word).strip():
                try:
                    score = float(value)
                    if score >= 0:
                        confidences.append(score)
                except (TypeError, ValueError):
                    pass
        if not words or not confidences:
            return -1.0
        # Confidence is more useful than simply selecting the longest OCR output.
        avg_conf = sum(confidences) / len(confidences)
        useful = sum(any(ch.isalpha() for ch in w) for w in words)
        return avg_conf + min(useful, 30) * 0.35

    def read_image(image):
        from PIL import Image, ImageOps, ImageEnhance, ImageFilter
        image = ImageOps.exif_transpose(image)
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        # Avoid excessive memory use while keeping enough detail for small writing.
        if image.width < 2200:
            scale = min(3, max(2, int(2200 / max(image.width, 1))))
            image = image.resize((image.width * scale, image.height * scale), Image.Resampling.LANCZOS)
        gray = ImageOps.grayscale(image)
        gray = ImageOps.autocontrast(gray, cutoff=1)
        variants = [
            gray,
            ImageEnhance.Contrast(gray).enhance(1.8).filter(ImageFilter.SHARPEN),
            gray.filter(ImageFilter.MedianFilter(size=3)).filter(ImageFilter.SHARPEN),
            gray.point(lambda px: 255 if px > 165 else 0),
            gray.point(lambda px: 255 if px > 190 else 0),
        ]
        # Adaptive thresholding can help unevenly lit phone photos; optional dependency.
        try:
            import cv2
            import numpy as np
            arr = np.array(gray)
            adaptive = cv2.adaptiveThreshold(arr, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                             cv2.THRESH_BINARY, 31, 11)
            variants.append(Image.fromarray(adaptive))
        except Exception:
            pass

        best_text, best_score = "", -1.0
        for variant in variants:
            for psm in (6, 11, 4, 3):
                config = f"--oem 3 --psm {psm}"
                try:
                    data = pytesseract.image_to_data(
                        variant, config=config, output_type=pytesseract.Output.DICT
                    )
                    score = ocr_score(data)
                    text = pytesseract.image_to_string(variant, config=config).strip()
                    if text and score > best_score:
                        best_text, best_score = text, score
                except Exception:
                    continue
        return best_text

    suffix = path.suffix.lower()
    pages = []
    if suffix == ".pdf":
        try:
            import fitz
        except ImportError as exc:
            raise RuntimeError("PDF support is missing. Run the setup script again.") from exc
        with fitz.open(path) as doc:
            if len(doc) > 30:
                raise RuntimeError("Please upload a prescription PDF with 30 pages or fewer.")
            for page in doc:
                embedded = page.get_text("text", sort=True) or ""
                if len(re.sub(r"\s+", "", embedded)) >= 20:
                    pages.append(embedded)
                else:
                    import io
                    from PIL import Image
                    pix = page.get_pixmap(matrix=fitz.Matrix(3, 3), alpha=False)
                    pages.append(read_image(Image.open(io.BytesIO(pix.tobytes("png")))))
    else:
        from PIL import Image
        with Image.open(path) as image:
            pages.append(read_image(image.copy()))

    result = "\n\n".join(page.strip() for page in pages if page.strip()).strip()
    if not result:
        raise RuntimeError(
            "No readable text found. Upload a sharp, straight, well-lit photo or a scanned PDF. "
            "Handwritten medicine names and dosage instructions may need manual confirmation."
        )
    return result


def extract_text(path: Path) -> str:
    """Backward-compatible helper."""
    return extract_document(path)["text"]


def _page_lines(text: str) -> list[tuple[int, str]]:
    page = 1
    output: list[tuple[int, str]] = []
    for raw in text.splitlines():
        marker = re.search(r"\[\[PAGE:(\d+)\]\]", raw)
        if marker:
            page = int(marker.group(1))
            continue
        line = re.sub(r"\s+", " ", raw).strip(" \t|")
        if line:
            output.append((page, line))
    return output


def _normalise_label_text(value: str) -> str:
    value = value.lower().replace("haemoglobin", "hemoglobin")
    value = value.replace("µ", "u").replace("μ", "u")
    return re.sub(r"[^a-z0-9%]+", " ", value).strip()


def _find_alias(line: str) -> tuple[str, str] | None:
    norm = _normalise_label_text(line)
    # Match aliases as whole words after normalisation.
    for alias, name in ALIAS_LOOKUP:
        a = _normalise_label_text(alias)
        if not a:
            continue
        if re.search(r"(?<![a-z0-9])" + re.escape(a) + r"(?![a-z0-9])", norm):
            return alias, name
    return None


def _parse_range(candidate_lines: list[str]) -> tuple[float | None, float | None]:
    for line in candidate_lines:
        # Ignore ranges that look like dates.
        for match in RANGE_RE.finditer(line):
            left, right = re.split(r"\s*(?:-|–|to)\s*", match.group(), maxsplit=1, flags=re.I)
            lo, hi = _clean_number(left), _clean_number(right)
            if lo is not None and hi is not None and lo <= hi:
                return lo, hi
    return None, None


def _candidate_value(lines: list[str], start: int, info: dict[str, Any]) -> tuple[float | None, str, float]:
    """Find a result near a label, preferring a number followed by a recognised unit."""
    window = [lines[i] for i in range(start, min(len(lines), start + 4))]
    joined = " | ".join(window)
    # First remove the parameter label from its own line, so digits in label names aren't used.
    first = window[0]
    alias_match = _find_alias(first)
    if alias_match:
        alias, _ = alias_match
        first_norm = first.lower()
        pos = first_norm.find(alias.lower())
        if pos >= 0:
            window[0] = first[:pos] + " " + first[pos + len(alias):]
    joined = " | ".join(window)
    # Try explicit result + unit first. Units are intentionally broad and not converted.
    for unit in sorted(info.get("units", []), key=len, reverse=True):
        pattern = re.compile(r"([-+]?\d+(?:[.,]\d+)?)\s*" + re.escape(unit) + r"\b", re.I)
        match = pattern.search(joined)
        if match:
            value = _clean_number(match.group(1))
            if value is not None:
                return value, joined[:180], 0.92
    # Next try a result separated from its label by spaces, colon, tabs or table separators.
    # Avoid grabbing the two endpoints of a printed reference interval.
    for line in window:
        stripped = line
        range_match = RANGE_RE.search(stripped)
        if range_match:
            stripped = stripped[:range_match.start()] + " " + stripped[range_match.end():]
        nums = NUMBER_RE.findall(stripped)
        if nums:
            # If line contains a parameter label and numeric data, the first number is usually result.
            for token in nums:
                value = _clean_number(token)
                if value is not None:
                    return value, joined[:180], 0.72
    # Handles a layout where value is printed immediately before the parameter label.
    for line in window[:2]:
        match = re.search(r"([-+]?\d+(?:[.,]\d+)?)\s+" + r".{0,30}$", line)
        if match:
            value = _clean_number(match.group(1))
            if value is not None:
                return value, joined[:180], 0.55
    return None, joined[:180], 0.0


def analyze_report(text: str, page_count: int | None = None, pages_with_ocr: list[int] | None = None) -> dict[str, Any]:
    lines = _page_lines(text)
    found: dict[str, dict[str, Any]] = {}

    # Find all label occurrences, not just the first matching line in the whole PDF.
    for idx, (page, line) in enumerate(lines):
        found_alias = _find_alias(line)
        if not found_alias:
            continue
        _, name = found_alias
        info = PARAMETERS[name]
        nearby = [x[1] for x in lines[idx:min(len(lines), idx + 4)] if x[0] == page]
        if not nearby:
            continue
        value, snippet, confidence = _candidate_value(nearby, 0, info)
        if value is None:
            continue
        # Printed range can be on the same row or in the next few lines.
        low, high = _parse_range(nearby)
        # Deduplicate repeated headers/summary copies. Prefer higher-confidence occurrence.
        existing = found.get(name)
        if existing is None or confidence > existing["confidence"]:
            found[name] = {
                "name": name, "value": value, "unit": _detect_unit(snippet, info),
                "status": "Needs review", "organ": info["organ"], "about": info["about"],
                "explanation": "A result was extracted, but no reliable laboratory reference interval was detected. Check the original report before interpreting it.",
                "lifestyle": info["lifestyle"], "low": low, "high": high,
                "page": page, "confidence": confidence, "source_text": snippet,
            }
        elif existing.get("low") is None and low is not None:
            existing["low"], existing["high"] = low, high

    results = []
    for name, result in found.items():
        info = PARAMETERS[name]
        low, high = result["low"], result["high"]
        if low is not None and high is not None:
            if result["value"] < low:
                result["status"] = "Below lab range"
                result["explanation"] = info["low_note"]
            elif result["value"] > high:
                result["status"] = "Above lab range"
                result["explanation"] = info["high_note"]
            else:
                result["status"] = "Within lab range"
                result["explanation"] = info["normal_note"]
        results.append(result)

    # Stable, familiar order as in the parameter catalogue.
    order = {name: i for i, name in enumerate(PARAMETERS)}
    results.sort(key=lambda x: (x["page"], order.get(x["name"], 999)))
    reviewed = sum(1 for x in results if x["status"] in ("Below lab range", "Above lab range"))
    normal = sum(1 for x in results if x["status"] == "Within lab range")
    needs_review = sum(1 for x in results if x["status"] == "Needs review")
    return {
        "summary": {
            "total": len(results), "flagged": reviewed, "normal": normal,
            "needs_review": needs_review, "pages_scanned": page_count or max([p for p, _ in lines], default=1),
        },
        "results": results,
        "notice": "Educational prototype only — not a diagnosis or treatment recommendation. Results are compared only when a reference interval is successfully read from the report. OCR and extraction can make mistakes; verify every value, unit and interval against the original report and consult a qualified clinician.",
        "pages_with_ocr": pages_with_ocr or [],
    }


def _detect_unit(snippet: str, info: dict[str, Any]) -> str:
    lower = snippet.lower()
    for unit in sorted(info.get("units", []), key=len, reverse=True):
        if unit.lower() in lower:
            return unit
    return "Unit not detected"
