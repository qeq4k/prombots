#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
📤 PDF Export — Экспорт статистики в PDF

Использование:
    from shared import export_stats_to_pdf
    
    pdf_path = await export_stats_to_pdf(stats_data, "report.pdf")
"""
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

logger = logging.getLogger(__name__)


async def export_stats_to_pdf(stats: Dict[str, Any], filename: str = "stats_report.pdf") -> str:
    """
    Экспорт статистики в PDF
    
    Args:
        stats: Данные статистики
        filename: Имя файла
    
    Returns:
        Путь к файлу
    """
    try:
        # Пытаемся импортировать reportlab
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import inch
            from reportlab.lib.enums import TA_CENTER, TA_LEFT
        except ImportError:
            logger.warning("⚠️ reportlab не установлен. Создаём TXT вместо PDF")
            return await _export_to_txt(stats, filename.replace(".pdf", ".txt"))
        
        # Создаём PDF
        output_path = Path(filename)
        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=A4,
            rightMargin=0.5*inch,
            leftMargin=0.5*inch,
            topMargin=0.5*inch,
            bottomMargin=0.5*inch
        )
        
        elements = []
        styles = getSampleStyleSheet()
        
        # Заголовок
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#1a1a2e'),
            spaceAfter=30,
            alignment=TA_CENTER
        )
        
        elements.append(Paragraph("📊 Отчёт по новостным каналам", title_style))
        elements.append(Spacer(1, 0.2*inch))
        
        # Дата
        date_style = ParagraphStyle(
            'DateStyle',
            parent=styles['Normal'],
            fontSize=12,
            textColor=colors.HexColor('#666'),
            alignment=TA_CENTER
        )
        elements.append(Paragraph(f"Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}", date_style))
        elements.append(Spacer(1, 0.3*inch))
        
        # Общая статистика
        if 'total_posts' in stats:
            elements.append(Paragraph("📈 Общая статистика", styles['Heading2']))
            
            data = [
                ["Метрика", "Значение"],
                ["Всего постов", str(stats.get('total_posts', 0))],
                ["Источников", str(stats.get('total_sources', 0))],
                ["Средний приоритет", str(stats.get('avg_priority', 0))],
                ["Период", f"{stats.get('period_days', 0)} дн."],
            ]
            
            table = Table(data, colWidths=[2.5*inch, 2*inch])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a1a2e')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 14),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8f9fa')),
                ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor('#1a1a2e')),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 12),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#ddd')),
            ]))
            
            elements.append(table)
            elements.append(Spacer(1, 0.3*inch))
        
        # Топ источников
        if 'top_sources' in stats:
            elements.append(Paragraph("🏆 Топ источников", styles['Heading2']))
            elements.append(Spacer(1, 0.2*inch))
            
            data = [
                ["#", "Источник", "Постов", "%", "Приоритет"],
            ]
            
            for i, src in enumerate(stats['top_sources'][:10], 1):
                data.append([
                    str(i),
                    src.get('source', 'N/A')[:30],
                    str(src.get('count', 0)),
                    f"{src.get('percent', 0)}%",
                    str(src.get('avg_priority', 0)),
                ])
            
            table = Table(data, colWidths=[0.4*inch, 2*inch, 0.8*inch, 0.6*inch, 0.8*inch])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a1a2e')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 12),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8f9fa')),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 10),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#ddd')),
            ]))
            
            elements.append(table)
        
        # Генерируем PDF
        doc.build(elements)
        
        logger.info(f"✅ PDF создан: {output_path}")
        return str(output_path)
        
    except Exception as e:
        logger.error(f"❌ Ошибка создания PDF: {e}")
        # Fallback в TXT
        return await _export_to_txt(stats, filename.replace(".pdf", ".txt"))


async def _export_to_txt(stats: Dict[str, Any], filename: str) -> str:
    """
    Экспорт в TXT (fallback если нет reportlab)
    """
    output_path = Path(filename)
    
    text = "=" * 60 + "\n"
    text += "📊 ОТЧЁТ ПО НОВОСТНЫМ КАНАЛАМ\n"
    text += "=" * 60 + "\n\n"
    text += f"Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
    
    if 'total_posts' in stats:
        text += "📈 ОБЩАЯ СТАТИСТИКА\n"
        text += "-" * 40 + "\n"
        text += f"Всего постов: {stats.get('total_posts', 0)}\n"
        text += f"Источников: {stats.get('total_sources', 0)}\n"
        text += f"Средний приоритет: {stats.get('avg_priority', 0)}\n"
        text += f"Период: {stats.get('period_days', 0)} дн.\n\n"
    
    if 'top_sources' in stats:
        text += "🏆 ТОП ИСТОЧНИКОВ\n"
        text += "-" * 40 + "\n"
        for i, src in enumerate(stats['top_sources'][:10], 1):
            text += f"{i}. {src.get('source', 'N/A')}\n"
            text += f"   Постов: {src.get('count', 0)} ({src.get('percent', 0)}%)\n"
            text += f"   Приоритет: {src.get('avg_priority', 0)}\n"
    
    text += "\n" + "=" * 60 + "\n"
    
    output_path.write_text(text, encoding='utf-8')
    logger.info(f"✅ TXT создан: {output_path}")
    return str(output_path)


__all__ = ['export_stats_to_pdf']
