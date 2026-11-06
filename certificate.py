"""Print-ready landscape certificates with the supplied, unmodified signature."""
from calendar import monthrange
from datetime import date
from io import BytesIO
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.utils import simpleSplit

ROOT = Path(__file__).parent
LOGO = ROOT / "static/logo.png"
SIGNATURE = ROOT / "static/IMG_8836.jpg"



def course_duration(data):
    """Elapsed calendar months and days; do not round partial months up."""
    start, end = (date.fromisoformat(data[k]) for k in ("joined", "completed"))
    months = (end.year-start.year)*12 + end.month-start.month
    def anniversary(count):
        year, month = divmod(start.year*12 + start.month-1 + count, 12)
        return date(year, month+1, min(start.day, monthrange(year, month+1)[1]))
    if anniversary(months) > end:
        months -= 1
    days = (end-anniversary(months)).days
    parts = []
    if months:
        parts.append(f"{months} month" + ("s" if months != 1 else ""))
    if days:
        parts.append(f"{days} day" + ("s" if days != 1 else ""))
    return " and ".join(parts) or "1 day"


def completion_statement(data):
    return data.get("summary") or "This certificate recognizes the successful completion of the course and the learner's commitment to continued learning."

def certificate(data, identifier=None):
    stream = BytesIO()
    width, height = landscape(A4)
    page = Canvas(stream, pagesize=(width, height))
    page.setTitle("Crafting Brain | Certificate of Completion")
    page.setAuthor("Crafting Brain")
    ink, gold, muted = map(HexColor, ("#173b3b", "#ad8845", "#627171"))
    page.setFillColor(HexColor("#ffffff"))
    page.rect(0, 0, width, height, fill=1, stroke=0)

    # An architectural frame with restrained gold detailing.
    page.setFillColor(ink)
    page.rect(0, 0, 22, height, fill=1, stroke=0)
    page.rect(width-22, 0, 22, height, fill=1, stroke=0)
    page.setStrokeColor(gold)
    page.setLineWidth(.7)
    page.rect(35, 29, width-70, height-58)
    page.setStrokeColor(HexColor("#e4ded1"))
    page.rect(41, 35, width-82, height-70)
    for x, direction in ((35, 1), (width-35, -1)):
        for y, vertical in ((29, 1), (height-29, -1)):
            page.setStrokeColor(gold)
            page.setLineWidth(2.5)
            page.line(x, y, x+direction*32, y)
            page.line(x, y, x, y+vertical*32)

    def center(value, y, face, size, color=ink):
        page.setFont(face, size)
        page.setFillColor(color)
        page.drawCentredString(width/2, y, value)

    def lines(value, y, face, size, max_width, leading, max_lines=2):
        # Wrap long names and custom courses without shrinking them to fine print.
        while size >= 12:
            wrapped = simpleSplit(value, face, size, max_width)
            if len(wrapped) <= max_lines and all(page.stringWidth(v, face, size) <= max_width for v in wrapped):
                break
            size -= 1
        if size < 12:
            size = 12
            wrapped, current = [], ""
            for character in value:
                if page.stringWidth(current + character, face, size) > max_width:
                    wrapped.append(current)
                    current = ""
                current += character
            if current:
                wrapped.append(current)
        for i, line in enumerate(wrapped):
            center(line, y-i*leading, face, size)

    page.drawImage(str(LOGO), 65, 474, 64, 64)
    page.setFillColor(ink)
    page.setFont("Times-Bold", 23)
    page.drawString(143, 510, "Crafting Brain")
    page.setFillColor(muted)
    page.setFont("Helvetica", 9)
    page.drawString(144, 490, "LEARNING  /  GROWTH  /  ACHIEVEMENT")
    page.setStrokeColor(gold)
    page.setLineWidth(.7)
    page.line(65, 457, width-65, 457)

    center("CERTIFICATE", 412, "Times-Roman", 44)
    center("O F   C O M P L E T I O N", 386, "Helvetica", 12, gold)
    center("THIS CERTIFICATE IS PROUDLY PRESENTED TO", 354, "Helvetica", 9, muted)
    lines(data["name"], 322, "Times-Italic", 34, width-160, 29)
    page.setStrokeColor(gold)
    page.line(width/2-95, 281, width/2+95, 281)
    center("for successfully completing", 260, "Times-Roman", 15, muted)
    lines(data["course"], 234, "Helvetica-Bold", 22, width-160, 23)
    dates = [date.fromisoformat(data[k]).strftime("%d %B %Y") for k in ("joined", "completed")]
    center("Duration: " + course_duration(data) + "   |   " + " - ".join(dates), 190, "Helvetica", 10, muted)
    statement_size = 10
    statement = simpleSplit(completion_statement(data), "Times-Roman", statement_size, width-180)
    while len(statement) > 3:
        statement_size -= .5
        statement = simpleSplit(completion_statement(data), "Times-Roman", statement_size, width-180)
    for i, line in enumerate(statement):
        center(line, 171-i*12, "Times-Roman", statement_size, muted)

    page.setFillColor(ink)
    page.setFont("Helvetica-Bold", 8)
    page.drawString(67, 100, "CERTIFICATE ID")
    page.setFont("Courier", 8)
    page.drawString(67, 83, identifier or "DRAFT / PREVIEW")
    page.setFillColor(muted)
    page.setFont("Helvetica", 8)
    page.drawString(67, 65, "Issued by Crafting Brain")

    # White certificate stock keeps the original signature image seamless.
    page.drawImage(str(SIGNATURE), width-240, 97, 150, 30,
                   preserveAspectRatio=True, anchor="c")
    page.setStrokeColor(gold)
    page.line(width-260, 95, width-73, 95)
    page.setFillColor(ink)
    page.setFont("Helvetica-Bold", 9)
    page.drawCentredString(width-166.5, 79, "AUTHORIZED SIGNATURE")
    page.setFillColor(muted)
    page.setFont("Helvetica", 8)
    page.drawCentredString(width-166.5, 64, "Crafting Brain")
    page.showPage()
    page.save()
    return stream.getvalue()
