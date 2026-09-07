"""Сборка презентации к промежуточной защите.

Шрифт Inter Tight, градиентные подложки картинками, разные раскладки на каждом слайде.
"""

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

HERE = Path(__file__).resolve().parent
ASSETS = HERE / "assets"
OUT = HERE / "presentation.pptx"

W, H = Inches(13.333), Inches(7.5)
M = Inches(0.72)  # поле

FONT = "Inter Tight"

# --- палитра: тёмно-синие чернила с латунным акцентом ------------------------
INK = RGBColor(0x0E, 0x14, 0x28)
DEEP = RGBColor(0x1B, 0x2A, 0x5B)
MID = RGBColor(0x2F, 0x4B, 0x9A)
PAPER = RGBColor(0xFF, 0xFF, 0xFF)
MUTED_D = RGBColor(0x9D, 0xAA, 0xC8)  # приглушённый на тёмном
MUTED_L = RGBColor(0x5B, 0x66, 0x7A)  # приглушённый на светлом
HAIR = RGBColor(0xD8, 0xDE, 0xE8)
BRASS = RGBColor(0xC9, 0xA2, 0x27)
OK = RGBColor(0x2E, 0x7D, 0x5B)
WARN = RGBColor(0xC0, 0x79, 0x1F)
CRIT = RGBColor(0xC0, 0x39, 0x2B)

prs = Presentation()
prs.slide_width, prs.slide_height = W, H
BLANK = prs.slide_layouts[6]


# ---------------------------------------------------------------- примитивы
def slide(bg="light"):
    s = prs.slides.add_slide(BLANK)
    img = {"light": "bg_light.jpg", "dark": "bg_dark.jpg"}[bg]
    s.shapes.add_picture(str(ASSETS / img), 0, 0, W, H)
    return s


def text(s, x, y, w, h, runs, size=16, color=None, bold=False, align=PP_ALIGN.LEFT,
         line=1.28, space_after=0, anchor=MSO_ANCHOR.TOP, caps=False, spacing=None):
    """runs: строка или список (текст, {переопределения})."""
    box = s.shapes.add_textbox(x, y, w, h)
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = anchor

    items = runs if isinstance(runs, list) else [(runs, {})]
    p = tf.paragraphs[0]
    p.alignment = align
    p.line_spacing = line
    p.space_after = Pt(space_after)
    for i, (chunk, over) in enumerate(items):
        r = p.add_run()
        r.text = chunk
        f = r.font
        f.name = FONT
        f.size = Pt(over.get("size", size))
        f.bold = over.get("bold", bold)
        f.color.rgb = over.get("color", color or INK)
        if over.get("caps", caps):
            f._rPr.set("cap", "all")
        sp = over.get("spacing", spacing)
        if sp:
            f._rPr.set("spc", str(int(sp * 100)))
        if i < len(items) - 1 and over.get("br"):
            p = tf.add_paragraph()
            p.alignment = align
            p.line_spacing = line
            p.space_after = Pt(space_after)
    return box


def para_list(s, x, y, w, h, items, size=14.5, color=None, gap=9, line=1.3, bullet_color=None):
    """Список без буллет-символов: тире-маркер рисуем префиксом руна."""
    box = s.shapes.add_textbox(x, y, w, h)
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.line_spacing = line
        p.space_after = Pt(gap)
        mark = p.add_run()
        mark.text = "—  "
        mark.font.name = FONT
        mark.font.size = Pt(size)
        mark.font.color.rgb = bullet_color or BRASS
        parts = item if isinstance(item, list) else [(item, {})]
        for chunk, over in parts:
            r = p.add_run()
            r.text = chunk
            r.font.name = FONT
            r.font.size = Pt(over.get("size", size))
            r.font.bold = over.get("bold", False)
            r.font.color.rgb = over.get("color", color or INK)
    return box


def eyebrow(s, x, y, label, note=None, on_dark=False):
    runs = [(label, {"color": BRASS if on_dark else MID})]
    if note:
        runs.append(("     " + note, {"color": MUTED_D if on_dark else MUTED_L}))
    return text(s, x, y, W - x - M, Inches(0.26), runs, size=10.5, bold=True, caps=True, spacing=1.4)


def title(s, x, y, w, txt, size=34, on_dark=False):
    return text(s, x, y, w, Inches(1.3), txt, size=size, bold=True,
                color=PAPER if on_dark else INK, line=1.08)


def rule(s, x, y, w, color=None):
    ln = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, y, w, Emu(9525))
    ln.fill.solid()
    ln.fill.fore_color.rgb = color or HAIR
    ln.line.fill.background()
    ln.shadow.inherit = False
    return ln


def card(s, x, y, w, h, fill=None, line_color=None):
    sh = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h)
    sh.adjustments[0] = 0.045
    sh.fill.solid()
    sh.fill.fore_color.rgb = fill or PAPER
    if line_color:
        sh.line.color.rgb = line_color
        sh.line.width = Pt(0.75)
    else:
        sh.line.fill.background()
    sh.shadow.inherit = False
    sh.text_frame.text = ""
    return sh


def circle(s, cx, cy, d, fill, label=None, label_color=None, size=13):
    sh = s.shapes.add_shape(MSO_SHAPE.OVAL, cx, cy, d, d)
    sh.fill.solid()
    sh.fill.fore_color.rgb = fill
    sh.line.fill.background()
    sh.shadow.inherit = False
    tf = sh.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = label or ""
    r.font.name = FONT
    r.font.size = Pt(size)
    r.font.bold = True
    r.font.color.rgb = label_color or PAPER
    return sh


def chip(s, x, y, txt, color, w=None):
    tw = w or Inches(0.09 * len(txt) + 0.30)
    sh = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, tw, Inches(0.27))
    sh.adjustments[0] = 0.5
    sh.fill.solid()
    sh.fill.fore_color.rgb = color
    sh.line.fill.background()
    sh.shadow.inherit = False
    tf = sh.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = txt
    r.font.name = FONT
    r.font.size = Pt(9.5)
    r.font.bold = True
    r.font.color.rgb = PAPER
    return sh


TOTAL_SLIDES = 17  # держать равным числу слайдов; проверяется при сборке


def foot(s, left, num, on_dark=False):
    text(s, M, H - Inches(0.58), Inches(9.4), Inches(0.28), left,
         size=9.5, color=MUTED_D if on_dark else MUTED_L)
    text(s, W - M - Inches(1.6), H - Inches(0.58), Inches(1.6), Inches(0.28),
         f"{num} / {TOTAL_SLIDES}", size=9.5, color=MUTED_D if on_dark else MUTED_L,
         align=PP_ALIGN.RIGHT)


def table(s, x, y, w, cols, rows, col_w, head_color=None, body_color=None,
          size=11, head_size=9.5, row_h=Inches(0.5)):
    """Ручная таблица: полный контроль над типографикой."""
    cy = y
    cx = x
    for i, c in enumerate(cols):
        text(s, cx, cy, col_w[i], Inches(0.3), c, size=head_size, bold=True,
             caps=True, spacing=1.0, color=head_color or MUTED_L)
        cx += col_w[i]
    cy += Inches(0.34)
    rule(s, x, cy, w, HAIR if not head_color else RGBColor(0x2B, 0x37, 0x5E))
    cy += Inches(0.14)

    for row in rows:
        cx = x
        maxlines = 1
        for i, cell in enumerate(row):
            content = cell["t"] if isinstance(cell, dict) else cell
            approx = max(1, int(len(str(content)) / max(1, int(col_w[i].inches * 8.6)) + 0.85))
            maxlines = max(maxlines, approx)
        rh = max(row_h, Inches(0.24 * maxlines + 0.2))
        for i, cell in enumerate(row):
            if isinstance(cell, dict) and cell.get("chip"):
                chip(s, cx, cy + Inches(0.02), cell["t"], cell["chip"])
            else:
                content = cell["t"] if isinstance(cell, dict) else cell
                over = cell.get("f", {}) if isinstance(cell, dict) else {}
                text(s, cx, cy, col_w[i] - Inches(0.22), rh, content,
                     size=over.get("size", size), bold=over.get("bold", False),
                     color=over.get("color", body_color or INK), line=1.24)
            cx += col_w[i]
        cy += rh
        rule(s, x, cy - Inches(0.08), w, HAIR if not head_color else RGBColor(0x22, 0x2C, 0x4C))
    return cy


# =============================================================== 01 · Титул
s = slide("dark")
text(s, M, Inches(0.9), Inches(9), Inches(0.3),
     [("ITMO AI Product Hack", {"color": BRASS}),
      ("     Промежуточная защита · 04.09.2026", {"color": MUTED_D})],
     size=11, bold=True, caps=True, spacing=1.6)
text(s, M, Inches(1.9), Inches(9.6), Inches(2.2),
     "Интеллектуальный центр\nPR/GR-мониторинга",
     size=52, bold=True, color=PAPER, line=1.02)
text(s, M, Inches(4.35), Inches(8.4), Inches(1.0),
     "Отраслевые новости и нормативные акты, оценённые по влиянию на конкретную "
     "компанию — с раскрытой методикой и проверяемым обоснованием каждого балла.",
     size=15.5, color=MUTED_D, line=1.42)
rule(s, M, Inches(5.55), Inches(11.9), RGBColor(0x2B, 0x37, 0x5E))
for i, (h, b) in enumerate([
    ("Заказчик", "ООО «Цифра» (GS Labs)\nЯрослав Якимов"),
    ("Метод", "GitHub Spec Kit\nСпецификация ведёт код"),
    ("Состояние", "Backend реализован,\n89 тестов проходят"),
]):
    cx = M + Inches(4.05) * i
    text(s, cx, Inches(5.85), Inches(3.5), Inches(0.25), h, size=10, bold=True,
         caps=True, spacing=1.3, color=BRASS)
    text(s, cx, Inches(6.18), Inches(3.6), Inches(0.8), b, size=13, color=MUTED_D, line=1.35)
foot(s, "github.com/veceloe/ai-gpr-center-cifra", "01", on_dark=True)

# =============================================================== 02 · Проблема
s = slide("dark")
eyebrow(s, M, Inches(0.72), "Проблематика", on_dark=True)
title(s, M, Inches(1.15), Inches(10.4),
      "Три-четыре часа в день уходят на то,\nчтобы просто собрать информацию",
      size=32, on_dark=True)
stats = [("3–4 ч", "ежедневно на ручной мониторинг СМИ, регуляторов и Telegram", PAPER),
         ("46", "карточек в Excel-реестре, который ведётся руками", PAPER),
         ("≈630 ч", "в год на специалиста — потенциал высвобождения", BRASS)]
for i, (n, l, c) in enumerate(stats):
    cx = M + Inches(4.05) * i
    rule(s, cx, Inches(2.72), Inches(3.5), RGBColor(0x3A, 0x48, 0x74))
    text(s, cx, Inches(2.95), Inches(3.5), Inches(0.7), n, size=40, bold=True, color=c, line=1.0)
    text(s, cx, Inches(3.62), Inches(3.4), Inches(0.9), l, size=12, color=MUTED_D, line=1.3)
text(s, M, Inches(4.75), Inches(5.6), Inches(0.25), "Что уже пробовали", size=10,
     bold=True, caps=True, spacing=1.3, color=BRASS)
para_list(s, M, Inches(5.1), Inches(5.5), Inches(1.7), [
    [("ИИ-саммаризация", {"bold": True, "color": PAPER}),
     (" — собрать материал для модели всё равно приходилось руками", {"color": MUTED_D})],
    [("Excel-реестр", {"bold": True, "color": PAPER}),
     (" — «as is неудобно и ДОЛГО»", {"color": MUTED_D})],
    [("Медиамониторинг", {"bold": True, "color": PAPER}),
     (" — «не решает основную задачу»", {"color": MUTED_D})],
], size=13, color=MUTED_D)
text(s, Inches(7.3), Inches(4.75), Inches(5.3), Inches(0.25), "Риск немониторинга",
     size=10, bold=True, caps=True, spacing=1.3, color=BRASS)
text(s, Inches(7.3), Inches(5.1), Inches(5.3), Inches(1.7),
     [("Пропущенное регуляторное изменение — это штрафы, проверки и тяжбы.\n",
       {"color": MUTED_D}),
      ("ПП № 1937", {"bold": True, "color": PAPER, "br": True}),
      (" — требования к реестровому ПО с 01.09.2026. ", {"color": MUTED_D}),
      ("Законопроект № 1215252-8", {"bold": True, "color": PAPER}),
      (" — переход на реестровые CAS/DRM с 01.01.2027, прямое влияние на ключевой продукт.",
       {"color": MUTED_D})],
     size=13, line=1.38)
foot(s, "Источник: описание кейса, Q&A и созвон с заказчиком 02.09.2026", "02", on_dark=True)

# =============================================================== 03 · Пользователи
s = slide()
eyebrow(s, M, Inches(0.72), "Постановка задачи")
title(s, M, Inches(1.15), Inches(10.2),
      "Сократить путь от разрозненных источников\nдо релевантного рабочего материала", size=31)
users = [("PR", "PR-специалист", "Репутация и инфоповоды. Читает, решает: писать, реагировать, передать в работу или пропустить.", MID),
         ("GR", "GR-специалист", "НПА и инициативы регуляторов. Держит документ на контроле месяцами — до вступления в силу.", DEEP),
         ("РУК", "Руководитель", "Получатель. Ему нужен контекст для решения, а не таблица на сорок столбцов.", BRASS)]
for i, (ini, name, desc, col) in enumerate(users):
    cx = M + Inches(4.05) * i
    card(s, cx, Inches(2.6), Inches(3.75), Inches(2.05), PAPER, HAIR)
    circle(s, cx + Inches(0.28), Inches(2.85), Inches(0.5), col, ini, size=11)
    text(s, cx + Inches(0.9), Inches(2.96), Inches(2.7), Inches(0.3), name, size=15, bold=True)
    text(s, cx + Inches(0.28), Inches(3.55), Inches(3.2), Inches(0.95), desc,
         size=12.5, color=MUTED_L, line=1.35)
card(s, M, Inches(5.0), Inches(11.9), Inches(1.35), RGBColor(0xF0, 0xF3, 0xF9))
text(s, M + Inches(0.45), Inches(5.25), Inches(7.6), Inches(0.5),
     "«Задача — мониторинг и аналитика для принятия управленческих решений»",
     size=17, bold=True, color=DEEP, line=1.25)
text(s, M + Inches(0.45), Inches(5.92), Inches(7.6), Inches(0.3),
     "Ирина Распопина, GS Labs — о том, почему готовые системы медиамониторинга не подходят",
     size=11, color=MUTED_L)
text(s, Inches(9.3), Inches(5.25), Inches(3.3), Inches(1.0),
     [("Ценность — не «что произошло», а ", {"color": MUTED_L}),
      ("что это значит для нас", {"bold": True, "color": INK}),
      (". Материал без связи с профилем компании — шум.", {"color": MUTED_L})],
     size=12.5, line=1.35)
foot(s, "7 пользовательских историй · 50 требований FR-### · 13 критериев SC-###", "03")

# =============================================================== 04 · Рынок
s = slide()
eyebrow(s, M, Inches(0.72), "Рынок", "Поле не пустое — и это надо знать")
title(s, M, Inches(1.15), Inches(10.4),
      "Аналоги существуют. Ни один не раскрывает методику оценки", size=31)
cw = [Inches(3.15), Inches(1.85), Inches(3.05), Inches(1.55), Inches(2.3)]
table(s, M, Inches(2.5), Inches(11.9),
      ["Решение", "Первоисточники", "Оценка влияния", "Цикл НПА", "Цена"],
      [["Brand Analytics, Медиалогия, СКАН", "нет", "нет, тональность и охват", "нет", "от 33 тыс. ₽/мес"],
       ["КонсультантПлюс, ГАРАНТ", "да", "нет, фильтр по отрасли", "частично", "от 5 тыс. ₽"],
       ["ПравоИнициативы, Сорегулирование", "да", {"t": "заявлена, не раскрыта", "chip": WARN}, "да", "360 тыс. ₽/год"],
       [{"t": "Наше решение", "f": {"bold": True}}, "да", {"t": "раскрыта: К1–К6", "chip": OK}, "в плане", "внутренний инструмент"]],
      cw, size=11.5)
rule(s, M, Inches(5.5), Inches(11.9))
text(s, M, Inches(5.75), Inches(5.6), Inches(0.9),
     [("Медиамониторинг опаздывает структурно. ", {"bold": True}),
      ("Новость о законе — сигнал постфактум. Brand Analytics не заявляет сайты госорганов "
       "в источниках вообще.", {"color": MUTED_L})], size=12.5, line=1.35)
text(s, Inches(7.3), Inches(5.75), Inches(5.3), Inches(0.9),
     [("Свободная ниша. ", {"bold": True}),
      ("Сравнение редакций законопроекта между чтениями не закрыл никто: из восьми мировых "
       "трекеров настоящий diff есть у одного.", {"color": MUTED_L})], size=12.5, line=1.35)
foot(s, "Разобрано ~40 продуктов по 6 направлениям · docs/competitive-research.md", "04")

# =============================================================== 05 · Подход (сплит)
s = slide()
s.shapes.add_picture(str(ASSETS / "bg_panel.jpg"), 0, 0, Inches(5.55), H)
eyebrow(s, M, Inches(0.72), "Подход", on_dark=True)
title(s, M, Inches(1.2), Inches(4.4), "Модель выставляет баллы.\nИндекс считает код", size=30, on_dark=True)
text(s, M, Inches(3.1), Inches(4.2), Inches(1.6),
     "У заказчика есть работающая методика: шесть критериев с весами, формула и шкала "
     "категорий. Мы её не заменяем — мы делаем её исполнимой.",
     size=13.5, color=MUTED_D, line=1.42)
card(s, M, Inches(5.0), Inches(4.15), Inches(1.5), RGBColor(0x16, 0x22, 0x46))
text(s, M + Inches(0.3), Inches(5.25), Inches(3.6), Inches(0.35),
     "ИВ = Σ(балл × вес) / 3 × 100", size=15, bold=True, color=BRASS)
text(s, M + Inches(0.3), Inches(5.72), Inches(3.6), Inches(0.6),
     "Шкала категорий: 0 · 25 · 50 · 75 · 90", size=12, color=MUTED_D)

LX = Inches(6.35)
text(s, LX, Inches(1.2), Inches(2.6), Inches(0.25), "Что делает модель",
     size=10, bold=True, caps=True, spacing=1.3, color=MID)
para_list(s, LX, Inches(1.58), Inches(6.2), Inches(1.9), [
    [("Балл 0–3", {"bold": True}), (" по каждому критерию К1–К6", {"color": MUTED_L})],
    [("Обоснование", {"bold": True}), (" со ссылкой на факт из материала и пункт профиля компании", {"color": MUTED_L})],
    [("Кандидат во флаг эскалации", {"bold": True}), (" — только дословной формулировкой из закрытого списка", {"color": MUTED_L})],
], size=13, bullet_color=MID)
rule(s, LX, Inches(3.72), Inches(6.2))
text(s, LX, Inches(3.95), Inches(2.6), Inches(0.25), "Что делает код",
     size=10, bold=True, caps=True, spacing=1.3, color=BRASS)
para_list(s, LX, Inches(4.33), Inches(6.2), Inches(2.2), [
    [("Индекс по формуле", {"bold": True}), (" и категорию по шкале", {"color": MUTED_L})],
    [("Флаги эскалации", {"bold": True}), (" — поднимают категорию на ступень", {"color": MUTED_L})],
    [("Релевантность", {"bold": True}), (" выводится из К1 — отдельный вызов не нужен", {"color": MUTED_L})],
], size=13)
foot(s, "ADR-0003 · в контракте ответа модели полей «категория» и «индекс» нет вовсе", "05")

# =============================================================== 06 · Лента
# Слайды с экранами продукта намеренно почти без текста: снимок и есть аргумент.
s = slide()
eyebrow(s, M, Inches(0.62), "Продукт", "лента за 6 сентября, данные заказчика")
title(s, M, Inches(1.0), Inches(11.9), "Сверху то, что важнее для компании, а не то, что свежее", size=27)
card(s, Inches(1.68), Inches(1.78), Inches(9.96), Inches(4.98), PAPER, HAIR)
s.shapes.add_picture(str(ASSETS / "shot_feed.jpg"), Inches(1.72), Inches(1.82), Inches(9.88), Inches(4.9))
text(s, M, Inches(6.86), Inches(11.9), Inches(0.4),
     [("Слева — индекс влияния и категория. ", {"bold": True, "color": INK}),
      ("Цветом отмечены только два верхних уровня: пять цветов превращают экран "
       "в светофор, а сортировка уже сделала главную работу.", {"color": MUTED_L})],
     size=11.5, line=1.35)
foot(s, "185.56.162.154", "06")

# =============================================================== 07 · Разбор оценки
s = slide("dark")
eyebrow(s, M, Inches(0.62), "Продукт", "карточка раскрыта", on_dark=True)
title(s, M, Inches(1.0), Inches(11.9), "Оценку видно целиком — и её можно поправить",
      size=27, on_dark=True)
s.shapes.add_picture(str(ASSETS / "shot_breakdown.jpg"), Inches(1.72), Inches(1.82), Inches(9.88), Inches(4.9))
text(s, M, Inches(6.86), Inches(5.7), Inches(0.5),
     [("Слева — заземление. ", {"bold": True, "color": PAPER}),
      ("Под каждым утверждением цитата из оригинала и счётчик проверенного.",
       {"color": MUTED_D})], size=11.5, line=1.35)
text(s, Inches(7.3), Inches(6.86), Inches(5.3), Inches(0.5),
     [("Справа — шесть критериев. ", {"bold": True, "color": PAPER}),
      ("Балл, вклад в индекс и обоснование. Меняете балл — индекс пересчитывается сразу.",
       {"color": MUTED_D})], size=11.5, line=1.35)
foot(s, "FR-024 · разложение оценки по критериям", "07", on_dark=True)

# =============================================================== 08 · Критерии
s = slide()
eyebrow(s, M, Inches(0.72), "Методика заказчика", "менять только через ADR")
title(s, M, Inches(1.15), Inches(10.4), "Две шкалы: НПА и новости оцениваются по-разному", size=31)

text(s, M, Inches(2.25), Inches(5.8), Inches(0.25), "НПА · индекс влияния",
     size=10, bold=True, caps=True, spacing=1.3, color=MID)
cw = [Inches(0.5), Inches(3.6), Inches(0.8)]
table(s, M, Inches(2.6), Inches(4.9),
      ["", "Критерий", "Вес"],
      [["К1", "Применимость к деятельности компании", {"t": "0,25", "f": {"bold": True, "color": MID}}],
       ["К2", "Юридическая сила и стадия принятия", "0,15"],
       ["К3", "Финансовое воздействие", {"t": "0,20", "f": {"bold": True, "color": MID}}],
       ["К4", "Операционная сложность адаптации", "0,15"],
       ["К5", "Юридический и репутационный риск", "0,15"],
       ["К6", "Срочность — время до применения", "0,10"]],
      cw, size=11.5, row_h=Inches(0.38))

text(s, Inches(6.9), Inches(2.25), Inches(5.7), Inches(0.25), "Новости · индекс актуальности",
     size=10, bold=True, caps=True, spacing=1.3, color=MID)
table(s, Inches(6.9), Inches(2.6), Inches(4.9),
      ["", "Критерий", "Вес"],
      [["Н1", "Актуальность события", {"t": "0,30", "f": {"bold": True, "color": MID}}],
       ["Н2", "Релевантность продуктам и бизнесу", {"t": "0,30", "f": {"bold": True, "color": MID}}],
       ["Н3", "Масштаб для отрасли", "0,20"],
       ["Н4", "Динамика развития", "0,20"]],
      cw, size=11.5, row_h=Inches(0.38))

card(s, Inches(6.9), Inches(4.75), Inches(5.7), Inches(1.15), PAPER, HAIR)
text(s, Inches(7.2), Inches(4.98), Inches(5.1), Inches(0.32),
     "ИВ = ( Σ балл × вес ) ÷ 3 × 100", size=18, bold=True, color=INK)
text(s, Inches(7.2), Inches(5.4), Inches(5.1), Inches(0.35),
     "Каждый критерий — целое от 0 до 3. Модель выдаёт только баллы и обоснование.",
     size=11, color=MUTED_L, line=1.3)

text(s, M, Inches(5.1), Inches(5.8), Inches(0.25), "Пороги категорий",
     size=10, bold=True, caps=True, spacing=1.3, color=MID)
text(s, M, Inches(5.45), Inches(5.8), Inches(0.6),
     [("0 ", {"bold": True, "color": INK}), ("Незначительное   ", {"color": MUTED_L}),
      ("25 ", {"bold": True, "color": INK}), ("Низкое   ", {"color": MUTED_L}),
      ("50 ", {"bold": True, "color": INK}), ("Среднее   ", {"color": MUTED_L}),
      ("75 ", {"bold": True, "color": MID}), ("Высокое   ", {"color": MID}),
      ("90 ", {"bold": True, "color": MID}), ("Критическое", {"color": MID})],
     size=12, line=1.4)
text(s, M, Inches(6.05), Inches(5.8), Inches(0.6),
     [("Флаг эскалации поднимает категорию на ступень. ", {"bold": True, "color": INK}),
      ("Список флагов закрытый: формулировку не из перечня код отбрасывает.", {"color": MUTED_L})],
     size=11.5, line=1.35)
foot(s, "backend/config/scoring.yaml", "08")

# =============================================================== 09 · Досье
s = slide()
eyebrow(s, M, Inches(0.62), "Продукт", "долгоживущая карточка законопроекта")
title(s, M, Inches(1.0), Inches(11.9), "НПА живёт отдельно: стадии, хронология, динамика влияния", size=27)
card(s, Inches(1.68), Inches(1.78), Inches(9.96), Inches(4.98), PAPER, HAIR)
s.shapes.add_picture(str(ASSETS / "shot_act.jpg"), Inches(1.72), Inches(1.82), Inches(9.88), Inches(4.9))
text(s, M, Inches(6.86), Inches(11.9), Inches(0.4),
     [("Стадия «Обсуждение» помечена как неприменимая, а не как непройденная. ",
       {"bold": True, "color": INK}),
      ("Российские акты стадии пропускают, и линейная шкала без этого состояния лжёт.",
       {"color": MUTED_L})], size=11.5, line=1.35)
foot(s, "FR-032 · FR-035 · смена стадии отправляет материалы на переоценку", "09")

# =============================================================== 10 · Конвейер
s = slide()
eyebrow(s, M, Inches(0.72), "Схема решения")
title(s, M, Inches(1.15), Inches(9), "Конвейер обработки материала", size=31)
steps = [("01", "Сбор", "RSS, страницы регуляторов, Telegram. Дедупликация по URL.", False),
         ("02", "Саммари", "3–5 утверждений, к каждому дословная цитата.", False),
         ("03", "Заземление", "Вхождение цитаты — код. Следует ли утверждение — модель.", True),
         ("04", "Классификация", "Новость или НПА: определяет схему оценки.", False),
         ("05", "Оценка", "Модель даёт баллы, код считает индекс.", True),
         ("06", "Лента", "По убыванию влияния, фильтры и поиск.", False)]
bw = Inches(1.87)
for i, (n, t, d, key) in enumerate(steps):
    cx = M + (bw + Inches(0.09)) * i
    card(s, cx, Inches(2.35), bw, Inches(1.95),
         RGBColor(0xEC, 0xF0, 0xF9) if key else PAPER, None if key else HAIR)
    circle(s, cx + Inches(0.2), Inches(2.55), Inches(0.36), DEEP if key else RGBColor(0xE2, 0xE7, 0xF0),
           n, PAPER if key else MUTED_L, size=10)
    text(s, cx + Inches(0.2), Inches(3.06), bw - Inches(0.4), Inches(0.3), t,
         size=13.5, bold=True, color=DEEP if key else INK)
    text(s, cx + Inches(0.2), Inches(3.42), bw - Inches(0.36), Inches(0.8), d,
         size=10.5, color=MUTED_L, line=1.3)
card(s, M, Inches(4.6), Inches(7.2), Inches(1.85), RGBColor(0xF0, 0xF3, 0xF9))
text(s, M + Inches(0.42), Inches(4.85), Inches(6.4), Inches(0.28),
     "Почему заземление в две ступени", size=10, bold=True, caps=True, spacing=1.3, color=DEEP)
text(s, M + Inches(0.42), Inches(5.22), Inches(6.4), Inches(1.1),
     [("Проверки вхождения цитаты недостаточно: настоящая цитата, не подтверждающая "
       "утверждение, проходит поиск по тексту. По измерению Stanford RegLab это главный "
       "класс ошибок — ", {"color": MUTED_L}),
      ("17% у Lexis+ AI, 33% у Westlaw", {"bold": True, "color": INK}),
      (", оба на RAG и оба продавались как «hallucination-free».", {"color": MUTED_L})],
     size=12.5, line=1.38)
text(s, Inches(8.4), Inches(4.85), Inches(4.2), Inches(0.28), "Что не теряется",
     size=10, bold=True, caps=True, spacing=1.3, color=BRASS)
para_list(s, Inches(8.4), Inches(5.22), Inches(4.2), Inches(1.4), [
    "Отбракованное сохраняется с причиной",
    "Отказ модели не теряет материал",
    "Правка человека не перезаписывается",
], size=12, color=MUTED_L)
foot(s, "ADR-0007 · backend/src/pipeline/grounding.py", "10")

# =============================================================== 07 · Этапы
s = slide()
eyebrow(s, M, Inches(0.72), "Выполненные этапы")
title(s, M, Inches(1.15), Inches(9.6), "Слой до кода собран, backend реализован", size=31)
text(s, M, Inches(2.35), Inches(5.5), Inches(0.25), "Продукт и постановка",
     size=10, bold=True, caps=True, spacing=1.3, color=MID)
para_list(s, M, Inches(2.72), Inches(5.5), Inches(2.3), [
    "Конституция проекта: 6 принципов, три необсуждаемые",
    "Спецификация: 7 историй, 50 требований, 13 критериев",
    "Модель данных, контракты API и вызовов модели",
    "8 ADR, 7 гипотез, бизнес-кейс, 14 вопросов заказчику",
    "Исследование рынка: ~40 продуктов, 31 находка",
], size=13, color=MUTED_L, bullet_color=OK)
text(s, Inches(7.3), Inches(2.35), Inches(5.3), Inches(0.25), "Реализация",
     size=10, bold=True, caps=True, spacing=1.3, color=MID)
para_list(s, Inches(7.3), Inches(2.72), Inches(5.3), Inches(2.3), [
    "Сбор из трёх типов источников",
    "Конвейер: саммари, заземление, классификация, оценка",
    "Формула индекса и шкала категорий в конфиге",
    "Лента, фильтры, поиск, ручное редактирование",
    "Профили компании и переоценка при переключении",
], size=13, color=MUTED_L, bullet_color=OK)
rule(s, M, Inches(5.28), Inches(11.9))
for i, (n, l) in enumerate([("54", "задачи закрыты из 105"),
                            ("89", "тестов, все проходят"),
                            ("5 735", "строк backend с тестами")]):
    cx = M + Inches(4.05) * i
    text(s, cx, Inches(5.55), Inches(3.5), Inches(0.6), n, size=36, bold=True, color=DEEP, line=1.0)
    text(s, cx, Inches(6.15), Inches(3.4), Inches(0.4), l, size=12, color=MUTED_L)
foot(s, "Спецификация ведёт код: каждая задача ссылается на требование", "11")

# =============================================================== 08 · Результаты
s = slide("dark")
eyebrow(s, M, Inches(0.72), "Первые результаты", on_dark=True)
title(s, M, Inches(1.15), Inches(9.6), "Формула воспроизводит методику заказчика точно",
      size=31, on_dark=True)
s.shapes.add_picture(str(ASSETS / "bg_stat.jpg"), M, Inches(2.4), Inches(3.5), Inches(1.95))
text(s, M + Inches(0.35), Inches(2.72), Inches(2.9), Inches(0.8), "42 / 42",
     size=46, bold=True, color=PAPER, line=1.0)
text(s, M + Inches(0.35), Inches(3.62), Inches(2.85), Inches(0.6),
     "карточки реестра — совпадение индекса и итоговой категории",
     size=11.5, color=RGBColor(0xC8, 0xD4, 0xEE), line=1.3)
text(s, M, Inches(4.6), Inches(3.5), Inches(0.25), "Ещё замерено",
     size=10, bold=True, caps=True, spacing=1.3, color=BRASS)
para_list(s, M, Inches(4.95), Inches(3.5), Inches(1.4), [
    "7–24 мс отклик фильтров при цели «менее секунды»",
    "0 незаземлённых утверждений проходит в саммари",
], size=12, color=MUTED_D)
cw2 = [Inches(2.3), Inches(2.0), Inches(2.0), Inches(1.9)]
table(s, Inches(4.6), Inches(2.4), Inches(8.0),
      ["Карточка", "Баллы К1–К6", "Excel заказчика", "Наш расчёт"],
      [["№ 1 · CAS DRM", "3 2 3 0 0 3", "65,0 → Высокое", {"t": "65,0 → Высокое", "f": {"bold": True, "color": BRASS}}],
       ["№ 2 · ФЗ № 243-ФЗ", "3 3 1 1 0 0", "51,7 → Среднее", {"t": "51,7 → Среднее", "f": {"bold": True, "color": BRASS}}],
       ["№ 22 · ПП № 402", "3 3 2 2 1 3", "78,3 → Высокое", {"t": "78,3 → Высокое", "f": {"bold": True, "color": BRASS}}]],
      cw2, head_color=MUTED_D, body_color=PAPER, size=11.5, row_h=Inches(0.42))
text(s, Inches(4.6), Inches(4.35), Inches(8.0), Inches(0.3),
     "Индекс 65 даёт «Среднее», флаг эскалации поднимает до «Высокого» — совпало тоже",
     size=10.5, color=MUTED_D)
text(s, Inches(4.6), Inches(4.9), Inches(8.0), Inches(0.25), "Дефекты, найденные при реализации",
     size=10, bold=True, caps=True, spacing=1.3, color=BRASS)
para_list(s, Inches(4.6), Inches(5.25), Inches(8.0), Inches(1.3), [
    [("Схема оценки сравнивалась через тождество", {"bold": True, "color": PAPER}),
     (" — оценка НПА молча уходила в схему новостей", {"color": MUTED_D})],
    [("Кириллица в JSON хранилась экранированной", {"bold": True, "color": PAPER}),
     (" — поиск не находил ничего", {"color": MUTED_D})],
], size=12, color=MUTED_D)
foot(s, "python -m src.cli verify-formula", "12", on_dark=True)

# =============================================================== 10 · Метрики
s = slide("dark")
eyebrow(s, M, Inches(0.72), "Метрики", "измерено, а не оценено на глаз", on_dark=True)
title(s, M, Inches(1.15), Inches(10.4), "Время, деньги, качество", size=31, on_dark=True)

blocks = [
    ("Время", "12,7 с", "медиана обработки одного материала при цели 10–15 с",
     "Ручной мониторинг 3–4 часа в день заменяется разбором готовой ленты за 10–15 минут"),
    ("Деньги", "$0,00044", "стоимость одного материала целиком: саммари, заземление, оценка",
     "Поток 150 материалов в сутки обходится примерно в 2 доллара в месяц"),
    ("Качество", "37 / 42", "карточки эталона заказчика — категория совпала или разошлась на ступень",
     "Провалов критичного в нижние категории: 1. Это ключевое условие заказчика"),
]
for i, (label, big, cap, note) in enumerate(blocks):
    cx = M + Inches(4.05) * i
    card(s, cx, Inches(2.3), Inches(3.75), Inches(2.75), RGBColor(0x16, 0x22, 0x46))
    text(s, cx + Inches(0.32), Inches(2.55), Inches(3.1), Inches(0.25), label,
         size=10, bold=True, caps=True, spacing=1.3, color=BRASS)
    text(s, cx + Inches(0.32), Inches(2.95), Inches(3.1), Inches(0.62), big,
         size=34, bold=True, color=PAPER, line=1.0)
    text(s, cx + Inches(0.32), Inches(3.72), Inches(3.1), Inches(0.6), cap,
         size=11, color=RGBColor(0xC8, 0xD4, 0xEE), line=1.3)
    text(s, cx + Inches(0.32), Inches(4.35), Inches(3.1), Inches(0.6), note,
         size=11, color=MUTED_D, line=1.3)

rule(s, M, Inches(5.35), Inches(11.9), RGBColor(0x2B, 0x37, 0x5E))
text(s, M, Inches(5.55), Inches(5.7), Inches(0.25), "Заземление саммари · 820 утверждений",
     size=10, bold=True, caps=True, spacing=1.3, color=BRASS)
para_list(s, M, Inches(5.9), Inches(5.7), Inches(1.1), [
    [("89,1 % ", {"bold": True, "color": PAPER}), ("подтверждены обеими ступенями", {"color": MUTED_D})],
    [("8,2 % ", {"bold": True, "color": PAPER}),
     ("поймала вторая ступень: цитата настоящая, но утверждения не подтверждает", {"color": MUTED_D})],
], size=11.5, color=MUTED_D)
text(s, Inches(7.3), Inches(5.55), Inches(5.3), Inches(1.4),
     [("Почему это важно. ", {"bold": True, "color": PAPER}),
      ("Проверка вхождения строки эти 8,2 % пропустила бы, и утверждения попали бы "
       "в ленту с видимой цитатой-подтверждением — то есть выглядели бы достовернее "
       "непроверенного текста. Именно на этом классе ошибок коммерческие правовые ИИ "
       "дают 17–33 %.", {"color": MUTED_D})], size=11.5, line=1.35)
foot(s, "evals/results.md · python -m src.cli evaluate", "13", on_dark=True)

# =============================================================== 11 · Демо
s = slide()
eyebrow(s, M, Inches(0.72), "Демонстрация")
title(s, M, Inches(1.15), Inches(10.4), "Что показываем и что честно назвать незакрытым", size=31)
card(s, M, Inches(2.4), Inches(5.8), Inches(3.4), PAPER, HAIR)
text(s, M + Inches(0.4), Inches(2.7), Inches(5.0), Inches(0.25), "Сценарий демо",
     size=10, bold=True, caps=True, spacing=1.3, color=OK)
para_list(s, M + Inches(0.4), Inches(3.05), Inches(5.0), Inches(2.6), [
    "Добавление источника и запуск сбора",
    "Лента, отсортированная по влиянию на компанию",
    "Карточка: шесть баллов с обоснованием",
    "Наведение на утверждение — цитата из оригинала",
    "Правка балла — индекс пересчитывается сразу",
    "Переключение профиля — порядок ленты меняется",
], size=12.5, color=MUTED_L, bullet_color=OK)
card(s, Inches(7.0), Inches(2.4), Inches(5.6), Inches(3.4), RGBColor(0xF7, 0xF3, 0xEC))
text(s, Inches(7.4), Inches(2.7), Inches(4.8), Inches(0.25), "Чего пока нет",
     size=10, bold=True, caps=True, spacing=1.3, color=WARN)
para_list(s, Inches(7.4), Inches(3.05), Inches(4.8), Inches(2.6), [
    [("Фронтенда", {"bold": True}), (" — сейчас API и автодокументация", {"color": MUTED_L})],
    [("Досье НПА", {"bold": True}), (" — главное отличие, следующий приоритет", {"color": MUTED_L})],
    [("Дедупликации и дайджеста", {"bold": True}), (" — приоритет пересмотрен вверх", {"color": MUTED_L})],
    [("Измерения на живой модели", {"bold": True}), (" — конвейер верен, качество не измерено", {"color": MUTED_L})],
], size=12.5, color=MUTED_L, bullet_color=WARN)
text(s, M, Inches(6.05), Inches(11.9), Inches(0.7),
     [("Инфраструктура. ", {"bold": True}),
      ("Пайплайн деплоя написан: сборка, доставка, health-проба. Два внешних блокера — "
       "Actions падает на старте по причине уровня аккаунта, порт 22 сервера не отвечает. "
       "Запасной путь развёртывания готов и не зависит от обоих.", {"color": MUTED_L})],
     size=12.5, line=1.35)
foot(s, "Локальный запуск — backend/README.md", "14")

# =============================================================== 10 · Риски
s = slide()
eyebrow(s, M, Inches(0.72), "Риски")
title(s, M, Inches(1.15), Inches(10.4), "Что может не сработать и как это проверяется", size=31)
cw3 = [Inches(4.4), Inches(1.7), Inches(5.8)]
table(s, M, Inches(2.5), Inches(11.9), ["Риск", "Оценка", "Как снимаем"],
      [[{"t": "H-01: профиля компании в промпте недостаточно", "f": {"bold": True}},
        {"t": "критический", "chip": CRIT},
        "Прогон на 42 карточках с эталонными баллами. Если не подтвердится — фильтр по профилю плюс few-shot."],
       [{"t": "Профиль GS Labs восстановлен нами, не подтверждён заказчиком", "f": {"bold": True}},
        {"t": "высокий", "chip": CRIT},
        "Вопрос OQ-01 заказчику. Единственное, что нельзя закрыть кодом."],
       [{"t": "42 карточек мало для значимости", "f": {"bold": True}},
        {"t": "высокий", "chip": WARN},
        "Заявляем как проверку на данных заказчика, не как бенчмарк. Расширение — OQ-08."],
       [{"t": "Отказ внешнего API во время защиты", "f": {"bold": True}},
        {"t": "средний", "chip": WARN},
        "Резервный провайдер модели и кеш ответов."],
       [{"t": "Сервер и CI недоступны", "f": {"bold": True}},
        {"t": "реализовался", "chip": CRIT},
        "Запасной путь развёртывания с рабочей машины теми же шагами."]],
      cw3, size=11, row_h=Inches(0.5))
card(s, M, Inches(6.16), Inches(11.9), Inches(0.64), RGBColor(0xF7, 0xF3, 0xEC))
text(s, M + Inches(0.35), Inches(6.29), Inches(11.2), Inches(0.42),
     [("Чего мы не будем делать. ", {"bold": True, "color": WARN}),
      ("Не добавляем «вероятность принятия законопроекта»: доля принимаемых актов — единицы "
       "процентов: модель, всегда отвечающая «не пройдёт», даёт ~95% точности и бесполезна. Ровно на этом FiscalNote потеряла заявленную ценность.", {"color": MUTED_L})],
     size=11.5, line=1.3)
foot(s, "7 гипотез с порогами принятия — docs/hypotheses.md", "15")

# =============================================================== 11 · План
s = slide()
eyebrow(s, M, Inches(0.72), "План до финальной защиты")
title(s, M, Inches(1.15), Inches(9.6), "Порядок работ и правило остановки", size=31)
card(s, M, Inches(2.4), Inches(5.8), Inches(2.9), RGBColor(0xEC, 0xF0, 0xF9))
circle(s, M + Inches(0.4), Inches(2.68), Inches(0.42), DEEP, "1", size=12)
text(s, M + Inches(0.98), Inches(2.78), Inches(4.6), Inches(0.3), "Доказать ценность",
     size=15, bold=True, color=DEEP)
para_list(s, M + Inches(0.4), Inches(3.35), Inches(5.0), Inches(2.0), [
    "Отправить заказчику OQ-01 и OQ-08",
    "Прогон на эталоне: базовая ставка, recall, precision",
    "Разбор ошибок, правка промптов, повторный замер",
    "Фронтенд ленты и карточки с раскрытой оценкой",
], size=12.5, color=MUTED_L, bullet_color=DEEP)
card(s, Inches(7.0), Inches(2.4), Inches(5.6), Inches(2.9), PAPER, HAIR)
circle(s, Inches(7.4), Inches(2.68), Inches(0.42), BRASS, "2", size=12)
text(s, Inches(7.98), Inches(2.78), Inches(4.4), Inches(0.3), "Отличие от конкурентов",
     size=15, bold=True)
para_list(s, Inches(7.4), Inches(3.35), Inches(4.8), Inches(2.0), [
    "Досье НПА: стадии, хронология, история оценок",
    "Четыре состояния стадии, включая «неприменима»",
    "Дедупликация с гейтом по общим сущностям",
    "Дайджест под получателя и выгрузка",
], size=12.5, color=MUTED_L)
rule(s, M, Inches(5.6), Inches(11.9))
text(s, M, Inches(5.85), Inches(5.6), Inches(0.9),
     [("Правило остановки. ", {"bold": True, "color": CRIT}),
      ("Если досье НПА не закрыто — не начинаем дедупликацию и дайджест. Досье отвечает на "
       "вопрос «чем вы лучше существующих решений», остальное нет.", {"color": MUTED_L})],
     size=12.5, line=1.35)
text(s, Inches(7.3), Inches(5.85), Inches(5.3), Inches(0.9),
     [("Что скажем про качество. ", {"bold": True}),
      ("Только измеренную величину с базовой ставкой рядом. Формулировка «без галлюцинаций» "
       "запрещена внутренним правилом проекта.", {"color": MUTED_L})],
     size=12.5, line=1.35)
foot(s, "51 задача осталась · specs/001-ai-monitoring-center/tasks.md", "16")

# =============================================================== 12 · Команда
s = slide("dark")
eyebrow(s, M, Inches(0.72), "Команда", on_dark=True)
title(s, M, Inches(1.15), Inches(10.4), "Роли, зоны ответственности и участие", size=31, on_dark=True)
team = [("ЛЕ", "Левочкин Егор", "AI Product · 1 курс · @veceloe",
         "Продуктовая постановка, спецификация и ADR, методика оценки, гипотезы, исследование рынка, заказчик. Инженерно — парсинг и фронтенд", BRASS),
        ("ГД", "Головаш Денис", "AI Engineer · 1 курс · @denizzzz_ka",
         "LLM-слой целиком: провайдер с резервным и кешем, версионированные промпты, схемы ответов, заземление, качество оценки", MID),
        ("АИ", "Артемьев Иван", "AI Engineer · 1 курс · @s3drmn",
         "Backend: модель данных, конвейер обработки, API по контракту, хранилище, развёртывание", RGBColor(0x4A, 0x6B, 0xC4))]
for i, (ini, name, meta, resp, col) in enumerate(team):
    cx = M + Inches(4.05) * i
    card(s, cx, Inches(2.35), Inches(3.75), Inches(3.15), RGBColor(0x16, 0x22, 0x46))
    circle(s, cx + Inches(0.32), Inches(2.65), Inches(0.62), col, ini,
           INK if col == BRASS else PAPER, size=15)
    text(s, cx + Inches(0.32), Inches(3.45), Inches(3.1), Inches(0.3), name,
         size=16, bold=True, color=PAPER)
    text(s, cx + Inches(0.32), Inches(3.82), Inches(3.1), Inches(0.28), meta,
         size=11, color=BRASS)
    text(s, cx + Inches(0.32), Inches(4.25), Inches(3.1), Inches(1.4), resp,
         size=11.5, color=MUTED_D, line=1.34)
rule(s, M, Inches(5.72), Inches(11.9), RGBColor(0x2B, 0x37, 0x5E))
# QR ведёт на живой стенд: с ним демо можно открыть с телефона прямо из зала.
s.shapes.add_picture(str(ASSETS / "qr-demo.png"), M, Inches(5.95), Inches(1.15), Inches(1.15))
text(s, M + Inches(1.35), Inches(6.02), Inches(4.4), Inches(0.3), "Живой стенд",
     size=10, bold=True, caps=True, spacing=1.3, color=BRASS)
text(s, M + Inches(1.35), Inches(6.34), Inches(4.4), Inches(0.6),
     [("185.56.162.154", {"bold": True, "color": PAPER, "size": 15}),
      ("\nЛента, досье НПА и дайджест на данных заказчика", {"color": MUTED_D})],
     size=11, line=1.3)
text(s, Inches(7.3), Inches(5.95), Inches(5.3), Inches(1.15),
     [("Как организована работа. ", {"bold": True, "color": PAPER}),
      ("Границей между дорожками служит контракт API, зафиксированный до кодирования: "
       "дорожки не блокируют друг друга, а расхождение ручных типов с контрактом "
       "становится ошибкой компиляции, а не сюрпризом у пользователя.",
       {"color": MUTED_D})], size=11.5, line=1.35)
foot(s, "github.com/veceloe/ai-gpr-center-cifra", "17", on_dark=True)

count = len(prs.slides._sldIdLst)
assert count == TOTAL_SLIDES, f"слайдов {count}, а в подвале написано {TOTAL_SLIDES}"
prs.save(str(OUT))
print("сохранено:", OUT, f"{OUT.stat().st_size // 1024} КБ, слайдов: {len(prs.slides.__iter__.__self__._sldIdLst)}")
