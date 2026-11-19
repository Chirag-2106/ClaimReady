"""Readiness scoring, report synthesis, and correction drafting."""
from __future__ import annotations

from backend.schemas import (
    ChecklistItem, ClaimReport, CorrectionAction, Discrepancy, PageRecord,
)


class ReportGeneratorAgent:
    def build(
        self,
        claim_id: str,
        pages: list[PageRecord],
        checklist: list[ChecklistItem],
        findings: list[Discrepancy],
        arithmetic_audits,
    ) -> ClaimReport:
        missing_required = [item for item in checklist if item.required and item.status != "PRESENT"]
        critical = [finding for finding in findings if finding.severity == "CRITICAL"]
        score = 100
        score -= 15 * sum(item.status == "MISSING" for item in missing_required)
        score -= 10 * sum(item.status == "LOW_LEGIBILITY" for item in missing_required)
        score -= 20 * len(critical)
        score -= 5 * sum(f.severity == "WARNING" for f in findings)
        score -= 3 * sum(item.status == "UNSUPPORTED" for item in checklist)
        score = max(0, min(100, score))
        status = "CRITICAL BLOCKERS" if critical or any(i.status == "MISSING" for i in missing_required) else (
            "NEEDS CORRECTION" if score < 90 or missing_required or findings else "READY"
        )

        actions: list[CorrectionAction] = []
        for item in missing_required:
            owner = "Patient / Attendant" if item.id in {"government_id", "insurance_card"} else "Insurer / TPA"
            if item.id == "discharge_summary":
                owner = "Treating Doctor"
            actions.append(CorrectionAction(
                owner=owner, priority="HIGH",
                action=f"Obtain and upload the {item.label.lower()}.",
                reason="This required checklist document is missing or not legible.",
            ))
        for finding in findings:
            if finding.category == "ARITHMETIC":
                owner = "Hospital Billing Desk"
            elif finding.category == "IDENTITY":
                owner = "Patient / Attendant"
            elif finding.category == "TIMELINE":
                owner = "Treating Doctor"
            else:
                owner = "Insurer / TPA"
            actions.append(CorrectionAction(
                owner=owner,
                priority="HIGH" if finding.severity == "CRITICAL" else "MEDIUM",
                action=f"Review and correct: {finding.title}.",
                reason=finding.detail,
            ))
        if not actions:
            actions.append(CorrectionAction(
                owner="Patient / Attendant", priority="LOW",
                action="No correction is currently required; retain original documents for submission.",
                reason="All required checklist and verification checks passed.",
            ))

        unresolved = "; ".join(f"{f.title}: {f.detail}" for f in findings)
        missing = "; ".join(i.label for i in missing_required)
        note = f"Claim {claim_id} readiness review: {status} ({score}/100)."
        if missing:
            note += f" Outstanding documents: {missing}."
        if unresolved:
            note += f" Items requiring review: {unresolved}"
        if not missing and not unresolved:
            note += " The uploaded documents passed the current automated completeness and consistency checks."
        note += " Please verify all originals and insurer-specific requirements before submission."
        return ClaimReport(
            claim_id=claim_id, readiness_score=score, status=status,
            checklist=checklist, discrepancies=findings,
            arithmetic_audits=arithmetic_audits, correction_actions=actions,
            executive_note_draft=note, pages=pages,
        )
