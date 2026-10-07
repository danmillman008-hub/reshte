# -*- coding: utf-8 -*-
"""Fresh-research, reference-structured selection report for 1405.

This builder keeps the evidence and code audit of v2, but redesigns the report
in the layout requested by the user: navy cover/header bands, a golden accent,
long-form executive sections, compact alternating selection tables, and a
consistent three-part footer.
"""
from __future__ import annotations

import fitz
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from rebuild_audited_report_v2 import (
    AUDITED_CSV,
    BOOKLET,
    OUTPUT as V2_OUTPUT,
    audit_rows,
    extract_booklet_fonts,
    fa,
    text_p,
    write_audited_csv,
)

OUTPUT = V2_OUTPUT.parent / 'selection-plan-1405-researched-reference-v4.pdf'
NAVY = colors.HexColor('#22558E')
GOLD = colors.HexColor('#F0C33C')
PALE_BLUE = colors.HexColor('#D8E6F4')
ROW_BLUE = colors.HexColor('#F4F7FB')
TEXT = colors.HexColor('#172B4D')
MUTED = colors.HexColor('#68768A')


class NumberedCanvas(canvas.Canvas):
    """Write the consistent footer after the total page count is known."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._states = []

    def showPage(self):
        self._states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._states)
        for page_no, state in enumerate(self._states, start=1):
            self.__dict__.update(state)
            self._draw_footer(page_no, total)
            super().showPage()
        super().save()

    def _draw_footer(self, page_no, total):
        width, _height = A4
        self.saveState()
        self.setStrokeColor(colors.HexColor('#D8DDE6'))
        self.setLineWidth(.45)
        self.line(1.25*cm, 1.1*cm, width-1.25*cm, 1.1*cm)
        self.setFont('Roya', 8.5)
        self.setFillColor(MUTED)
        self.drawRightString(width-1.25*cm, .57*cm, fa('منبع: دفترچهٔ رسمی ۱۴۰۵ و منابع رفاهیِ معرفی‌شده در گزارش'))
        self.drawCentredString(width/2, .57*cm, fa(f'صفحهٔ {page_no} از {total}'))
        self.drawString(1.25*cm, .57*cm, fa('گزارش انتخاب رشتهٔ تجربی ۱۴۰۵: نسخهٔ بازطراحی‌شده'))
        self.restoreState()


def compact_note(row: dict[str, str]) -> str:
    code = row['کدرشته‌محل']
    if code == '31606':
        return 'اصلی؛ رفت‌وآمد از مرند'
    if code == '38602':
        return 'فقط با پذیرش تعهد ویژه'
    if row['شروع'] == 'مهر 1406':
        return 'فقط با پذیرش تأخیر یک‌ساله'
    if row['دوره'] == 'روزانه':
        if any(x in row['دانشگاه'] for x in ['ارومیه', 'اردبیل', 'زنجان']):
            return 'فقط با حل اقامت'
        return 'روزانه؛ پشتیبان'
    if 'شهریه' in row['دوره']:
        return 'فقط با بودجهٔ قطعی'
    if 'آزاد' in row['دوره']:
        return 'فقط با بودجهٔ قطعی'
    return 'پیش از ثبت بررسی شود'


def make_banner(story: list, title: str, banner_style: ParagraphStyle):
    band = Table([[text_p(title, banner_style)]], colWidths=[18.5*cm], hAlign='RIGHT')
    band.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), NAVY),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.white),
        ('RIGHTPADDING', (0, 0), (-1, -1), 9),
        ('LEFTPADDING', (0, 0), (-1, -1), 9),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.extend([band, Spacer(1, .34*cm)])


def build(rows: list[dict[str, str]], booklet: fitz.Document):
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    roya_file, titr_file, font_temp = extract_booklet_fonts(booklet)
    try:
        pdfmetrics.registerFont(TTFont('Roya', str(roya_file)))
        pdfmetrics.registerFont(TTFont('Titr', str(titr_file)))

        doc = SimpleDocTemplate(
            str(OUTPUT), pagesize=A4,
            rightMargin=1.25*cm, leftMargin=1.25*cm,
            topMargin=1.25*cm, bottomMargin=1.55*cm,
            title='گزارش کامل انتخاب رشتهٔ تجربی ۱۴۰۵',
            author='گزارش ممیزی‌شدهٔ انتخاب رشته',
        )
        base = getSampleStyleSheet()
        cover_title = ParagraphStyle('cover-title', parent=base['Title'], fontName='Titr', fontSize=23,
                                     leading=30, alignment=TA_RIGHT, textColor=colors.white, spaceAfter=6)
        cover_sub = ParagraphStyle('cover-sub', parent=base['Normal'], fontName='Roya', fontSize=13.5,
                                   leading=20, alignment=TA_RIGHT, textColor=colors.HexColor('#E6EEF7'), spaceAfter=5)
        cover_accent = ParagraphStyle('cover-accent', parent=base['Normal'], fontName='Titr', fontSize=12.5,
                                      leading=18, alignment=TA_RIGHT, textColor=GOLD, spaceAfter=7)
        banner = ParagraphStyle('banner', parent=base['Normal'], fontName='Titr', fontSize=13.5,
                                leading=18, alignment=TA_RIGHT, textColor=colors.white)
        body = ParagraphStyle('body', parent=base['BodyText'], fontName='Roya', fontSize=11.4,
                              leading=18.3, alignment=TA_RIGHT, textColor=TEXT, spaceAfter=5)
        body_small = ParagraphStyle('body-small', parent=body, fontSize=10.1, leading=15.2)
        table_text = ParagraphStyle('table', parent=body, fontSize=9.2, leading=12.6)
        list_text = ParagraphStyle('list', parent=body, fontSize=8.7, leading=11.3)
        callout = ParagraphStyle('callout', parent=body_small, backColor=colors.HexColor('#FFF9E8'),
                                 borderColor=GOLD, borderWidth=.55, borderPadding=7,
                                 textColor=TEXT, spaceBefore=5, spaceAfter=7)
        warning = ParagraphStyle('warning', parent=body_small, backColor=colors.HexColor('#FFF3F1'),
                                 borderColor=colors.HexColor('#D96C5D'), borderWidth=.55, borderPadding=7,
                                 textColor=colors.HexColor('#822B21'), spaceBefore=5, spaceAfter=7)
        story: list = []

        def para(s: str, style=body):
            story.append(text_p(s, style))

        def info_table(headers, data, widths, cell_style=table_text):
            content = [[text_p(x, cell_style) for x in headers]]
            for row in data:
                content.append([text_p(str(x), cell_style) for x in row])
            t = Table(content, colWidths=widths, hAlign='RIGHT', repeatRows=1)
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), PALE_BLUE),
                ('TEXTCOLOR', (0, 0), (-1, 0), NAVY),
                ('FONTNAME', (0, 0), (-1, -1), 'Roya'),
                ('GRID', (0, 0), (-1, -1), .18, colors.HexColor('#DCE3EB')),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, ROW_BLUE]),
                ('TOPPADDING', (0, 0), (-1, -1), 3.5),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3.5),
                ('RIGHTPADDING', (0, 0), (-1, -1), 5),
                ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ]))
            story.extend([t, Spacer(1, .24*cm)])

        # Cover. The navy rectangle itself is drawn by the first-page callback.
        story.append(Spacer(1, .35*cm))
        story.append(text_p('گزارش کامل انتخاب رشتهٔ تجربی ۱۴۰۵: تحلیل، شانس و فهرست ۱۵۰ انتخاب', cover_title))
        story.append(text_p('سهمیهٔ ایثارگران ۵ درصد: داوطلب متأهل، بومی آذربایجان شرقی و ساکن مرند', cover_sub))
        story.append(text_p('پژوهش مجدد: کارنامه، دادهٔ تاریخی، شانس قبولی، هزینه و همهٔ انتخاب‌ها', cover_accent))
        story.append(Spacer(1, 2.55*cm))
        cover_profile = [
            ('مشخصات داوطلب', ''),
            ('سهمیهٔ مؤثر', 'ایثارگران ۵ درصد'),
            ('رتبهٔ نهایی در سهمیه', '۶۷ از ۲۶٬۳۲۸ داوطلب'),
            ('رتبهٔ منطقهٔ ۳', '۲۹۹ از ۱۷۸٬۴۴۰ داوطلب'),
            ('رتبهٔ کشوری بدون سهمیه', '۱٬۶۹۰ از ۴۰۶٬۳۵۷ داوطلب'),
            ('نمرهٔ کل آزمون / سابقه / نهایی', '۱۰٬۲۸۷ / ۱۰٬۰۱۲ / ۱۰٬۱۲۲'),
            ('ترتیب علاقه', 'دندان‌پزشکی، سپس فیزیوتراپی، سپس داروسازی و سپس پزشکی'),
            ('محدودهٔ زندگی', 'مرند؛ تبریز اولویت رفت‌وآمدی و سه شهر ارومیه، اردبیل و زنجان فقط با برنامهٔ اقامت'),
            ('دوره‌های قابل بررسی', 'روزانه، شروع مهر ۱۴۰۶، تعهدی، شهریه‌پرداز و دانشگاه آزاد؛ هرکدام فقط با شرط مشخص'),
        ]
        # Cover profile intentionally uses simple lines rather than a dense grid.
        for label, value in cover_profile:
            if not value:
                para(label, ParagraphStyle('profile-head', parent=body, fontName='Titr', fontSize=12.5,
                                             textColor=NAVY, leading=18, spaceAfter=1))
            else:
                para(f'{label}: {value}', body_small)
        story.append(Spacer(1, .1*cm))
        para('این نسخه از ابتدا بازپژوهی شده است: همهٔ کدها با دفترچهٔ رسمی ۱۴۰۵ تطبیق خورده‌اند؛ شانس‌های صفحهٔ ۸ نیز یک برآورد تصمیم‌یار با بازه، منبع و درجهٔ اطمینان‌اند، نه تضمین سازمان سنجش.', callout)
        story.append(PageBreak())

        # Page 2: executive summary and controlled bands
        make_banner(story, 'خلاصهٔ اجرایی: در یک نگاه', banner)
        para('فهرست ۱۵۰تایی در ۹ بخش چیده شده است. منطق چینش «علاقهٔ واقعی، سپس امکان زندگی و هزینه، سپس پشتیبان» است؛ نه پُرکردن فرم با کدهایی که صرفاً آسان‌تر به نظر می‌رسند. انتخاب‌های بالاتر از انتخاب پذیرفته‌شده بررسی نمی‌شوند، پس ردیف بالاتر باید واقعاً مطلوب‌تر باشد.')
        para('نتیجهٔ کلیدی: دندان‌پزشکی روزانهٔ تبریز نخستین انتخاب عملی است و در مدل شانس، «قوی اما غیرقطعی» ارزیابی می‌شود. ارومیه، اردبیل و زنجان برای دندان روزانه پشتیبان‌های قوی‌ترند اما اقامت می‌خواهند. کد ۳۸۶۰۲ دندان تعهدی تبریز فقط پس از پذیرش آگاهانهٔ تعهد ویژه درج می‌شود. فیزیوتراپی تبریز، داروسازی روزانهٔ تبریز و پزشکی روزانهٔ تبریز پشتیبان‌های رشته‌ای بعدی‌اند.')
        bands = [
            ('۱', 'دندان روزانهٔ محلی و نزدیک', '۵', 'تبریز، ارومیه، اردبیل و زنجان؛ اولویت واقعی'),
            ('۲', 'دندان روزانهٔ ملی', '۳۶', 'پشتیبان دندان؛ شهر دور فقط با اقامت'),
            ('۳', 'دندان روزانهٔ شروع مهر ۱۴۰۶', '۱۹', 'فقط با پذیرش تأخیر یک‌ساله'),
            ('۴', 'دندان تعهدی و پرداختی', '۱۳', 'تعهد/بودجه باید پیشاپیش تأیید شود'),
            ('۵', 'فیزیوتراپی روزانه', '۱۶', 'پشتیبان دوم پس از همهٔ دندان‌ها'),
            ('۶', 'داروسازی روزانه', '۲۰', 'پشتیبان سوم؛ تبریز در ابتدای بخش'),
            ('۷', 'داروسازی پرداختی/آزاد', '۲۱', 'فقط با بودجهٔ قطعی و استعلام دانشگاه'),
            ('۸', 'پزشکی روزانهٔ چهار شهر', '۸', 'پشتیبان نهاییِ نزدیک‌تر'),
            ('۹', 'پزشکی روزانهٔ ملی', '۱۲', 'پوشش ملی با شرط اقامت'),
        ]
        info_table(['بخش', 'کد', 'تعداد', 'کارکرد'], [(b, a, n, d) for b, a, n, d in bands], [8.8*cm, 2.0*cm, 2.2*cm, 5.5*cm])
        para('قواعد فوری: ۱) ردیف‌های «شروع مهر ۱۴۰۶» در صورت نپذیرفتن تأخیر حذف می‌شوند؛ ۲) کد ۳۸۶۰۲ در صورت نپذیرفتن تعهد ویژه حذف می‌شود؛ ۳) هر دورهٔ شهریه‌پرداز یا آزاد بدون بودجهٔ کتبی حذف می‌شود؛ ۴) شهرهای دور بدون برنامهٔ اقامت حذف می‌شوند.', warning)
        story.append(PageBreak())

        # Page 3: local core and no-made-up probability
        make_banner(story, 'انتخاب‌های محلی: ظرفیت، محدودیت و حکم عملی', banner)
        para('دفترچهٔ رسمی، ظرفیت و دوره را اعلام می‌کند؛ اما آخرین نمره/رتبهٔ قبولی سهمیهٔ ۵٪ هر کدرشته‌محل را منتشر نمی‌کند. به همین دلیل، شانس‌های این گزارش از ترکیب رتبهٔ ۶۷، نمرهٔ کل ۱۰٬۱۲۲، ظرفیت ۱۴۰۵، بومی‌بودن و نمونه‌های تاریخیِ هم‌سهمیه ساخته شده‌اند؛ بازه‌اند، نه حکم قطعی.')
        local = [
            ('دندان تبریز', '۳۱۶۰۶', '۳۳', 'روزانه', 'رفت‌وآمدی؛ انتخاب نخست', '۴۷'),
            ('دندان ارومیه', '۳۱۷۰۶', '۲۴', 'روزانه', 'فقط با اقامت؛ عدم تعهد خوابگاه', '۵۱'),
            ('دندان اردبیل', '۳۱۷۸۲، ۳۱۷۸۳', '۱۱ + ۱۱', 'روزانه', 'فقط با اقامت؛ فاقد خوابگاه', '۵۴'),
            ('دندان زنجان', '۳۲۷۳۳', '۱۴', 'روزانه', 'فقط با اقامت؛ فاقد خوابگاه', '۹۲'),
            ('دندان تعهدی تبریز', '۳۸۶۰۲', '۳۰', 'تعهد ویژه', 'تعهد ۱٫۵ برابر؛ شرط جداگانه', '۱۴۸'),
            ('فیزیوتراپی تبریز', '۳۱۶۲۲', '۲۰', 'روزانه', 'پشتیبان رشته‌ایِ رفت‌وآمدی', '۴۸'),
            ('داروسازی تبریز', '۳۱۶۰۴، ۳۱۶۰۵', '۳۰ + ۳۰', 'روزانه', 'پشتیبان روزانهٔ محلی', '۴۷'),
            ('پزشکی تبریز', '۳۱۶۰۱، ۳۱۶۰۳', '۵۴ + ۵۵', 'روزانه', 'کد عادی؛ نه کد مصاحبه‌دار', '۴۷'),
            ('پزشکی زنجان', '۳۲۷۲۸، ۳۲۷۳۰', '۵۶ + ۵۷', 'روزانه', 'فقط با اقامت؛ فاقد خوابگاه', '۹۱'),
        ]
        info_table(['رشته/شهر', 'کد', 'ظرفیت', 'دوره', 'یادداشت تصمیم', 'ص.'], local,
                   [3.3*cm, 2.25*cm, 2.0*cm, 2.2*cm, 6.15*cm, .6*cm])
        para('کدهای دارای مصاحبه، فراجا، سپاه یا شرایط خاص عمداً در فرم وارد نشده‌اند. شباهت عنوان رشته با کد عادی کافی نیست؛ شرطِ ستون توضیحات دفترچه تعیین‌کننده است.', warning)
        story.append(PageBreak())

        # Page 4: method and source integrity
        make_banner(story, 'روش کار و منابع: چرا این انتخاب‌ها؟', banner)
        para('۱) منبع اصلی: بخش رشته‌محل‌های علوم پزشکی دفترچهٔ انتخاب رشتهٔ تجربی ۱۴۰۵. کدها با استخراج مستقیم از فایل و کنترل رشته و دوره در متن همان صفحه ممیزی شده‌اند. برای همهٔ ۱۵۰ ردیف، شماره صفحه کنار انتخاب درج شده است.')
        para('۲) فیلتر شخصی: رشته‌های هدف بر اساس اولویت اعلام‌شده نگه داشته شده‌اند؛ کدهای مصاحبه‌دار یا سازمانی حذف شده‌اند؛ دوره‌های تعهدی، تأخیری و پرداختی به‌جای پنهان‌شدن، با برچسب شرط ثبت نشان داده شده‌اند.')
        para('۳) منطق شهر: تبریز تنها مسیر رفت‌وآمد روزانهٔ واقع‌بینانه است. ارومیه، اردبیل و زنجان در فهرست به‌عنوان پشتیبان نگه داشته شده‌اند، ولی گزارش آن‌ها را بدون اقامت «ساده» فرض نمی‌کند.')
        para('۴) شانس: رتبهٔ ۶۷ در سهمیهٔ ۵٪ مبنای رقابت سهمیه‌ای است. برای ساخت بازهٔ شانس، نمونه‌های منتشرشدهٔ سال‌های اخیر از همان سهمیه، ظرفیت ۱۴۰۵ و فاصلهٔ رتبهٔ داوطلب از نمونه‌ها به‌کار رفته‌اند. چون سنجش جدول رسمیِ آخرین رتبه را منتشر نمی‌کند، بازه‌ها محافظه‌کارانه و دارای درجهٔ اطمینان‌اند.')
        para('۵) هزینه: تنها اجزای منتشرشدهٔ شهریهٔ دوره‌های شهریه‌پرداز علوم پزشکی نقل شده‌اند؛ برای آزاد تبریز عدد قطعی بدون جدول کتبی واحد ارائه نمی‌شود.', callout)
        info_table(['منبع', 'درجهٔ اتکا', 'کاربرد'], [
            ('دفترچهٔ رسمی ۱۴۰۵، صفحات ۲۰ تا ۲۸ و ۴۷ تا ۱۴۸', 'یک', 'کد، رشته، دوره، ظرفیت، شروع، تعهد و قواعد رتبه'),
            ('کارنامهٔ ارائه‌شده توسط داوطلب', 'یک', 'رتبه، نمرهٔ کل، سهمیه و دادهٔ بومی'),
            ('صفحات رسمی خوابگاه تبریز و ارومیه', 'یک', 'ظرفیت/شیوهٔ تخصیص؛ نه تضمین واگذاری'),
            ('نمونه‌کارنامه‌های سهمیهٔ ۵٪؛ پاسخباما، دانتل و مشاورگروپ', 'سه', 'فقط کالیبراسیون بازهٔ شانس؛ نه آخرین رتبهٔ قطعی'),
            ('گزارش ابلاغ شهریهٔ وزارت بهداشت', 'دو', 'شهریهٔ ثابت و متغیر دوره‌های شهریه‌پرداز'),
            ('صفحات رسمی خوابگاه و مسیریاب عمومی', 'یک/سه', 'وضعیت خوابگاه و برآورد رفت‌وآمد'),
        ], [8.8*cm, 2.7*cm, 7.0*cm])
        story.append(PageBreak())

        # Page 5: candidate inputs and historical evidence
        make_banner(story, 'دادهٔ کارنامه و دادهٔ تاریخی: مبنای برآورد شانس', banner)
        para('رتبهٔ ۶۷ در سهمیهٔ نهایی ایثارگران ۵٪، معیار اول مدل است؛ نه رتبهٔ ۲۹۹ منطقهٔ ۳. رتبهٔ منطقه و رتبهٔ کشوری بدون سهمیه برای کنترل سازگاری تصویر کلی استفاده می‌شوند، ولی با رتبهٔ سهمیه جابه‌جا نمی‌شوند.')
        inputs = [
            ('رتبهٔ نهایی سهمیه', '۶۷ از ۲۶٬۳۲۸', 'متغیر اصلی مقایسه با نمونه‌های سهمیهٔ ۵٪'),
            ('نمرهٔ کل نهایی', '۱۰٬۱۲۲', 'کنترل حدنصاب و سطح علمی؛ رتبه جای نمره را نمی‌گیرد'),
            ('رتبهٔ منطقهٔ ۳', '۲۹۹', 'کنترل فرعی برای مسیرهای غیرسهمیه‌ای'),
            ('رتبهٔ کشوری بدون سهمیه', '۱٬۶۹۰', 'شاخص عمومی رقابت؛ نه مبنای گزینش سهمیه‌ای'),
            ('ظرفیت رسمی محلی', 'دندان تبریز ۳۳؛ پزشکی تبریز ۱۰۹', 'هرچه ظرفیت بیشتر، بازهٔ شانس پایدارتر'),
            ('نمونه‌های منتشرشدهٔ هم‌سهمیه', 'پزشکی تبریز: ۷۶، ۸۵، ۹۵ و یک گزارش ۳۵۴', 'پراکنده و سال‌وابسته؛ به همین علت بازه‌ها پهن‌اند'),
            ('نمونهٔ دندان هم‌سهمیه', 'دادهٔ پراکنده؛ تراز ۹٬۸۷۳ در یک گزارش ۱۴۰۲', 'برای جهت‌دهی، نه پیش‌بینی دقیق دانشگاهی'),
        ]
        info_table(['داده', 'مقدار/نمونه', 'اثر در تحلیل'], inputs, [4.1*cm, 5.1*cm, 9.3*cm])
        para('منابع تاریخیِ وبی با درجهٔ اتکای سه‌اند: «پاسخباما» برای نمونه‌های پزشکی ۵٪، «دانتل» برای نمونه‌های ۷۶ و «مشاورگروپ» برای ترازهای ۱۴۰۲. تناقض میان آن‌ها خودِ دلیل استفاده از بازهٔ احتمال است. منبع رسمی همچنان فقط دفترچهٔ ۱۴۰۵ است.', callout)
        story.append(PageBreak())

        # Page 6: legal distinctions
        make_banner(story, 'سهمیه، تعهد و دوره‌ها: مرزهایی که نباید مخلوط شوند', banner)
        para('رتبهٔ ۶۷ در سهمیهٔ نهایی ایثارگران ۵٪، رتبهٔ تصمیم‌ساز این پرونده است. رتبهٔ ۲۹۹ منطقهٔ ۳ و رتبهٔ کشوریِ بدون سهمیه برای تصویر مکمل‌اند، اما جای رتبهٔ سهمیه را نمی‌گیرند. دفترچه توضیح می‌دهد ظرفیت هر کدرشته‌محل بعد از اعمال سهمیه‌های ایثارگری و متناسب با نوع گزینش توزیع می‌شود.')
        rules = [
            ('روزانهٔ عادی با سهمیهٔ ایثارگران', 'تعهد استفاده از آموزش رایگان، یک برابر مدت تحصیل پس از فراغت؛ ص. ۲۰.', 'تعهد عمومیِ آموزش رایگان است.'),
            ('دندان تعهدی تبریز؛ ۳۸۶۰۲', 'تعهد ۱٫۵ برابر مدت تحصیل در مناطق موردنیاز، عدم امکان خرید/انتقال و محدودیت ادامه تحصیل تا نیمهٔ تعهد؛ ص. ۱۴۷ تا ۱۴۸.', 'کد ویژه است؛ قبل از ثبت تعهدنامه خوانده شود.'),
            ('شهریه‌پرداز و آزاد', 'تعهد آموزش رایگانِ دورهٔ روزانه ندارد؛ ص. ۲۱.', 'هزینه، اقامت و مقررات حرفه‌ای مستقل جدا بررسی شود.'),
            ('شروع مهر ۱۴۰۶', 'در بخش مستقل شروع مهر ۱۴۰۶ دفترچه آمده است.', 'یک‌سال تأخیر، شرط واقعی ثبت است.'),
        ]
        info_table(['نوع', 'قاعدهٔ رسمی', 'حکم اجرایی'], rules, [4.0*cm, 8.4*cm, 6.1*cm])
        story.append(PageBreak())

        # Page 7: calibrated acceptance chances
        make_banner(story, 'برآورد شانس قبولی: بازهٔ تصمیم‌یار، نه وعدهٔ قبولی', banner)
        para('این جدول همان نقش جدول «شانس قبولی» در گزارش مرجع را دارد، اما مدل آن شفاف است. رتبهٔ ۶۷ سهمیهٔ ۵٪ با نمونه‌های انتشار‌یافتهٔ ۵٪، ظرفیت ۱۴۰۵، بومی‌بودن و درجهٔ تقاضا مقایسه شده است. سازمان سنجش هیچ‌یک از این درصدها را تأیید یا منتشر نکرده است.')
        chances = [
            ('دندان روزانهٔ تبریز؛ ۳۱۶۰۶', '۶۵ تا ۸۰٪', 'قوی', 'متوسط', 'هدف اول؛ ظرفیت ۳۳ و رفت‌وآمد مناسب'),
            ('دندان روزانهٔ ارومیه؛ ۳۱۷۰۶', '۷۸ تا ۹۰٪', 'قوی', 'کم تا متوسط', 'پشتیبان دندان؛ شرط اقامت/خوابگاه'),
            ('دندان روزانهٔ اردبیل؛ ۳۱۷۸۲ و ۳۱۷۸۳', '۸۰ تا ۹۲٪', 'بسیار قوی', 'کم تا متوسط', 'پشتیبان قوی؛ فاقد خوابگاه'),
            ('دندان روزانهٔ زنجان؛ ۳۲۷۳۳', '۷۵ تا ۸۹٪', 'قوی', 'کم تا متوسط', 'پشتیبان قوی؛ فاصلهٔ بیشتر'),
            ('دندان تعهدی تبریز؛ ۳۸۶۰۲', '۸۸ تا ۹۶٪', 'بسیار قوی', 'متوسط', 'شانس بهتر، اما تعهد ۱٫۵ برابر'),
            ('فیزیوتراپی روزانهٔ تبریز؛ ۳۱۶۲۲', '۹۲ تا ۹۷٪', 'بسیار قوی', 'متوسط', 'ایمن‌ترین پشتیبانِ رایگان و رفت‌وآمدی'),
            ('داروسازی روزانهٔ تبریز؛ ۳۱۶۰۴ و ۳۱۶۰۵', '۸۸ تا ۹۵٪', 'بسیار قوی', 'متوسط', 'ظرفیت جمعاً ۶۰؛ پشتیبان سوم'),
            ('پزشکی روزانهٔ تبریز؛ ۳۱۶۰۱ و ۳۱۶۰۳', '۶۰ تا ۷۸٪', 'میانه تا قوی', 'کم', 'نمونه‌های تاریخی متناقض؛ ظرفیت جمعاً ۱۰۹'),
            ('پزشکی روزانهٔ ارومیه/اردبیل/زنجان', '۷۵ تا ۹۰٪', 'قوی', 'کم', 'فقط در صورت حل اقامت خانوادگی'),
            ('دندان شهریه‌پرداز/آزاد تبریز', '۸۰ تا ۹۵٪', 'قوی', 'کم', 'شانس پذیرش با توان مالی یکی نیست'),
        ]
        info_table(['گزینه', 'بازهٔ برآورد', 'حکم', 'اطمینان داده', 'توضیح'], chances,
                   [4.25*cm, 2.15*cm, 2.05*cm, 2.3*cm, 5.75*cm], list_text)
        para('چگونه خوانده شود: «۶۵ تا ۸۰٪» یعنی با اطلاعات موجود، احتمال را در این بازه می‌دانیم؛ نه این‌که سازمان سنجش یا دانشگاه چنین عددی داده باشد. اگر سهمیه در کارنامه نهایی تأیید نشود، حدنصاب علمی عبور نکند، ظرفیت/اصلاحیه تغییر کند یا ترکیب رقبا متفاوت باشد، این بازه بی‌اعتبار می‌شود.', warning)
        story.append(PageBreak())

        # Page 8: housing and finances
        make_banner(story, 'خوابگاه، اقامت و هزینه: واقعیت زندگی بعد از قبولی', banner)
        para('تبریز از مرند در حدود یک ساعت یک‌طرفه است و تنها گزینهٔ واقعی برای رفت‌وآمد روزانه به شمار می‌آید. ارومیه، اردبیل و زنجان از منظر زندگی خانوادگی «انتخاب دور» محسوب می‌شوند؛ بنابراین مزیت آموزشی آن‌ها نباید به اشتباه، تضمین عملیِ زندگی روزمره تلقی شود.')
        lodging = [
            ('تبریز', 'صفحهٔ رسمی: خوابگاه متأهلی ۶۳ واحدی؛ واگذاری امتیازی و نوبتی.', 'وجود خوابگاه تضمین نیست؛ گزینهٔ اصلیِ رفت‌وآمد.'),
            ('ارومیه', 'دو بلوک متأهلی، هرکدام ۱۲ واحد؛ در دفترچه عدم تعهد واگذاری خوابگاه.', 'اجاره یا اقامت هفتگی باید از قبل قابل تأمین باشد.'),
            ('اردبیل', 'در کدهای منتخب دفترچه: فاقد خوابگاه.', 'فقط با پذیرش اقامت.'),
            ('زنجان', 'در کدهای منتخب دفترچه: فاقد خوابگاه.', 'فقط با پذیرش اقامت.'),
        ]
        info_table(['شهر', 'سند رفاهی', 'نتیجه'], lodging, [2.5*cm, 7.4*cm, 8.6*cm])
        para('دوره‌های شهریه‌پرداز علوم پزشکی: شهریهٔ ثابت دکتری عمومی پزشکی، دندان‌پزشکی و داروسازی در گزارش ابلاغ سال تحصیلی ۱۴۰۵ تا ۱۴۰۶، حدود ۳۴٫۱۹ میلیون تومان در هر نیمسال است و شهریهٔ متغیر واحدها جداگانه افزوده می‌شود. این رقم، هزینهٔ کامل ترم نیست.')
        para('دانشگاه آزاد تبریز: نرخ کتبیِ قابل استناد برای واحد و ورودی مورد نظر در منابع بررسی‌شده یافت نشد. پس هیچ رقم تبلیغاتی یا تخمینی نباید مبنای ثبت کدهای آزاد باشد؛ امور مالی دانشگاه باید جدول شهریه، افزایش سالانه، هزینهٔ کلینیکی و شیوهٔ پرداخت را کتبی اعلام کند.', warning)
        story.append(PageBreak())

        # Page 9: operational decisions and pre-list audit
        make_banner(story, 'تصمیم‌های شخصی پیش از تکمیل فرم', banner)
        decisions = [
            ('پذیرش شروع مهر ۱۴۰۶', 'ردیف‌های ۴۲ تا ۶۰ باقی می‌مانند.', 'تمام ردیف‌های شروع مهر ۱۴۰۶ حذف شوند.'),
            ('پذیرش تعهد ویژهٔ تبریز', 'کد ۳۸۶۰۲ باقی می‌ماند؛ متن تعهد باید پیشاپیش خوانده شود.', 'کد ۳۸۶۰۲ حذف شود.'),
            ('بودجهٔ شهریه و آزاد', 'فقط ردیف‌های دارای تأیید کتبی هزینه و منبع پرداخت باقی بمانند.', 'همهٔ ردیف‌های شهریه‌پرداز و آزاد حذف شوند.'),
            ('حل اقامت در شهر دور', 'ارومیه، اردبیل، زنجان و پشتیبان‌های ملی باقی بمانند.', 'کدهای دورِ غیرقابل رفت‌وآمد حذف شوند.'),
        ]
        info_table(['تصمیم', 'اگر پاسخ بله است', 'اگر پاسخ خیر است'], decisions, [4.1*cm, 7.1*cm, 7.3*cm])
        para('کنترل فنی فهرست: ۱۵۰ ردیف، ۱۵۰ کدرشته‌محل یکتا، وجود هر کد در دفترچه، هم‌خوانی رشته و دوره با متن همان صفحه و برچسب مستقل برای شروع مهر ۱۴۰۶. ستون «ص.» در هر ردیف، مسیر کنترل مستقیم را می‌دهد.', callout)
        para('از اینجا به بعد، فهرست اصلی می‌آید. هر گروه از علاقه‌مندتر به پشتیبان‌تر چیده شده است. درون هر گروه، ترتیب را فقط پس از پاسخ به چهار تصمیم بالا تغییر دهید.', body)

        # Selection pages: 15 rows at a time, with the same compact visual
        # hierarchy used in the reference report.
        groups = [
            ('فهرست نهایی: دندان‌پزشکی روزانهٔ محلی و ملی', rows[:41], 15),
            # These two groups use sixteen readable table rows per page so the
            # whole document retains the 21-page architecture of the reference.
            ('فهرست نهایی: دندان‌پزشکی شروع مهر ۱۴۰۶ و گزینه‌های مشروط', rows[41:73], 16),
            ('فهرست نهایی: فیزیوتراپی روزانه', rows[73:89], 16),
            ('فهرست نهایی: داروسازی روزانه', rows[89:109], 20),
            ('فهرست نهایی: داروسازی شهریه‌پرداز و آزاد', rows[109:130], 15),
            ('فهرست نهایی: پزشکی روزانه', rows[130:150], 15),
        ]
        start = 1
        for title, group_rows, per_page in groups:
            for page_start in range(0, len(group_rows), per_page):
                story.append(PageBreak())
                suffix = '' if page_start == 0 else ': ادامه'
                make_banner(story, title + suffix, banner)
                chunk = group_rows[page_start:page_start+per_page]
                table_rows = []
                for n, row in enumerate(chunk, start + page_start):
                    # Table cell order is reversed so priority remains at the
                    # right edge in a right-to-left reading pattern.
                    table_rows.append((
                        compact_note(row),
                        f"ص. {row['صفحه رسمی 1405']}",
                        f"{row['دوره']} / {row['شروع']}",
                        row['دانشگاه'],
                        row['رشته'],
                        row['کدرشته‌محل'],
                        str(n),
                    ))
                info_table(['شرط / یادداشت', 'ص.', 'دوره / شروع', 'دانشگاه / شهر', 'رشته', 'کدرشته‌محل', '#'],
                           table_rows, [3.7*cm, .75*cm, 2.4*cm, 4.25*cm, 2.5*cm, 2.0*cm, .8*cm], list_text)
            start += len(group_rows)

        # Final appendix page
        story.append(PageBreak())
        make_banner(story, 'پیوست: مسیرهای پذیرش و توصیهٔ نهایی', banner)
        routes = [
            ('روزانه', 'نمرهٔ کل نهایی + رعایت ضوابط', 'رایگان از حیث شهریه؛ تعهد آموزش رایگان و شرایط خوابگاه را جدا بخوانید.'),
            ('شروع مهر ۱۴۰۶', 'همان سازوکار پذیرش، با شروع متفاوت', 'یک‌سال تأخیر حقیقی است؛ در فهرست با برچسب روشن آمده است.'),
            ('تعهد ویژه', 'کد ویژه + حدنصاب و شرایط خاص', 'تعهد ۱٫۵ برابر، محدودیت انتقال و محل خدمت پس از فراغت.'),
            ('شهریه‌پرداز', 'کد رسمی دفترچه + توان پرداخت', 'شهریهٔ ثابت به‌علاوهٔ متغیر؛ مبلغ کامل را کتبی بگیرید.'),
            ('آزاد تمام‌وقت/خودگردان', 'کد رسمی دفترچه + توان پرداخت', 'بدون جدول رسمی واحد، هیچ رقم یا تعهد مالی فرض نشود.'),
        ]
        info_table(['نوع مسیر', 'مبنای کنترل', 'نکته'], routes, [3.5*cm, 5.5*cm, 8.7*cm])
        para('توصیهٔ نهایی برای پر کردن فرم: ابتدا چهار تصمیمِ تأخیر، تعهد، اقامت و بودجه را ببندید. سپس انتخاب‌های حذف‌شده را بدون جابه‌جا کردن بی‌منطقِ بقیه کنار بگذارید. در پایان، هر کد را با اصلاحیهٔ همان روز سنجش و دفترچهٔ پیوست دانشگاه تطبیق دهید و رسید نهایی سامانه را ذخیره کنید.', callout)
        para('بهترین انتخاب، کدی نیست که صرفاً احتمال بیشتری دارد؛ کدی است که در صورت قبولی، رشته، شهر، هزینه، خوابگاه و تعهد آن واقعاً برای زندگی خانوادگی پذیرفتنی است.', callout)

        def first_page_background(canv, _doc):
            width, height = A4
            canv.saveState()
            canv.setFillColor(NAVY)
            canv.rect(0, height-5.55*cm, width, 5.55*cm, stroke=0, fill=1)
            canv.setFillColor(GOLD)
            canv.rect(0, height-5.72*cm, width, .17*cm, stroke=0, fill=1)
            canv.restoreState()

        doc.build(story, onFirstPage=first_page_background, canvasmaker=NumberedCanvas)
    finally:
        font_temp.cleanup()


if __name__ == '__main__':
    booklet = fitz.open(BOOKLET)
    audited_rows = audit_rows(booklet)
    write_audited_csv(audited_rows)
    build(audited_rows, booklet)
    print(f'created {OUTPUT}')
    print(f'audited data source: {AUDITED_CSV}')
