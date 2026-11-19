"""Targeted second-pass checks for uncertain or anomalous extracted fields."""
from __future__ import annotations

import re

from backend.agents.classifier import _vision_json
from backend.agents.extractor import EXTRACTION_SCHEMA
from backend.config import vision_configured
from backend.schemas import Discrepancy, PageExtraction, PageRecord


class ReflectionAgent:
    def run(self, pages: list[PageRecord], findings: list[Discrepancy]) -> list[str]:
        notes: list[str] = []
        finding_pages = {page_id for finding in findings for page_id in finding.page_ids}
        findings_by_page = {
            page_id: [finding for finding in findings if page_id in finding.page_ids]
            for page_id in finding_pages
        }
        for page in pages:
            if page.page_id not in finding_pages and page.extraction.confidence >= 0.45:
                continue
            page_findings = findings_by_page.get(page.page_id, [])
            if vision_configured() and page.image_base64 and page_findings:
                context = "; ".join(f"{finding.title}: {finding.detail}" for finding in page_findings)
                try:
                    result = _vision_json(
                        "Perform a targeted second visual read of this specific claim document page. "
                        f"Recheck only the evidence relevant to these findings: {context}. "
                        "Return the structured extraction, use null for fields that cannot be read, "
                        "and do not infer what a corrected value should be.",
                        page.image_base64,
                        page.mime_type,
                        EXTRACTION_SCHEMA,
                    )
                    candidate = PageExtraction.model_validate(result)
                    if candidate.confidence >= 0.65:
                        previous = page.extraction
                        candidate_data = previous.model_dump()
                        for field, value in candidate.model_dump().items():
                            if value is not None and value != [] and field != "extraction_notes":
                                candidate_data[field] = value
                        candidate_data["confidence"] = candidate.confidence
                        page.extraction = PageExtraction.model_validate(candidate_data)
                        notes.append(
                            f"{page.filename} page {page.page_number}: targeted vision re-read completed "
                            f"for {', '.join(sorted({finding.category for finding in page_findings}))}; "
                            "verification was recalculated from the second read."
                        )
                    else:
                        notes.append(
                            f"{page.filename} page {page.page_number}: targeted vision re-read was low confidence; "
                            "the original extraction was retained."
                        )
                except Exception as exc:
                    notes.append(
                        f"{page.filename} page {page.page_number}: targeted vision re-read failed "
                        f"({type(exc).__name__}); the original extraction was retained."
                    )
                continue
            if not page.text.strip():
                notes.append(
                    f"{page.filename} page {page.page_number}: no embedded text is available for targeted local re-read; "
                    "a vision-enabled run or a clearer/text-searchable copy is needed."
                )
                continue
            # Recheck the exact printed total from selectable PDF text. This
            # can corroborate an OCR/LLM amount without inventing a correction.
            amount_matches = re.findall(
                r"(?:Grand Total|Total Amount|Amount Payable|Stated Total)\s*[:\-]?\s*(?:₹|INR\s*)?([\d,]+(?:\.\d{1,2})?)",
                page.text, re.I,
            )
            if amount_matches:
                notes.append(
                    f"{page.filename} page {page.page_number}: targeted text re-read confirmed printed total "
                    f"{amount_matches[-1]}."
                )
            elif page.page_id in finding_pages:
                notes.append(
                    f"{page.filename} page {page.page_number}: anomaly retained; a second independent printed value "
                    "was not available to confirm it."
                )
        return notes
