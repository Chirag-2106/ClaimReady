"""Application configuration and insurer checklist defaults."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o").strip()
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").strip().lower()
if LLM_PROVIDER not in {"gemini", "openai"}:
    raise ValueError("LLM_PROVIDER must be 'gemini' or 'openai'.")
USE_VISION_LLM = os.getenv("USE_VISION_LLM", "true").lower() in {"1", "true", "yes"}
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "20"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024


def vision_configured() -> bool:
    key_present = GEMINI_API_KEY if LLM_PROVIDER == "gemini" else OPENAI_API_KEY
    return USE_VISION_LLM and bool(key_present)

# A schedule is distinct from an insurance/TPA card. The demo packet
# intentionally omits it to show how a missing mandatory item is surfaced.
INSURER_CHECKLIST: dict[str, list[dict[str, str]]] = {
    "standard": [
        {"id": "government_id", "label": "Government-issued patient ID", "doc_type": "GOVERNMENT_ID"},
        {"id": "insurance_card", "label": "Insurance / TPA card", "doc_type": "INSURANCE_CARD_OR_POLICY"},
        {"id": "policy_schedule", "label": "Policy schedule / coverage page", "doc_type": "POLICY_SCHEDULE"},
        {"id": "discharge_summary", "label": "Hospital discharge summary", "doc_type": "DISCHARGE_SUMMARY"},
        {"id": "itemized_bill", "label": "Itemized final hospital bill", "doc_type": "ITEMIZED_HOSPITAL_BILL"},
        {"id": "prescription", "label": "Doctor prescription / pharmacy record", "doc_type": "PHARMACY_BILL_AND_PRESCRIPTION"},
    ]
}

ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}
