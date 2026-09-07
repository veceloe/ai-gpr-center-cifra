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
text(s, M + Inches(0.42), Inches(3.35), Inches(10.4), Inches(0.9),
     "В контракте ответа модели полей «индекс» и «категория» нет вовсе — она физически "
     "не может их вернуть. Поэтому оценку можно проверить, объяснить и поправить.",
     size=15.5, color=MUTED, line=1.45)
text(s, M + Inches(0.42), Inches(4.72), Inches(11.0), Inches(0.9),
     "ИВ  =  ( Σ балл × вес )  ÷  3  ×  100", size=32, bold=True, color=BRAND_DARK)
text(s, M + Inches(0.42), Inches(5.75), Inches(10.4), Inches(0.7),
     "Веса и пороги — методика заказчика, она у него уже была в Excel. Мы её не придумывали "
     "и менять можем только с его согласия.", size=13.5, color=MUTED, line=1.45)
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
# Два числа в одном масштабе, без карточек и без диаграмм: контраст говорит сам.
s = slide()
bar(s, M, Inches(1.5), Inches(0.9))
text(s, M + Inches(0.42), Inches(1.45), Inches(11.0), Inches(1.0),
     "Обработка потока стоит дешевле,\nчем один пропущенный документ", size=34, bold=True, line=1.16)
bar(s, M, Inches(3.32), Inches(1.0))
big(s, M + Inches(0.42), Inches(3.3), Inches(5.0), "≈ 2 100 ₽", size=54, color=BRAND_DARK)
label(s, M + Inches(0.42), Inches(4.35), Inches(5.0), "в год")
text(s, M + Inches(0.42), Inches(4.72), Inches(4.8), Inches(1.0),
     "Полная обработка потока в 150 материалов в сутки: саммари, заземление, "
     "классификация и оценка. Четыре копейки за материал.", size=13.5, color=MUTED, line=1.45)
bar(s, Inches(7.1), Inches(3.32), Inches(1.0), RISK)
big(s, Inches(7.52), Inches(3.3), Inches(5.2), "500 000 ₽", size=54, color=INK)
label(s, Inches(7.52), Inches(4.35), Inches(5.2), "один штраф")
text(s, Inches(7.52), Inches(4.72), Inches(5.0), Inches(1.0),
     "Верхняя граница по ФЗ № 295-ФЗ для операторов цифровых платформ. "
     "Одного пропуска хватает, чтобы перекрыть двести лет работы модели.",
     size=13.5, color=MUTED, line=1.45)
text(s, M, Inches(6.25), Inches(11.7), Inches(0.4),
     "Пересчитано по курсу ЦБ на 05.09.2026 — 86,59 ₽ за доллар.",
     size=11.5, color=FAINT)
foot(s, "docs/business-case.md · замер стоимости на реальном материале")

# ============================================================ 08 · Насколько точно
s = slide()
bar(s, M, Inches(1.5), Inches(0.62))
text(s, M + Inches(0.42), Inches(1.45), Inches(11.0), Inches(0.7),
     "Проверено на реестре самого заказчика", size=34, bold=True)
big(s, M, Inches(2.75), Inches(4.2), "37 / 42", size=56, color=BRAND_DARK)
label(s, M, Inches(3.8), Inches(4.6), "категория совпала или рядом")
text(s, M, Inches(4.18), Inches(4.4), Inches(1.2),
     "Из сорока двух карточек с проставленными вручную баллами. Формула воспроизводит "
     "методику точно: индекс и категория сошлись на всех сорока двух.",
     size=13.5, color=MUTED, line=1.45)
big(s, Inches(5.9), Inches(2.75), Inches(3.0), "8,2 %", size=56, color=BRAND_DARK)
label(s, Inches(5.9), Inches(3.8), Inches(3.4), "поймала вторая ступень")
text(s, Inches(5.9), Inches(4.18), Inches(3.2), Inches(1.4),
     "Утверждений, где цитата дословно есть в оригинале, но утверждения не подтверждает. "
     "Проверка подстрокой их пропустила бы. У коммерческих правовых ИИ этот класс даёт 17–33 %.",
     size=13.5, color=MUTED, line=1.45)
big(s, Inches(9.9), Inches(2.75), Inches(2.8), "12,7", size=56, color=BRAND_DARK)
label(s, Inches(9.9), Inches(3.8), Inches(2.8), "секунды на материал")
text(s, Inches(9.9), Inches(4.18), Inches(2.7), Inches(1.2),
     "Медиана полной обработки при целевых десяти-пятнадцати секундах.",
     size=13.5, color=MUTED, line=1.45)
text(s, M, Inches(6.05), Inches(11.7), Inches(0.5),
     [("Ведущая метрика — не общая точность. ", {"bold": True, "color": INK}),
      ("Заказчик назвал ключевым условием отсутствие провалов важного в нижние категории: "
       "пропущенное регуляторное изменение стоит дороже десятка лишних материалов в ленте.",
       {"color": MUTED})], size=13.5, line=1.45)
foot(s, "evals/results.md · python -m src.cli evaluate")

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
