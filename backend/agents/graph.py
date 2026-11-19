"""Explicit, event-producing ClaimReady state-machine orchestrator."""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from backend.agents.auditor import ChecklistAgent, VerificationAgent
from backend.agents.classifier import PageClassifierAgent
from backend.agents.extractor import DocumentExtractorAgent
from backend.agents.reflector import ReflectionAgent
from backend.agents.reporter import ReportGeneratorAgent
from backend.schemas import ClaimState, PageRecord


class ClaimGraph:
    def __init__(self) -> None:
        self.classifier = PageClassifierAgent()
        self.extractor = DocumentExtractorAgent()
        self.checklist_agent = ChecklistAgent()
        self.verifier = VerificationAgent()
        self.reflector = ReflectionAgent()
        self.reporter = ReportGeneratorAgent()

    async def run(self, claim_id: str, pages: list[PageRecord]) -> AsyncIterator[tuple[str, dict]]:
        state = ClaimState(claim_id=claim_id, pages=pages)
        total = len(pages)
        yield "trace", {"agent": "PageClassifierAgent", "status": "active", "message": f"Classifying {total} page(s)."}
        classified = []
        for index, page in enumerate(state.pages, 1):
            page, message = await asyncio.to_thread(self.classifier.classify, page)
            classified.append(page)
            yield "trace", {
                "agent": "PageClassifierAgent", "status": "progress",
                "message": f"{index}/{total} {page.filename} p.{page.page_number}: {page.document_type} · {message}",
            }
        state.pages = classified
        yield "trace", {"agent": "PageClassifierAgent", "status": "complete", "message": "Page triage complete."}

        yield "trace", {"agent": "DocumentExtractorAgent", "status": "active", "message": "Extracting targeted claim fields."}
        for index, page in enumerate(state.pages, 1):
            page, message = await asyncio.to_thread(self.extractor.extract, page)
            state.pages[index - 1] = page
            yield "trace", {
                "agent": "DocumentExtractorAgent", "status": "progress",
                "message": f"{index}/{total} {page.filename}: {message}",
            }
        yield "trace", {"agent": "DocumentExtractorAgent", "status": "complete", "message": "Field extraction complete."}

        yield "trace", {"agent": "ChecklistAgent", "status": "active", "message": "Comparing uploads with the standard claim checklist."}
        state.checklist = self.checklist_agent.run(state.pages)
        yield "trace", {"agent": "ChecklistAgent", "status": "complete", "message": "Document checklist evaluated."}

        yield "trace", {"agent": "VerificationAgent", "status": "active", "message": "Checking names, policy numbers, dates, and bill arithmetic."}
        state.discrepancies, state.arithmetic_audits = self.verifier.run(state.pages)
        yield "trace", {
            "agent": "VerificationAgent", "status": "complete",
            "message": f"Verification complete: {len(state.discrepancies)} finding(s), {len(state.arithmetic_audits)} bill audit(s).",
        }

        yield "trace", {"agent": "ReflectionAgent", "status": "active", "message": "Re-reading uncertain fields and anomaly evidence."}
        state.reflection_notes = await asyncio.to_thread(self.reflector.run, state.pages, state.discrepancies)
        state.discrepancies, state.arithmetic_audits = await asyncio.to_thread(self.verifier.run, state.pages)
        yield "trace", {
            "agent": "ReflectionAgent", "status": "complete",
            "message": f"Reflection complete: {len(state.reflection_notes)} targeted review note(s); findings recalculated.",
        }

        yield "trace", {"agent": "ReportGeneratorAgent", "status": "active", "message": "Scoring readiness and drafting correction actions."}
        for page in state.pages:
            page.image_base64 = None
            page.text = ""
        state.report = self.reporter.build(
            state.claim_id, state.pages, state.checklist, state.discrepancies, state.arithmetic_audits,
        )
        state.report.pages = state.pages
        state.report.reflection_notes = state.reflection_notes
        yield "trace", {
            "agent": "ReportGeneratorAgent", "status": "complete",
            "message": f"Report ready: {state.report.status} · score {state.report.readiness_score}/100.",
        }
        yield "report", state.report.model_dump(mode="json")
