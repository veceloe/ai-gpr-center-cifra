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


def slide(bg=CANVAS):
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


# ============================================================ 01 · Титул
s = slide(BRAND)
text(s, M, Inches(2.0), Inches(11.7), Inches(0.3), "ITMO AI Product Hack · кейс ООО «Цифра»",
     size=12, bold=True, color=SURFACE, caps=True, spacing=1.6)
text(s, M, Inches(2.6), Inches(11.7), Inches(1.7), "Интеллектуальный центр\nPR/GR-мониторинга",
     size=50, bold=True, color=SURFACE, line=1.06)
text(s, M, Inches(4.72), Inches(8.4), Inches(0.5),
     "Лента, отсортированная по влиянию на компанию, а не по дате публикации",
     size=17, color=RGBColor(0xE4, 0xF5, 0xDE))
text(s, M, Inches(5.9), Inches(8.4), Inches(0.4),
     "Левочкин Егор · Головаш Денис · Артемьев Иван",
     size=13, color=RGBColor(0xD3, 0xEF, 0xC9))
s.shapes.add_picture(str(ASSETS / "qr-demo.png"), W - M - Inches(1.55), Inches(4.5),
                     Inches(1.55), Inches(1.55))
text(s, W - M - Inches(3.0), Inches(6.18), Inches(3.0), Inches(0.3), "185.56.162.154",
     size=11.5, color=SURFACE, align=PP_ALIGN.RIGHT)

# ============================================================ 02 · Проблема
# Ни карточек, ни списка: одно утверждение и одно число рядом.
s = slide()
bar(s, M, Inches(1.6), Inches(2.5))
text(s, M + Inches(0.42), Inches(1.55), Inches(7.4), Inches(2.6),
     "Три-четыре часа в день\nуходит на то, чтобы\nпрочитать всё вручную",
     size=40, bold=True, line=1.14)
text(s, M + Inches(0.42), Inches(4.55), Inches(7.0), Inches(1.2),
     "И дело не в объёме. Агрегаторы отвечают на вопрос «что интересного произошло». "
     "GR-специалисту нужен другой ответ: что из этого касается нашей компании.",
     size=15, color=MUTED, line=1.45)
big(s, Inches(9.1), Inches(1.62), Inches(3.5), "630", size=88, color=BRAND_DARK)
label(s, Inches(9.1), Inches(3.35), Inches(3.5), "часов в год на специалиста")
text(s, Inches(9.1), Inches(3.75), Inches(3.4), Inches(1.0),
     "Столько уходит на ручной мониторинг. Целевой ориентир заказчика — "
     "разбор суточной повестки за 10–15 минут.", size=13, color=MUTED, line=1.45)
foot(s, "docs/business-case.md · расчёт согласован с заказчиком")

# ============================================================ 03 · Решение
s = slide()
bar(s, M, Inches(1.5), Inches(1.5))
text(s, M + Inches(0.42), Inches(1.45), Inches(11.0), Inches(1.6),
     "Модель выставляет баллы.\nИндекс считает код.", size=42, bold=True, line=1.14)

# Схема границы: что отдаёт модель и что из этого делает код.
box(s, M, Inches(3.5), Inches(4.6), Inches(1.85), SURFACE, BRAND, Pt(1.5))
label(s, M + Inches(0.32), Inches(3.75), Inches(4.0), "Модель", BRAND_DARK)
text(s, M + Inches(0.32), Inches(4.1), Inches(4.0), Inches(1.1),
     "К1 · 3    К2 · 2    К3 · 3\nК4 · 0    К5 · 0    К6 · 3\n\nи обоснование к каждому баллу",
     size=15, color=INK, line=1.5)
arrow(s, M + Inches(4.85), Inches(4.34), Inches(0.85), BRAND_DARK)
box(s, M + Inches(6.0), Inches(3.5), Inches(4.9), Inches(1.85), INK, INK, Pt(1.5))
label(s, M + Inches(6.32), Inches(3.75), Inches(4.2), "Код", RGBColor(0x9A, 0xE0, 0x88))
text(s, M + Inches(6.32), Inches(4.08), Inches(4.3), Inches(1.2),
     [("индекс 65,0", {"bold": True, "color": SURFACE, "size": 17}),
      ("  →  ", {"color": FAINT, "size": 17}),
      ("категория «Среднее»", {"bold": True, "color": SURFACE, "size": 17}),
      ("\nфлаг эскалации поднимает до «Высокого»",
       {"color": RGBColor(0xC8, 0xD4, 0xC8), "size": 13})], line=1.5)
text(s, M, Inches(5.75), Inches(11.0), Inches(0.7),
     [("В контракте ответа модели полей «индекс» и «категория» нет вовсе. ",
       {"bold": True, "color": INK}),
      ("Она физически не может их вернуть — поэтому оценку можно проверить и поправить.",
       {"color": MUTED})], size=14.5, line=1.45)
foot(s, "ADR-0003 · backend/config/scoring.yaml")

# ============================================================ 04 · Лента
s = slide()
label(s, M, Inches(0.62), Inches(6.0), "Продукт", BRAND_DARK)
headline(s, "Сверху то, что важнее для компании, а не то, что свежее", size=28)
lead(s, Inches(1.52),
     "Цветом отмечены только два верхних уровня серьёзности: сортировка уже сделала главную работу.",
     size=12.5)
shot(s, "shot_feed.jpg")
foot(s, "185.56.162.154")

# ============================================================ 05 · Разбор оценки
s = slide()
label(s, M, Inches(0.62), Inches(6.0), "Продукт", BRAND_DARK)
headline(s, "Оценку видно целиком — и её можно поправить", size=28)
lead(s, Inches(1.52),
     "Слева цитата из оригинала под каждым утверждением. Справа шесть критериев: балл, "
     "вклад в индекс, обоснование. Меняете балл — индекс пересчитывается сразу.", size=12.5)
shot(s, "shot_breakdown.jpg")
foot(s, "FR-024 · FR-081")

# ============================================================ 06 · Досье
s = slide()
label(s, M, Inches(0.62), Inches(6.0), "Продукт", BRAND_DARK)
headline(s, "НПА живёт отдельно: стадии, хронология, динамика влияния", size=28)
lead(s, Inches(1.52),
     "Стадия «Обсуждение» помечена неприменимой, а не непройденной: российские акты стадии "
     "пропускают, и линейная шкала без этого состояния лжёт.", size=12.5)
shot(s, "shot_act.jpg")
foot(s, "FR-032 · FR-035")

# ============================================================ 07 · Сколько стоит
s = slide()
bar(s, M, Inches(1.5), Inches(0.9))
text(s, M + Inches(0.42), Inches(1.45), Inches(11.0), Inches(1.0),
     "Обработка потока стоит дешевле,\nчем один пропущенный документ", size=34, bold=True, line=1.16)

# Полосы в честном масштабе: 2 100 против 500 000 — это 0,42 %, и малая полоса
# почти не видна. Это и есть сообщение, поэтому она не увеличена «для наглядности».
SCALE = Inches(11.0) / 500000
text(s, M, Inches(3.5), Inches(6.0), Inches(0.3), "Год работы модели на потоке 150 материалов в сутки",
     size=13, color=MUTED)
r = s.shapes.add_shape(1, M, Inches(3.85), max(int(2100 * SCALE), Inches(0.04)), Inches(0.34))
r.fill.solid(); r.fill.fore_color.rgb = BRAND
r.line.fill.background(); r.shadow.inherit = False
text(s, M + Inches(0.18), Inches(3.83), Inches(4.0), Inches(0.35), "≈ 2 100 ₽",
     size=17, bold=True, color=BRAND_DARK)

text(s, M, Inches(4.75), Inches(8.0), Inches(0.3),
     "Один штраф по ФЗ № 295-ФЗ для операторов цифровых платформ, верхняя граница",
     size=13, color=MUTED)
r = s.shapes.add_shape(1, M, Inches(5.1), Inches(11.0), Inches(0.34))
r.fill.solid(); r.fill.fore_color.rgb = RISK
r.line.fill.background(); r.shadow.inherit = False
text(s, M + Inches(0.18), Inches(5.08), Inches(4.0), Inches(0.35), "500 000 ₽",
     size=17, bold=True, color=SURFACE)

text(s, M, Inches(5.75), Inches(11.7), Inches(0.7),
     [("Полосы в одном масштабе. ", {"bold": True, "color": INK}),
      ("Верхняя — годовая стоимость обработки: четыре копейки за материал. "
       "Одного пропущенного документа хватает, чтобы перекрыть двести лет её работы.",
       {"color": MUTED})], size=14.5, line=1.45)
text(s, M, Inches(6.55), Inches(11.7), Inches(0.3),
     "Пересчитано по курсу ЦБ на 05.09.2026 — 86,59 ₽ за доллар.",
     size=11.5, color=FAINT)
foot(s, "docs/business-case.md · замер стоимости на реальном материале")

# ============================================================ 08 · Насколько точно
s = slide()
bar(s, M, Inches(1.5), Inches(0.62))
text(s, M + Inches(0.42), Inches(1.45), Inches(11.0), Inches(0.7),
     "Проверено на реестре самого заказчика", size=34, bold=True)
text(s, M + Inches(0.42), Inches(2.15), Inches(10.6), Inches(0.4),
     "Сорок две карточки, баллы в них проставлены человеком. Одна клетка — одна карточка.",
     size=14, color=MUTED)

waffle(s, M, Inches(2.85), [(BRAND, 18), (MID_GREEN, 20), (RISK, 4)])
legend(s, M, Inches(4.7), [
    (BRAND, "18 — категория совпала точно"),
    (MID_GREEN, "20 — разошлась на одну ступень"),
    (RISK, "4 — разошлась сильнее"),
])

big(s, Inches(8.8), Inches(2.8), Inches(3.8), "42 / 42", size=46, color=BRAND_DARK)
label(s, Inches(8.8), Inches(3.72), Inches(3.8), "формула сходится точно")
text(s, Inches(8.8), Inches(4.08), Inches(3.7), Inches(0.9),
     "Отдельная проверка: получив экспертные баллы, код выдаёт тот же индекс "
     "и ту же категорию, что в Excel заказчика. Включая эскалацию.",
     size=13, color=MUTED, line=1.45)

text(s, M, Inches(5.5), Inches(11.7), Inches(0.9),
     [("Провалов важного в нижние категории: один при цели ноль. ",
       {"bold": True, "color": INK}),
      ("Это ключевое условие заказчика, и оно важнее общей точности: пропущенное "
       "регуляторное изменение стоит дороже десятка лишних материалов в ленте. "
       "Заземление отдельно: 8,2 % утверждений отбраковала вторая ступень — цитата "
       "в оригинале есть, но утверждения не подтверждает.", {"color": MUTED})],
     size=14, line=1.45)
foot(s, "evals/results.md · python -m src.cli evaluate · verify-formula")

# ============================================================ 09 · Границы
s = slide()
label(s, M, Inches(0.62), Inches(6.0), "Честно", RISK)
text(s, M, Inches(1.0), Inches(11.7), Inches(0.8), "Чего мы измерить не смогли",
     size=34, bold=True)
items = [
    ("Точность фильтрации", RISK,
     "В реестре заказчика нет ни одной нерелевантной карточки — сравнивать не с чем. "
     "Заявленные восемьдесят процентов на таких данных неизмеримы в принципе. "
     "Нужен размеченный набор с отрицательными примерами."),
    ("Провалы важного: один при цели ноль", RISK,
     "Единственный провал — следствие того, что новостная схема систематически занижает "
     "оценку на материалах с непрямой связью с бизнесом."),
    ("Живой сбор на стенде выключен", MUTED,
     "Обработка не успевает за сбором, и необработанные материалы попадают в ленту "
     "пустыми карточками. Показываем подготовленный срез."),
]
for i, (t, c, d) in enumerate(items):
    y = Inches(2.3) + Inches(1.42) * i
    bar(s, M, y, Inches(1.05), c)
    text(s, M + Inches(0.42), y - Inches(0.04), Inches(11.0), Inches(0.34), t,
         size=19, bold=True)
    text(s, M + Inches(0.42), y + Inches(0.42), Inches(10.6), Inches(0.7), d,
         size=13.5, color=MUTED, line=1.45)
foot(s, "docs/hypotheses.md · specs/…/open-questions.md")

# ============================================================ 10 · Команда
s = slide(BRAND)
label(s, M, Inches(0.62), Inches(6.0), "Команда", RGBColor(0xD3, 0xEF, 0xC9))
text(s, M, Inches(1.0), Inches(11.7), Inches(0.8), "Кто делал и где посмотреть",
     size=34, bold=True, color=SURFACE)
team = [("Левочкин Егор", "@veceloe", "продукт, парсинг, фронтенд"),
        ("Головаш Денис", "@denizzzz_ka", "весь слой работы с моделью"),
        ("Артемьев Иван", "@s3drmn", "бэкенд, конвейер, развёртывание")]
for i, (name, tg, role) in enumerate(team):
    y = Inches(2.5) + Inches(1.0) * i
    text(s, M, y, Inches(3.4), Inches(0.34), name, size=20, bold=True, color=SURFACE)
    text(s, M, y + Inches(0.42), Inches(6.0), Inches(0.3),
         f"{tg}  ·  {role}", size=13.5, color=RGBColor(0xD3, 0xEF, 0xC9))
s.shapes.add_picture(str(ASSETS / "qr-demo.png"), W - M - Inches(2.1), Inches(2.5),
                     Inches(2.1), Inches(2.1))
text(s, W - M - Inches(3.4), Inches(4.72), Inches(3.4), Inches(0.3), "185.56.162.154",
     size=14, bold=True, color=SURFACE, align=PP_ALIGN.RIGHT)
text(s, M, Inches(6.0), Inches(11.7), Inches(0.4),
     "github.com/veceloe/ai-gpr-center-cifra", size=14, color=RGBColor(0xE4, 0xF5, 0xDE))
foot(s, color=RGBColor(0xD3, 0xEF, 0xC9))

count = len(prs.slides._sldIdLst)
assert count == TOTAL, f"слайдов {count}, а в подвале написано {TOTAL}"
prs.save(str(OUT))
print(f"сохранено: {OUT.name}, слайдов: {count}, {OUT.stat().st_size // 1024} КБ")
