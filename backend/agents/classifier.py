"""Page classification and document legibility agent."""
from __future__ import annotations

import json
import re
from typing import Any

from backend.config import (
    GEMINI_API_KEY, GEMINI_MODEL, LLM_PROVIDER, OPENAI_API_KEY, OPENAI_MODEL, vision_configured,
)
from backend.schemas import PageRecord


CLASSIFIER_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "document_type": {"type": "STRING", "enum": [
            "GOVERNMENT_ID", "INSURANCE_CARD_OR_POLICY", "POLICY_SCHEDULE",
            "DISCHARGE_SUMMARY", "ITEMIZED_HOSPITAL_BILL",
            "PHARMACY_BILL_AND_PRESCRIPTION", "DIAGNOSTIC_LAB_REPORT",
            "UNKNOWN_OR_UNREADABLE",
        ]},
        "quality": {"type": "STRING", "enum": ["HIGH", "MEDIUM", "BLURRY_RESCAN_NEEDED"]},
        "page_summary": {"type": "STRING"},
    },
    "required": ["document_type", "quality", "page_summary"],
}


def _vision_json(prompt: str, image_b64: str, mime_type: str, schema: dict[str, Any]) -> dict[str, Any]:
    if LLM_PROVIDER == "gemini":
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=GEMINI_API_KEY)
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[prompt, types.Part.from_bytes(data=__import__("base64").b64decode(image_b64), mime_type=mime_type)],
            config={"response_mime_type": "application/json", "response_schema": schema},
        )
        if getattr(response, "parsed", None) is not None:
            parsed = response.parsed
            return parsed.model_dump() if hasattr(parsed, "model_dump") else dict(parsed)
        return json.loads(response.text or "{}")

    from openai import OpenAI

    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": [
            {"type": "text", "text": prompt + " Return one valid JSON object matching the requested fields."},
            {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{image_b64}"}},
        ]}],
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content
    if not content:
        raise ValueError("OpenAI returned an empty structured response.")
    return json.loads(content)


def _local_type(text: str, filename: str) -> tuple[str, str]:
    haystack = f"{filename} {text}".lower()
    rules = [
        ("POLICY_SCHEDULE", ("policy schedule", "coverage schedule", "sum insured")),
        ("GOVERNMENT_ID", ("aadhaar", "government of india", "identity card", "date of birth", "pan card")),
        ("INSURANCE_CARD_OR_POLICY", ("insurance card", "tpa", "health insurance", "member id", "policy no")),
        ("ITEMIZED_HOSPITAL_BILL", ("itemized bill", "hospital bill", "bill no", "amount payable", "grand total")),
        ("PHARMACY_BILL_AND_PRESCRIPTION", ("prescription", "prescribed medicines", "doctor reg", "pharmacy")),
        ("DISCHARGE_SUMMARY", ("discharge summary", "date of admission", "date of discharge")),
        ("DIAGNOSTIC_LAB_REPORT", ("laboratory", "lab report", "test result", "diagnostic")),
    ]
    for kind, terms in rules:
        if any(re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", haystack) for term in terms):
            return kind, f"Local text/filename match for {kind.replace('_', ' ').lower()}."
    if len(re.sub(r"\s+", "", text)) < 12:
        return "UNKNOWN_OR_UNREADABLE", "No readable page text was available to the local classifier."
    return "UNKNOWN_OR_UNREADABLE", "Readable content did not match a supported document type."


class PageClassifierAgent:
    def classify(self, page: PageRecord) -> tuple[PageRecord, str]:
        if vision_configured() and page.image_base64:
            try:
                result = _vision_json(
                    "Classify this health insurance claim document page. Return the document_type, "
                    "legibility quality, and a concise page_summary. Do not infer missing content.",
                    page.image_base64,
                    page.mime_type,
                    CLASSIFIER_SCHEMA,
                )
                page.document_type = result["document_type"]
                page.quality = result["quality"]
                page.page_summary = result["page_summary"]
                return page, "Vision classification completed."
            except Exception as exc:
                kind, summary = _local_type(page.text, page.filename)
                page.document_type = kind
                page.page_summary = summary
                return page, f"Vision service unavailable; local classification used ({type(exc).__name__})."
        kind, summary = _local_type(page.text, page.filename)
        page.document_type = kind
        page.page_summary = summary
        return page, "Local classifier used (configure GEMINI_API_KEY for multimodal vision)."
