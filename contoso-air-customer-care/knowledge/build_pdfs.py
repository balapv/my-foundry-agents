"""Build the four Contoso Air policy PDFs from the Markdown sources in knowledge/source/.

The PDFs are the files uploaded to the agent's knowledge (File Search vector store),
whether you build the agent in the Foundry portal or with code. Both the sources and the
generated PDFs are committed. Rebuild after editing a source:

    python knowledge/build_pdfs.py            # write PDFs
    python knowledge/build_pdfs.py --check    # verify PDFs exist and match page targets

Supports the small Markdown subset used by the sources: headings, paragraphs,
single-level bullet lists, pipe tables, and **bold**.
"""

from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

KNOWLEDGE_DIR = Path(__file__).resolve().parent
SOURCE_DIR = KNOWLEDGE_DIR / "source"
BRAND = colors.HexColor("#0B4F8A")

# name -> (min pages, max pages) from the implementation spec, section 6
DOCUMENTS = {
    "flight-disruption-policy": (4, 6),
    "loyalty-benefits": (3, 4),
    "meal-hotel-assistance": (3, 4),
    "customer-service-escalation": (3, 4),
}


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    body = ParagraphStyle("Body", parent=base["BodyText"], fontName="Helvetica", fontSize=9, leading=11.4,
                          spaceAfter=3.5, alignment=TA_LEFT)
    return {
        "title": ParagraphStyle("Title", parent=base["Title"], fontName="Helvetica-Bold", fontSize=18, leading=22,
                                textColor=BRAND, alignment=TA_LEFT, spaceAfter=10),
        "h2": ParagraphStyle("H2", parent=body, fontName="Helvetica-Bold", fontSize=12, leading=15,
                             textColor=BRAND, spaceBefore=7, spaceAfter=3),
        "h3": ParagraphStyle("H3", parent=body, fontName="Helvetica-Bold", fontSize=10.5, leading=14,
                             spaceBefore=4, spaceAfter=2),
        "body": body,
        "cell": ParagraphStyle("Cell", parent=body, fontSize=8, leading=10, spaceAfter=0),
        "cellhead": ParagraphStyle("CellHead", parent=body, fontName="Helvetica-Bold", fontSize=8, leading=10,
                                   spaceAfter=0, textColor=colors.white),
    }


def _inline(text: str) -> str:
    escaped = html.escape(text.strip(), quote=False)
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)


def _table(rows: list[list[str]], styles: dict[str, ParagraphStyle], width: float) -> Table:
    header, *body = rows
    data = [[Paragraph(_inline(c), styles["cellhead"]) for c in header]]
    data += [[Paragraph(_inline(c), styles["cell"]) for c in row] for row in body]
    # Give longer columns more room, based on the longest text in each column.
    lengths = [max(len(r[i]) if i < len(r) else 0 for r in rows) for i in range(len(header))]
    weights = [max(10, min(n, 60)) for n in lengths]
    col_widths = [width * w / sum(weights) for w in weights]
    table = Table(data, colWidths=col_widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BRAND),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#EEF3F8")]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#B8C4D0")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return table


def markdown_to_flowables(markdown: str, styles: dict[str, ParagraphStyle], width: float) -> list:
    flowables: list = []
    lines = markdown.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        if not line.strip():
            i += 1
            continue
        if line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{3,}:?", c) for c in cells):
                    rows.append(cells)
                i += 1
            flowables += [_table(rows, styles, width), Spacer(1, 6)]
            continue
        if line.startswith("- "):
            items = []
            while i < len(lines) and lines[i].startswith("- "):
                items.append(ListItem(Paragraph(_inline(lines[i][2:]), styles["body"]), leftIndent=14))
                i += 1
            flowables.append(ListFlowable(items, bulletType="bullet", start="\u2022", leftIndent=14,
                                          bulletFontSize=8))
            continue
        if line.startswith("# "):
            flowables.append(Paragraph(_inline(line[2:]), styles["title"]))
        elif line.startswith("## "):
            flowables.append(Paragraph(_inline(line[3:]), styles["h2"]))
        elif line.startswith("### "):
            flowables.append(Paragraph(_inline(line[4:]), styles["h3"]))
        else:
            paragraph = [line]
            while (i + 1 < len(lines) and lines[i + 1].strip()
                   and not lines[i + 1].startswith(("#", "- ", "|"))):
                i += 1
                paragraph.append(lines[i].strip())
            flowables.append(Paragraph(_inline(" ".join(paragraph)), styles["body"]))
        i += 1
    return flowables


def _document_meta(markdown: str) -> tuple[str, str, str]:
    title = next(line[2:].strip() for line in markdown.splitlines() if line.startswith("# "))
    doc_id = re.search(r"\|\s*Document ID\s*\|\s*([^|]+?)\s*\|", markdown)
    version = re.search(r"\|\s*Version\s*\|\s*([^|]+?)\s*\|", markdown)
    return title, doc_id.group(1) if doc_id else "", version.group(1) if version else ""


def build_pdf(name: str) -> Path:
    source = SOURCE_DIR / f"{name}.md"
    target = KNOWLEDGE_DIR / f"{name}.pdf"
    markdown = source.read_text(encoding="utf-8")
    title, doc_id, version = _document_meta(markdown)
    styles = _styles()

    def decorate(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(BRAND)
        canvas.rect(0, LETTER[1] - 0.42 * inch, LETTER[0], 0.42 * inch, stroke=0, fill=1)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 10)
        canvas.drawString(0.75 * inch, LETTER[1] - 0.27 * inch, "CONTOSO AIR")
        canvas.setFont("Helvetica", 8.5)
        canvas.drawRightString(LETTER[0] - 0.75 * inch, LETTER[1] - 0.27 * inch, title)
        canvas.setFillColor(colors.HexColor("#5A6B7B"))
        canvas.setFont("Helvetica", 7.5)
        canvas.drawString(0.75 * inch, 0.5 * inch, f"{doc_id}  |  Version {version}  |  Internal - Customer Care")
        canvas.drawRightString(LETTER[0] - 0.75 * inch, 0.5 * inch, f"Page {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(
        str(target), pagesize=LETTER, leftMargin=0.7 * inch, rightMargin=0.7 * inch,
        topMargin=0.7 * inch, bottomMargin=0.75 * inch,
        title=title, author="Contoso Air Customer Experience", subject=f"{doc_id} v{version}",
        creator="Contoso Air Policy Publishing", invariant=True,
    )
    doc.build(markdown_to_flowables(markdown, styles, doc.width), onFirstPage=decorate, onLaterPages=decorate)
    return target


def page_count(path: Path) -> int:
    from pypdf import PdfReader

    return len(PdfReader(str(path)).pages)


def check() -> list[str]:
    problems = []
    for name, (low, high) in DOCUMENTS.items():
        pdf = KNOWLEDGE_DIR / f"{name}.pdf"
        if not pdf.exists():
            problems.append(f"{pdf.name} is missing; run python knowledge/build_pdfs.py")
            continue
        pages = page_count(pdf)
        if not low <= pages <= high:
            problems.append(f"{pdf.name} has {pages} pages; target is {low}-{high}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="verify the PDFs without rebuilding")
    args = parser.parse_args()
    if not args.check:
        for name in DOCUMENTS:
            path = build_pdf(name)
            print(f"Built {path.name} ({page_count(path)} pages)")
    problems = check()
    if problems:
        print("\n".join(problems))
        return 1
    print("Knowledge PDFs are present and within page targets.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
