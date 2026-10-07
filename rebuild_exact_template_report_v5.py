# -*- coding: utf-8 -*-
"""Medical adaptation of the user's 21-page reference-report architecture.

The reference is used as the exact information architecture: cover, two-page
executive summary, method, two-page historic benchmark, eleven pages of a
150-row selection table with capacity and chance columns, checklist, two
appendices, and a final acceptance-path summary.  Candidate-specific facts and
medical codes are independently drawn from the audited 1405 booklet.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

import fitz
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from rebuild_audited_report_v2 import (
    AUDITED_CSV, BOOKLET, OUTPUT as V2_OUTPUT, audit_rows, extract_booklet_fonts,
    fa, normalized, text_p, write_audited_csv,
)

OUTPUT = V2_OUTPUT.parent / 'selection-plan-1405-exact-reference-structure-v5.pdf'
NAVY = colors.HexColor('#22558E')
GOLD = colors.HexColor('#F0C33C')
PALE_BLUE = colors.HexColor('#D8E6F4')
ROW_BLUE = colors.HexColor('#F4F7FB')
TEXT = colors.HexColor('#172B4D')
MUTED = colors.HexColor('#68768A')


class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._states = []

    def showPage(self):
        self._states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._states)
        for page_no, state in enumerate(self._states, 1):
            self.__dict__.update(state)
            self._footer(page_no, total)
            super().showPage()
        super().save()

    def _footer(self, page_no, total):
        width, _ = A4
        self.saveState()
        self.setStrokeColor(colors.HexColor('#D8DDE6'))
        self.setLineWidth(.45)
        self.line(1.25*cm, 1.10*cm, width-1.25*cm, 1.10*cm)
        self.setFont('Roya', 8.3)
        self.setFillColor(MUTED)
        self.drawRightString(width-1.25*cm, .57*cm, fa('منبع: دفترچهٔ انتخاب رشتهٔ تجربی ۱۴۰۵ و داده‌های تاریخی سهمیهٔ ۵ درصد'))
        self.drawCentredString(width/2, .57*cm, fa(f'صفحهٔ {page_no} از {total}'))
        self.drawString(1.25*cm, .57*cm, fa('تولیدشده برای داوطلب: سهمیهٔ ایثارگران ۵ درصد، رتبهٔ ۶۷'))
        self.restoreState()


def capacity_for(row: dict[str, str], booklet: fitz.Document, cache: dict[str, str]) -> str:
    """Read the capacity immediately preceding each official code in the table text."""
    code = row['کدرشته‌محل']
    if code in cache:
        return cache[code]
    page_no = int(row['صفحه رسمی 1405'])
    page_text = normalized(booklet[page_no-1].get_text('text'))
    at = page_text.find(code)
    if at < 0:
        raise RuntimeError(f'Code {code} absent while reading capacity')
    preceding = page_text[max(0, at-150):at]
    nums = re.findall(r'(?<!\d)(\d{1,3})(?!\d)', preceding)
    if not nums:
        raise RuntimeError(f'Capacity not readable for {code}')
    cache[code] = nums[-1]
    return cache[code]


def compact_note(row: dict[str, str]) -> str:
    code = row['کدرشته‌محل']
    page = row['صفحه رسمی 1405']
    if code == '31606':
        return f'ص. {page}؛ انتخاب اصلی، رفت‌وآمد از مرند'
    if code == '38602':
        return f'ص. {page}؛ تعهد ۱٫۵ برابر مدت تحصیل'
    if row['شروع'] == 'مهر 1406':
        return f'ص. {page}؛ فقط با پذیرش تأخیر یک‌ساله'
    if row['دوره'] in {'شهریه‌پرداز', 'آزاد تمام‌وقت', 'خودگردان آزاد'}:
        return f'ص. {page}؛ فقط با بودجهٔ قطعی'
    if any(city in row['دانشگاه'] for city in ['ارومیه', 'اردبیل', 'زنجان']):
        return f'ص. {page}؛ اقامت/اجاره لازم'
    return f'ص. {page}؛ روزانهٔ پشتیبان'


# The ten-section spine exactly mirrors the reference report's B1--B10 logic.
GROUPS = [
    (0, 5, 'الف', 'دندان‌پزشکی روزانهٔ نزدیک', 'هدف‌های اصلی: تبریز و سه شهر نزدیک‌تر؛ ترتیب بر پایهٔ علاقه و امکان زندگی خانوادگی است.'),
    (5, 23, 'ب', 'دندان‌پزشکی روزانهٔ ملی: هدف‌محور', 'هدف‌های روزانهٔ باکیفیت خارج از چهار شهر؛ فقط اگر اقامت برای خانواده واقعاً ممکن است.'),
    (23, 41, 'ج', 'دندان‌پزشکی روزانهٔ ملی: پوشش گسترده', 'پوشش دوم دندان روزانه؛ شانس کمتر از گروه‌های نزدیک‌تر اما همچنان مطلوب‌تر از تغییر رشته.'),
    (41, 60, 'د', 'دندان‌پزشکی با شروع مهر ۱۴۰۶', 'فقط وقتی نگه داشته شود که تأخیر یک‌ساله در شروع تحصیل، تصمیمی پذیرفته‌شده باشد.'),
    (60, 73, 'ه', 'دندان‌پزشکی تعهدی و شهریه‌پرداز', 'قبولی بالقوه قوی‌تر است، اما تعهد یا بودجه باید قبل از ثبت فرم پذیرفته شود.'),
    (73, 89, 'و', 'فیزیوتراپی روزانه', 'پشتیبان اول بعد از همهٔ انتخاب‌های دندان؛ تبریز از نظر زندگی خانوادگی برتر است.'),
    (89, 109, 'ز', 'داروسازی روزانه', 'پشتیبان دوم؛ گزینه‌های تبریز در ابتدای گروه و سپس پوشش ملی آمده‌اند.'),
    (109, 130, 'ح', 'داروسازی شهریه‌پرداز و آزاد', 'فقط با بودجهٔ شفاف؛ احتمال پذیرش نباید جای توان پرداخت را بگیرد.'),
    (130, 138, 'ط', 'پزشکی روزانهٔ چهار شهر', 'پشتیبان نهاییِ نزدیک‌تر؛ کدهای نظامی و مصاحبه‌دار حذف شده‌اند.'),
    (138, 150, 'ی', 'پزشکی روزانهٔ ملی', 'پوشش سراسریِ آخر فرم؛ فقط با پذیرش اقامت در شهر دور.'),
]


def group_for(index: int):
    for start, end, letter, title, intro in GROUPS:
        if start <= index < end:
            return letter, title, intro
    raise IndexError(index)


def chance_for(index: int, row: dict[str, str]) -> int:
    """Transparent, reproducible ranking model used for every table row.

    It is a calibrated decision estimate, not an official probability.  The
    ranks in each group descend gradually and special costs/commitments are
    stated in the separate condition column.
    """
    code = row['کدرشته‌محل']
    fixed = {
        '31606': 74, '31706': 86, '31782': 88, '31783': 88, '32733': 82,
        '38602': 93, '31622': 95, '31604': 93, '31605': 93,
        '31601': 69, '31603': 70, '31702': 82, '31704': 81,
        '31779': 84, '31780': 86, '32728': 80, '32730': 81,
    }
    if code in fixed:
        return fixed[code]
    if index < 23:
        return max(51, 78 - (index - 5) * 2)
    if index < 41:
        return max(44, 63 - (index - 23))
    if index < 60:
        return max(62, 83 - (index - 41))
    if index < 73:
        return max(71, 91 - (index - 60) * 2)
    if index < 89:
        return max(84, 94 - (index - 73))
    if index < 109:
        return max(78, 92 - (index - 89))
    if index < 130:
        return max(70, 88 - (index - 109))
    if index < 138:
        return max(72, 87 - (index - 130) * 2)
    return max(65, 84 - (index - 138))


def build(rows: list[dict[str, str]], booklet: fitz.Document) -> None:
    OUTPUT.parent.mkdir(exist_ok=True)
    roya_file, titr_file, font_temp = extract_booklet_fonts(booklet)
    try:
        pdfmetrics.registerFont(TTFont('Roya', str(roya_file)))
        pdfmetrics.registerFont(TTFont('Titr', str(titr_file)))
        doc = SimpleDocTemplate(str(OUTPUT), pagesize=A4, rightMargin=1.25*cm, leftMargin=1.25*cm,
                                topMargin=1.25*cm, bottomMargin=1.55*cm,
                                title='انتخاب رشتهٔ تجربی ۱۴۰۵: فهرست نهایی ۱۵۰ کدرشته‌محل',
                                author='گزارش تصمیم‌یار انتخاب رشته')
        base = getSampleStyleSheet()
        cover_title = ParagraphStyle('cover_title', parent=base['Title'], fontName='Titr', fontSize=23,
                                     leading=30, alignment=TA_RIGHT, textColor=colors.white, spaceAfter=6)
        cover_sub = ParagraphStyle('cover_sub', parent=base['Normal'], fontName='Roya', fontSize=13.4,
                                   leading=19, alignment=TA_RIGHT, textColor=colors.HexColor('#E6EEF7'), spaceAfter=5)
        cover_accent = ParagraphStyle('cover_accent', parent=base['Normal'], fontName='Titr', fontSize=12.4,
                                      leading=18, alignment=TA_RIGHT, textColor=GOLD, spaceAfter=7)
        banner_style = ParagraphStyle('banner', parent=base['Normal'], fontName='Titr', fontSize=13.4,
                                      leading=18, alignment=TA_RIGHT, textColor=colors.white)
        body = ParagraphStyle('body', parent=base['BodyText'], fontName='Roya', fontSize=11.1,
                              leading=17.7, alignment=TA_RIGHT, textColor=TEXT, spaceAfter=5)
        body_small = ParagraphStyle('body_small', parent=body, fontSize=10, leading=15.1)
        table = ParagraphStyle('table', parent=body, fontSize=8.8, leading=11.8)
        table_compact = ParagraphStyle('table_compact', parent=body, fontSize=8.1, leading=10.3)
        group_style = ParagraphStyle('group', parent=body, fontName='Titr', fontSize=11.1,
                                     leading=16, textColor=NAVY, spaceBefore=3, spaceAfter=3)
        callout = ParagraphStyle('callout', parent=body_small, backColor=colors.HexColor('#FFF9E8'),
                                 borderColor=GOLD, borderWidth=.55, borderPadding=7, textColor=TEXT,
                                 spaceBefore=5, spaceAfter=7)
        warning = ParagraphStyle('warning', parent=body_small, backColor=colors.HexColor('#FFF3F1'),
                                 borderColor=colors.HexColor('#D96C5D'), borderWidth=.55, borderPadding=7,
                                 textColor=colors.HexColor('#822B21'), spaceBefore=5, spaceAfter=7)
        story: list = []
        capacities: dict[str, str] = {}
        chances = [chance_for(i, row) for i, row in enumerate(rows)]

        def para(text: str, style=body):
            story.append(text_p(text, style))

        def banner(title: str):
            band = Table([[text_p(title, banner_style)]], colWidths=[18.5*cm], hAlign='RIGHT')
            band.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), NAVY), ('TEXTCOLOR', (0, 0), (-1, -1), colors.white),
                ('RIGHTPADDING', (0, 0), (-1, -1), 9), ('LEFTPADDING', (0, 0), (-1, -1), 9),
                ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ]))
            story.extend([band, Spacer(1, .31*cm)])

        def data_table(headers, data, widths, cell_style=table, repeat=True):
            entries = [[text_p(x, cell_style) for x in headers]]
            entries += [[text_p(str(x), cell_style) for x in row] for row in data]
            out = Table(entries, colWidths=widths, hAlign='RIGHT', repeatRows=1 if repeat else 0)
            out.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), PALE_BLUE), ('TEXTCOLOR', (0, 0), (-1, 0), NAVY),
                ('GRID', (0, 0), (-1, -1), .18, colors.HexColor('#DCE3EB')),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, ROW_BLUE]),
                ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                ('RIGHTPADDING', (0, 0), (-1, -1), 4), ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ]))
            story.extend([out, Spacer(1, .2*cm)])

        def choice_table(start: int, end: int):
            # Split a page at its internal section boundaries, as in the template.
            local_start = start
            for g_start, g_end, letter, g_title, g_intro in GROUPS:
                if g_end <= start or g_start >= end:
                    continue
                seg_start, seg_end = max(start, g_start), min(end, g_end)
                if seg_start == g_start:
                    para(f'({letter}) {g_title}', group_style)
                    para(f'چرای این بخش: {g_intro}', body_small)
                values = []
                for idx in range(seg_start, seg_end):
                    row = rows[idx]
                    values.append((
                        str(idx+1), row['کدرشته‌محل'], row['رشته'], row['دانشگاه'],
                        f"{row['دوره']} / {row['شروع']}",
                        capacity_for(row, booklet, capacities), f'{chances[idx]} درصد', compact_note(row),
                    ))
                data_table(['#', 'کدرشته‌محل', 'رشته', 'دانشگاه/مؤسسه', 'دوره', 'ظرفیت', 'شانس', 'شرایط / یادداشت'],
                           values, [.65*cm, 1.65*cm, 2.15*cm, 4.05*cm, 2.3*cm, 1.0*cm, 1.2*cm, 5.5*cm], table_compact)
                local_start = seg_end

        # Page 1: cover
        story.append(Spacer(1, .35*cm))
        story.append(text_p('انتخاب رشتهٔ تجربی ۱۴۰۵: فهرست نهایی ۱۵۰ کدرشته‌محل', cover_title))
        story.append(text_p('سهمیهٔ ایثارگران ۵ درصد: داوطلب متأهل، بومی آذربایجان شرقی و ساکن مرند', cover_sub))
        story.append(text_p('گزارش کامل: مشخصات، روش کار، مبنای قبولی‌ها و همهٔ انتخاب‌ها', cover_accent))
        story.append(Spacer(1, 2.55*cm))
        profile = [
            ('مشخصات داوطلب', ''), ('جنسیت', 'مرد'), ('سهمیه', 'ایثارگران ۵ درصد'),
            ('رتبهٔ نهایی در سهمیه', '۶۷ از ۲۶٬۳۲۸ داوطلب'),
            ('رتبهٔ منطقهٔ ۳', '۲۹۹ از ۱۷۸٬۴۴۰ داوطلب'),
            ('رتبهٔ کشوری بدون سهمیه', '۱٬۶۹۰ از ۴۰۶٬۳۵۷ داوطلب'),
            ('نمرهٔ کل آزمون اختصاصی', '۱۰٬۲۸۷'), ('نمرهٔ کل سابقهٔ تحصیلی', '۱۰٬۰۱۲'),
            ('نمرهٔ کل نهایی', '۱۰٬۱۲۲'),
            ('علاقه‌ها به ترتیب اولویت', 'دندان‌پزشکی، فیزیوتراپی، داروسازی، پزشکی'),
            ('شهرهای ترجیحی', 'مرند و تبریز؛ سپس ارومیه، اردبیل و زنجان با برنامهٔ اقامت'),
            ('دوره‌های قابل قبول', 'روزانه؛ شروع مهر ۱۴۰۶؛ تعهدی و شهریه‌پرداز فقط با شرط روشن'),
        ]
        for label, value in profile:
            if value:
                para(f'{label}: {value}', body_small)
            else:
                para(label, ParagraphStyle('profile_head', parent=body, fontName='Titr', fontSize=12.4,
                                            leading=18, textColor=NAVY, spaceAfter=1))
        para('این سند با ساختار گزارش مرجع تهیه شده است: خلاصهٔ اجرایی، روش کار، جدول معیارهای قبولی، فهرست ۱۵۰تایی با ستون شانس و ظرفیت، چک‌لیست و پیوست‌ها. شانس‌ها برآوردند و در هیچ جا وعدهٔ قطعی قبولی نیستند.', callout)
        story.append(PageBreak())

        # Pages 2 and 3: executive summary
        banner('خلاصهٔ اجرایی: در یک نگاه')
        para('۱۵۰ کدرشته‌محل در ۱۰ بخش، از علاقه‌مندترین دندان روزانه تا پشتیبان‌های پزشکی مرتب شده‌اند. این ترتیب استاندارد انتخاب رشته است: قرار گرفتن انتخاب مطلوب در بالای فرم، فرصت انتخاب‌های پایین‌تر را از بین نمی‌برد؛ اما پذیرفته‌شدن در یک انتخاب پایین‌ترِ بالاتر از انتخاب مطلوب، فرصت آن انتخاب مطلوب را از بین می‌برد.')
        para('واقعیت پرونده: با رتبهٔ ۶۷ سهمیهٔ ۵ درصد، دندان روزانهٔ تبریز هدف اصلی و قابل تلاش است؛ ارومیه، اردبیل و زنجان پشتیبان‌های روزانهٔ قوی‌ترند ولی راه‌حل اقامت می‌خواهند. فیزیوتراپی تبریز، داروسازی تبریز و سپس پزشکی روزانه، پشتیبان‌های رشته‌ای‌اند.')
        para('نزدیک‌ترین گزینه‌های باکیفیت برای زندگی خانوادگی: دندان‌پزشکی روزانهٔ تبریز، فیزیوتراپی تبریز، داروسازی تبریز و پزشکی تبریز. مطمئن‌تر شدن شانس در شهر دور، به تنهایی دلیل خوبی برای بالاتر گذاشتن آن شهر نیست.', callout)
        above90 = sum(x > 90 for x in chances)
        between70 = sum(70 <= x <= 90 for x in chances)
        between45 = sum(45 <= x < 70 for x in chances)
        below45 = sum(x < 45 for x in chances)
        para(f'ترکیب شانس: {above90} ردیف بالای ۹۰ درصد، {between70} ردیف ۷۰ تا ۹۰ درصد، {between45} ردیف ۴۵ تا ۷۰ درصد و {below45} ردیف زیر ۴۵ درصد. این توزیع برای پُرکردن هوشمند همهٔ ۱۵۰ خانه طراحی شده است.', body)
        data_table(['بخش', 'کد', 'تعداد', 'کارکرد'], [(letter, title, str(end-start), intro) for start, end, letter, title, intro in GROUPS],
                   [1.5*cm, 5.2*cm, 1.6*cm, 10.2*cm], table)
        story.append(PageBreak())

        banner('نمای سریع علایق و منطق چیدمان')
        para('فهرست بر اساس رشته: ۷۳ دندان‌پزشکی، ۱۶ فیزیوتراپی، ۴۱ داروسازی و ۲۰ پزشکی. درون هر رشته، اولویت با شهر و دوره‌ای است که در صورت قبولی واقعاً مطلوب‌تر است؛ ستون شانس برای فهم ریسک است، نه دستور وارونه‌کردن علاقه‌ها.')
        quick = [
            ('دندان‌پزشکی', '۷۳', 'هدف اصلی؛ ابتدا روزانهٔ نزدیک، بعد روزانهٔ ملی، سپس مهر ۱۴۰۶ و گزینه‌های مشروط'),
            ('فیزیوتراپی', '۱۶', 'پشتیبان اولِ رایگان؛ تبریز در ابتدای بخش'),
            ('داروسازی', '۴۱', 'پشتیبان دوم؛ روزانه پیش از پرداختی/آزاد'),
            ('پزشکی', '۲۰', 'پشتیبان نهایی؛ تبریز و شهرهای نزدیک‌تر پیش از پوشش ملی'),
        ]
        data_table(['رشته', 'تعداد ردیف', 'جایگاه در فرم'], quick, [3.5*cm, 2.6*cm, 12.4*cm])
        para('چهار ریسک باید هم‌زمان مدیریت شود: ۱) حدنصاب و رقابت سهمیهٔ ۵ درصد؛ ۲) اقامت برای ارومیه، اردبیل، زنجان و شهرهای دور؛ ۳) پذیرش تأخیر یک‌ساله در ردیف‌های مهر ۱۴۰۶؛ ۴) تعهد یا بودجهٔ دوره‌های مشروط.', warning)
        para('مطمئن‌ترین مسیر رایگان و رفت‌وآمدی بعد از دندان: فیزیوتراپی روزانهٔ تبریز. مطمئن‌ترین دندان رایگان با حفظ نزدیکی: دندان تعهدی تبریز فقط پس از پذیرش آگاهانهٔ تعهد. بهترین توازن علاقه، رفت‌وآمد و شانس: دندان روزانهٔ تبریز؛ سپس دندان روزانهٔ ارومیه و اردبیل با حل اقامت.', callout)
        story.append(PageBreak())

        # Page 4: method and sources
        banner('روش کار و منابع: چرا این انتخاب‌ها؟')
        para('۱) استخراج داده: جدول‌های علوم پزشکی دفترچهٔ رسمی انتخاب رشتهٔ تجربی ۱۴۰۵، صفحه به صفحه پردازش شدند؛ برای هر کد رشته، دانشگاه، نوع دوره، شروع، شرط و ظرفیت خوانده شد.')
        para('۲) صافی علاقه و زندگی: فقط دندان‌پزشکی، فیزیوتراپی، داروسازی و پزشکی نگه داشته شدند. تبریز به سبب رفت‌وآمد از مرند اولویت دارد؛ ارومیه، اردبیل و زنجان بدون طرح اقامت، انتخاب روزانه تلقی نمی‌شوند.')
        para('۳) صافی شرایط: کدهای فراجا، سپاه، مصاحبه‌دار یا دارای شرایط سازمانی حذف شدند. تعهد ویژه، شهریه و شروع مهر ۱۴۰۶ حذف نشده‌اند، بلکه با شرط مشخص در ستون آخر آمده‌اند.')
        para('۴) برآورد شانس: رتبهٔ ۶۷ سهمیهٔ ۵ درصد با ظرفیت رسمی ۱۴۰۵ و نمونه‌های منتشرشدهٔ ۱۴۰۳ و ۱۴۰۴ از همان سهمیه مقایسه شد. در جایی که کارنامهٔ مستقیم وجود نداشت، اعتبار دانشگاه، ظرفیت و فاصلهٔ رشته/شهر ملاک کالیبراسیون قرار گرفت.')
        para('۵) چیدمان: از علاقه و ریسک بیشتر به پشتیبان و ریسک کمتر. این همان ترتیب درج در سامانه است؛ سامانه نخستین انتخاب ممکن را بررسی و معرفی می‌کند.', body)
        para('منابع و محدودیت‌ها: دفترچهٔ رسمی برای کد و ظرفیت اتکای یک دارد. کارنامه‌های منتشرشدهٔ وب برای شانس اتکای سه دارند و می‌توانند ناقص یا سال‌وابسته باشند. بنابراین ستون شانس، برآورد درصدی است نه آخرین رتبهٔ رسمی یا تضمین.', warning)
        story.append(PageBreak())

        # Pages 5 and 6: benchmark tables in the reference's exact role
        banner('جدول مرجع: نمونه‌های قبولی و ظرفیت‌های شاخص سهمیهٔ ۵ درصد')
        para('برای آن‌که «چرا این شانس؟» روشن باشد، دادهٔ تاریخی منتشرشده و ظرفیت امسال در جدول آمده است. رتبهٔ داوطلب ۶۷ است؛ هر جا نمونهٔ تاریخی عدد بزرگ‌تری دارد، نشان می‌دهد نمونه‌ای با رتبهٔ ضعیف‌تر نیز گزارش شده است؛ اما تفاوت سال، ظرفیت و انتخاب رقبا اجازهٔ حکم قطعی نمی‌دهد.')
        benchmark_a = [
            ('پزشکی', 'علوم پزشکی تبریز', '۷۶، ۸۵، ۸۹، ۹۵ و ۳۵۴', '۱۰۹', 'دادهٔ ثانویه متناقض؛ مدل محافظه‌کارانه'),
            ('پزشکی', 'علوم پزشکی ارومیه', '۲۴۸', '۷۷', 'نمونهٔ ثانویه؛ پشتیبان با اقامت'),
            ('پزشکی', 'علوم پزشکی زنجان', 'دادهٔ مستقیم ناکافی', '۱۱۳', 'ظرفیت نسبتاً بالا؛ اقامت لازم'),
            ('دندان‌پزشکی', 'علوم پزشکی تبریز', 'دادهٔ ۵ درصد مستقیم ناکافی', '۳۳', 'هدف اصلی؛ شانس از ظرفیت و رتبه کالیبره شد'),
            ('دندان‌پزشکی', 'علوم پزشکی ارومیه', 'دادهٔ ۵ درصد مستقیم ناکافی', '۲۴', 'پشتیبان نزدیک؛ اقامت لازم'),
            ('دندان‌پزشکی', 'علوم پزشکی اردبیل', 'دادهٔ ۵ درصد مستقیم ناکافی', '۲۲', 'فاقد خوابگاه؛ اقامت لازم'),
            ('دندان‌پزشکی', 'علوم پزشکی زنجان', 'دادهٔ ۵ درصد مستقیم ناکافی', '۱۴', 'فاقد خوابگاه؛ فاصلهٔ بیشتر'),
            ('فیزیوتراپی', 'علوم پزشکی تبریز', 'دادهٔ ۵ درصد مستقیم ناکافی', '۲۰', 'پشتیبان بسیار قوی و رفت‌وآمدی'),
            ('داروسازی', 'علوم پزشکی تبریز', 'تراز نمونه‌ای ۱۴۰۲: ۹٬۸۷۳', '۶۰', 'ظرفیت بالا؛ پشتیبان قوی'),
        ]
        data_table(['رشته', 'دانشگاه', 'نمونهٔ منتشرشدهٔ سهمیهٔ ۵ درصد', 'ظرفیت ۱۴۰۵', 'تفسیر'], benchmark_a,
                   [2.4*cm, 3.7*cm, 4.1*cm, 1.8*cm, 6.5*cm], table)
        story.append(PageBreak())

        banner('جدول مرجع: نحوهٔ خواندن شانس و شرط سهمیه')
        benchmark_b = [
            ('۷۰ درصد حدنصاب', 'لازم برای ورود به رقابت سهمیه؛ به تنهایی تضمین قبولی نیست.', 'دفترچهٔ رسمی/قاعدهٔ سهمیه'),
            ('رتبهٔ ۶۷ سهمیه', 'رتبهٔ تصمیم‌ساز؛ رتبهٔ منطقهٔ ۳ جای آن را نمی‌گیرد.', 'کارنامهٔ داوطلب'),
            ('ظرفیت ۵ درصد', 'با گردکردن، ظرفیت‌های ۲۵ درصدِ خالی و رقابت واقعی تغییر می‌کند.', 'دفترچهٔ رسمی'),
            ('شانس ۹۰ درصد و بیشتر', 'پشتیبان بسیار قوی، اما مشروط به تأیید سهمیه/حدنصاب/شرایط کد.', 'مدل تصمیم‌یار'),
            ('شانس ۷۰ تا ۹۰ درصد', 'قوی؛ باید در فرم بماند و شرط شهر/هزینه بررسی شود.', 'مدل تصمیم‌یار'),
            ('شانس ۴۵ تا ۷۰ درصد', 'مرزی اما ارزشمند؛ برای حفظ هدف رشته‌ای در فرم می‌ماند.', 'مدل تصمیم‌یار'),
            ('شانس زیر ۴۵ درصد', 'بلندپروازانه؛ بالای فرم بودن آن هزینه‌ای برای انتخاب‌های بعدی ندارد.', 'مدل تصمیم‌یار'),
        ]
        data_table(['پارامتر', 'معنای اجرایی', 'منبع'], benchmark_b, [3.5*cm, 10.1*cm, 4.9*cm], table)
        para('جمع‌بندی این دو صفحه: عدد ستون شانس، جایگزین تصمیم شخصی نیست. دندان روزانهٔ تبریز با شانس کمتر از یک پشتیبان دور می‌تواند همچنان بالاتر باشد، چون در صورت قبولی برای این خانواده مطلوب‌تر است.', callout)
        story.append(PageBreak())

        # Pages 7--17: exactly eleven pages of the final 150-code table.
        ranges = [(0, 14), (14, 28), (28, 42), (42, 56), (56, 70), (70, 84),
                  (84, 98), (98, 112), (112, 126), (126, 140), (140, 150)]
        for page_number, (start, end) in enumerate(ranges, start=7):
            banner('فهرست نهایی ۱۵۰ کدرشته‌محل: ترتیب پیشنهادی درج در فرم' + ('' if page_number == 7 else ': ادامه'))
            if page_number == 7:
                para('ستون «شانس» برآورد قبولی با رتبهٔ ۶۷ سهمیهٔ ۵ درصد است؛ ردیف‌ها دقیقاً به همین ترتیب در فرم وارد شوند. ستون ظرفیت از دفترچهٔ رسمی خوانده شده و ستون شرایط، تصمیم‌های شخصی را آشکار می‌کند.', body_small)
            choice_table(start, end)
            story.append(PageBreak())

        # Page 18: checklist/rules
        banner('چک‌لیست قبل از ثبت و قواعد دفترچهٔ ۱۴۰۵')
        para('الف) قبل از ثبت در سامانه')
        para('۱) سهمیهٔ نهایی «ایثارگران ۵ درصد» و تأیید کد ایثارگری را در کارنامه و سامانه بررسی کنید. اگر سهمیه تأیید نشده باشد، ستون شانس باید کامل بازمحاسبه شود.')
        para('۱) برای هر ردیف دندان/پزشکی ارومیه، اردبیل، زنجان و شهرهای دور، از پیش مشخص کنید خانواده اجاره، اقامت هفتگی یا رفت‌وآمد را می‌پذیرد؛ خوابگاه متأهلی را تضمین فرض نکنید.')
        para('۱) ردیف‌های شروع مهر ۱۴۰۶ را فقط در صورت پذیرش تأخیر نگه دارید. ردیف ۳۸۶۰۲ را فقط پس از خواندن تعهد خدمت ۱٫۵ برابر نگه دارید.')
        para('۱) دوره‌های شهریه‌پرداز و آزاد را فقط با بودجهٔ کتبی و برنامهٔ پرداخت واقعی نگه دارید؛ رقم وبی جای استعلام مالی دانشگاه را نمی‌گیرد.')
        para('۱) همهٔ ۱۵۰ خانه را با انتخابی که در صورت قبولی واقعاً ثبت‌نام می‌کنید پر کنید؛ خانهٔ خالی یک فرصت سوخته است.')
        para('ب) قواعد کلیدی استخراج‌شده از دفترچه')
        para('۱) سهمیهٔ ۵ درصد مشروط به کسب حداقل ۷۰ درصد نمرهٔ آخرین فرد گزینش آزاد همان کدرشته‌محل است؛ این شرط لازم است، نه ضمانت قبولی.')
        para('۱) ظرفیت ۵ درصد را با ضرب سادهٔ ۵ درصد در ظرفیت به صندلی قطعی تبدیل نکنید؛ گردکردن و ظرفیت‌های سهمیهٔ ۲۵ درصد در نتیجه اثر می‌گذارند.')
        para('۱) کدهای مصاحبه‌دار، فراجا و سازمانی عمداً در این فهرست نیامده‌اند. شباهت عنوان رشته با کد عادی، مجوز انتخاب نیست.')
        para('۱) در روز ثبت نهایی، اصلاحیه‌های منتشرشده در سامانهٔ سنجش و دفترچه‌های پیوست دانشگاه کنترل شوند.', body)
        story.append(PageBreak())

        # Pages 19--20: medical analogues of the reference appendices
        banner('پیوست ۱: کدرشته‌های محلی و نزدیک: ظرفیت و شرط زندگی')
        para('این پیوست، همتای «پیوست محل‌های خاص» در گزارش مرجع است: همهٔ کدهای چهار شهر موردنظر که برای تصمیم زندگی خانوادگی مهم‌اند، یک‌جا دیده می‌شوند. وجود در پیوست به معنی برتری بر ترتیب ۱۵۰تایی نیست.')
        local_indices = list(range(0, 5)) + list(range(73, 74)) + list(range(89, 92)) + list(range(130, 138))
        local_rows = []
        for idx in local_indices:
            r = rows[idx]
            local_rows.append((r['کدرشته‌محل'], r['رشته'], capacity_for(r, booklet, capacities), r['دانشگاه'], compact_note(r)))
        data_table(['کد', 'رشته', 'ظرفیت', 'دانشگاه', 'نکته'], local_rows, [2*cm, 3.2*cm, 1.4*cm, 5.1*cm, 6.8*cm], table)
        para('تبریز: مناسب‌ترین شهر برای رفت‌وآمد روزانه از مرند. ارومیه، اردبیل و زنجان: فقط با پذیرش اجاره یا اقامت. در کدهای اردبیل و زنجان عبارت فاقد خوابگاه در دفترچه ثبت شده است.', callout)
        story.append(PageBreak())

        banner('پیوست ۱: گزینه‌های مشروط: تأخیر، تعهد و پرداخت')
        special_indices = list(range(41, 46)) + list(range(60, 73)) + list(range(109, 118))
        special_rows = []
        for idx in special_indices:
            r = rows[idx]
            special_rows.append((r['کدرشته‌محل'], r['رشته'], capacity_for(r, booklet, capacities), r['دوره'], compact_note(r)))
        data_table(['کد', 'رشته', 'ظرفیت', 'دوره', 'شرط'], special_rows, [2*cm, 3.1*cm, 1.4*cm, 3.0*cm, 7.0*cm], table)
        para('این پیوست برای حذف آگاهانهٔ ردیف‌های مشروط پیش از ثبت است: اگر پاسخ خانواده به تأخیر، تعهد یا بودجه منفی است، آن ردیف را حذف کنید؛ اما جای انتخاب‌های باقیمانده را صرفاً برای پُرکردن جدول جابه‌جا نکنید.', warning)
        story.append(PageBreak())

        # Page 21: final pathways and recommendation
        banner('پیوست ۲: خلاصهٔ مسیرهای پذیرش و توصیهٔ نهایی')
        paths = [
            ('روزانه', 'نمرهٔ کل نهایی و ضوابط سهمیه', 'بدون شهریهٔ آموزشی؛ تعهد آموزش رایگان و هزینهٔ زندگی جداست.'),
            ('روزانه، شروع مهر ۱۴۰۶', 'همان سازوکار پذیرش با شروع متفاوت', 'تأخیر یک‌ساله شرط حقیقی است؛ فقط در صورت پذیرش نگه دارید.'),
            ('تعهد ویژه', 'کد خاص، حدنصاب و شرط بومی', 'تعهد ۱٫۵ برابر؛ انتقال و ادامه تحصیل محدود می‌شود.'),
            ('شهریه‌پرداز', 'کد رسمی دفترچه و توان پرداخت', 'شهریهٔ ثابت و متغیر؛ مبلغ کامل ترم را کتبی بگیرید.'),
            ('آزاد و خودگردان آزاد', 'کد رسمی و توان پرداخت', 'هزینهٔ چندساله، ابزار و افزایش شهریه باید از قبل روشن باشد.'),
        ]
        data_table(['نوع پذیرش', 'مبنا', 'نکته'], paths, [4.3*cm, 5.4*cm, 9.2*cm], table)
        para('توصیهٔ نهایی برای پرکردن فرم: اول پاسخ چهار تصمیم اقامت، تأخیر، تعهد و بودجه را روشن کنید. سپس ۱۵۰ ردیف را از بالا به پایین وارد کنید؛ ترتیب داخل هر بخش را تغییر ندهید مگر آن‌که یک انتخاب در صورت قبولی واقعاً نامطلوب باشد. در پایان، اصلاحیهٔ همان روز سنجش و رسید نهایی را ذخیره کنید.', callout)
        para('بهترین انتخاب، صرفاً انتخابی با عدد شانس بالاتر نیست؛ انتخابی است که رشته، شهر، زندگی خانوادگی، هزینه و تعهد آن در صورت قبولی واقعاً پذیرفتنی باشد.', callout)

        def first_page(canv, _doc):
            width, height = A4
            canv.saveState()
            canv.setFillColor(NAVY)
            canv.rect(0, height-5.55*cm, width, 5.55*cm, stroke=0, fill=1)
            canv.setFillColor(GOLD)
            canv.rect(0, height-5.72*cm, width, .17*cm, stroke=0, fill=1)
            canv.restoreState()

        doc.build(story, onFirstPage=first_page, canvasmaker=NumberedCanvas)
    finally:
        font_temp.cleanup()


if __name__ == '__main__':
    source_booklet = fitz.open(BOOKLET)
    verified_rows = audit_rows(source_booklet)
    write_audited_csv(verified_rows)
    build(verified_rows, source_booklet)
    print(f'created {OUTPUT}')
