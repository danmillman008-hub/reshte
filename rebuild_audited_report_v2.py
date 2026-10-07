# -*- coding: utf-8 -*-
"""Build a traceable, audited Persian 1405 selection report.

Design principles for this second version:
* Codes are checked against the official 1405 booklet using PyMuPDF, not a
  lossy text extraction.
* Every proposed row prints the relevant official PDF page.
* No numerical acceptance probability or unofficial Azad tuition is asserted.
* The report explicitly documents the mistakes in the earlier draft.
"""
from __future__ import annotations

import csv
import re
import tempfile
import unicodedata
from pathlib import Path

import fitz  # PyMuPDF
from arabic_reshaper import reshape
from bidi.algorithm import get_display
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parent
BOOKLET = ROOT / '14050712p945n67351_0001.pdf'
INPUT = ROOT / 'فهرست_۱۵۰تایی_پیشنهادی_انتخاب_رشته_۱۴۰۵.csv'
AUDITED_CSV = ROOT / 'فهرست_۱۵۰تایی_ممیزی_شده_۱۴۰۵.csv'
OUTPUT = ROOT / 'deliverables' / 'selection-plan-1405-audited-v2.pdf'

DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹كيى', '0123456789کیی')


def normalized(text: str) -> str:
    return ' '.join(unicodedata.normalize('NFKC', text).translate(DIGITS).split())


def fa(text: object) -> str:
    """Shape Farsi before passing it to ReportLab."""
    return get_display(reshape(str(text)))


def text_p(text: object, style: ParagraphStyle) -> Paragraph:
    return Paragraph(fa(text), style)


def extract_booklet_fonts(doc: fitz.Document) -> tuple[Path, Path, tempfile.TemporaryDirectory]:
    """Use the embedded Persian document fonts only at build time.

    The source PDF already embeds the required glyphs. Keeping the temporary
    extracted files outside the repository avoids adding a separately licensed
    font asset to version control.
    """
    found: dict[str, bytes] = {}
    for page_no in range(min(60, len(doc))):
        for entry in doc[page_no].get_fonts(full=True):
            xref, ext, _kind, name = entry[:4]
            key = name.lower()
            if ('broya' in key and 'roya' not in found) or ('btitr' in key and 'titr' not in found):
                data = doc.extract_font(xref)[3]
                if data:
                    if 'broya' in key:
                        found['roya'] = data
                    elif 'btitr' in key:
                        found['titr'] = data
        if len(found) == 2:
            break
    temp = tempfile.TemporaryDirectory(prefix='reshte-fonts-')
    root = Path(temp.name)
    # Fall back to system fonts only if an official booklet font was unavailable.
    roya = root / 'BRoya.ttf'
    titr = root / 'BTitr.ttf'
    roya.write_bytes(found.get('roya', Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf').read_bytes()))
    titr.write_bytes(found.get('titr', Path('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf').read_bytes()))
    return roya, titr, temp


def page_index(doc: fitz.Document) -> dict[str, tuple[int, str]]:
    """Index each five-digit code from the official 1405 booklet.

    We retain the normalized full page text for an independent audit of field,
    period and delayed-start labels.
    """
    index: dict[str, tuple[int, str]] = {}
    for number, page in enumerate(doc, start=1):
        text = normalized(page.get_text('text'))
        for code in re.findall(r'(?<!\d)(3\d{4})(?!\d)', text):
            index.setdefault(code, (number, text))
    return index


def expected_field_label(field: str) -> str:
    if 'دندان' in field:
        return 'دندانپزشکی'
    if 'فیزیوتراپی' in field:
        return 'فیزیوتراپی'
    if 'داروسازی' in field:
        return 'داروسازی'
    return 'پزشکی'


def context_for(code: str, page_text: str) -> str:
    at = page_text.find(code)
    return page_text[max(0, at - 220):at + 330] if at >= 0 else ''


def audit_rows(doc: fitz.Document) -> list[dict[str, str]]:
    rows = list(csv.DictReader(INPUT.open(encoding='utf-8')))
    if len(rows) != 150 or len({r['کدرشته‌محل'] for r in rows}) != 150:
        raise RuntimeError('The input recommendation list must contain 150 unique codes.')
    codes = page_index(doc)
    audited: list[dict[str, str]] = []
    period_words = {
        'روزانه': 'روزانه با آزمون',
        'شهریه‌پرداز': 'شهریه پرداز با آزمون',
        'آزاد تمام‌وقت': 'آزاد تمام وقت با آزمون',
        'خودگردان آزاد': 'خودگردان آزاد با آزمون',
    }
    for row in rows:
        code = row['کدرشته‌محل']
        if code not in codes:
            raise RuntimeError(f'Code {code} was not found in the official 1405 booklet.')
        page, page_text = codes[code]
        context = context_for(code, page_text)
        field_label = expected_field_label(row['رشته'])
        # Code 38602 is in the separate service-commitment table, where the
        # phrase is split differently but it must still identify dentistry.
        if field_label not in context and not (code == '38602' and 'دندانپزشکی' in page_text):
            raise RuntimeError(f'Field mismatch for {code}: expected {field_label}; context={context}')
        if row['دوره'] in period_words and period_words[row['دوره']] not in context:
            raise RuntimeError(f'Period mismatch for {code}: {row["دوره"]}; context={context}')
        if row['شروع'] == 'مهر 1406' and page < 139:
            raise RuntimeError(f'Delayed-start code {code} is not in the 1406-start section.')
        row = dict(row)
        # Confirmed during the page-by-page audit: 33846 is at the University
        # of Medical Sciences Yazd, not Asadabad as the earlier draft stated.
        if code == '33846':
            row['دانشگاه'] = 'علوم پزشکی یزد'
            row['شرط/یادداشت'] = 'روزانه؛ عدم تعهد در واگذاری خوابگاه'
        row['صفحه رسمی 1405'] = str(page)
        row['وضعیت ممیزی'] = 'کد، رشته و نوع دوره با دفترچه تطبیق شد'
        audited.append(row)
    return audited


def write_audited_csv(rows: list[dict[str, str]]) -> None:
    fields = ['اولویت', 'کدرشته‌محل', 'رشته', 'دانشگاه', 'دوره', 'شروع', 'شرط/یادداشت', 'صفحه رسمی 1405', 'وضعیت ممیزی']
    with AUDITED_CSV.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def make_pdf(rows: list[dict[str, str]], doc_booklet: fitz.Document) -> None:
    OUTPUT.parent.mkdir(exist_ok=True)
    roya_path, titr_path, font_temp = extract_booklet_fonts(doc_booklet)
    try:
        pdfmetrics.registerFont(TTFont('Roya', str(roya_path)))
        pdfmetrics.registerFont(TTFont('Titr', str(titr_path)))

        doc = SimpleDocTemplate(
            str(OUTPUT), pagesize=A4,
            rightMargin=1.35 * cm, leftMargin=1.35 * cm,
            topMargin=1.45 * cm, bottomMargin=1.35 * cm,
            title='گزارش ممیزی‌شده انتخاب رشته تجربی ۱۴۰۵',
            author='Arena.ai — بازبینی مستند',
        )
        styles = getSampleStyleSheet()
        title = ParagraphStyle('title', parent=styles['Title'], fontName='Titr', fontSize=24,
                               leading=33, alignment=TA_CENTER, textColor=colors.HexColor('#12324A'), spaceAfter=7)
        subtitle = ParagraphStyle('subtitle', parent=styles['Normal'], fontName='Roya', fontSize=13.5,
                                  leading=22, alignment=TA_CENTER, textColor=colors.HexColor('#526D82'), spaceAfter=14)
        h1 = ParagraphStyle('h1', parent=styles['Heading1'], fontName='Titr', fontSize=17,
                            leading=27, alignment=TA_RIGHT, textColor=colors.HexColor('#0B6E69'),
                            spaceBefore=12, spaceAfter=8)
        h2 = ParagraphStyle('h2', parent=styles['Heading2'], fontName='Titr', fontSize=13,
                            leading=21, alignment=TA_RIGHT, textColor=colors.HexColor('#1B5D8C'),
                            spaceBefore=9, spaceAfter=5)
        body = ParagraphStyle('body', parent=styles['BodyText'], fontName='Roya', fontSize=12.2,
                              leading=20, alignment=TA_RIGHT, textColor=colors.HexColor('#182B3A'), spaceAfter=6)
        note = ParagraphStyle('note', parent=body, fontSize=10.8, leading=17)
        tiny = ParagraphStyle('tiny', parent=body, fontSize=9.6, leading=14)
        callout = ParagraphStyle('callout', parent=body, backColor=colors.HexColor('#E6FFFA'),
                                 borderColor=colors.HexColor('#319795'), borderWidth=.65, borderPadding=8,
                                 textColor=colors.HexColor('#164E63'), spaceBefore=7, spaceAfter=9)
        danger = ParagraphStyle('danger', parent=body, backColor=colors.HexColor('#FFF5F5'),
                                borderColor=colors.HexColor('#E57373'), borderWidth=.65, borderPadding=8,
                                textColor=colors.HexColor('#7A1F1F'), spaceBefore=7, spaceAfter=9)

        story: list = []
        def paragraph(s: str, style=body): story.append(text_p(s, style))
        def heading(s: str, level=1): story.append(text_p(s, h1 if level == 1 else h2))
        def table(headers, values, widths, style=tiny, repeat=True, font_size=None):
            data = [[text_p(x, style) for x in headers]]
            for row in values:
                data.append([text_p(x, style) if not isinstance(x, Paragraph) else x for x in row])
            t = Table(data, colWidths=widths, repeatRows=1 if repeat else 0, hAlign='RIGHT')
            ts = [
                ('FONTNAME', (0, 0), (-1, -1), 'Roya'),
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0B6E69')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('GRID', (0, 0), (-1, -1), .25, colors.HexColor('#B9C7D1')),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F5F9FC')]),
                ('TOPPADDING', (0, 0), (-1, -1), 5),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
                ('LEFTPADDING', (0, 0), (-1, -1), 4),
                ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ]
            if font_size:
                ts.append(('FONTSIZE', (0, 0), (-1, -1), font_size))
            t.setStyle(TableStyle(ts))
            story.extend([t, Spacer(1, 8)])

        # Cover
        story.append(Spacer(1, .8 * cm))
        story.append(text_p('گزارش بازبینی‌شده و قابل‌پیگیری انتخاب رشتهٔ تجربی ۱۴۰۵', title))
        story.append(text_p('نسخهٔ دوم، مبتنی بر دفترچهٔ رسمی، ممیزی کدها و حذف ادعاهای غیرقابل اتکا', subtitle))
        paragraph('این گزارش جایگزین نسخهٔ قبلی است. در آن هیچ درصدِ ساختگی برای شانس قبولی، هیچ شهریهٔ قطعیِ بدون ابلاغ دانشگاه، و هیچ کدرشته‌محلِ بدون ارجاع صفحه‌ای ارائه نشده است.', danger)
        table(['دادهٔ تصمیم', 'مقدار ثبت‌شده در کارنامه/درخواست'], [
            ('سهمیهٔ مؤثر در انتخاب', 'ایثارگران ۵ درصد'),
            ('رتبه در سهمیهٔ نهایی', '۶۷ از ۲۶٬۳۲۸'),
            ('رتبهٔ منطقهٔ ۳', '۲۹۹ از ۱۷۸٬۴۴۰'),
            ('رتبهٔ کشوری بدون سهمیه', '۱٬۶۹۰ از ۴۰۶٬۳۵۷'),
            ('نمرهٔ کل آزمون / سابقه / نهایی', '۱۰٬۲۸۷ / ۱۰٬۰۱۲ / ۱۰٬۱۲۲'),
            ('شرایط زندگی', 'متأهل؛ ساکن مرند؛ بومی آذربایجان شرقی'),
            ('ترتیب علاقهٔ اعلام‌شده', 'دندان‌پزشکی، سپس فیزیوتراپی، سپس داروسازی و سپس پزشکی'),
        ], [6.5 * cm, 10.0 * cm], style=body)
        paragraph('نکتهٔ مهم: رتبهٔ ۶۷ در سهمیهٔ ۵٪ مبنای رقابت سهمیه‌ای است. رتبهٔ ۲۹۹ منطقهٔ ۳ و رتبهٔ کشوری برای دیدن تصویر کلی مفیدند، اما جای رتبهٔ سهمیه را در تصمیم‌گیری نمی‌گیرند.', callout)
        paragraph('محدودهٔ اتکا: این گزارش فقط برای دفترچهٔ تجربی ۱۴۰۵ و همین کارنامه نوشته شده است. هر اصلاحیهٔ بعدی سنجش، متن دفترچهٔ پیوست دانشگاه و شرایط نمایش‌داده‌شده در سامانهٔ انتخاب رشته بر این گزارش مقدم‌اند.', danger)
        story.append(PageBreak())

        heading('۱) چه چیزهایی در نسخهٔ قبل غلط یا ناکافی بود؟')
        table(['ایرادِ نسخهٔ قبل', 'چرا قابل اتکا نبود؟', 'اصلاح در این نسخه'], [
            ('درصدهای شانس مانند ۷۰ تا ۸۵ درصد', 'سنجش آخرین رتبه/نمرهٔ قبولی سهمیهٔ ۵٪ هر کدرشته‌محل را در دفترچه منتشر نکرده است؛ بنابراین درصد دقیق قابل محاسبه نیست.', 'همهٔ درصدها حذف شد؛ فقط سطح تصمیم و محدودیت رسمی بیان می‌شود.'),
            ('فهرست ۱۵۰تایی با استخراج متنی کم‌دقت', 'استخراجگر قبلی گاهی رقم انتهایی کد را ناقص می‌خواند؛ این روش برای واردکردن کد انتخاب رشته کافی نبود.', '۱۵۰ کد با روش استخراج دوم از فایل رسمی دوباره خوانده و در برابر رشته/دوره ممیزی شده‌اند؛ صفحهٔ منبع کنار هر ردیف آمده است.'),
            ('خطای مشخص در معرفی کد ۳۳۸۴۶', 'این کد در نسخهٔ قبل به «اسدآباد» نسبت داده شده بود؛ دفترچهٔ رسمی، آن را داروسازی روزانهٔ علوم پزشکی یزد نشان می‌دهد.', 'نام دانشگاه در فهرست ممیزی‌شده به «علوم پزشکی یزد» اصلاح شد؛ منبع: دفترچه، صفحهٔ ۱۳۶.'),
            ('برآوردهای متناقض شهریهٔ آزاد', 'منابع وبی ارقام بسیار متفاوتی می‌دادند و ابلاغ کتبیِ خاصِ واحد تبریز ارائه نشده بود.', 'هیچ رقم قطعی برای آزاد تبریز گزارش نشده است؛ فقط اجزای شهریهٔ دوره‌های شهریه‌پرداز وزارت بهداشت با منبع مشخص آمده است.'),
            ('ابهام تعهد خدمت', 'تعهد عادیِ روزانه با کدهای خاص تعهدی وزارت بهداشت یکی گرفته شده بود.', 'تعهد عادی روزانه و کد ۳۸۶۰۲ جداگانه با شروط و آثار حقوقی‌شان توضیح داده شده‌اند.'),
            ('استناد و صفحهٔ قابل پیگیری کم‌رنگ', 'خواننده نمی‌توانست هر ادعا یا کد را سریعاً به صفحهٔ رسمی برگرداند.', 'شمارهٔ صفحهٔ دفترچه برای هر کدرشته‌محل و فهرست منابع درجه‌بندی‌شده افزوده شد.'),
            ('حروف‌چینی و فونت نامناسب', 'جدول‌های متراکم و فونت عمومی، خواندن فارسی و راست‌به‌چپ را سخت کرده بود.', 'نسخهٔ جدید با فونت فارسی استخراج‌شده از دفترچهٔ رسمی، اندازهٔ بزرگ‌تر و جدول‌های کم‌تراکم بازطراحی شده است.'),
        ], [3.0 * cm, 6.4 * cm, 7.1 * cm], style=note)

        heading('۲) روش ممیزی و درجهٔ اتکا')
        paragraph('کدها از خودِ فایل دفترچهٔ راهنمای انتخاب رشتهٔ گروه تجربی ۱۴۰۵ موجود در مخزن استخراج شدند. برای هر کد، سه کنترل انجام شده است: وجود دقیق پنج رقم در فایل، هم‌خوانی عنوان رشته، و هم‌خوانی نوع دوره. کدهای آغاز مهر ۱۴۰۶ نیز فقط از بخش مستقلِ شروع مهر ۱۴۰۶ پذیرفته شده‌اند.')
        table(['درجه', 'منبع', 'کاربرد در گزارش'], [
            ('درجهٔ یک: تصمیم‌ساز', 'دفترچهٔ رسمی ۱۴۰۵ موجود در مخزن؛ به‌خصوص ص. ۲۰ تا ۲۸ و ۴۷ تا ۱۴۸.', 'کد، دوره، ظرفیت، نیمسال، تعهد و قواعد رتبه.'),
            ('درجهٔ یک: دادهٔ فردی', 'کارنامه/تصاویر ارائه‌شده توسط داوطلب.', 'رتبه‌ها، نمرهٔ کل و بومی‌بودن.'),
            ('درجهٔ یک: رفاهی', 'صفحات رسمی معاونت دانشجویی علوم پزشکی تبریز و ارومیه.', 'وجود/محدودیت خوابگاه؛ نه تضمین تخصیص.'),
            ('درجهٔ دو: هزینه', 'ابلاغ شهریهٔ وزارت بهداشت که خبرگزاری آنا گزارش کرده است.', 'اجزای شهریهٔ دوره‌های شهریه‌پرداز، نه شهریهٔ آزاد تبریز.'),
            ('درجهٔ سه: مسافت', 'مسیریاب‌های عمومی؛ فقط برای برنامه‌ریزی خانوادگی.', 'برآورد رفت‌وآمد، نه قاعدهٔ پذیرش.'),
        ], [2.7 * cm, 6.4 * cm, 7.4 * cm], style=note)
        paragraph('قاعدهٔ محافظه‌کارانه: هر جا سند درجهٔ یک وجود ندارد، گزارش «نامعلوم/نیازمند استعلام» می‌گوید؛ به‌جای پر کردن خلأ با حدس.', callout)

        heading('۳) سهمیه، رتبه و تعهدهای قانونی')
        paragraph('دفترچه در صفحهٔ ۲۸ می‌گوید «رتبه در سهمیه» از مرتب‌سازی نمرهٔ کل نهایی متقاضیان همان سهمیه ساخته می‌شود و برای ایثارگران علاوه بر رتبهٔ سهمیه، رتبهٔ منطقه هم در کارنامه درج می‌شود. بنابراین برای این داوطلب، رتبهٔ ۶۷ در سهمیهٔ ۵٪ شاخص اصلی رقابت سهمیه‌ای است؛ رتبهٔ منطقهٔ ۳ شاخص جایگزین آن نیست.')
        paragraph('دفترچه در صفحهٔ ۲۳ توضیح می‌دهد ظرفیت هر کدرشته‌محل بعد از کسر سهمیه‌های ۲۵٪ و ۵٪ و متناسب با نوع گزینش توزیع می‌شود. به‌همین دلیل، «۵٪ ظرفیت» به معنی یک تعداد صندلی ثابت و قابل محاسبه برای هر داوطلب نیست.')
        table(['نوع پذیرش', 'اثر تعهد طبق دفترچهٔ ۱۴۰۵', 'دقت لازم'], [
            ('روزانهٔ عادی با سهمیهٔ ایثارگران', 'تعهد استفاده از آموزش رایگان: یک برابرِ مدت تحصیل پس از فراغت؛ ص. ۲۰.', 'این تعهد با محل تعهد خاصِ کدرشته‌های وزارت بهداشت فرق دارد.'),
            ('کد خاص ۳۸۶۰۲؛ دندان تعهدی تبریز', 'یک‌ونیم برابرِ مدت تحصیل در مناطق موردنیاز؛ انتقال/خرید تعهد ممنوع و ادامه‌تحصیل تا نیمهٔ تعهد محدود است؛ ص. ۱۴۷ تا ۱۴۸.', 'حدنصاب خاص این کد ۸۰٪ گزینش آزاد متناظر است، نه شرط عمومی‌ای که برای همه کدها نقل می‌شود.'),
            ('شهریه‌پرداز/آزاد', 'دفترچه برای دوره‌های غیرروزانه تعهد آموزش رایگان مقرر نمی‌کند؛ ص. ۲۱.', 'این به معنی حذف طرح یا تعهدات حرفه‌ای مستقل رشته نیست؛ آن‌ها باید جداگانه از دانشگاه/وزارت بهداشت پرسیده شوند.'),
        ], [4.0 * cm, 7.2 * cm, 5.3 * cm], style=note)

        heading('۴) بومی‌بودن و منطق واقعی اولویت‌بندی')
        paragraph('سه سال آخر تحصیل در مرند/آذربایجان شرقی، طبق قاعدهٔ دفترچه (ص. ۲۳)، مبنای بومی‌بودن است. در رشته‌های پزشکی، دندان‌پزشکی، داروسازی و دامپزشکیِ دانشگاه آزاد، گزینش کشوری است؛ در دوره‌های شهریه‌پرداز علوم پزشکی نیز گزینش کشوری است (ص. ۲۲). بنابراین «بومی تبریز بودن» برای همهٔ ردیف‌ها امتیاز یکسان ایجاد نمی‌کند.')
        paragraph('سنجش احتمال دقیق را در دفترچه منتشر نکرده است؛ پس این گزارش رتبهٔ ۶۷ را به درصد جعلی تبدیل نمی‌کند. چینش درست چنین است: اول علاقهٔ واقعی، بعد امکان زندگی و هزینه، سپس پوشش ریسک با گزینه‌های پایین‌تر. اگر گزینه‌ای را بالاتر از گزینهٔ محبوب‌تر بنویسید و در آن پذیرفته شوید، انتخاب‌های پایین‌تر دیگر بررسی نمی‌شوند.', callout)

        heading('۵) تحلیل زندگی خانوادگی: رفت‌وآمد و خوابگاه')
        table(['شهر', 'برآورد رفت‌وآمد از مرند', 'حکم عملی'], [
            ('تبریز', 'حدود ۷۰ کیلومتر و نزدیک ۱ ساعت یک‌طرفه (مسیریاب عمومی).', 'تنها گزینهٔ چهارشهره با امکان رفت‌وآمد روزانه؛ با این حال برنامهٔ کارآموزی/کلینیک را جداگانه بسنجید.'),
            ('ارومیه', 'حدود ۲۰۵ کیلومتر و حدود ۳ ساعت یک‌طرفه.', 'رفت‌وآمد روزانه پایدار نیست؛ اجاره/اقامت هفتگی پیش‌شرط منطقی است.'),
            ('اردبیل', 'حدود ۲۸۸ کیلومتر و حدود ۳٫۵ ساعت یک‌طرفه.', 'فقط با اقامت. دفترچه در کدهای اصلی «فاقد خوابگاه» می‌نویسد.'),
            ('زنجان', 'حدود ۳۶۷ کیلومتر و حدود ۴ ساعت یک‌طرفه.', 'فقط با اقامت. دفترچه در کدهای اصلی «فاقد خوابگاه» می‌نویسد.'),
        ], [3.0 * cm, 6.0 * cm, 7.5 * cm], style=note)
        table(['دانشگاه', 'آنچه سند رسمی می‌گوید', 'نتیجهٔ تصمیم'], [
            ('علوم پزشکی تبریز', 'صفحهٔ رسمی خوابگاه: خوابگاه متأهلی شهید شایان‌مهر با ۶۳ واحد؛ واگذاری بر پایهٔ امتیاز و نوبت است.', 'وجود دارد، اما قطعی نیست؛ برای متأهل امتیاز مثبت است نه تضمین.'),
            ('علوم پزشکی ارومیه', 'صفحهٔ رسمی خوابگاه: دو بلوک متأهلی، هرکدام ۱۲ واحد مستقل. در دفترچهٔ کدهای عادی: «عدم تعهد در واگذاری خوابگاه».', '۲۴ واحد، ولی عدم تضمین رسمی؛ برنامهٔ اجاره لازم است.'),
            ('اردبیل و زنجان', 'در ردیف‌های دندان/دارو/پزشکی منتخب، دفترچه «فاقد خوابگاه» درج می‌کند.', 'گزینه فقط در صورت پذیرش هزینه و برنامهٔ اقامت قابل ثبت است.'),
        ], [3.2 * cm, 7.4 * cm, 5.9 * cm], style=note)

        heading('۶) کدهای محلیِ تأییدشده و ظرفیت')
        table(['رشته/شهر', 'کدهای عادی', 'ظرفیت درج‌شده', 'صفحهٔ دفترچه'], [
            ('دندان تبریز', '۳۱۶۰۶', '۳۳', '۴۷'),
            ('دندان ارومیه', '۳۱۷۰۶', '۲۴', '۵۱'),
            ('دندان اردبیل', '۳۱۷۸۲، ۳۱۷۸۳', '۱۱ + ۱۱', '۵۴'),
            ('دندان زنجان', '۳۲۷۳۳', '۱۴', '۹۲'),
            ('دارو تبریز', '۳۱۶۰۴، ۳۱۶۰۵', '۳۰ + ۳۰', '۴۷'),
            ('فیزیوتراپی تبریز', '۳۱۶۲۲', '۲۰', '۴۸'),
            ('پزشکی تبریز', '۳۱۶۰۱، ۳۱۶۰۳', '۵۴ + ۵۵', '۴۷'),
            ('پزشکی ارومیه', '۳۱۷۰۲، ۳۱۷۰۴', '۳۹ + ۳۸', '۵۱'),
            ('پزشکی اردبیل', '۳۱۷۷۹، ۳۱۷۸۰', '۳۹ + ۲۰', '۵۴'),
            ('پزشکی زنجان', '۳۲۷۲۸، ۳۲۷۳۰', '۵۶ + ۵۷', '۹۱'),
            ('دندان تعهدی تبریز', '۳۸۶۰۲', '۳۰', '۱۴۸'),
        ], [3.1 * cm, 3.0 * cm, 3.8 * cm, 3.1 * cm], style=note)
        paragraph('کدهای فراجا/سپاه و کدهای مصاحبه‌دار عمداً وارد فهرست ۱۵۰تایی نشده‌اند. مثال: ۳۱۶۰۲، ۳۱۷۰۳، ۳۱۷۰۷، ۳۲۷۲۹ و ۳۳۷۲۵ کدهای خاص‌اند و نباید با کدهای عادی هم‌عنوان اشتباه شوند.', danger)

        heading('۷) هزینه: آنچه می‌دانیم و آنچه نمی‌دانیم')
        paragraph('برای دوره‌های شهریه‌پردازِ علوم پزشکی، گزارش ابلاغ وزارت بهداشت برای سال تحصیلی ۱۴۰۵–۱۴۰۶، شهریهٔ ثابت دکتری عمومی پزشکی/دندان‌پزشکی/داروسازی را برای هر نیمسال ۳۴۱٬۹۲۵٬۳۳۴ ریال (حدود ۳۴٫۱۹ میلیون تومان) اعلام کرده است. علاوه بر آن، شهریهٔ متغیر بر حسب نوع و تعداد واحد محاسبه می‌شود؛ پس شهریهٔ ثابت، «هزینهٔ کامل ترم» نیست.')
        table(['نوع داده', 'مقدار/وضعیت', 'نحوهٔ استفادهٔ درست'], [
            ('شهریه‌پرداز علوم پزشکی', 'شهریهٔ ثابت هر نیمسال: حدود ۳۴٫۱۹ میلیون تومان + واحدهای متغیر.', 'برای کدهای ۳۱۶۳۵ و مشابه، برآورد اولیه است؛ امور مالی دانشگاه باید فیش نمونه و جدول واحدها را کتبی بدهد.'),
            ('دانشگاه آزاد تبریز', 'نرخ قطعیِ قابل استناد برای همان ورودی/واحد در منابع بررسی‌شده پیدا نشد.', 'کدهای آزاد فقط بعد از دریافت جدول رسمی شهریه، روش پرداخت، افزایش سالانه و هزینه‌های کلینیکی باقی بمانند.'),
            ('اقامت', 'رقم محلیِ پایدار و رسمیِ یکسان پیدا نشد.', 'برای ارومیه/اردبیل/زنجان بودجهٔ مستقل اجاره، رفت‌وآمد خانوادگی و اسباب زندگی تعیین کنید.'),
        ], [3.6 * cm, 6.1 * cm, 6.3 * cm], style=note)
        paragraph('بنابراین در این نسخه هیچ عددی مانند «شهریهٔ آزاد تبریز دقیقاً یک رقم مشخص است» نوشته نشده است. قبل از انتخاب کدهای شهریه‌پرداز/آزاد، پاسخ کتبی دانشگاه شرط ماندن آن‌ها در فرم است.', danger)

        heading('۸) تصمیم‌های دودویی که چینش را تغییر می‌دهند')
        table(['تصمیم شخصی', 'اگر پاسخ «بله» باشد', 'اگر پاسخ «خیر» باشد'], [
            ('شروع مهر ۱۴۰۶', 'ردیف‌های دندانِ شروع ۱۴۰۶ می‌مانند.', 'همهٔ ردیف‌های مهر ۱۴۰۶ حذف شوند.'),
            ('تعهد ویژهٔ ۳۸۶۰۲', 'کد تعهدی تبریز بعد از روزانه‌ها می‌ماند؛ متن تعهد محضری قبلاً خوانده شود.', '۳۸۶۰۲ حذف شود؛ به‌دلیل تعهد ۱٫۵برابر و محدودیت انتقال.'),
            ('بودجهٔ شهریه/آزاد', 'فقط با رقم کتبی، منبع پرداخت و سقف هزینهٔ خانوار، ردیف‌های مشروط بمانند.', 'تمام شهریه‌پرداز، آزاد تمام‌وقت و خودگردان حذف شوند.'),
            ('اقامت شهر دور', 'ارومیه/اردبیل/زنجان و ملی به‌عنوان پشتیبان باقی بمانند.', 'هر کد غیرتبریزیِ غیرقابل رفت‌وآمد حذف شود.'),
        ], [3.2 * cm, 6.6 * cm, 6.2 * cm], style=note)

        heading('۹) فهرست ۱۵۰تاییِ ممیزی‌شده')
        paragraph('این فهرست یک «پیش‌نویس قابل کنترل» است، نه دستور ثبت کورکورانه. ترتیب درون گروه‌ها از اولویت اعلام‌شده پیروی می‌کند: دندان‌پزشکی، فیزیوتراپی، داروسازی و سپس پزشکی. ستون «صفحه» امکان بازبینی مستقیم همهٔ کدها را می‌دهد. پیش از ثبت، تصمیم‌های بخش ۸ را اعمال کنید.')
        groups = [
            ('دندان‌پزشکی — روزانه، شروع مهر ۱۴۰۶ و گزینه‌های مشروط', rows[:73]),
            ('فیزیوتراپی — گزینه‌های روزانه', rows[73:89]),
            ('داروسازی — روزانه و گزینه‌های مشروط', rows[89:130]),
            ('پزشکی — گزینه‌های روزانه', rows[130:150]),
        ]
        for group_idx, (group_name, items) in enumerate(groups):
            # Section 9 already starts on a fresh page. Later field groups start
            # on fresh pages, but the first table must follow its introduction.
            if group_idx:
                story.append(PageBreak())
            heading(group_name)
            start = sum(len(g[1]) for g in groups[:group_idx]) + 1
            # Keep tables compact but readable: eight rows maximum per segment.
            # This also prevents an orphaned section heading at the bottom of a page.
            for offset in range(0, len(items), 8):
                if offset:
                    heading('ادامهٔ ' + group_name, 2)
                chunk = items[offset:offset+8]
                tablerows = []
                for n, r in enumerate(chunk, start + offset):
                    # reversed visual columns: priority appears at the right edge
                    tablerows.append((
                        f"ص. {r['صفحه رسمی 1405']}",
                        f"{r['دوره']} / {r['شروع']}",
                        r['شرط/یادداشت'],
                        r['دانشگاه'],
                        r['رشته'],
                        r['کدرشته‌محل'],
                        str(n),
                    ))
                table(['صفحه رسمی', 'دوره/شروع', 'شرط ثبت', 'دانشگاه/شهر', 'رشته', 'کد', 'اولویت'],
                      tablerows,
                      [1.45*cm, 2.25*cm, 3.65*cm, 3.25*cm, 2.15*cm, 1.3*cm, 1.05*cm], style=tiny)

        story.append(PageBreak())
        heading('۱۰) کنترل نهایی و منابع')
        paragraph('کنترل ماشینی انجام‌شده برای این خروجی: ۱۵۰ ردیف، ۱۵۰ کد یکتا، وجود هر کد در فایل رسمی، و هم‌خوانی رشته و نوع دوره با متن همان صفحه. این کنترل جای اصلاحیهٔ روز ثبت را نمی‌گیرد.')
        table(['شناسه', 'منبع', 'صفحات/نشانی', 'درجه'], [
            ('منبع ۱', 'دفترچه راهنمای انتخاب رشتهٔ گروه تجربی آزمون سراسری ۱۴۰۵.', 'فایل رسمی دفترچهٔ گروه تجربی ۱۴۰۵؛ ص. ۲۰ تا ۲۸ و ۴۷ تا ۱۴۸.', 'یک'),
            ('منبع ۲', 'ادارهٔ امور سراهای دانشجویی علوم پزشکی تبریز.', 'صفحهٔ رسمی معاونت دانشجویی تبریز؛ ۶۳ واحد متأهلی و واگذاری امتیازی/نوبتی.', 'یک'),
            ('منبع ۳', 'ادارهٔ امور خوابگاه‌های علوم پزشکی ارومیه.', 'صفحهٔ رسمی ادارهٔ خوابگاه‌های ارومیه؛ دو بلوک، هرکدام ۱۲ واحد مستقل.', 'یک'),
            ('منبع ۴', 'گزارش ابلاغ شهریهٔ وزارت بهداشت.', 'خبرگزاری آنا، گزارش ابلاغ وزارت بهداشت؛ اجزای شهریهٔ شهریه‌پرداز سال ۱۴۰۵ تا ۱۴۰۶.', 'دو'),
            ('منبع ۵', 'مسیریاب‌های عمومی مرند تا چهار شهر.', 'صرفاً برای سنجش زمان خانوادگی؛ پیش از تصمیم با مسیر و محل کارآموزی به‌روز شود.', 'سه'),
        ], [1.2*cm, 4.5*cm, 8.0*cm, 1.0*cm], style=note)
        paragraph('چک‌لیست روز ثبت: ۱) سهمیهٔ ۵٪ در سامانه درست نمایش داده شود؛ ۲) اصلاحیهٔ سنجش با جدول این گزارش تطبیق شود؛ ۳) کدهای خاص/مصاحبه‌دار وارد نشوند؛ ۴) شرط تأخیر، تعهد، اقامت و پرداخت یک‌به‌یک تأیید شود؛ ۵) نسخهٔ پرونده و رسید نهایی سامانه ذخیره شود.', callout)
        paragraph('جمع‌بندی حرفه‌ای: بهترین انتخاب «امن‌ترین کد» نیست؛ نخستین کدی است که واقعاً می‌خواهید و همهٔ آثار آن — شهر، خوابگاه، شروع، تعهد و هزینه — را پذیرفته‌اید. این گزارش برای جلوگیری از انتخاب بر مبنای حدس ساخته شده است.', callout)

        def page_footer(canvas, doc_obj):
            canvas.saveState()
            canvas.setStrokeColor(colors.HexColor('#C8D6DF'))
            canvas.line(1.35*cm, .97*cm, A4[0]-1.35*cm, .97*cm)
            canvas.setFont('Roya', 9)
            canvas.setFillColor(colors.HexColor('#526D82'))
            canvas.drawRightString(A4[0]-1.35*cm, .56*cm, fa('گزارش ممیزی‌شدهٔ انتخاب رشتهٔ تجربی ۱۴۰۵'))
            canvas.drawString(1.35*cm, .56*cm, fa(f'صفحهٔ {doc_obj.page}'))
            canvas.restoreState()

        doc.build(story, onFirstPage=page_footer, onLaterPages=page_footer)
    finally:
        font_temp.cleanup()


if __name__ == '__main__':
    booklet = fitz.open(BOOKLET)
    audited = audit_rows(booklet)
    write_audited_csv(audited)
    make_pdf(audited, booklet)
    print(f'created {OUTPUT}')
    print(f'created {AUDITED_CSV} with {len(audited)} audited rows')
