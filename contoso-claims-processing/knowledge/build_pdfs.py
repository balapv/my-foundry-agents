"""Build the four Contoso Insurance claims-guidance PDFs from the Markdown sources in knowledge/source/.

The PDFs are the reusable company guidance uploaded to the agent's File Search vector store,
whether the agent is built in the Foundry portal or with code. Markdown is the source of
truth; both the sources and the generated PDFs are committed. Rebuild after editing a source:

    python knowledge/build_pdfs.py            # write PDFs
    python knowledge/build_pdfs.py --check    # verify PDFs exist, are current and match page targets

Output is deterministic (fixed metadata, no timestamps), so --check compares a fresh in-memory
build with the committed PDF byte-for-byte.

Supports the Markdown subset used by the sources: headings (#, ##, ###), paragraphs,
single-level bullet and numbered lists, pipe tables and **bold**.
"""

from __future__ import annotations

import argparse
import html
import io
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
BRAND = colors.HexColor("#1F4E5F")
SHADE = colors.HexColor("#EDF3F4")

# name -> (min pages, max pages), from IMPLEMENTATION-SPEC sections 19-22.
DOCUMENTS = {
    "claims-handling-guidelines": (5, 7),
    "auto-coverage-guidance": (4, 6),
    "repair-estimate-review": (4, 6),
    "claims-escalation-guidance": (4, 5),
}

BULLET = re.compile(r"^- (.*)$")
NUMBERED = re.compile(r"^(\d+)\. (.*)$")


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    body = ParagraphStyle("Body", parent=base["BodyText"], fontName="Helvetica", fontSize=9.5, leading=12.4,
                          spaceAfter=4.5, alignment=TA_LEFT)
    return {
        "title": ParagraphStyle("Title", parent=base["Title"], fontName="Helvetica-Bold", fontSize=18, leading=22,
                                textColor=BRAND, alignment=TA_LEFT, spaceAfter=10),
        "h2": ParagraphStyle("H2", parent=body, fontName="Helvetica-Bold", fontSize=12, leading=15,
                             textColor=BRAND, spaceBefore=8, spaceAfter=3),
        "h3": ParagraphStyle("H3", parent=body, fontName="Helvetica-Bold", fontSize=10.5, leading=14,
                             spaceBefore=5, spaceAfter=2),
        "body": body,
        "cell": ParagraphStyle("Cell", parent=body, fontSize=8.5, leading=10.5, spaceAfter=0),
        "cellhead": ParagraphStyle("CellHead", parent=body, fontName="Helvetica-Bold", fontSize=8.5, leading=10.5,
                                   spaceAfter=0, textColor=colors.white),
    }


def _inline(text: str) -> str:
    escaped = html.escape(text.strip(), quote=False)
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)


def _table(rows: list[list[str]], styles: dict[str, ParagraphStyle], width: float) -> Table:
    header, *body = rows
    data = [[Paragraph(_inline(c), styles["cellhead"]) for c in header]]
    data += [[Paragraph(_inline(c), styles["cell"]) for c in row] for row in body]
    lengths = [max(len(r[i]) if i < len(r) else 0 for r in rows) for i in range(len(header))]
    weights = [max(10, min(n, 60)) for n in lengths]
    col_widths = [width * w / sum(weights) for w in weights]
    table = Table(data, colWidths=col_widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BRAND),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, SHADE]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#B5C6CB")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
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
        for pattern, kind in ((BULLET, "bullet"), (NUMBERED, "1")):
            if pattern.match(line):
                items, start = [], None
                while i < len(lines) and (match := pattern.match(lines[i].rstrip())):
                    if kind == "1" and start is None:
                        start = int(match.group(1))
                    items.append(ListItem(Paragraph(_inline(match.group(match.lastindex)), styles["body"]),
                                          leftIndent=16))
                    i += 1
                if kind == "bullet":
                    flowables.append(ListFlowable(items, bulletType="bullet", start="\u2022", leftIndent=16,
                                                  bulletFontSize=8))
                else:
                    flowables.append(ListFlowable(items, bulletType="1", start=start, leftIndent=16,
                                                  bulletFontName="Helvetica", bulletFontSize=9, bulletFormat="%s."))
                break
        else:
            if line.startswith("# "):
                flowables.append(Paragraph(_inline(line[2:]), styles["title"]))
            elif line.startswith("## "):
                flowables.append(Paragraph(_inline(line[3:]), styles["h2"]))
            elif line.startswith("### "):
                flowables.append(Paragraph(_inline(line[4:]), styles["h3"]))
            else:
                paragraph = [line]
                while (i + 1 < len(lines) and lines[i + 1].strip()
                       and not lines[i + 1].startswith(("#", "- ", "|"))
                       and not NUMBERED.match(lines[i + 1])):
                    i += 1
                    paragraph.append(lines[i].strip())
                flowables.append(Paragraph(_inline(" ".join(paragraph)), styles["body"]))
            i += 1
    return flowables


def document_meta(markdown: str) -> dict[str, str]:
    """Return the title and the metadata table fields (Document ID, Version, Policy owner, ...)."""
    meta = {"Title": next(line[2:].strip() for line in markdown.splitlines() if line.startswith("# "))}
    for field, value in re.findall(r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*$", markdown, flags=re.MULTILINE):
        if field not in meta and field not in ("Field",) and not set(value) <= set("-:"):
            meta[field] = value
    return meta


def render_pdf(name: str) -> bytes:
    markdown = (SOURCE_DIR / f"{name}.md").read_text(encoding="utf-8")
    meta = document_meta(markdown)
    title, doc_id, version = meta["Title"], meta.get("Document ID", ""), meta.get("Version", "")
    styles = _styles()

    def decorate(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(BRAND)
        canvas.rect(0, LETTER[1] - 0.42 * inch, LETTER[0], 0.42 * inch, stroke=0, fill=1)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 10)
        canvas.drawString(0.75 * inch, LETTER[1] - 0.27 * inch, "CONTOSO INSURANCE")
        canvas.setFont("Helvetica", 8.5)
        canvas.drawRightString(LETTER[0] - 0.75 * inch, LETTER[1] - 0.27 * inch, title)
        canvas.setFillColor(colors.HexColor("#5A6B70"))
        canvas.setFont("Helvetica", 7.5)
        canvas.drawString(0.75 * inch, 0.5 * inch,
                          f"{doc_id}  |  Version {version}  |  Internal - Claims Operations  |  Synthetic demo content")
        canvas.drawRightString(LETTER[0] - 0.75 * inch, 0.5 * inch, f"Page {doc.page}")
        canvas.restoreState()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=LETTER, leftMargin=0.75 * inch, rightMargin=0.75 * inch,
        topMargin=0.75 * inch, bottomMargin=0.8 * inch,
        title=title, author="Contoso Insurance Claims", subject=f"{doc_id} v{version}",
        creator="Contoso Insurance Policy Publishing", invariant=True,
    )
    doc.build(markdown_to_flowables(markdown, styles, doc.width), onFirstPage=decorate, onLaterPages=decorate)
    return buffer.getvalue()


def pdf_path(name: str) -> Path:
    return KNOWLEDGE_DIR / f"{name}.pdf"


def page_count(data: bytes) -> int:
    from pypdf import PdfReader

    return len(PdfReader(io.BytesIO(data)).pages)


def check() -> list[str]:
    problems = []
    for name, (low, high) in DOCUMENTS.items():
        path = pdf_path(name)
        if not path.exists():
            problems.append(f"{path.name} is missing; run python knowledge/build_pdfs.py")
            continue
        data = path.read_bytes()
        if data != render_pdf(name):
            problems.append(f"{path.name} is out of date with knowledge/source/{name}.md; rebuild it")
        pages = page_count(data)
        if not low <= pages <= high:
            problems.append(f"{path.name} has {pages} pages; target is {low}-{high}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="verify the PDFs without rebuilding")
    args = parser.parse_args(argv)
    if not args.check:
        for name in DOCUMENTS:
            data = render_pdf(name)
            pdf_path(name).write_bytes(data)
            print(f"Built {name}.pdf ({page_count(data)} pages)")
    problems = check()
    if problems:
        print("\n".join(problems))
        return 1
    print("Knowledge PDFs are present, current and within page targets.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
