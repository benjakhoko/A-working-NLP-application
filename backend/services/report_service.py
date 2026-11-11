"""PDF report generation with ReportLab."""
from __future__ import annotations

import io
from datetime import datetime
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from backend.models import ANALYSIS_TYPES, Analysis, Document, User
from backend.services.nlp.preprocessing import text_statistics, truncate

NAVY = colors.HexColor("#0F172A")
ACCENT = colors.HexColor("#2563EB")
MUTED = colors.HexColor("#64748B")
LINE = colors.HexColor("#E2E8F0")
SURFACE = colors.HexColor("#F8FAFC")

_FONT = "Helvetica"
_BOLD = "Helvetica-Bold"
try:  # Better Unicode coverage on Windows; ReportLab's core fonts are Latin-1 only.
    pdfmetrics.registerFont(TTFont("ReportArial", "C:/Windows/Fonts/arial.ttf"))
    pdfmetrics.registerFont(TTFont("ReportArial-Bold", "C:/Windows/Fonts/arialbd.ttf"))
    _FONT, _BOLD = "ReportArial", "ReportArial-Bold"
except Exception:  # pragma: no cover - platform dependent
    pass


def _styles() -> dict:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("Title", parent=base["Title"], fontName=_BOLD, fontSize=20, leading=25, textColor=NAVY, alignment=TA_LEFT, spaceAfter=4),
        "subtitle": ParagraphStyle("Subtitle", fontName=_FONT, fontSize=9.5, leading=14, textColor=MUTED, spaceAfter=14),
        "h2": ParagraphStyle("H2", fontName=_BOLD, fontSize=12.5, leading=17, textColor=NAVY, spaceBefore=14, spaceAfter=6),
        "h3": ParagraphStyle("H3", fontName=_BOLD, fontSize=10, leading=14, textColor=ACCENT, spaceBefore=8, spaceAfter=3),
        "body": ParagraphStyle("Body", fontName=_FONT, fontSize=9.5, leading=14, textColor=colors.HexColor("#1E293B")),
        "small": ParagraphStyle("Small", fontName=_FONT, fontSize=8, leading=11, textColor=MUTED),
        "cell": ParagraphStyle("Cell", fontName=_FONT, fontSize=8.5, leading=12, textColor=colors.HexColor("#1E293B")),
        "cellbold": ParagraphStyle("CellBold", fontName=_BOLD, fontSize=8.5, leading=12, textColor=NAVY),
        "quote": ParagraphStyle("Quote", fontName=_FONT, fontSize=9.5, leading=15, textColor=NAVY, leftIndent=8, rightIndent=8, borderPadding=8, backColor=SURFACE),
    }


def _esc(value: object) -> str:
    return escape(str(value if value is not None else "")).replace("\n", "<br/>")


def _p(text: object, style) -> Paragraph:
    return Paragraph(_esc(text), style)


def _kv_table(rows: list[tuple[str, str]], styles: dict) -> Table:
    data = [[Paragraph(_esc(key), styles["cellbold"]), Paragraph(_esc(value), styles["cell"])] for key, value in rows]
    table = Table(data, colWidths=[42 * mm, 120 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), SURFACE),
                ("GRID", (0, 0), (-1, -1), 0.4, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def _page_footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.5)
    canvas.line(20 * mm, 16 * mm, A4[0] - 20 * mm, 16 * mm)
    canvas.setFont(_FONT, 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(20 * mm, 11 * mm, "Intelligent Text Analysis System · Academic project report")
    canvas.drawRightString(A4[0] - 20 * mm, 11 * mm, f"Page {doc.page}")
    canvas.restoreState()


def _analysis_section(analysis: Analysis, styles: dict) -> list:
    story = []
    result = analysis.result or {}
    label = ANALYSIS_TYPES.get(analysis.analysis_type, analysis.analysis_type)
    story.append(Paragraph(f"{label}", styles["h2"]))
    story.append(
        _kv_table(
            [
                ("Analysis date", analysis.created_at.strftime("%d %B %Y, %H:%M UTC")),
                ("Method / algorithm", analysis.algorithm_used or "—"),
                ("Processing time", f"{analysis.processing_time:.3f} seconds"),
                ("Status", analysis.status.capitalize()),
            ],
            styles,
        )
    )

    if analysis.analysis_type == "keywords":
        keywords = analysis.keywords or [
            type("K", (), {"keyword": item.get("keyword"), "relevance_score": item.get("relevance_score")})
            for item in result.get("keywords", [])
        ]
        story.append(Paragraph("Ranked keywords", styles["h3"]))
        data = [[Paragraph("#", styles["cellbold"]), Paragraph("Keyword", styles["cellbold"]), Paragraph("Relevance (0-1)", styles["cellbold"])]]
        for index, item in enumerate(keywords[:30], start=1):
            data.append(
                [
                    Paragraph(str(index), styles["cell"]),
                    Paragraph(_esc(item.keyword), styles["cell"]),
                    Paragraph(f"{float(item.relevance_score):.3f}", styles["cell"]),
                ]
            )
        table = Table(data, colWidths=[12 * mm, 120 * mm, 30 * mm], repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.4, LINE),
                    ("BACKGROUND", (0, 0), (-1, 0), SURFACE),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        story.append(table)

    elif analysis.analysis_type in {"extractive_summary", "abstractive_summary"}:
        story.append(Paragraph("Generated summary", styles["h3"]))
        story.append(_p(result.get("summary", "No summary recorded."), styles["quote"]))
        story.append(
            _kv_table(
                [
                    ("Original words", str(result.get("original_word_count", "—"))),
                    ("Summary words", str(result.get("summary_word_count", "—"))),
                    ("Compression", f"{result.get('compression_percentage', 0)}%"),
                    ("Summary type", str(result.get("method", "")).capitalize()),
                ],
                styles,
            )
        )

    elif analysis.analysis_type == "language":
        story.append(Paragraph("Detected language", styles["h3"]))
        story.append(
            _kv_table(
                [
                    ("Language", f"{result.get('name', '—')} ({result.get('code', '—')})"),
                    ("Confidence", f"{result.get('confidence_percentage', 0)}%"),
                    ("Reliable", "Yes" if result.get("reliable") else "Low confidence"),
                ],
                styles,
            )
        )
        if result.get("warning"):
            story.append(Paragraph(_esc(result["warning"]), styles["small"]))

    elif analysis.analysis_type == "sentiment":
        story.append(Paragraph("Sentiment result", styles["h3"]))
        story.append(
            _kv_table(
                [
                    ("Classification", str(result.get("label", "—")).capitalize()),
                    ("Compound score", f"{result.get('compound_score', 0):+.3f}"),
                    ("Positive", f"{result.get('positive_score', 0):.3f}"),
                    ("Neutral", f"{result.get('neutral_score', 0):.3f}"),
                    ("Negative", f"{result.get('negative_score', 0):.3f}"),
                    ("Model", result.get("model", "VADER")),
                ],
                styles,
            )
        )
        story.append(Paragraph(_esc(result.get("disclaimer", "")), styles["small"]))

    elif analysis.analysis_type == "explanation":
        story.append(Paragraph("Simplified explanation", styles["h3"]))
        story.append(_p(result.get("explanation", ""), styles["quote"]))
        story.append(
            _kv_table(
                [
                    ("Complexity", str(result.get("complexity", "standard")).capitalize()),
                    ("Provider", result.get("provider_label", "—")),
                    ("Key terms", ", ".join(result.get("key_terms", [])) or "—"),
                ],
                styles,
            )
        )
        story.append(Paragraph(_esc(result.get("disclaimer", "")), styles["small"]))

    elif analysis.analysis_type == "translation":
        story.append(Paragraph("Translation", styles["h3"]))
        story.append(_p(result.get("translated_text", ""), styles["quote"]))
        source = result.get("source_language") or {}
        target = result.get("target_language") or {}
        story.append(
            _kv_table(
                [
                    ("Language pair", f"{source.get('name', '—')} → {target.get('name', '—')}"),
                    ("Provider", result.get("provider_label", "—")),
                ],
                styles,
            )
        )
        story.append(Paragraph(_esc(result.get("limitations", "")), styles["small"]))
    return story


def build_report_pdf(
    *,
    user: User,
    title: str,
    analyses: list[Analysis],
    document: Document | None = None,
) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=24 * mm,
        title=title,
        author="Intelligent Text Analysis System",
    )
    styles = _styles()
    story = [
        Paragraph(_esc(title), styles["title"]),
        Paragraph(
            "Generated by the Intelligent Text Analysis System · "
            + datetime.utcnow().strftime("%d %B %Y, %H:%M UTC"),
            styles["subtitle"],
        ),
    ]

    metadata = [
        ("Prepared for", f"{user.full_name} ({user.email})"),
        ("Document", document.filename if document else "Pasted text"),
        ("Analyses included", str(len(analyses))),
    ]
    if document is not None:
        metadata[:0] = [
            ("File type", document.file_type.upper()),
            ("Uploaded", document.created_at.strftime("%d %B %Y, %H:%M UTC")),
        ]
    story.append(_kv_table(metadata, styles))

    # Source text statistics come from the first analysis result when available.
    source_text = document.extracted_text if document else (analyses[0].input_text if analyses else "")
    stats = text_statistics(source_text)
    for analysis in analyses:
        if analysis.result and analysis.result.get("original_statistics"):
            stats = analysis.result["original_statistics"]
            break
    story.append(Paragraph("Source text statistics", styles["h2"]))
    story.append(
        _kv_table(
            [
                ("Words", f"{stats.get('word_count', 0):,}"),
                ("Characters", f"{stats.get('character_count', 0):,}"),
                ("Sentences", f"{stats.get('sentence_count', 0):,}"),
                ("Paragraphs", f"{stats.get('paragraph_count', 0):,}"),
                ("Lexical diversity", f"{stats.get('lexical_diversity', 0)}"),
                ("Average sentence length", f"{stats.get('average_sentence_length', 0)} words"),
            ],
            styles,
        )
    )

    if source_text:
        story.append(Paragraph("Source text (excerpt)", styles["h2"]))
        story.append(_p(truncate(source_text, 1500), styles["quote"]))

    story.append(Paragraph("Analysis results", styles["h2"]))
    for analysis in analyses:
        if analysis.status != "completed":
            story.append(
                _kv_table(
                    [("Analysis", ANALYSIS_TYPES.get(analysis.analysis_type, analysis.analysis_type)), ("Status", "Failed")],
                    styles,
                )
            )
            continue
        story.extend(_analysis_section(analysis, styles))

    story.append(Spacer(1, 8 * mm))
    story.append(
        Paragraph(
            "Methodology note: NLP outputs are statistical estimates. Abstractive summaries and "
            "generated explanations may contain inaccuracies, sentiment scores are not objective "
            "measures of emotion, and machine translation is not suitable for certified legal or "
            "medical use without human review.",
            styles["small"],
        )
    )

    doc.build(story, onFirstPage=_page_footer, onLaterPages=_page_footer)
    return buffer.getvalue()
