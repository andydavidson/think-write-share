"""
PDF export for Think–Write–Share session reports.

Uses ReportLab (pure Python, no system library dependencies).
Layout is built with Platypus so text reflows correctly across pages.
"""
import xml.sax.saxutils as saxutils
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ---------------------------------------------------------------------------
# Colour palette — matches the app's CSS variables
# ---------------------------------------------------------------------------
_PRIMARY = colors.HexColor("#2a6496")
_TEXT    = colors.HexColor("#1a1e2e")
_MUTED   = colors.HexColor("#5a6378")
_BG      = colors.HexColor("#f5f6f8")
_BORDER  = colors.HexColor("#d8dde6")

_LEFT_MARGIN  = 2.5 * cm
_RIGHT_MARGIN = 2.5 * cm
_TOP_MARGIN   = 3.0 * cm
_BOTTOM_MARGIN = 2.5 * cm
_CONTENT_W = A4[0] - _LEFT_MARGIN - _RIGHT_MARGIN


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rl(text: str) -> str:
    """
    Escape arbitrary text for use inside a ReportLab Paragraph (XML context).
    Preserves newlines as <br/> tags and encodes non-Latin-1 characters as
    XML character references so they display as-is rather than crashing.
    """
    # 1. Escape XML special characters first
    text = saxutils.escape(str(text))
    # 2. Encode characters outside Latin-1 as XML entities
    text = "".join(
        f"&#x{ord(c):X};" if ord(c) > 127 else c for c in text
    )
    # 3. Preserve line breaks
    text = text.replace("\n", "<br/>")
    return text


def _ps(name: str, **kw) -> ParagraphStyle:
    """Build a ParagraphStyle with sensible defaults."""
    defaults = dict(
        fontName="Times-Roman",
        fontSize=11,
        leading=18,
        textColor=_TEXT,
        spaceAfter=0,
        spaceBefore=0,
        alignment=TA_LEFT,
    )
    defaults.update(kw)
    return ParagraphStyle(name, **defaults)


def _card(rows, *, left_accent=None, background=None, box_border=None):
    """
    Wrap a list of [Paragraph] rows in a full-width Table styled as a card.
    """
    commands = [
        ("LEFTPADDING",   (0, 0), (-1, -1), 11),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 11),
        ("TOPPADDING",    (0, 0), (-1,  0),  9),
        ("TOPPADDING",    (0, 1), (-1, -1),  4),
        ("BOTTOMPADDING", (0,-1), (-1, -1), 11),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
    ]
    if background:
        commands.append(("BACKGROUND", (0, 0), (-1, -1), background))
    if box_border:
        commands.append(("BOX", (0, 0), (-1, -1), 0.5, box_border))
    if left_accent:
        commands.append(("LINEBEFORE", (0, 0), (0, -1), 3, left_accent))

    t = Table([[row] for row in rows], colWidths=[_CONTENT_W])
    t.setStyle(TableStyle(commands))
    return t


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_pdf(session, answers, created_fmt: str, closed_fmt: str) -> bytes:
    """
    Render a session report as PDF bytes.

    Parameters
    ----------
    session     sqlite3.Row (or dict) for the session
    answers     list of sqlite3.Row with answer_text
    created_fmt human-readable creation timestamp
    closed_fmt  human-readable close timestamp
    """
    slug         = session["slug"]
    question     = session["question"]
    answer_count = len(answers)

    # --- Styles -----------------------------------------------------------------
    s_title   = _ps("Title",   fontSize=20, leading=26)
    s_label   = _ps("Label",   fontSize=7,  leading=10,
                    fontName="Helvetica-Bold", textColor=_MUTED)
    s_question= _ps("Q",       fontSize=14, leading=22)
    s_meta_k  = _ps("MetaK",   fontSize=9,  leading=14,
                    fontName="Helvetica-Bold")
    s_meta_v  = _ps("MetaV",   fontSize=9,  leading=14,
                    fontName="Helvetica",    textColor=_MUTED)
    s_section = _ps("Section", fontSize=7.5, leading=10,
                    fontName="Helvetica-Bold", textColor=_MUTED)
    s_ans_num = _ps("AnsNum",  fontSize=7,  leading=10,
                    fontName="Helvetica-Bold", textColor=_PRIMARY)
    s_ans_txt = _ps("AnsTxt",  fontSize=11, leading=18)
    s_none    = _ps("None",    fontSize=10, leading=16,
                    fontName="Times-Italic", textColor=_MUTED)

    # --- Page header / footer (drawn on canvas, outside the flow) ---------------
    def _header_footer(canvas, doc):
        canvas.saveState()
        w, h = A4
        lm, rm = _LEFT_MARGIN, _RIGHT_MARGIN
        bm = _BOTTOM_MARGIN

        # Top rule + labels
        canvas.setStrokeColor(_PRIMARY)
        canvas.setLineWidth(1.2)
        canvas.line(lm, h - 2.0 * cm, w - rm, h - 2.0 * cm)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(_MUTED)
        canvas.drawString(lm,         h - 2.0 * cm + 4, "Think\u2013Write\u2013Share")
        canvas.drawRightString(w - rm, h - 2.0 * cm + 4, "Session Report")

        # Bottom rule + labels
        canvas.setStrokeColor(_BORDER)
        canvas.setLineWidth(0.4)
        canvas.line(lm, bm - 5, w - rm, bm - 5)
        canvas.setFont("Courier", 7.5)
        canvas.setFillColor(_MUTED)
        canvas.drawString(lm, bm - 13, f"/s/{slug}")
        canvas.setFont("Helvetica", 7.5)
        canvas.drawRightString(w - rm, bm - 13, f"Page {doc.page}")

        canvas.restoreState()

    # --- Build story ------------------------------------------------------------
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=_LEFT_MARGIN,
        rightMargin=_RIGHT_MARGIN,
        topMargin=_TOP_MARGIN,
        bottomMargin=_BOTTOM_MARGIN,
    )

    story = []

    # Title + rule
    story.append(Paragraph("Think\u2013Write\u2013Share", s_title))
    story.append(Spacer(1, 6))
    story.append(HRFlowable(width="100%", thickness=1.5, color=_PRIMARY, spaceAfter=18))

    # Question card
    story.append(_card(
        [Paragraph("QUESTION", s_label), Paragraph(_rl(question), s_question)],
        left_accent=_PRIMARY,
        background=_BG,
    ))
    story.append(Spacer(1, 18))

    # Metadata two-column table
    key_w = 2.8 * cm
    meta = Table(
        [
            [Paragraph("Session",   s_meta_k), Paragraph(f"/s/{slug}",     s_meta_v)],
            [Paragraph("Created",   s_meta_k), Paragraph(_rl(created_fmt), s_meta_v)],
            [Paragraph("Closed",    s_meta_k), Paragraph(_rl(closed_fmt),  s_meta_v)],
            [Paragraph("Responses", s_meta_k), Paragraph(str(answer_count), s_meta_v)],
        ],
        colWidths=[key_w, _CONTENT_W - key_w],
    )
    meta.setStyle(TableStyle([
        ("TOPPADDING",    (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING",   (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(meta)
    story.append(Spacer(1, 22))

    # Section heading
    story.append(Paragraph("RESPONSES", s_section))
    story.append(HRFlowable(width="100%", thickness=0.5, color=_BORDER, spaceAfter=10))

    if answers:
        for i, row in enumerate(answers, 1):
            card = _card(
                [
                    Paragraph(f"RESPONSE {i}", s_ans_num),
                    Paragraph(_rl(row["answer_text"]), s_ans_txt),
                ],
                left_accent=_PRIMARY,
                box_border=_BORDER,
            )
            story.append(KeepTogether([card, Spacer(1, 9)]))
    else:
        story.append(Paragraph("No responses were submitted.", s_none))

    doc.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)
    return buf.getvalue()
