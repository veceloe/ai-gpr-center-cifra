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


# ============================================================ 01 · Титул
s = slide(BRAND)
text(s, M, Inches(2.15), Inches(11.7), Inches(0.3), "ITMO AI Product Hack · кейс ООО «Цифра»",
     size=12, bold=True, color=SURFACE, caps=True, spacing=1.6)
text(s, M, Inches(2.75), Inches(11.7), Inches(1.6), "Интеллектуальный центр\nPR/GR-мониторинга",
     size=48, bold=True, color=SURFACE, line=1.08)
text(s, M, Inches(4.75), Inches(9.0), Inches(0.5),
     "Лента, отсортированная по влиянию на компанию, а не по дате публикации",
     size=16, color=RGBColor(0xE4, 0xF5, 0xDE))
text(s, M, Inches(5.75), Inches(9.0), Inches(0.6),
     "Левочкин Егор · Головаш Денис · Артемьев Иван",
     size=13, color=RGBColor(0xD3, 0xEF, 0xC9))
s.shapes.add_picture(str(ASSETS / "qr-demo.png"), W - M - Inches(1.5), Inches(4.6),
                     Inches(1.5), Inches(1.5))
text(s, W - M - Inches(2.6), Inches(6.22), Inches(2.6), Inches(0.3), "185.56.162.154",
     size=11, color=SURFACE, align=PP_ALIGN.RIGHT)

# ============================================================ 02 · Проблема
s = slide()
eyebrow(s, "Проблема")
headline(s, "Специалист тратит 3–4 часа в день,\nчтобы прочитать всё вручную", size=34)
lead(s, Inches(2.55),
     "И дело не в объёме. Агрегаторы отвечают на вопрос «что интересного произошло». "
     "GR-специалисту нужен другой ответ: что из этого касается нашей компании.",
     size=16, width=Inches(10.4))
for i, (big, cap) in enumerate([
    ("3–4 ч", "в день на ручной мониторинг лент, порталов и телеграм-каналов"),
    ("0", "формализованных правил: решения строятся на опыте, два эксперта дают разные ответы"),
    ("1", "пропущенной поправки достаточно, чтобы перестраивать продукт"),
]):
    x = M + Inches(3.95) * i
    text(s, x, Inches(4.35), Inches(3.6), Inches(0.8), big, size=40, bold=True,
         color=BRAND_DARK, line=1.0)
    text(s, x, Inches(5.25), Inches(3.5), Inches(1.2), cap, size=12.5, color=MUTED, line=1.4)
foot(s, "Источник: созвон с заказчиком 02.09.2026, Q&A и описание кейса")

# ============================================================ 03 · Решение
s = slide()
eyebrow(s, "Решение")
headline(s, "Модель выставляет баллы.\nИндекс считает код.", size=38)
lead(s, Inches(2.9),
     "В контракте ответа модели полей «индекс» и «категория» нет вовсе — она физически "
     "не может их вернуть. Поэтому оценку можно проверить, объяснить и поправить.",
     size=16, width=Inches(10.4))
text(s, M, Inches(4.3), Inches(11.7), Inches(0.9),
     "ИВ  =  ( Σ балл × вес )  ÷  3  ×  100", size=30, bold=True, color=INK)
lead(s, Inches(5.3),
     "Веса и пороги — методика заказчика, она у него уже была в Excel. Мы её не придумывали "
     "и менять можем только с его согласия.", width=Inches(10.4))
foot(s, "ADR-0003 · backend/config/scoring.yaml")

# ============================================================ 04 · Лента
s = slide()
eyebrow(s, "Продукт")
headline(s, "Сверху то, что важнее для компании, а не то, что свежее", size=28)
lead(s, Inches(1.52),
     "Цветом отмечены только два верхних уровня серьёзности: сортировка уже сделала главную работу.",
     size=12.5)
shot(s, "shot_feed.jpg")
foot(s, "185.56.162.154")

# ============================================================ 05 · Разбор оценки
s = slide()
eyebrow(s, "Продукт")
headline(s, "Оценку видно целиком — и её можно поправить", size=28)
lead(s, Inches(1.52),
     "Слева цитата из оригинала под каждым утверждением. Справа шесть критериев: балл, "
     "вклад в индекс, обоснование. Меняете балл — индекс пересчитывается сразу.",
     size=12.5)
shot(s, "shot_breakdown.jpg")
foot(s, "FR-024 · FR-081")

# ============================================================ 06 · Досье
s = slide()
eyebrow(s, "Продукт")
headline(s, "НПА живёт отдельно: стадии, хронология, динамика влияния", size=28)
lead(s, Inches(1.52),
     "Стадия «Обсуждение» помечена неприменимой, а не непройденной: российские акты стадии "
     "пропускают, и линейная шкала без этого состояния лжёт.", size=12.5)
shot(s, "shot_act.jpg")
foot(s, "FR-032 · FR-035")

# ============================================================ 07 · Метрики
s = slide()
eyebrow(s, "Измерено")
headline(s, "Время, деньги, качество", size=34)
for i, (big, unit, cap) in enumerate([
    ("12,7", "секунды", "медиана обработки одного материала при целевых 10–15 с"),
    ("$0,00044", "", "полный цикл на материал. Поток 150 в сутки — около $2 в месяц"),
    ("37 / 42", "", "карточки эталона заказчика: категория совпала или разошлась на ступень"),
]):
    x = M + Inches(3.95) * i
    rect = s.shapes.add_shape(1, x, Inches(2.6), Inches(3.6), Inches(1.95))
    rect.fill.solid()
    rect.fill.fore_color.rgb = SURFACE
    rect.line.color.rgb = LINE
    rect.line.width = Pt(0.75)
    rect.shadow.inherit = False
    text(s, x + Inches(0.32), Inches(2.88), Inches(3.0), Inches(0.7), big,
         size=36, bold=True, color=BRAND_DARK, line=1.0)
    if unit:
        text(s, x + Inches(0.32), Inches(3.6), Inches(3.0), Inches(0.28), unit,
             size=12, color=MUTED)
    text(s, x + Inches(0.32), Inches(3.92), Inches(3.0), Inches(0.75), cap,
         size=12.5, color=MUTED, line=1.4)
text(s, M, Inches(5.1), Inches(11.7), Inches(0.9),
     [("Заземление: на 820 утверждениях 8,2 % поймала вторая ступень. ",
       {"bold": True, "color": INK, "size": 15}),
      ("Цитата дословно есть в оригинале, но утверждения не подтверждает — проверка "
       "подстрокой их пропустила бы. У коммерческих правовых ИИ этот класс ошибок даёт 17–33 %.",
       {"color": MUTED, "size": 15})], line=1.4)
foot(s, "evals/results.md · python -m src.cli evaluate")

# ============================================================ 08 · Критерии
s = slide()
eyebrow(s, "Методика заказчика")
headline(s, "Две шкалы: НПА и новости оцениваются по-разному", size=28)
cols = [
    ("НПА · индекс влияния", [
        ("К1", "Применимость к деятельности", "0,25"), ("К2", "Юридическая сила", "0,15"),
        ("К3", "Финансовое воздействие", "0,20"), ("К4", "Сложность адаптации", "0,15"),
        ("К5", "Юридический и репутационный риск", "0,15"), ("К6", "Срочность", "0,10")]),
    ("Новости · индекс актуальности", [
        ("Н1", "Актуальность события", "0,30"), ("Н2", "Релевантность бизнесу", "0,30"),
        ("Н3", "Масштаб для отрасли", "0,20"), ("Н4", "Динамика развития", "0,20")]),
]
for i, (cap, rows) in enumerate(cols):
    x = M + Inches(6.05) * i
    text(s, x, Inches(2.25), Inches(5.5), Inches(0.25), cap,
         size=10.5, bold=True, color=BRAND_DARK, caps=True, spacing=1.3)
    for j, (code, name, weight) in enumerate(rows):
        y = Inches(2.7) + Inches(0.46) * j
        text(s, x, y, Inches(0.5), Inches(0.3), code, size=13, bold=True, color=INK)
        text(s, x + Inches(0.62), y, Inches(3.6), Inches(0.3), name, size=13, color=MUTED)
        text(s, x + Inches(4.5), y, Inches(0.8), Inches(0.3), weight, size=13,
             bold=True, color=INK, align=PP_ALIGN.RIGHT)
text(s, M, Inches(5.75), Inches(11.7), Inches(0.7),
     [("Каждый критерий — целое от 0 до 3. ", {"bold": True, "color": INK}),
      ("Флаг эскалации из закрытого перечня поднимает итоговую категорию на ступень; "
       "формулировку не из перечня код отбрасывает.", {"color": MUTED})], size=14, line=1.4)
foot(s, "docs/scoring-methodology.md")

# ============================================================ 09 · Границы
s = slide()
eyebrow(s, "Честно", RISK)
headline(s, "Что мы измерить не смогли", size=34)
items = [
    ("Точность фильтрации — не измерена",
     "В реестре заказчика нет ни одной нерелевантной карточки: базовая ставка 100 %. "
     "Заявленные 80 % на таких данных неизмеримы в принципе. Нужен размеченный набор "
     "с отрицательными примерами — открытый вопрос к заказчику."),
    ("Провалы критичного: 1 при цели 0",
     "Единственный провал — следствие того, что новостная схема систематически занижает "
     "оценку на материалах с непрямой связью."),
    ("Автосбор на стенде выключен",
     "Обработка не успевает за сбором, и необработанные материалы попадают в ленту "
     "пустыми карточками. Показываем подготовленный срез."),
]
for i, (t, d) in enumerate(items):
    y = Inches(2.55) + Inches(1.35) * i
    text(s, M, y, Inches(11.5), Inches(0.32), t, size=17, bold=True, color=INK)
    text(s, M, y + Inches(0.42), Inches(11.3), Inches(0.8), d, size=13, color=MUTED, line=1.4)
foot(s, "docs/hypotheses.md · evals/results.md")

# ============================================================ 10 · Команда
s = slide(BRAND)
eyebrow(s, "Команда", RGBColor(0xD3, 0xEF, 0xC9))
headline(s, "Кто делал и где посмотреть", size=34, color=SURFACE)
team = [("Левочкин Егор", "@veceloe", "продукт, парсинг, фронтенд"),
        ("Головаш Денис", "@denizzzz_ka", "весь слой работы с моделью"),
        ("Артемьев Иван", "@s3drmn", "бэкенд, конвейер, развёртывание")]
for i, (name, tg, role) in enumerate(team):
    y = Inches(2.65) + Inches(0.95) * i
    text(s, M, y, Inches(3.4), Inches(0.32), name, size=19, bold=True, color=SURFACE)
    text(s, M + Inches(3.5), y + Inches(0.05), Inches(2.4), Inches(0.3), tg,
         size=14, color=RGBColor(0xD3, 0xEF, 0xC9))
    text(s, M + Inches(5.9), y + Inches(0.05), Inches(4.4), Inches(0.3), role,
         size=14, color=RGBColor(0xE4, 0xF5, 0xDE))
s.shapes.add_picture(str(ASSETS / "qr-demo.png"), W - M - Inches(2.0), Inches(2.6),
                     Inches(2.0), Inches(2.0))
text(s, W - M - Inches(3.2), Inches(4.72), Inches(3.2), Inches(0.3), "185.56.162.154",
     size=13, bold=True, color=SURFACE, align=PP_ALIGN.RIGHT)
text(s, M, Inches(6.05), Inches(11.7), Inches(0.4),
     "github.com/veceloe/ai-gpr-center-cifra", size=14, color=RGBColor(0xE4, 0xF5, 0xDE))
foot(s, color=RGBColor(0xD3, 0xEF, 0xC9))

count = len(prs.slides._sldIdLst)
assert count == TOTAL, f"слайдов {count}, а в подвале написано {TOTAL}"
prs.save(str(OUT))
print(f"сохранено: {OUT.name}, слайдов: {count}, {OUT.stat().st_size // 1024} КБ")
