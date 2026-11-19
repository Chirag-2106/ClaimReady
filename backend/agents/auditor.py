"""Checklist completeness and deterministic cross-verification auditors."""
from __future__ import annotations

from backend.config import INSURER_CHECKLIST
from backend.schemas import ArithmeticAudit, ChecklistItem, Discrepancy, PageRecord
from backend.utils.math_audit import money, name_similarity, parse_date


class ChecklistAgent:
    def run(self, pages: list[PageRecord], checklist_name: str = "standard") -> list[ChecklistItem]:
        rules = INSURER_CHECKLIST.get(checklist_name, INSURER_CHECKLIST["standard"])
        items: list[ChecklistItem] = []
        for rule in rules:
            matches = [p for p in pages if p.document_type == rule["doc_type"]]
            if not matches:
                items.append(ChecklistItem(
                    id=rule["id"], label=rule["label"], status="MISSING",
                    detail="No uploaded page was classified as this required document.",
                ))
            elif any(p.quality == "BLURRY_RESCAN_NEEDED" for p in matches):
                items.append(ChecklistItem(
                    id=rule["id"], label=rule["label"], status="LOW_LEGIBILITY",
                    detail="At least one matching page needs a clearer scan.",
                    page_ids=[p.page_id for p in matches],
                ))
            else:
                items.append(ChecklistItem(
                    id=rule["id"], label=rule["label"], status="PRESENT",
                    detail=f"Found {len(matches)} matching page(s).",
                    page_ids=[p.page_id for p in matches],
                ))
        unknown = [p for p in pages if p.document_type == "UNKNOWN_OR_UNREADABLE"]
        items.extend(ChecklistItem(
            id=f"unsupported-{i}", label=f"Unrecognized document: {p.filename} (page {p.page_number})",
            status="UNSUPPORTED", detail=p.page_summary or "The page could not be classified.",
            page_ids=[p.page_id], required=False,
        ) for i, p in enumerate(unknown, 1))
        return items


class VerificationAgent:
    def run(self, pages: list[PageRecord]) -> tuple[list[Discrepancy], list[ArithmeticAudit]]:
        findings: list[Discrepancy] = []
        audits: list[ArithmeticAudit] = []
        bill_pages = [p for p in pages if p.document_type == "ITEMIZED_HOSPITAL_BILL"]
        for page in bill_pages:
            extraction = page.extraction
            known_amounts = [row.amount for row in extraction.line_items if row.amount is not None]
            itemized_sum = sum(known_amounts) if known_amounts else None
            base = extraction.subtotal if extraction.subtotal is not None else itemized_sum
            calculated = None
            if base is not None and (extraction.taxes is not None or extraction.discounts is not None):
                calculated = base + (extraction.taxes or 0) - (extraction.discounts or 0)
            elif base is not None:
                calculated = base
            detail = "Bill does not contain enough structured amounts for a full arithmetic audit."
            status = "INCOMPLETE"
            difference = None
            if extraction.line_items and extraction.subtotal is not None and itemized_sum is not None:
                if abs(itemized_sum - extraction.subtotal) > 0.01:
                    findings.append(Discrepancy(
                        category="ARITHMETIC", severity="CRITICAL",
                        title="Bill line items do not match subtotal",
                        detail=f"Line items sum to {money(itemized_sum)} but the printed subtotal is {money(extraction.subtotal)}.",
                        page_ids=[page.page_id],
                    ))
                    status = "MISMATCH"
            elif not extraction.line_items:
                detail = "No itemized rows could be read; subtotal/total comparison is shown if available."
            if extraction.stated_total_amount is not None and calculated is not None:
                difference = round(extraction.stated_total_amount - calculated, 2)
                if abs(difference) > 0.01:
                    detail = (
                        f"Calculated total is {money(calculated)}; printed total is "
                        f"{money(extraction.stated_total_amount)} (difference {money(difference)})."
                    )
                    findings.append(Discrepancy(
                        category="ARITHMETIC", severity="CRITICAL",
                        title="Printed bill total does not reconcile",
                        detail=detail,
                        page_ids=[page.page_id],
                    ))
                    status = "MISMATCH"
                else:
                    detail = "Printed total reconciles with the available bill amounts."
                    status = "PASS" if status != "MISMATCH" else status
            elif status == "MISMATCH":
                detail = "Line-item subtotal mismatch detected."
            audits.append(ArithmeticAudit(
                page_id=page.page_id, filename=page.filename, itemized_sum=itemized_sum,
                subtotal=extraction.subtotal, taxes=extraction.taxes, discounts=extraction.discounts,
                calculated_total=calculated, stated_total=extraction.stated_total_amount,
                discrepancy=difference, status=status, detail=detail,
            ))

        named = [(p, p.extraction.patient_name) for p in pages if p.extraction.patient_name]
        if len(named) > 1:
            anchor_page, anchor_name = named[0]
            for page, patient_name in named[1:]:
                similarity = name_similarity(anchor_name, patient_name)
                if similarity < 0.70:
                    findings.append(Discrepancy(
                        category="IDENTITY", severity="CRITICAL",
                        title="Patient name differs across documents",
                        detail=f"{anchor_name!r} on {anchor_page.filename} differs from {patient_name!r} on {page.filename}.",
                        page_ids=[anchor_page.page_id, page.page_id],
                    ))
                elif similarity < 0.90:
                    findings.append(Discrepancy(
                        category="IDENTITY", severity="WARNING",
                        title="Patient name uses a shortened or variant form",
                        detail=f"Compare {anchor_name!r} with {patient_name!r} and confirm they refer to the same patient.",
                        page_ids=[anchor_page.page_id, page.page_id],
                    ))

        policy_pages = [(p, p.extraction.policy_number) for p in pages if p.extraction.policy_number]
        normalized_numbers = {(value or "").replace(" ", "").replace("-", "").lower() for _, value in policy_pages}
        if len(normalized_numbers) > 1:
            findings.append(Discrepancy(
                category="POLICY", severity="CRITICAL", title="Policy numbers do not match",
                detail="Different policy numbers were extracted from the uploaded documents: " +
                       ", ".join(sorted({value for _, value in policy_pages if value})),
                page_ids=[p.page_id for p, _ in policy_pages],
            ))

        policy_dates = [
            (p, parse_date(p.extraction.policy_valid_from), parse_date(p.extraction.policy_valid_to))
            for p in pages if p.extraction.policy_valid_from or p.extraction.policy_valid_to
        ]
        admissions = [
            (p, parse_date(p.extraction.admission_date), parse_date(p.extraction.discharge_date))
            for p in pages if p.extraction.admission_date or p.extraction.discharge_date
        ]
        for policy_page, valid_from, valid_to in policy_dates:
            for claim_page, admission, discharge in admissions:
                outside_start = admission is not None and valid_from is not None and admission < valid_from
                outside_end = discharge is not None and valid_to is not None and discharge > valid_to
                if outside_start or outside_end:
                    findings.append(Discrepancy(
                        category="POLICY", severity="CRITICAL",
                        title="Hospital dates fall outside policy validity",
                        detail=(
                            f"Hospital stay on {claim_page.filename} is {admission or 'unknown'} to "
                            f"{discharge or 'unknown'}, outside the policy validity period "
                            f"{valid_from or 'unknown'} to {valid_to or 'unknown'}."
                        ),
                        page_ids=[policy_page.page_id, claim_page.page_id],
                    ))

        for page in pages:
            admission = parse_date(page.extraction.admission_date)
            discharge = parse_date(page.extraction.discharge_date)
            if admission and discharge and admission > discharge:
                findings.append(Discrepancy(
                    category="TIMELINE", severity="CRITICAL", title="Invalid admission/discharge timeline",
                    detail=f"Admission date {admission.isoformat()} is later than discharge date {discharge.isoformat()}.",
                    page_ids=[page.page_id],
                ))
        stays = [
            (p, parse_date(p.extraction.admission_date), parse_date(p.extraction.discharge_date))
            for p in pages
            if p.extraction.admission_date and p.extraction.discharge_date
        ]
        for service_page in pages:
            for value in service_page.extraction.service_dates:
                service_date = parse_date(value)
                if not service_date:
                    continue
                for stay_page, admission, discharge in stays:
                    if admission and discharge and not admission <= service_date <= discharge:
                        findings.append(Discrepancy(
                            category="TIMELINE", severity="WARNING", title="Service date falls outside hospital stay",
                            detail=(
                                f"Service date {service_date.isoformat()} on {service_page.filename} is outside "
                                f"{admission.isoformat()} to {discharge.isoformat()}."
                            ),
                            page_ids=[service_page.page_id, stay_page.page_id],
                        ))
        return findings, audits
