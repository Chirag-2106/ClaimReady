"""Structured field extraction tailored to classified document types."""
from __future__ import annotations

import re
from typing import Any

from backend.agents.classifier import _vision_json
from backend.config import vision_configured
from backend.schemas import LineItem, PageExtraction, PageRecord


EXTRACTION_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "patient_name": {"type": "STRING", "nullable": True},
        "dob": {"type": "STRING", "nullable": True},
        "gender": {"type": "STRING", "nullable": True},
        "id_number": {"type": "STRING", "nullable": True},
        "insurer_name": {"type": "STRING", "nullable": True},
        "policy_number": {"type": "STRING", "nullable": True},
        "tpa_id": {"type": "STRING", "nullable": True},
        "policy_valid_from": {"type": "STRING", "nullable": True},
        "policy_valid_to": {"type": "STRING", "nullable": True},
        "hospital_name": {"type": "STRING", "nullable": True},
        "admission_date": {"type": "STRING", "nullable": True},
        "discharge_date": {"type": "STRING", "nullable": True},
        "service_dates": {"type": "ARRAY", "items": {"type": "STRING"}},
        "line_items": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "description": {"type": "STRING"},
            "quantity": {"type": "NUMBER", "nullable": True},
            "unit_price": {"type": "NUMBER", "nullable": True},
            "amount": {"type": "NUMBER", "nullable": True},
        }, "required": ["description"]}},
        "subtotal": {"type": "NUMBER", "nullable": True},
        "taxes": {"type": "NUMBER", "nullable": True},
        "discounts": {"type": "NUMBER", "nullable": True},
        "stated_total_amount": {"type": "NUMBER", "nullable": True},
        "doctor_name": {"type": "STRING", "nullable": True},
        "doctor_reg_no": {"type": "STRING", "nullable": True},
        "diagnosis": {"type": "STRING", "nullable": True},
        "prescribed_medicines": {"type": "ARRAY", "items": {"type": "STRING"}},
        "confidence": {"type": "NUMBER"},
        "extraction_notes": {"type": "ARRAY", "items": {"type": "STRING"}},
    },
}


def _amount(text: str, labels: tuple[str, ...]) -> float | None:
    for label in labels:
        match = re.search(rf"{label}\s*[:\-]?\s*(?:₹|INR\s*)?([\d,]+(?:\.\d{{1,2}})?)", text, re.I)
        if match:
            try:
                return float(match.group(1).replace(",", ""))
            except ValueError:
                return None
    return None


def _field(text: str, labels: tuple[str, ...]) -> str | None:
    for label in labels:
        match = re.search(rf"^{label}\s*(?:[:\-]\s*|\n\s*)([^\n]+)\s*$", text, re.I | re.M)
        if match:
            return match.group(1).strip()
    return None


def _local_extract(page: PageRecord) -> PageExtraction:
    text = page.text
    result = PageExtraction()
    result.patient_name = _field(text, ("Patient(?: Name)?", "Name of Patient", "Member Name"))
    result.dob = _field(text, ("DOB", "Date of Birth"))
    result.gender = _field(text, ("Gender", "Sex"))
    result.id_number = _field(text, ("ID Number", "Aadhaar Number", "Member ID"))
    result.insurer_name = _field(text, ("Insurer", "Insurance Company"))
    result.policy_number = _field(text, ("Policy Number", "Policy No", "Policy No\\."))
    result.tpa_id = _field(text, ("TPA ID", "TPA"))
    validity = _field(text, ("Coverage Period", "Policy Validity", "Policy Period"))
    if validity:
        dates = re.findall(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{4}\b|\b\d{4}-\d{2}-\d{2}\b", validity)
        if dates:
            result.policy_valid_from = dates[0]
        if len(dates) > 1:
            result.policy_valid_to = dates[1]
    result.hospital_name = _field(text, ("Hospital", "Hospital Name"))
    result.admission_date = _field(text, ("Admission Date", "Date of Admission"))
    result.discharge_date = _field(text, ("Discharge Date", "Date of Discharge"))
    result.doctor_name = _field(text, ("Doctor", "Treating Doctor", "Dr\\."))
    result.doctor_reg_no = _field(text, ("Doctor Reg(?:istration)? No", "Reg No"))
    result.diagnosis = _field(text, ("Diagnosis", "Provisional Diagnosis"))
    date_values = re.findall(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{4}\b|\b\d{4}-\d{2}-\d{2}\b", text)
    excluded_dates = {
        result.dob, result.admission_date, result.discharge_date,
        result.policy_valid_from, result.policy_valid_to,
    }
    result.service_dates = list(dict.fromkeys(value for value in date_values if value not in excluded_dates))
    result.subtotal = _amount(text, ("Subtotal", "Sub Total"))
    result.taxes = _amount(text, ("Tax(?:es)?", "GST"))
    result.discounts = _amount(text, ("Discount(?:s)?",))
    result.stated_total_amount = _amount(text, ("Grand Total", "Total Amount", "Amount Payable", "Stated Total"))

    lines = [line.strip() for line in text.splitlines()]
    for index in range(max(0, len(lines) - 3)):
        description, quantity, unit_price, amount = lines[index:index + 4]
        if not description or not re.fullmatch(r"\d+(?:\.\d+)?", quantity):
            continue
        amount_pattern = r"(?:₹|INR\s*)?([\d,]+(?:\.\d{1,2})?)"
        unit_match = re.fullmatch(amount_pattern, unit_price, re.I)
        amount_match = re.fullmatch(amount_pattern, amount, re.I)
        if unit_match and amount_match:
            result.line_items.append(LineItem(
                description=description,
                quantity=float(quantity),
                unit_price=float(unit_match.group(1).replace(",", "")),
                amount=float(amount_match.group(1).replace(",", "")),
            ))
    meds = _field(text, ("Medicines", "Prescribed Medicines"))
    if meds:
        result.prescribed_medicines = [item.strip() for item in re.split(r"[,;]", meds) if item.strip()]
    result.confidence = 0.88 if text.strip() else 0.15
    if not text.strip():
        result.extraction_notes.append("No embedded text is available; configure Gemini for image-based extraction.")
    return result


class DocumentExtractorAgent:
    def extract(self, page: PageRecord) -> tuple[PageRecord, str]:
        if vision_configured() and page.image_base64:
            try:
                prompt = (
                    f"Extract fields from this {page.document_type} page. Return only the specified JSON. "
                    "Use null when a field is absent, do not calculate or invent totals, and include every "
                    "visible bill line item with its printed quantity, unit price, and amount. "
                    "Dates should remain in their printed form."
                )
                result = _vision_json(prompt, page.image_base64, page.mime_type, EXTRACTION_SCHEMA)
                page.extraction = PageExtraction.model_validate(result)
                return page, "Targeted vision extraction completed."
            except Exception as exc:
                page.extraction = _local_extract(page)
                page.extraction.extraction_notes.append(
                    f"Vision extraction unavailable; local parser used ({type(exc).__name__})."
                )
                return page, "Vision extraction failed; local text parser used."
        page.extraction = _local_extract(page)
        return page, "Local structured extraction completed."
