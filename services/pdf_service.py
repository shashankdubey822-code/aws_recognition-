"""
Professional PDF Attendance Report Generator
Utilizes ReportLab with custom NumberedCanvas, professional styling, summary KPI metrics,
and formatted tabular ledgers in 24-hour IST time.
"""

import os
import time
from typing import List, Dict, Any, Union, Optional
from datetime import datetime

from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, HRFlowable
)
from reportlab.pdfgen import canvas

from core.config import REPORTS_DIR
from core.timezone_utils import get_time_str, get_date_str, get_timestamp_full_str, get_compact_timestamp_str


class NumberedCanvas(canvas.Canvas):
    """
    Two-pass canvas to dynamically compute total pages and draw consistent
    header/footer decorations on all pages.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count: int):
        self.saveState()
        self.setFont('Helvetica', 8)
        self.setFillColor(colors.HexColor('#64748b'))
        
        # Subtle horizontal rule above footer
        self.setStrokeColor(colors.HexColor('#cbd5e1'))
        self.setLineWidth(0.5)
        self.line(36, 38, 576, 38)
        
        # Running Footer
        self.drawString(36, 26, "Anyiiiiie.AI Enterprise Biometric Surveillance & Attendance System")
        self.drawCentredString(306, 26, "Official Audit Ledger • 24-Hour IST")
        self.drawRightString(576, 26, f"Page {self._pageNumber} of {page_count}")
        self.restoreState()


def generate_session_pdf(
    session_id_or_data: Union[str, Dict[str, Any]], 
    attendees_list: Optional[List[Dict[str, Any]]] = None, 
    output_dir: str = REPORTS_DIR,
    duration_minutes: Union[int, str] = 50,
    device_id: str = "Classroom 101",
    **kwargs
) -> str:
    """
    Generates a high-quality, professional PDF attendance report for a concluded session.
    
    Args:
        session_id_or_data: Either session ID string or dictionary containing session metadata.
        attendees_list: List of attendee dicts (keys: 'roll_number', 'name', 'time', 'date', 'device_id', 'status').
        output_dir: Directory where the generated PDF will be saved.
        duration_minutes: Duration of the monitoring session.
        device_id: Primary device or classroom identifier.
        
    Returns:
        Absolute or relative filepath of the generated .pdf file.
    """
    os.makedirs(output_dir, exist_ok=True)

    # Normalize input arguments
    if isinstance(session_id_or_data, dict):
        session_data = session_id_or_data
        session_id = session_data.get("id", "SESSION")
        attendees = session_data.get("attendees", [])
        duration_minutes = session_data.get("duration_minutes", duration_minutes)
        device_id = session_data.get("target_device", device_id)
    else:
        session_id = str(session_id_or_data)
        attendees = attendees_list if attendees_list is not None else kwargs.get("attendees", [])

    timestamp_compact = get_compact_timestamp_str()
    filename = f"Attendance_Report_{session_id}_{timestamp_compact}.pdf"
    filepath = os.path.join(output_dir, filename)

    # Setup Document (0.5 inch margins = 36 pt, printable width = 540 pt)
    doc = SimpleDocTemplate(
        filepath,
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=50
    )

    # Styles
    base_styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'DocTitle',
        parent=base_styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=18,
        leading=22,
        textColor=colors.HexColor('#0f172a')
    )
    
    subtitle_style = ParagraphStyle(
        'DocSubTitle',
        parent=base_styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=14,
        textColor=colors.HexColor('#475569')
    )
    
    section_heading = ParagraphStyle(
        'SectionHeading',
        parent=base_styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=16,
        textColor=colors.HexColor('#1e293b'),
        spaceAfter=6
    )

    meta_label = ParagraphStyle(
        'MetaLabel',
        parent=base_styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=11,
        textColor=colors.HexColor('#64748b'),
        textTransform='uppercase'
    )

    meta_val = ParagraphStyle(
        'MetaValue',
        parent=base_styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=13,
        textColor=colors.HexColor('#0f172a')
    )

    tbl_header = ParagraphStyle(
        'TblHeader',
        parent=base_styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=11,
        alignment=1, # Center
        textColor=colors.white
    )

    tbl_cell = ParagraphStyle(
        'TblCell',
        parent=base_styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor('#1e293b')
    )

    tbl_cell_center = ParagraphStyle(
        'TblCellCenter',
        parent=tbl_cell,
        alignment=1 # Center
    )

    tbl_cell_roll = ParagraphStyle(
        'TblCellRoll',
        parent=tbl_cell,
        fontName='Helvetica-Bold',
        alignment=1,
        textColor=colors.HexColor('#0284c7')
    )

    tbl_cell_status = ParagraphStyle(
        'TblCellStatus',
        parent=tbl_cell,
        fontName='Helvetica-Bold',
        alignment=1,
        textColor=colors.HexColor('#16a34a')
    )

    story = []

    # 1. Header Banner
    header_table_data = [
        [
            Paragraph("🎓 Anyiiiiie.AI Security & Biometrics", title_style),
            Paragraph(f"<b>Report ID:</b> {session_id}<br/><b>Date:</b> {get_date_str()}", ParagraphStyle('RightMeta', parent=subtitle_style, alignment=2))
        ],
        [
            Paragraph("Official Classroom Attendance & Edge Surveillance Audit Ledger (24-Hour IST)", subtitle_style),
            Paragraph(f"<b>Generated:</b> {get_time_str()} IST", ParagraphStyle('RightMeta2', parent=subtitle_style, alignment=2))
        ]
    ]
    header_tbl = Table(header_table_data, colWidths=[360, 180])
    header_tbl.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(header_tbl)
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#0284c7"), spaceBefore=2, spaceAfter=10))

    # 2. Session Overview & KPI Cards (4-box grid)
    total_present = len(attendees)
    meta_box_data = [
        [
            Paragraph("SESSION ID", meta_label),
            Paragraph("DURATION", meta_label),
            Paragraph("PRIMARY NODE", meta_label),
            Paragraph("TOTAL VERIFIED", meta_label)
        ],
        [
            Paragraph(str(session_id), meta_val),
            Paragraph(f"{duration_minutes} Mins", meta_val),
            Paragraph(str(device_id or "Classroom 101"), meta_val),
            Paragraph(f"<font color='#16a34a'>{total_present} Present</font>", meta_val)
        ]
    ]
    meta_box = Table(meta_box_data, colWidths=[140, 120, 140, 140])
    meta_box.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f1f5f9')),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#cbd5e1')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(meta_box)
    story.append(Spacer(1, 14))

    # 3. Attendance Ledger Table
    story.append(Paragraph("Verified Attendance Ledger", section_heading))

    # Table columns total 540 pt: 35 + 75 + 160 + 85 + 95 + 90 = 540
    table_rows = [
        [
            Paragraph("S.No", tbl_header),
            Paragraph("Roll No", tbl_header),
            Paragraph("Student / Faculty Name", tbl_header),
            Paragraph("Time (24h IST)", tbl_header),
            Paragraph("Classroom Node", tbl_header),
            Paragraph("Status", tbl_header)
        ]
    ]

    if attendees:
        for idx, att in enumerate(attendees, 1):
            roll = str(att.get("roll_number", "N/A"))
            name = str(att.get("name", "Unknown"))
            time_val = str(att.get("time", get_time_str()))
            node = str(att.get("device_id", device_id or "Classroom 101"))
            status_text = "VERIFIED ✓"
            
            table_rows.append([
                Paragraph(str(idx), tbl_cell_center),
                Paragraph(roll, tbl_cell_roll),
                Paragraph(name, tbl_cell),
                Paragraph(time_val, tbl_cell_center),
                Paragraph(node, tbl_cell_center),
                Paragraph(status_text, tbl_cell_status)
            ])
    else:
        empty_p = Paragraph("<i>No students were recorded during this monitoring session.</i>", tbl_cell_center)
        table_rows.append([empty_p, "", "", "", "", ""])

    ledger_tbl = Table(table_rows, colWidths=[35, 75, 160, 85, 95, 90], repeatRows=1)
    
    t_style = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f172a')),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
    ]

    # Alternating row colors
    if attendees:
        for r_idx in range(1, len(table_rows)):
            bg = colors.HexColor('#f8fafc') if r_idx % 2 == 0 else colors.white
            t_style.append(('BACKGROUND', (0, r_idx), (-1, r_idx), bg))
    else:
        t_style.append(('SPAN', (0, 1), (-1, 1)))
        t_style.append(('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#f8fafc')))

    ledger_tbl.setStyle(TableStyle(t_style))
    story.append(ledger_tbl)
    story.append(Spacer(1, 15))

    # 4. Verification & Audit Statement
    audit_text = (
        "<b>Biometric Verification Notice:</b> Attendance records in this ledger have been authenticated via "
        "AWS Rekognition facial feature embeddings and multi-scale ONNX neural inference. All timestamps are recorded "
        "in Indian Standard Time (IST, UTC+5:30) with 24-hour precision. This document serves as an immutable security audit ledger."
    )
    story.append(Paragraph(audit_text, ParagraphStyle('Audit', parent=subtitle_style, fontSize=7.5, leading=10, textColor=colors.HexColor('#64748b'))))

    # Build document with NumberedCanvas
    doc.build(story, canvasmaker=NumberedCanvas)
    return filepath
