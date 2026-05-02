"""PDF report generation for T-Hisob"""
from datetime import datetime
from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from sqlalchemy.orm import Session
from app.models.models import Transaction


def generate_monthly_report_pdf(telegram_id: int, db: Session,
                                month: datetime = None,
                                ai_summary: str = "") -> BytesIO:
    """
    Generate a monthly P&L (Profit & Loss) report as PDF
    Returns: BytesIO object with PDF content
    """
    if month is None:
        month = datetime.utcnow()
    
    month_start = datetime(month.year, month.month, 1)
    if month.month == 12:
        month_end = datetime(month.year + 1, 1, 1)
    else:
        month_end = datetime(month.year, month.month + 1, 1)
    
    # Get transactions
    txns = db.query(Transaction).filter(
        Transaction.telegram_id == telegram_id,
        Transaction.created_at >= month_start,
        Transaction.created_at < month_end,
    ).all()
    
    # Calculate totals
    income_total = sum(t.amount for t in txns if t.type == "kirim")
    expense_by_category = {}
    for t in txns:
        if t.type == "chiqim":
            cat = t.category or "Boshqa"
            if cat not in expense_by_category:
                expense_by_category[cat] = 0
            expense_by_category[cat] += t.amount
    
    expense_total = sum(expense_by_category.values())
    profit = income_total - expense_total
    tax_4pct = income_total * 0.04
    
    # Create PDF
    pdf_buffer = BytesIO()
    doc = SimpleDocTemplate(pdf_buffer, pagesize=A4)
    elements = []
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#1f4788'),
        spaceAfter=10,
        alignment=1,  # Center
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=colors.HexColor('#2c5aa0'),
        spaceAfter=8,
    )
    
    # Title
    title = Paragraph("📊 T-HISOB OYLIK HISOBOTI", title_style)
    elements.append(title)
    
    month_str = month.strftime("%B %Y")
    subtitle = Paragraph(f"<b>{month_str}</b>", styles['Normal'])
    elements.append(subtitle)
    elements.append(Spacer(1, 0.3*inch))
    
    # Summary section
    elements.append(Paragraph("UMUMIY QISQACHA", heading_style))
    
    summary_data = [
        ["", "So'm", ""],
        ["📈 Umumiy kirim", f"{income_total:,.0f}", ""],
        ["📉 Umumiy chiqim", f"{expense_total:,.0f}", ""],
        ["💰 Sof foyda/zarar", f"{profit:,.0f}", ""],
        ["🏛 Soliq (4%)", f"{tax_4pct:,.0f}", ""],
    ]
    
    summary_table = Table(summary_data, colWidths=[2.5*inch, 2*inch, 1.5*inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c5aa0')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 0), (-1, 0), 8),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('FONTSIZE', (0, 1), (-1, -1), 11),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 0.3*inch))
    
    # Expense categories section
    if expense_by_category:
        elements.append(Paragraph("XARAJATLAR KATEGORIYALAR BO'YICHA", heading_style))
        
        expense_data = [["Kategoriya", "Summa", "Foiz"]]
        total_expense = sum(expense_by_category.values())
        for cat in sorted(expense_by_category.keys()):
            amount = expense_by_category[cat]
            pct = (amount / total_expense * 100) if total_expense > 0 else 0
            expense_data.append([cat, f"{amount:,.0f}", f"{pct:.1f}%"])
        
        expense_table = Table(expense_data, colWidths=[2.5*inch, 2*inch, 1.5*inch])
        expense_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e74c3c')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('TOPPADDING', (0, 0), (-1, 0), 8),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#fadbd8')),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
        ]))
        elements.append(expense_table)
        elements.append(Spacer(1, 0.3*inch))
    
    # Recent transactions section
    if txns:
        elements.append(Paragraph("OXIRGI TRANZAKSIYALAR", heading_style))
        
        recent_txns = sorted(txns, key=lambda t: t.created_at, reverse=True)[:10]
        txn_data = [["Sana", "Turi", "Summa", "Tavsif"]]
        for t in recent_txns:
            date_str = t.created_at.strftime("%d.%m.%Y")
            txn_type = "💰 Kirim" if t.type == "kirim" else "📌 Chiqim"
            txn_data.append([
                date_str,
                txn_type,
                f"{t.amount:,.0f}",
                t.description[:20] + ("..." if len(t.description) > 20 else "")
            ])
        
        txn_table = Table(txn_data, colWidths=[1.3*inch, 1.3*inch, 1.4*inch, 2*inch])
        txn_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#27ae60')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('TOPPADDING', (0, 0), (-1, 0), 8),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#eafaf1')),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
        ]))
        elements.append(txn_table)
    
    elements.append(Spacer(1, 0.3*inch))

    # AI Analysis section
    if ai_summary:
        elements.append(Paragraph("AI TAHLILIY XULOSA", heading_style))
        ai_style = ParagraphStyle(
            'AIStyle',
            parent=styles['Normal'],
            fontSize=11,
            leading=16,
            backColor=colors.HexColor('#f0f4ff'),
            borderPadding=10,
            leftIndent=8,
            rightIndent=8,
        )
        elements.append(Paragraph(ai_summary.replace('\n', '<br/>'), ai_style))
        elements.append(Spacer(1, 0.3*inch))

    elements.append(Spacer(1, 0.2*inch))

    # Footer
    from datetime import timezone, timedelta
    uzb_now = datetime.now(timezone(timedelta(hours=5)))
    footer_text = (
        f"<i>Ushbu hisobot {uzb_now.strftime('%d.%m.%Y %H:%M')} (O'zbekiston vaqti) "
        f"T-Hisob tizimi tomonidan avtomatik yaratildi.<br/>"
        f"Buxgalteriya va soliq bo'yicha maslahat uchun professional konsultantga murojaat qiling.</i>"
    )
    elements.append(Paragraph(footer_text, styles['Normal']))
    
    # Build PDF
    doc.build(elements)
    pdf_buffer.seek(0)
    return pdf_buffer
