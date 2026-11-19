"""FastAPI API and static frontend hosting for ClaimReady."""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.agents.graph import ClaimGraph
from backend.config import ALLOWED_EXTENSIONS, MAX_UPLOAD_BYTES
from backend.schemas import Approval, ClaimReport
from backend.utils.pdf_processor import pages_from_upload

ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = ROOT / "frontend"
app = FastAPI(title="ClaimReady", version="1.0.0")
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
CLAIMS: dict[str, ClaimReport] = {}


class ApprovalRequest(BaseModel):
    executive_name: str = Field(min_length=1, max_length=120)
    executive_id: str = Field(min_length=1, max_length=80)
    note: str = Field(default="", max_length=2000)
    resolved_discrepancy_indexes: list[int] = Field(default_factory=list)


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/demo_claim.pdf", include_in_schema=False)
async def demo_claim() -> FileResponse:
    demo_path = ROOT / "demo_claim.pdf"
    if not demo_path.is_file():
        raise HTTPException(status_code=404, detail="Demo packet missing. Run python generate_mock_claim.py first.")
    return FileResponse(demo_path, media_type="application/pdf", filename="demo_claim.pdf")


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "ClaimReady"}


@app.post("/api/analyze")
async def analyze(files: list[UploadFile] = File(...)) -> StreamingResponse:
    if not files:
        raise HTTPException(status_code=400, detail="Upload at least one PDF or image.")
    claim_id = f"CR-{uuid.uuid4().hex[:8].upper()}"
    pages = []
    total_bytes = 0
    for upload in files:
        filename = Path(upload.filename or "upload").name
        suffix = Path(filename).suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {filename}")
        remaining = MAX_UPLOAD_BYTES - total_bytes
        data = await upload.read(remaining + 1)
        if len(data) > remaining:
            raise HTTPException(status_code=413, detail=f"Combined upload exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")
        total_bytes += len(data)
        if not data:
            raise HTTPException(status_code=400, detail=f"{filename} is empty.")
        try:
            pages.extend(pages_from_upload(filename, data, upload.content_type or "application/octet-stream"))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not pages:
        raise HTTPException(status_code=400, detail="No readable pages were found in the upload.")

    async def event_stream():
        try:
            async for event_name, payload in ClaimGraph().run(claim_id, pages):
                if event_name == "report":
                    CLAIMS[claim_id] = ClaimReport.model_validate(payload)
                yield f"event: {event_name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
        except Exception as exc:
            yield f"event: error\ndata: {json.dumps({'message': f'Analysis failed: {type(exc).__name__}: {exc}'})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    })


@app.get("/api/claims/{claim_id}")
async def get_claim(claim_id: str) -> dict:
    report = CLAIMS.get(claim_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Claim report not found.")
    return report.model_dump(mode="json")


@app.post("/api/claims/{claim_id}/approve")
async def approve_claim(claim_id: str, request: ApprovalRequest) -> dict:
    report = CLAIMS.get(claim_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Claim report not found.")
    if report.locked:
        raise HTTPException(status_code=409, detail="This report is already locked and approved.")
    indexes = set(request.resolved_discrepancy_indexes)
    if any(index < 0 or index >= len(report.discrepancies) for index in indexes):
        raise HTTPException(status_code=400, detail="A resolved-item selection is outside the report.")
    for index in indexes:
        report.discrepancies[index].resolved = True
    report.approval = Approval(
        approved=True,
        executive_name=request.executive_name.strip(),
        executive_id=request.executive_id.strip(),
        note=request.note.strip(),
        approved_at=datetime.now(timezone.utc).isoformat(),
    )
    report.locked = True
    return report.model_dump(mode="json")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)
