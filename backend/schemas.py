"""Typed contracts shared by ClaimReady's agents and API."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DocumentType = Literal[
    "GOVERNMENT_ID",
    "INSURANCE_CARD_OR_POLICY",
    "POLICY_SCHEDULE",
    "DISCHARGE_SUMMARY",
    "ITEMIZED_HOSPITAL_BILL",
    "PHARMACY_BILL_AND_PRESCRIPTION",
    "DIAGNOSTIC_LAB_REPORT",
    "UNKNOWN_OR_UNREADABLE",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class LineItem(StrictModel):
    description: str = ""
    quantity: float | None = None
    unit_price: float | None = None
    amount: float | None = None


class PageExtraction(StrictModel):
    patient_name: str | None = None
    dob: str | None = None
    gender: str | None = None
    id_number: str | None = None
    insurer_name: str | None = None
    policy_number: str | None = None
    tpa_id: str | None = None
    policy_valid_from: str | None = None
    policy_valid_to: str | None = None
    hospital_name: str | None = None
    admission_date: str | None = None
    discharge_date: str | None = None
    service_dates: list[str] = Field(default_factory=list)
    line_items: list[LineItem] = Field(default_factory=list)
    subtotal: float | None = None
    taxes: float | None = None
    discounts: float | None = None
    stated_total_amount: float | None = None
    doctor_name: str | None = None
    doctor_reg_no: str | None = None
    diagnosis: str | None = None
    prescribed_medicines: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.55, ge=0, le=1)
    extraction_notes: list[str] = Field(default_factory=list)


class PageRecord(StrictModel):
    page_id: str
    filename: str
    page_number: int
    mime_type: str
    image_base64: str | None = None
    text: str = ""
    document_type: DocumentType = "UNKNOWN_OR_UNREADABLE"
    quality: Literal["HIGH", "MEDIUM", "BLURRY_RESCAN_NEEDED"] = "MEDIUM"
    page_summary: str = ""
    extraction: PageExtraction = Field(default_factory=PageExtraction)


class Discrepancy(StrictModel):
    category: str
    severity: Literal["CRITICAL", "WARNING", "INFO"]
    title: str
    detail: str
    page_ids: list[str] = Field(default_factory=list)
    resolved: bool = False


class ChecklistItem(StrictModel):
    id: str
    label: str
    status: Literal["PRESENT", "MISSING", "LOW_LEGIBILITY", "UNSUPPORTED"]
    detail: str = ""
    page_ids: list[str] = Field(default_factory=list)
    required: bool = True


class ArithmeticAudit(StrictModel):
    page_id: str
    filename: str
    itemized_sum: float | None = None
    subtotal: float | None = None
    taxes: float | None = None
    discounts: float | None = None
    calculated_total: float | None = None
    stated_total: float | None = None
    discrepancy: float | None = None
    status: Literal["PASS", "MISMATCH", "INCOMPLETE"] = "INCOMPLETE"
    detail: str = ""


class CorrectionAction(StrictModel):
    owner: Literal["Hospital Billing Desk", "Patient / Attendant", "Treating Doctor", "Insurer / TPA"]
    priority: Literal["HIGH", "MEDIUM", "LOW"]
    action: str
    reason: str


class Approval(StrictModel):
    approved: bool
    executive_name: str
    executive_id: str
    note: str = ""
    approved_at: str


class ClaimReport(StrictModel):
    claim_id: str
    readiness_score: int = Field(ge=0, le=100)
    status: Literal["READY", "NEEDS CORRECTION", "CRITICAL BLOCKERS"]
    checklist: list[ChecklistItem] = Field(default_factory=list)
    discrepancies: list[Discrepancy] = Field(default_factory=list)
    arithmetic_audits: list[ArithmeticAudit] = Field(default_factory=list)
    correction_actions: list[CorrectionAction] = Field(default_factory=list)
    executive_note_draft: str = ""
    reflection_notes: list[str] = Field(default_factory=list)
    pages: list[PageRecord] = Field(default_factory=list)
    approval: Approval | None = None
    locked: bool = False


class ClaimState(StrictModel):
    claim_id: str
    pages: list[PageRecord] = Field(default_factory=list)
    checklist: list[ChecklistItem] = Field(default_factory=list)
    discrepancies: list[Discrepancy] = Field(default_factory=list)
    arithmetic_audits: list[ArithmeticAudit] = Field(default_factory=list)
    reflection_notes: list[str] = Field(default_factory=list)
    report: ClaimReport | None = None
