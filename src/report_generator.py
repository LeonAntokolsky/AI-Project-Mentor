import os
import html
from datetime import datetime
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


from functools import lru_cache


@lru_cache(maxsize=1)
def _register_cyrillic_font() -> str:
    """Registers a Cyrillic-compatible font for ReportLab with cached lookup."""
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
        "C:\\Windows\\Fonts\\arial.ttf",
    ]
    for path in font_paths:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont("DejaVu", path))
                return "DejaVu"
            except Exception:
                pass
    return "Helvetica"


def generate_session_pdf_report(
        session_focus: str,
        completed_tasks: list[dict],
        output_dir: str = "/app/data/reports"
) -> Path:
    """Generates a structured PDF report detailing all applied code fixes."""
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    font_name = _register_cyrillic_font()
    pdf_filename = Path(output_dir) / f"Report_{timestamp}.pdf"

    doc = SimpleDocTemplate(
        str(pdf_filename),
        pagesize=A4,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName=font_name,
        fontSize=18,
        leading=22,
        textColor=colors.HexColor('#1E293B'),
        spaceAfter=10
    )

    meta_style = ParagraphStyle(
        'MetaText',
        parent=styles['Normal'],
        fontName=font_name,
        fontSize=10,
        leading=14,
        textColor=colors.HexColor('#64748B')
    )

    h2_style = ParagraphStyle(
        'SectionHeading',
        parent=styles['Heading2'],
        fontName=font_name,
        fontSize=12,
        leading=16,
        textColor=colors.HexColor('#0F172A'),
        spaceBefore=10,
        spaceAfter=6
    )

    body_style = ParagraphStyle(
        'BodyTextCustom',
        parent=styles['Normal'],
        fontName=font_name,
        fontSize=9,
        leading=12,
        textColor=colors.HexColor('#334155')
    )

    code_style = ParagraphStyle(
        'CodeBlock',
        parent=styles['Code'],
        fontName=font_name,
        fontSize=8,
        leading=10,
        textColor=colors.HexColor('#0F172A'),
        backColor=colors.HexColor('#F1F5F9'),
        borderPadding=6,
        spaceBefore=4,
        spaceAfter=6
    )

    story = []

    # Title & Metadata
    story.append(Paragraph("🚀 AI Project Mentor — Fix Summary Report", title_style))
    story.append(Paragraph(f"<b>Date & Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", meta_style))
    story.append(
        Paragraph(f"<b>Session Goal / Focus:</b> {html.escape(session_focus or 'General Refactoring')}", meta_style))
    story.append(Paragraph(f"<b>Total Fixes Applied:</b> {len(completed_tasks)}", meta_style))
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#E2E8F0'), spaceAfter=12))

    def _format_code_snippet(code: str | None) -> str:
        return html.escape((code or 'N/A').strip()[:1500]).replace('\n', '<br/>')

    if not completed_tasks:
        story.append(Paragraph("No tasks were completed in this session.", body_style))
    else:
        for idx, t in enumerate(completed_tasks, start=1):
            title_esc = html.escape(t.get('title', 'Micro-Task'))
            file_path_esc = html.escape(t.get('file_path', 'N/A'))
            profit_esc = html.escape(t.get('expected_profit') or t.get('explanation') or 'Improve code quality')
            search_code_esc = _format_code_snippet(t.get('search_block'))
            fix_code_esc = _format_code_snippet(t.get('ready_code_fix'))

            story.append(Paragraph(f"<b>{idx}. {title_esc}</b>", h2_style))

            raw_file_path = t.get('file_path') or 'item'
            file_stem = Path(raw_file_path).stem
            task_title = (t.get('title') or '').lower()
            unique_commit_esc = html.escape(t.get('git_commit_message') or f"refactor({file_stem}): {task_title}")
            meta_table_data = [
                [Paragraph("<b>Target File:</b>", body_style), Paragraph(file_path_esc, body_style)],
                [Paragraph("<b>Git Commit:</b>", body_style), Paragraph(f"<code>{unique_commit_esc}</code>", body_style)],
                [Paragraph("<b>Category:</b>", body_style),
                 Paragraph(html.escape(t.get('category', 'improvement')), body_style)],
                [Paragraph("<b>Why / ROI:</b>", body_style), Paragraph(profit_esc, body_style)],
            ]

            t_meta = Table(meta_table_data, colWidths=[80, 440])
            t_meta.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
                ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
                ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#F1F5F9')),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ]))
            story.append(t_meta)
            story.append(Spacer(1, 6))

            story.append(Paragraph("<b>Before (Original Code):</b>", body_style))
            story.append(Paragraph(search_code_esc, code_style))

            story.append(Paragraph("<b>After (Applied Fix):</b>", body_style))
            story.append(Paragraph(fix_code_esc, code_style))
            story.append(Spacer(1, 8))

    doc.build(story)
    return pdf_filename