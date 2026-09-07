"""Сборка презентации к защите.

Три правила, нарушать нельзя — они и есть ответ на «почему было плохо»:

1. ОДНА МЫСЛЬ НА СЛАЙД. Заголовок — утверждение, а не тема. Под ним одна строка
   пояснения и либо экран продукта, либо три числа. Таблиц почти нет.
2. ПАЛИТРА ПРОДУКТА. Те же цвета, что в интерфейсе: зелёный GS Labs на белом.
   Прежняя дека была тёмно-синей с латунью и выглядела как из другого проекта.
3. СТОЛЬКО СЛАЙДОВ, СКОЛЬКО ПРОИЗНОСИТСЯ. Речь идёт три минуты по шести слайдам;
   семнадцать слайдов означали, что одиннадцать никто не смотрит.
"""

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

HERE = Path(__file__).resolve().parent
ASSETS = HERE / "assets"
OUT = HERE / "presentation.pptx"

W, H = Inches(13.333), Inches(7.5)
M = Inches(0.8)
FONT = "Inter Tight"

# --- палитра взята из styles/app.css продукта ---------------------------------
INK = RGBColor(0x23, 0x1F, 0x20)
NIGHT = RGBColor(0x10, 0x12, 0x14)      # основной фон
PANEL = RGBColor(0x1B, 0x1F, 0x24)      # блок бенто
PANEL_2 = RGBColor(0x23, 0x28, 0x2E)
TEXT_D = RGBColor(0xF2, 0xF4, 0xF3)     # текст на тёмном
MUTED_D = RGBColor(0x8B, 0x94, 0x9E)
BRAND = RGBColor(0x43, 0xB0, 0x2A)
BRAND_DARK = RGBColor(0x37, 0x91, 0x23)
BRAND_SOFT = RGBColor(0xEE, 0xF8, 0xEA)
CANVAS = RGBColor(0xF9, 0xF9, 0xF9)
SURFACE = RGBColor(0xFF, 0xFF, 0xFF)
LINE = RGBColor(0xD9, 0xD9, 0xD9)
MUTED = RGBColor(0x6B, 0x72, 0x80)
FAINT = RGBColor(0x9A, 0xA1, 0xAB)
RISK = RGBColor(0xEB, 0x57, 0x57)
MID_GREEN = RGBColor(0xA8, 0xDC, 0x98)

prs = Presentation()
prs.slide_width, prs.slide_height = W, H
BLANK = prs.slide_layouts[6]
TOTAL = 10
_num = 0


def slide(bg=NIGHT):
    s = prs.slides.add_slide(BLANK)
    r = s.shapes.add_shape(1, 0, 0, W, H)
    r.fill.solid()
    r.fill.fore_color.rgb = bg
    r.line.fill.background()
    r.shadow.inherit = False
    return s


def text(s, x, y, w, h, runs, size=14, color=INK, bold=False, line=1.32,
         align=PP_ALIGN.LEFT, caps=False, spacing=None):
    box = s.shapes.add_textbox(x, y, w, h)
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    p = tf.paragraphs[0]
    p.alignment = align
    p.line_spacing = line
    for chunk, over in (runs if isinstance(runs, list) else [(runs, {})]):
        r = p.add_run()
        r.text = chunk
        f = r.font
        f.name = FONT
        f.size = Pt(over.get("size", size))
        f.bold = over.get("bold", bold)
        f.color.rgb = over.get("color", color)
        if over.get("caps", caps):
            f._rPr.set("cap", "all")
        if over.get("spacing", spacing):
            f._rPr.set("spc", str(int(over.get("spacing", spacing) * 100)))
    return box


def eyebrow(s, txt, color=BRAND_DARK):
    text(s, M, Inches(0.62), Inches(11.7), Inches(0.25), txt,
         size=10.5, bold=True, color=color, caps=True, spacing=1.4)


def headline(s, txt, size=30, color=INK, width=Inches(11.7)):
    text(s, M, Inches(1.0), width, Inches(1.0), txt, size=size, bold=True,
         color=color, line=1.14)


def lead(s, y, txt, color=MUTED, width=Inches(11.7), size=14.5):
    text(s, M, y, width, Inches(0.7), txt, size=size, color=color, line=1.4)


def shot(s, name, y=Inches(1.9)):
    """Экран продукта. Пропорции 2880x1428 сохраняются: ширина 9.9 → высота 4.909.

    Ширина подобрана так, чтобы снимок не наезжал на подвал: 1,9 + 4,91 = 6,81
    при подвале на 6,98. Подпись идёт НАД снимком — под ним места уже нет.
    """
    w, h = Inches(9.9), Inches(4.909)
    x = Inches((13.333 - 9.9) / 2)
    frame = s.shapes.add_shape(1, x - Inches(0.03), y - Inches(0.03),
                               w + Inches(0.06), h + Inches(0.06))
    frame.fill.solid()
    frame.fill.fore_color.rgb = SURFACE
    frame.line.color.rgb = LINE
    frame.line.width = Pt(0.75)
    frame.shadow.inherit = False
    s.shapes.add_picture(str(ASSETS / name), x, y, w, h)


def foot(s, left="", color=FAINT):
    global _num
    _num += 1
    if left:
        text(s, M, H - Inches(0.52), Inches(9.6), Inches(0.26), left, size=9.5, color=color)
    text(s, W - M - Inches(1.4), H - Inches(0.52), Inches(1.4), Inches(0.26),
         f"{_num} / {TOTAL}", size=9.5, color=color, align=PP_ALIGN.RIGHT)


def bar(s, x, y, h, color=BRAND):
    """Вертикальная полоса — тот же приём, что слева от строки в ленте продукта."""
    r = s.shapes.add_shape(1, x, y, Inches(0.055), h)
    r.fill.solid()
    r.fill.fore_color.rgb = color
    r.line.fill.background()
    r.shadow.inherit = False


def big(s, x, y, w, txt, size=60, color=INK):
    text(s, x, y, w, Inches(size / 58), txt, size=size, bold=True, color=color, line=1.0)


def label(s, x, y, w, txt, color=MUTED):
    text(s, x, y, w, Inches(0.24), txt, size=10.5, bold=True, color=color,
         caps=True, spacing=1.4)


def box(s, x, y, w, h, fill=SURFACE, line_color=LINE, width=Pt(1.0)):
    r = s.shapes.add_shape(5, x, y, w, h)  # скруглённый прямоугольник
    r.fill.solid()
    r.fill.fore_color.rgb = fill
    r.line.color.rgb = line_color
    r.line.width = width
    r.shadow.inherit = False
    r.adjustments[0] = 0.06
    return r


def arrow(s, x, y, w, color=INK):
    a = s.shapes.add_shape(13, x, y, w, Inches(0.16))  # стрелка вправо
    a.fill.solid()
    a.fill.fore_color.rgb = color
    a.line.fill.background()
    a.shadow.inherit = False
    return a


def waffle(s, x, y, counts, cell=Inches(0.42), gap=Inches(0.09), per_row=14):
    """Одна клетка — одна карточка эталона. Не украшение: раскладка равна замеру."""
    i = 0
    for color, n in counts:
        for _ in range(n):
            cx = x + (cell + gap) * (i % per_row)
            cy = y + (cell + gap) * (i // per_row)
            r = s.shapes.add_shape(1, cx, cy, cell, cell)
            r.fill.solid()
            r.fill.fore_color.rgb = color
            r.line.fill.background()
            r.shadow.inherit = False
            i += 1


def legend(s, x, y, entries, size=12):
    off = Inches(0)
    for color, txt in entries:
        d = s.shapes.add_shape(1, x + off, y + Inches(0.03), Inches(0.16), Inches(0.16))
        d.fill.solid(); d.fill.fore_color.rgb = color
        d.line.fill.background(); d.shadow.inherit = False
        text(s, x + off + Inches(0.26), y, Inches(2.9), Inches(0.25), txt, size=size, color=MUTED)
        off += Inches(3.15)



def panel(s, x, y, w, h, fill=PANEL):
    """Блок бенто-сетки: разные размеры на одном слайде, без рамок."""
    r = s.shapes.add_shape(5, x, y, w, h)
    r.fill.solid()
    r.fill.fore_color.rgb = fill
    r.line.fill.background()
    r.shadow.inherit = False
    r.adjustments[0] = 0.045
    return r


# ============================================================ 01 · Титул
s = slide()
text(s, M, Inches(2.3), Inches(11.7), Inches(0.3), "ITMO AI PRODUCT HACK · КЕЙС ООО «ЦИФРА»",
     size=11.5, bold=True, color=MUTED_D, spacing=2.0)
text(s, M, Inches(2.95), Inches(11.7), Inches(2.4),
     [("Мониторинг,\nкоторый отвечает\nна вопрос ", {"color": TEXT_D}),
      ("«и что?»", {"color": BRAND})],
     size=62, bold=True, line=1.05)
text(s, M, Inches(5.95), Inches(7.6), Inches(0.5),
     "Интеллектуальный центр PR/GR-мониторинга для GS Labs",
     size=17, color=MUTED_D)
s.shapes.add_picture(str(ASSETS / "qr-demo.png"), W - M - Inches(1.5), Inches(5.2),
                     Inches(1.5), Inches(1.5))
text(s, W - M - Inches(3.4), Inches(6.82), Inches(3.4), Inches(0.3), "185.56.162.154",
     size=12, bold=True, color=TEXT_D, align=PP_ALIGN.RIGHT)

# ============================================================ 02 · Проблема
# Одно огромное число и одна фраза. Больше на слайде ничего нет.
s = slide()
text(s, M, Inches(1.5), Inches(7.2), Inches(0.3), "ЗАЧЕМ ЭТО ВООБЩЕ",
     size=11, bold=True, color=BRAND, spacing=2.0)
text(s, M, Inches(2.0), Inches(6.6), Inches(2.6),
     "630", size=150, bold=True, color=TEXT_D, line=0.94)
text(s, M, Inches(4.3), Inches(6.2), Inches(0.4),
     "часов в год у одного специалиста", size=20, color=BRAND)
text(s, M, Inches(4.95), Inches(5.9), Inches(1.4),
     "Столько уходит на ручное чтение лент, порталов регуляторов и телеграм-каналов. "
     "Ориентир заказчика — разбирать суточную повестку за 10–15 минут.",
     size=14.5, color=MUTED_D, line=1.5)
panel(s, Inches(7.6), Inches(2.0), Inches(5.0), Inches(3.9))
text(s, Inches(8.0), Inches(2.5), Inches(4.2), Inches(2.6),
     [("Агрегаторы отвечают, ", {"color": MUTED_D}),
      ("что интересного произошло", {"color": TEXT_D, "bold": True}),
      (".\n\nGR-специалисту нужен другой ответ: ", {"color": MUTED_D}),
      ("что из этого касается нашей компании", {"color": BRAND, "bold": True}),
      (".", {"color": MUTED_D})], size=21, line=1.42)
foot(s, "docs/business-case.md · расчёт согласован с заказчиком", MUTED_D)

# ============================================================ 03 · Решение
s = slide()
text(s, M, Inches(1.15), Inches(11.7), Inches(1.4),
     [("Модель выставляет баллы.\n", {"color": TEXT_D}),
      ("Индекс считает код.", {"color": BRAND})],
     size=52, bold=True, line=1.1)
panel(s, M, Inches(3.55), Inches(5.1), Inches(2.0))
text(s, M + Inches(0.4), Inches(3.85), Inches(4.4), Inches(0.3), "МОДЕЛЬ ОТДАЁТ",
     size=10.5, bold=True, color=MUTED_D, spacing=1.8)
text(s, M + Inches(0.4), Inches(4.25), Inches(4.4), Inches(1.1),
     [("К1·3   К2·2   К3·3   К4·0   К5·0   К6·3", {"color": TEXT_D, "size": 19, "bold": True}),
      ("\nи обоснование к каждому баллу", {"color": MUTED_D, "size": 14})], line=1.55)
arrow(s, M + Inches(5.35), Inches(4.45), Inches(0.75), BRAND)
panel(s, M + Inches(6.5), Inches(3.55), Inches(5.2), Inches(2.0), PANEL_2)
text(s, M + Inches(6.9), Inches(3.85), Inches(4.5), Inches(0.3), "КОД ВЫЧИСЛЯЕТ",
     size=10.5, bold=True, color=BRAND, spacing=1.8)
text(s, M + Inches(6.9), Inches(4.25), Inches(4.5), Inches(1.1),
     [("65,0", {"color": TEXT_D, "size": 26, "bold": True}),
      ("  →  ", {"color": MUTED_D, "size": 20}),
      ("Среднее", {"color": TEXT_D, "size": 20, "bold": True}),
      ("\nфлаг эскалации поднимает до «Высокого»", {"color": MUTED_D, "size": 14})],
     line=1.5)
text(s, M, Inches(5.95), Inches(11.5), Inches(0.7),
     [("В контракте ответа модели полей «индекс» и «категория» нет вовсе. ",
       {"color": TEXT_D, "bold": True}),
      ("Она физически не может их вернуть — поэтому оценку можно проверить и поправить.",
       {"color": MUTED_D})], size=15, line=1.45)
foot(s, "ADR-0003 · backend/config/scoring.yaml", MUTED_D)

# ============================================================ 04 · Лента
s = slide(CANVAS)
text(s, M, Inches(0.62), Inches(11.7), Inches(0.3), "ВОТ КАК ЭТО ВЫГЛЯДИТ",
     size=11, bold=True, color=BRAND_DARK, spacing=2.0)
text(s, M, Inches(1.0), Inches(11.7), Inches(0.5),
     "Сверху то, что важнее для компании, а не то, что свежее", size=30, bold=True, color=INK)
lead(s, Inches(1.6), "Цветом отмечены только два верхних уровня серьёзности — сортировка "
     "уже сделала главную работу.", size=13)
shot(s, "shot_feed.jpg", Inches(2.0))
foot(s, "живой стенд: 185.56.162.154")

# ============================================================ 05 · Сколько стоит
s = slide()
text(s, M, Inches(1.15), Inches(11.7), Inches(0.3), "СКОЛЬКО СТОИТ",
     size=11, bold=True, color=BRAND, spacing=2.0)
text(s, M, Inches(1.6), Inches(11.5), Inches(1.2),
     "Год работы модели дешевле,\nчем один пропущенный документ",
     size=42, bold=True, color=TEXT_D, line=1.1)

panel(s, M, Inches(3.9), Inches(11.7), Inches(2.15))
text(s, M + Inches(0.45), Inches(4.2), Inches(6.0), Inches(0.28),
     "ГОД ОБРАБОТКИ ПОТОКА В 150 МАТЕРИАЛОВ В СУТКИ",
     size=10.5, bold=True, color=MUTED_D, spacing=1.6)
SCALE = Inches(9.6) / 500000
r = s.shapes.add_shape(1, M + Inches(0.45), Inches(4.58), max(int(2100 * SCALE), Inches(0.035)), Inches(0.3))
r.fill.solid(); r.fill.fore_color.rgb = BRAND
r.line.fill.background(); r.shadow.inherit = False
text(s, M + Inches(0.62), Inches(4.55), Inches(4.0), Inches(0.34), "2 100 ₽",
     size=18, bold=True, color=BRAND)
text(s, M + Inches(0.45), Inches(5.12), Inches(8.0), Inches(0.28),
     "ОДИН ШТРАФ ПО ФЗ № 295-ФЗ, ВЕРХНЯЯ ГРАНИЦА",
     size=10.5, bold=True, color=MUTED_D, spacing=1.6)
r = s.shapes.add_shape(1, M + Inches(0.45), Inches(5.5), Inches(9.6), Inches(0.3))
r.fill.solid(); r.fill.fore_color.rgb = RISK
r.line.fill.background(); r.shadow.inherit = False
text(s, M + Inches(0.62), Inches(5.47), Inches(4.0), Inches(0.34), "500 000 ₽",
     size=18, bold=True, color=TEXT_D)

text(s, M, Inches(6.35), Inches(11.5), Inches(0.6),
     [("Полосы в одном масштабе, зелёная не увеличена. ", {"color": TEXT_D, "bold": True}),
      ("Четыре копейки за материал. Одного пропуска хватает, чтобы перекрыть "
       "двести лет работы модели. Курс ЦБ на 05.09.2026.", {"color": MUTED_D})],
     size=14, line=1.45)
foot(s, "docs/business-case.md", MUTED_D)

# ============================================================ 06 · Насколько точно
s = slide()
text(s, M, Inches(0.95), Inches(11.7), Inches(0.3), "НАСКОЛЬКО ТОЧНО",
     size=11, bold=True, color=BRAND, spacing=2.0)
text(s, M, Inches(1.4), Inches(11.5), Inches(0.6),
     "Проверено на реестре самого заказчика", size=40, bold=True, color=TEXT_D)

panel(s, M, Inches(2.45), Inches(7.5), Inches(3.5))
text(s, M + Inches(0.42), Inches(2.75), Inches(6.6), Inches(0.28),
     "42 КАРТОЧКИ · ОДНА КЛЕТКА — ОДНА КАРТОЧКА",
     size=10.5, bold=True, color=MUTED_D, spacing=1.6)
waffle(s, M + Inches(0.42), Inches(3.2), [(BRAND, 18), (MID_GREEN, 20), (RISK, 4)],
       cell=Inches(0.36), gap=Inches(0.1), per_row=14)
legend(s, M + Inches(0.42), Inches(5.35), [
    (BRAND, "18 — точно"), (MID_GREEN, "20 — на ступень"), (RISK, "4 — дальше"),
], size=12)

panel(s, Inches(8.8), Inches(2.45), Inches(3.8), Inches(1.62), PANEL_2)
text(s, Inches(9.15), Inches(2.7), Inches(3.2), Inches(0.8), "42 / 42",
     size=40, bold=True, color=BRAND, line=1.0)
text(s, Inches(9.15), Inches(3.42), Inches(3.2), Inches(0.5),
     "формула сходится с Excel заказчика точно", size=12.5, color=MUTED_D, line=1.4)

panel(s, Inches(8.8), Inches(4.33), Inches(3.8), Inches(1.62))
text(s, Inches(9.15), Inches(4.58), Inches(3.2), Inches(0.8), "1",
     size=40, bold=True, color=RISK, line=1.0)
text(s, Inches(9.15), Inches(5.3), Inches(3.2), Inches(0.5),
     "провал важного в нижние категории при цели ноль", size=12.5, color=MUTED_D, line=1.4)

text(s, M, Inches(6.25), Inches(11.5), Inches(0.6),
     [("Клетки — это модель. ", {"color": TEXT_D, "bold": True}),
      ("Она сама выставила баллы. «42 из 42» — это про формулу: получив экспертные "
       "баллы, код выдаёт тот же индекс. Путать эти два числа нельзя.",
       {"color": MUTED_D})], size=14, line=1.45)
foot(s, "evals/results.md · verify-formula", MUTED_D)

# ============================================================ 07 · Границы
s = slide()
text(s, M, Inches(1.15), Inches(11.7), Inches(0.3), "ЧЕСТНО",
     size=11, bold=True, color=RISK, spacing=2.0)
text(s, M, Inches(1.6), Inches(11.5), Inches(0.7), "Чего мы измерить не смогли",
     size=42, bold=True, color=TEXT_D)
panel(s, M, Inches(2.95), Inches(7.5), Inches(3.15), PANEL_2)
text(s, M + Inches(0.45), Inches(3.3), Inches(6.6), Inches(0.4),
     "Точность фильтрации", size=24, bold=True, color=TEXT_D)
text(s, M + Inches(0.45), Inches(3.9), Inches(6.6), Inches(1.9),
     "В реестре заказчика нет ни одной нерелевантной карточки — сравнивать не с чем. "
     "Заявленные 80 % на таких данных неизмеримы в принципе: тривиальный классификатор "
     "«всё релевантно» даёт здесь 100 %. Нужен размеченный набор с отрицательными "
     "примерами; это открытый вопрос к заказчику.",
     size=14.5, color=MUTED_D, line=1.5)
panel(s, Inches(8.8), Inches(2.95), Inches(3.8), Inches(1.5))
text(s, Inches(9.15), Inches(3.2), Inches(3.2), Inches(0.3),
     "Новостная схема занижает", size=15, bold=True, color=TEXT_D)
text(s, Inches(9.15), Inches(3.58), Inches(3.2), Inches(0.7),
     "Отсюда единственный провал важного.", size=13, color=MUTED_D, line=1.45)
panel(s, Inches(8.8), Inches(4.6), Inches(3.8), Inches(1.5))
text(s, Inches(9.15), Inches(4.85), Inches(3.2), Inches(0.3),
     "Живой сбор выключен", size=15, bold=True, color=TEXT_D)
text(s, Inches(9.15), Inches(5.23), Inches(3.2), Inches(0.7),
     "Обработка не успевает за сбором. Показываем срез.", size=13, color=MUTED_D, line=1.45)
foot(s, "docs/hypotheses.md · specs/…/open-questions.md", MUTED_D)

# ============================================================ 08 · Команда
s = slide()
text(s, M, Inches(1.15), Inches(11.7), Inches(0.3), "КОМАНДА",
     size=11, bold=True, color=BRAND, spacing=2.0)
text(s, M, Inches(1.6), Inches(11.5), Inches(0.7), "Кто делал и где посмотреть",
     size=42, bold=True, color=TEXT_D)
team = [("Левочкин Егор", "@veceloe", "продукт, парсинг, фронтенд"),
        ("Головаш Денис", "@denizzzz_ka", "весь слой работы с моделью"),
        ("Артемьев Иван", "@s3drmn", "бэкенд, конвейер, развёртывание")]
for i, (name, tg, role) in enumerate(team):
    y = Inches(3.0) + Inches(1.05) * i
    text(s, M, y, Inches(3.6), Inches(0.34), name, size=21, bold=True, color=TEXT_D)
    text(s, M, y + Inches(0.42), Inches(6.4), Inches(0.3), f"{tg}   ·   {role}",
         size=14, color=MUTED_D)
panel(s, Inches(8.2), Inches(2.9), Inches(4.4), Inches(3.3), PANEL_2)
s.shapes.add_picture(str(ASSETS / "qr-demo.png"), Inches(9.35), Inches(3.2),
                     Inches(2.1), Inches(2.1))
text(s, Inches(8.5), Inches(5.5), Inches(3.8), Inches(0.3), "185.56.162.154",
     size=15, bold=True, color=TEXT_D, align=PP_ALIGN.CENTER)
text(s, Inches(8.5), Inches(5.82), Inches(3.8), Inches(0.3), "лента, досье и дайджест на живых данных",
     size=11.5, color=MUTED_D, align=PP_ALIGN.CENTER)
text(s, M, Inches(6.4), Inches(7.0), Inches(0.3),
     "github.com/veceloe/ai-gpr-center-cifra", size=14, color=MUTED_D)
foot(s, "", MUTED_D)

# ============================================================ 09 · Приложение · оценка
s = slide(CANVAS)
text(s, M, Inches(0.62), Inches(11.7), Inches(0.3), "ПРИЛОЖЕНИЕ · ДЛЯ ВОПРОСОВ",
     size=11, bold=True, color=FAINT, spacing=2.0)
text(s, M, Inches(1.0), Inches(11.7), Inches(0.5),
     "Разбор оценки: шесть критериев и заземление", size=30, bold=True, color=INK)
lead(s, Inches(1.6), "Слева цитата из оригинала под каждым утверждением. Справа балл, "
     "вклад в индекс и обоснование по каждому критерию.", size=13)
shot(s, "shot_breakdown.jpg", Inches(2.0))
foot(s, "FR-024 · FR-081")

# ============================================================ 10 · Приложение · досье
s = slide(CANVAS)
text(s, M, Inches(0.62), Inches(11.7), Inches(0.3), "ПРИЛОЖЕНИЕ · ДЛЯ ВОПРОСОВ",
     size=11, bold=True, color=FAINT, spacing=2.0)
text(s, M, Inches(1.0), Inches(11.7), Inches(0.5),
     "Досье НПА: стадии, хронология, динамика влияния", size=30, bold=True, color=INK)
lead(s, Inches(1.6), "Стадия «Обсуждение» помечена неприменимой, а не непройденной: "
     "российские акты стадии пропускают, и линейная шкала без этого состояния лжёт.", size=13)
shot(s, "shot_act.jpg", Inches(2.0))
foot(s, "FR-032 · FR-035")

count = len(prs.slides._sldIdLst)
assert count == TOTAL, f"слайдов {count}, а в подвале написано {TOTAL}"
prs.save(str(OUT))
print(f"сохранено: {OUT.name}, слайдов: {count}, {OUT.stat().st_size // 1024} КБ")
