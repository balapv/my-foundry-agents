"""Build claim evidence files from evidence/source/<claim id>/.

All evidence is synthetic. Contoso Insurance, the people, vehicles, agencies and
repair facilities named in it are fictional.

Run from the contoso-claims-processing/ directory:

    python evidence/build_evidence.py                      # rebuild PDFs and manifests
    python evidence/build_evidence.py --check              # verify committed files are current
    python evidence/build_evidence.py --import-photos DIR  # import source PNGs from DIR, then build

For each claim folder under evidence/source/ the builder:

* renders claim-form.pdf, police-report.pdf and repair-estimate.pdf from the JSON
  sources, using the structured records in data/ for names, vehicles and rates;
* computes every repair-estimate amount from its lines and the repair facility's
  labor rates, and stops if the computed total differs from the stated total or
  from the claim record;
* optionally imports the synthetic photographs (PNG -> JPEG, no metadata);
* writes evidence-manifest.json, mapping each claim document to its file with
  size, SHA-256 and page count or pixel dimensions.

PDF output is deterministic (ReportLab invariant mode): rebuilding produces
byte-identical files. Photographs are imported once and then treated as fixed
inputs; --check verifies them against the manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image
from pypdf import PdfReader
from reportlab import rl_config
from reportlab.graphics.shapes import Drawing, Line, Polygon, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

rl_config.invariant = 1

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE_DIR = ROOT / "evidence"
SOURCE_DIR = EVIDENCE_DIR / "source"
DATA_DIR = ROOT / "data"

SYNTHETIC_FOOTER = "SYNTHETIC DEMO DOCUMENT - fictional data created for demonstration. Not a real record."
MANIFEST_NOTICE = (
    "Synthetic demonstration evidence. Contoso Insurance is fictional; the documents and "
    "photographs in this folder are invented and do not describe a real person, vehicle or incident."
)
JPEG_QUALITY = 88
CENT = Decimal("0.01")

LABOR_RATE_FIELDS = {
    "Body": "bodyPerHour",
    "Mech": "mechanicalPerHour",
    "Frame": "framePerHour",
}
LABOR_NAMES = {"Body": "Body labor", "Mech": "Mechanical labor", "Frame": "Frame labor"}
PART_TYPES = {"OEM", "Sublet", "Material", None}


class BuildError(Exception):
    """Raised when a source file is inconsistent with itself or with data/."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def load_json(path: Path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def dumps_json(obj) -> bytes:
    return (json.dumps(obj, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def dec(value) -> Decimal:
    return Decimal(str(value))


def money(value: Decimal) -> str:
    return f"{value.quantize(CENT, rounding=ROUND_HALF_UP):,.2f}"


def hours(value: Decimal) -> str:
    return f"{value:.1f}"


def percent(rate: Decimal) -> str:
    """Show the full rate (7.25%, not 7.2%) so the printed tax can be recomputed; keep at least one decimal."""
    value = (rate * 100).normalize()
    return f"{value:.1f}%" if value == value.quantize(Decimal("0.1")) else f"{value:f}%"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_data() -> dict:
    def index(file_name: str, list_key: str, id_key: str) -> dict:
        records = load_json(DATA_DIR / file_name)[list_key]
        return {r[id_key]: r for r in records}

    return {
        "claims": index("claims.json", "claims", "claimId"),
        "customers": index("customers.json", "customers", "customerId"),
        "policies": index("policies.json", "policies", "policyId"),
        "vehicles": index("vehicles.json", "vehicles", "vehicleId"),
        "facilities": index("repair-facilities.json", "repairFacilities", "repairFacilityId"),
    }


# ---------------------------------------------------------------------------
# Repair estimate arithmetic
# ---------------------------------------------------------------------------


def compute_estimate(source: dict, facility: dict) -> dict:
    """Compute line amounts and totals for a repair estimate source.

    A line amount is its part/sublet/material price plus its labor and refinish
    labor at the facility's rates. Paint materials are charged per refinish hour.
    """
    rates = facility["laborRates"]
    labor_rates = {k: dec(rates[v]) for k, v in LABOR_RATE_FIELDS.items()}
    refinish_rate = dec(rates["refinishPerHour"])
    materials_rate = dec(rates["paintMaterialsPerRefinishHour"])

    lines = []
    labor_hours = {k: Decimal("0") for k in LABOR_RATE_FIELDS}
    refinish_hours = Decimal("0")
    parts = sublet = materials = Decimal("0")

    for number, line in enumerate(source["lines"], start=1):
        part_type = line["partType"]
        if part_type not in PART_TYPES:
            raise BuildError(f"line {number}: unknown partType {part_type!r}")
        price = (dec(line["unitPrice"]) * line["quantity"]).quantize(CENT)
        if price and part_type is None:
            raise BuildError(f"line {number}: priced line needs a partType")
        labor_type = line["laborType"]
        line_hours = dec(line["laborHours"])
        if line_hours and labor_type not in LABOR_RATE_FIELDS:
            raise BuildError(f"line {number}: labor hours need a known laborType")
        labor = (line_hours * labor_rates[labor_type]).quantize(CENT) if line_hours else Decimal("0.00")
        line_refinish = dec(line["refinishHours"])
        refinish = (line_refinish * refinish_rate).quantize(CENT)

        if part_type == "OEM":
            parts += price
        elif part_type == "Sublet":
            sublet += price
        elif part_type == "Material":
            materials += price
        if line_hours:
            labor_hours[labor_type] += line_hours
        refinish_hours += line_refinish

        lines.append(
            {
                "line": number,
                "section": line["section"],
                "operation": line["operation"],
                "description": line["description"],
                "partNumber": line["partNumber"],
                "partType": part_type,
                "quantity": line["quantity"],
                "price": price,
                "laborType": labor_type,
                "laborHours": line_hours,
                "laborAmount": labor,
                "refinishHours": line_refinish,
                "refinishAmount": refinish,
                "amount": price + labor + refinish,
            }
        )

    labor_amounts = {k: (labor_hours[k] * labor_rates[k]).quantize(CENT) for k in LABOR_RATE_FIELDS}
    refinish_amount = (refinish_hours * refinish_rate).quantize(CENT)
    paint_materials = (refinish_hours * materials_rate).quantize(CENT)
    subtotal = parts + sum(labor_amounts.values()) + refinish_amount + paint_materials + sublet + materials
    tax_rate = dec(source["salesTax"]["rate"])
    tax = (subtotal * tax_rate).quantize(CENT, rounding=ROUND_HALF_UP)
    grand_total = subtotal + tax

    line_sum = sum(l["amount"] for l in lines) + paint_materials
    if line_sum != subtotal:
        raise BuildError(f"line amounts ({line_sum}) do not reconcile with category totals ({subtotal})")
    if grand_total != dec(source["statedGrandTotal"]).quantize(CENT):
        raise BuildError(
            f"{source['estimateId']}: computed total {grand_total} != stated total {source['statedGrandTotal']}"
        )

    return {
        "lines": lines,
        "rates": {"labor": labor_rates, "refinish": refinish_rate, "materials": materials_rate},
        "laborHours": labor_hours,
        "laborAmounts": labor_amounts,
        "refinishHours": refinish_hours,
        "refinishAmount": refinish_amount,
        "paintMaterials": paint_materials,
        "parts": parts,
        "sublet": sublet,
        "materials": materials,
        "subtotal": subtotal,
        "taxRate": tax_rate,
        "tax": tax,
        "grandTotal": grand_total,
    }


# ---------------------------------------------------------------------------
# PDF rendering
# ---------------------------------------------------------------------------

INK = colors.HexColor("#1f2933")
MUTED = colors.HexColor("#52606d")
RULE = colors.HexColor("#9aa5b1")
BAND = colors.HexColor("#e4e7eb")

STYLES = {
    "issuer": ParagraphStyle("issuer", fontName="Helvetica-Bold", fontSize=15, leading=18, textColor=INK),
    "issuer_sub": ParagraphStyle("issuer_sub", fontName="Helvetica", fontSize=8.5, leading=11, textColor=MUTED),
    "title": ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=12.5, leading=15, textColor=INK),
    "subtitle": ParagraphStyle("subtitle", fontName="Helvetica", fontSize=9, leading=12, textColor=MUTED),
    "heading": ParagraphStyle("heading", fontName="Helvetica-Bold", fontSize=9, leading=11, textColor=INK),
    "label": ParagraphStyle("label", fontName="Helvetica", fontSize=8, leading=10, textColor=MUTED),
    "value": ParagraphStyle("value", fontName="Helvetica", fontSize=8.5, leading=10.5, textColor=INK),
    "body": ParagraphStyle("body", fontName="Helvetica", fontSize=8.5, leading=11.5, textColor=INK, spaceAfter=4),
    "cell": ParagraphStyle("cell", fontName="Helvetica", fontSize=7.5, leading=9, textColor=INK),
    "cell_r": ParagraphStyle("cell_r", fontName="Helvetica", fontSize=7.5, leading=9, textColor=INK, alignment=TA_RIGHT),
    "cell_b": ParagraphStyle("cell_b", fontName="Helvetica-Bold", fontSize=7.5, leading=9, textColor=INK),
    "cell_br": ParagraphStyle(
        "cell_br", fontName="Helvetica-Bold", fontSize=7.5, leading=9, textColor=INK, alignment=TA_RIGHT
    ),
    "small": ParagraphStyle("small", fontName="Helvetica", fontSize=7.5, leading=9.5, textColor=MUTED),
}

CONTENT_WIDTH = LETTER[0] - 1.3 * inch


def p(text: str, style: str = "value") -> Paragraph:
    return Paragraph(escape(str(text)), STYLES[style])


def footer_painter(issuer: str):
    def paint(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(MUTED)
        canvas.drawString(0.65 * inch, 0.45 * inch, SYNTHETIC_FOOTER)
        canvas.drawRightString(LETTER[0] - 0.65 * inch, 0.45 * inch, f"{issuer} - Page {doc.page}")
        canvas.restoreState()

    return paint


def render_pdf(story: list, *, title: str, author: str, issuer: str) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=LETTER,
        leftMargin=0.65 * inch,
        rightMargin=0.65 * inch,
        topMargin=0.6 * inch,
        bottomMargin=0.75 * inch,
        title=title,
        author=author,
        subject="Synthetic demonstration document",
        creator="Contoso claims demo evidence builder",
    )
    paint = footer_painter(issuer)
    doc.build(story, onFirstPage=paint, onLaterPages=paint)
    return buffer.getvalue()


def letterhead(issuer: str, issuer_lines: list[str], title: str, subtitle: str) -> list:
    left = [p(issuer, "issuer")] + [p(line, "issuer_sub") for line in issuer_lines]
    right = [p(title, "title"), p(subtitle, "subtitle")]
    table = Table([[left, right]], colWidths=[CONTENT_WIDTH * 0.52, CONTENT_WIDTH * 0.48])
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, 0), 1.2, INK),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return [table, Spacer(1, 8)]


def field_grid(pairs: list, columns: int = 1, label_ratio: float = 0.34) -> Table:
    """Label/value pairs laid out in one or more column pairs."""
    col_width = CONTENT_WIDTH / columns
    widths = []
    for _ in range(columns):
        widths += [col_width * label_ratio, col_width * (1 - label_ratio)]
    rows = []
    for start in range(0, len(pairs), columns):
        row = []
        for label, value in pairs[start : start + columns]:
            row += [p(label, "label"), p(value, "value")]
        row += [""] * (2 * columns - len(row))
        rows.append(row)
    table = Table(rows, colWidths=widths)
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, -1), 0.25, RULE),
                ("TOPPADDING", (0, 0), (-1, -1), 2.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return table


def section_band(text: str) -> Table:
    table = Table([[p(text, "heading")]], colWidths=[CONTENT_WIDTH])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), BAND),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def section(heading: str, body) -> KeepTogether:
    items = body if isinstance(body, list) else [body]
    return KeepTogether([section_band(heading), Spacer(1, 2)] + items + [Spacer(1, 7)])


def scene_diagram(spec: dict) -> Drawing:
    drawing = Drawing(spec["width"], spec["height"])
    drawing.add(Rect(0, 0, spec["width"], spec["height"], strokeColor=RULE, fillColor=None, strokeWidth=0.5))
    for shape in spec["shapes"]:
        kind = shape["kind"]
        if kind == "line":
            line = Line(shape["x1"], shape["y1"], shape["x2"], shape["y2"], strokeColor=MUTED, strokeWidth=0.8)
            if shape.get("dash"):
                line.strokeDashArray = [3, 2]
            drawing.add(line)
        elif kind == "rect":
            drawing.add(
                Rect(shape["x"], shape["y"], shape["w"], shape["h"], strokeColor=INK, fillColor=BAND, strokeWidth=1)
            )
            drawing.add(
                String(
                    shape["x"] + shape["w"] / 2,
                    shape["y"] + shape["h"] / 2 - 4,
                    shape["label"],
                    fontName="Helvetica-Bold",
                    fontSize=11,
                    textAnchor="middle",
                    fillColor=INK,
                )
            )
        elif kind == "arrow":
            x1, y1, x2, y2 = shape["x1"], shape["y1"], shape["x2"], shape["y2"]
            drawing.add(Line(x1, y1, x2, y2, strokeColor=INK, strokeWidth=1.2))
            length = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
            ux, uy = (x2 - x1) / length, (y2 - y1) / length
            px, py = -uy, ux
            head = [x2, y2, x2 - 7 * ux + 3.5 * px, y2 - 7 * uy + 3.5 * py, x2 - 7 * ux - 3.5 * px, y2 - 7 * uy - 3.5 * py]
            drawing.add(Polygon(head, fillColor=INK, strokeColor=INK, strokeWidth=0.5))
        elif kind == "marker":
            x, y = shape["x"], shape["y"]
            for dx in (-5, 5):
                drawing.add(Line(x - dx, y - 5, x + dx, y + 5, strokeColor=INK, strokeWidth=1.6))
        elif kind == "north":
            x, y = shape["x"], shape["y"]
            drawing.add(Line(x, y, x, y + 28, strokeColor=INK, strokeWidth=1))
            drawing.add(Polygon([x, y + 34, x - 4, y + 25, x + 4, y + 25], fillColor=INK, strokeColor=INK))
            drawing.add(String(x, y + 38, "N", fontName="Helvetica-Bold", fontSize=9, textAnchor="middle"))
        elif kind == "text":
            drawing.add(String(shape["x"], shape["y"], shape["text"], fontName="Helvetica", fontSize=7.5, fillColor=MUTED))
        else:
            raise BuildError(f"unknown diagram shape {kind!r}")
    return drawing


def build_claim_form(source: dict) -> bytes:
    story = letterhead(source["issuer"], ["Personal auto claims"], source["title"], source["subtitle"])
    story.append(field_grid(source["header"], columns=2, label_ratio=0.36))
    story.append(Spacer(1, 10))
    for sec in source["sections"]:
        if "paragraph" in sec:
            story.append(section(sec["heading"], p(sec["paragraph"], "body")))
        else:
            story.append(section(sec["heading"], field_grid(sec["fields"], label_ratio=0.4)))
    story.append(section("Declaration", [p(source["declaration"], "body"), Spacer(1, 4), field_grid(source["signature"], label_ratio=0.4)]))
    return render_pdf(story, title=f"{source['title']} - {source['claimId']}", author=source["issuer"], issuer=source["issuer"])


def build_police_report(source: dict) -> bytes:
    story = letterhead(source["issuer"], ["Patrol Division - Records Section"], source["title"], source["subtitle"])
    story.append(field_grid(source["header"], columns=2, label_ratio=0.36))
    story.append(Spacer(1, 10))
    for sec in source["sections"]:
        story.append(section(sec["heading"], field_grid(sec["fields"], label_ratio=0.3)))
    for unit in source["units"]:
        story.append(section(unit["unit"], field_grid(unit["fields"], label_ratio=0.3)))
    diagram = source["diagram"]
    story.append(section("Scene diagram", [scene_diagram(diagram), Spacer(1, 3), p(diagram["caption"], "small")]))
    story.append(section("Statements", field_grid(source["statements"], label_ratio=0.22)))
    story.append(section("Officer narrative", [p(text, "body") for text in source["narrative"]]))
    story.append(section("Findings", field_grid(source["findings"], label_ratio=0.4)))
    story.append(section("Report approval", field_grid(source["signature"], label_ratio=0.3)))
    return render_pdf(
        story,
        title=f"{source['title']} {source['header'][0][1]}",
        author=source["issuer"],
        issuer=source["issuer"],
    )


def build_repair_estimate(source: dict, calc: dict, *, claim: dict, customer: dict, policy: dict, vehicle: dict, facility: dict) -> bytes:
    address = facility["address"]
    story = letterhead(
        facility["name"],
        [f"{address['street']}, {address['city']}, {address['state']} {address['postalCode']}", f"Phone {facility['phone']}"],
        source["estimateType"].upper(),
        f"Estimate {source['estimateId']}",
    )
    inspection = source["inspection"]
    story.append(
        field_grid(
            [
                ["Estimate ID", source["estimateId"]],
                ["Estimate date", source["estimateDate"]],
                ["Estimator", source["estimator"]],
                ["Insurer", "Contoso Insurance"],
                ["Claim number", claim["claimId"]],
                ["Policy number", policy["policyId"]],
                ["Owner", customer["fullName"]],
                ["Owner phone", customer["phone"]],
                ["Inspection", f"{inspection['type']}, {inspection['date']}"],
                ["Inspection location", inspection["location"]],
            ],
            columns=2,
            label_ratio=0.36,
        )
    )
    story.append(Spacer(1, 8))
    veh = source["vehicle"]
    story.append(
        section(
            "Vehicle",
            [
                field_grid(
                    [
                        ["Vehicle", f"{vehicle['year']} {vehicle['make']} {vehicle['model']} {vehicle['trim']} {vehicle['drivetrain']}"],
                        ["Body style", vehicle["bodyStyle"]],
                        ["VIN", vehicle["vin"]],
                        ["Exterior color", vehicle["exteriorColor"]],
                        ["Odometer", f"{veh['odometer']:,}"],
                        ["Production date", veh["productionDate"]],
                        ["Condition", veh["condition"]],
                        ["Point of impact", veh["pointOfImpact"]],
                    ],
                    columns=2,
                    label_ratio=0.36,
                ),
                Spacer(1, 3),
                p("Options: " + ", ".join(vehicle["equipment"]), "small"),
            ],
        )
    )

    header = ["Line", "Oper", "Description", "Part number", "Qty", "Price", "Labor", "Paint", "Line total"]
    widths = [0.045, 0.06, 0.345, 0.135, 0.04, 0.095, 0.1, 0.06, 0.12]
    rows = [[p(h, "cell_b" if i < 4 else "cell_br") for i, h in enumerate(header)]]
    styles = [
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, INK),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 1.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
    ]
    current_section = None
    for line in calc["lines"]:
        if line["section"] != current_section:
            current_section = line["section"]
            rows.append([p(current_section, "cell_b")] + [""] * 8)
            r = len(rows) - 1
            styles += [("SPAN", (0, r), (-1, r)), ("BACKGROUND", (0, r), (-1, r), BAND)]
        labor = f"{hours(line['laborHours'])} {line['laborType']}" if line["laborHours"] else ("Incl." if line["partType"] == "OEM" else "")
        rows.append(
            [
                p(line["line"], "cell"),
                p(line["operation"], "cell"),
                p(line["description"], "cell"),
                p(line["partNumber"] or ("Sublet" if line["partType"] == "Sublet" else ""), "cell"),
                p(line["quantity"] or "", "cell_r"),
                p(money(line["price"]) if line["price"] else "", "cell_r"),
                p(labor, "cell_r"),
                p(hours(line["refinishHours"]) if line["refinishHours"] else "", "cell_r"),
                p(money(line["amount"]), "cell_r"),
            ]
        )
    lines_table = Table(rows, colWidths=[CONTENT_WIDTH * w for w in widths], repeatRows=1)
    lines_table.setStyle(TableStyle(styles))
    story.append(section_band("Estimate lines"))
    story.append(Spacer(1, 2))
    story.append(lines_table)
    story.append(Spacer(1, 10))

    rates = calc["rates"]
    totals = [["Parts (OEM)", "", money(calc["parts"])]]
    for key in LABOR_RATE_FIELDS:
        if calc["laborHours"][key]:
            totals.append(
                [LABOR_NAMES[key], f"{hours(calc['laborHours'][key])} hrs @ ${money(rates['labor'][key])}", money(calc["laborAmounts"][key])]
            )
    totals += [
        ["Paint labor", f"{hours(calc['refinishHours'])} hrs @ ${money(rates['refinish'])}", money(calc["refinishAmount"])],
        ["Paint materials", f"{hours(calc['refinishHours'])} hrs @ ${money(rates['materials'])}", money(calc["paintMaterials"])],
        ["Sublet repairs", "", money(calc["sublet"])],
        ["Miscellaneous materials", "", money(calc["materials"])],
        ["Subtotal", "", money(calc["subtotal"])],
        [f"Sales tax ({source['salesTax']['jurisdiction']})", percent(calc["taxRate"]), money(calc["tax"])],
        ["Grand total", "", money(calc["grandTotal"])],
    ]
    total_rows = [[p(a, "cell"), p(b, "cell"), p(c, "cell_r")] for a, b, c in totals[:-1]]
    total_rows.append([p(totals[-1][0], "cell_b"), "", Paragraph(f"<b>${money(calc['grandTotal'])}</b>", STYLES["cell_r"])])
    totals_table = Table(total_rows, colWidths=[CONTENT_WIDTH * 0.22, CONTENT_WIDTH * 0.2, CONTENT_WIDTH * 0.13], hAlign="RIGHT")
    totals_table.setStyle(
        TableStyle(
            [
                ("LINEBELOW", (0, 0), (-1, -1), 0.25, RULE),
                ("LINEABOVE", (0, -3), (-1, -3), 0.8, INK),
                ("LINEABOVE", (0, -1), (-1, -1), 0.8, INK),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    story.append(KeepTogether([section_band("Estimate totals"), Spacer(1, 2), totals_table]))
    story.append(Spacer(1, 10))
    story.append(section("Notes", [p(f"{i}. {note}", "small") for i, note in enumerate(source["notes"], start=1)]))
    story.append(field_grid([["Prepared by", f"{source['estimator']}, {facility['name']}"], ["Date", source["estimateDate"]]], label_ratio=0.3))
    return render_pdf(story, title=f"Repair estimate {source['estimateId']}", author=facility["name"], issuer=facility["name"])


# ---------------------------------------------------------------------------
# Photographs
# ---------------------------------------------------------------------------


def import_photo(source_png: Path, expected_sha256: str, destination: Path) -> None:
    raw = source_png.read_bytes()
    actual = sha256_bytes(raw)
    if actual != expected_sha256:
        raise BuildError(f"{source_png.name}: SHA-256 {actual} does not match provenance {expected_sha256}")
    with Image.open(io.BytesIO(raw)) as image:
        rgb = image.convert("RGB")
        buffer = io.BytesIO()
        rgb.save(buffer, format="JPEG", quality=JPEG_QUALITY, subsampling=2, optimize=False, progressive=False)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(buffer.getvalue())


def find_source_png(directory: Path, sha256: str) -> Path:
    for candidate in sorted(directory.glob("*.png")):
        if sha256_bytes(candidate.read_bytes()) == sha256:
            return candidate
    raise BuildError(f"no PNG with SHA-256 {sha256} in {directory}")


# ---------------------------------------------------------------------------
# Claim build
# ---------------------------------------------------------------------------


SOURCE_DOCUMENT_TYPES = {
    "claim-form": "Claim form",
    "police-report": "Police report",
    "repair-estimate": "Repair estimate",
}


def load_sources(claim_dir: Path, claim: dict) -> dict:
    """Load the source files a claim needs.

    A claim form and photo provenance are always required. A police report or repair
    estimate source is required exactly when the claim's document index lists one.
    """
    listed_types = {d["documentType"] for d in claim["documents"]}
    sources = {}
    for name in ("claim-form", "police-report", "repair-estimate", "photos"):
        path = claim_dir / f"{name}.json"
        expected = name in ("claim-form", "photos") or SOURCE_DOCUMENT_TYPES[name] in listed_types
        if expected and not path.exists():
            raise BuildError(f"{claim_dir.name}: missing source {name}.json")
        if not expected and path.exists():
            raise BuildError(f"{claim_dir.name}: {name}.json has no matching document in the claim record")
        if expected:
            sources[name] = load_json(path)
    return sources


def check_consistency(claim_id: str, sources: dict, data: dict) -> None:
    claim = data["claims"].get(claim_id)
    if claim is None:
        raise BuildError(f"{claim_id}: no claim record in data/claims.json")
    estimate = sources.get("repair-estimate")
    if estimate is not None:
        if claim["estimate"] is None:
            raise BuildError(f"{claim_id}: estimate source but the claim record has no estimate")
        if estimate["claimId"] != claim_id or estimate["estimateId"] != claim["estimate"]["estimateId"]:
            raise BuildError(f"{claim_id}: estimate source does not match the claim's estimate reference")
        if estimate["estimateDate"] != claim["estimate"]["estimateDate"]:
            raise BuildError(f"{claim_id}: estimate date differs from the claim record")
        if dec(estimate["statedGrandTotal"]) != dec(claim["estimate"]["grossAmount"]):
            raise BuildError(f"{claim_id}: estimate total differs from the claim record")
    for key in SOURCE_DOCUMENT_TYPES:
        if key in sources and sources[key]["claimId"] != claim_id:
            raise BuildError(f"{claim_id}: {key} source names claim {sources[key]['claimId']}")
    if sources["photos"]["claimId"] != claim_id:
        raise BuildError(f"{claim_id}: photos source names claim {sources['photos']['claimId']}")


def build_claim(claim_dir: Path, data: dict, photo_source_dir: Path | None) -> dict[Path, bytes]:
    """Return {output path: bytes} for every generated file of one claim."""
    claim_id = claim_dir.name
    if claim_id not in data["claims"]:
        raise BuildError(f"{claim_id}: no claim record in data/claims.json")
    sources = load_sources(claim_dir, data["claims"][claim_id])
    check_consistency(claim_id, sources, data)

    claim = data["claims"][claim_id]
    out_dir = EVIDENCE_DIR / claim_id

    outputs: dict[Path, bytes] = {
        out_dir / sources["claim-form"]["fileName"]: build_claim_form(sources["claim-form"]),
    }
    if "police-report" in sources:
        outputs[out_dir / sources["police-report"]["fileName"]] = build_police_report(sources["police-report"])
    estimate = sources.get("repair-estimate")
    if estimate is not None:
        facility = data["facilities"][claim["estimate"]["repairFacilityId"]]
        outputs[out_dir / estimate["fileName"]] = build_repair_estimate(
            estimate,
            compute_estimate(estimate, facility),
            claim=claim,
            customer=data["customers"][claim["customerId"]],
            policy=data["policies"][claim["policyId"]],
            vehicle=data["vehicles"][claim["vehicleId"]],
            facility=facility,
        )

    if photo_source_dir is not None:
        for photo in sources["photos"]["photos"]:
            png = find_source_png(photo_source_dir, photo["sourceSha256"])
            import_photo(png, photo["sourceSha256"], out_dir / photo["fileName"])

    files_by_doc = {sources[key]["documentId"]: sources[key]["fileName"] for key in SOURCE_DOCUMENT_TYPES if key in sources}
    for photo in sources["photos"]["photos"]:
        files_by_doc[photo["documentId"]] = photo["fileName"]

    claim_docs = {d["documentId"]: d for d in claim["documents"]}
    if set(files_by_doc) != set(claim_docs):
        raise BuildError(
            f"{claim_id}: evidence files {sorted(files_by_doc)} do not match claim documents {sorted(claim_docs)}"
        )
    photo_titles = {ph["documentId"]: ph["title"] for ph in sources["photos"]["photos"]}
    for doc_id, title in photo_titles.items():
        if claim_docs[doc_id]["title"] != title:
            raise BuildError(f"{doc_id}: photo title differs from the claim document index")

    manifest_docs = []
    for doc in claim["documents"]:
        file_name = files_by_doc[doc["documentId"]]
        path = out_dir / file_name
        content = outputs[path] if path in outputs else path.read_bytes() if path.exists() else None
        if content is None:
            raise BuildError(f"{doc['documentId']}: {path.relative_to(ROOT).as_posix()} is missing")
        entry = {
            "documentId": doc["documentId"],
            "documentType": doc["documentType"],
            "title": doc["title"],
            "source": doc["source"],
            "receivedAt": doc["receivedAt"],
            "fileName": file_name,
        }
        if file_name.endswith(".pdf"):
            entry["mediaType"] = "application/pdf"
            entry["pageCount"] = len(PdfReader(io.BytesIO(content)).pages)
        elif file_name.endswith(".jpg"):
            entry["mediaType"] = "image/jpeg"
            with Image.open(io.BytesIO(content)) as image:
                entry["widthPx"], entry["heightPx"] = image.size
        else:
            raise BuildError(f"{file_name}: unsupported evidence file type")
        entry["bytes"] = len(content)
        entry["sha256"] = sha256_bytes(content)
        manifest_docs.append(entry)

    manifest = {
        "claimId": claim_id,
        "synthetic": True,
        "notice": MANIFEST_NOTICE,
        "documents": manifest_docs,
    }
    outputs[out_dir / "evidence-manifest.json"] = dumps_json(manifest)
    return outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="verify committed evidence files are current; write nothing")
    parser.add_argument("--import-photos", type=Path, metavar="DIR", help="import source PNGs (matched by SHA-256) from DIR")
    parser.add_argument("--claim", metavar="CLAIM_ID", help="build only this claim's evidence folder")
    args = parser.parse_args(argv)
    if args.check and args.import_photos:
        parser.error("--check and --import-photos cannot be combined")

    data = load_data()
    claim_dirs = sorted(d for d in SOURCE_DIR.iterdir() if d.is_dir() and (args.claim is None or d.name == args.claim))
    if not claim_dirs:
        parser.error(f"no evidence source folder for {args.claim}")
    stale = []
    try:
        for claim_dir in claim_dirs:
            outputs = build_claim(claim_dir, data, args.import_photos)
            for path, content in outputs.items():
                rel = path.relative_to(ROOT).as_posix()
                if args.check:
                    if not path.exists() or path.read_bytes() != content:
                        stale.append(rel)
                else:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(content)
                    print(f"wrote {rel} ({len(content):,} bytes)")
    except BuildError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.check:
        if stale:
            print("Evidence is out of date:", *stale, sep="\n  ", file=sys.stderr)
            return 1
        print(f"Evidence is current ({len(claim_dirs)} claim folder(s)).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
