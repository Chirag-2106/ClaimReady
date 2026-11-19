# ClaimReady

ClaimReady is a runnable health-insurance claim document checker demo. It accepts PDF and image uploads, emits a live agent execution trace, audits required documents and bill arithmetic, and provides an executive approval/export workflow.

> **Important:** ClaimReady is a decision-support demo, not a medical, legal, insurance, or coverage determination. Do not use its output as a substitute for checking original documents and insurer-specific rules. The included claim packet contains synthetic data only.

## What is included

- FastAPI backend with a streaming Server-Sent Events analysis endpoint.
- An explicit six-node state-machine workflow: page classifier, field extractor, checklist auditor, verification auditor, reflection pass, and report generator.
- Optional Gemini multimodal classification and extraction via `google-genai`. When no key is configured or a model call fails, the app continues with a local text-based parser and surfaces fallback information in the trace.
- PDF page rendering / selectable text extraction using PyMuPDF and image validation using Pillow.
- Browser UI with drag-and-drop multi-file upload, execution trace, checklist, consistency findings, arithmetic audit, correction actions, executive sign-off, JSON export, and print-to-PDF.
- `generate_mock_claim.py` produces a selectable-text synthetic PDF packet and five lightly imperfect grayscale scan images containing a patient ID, insurance member card, discharge summary, itemized bill, and prescription. The policy schedule is intentionally omitted; the bill has a patient-name mismatch and an intentional total discrepancy.

## Requirements

- Python 3.10 or later
- Windows PowerShell, macOS, or Linux terminal
- Optional Gemini API key for image-only/scanned documents; local parsing works best with the included selectable-text demo PDF.

## Install and run

From the `claimready` directory:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
python generate_mock_claim.py
python -m uvicorn backend.main:app --reload
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000), click **Use generated demo packet**, then review the report. The generated `demo_claim.pdf` and the page images in `demo_scans/` are available in the project root.

macOS/Linux venv activation is `source .venv/bin/activate`; copy `.env.example` to `.env` with `cp .env.example .env`.

## Optional Gemini vision

Set `GEMINI_API_KEY` in `.env` to enable Gemini vision classification and targeted extraction. `GEMINI_MODEL` defaults to `gemini-2.5-flash`; `USE_VISION_LLM=false` forces local parsing. To switch providers, set `LLM_PROVIDER=openai`, provide `OPENAI_API_KEY`, and optionally set `OPENAI_MODEL` (defaults to `gpt-4o`). Vision calls are best effort: errors/rate limits fall back to the local parser, and the per-agent trace calls out that fallback. Do not upload sensitive claims to a third-party model unless your organization has approved that processing.

## API

- `GET /api/health` — health check.
- `POST /api/analyze` — multipart `files` upload; returns `trace`, `report`, or `error` SSE events.
- `GET /api/claims/{claim_id}` — current in-memory report.
- `POST /api/claims/{claim_id}/approve` — lock the report with executive name, ID, note, and resolved discrepancy indexes.

Analysis reports and approvals are stored in process memory and are cleared when the server restarts. Configure an appropriate persistent database and access controls before adapting the demo for operational use. The approval lock records human sign-off; it does not change the automated readiness result.

## Test claim manually

```powershell
python generate_mock_claim.py
python -m uvicorn backend.main:app --reload
```

Open the dashboard, select `demo_claim.pdf` (or use the demo button), and verify that the policy schedule is missing, the patient name mismatch is flagged, and the printed bill total differs from the deterministic calculation. Approve with a test executive name and ID; then try **Export JSON** or **Print / Save PDF**.

The generator can write to another location:

```powershell
python generate_mock_claim.py --output .\demo-data\mock-packet.pdf
```
