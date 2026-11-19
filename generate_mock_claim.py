"""Generate a small, selectable-text synthetic health insurance claim PDF."""
from __future__ import annotations

import argparse
from pathlib import Path

import pymupdf as fitz
from PIL import Image, ImageEnhance, ImageFilter
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle,
)


OUTPUT = Path(__file__).resolve().parent / "demo_claim.pdf"
NAVY = colors.HexColor("#15345b")
BLUE = colors.HexColor("#2563eb")
PALE = colors.HexColor("#eff6ff")
INK = colors.HexColor("#172033")


def build_pdf(destination: Path) -> None:
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="Brand", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=17, leading=21, textColor=NAVY, alignment=TA_LEFT, spaceAfter=2))
    styles.add(ParagraphStyle(name="SubBrand", parent=styles["Normal"], fontSize=8, leading=11, textColor=colors.HexColor("#64748b")))
    styles.add(ParagraphStyle(name="Section", parent=styles["Heading2"], fontSize=12, leading=15, textColor=NAVY, spaceBefore=9, spaceAfter=6))
    styles.add(ParagraphStyle(name="BodySmall", parent=styles["BodyText"], fontSize=9, leading=13, textColor=INK))
    styles.add(ParagraphStyle(name="Fine", parent=styles["BodyText"], fontSize=7.5, leading=10, textColor=colors.HexColor("#64748b")))

    def header_footer(canvas, doc):
        canvas.saveState()
        width, height = A4
        canvas.setFillColor(NAVY)
        canvas.rect(0, height - 13 * mm, width, 13 * mm, stroke=0, fill=1)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 9)
        canvas.drawString(18 * mm, height - 8.5 * mm, "CLAIMREADY · SYNTHETIC DEMO DOCUMENT")
        canvas.setStrokeColor(colors.HexColor("#dbe3ee"))
        canvas.line(18 * mm, 15 * mm, width - 18 * mm, 15 * mm)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.setFont("Helvetica", 7)
        canvas.drawString(18 * mm, 10 * mm, "Fictional data for demonstration only · Not valid for insurance submission")
        canvas.drawRightString(width - 18 * mm, 10 * mm, f"Page {doc.page}")
        canvas.restoreState()

    doc = BaseDocTemplate(
        str(destination), pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=22 * mm, bottomMargin=21 * mm,
        title="ClaimReady Synthetic Claim Packet",
        author="ClaimReady demo generator",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="normal")
    doc.addPageTemplates([PageTemplate(id="claim", frames=frame, onPage=header_footer)])
    story = []

    def title(heading, subheading):
        story.extend([Paragraph(heading, styles["Brand"]), Paragraph(subheading, styles["SubBrand"]), Spacer(1, 5 * mm)])

    def section(heading):
        story.append(Paragraph(heading, styles["Section"]))

    def fields(rows):
        table = Table([[Paragraph(f"<b>{label}</b>", styles["BodySmall"]), Paragraph(value, styles["BodySmall"])] for label, value in rows], colWidths=[43 * mm, 118 * mm])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), PALE),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d7e1ef")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(table)

    # Government-issued ID copy.
    title("PATIENT IDENTITY CARD", "Demo hospital intake · ID copy")
    story.append(Paragraph("SYNTHETIC SAMPLE — NOT A GOVERNMENT DOCUMENT", styles["Fine"]))
    section("Identity details")
    fields([
        ("Patient Name", "Ramesh Kumar Sharma"),
        ("Date of Birth", "14/06/1982"),
        ("Gender", "Male"),
        ("ID Number", "DEMO-ID-4821-7710"),
        ("Address", "42 Sample Residency, Pune, Maharashtra"),
    ])
    story.append(Spacer(1, 9 * mm))
    story.append(Paragraph("This fictional identity page is generated only to demonstrate document classification and field matching.", styles["BodySmall"]))

    # Insurance card is present; policy schedule is intentionally absent.
    story.append(PageBreak())
    title("HEALTH PLAN MEMBER CARD", "BlueRiver Health Assurance · TPA member card")
    fields([
        ("Insurer", "BlueRiver Health Assurance (fictional)"),
        ("Member Name", "Ramesh Kumar Sharma"),
        ("Policy Number", "BR-2026-884210"),
        ("TPA ID", "TPA-554290"),
        ("Coverage Period", "01/04/2026 to 31/03/2027"),
    ])
    story.append(Spacer(1, 6 * mm))

    # Discharge summary.
    story.append(PageBreak())
    title("HOSPITAL DISCHARGE SUMMARY", "Sunrise Multispeciality Hospital · Pune")
    fields([
        ("Patient Name", "R. K. Sharma"),
        ("Hospital", "Sunrise Multispeciality Hospital"),
        ("Admission Date", "10/11/2026"),
        ("Discharge Date", "13/11/2026"),
        ("Diagnosis", "Acute appendicitis"),
        ("Treating Doctor", "Dr. Meera Nair"),
        ("Policy Number", "BR-2026-884210"),
    ])
    section("Clinical summary")
    story.append(Paragraph("Patient admitted with abdominal pain. Laparoscopic appendectomy was performed on 11/11/2026. Recovery was stable and discharge advice was provided.", styles["BodySmall"]))

    # Itemized final bill includes an intentional arithmetic discrepancy.
    story.append(PageBreak())
    title("FINAL ITEMIZED HOSPITAL BILL", "Sunrise Multispeciality Hospital · Bill SB-2026-1184")
    fields([
        ("Patient Name", "Suresh Sharma"),  # Intentional name discrepancy.
        ("Hospital", "Sunrise Multispeciality Hospital"),
        ("Admission / Discharge", "10/11/2026 – 13/11/2026"),
        ("Policy Number", "BR-2026-884210"),
    ])
    story.append(Spacer(1, 4 * mm))
    bill_rows = [
        ["Description", "Qty", "Unit price", "Amount"],
        ["Room charges", "3", "INR 8,000.00", "INR 24,000.00"],
        ["Surgery package", "1", "INR 42,000.00", "INR 42,000.00"],
        ["Medicines and consumables", "1", "INR 11,500.00", "INR 11,500.00"],
        ["Laboratory investigations", "1", "INR 6,500.00", "INR 6,500.00"],
    ]
    bill_table = Table(bill_rows, colWidths=[76 * mm, 15 * mm, 36 * mm, 36 * mm], repeatRows=1)
    bill_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d7e1ef")),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(bill_table)
    story.append(Spacer(1, 4 * mm))
    fields([
        ("Subtotal", "INR 84,000.00"),  # Intentional: line-item sum is INR 84,000.
        ("Taxes", "INR 4,200.00"),
        ("Discount", "INR 2,000.00"),
        ("Grand Total", "INR 88,000.00"),  # Intentional: calculated total should be INR 86,200.
    ])
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph("Demo discrepancies: patient name differs from ID/discharge summary; printed grand total is intentionally ₹1,800 above subtotal + tax − discount.", styles["Fine"]))

    # Prescription page.
    story.append(PageBreak())
    title("DOCTOR PRESCRIPTION", "Sunrise Multispeciality Hospital · Outpatient / discharge advice")
    fields([
        ("Patient Name", "Ramesh Kumar Sharma"),
        ("Treating Doctor", "Dr. Meera Nair"),
        ("Doctor Reg No", "MMC-DEMO-19384"),
        ("Diagnosis", "Acute appendicitis · post-operative care"),
        ("Medicines", "Paracetamol 500 mg; Amoxicillin 500 mg"),
        ("Date", "13/11/2026"),
    ])
    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph("Signature: ____________________      Clinic seal: ____________________", styles["BodySmall"]))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("All people, facilities, IDs, policy details, and amounts in this packet are fictional.", styles["Fine"]))
    doc.build(story)


def build_scan_images(pdf_path: Path, output_dir: Path) -> None:
    """Render lightly imperfect grayscale scans alongside the searchable demo PDF."""
    output_dir.mkdir(parents=True, exist_ok=True)
    with fitz.open(pdf_path) as document:
        for index, page in enumerate(document, 1):
            pixmap = page.get_pixmap(matrix=fitz.Matrix(1.7, 1.7), alpha=False)
            image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples).convert("L")
            image = ImageEnhance.Contrast(image).enhance(0.94)
            image = image.filter(ImageFilter.GaussianBlur(radius=0.18))
            noise = Image.effect_noise(image.size, 4).convert("L")
            image = Image.blend(image, noise, 0.025)
            image.rotate(0.15 if index % 2 else -0.15, resample=Image.Resampling.BICUBIC, fillcolor=255).save(
                output_dir / f"page-{index:02d}.png",
                format="PNG",
                optimize=True,
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT, help="Destination PDF path (default: claimready/demo_claim.pdf)")
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    build_pdf(args.output)
    build_scan_images(args.output, args.output.parent / "demo_scans")
    print(f"Generated synthetic claim packet: {args.output}")
    print(f"Generated lightly imperfect scan images: {args.output.parent / 'demo_scans'}")
    print("Includes a patient-name mismatch, an arithmetic discrepancy, and no policy schedule.")


if __name__ == "__main__":
    main()
