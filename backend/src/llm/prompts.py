"""Промпты с версиями — FR-019.

Версия сохраняется в Assessment.prompt_version: без неё невозможно понять, к какой
формулировке относится измеренное качество. Менять текст промпта, не подняв версию,
запрещено — иначе цифры в отчёте перестают что-либо значить.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date

from src.models import AssessmentScheme
from src.scoring.config import ScoringConfig


@dataclass(frozen=True)
class Prompt:
    id: str
    system: str


SUMMARIZE = Prompt(
    id="summarize/v1",
    system="""Ты аналитик, готовящий выжимку материала для PR- и GR-специалистов.

Верни 3-5 утверждений о сути материала. К КАЖДОМУ утверждению приложи дословную цитату
из исходного текста, которая его подтверждает.

Жёсткие правила:
- quote — фрагмент исходного текста СИМВОЛ В СИМВОЛ, без перефразирования, без сокращений,
  без исправления опечаток. Он будет проверен автоматическим поиском по тексту.
- Если утверждение нельзя подтвердить дословной цитатой — не включай его вообще.
- Не додумывай последствия, которых нет в тексте. Не обобщай до того, чего текст не говорит.
- Утверждения — на русском языке, по одному предложению.

Дополнительно извлеки сущности: кто (участники, органы, компании), что (суть события),
когда (даты, сроки, периоды), последствия (что меняется для участников рынка).

Отвечай ТОЛЬКО валидным JSON вида:
{"claims": [{"statement": "...", "quote": "..."}],
 "entities": {"who": ["..."], "what": "...", "when": "...", "consequences": "..."}}""",
)

VERIFY_CLAIMS = Prompt(
    id="verify_claims/v1",
    system="""Ты проверяешь, следует ли утверждение из приведённой цитаты.

Тебе дан список пар «утверждение — цитата». Для каждой пары ответь, подтверждает ли
цитата утверждение ЦЕЛИКОМ.

Правила:
- entailed = true только если всё содержание утверждения выводится из цитаты.
- Частично подтверждённое утверждение — entailed = false.
- Отсутствие противоречия НЕ является подтверждением. Если утверждение правдоподобно,
  но в цитате этого не сказано — entailed = false.
- Не опирайся на общие знания о мире. Только на текст цитаты.
- В reason коротко укажи, чего именно не хватает, если entailed = false.

Отвечай ТОЛЬКО валидным JSON вида:
{"verdicts": [{"index": 0, "entailed": true, "reason": "..."}]}""",
)

CLASSIFY = Prompt(
    id="classify/v1",
    system="""Ты определяешь тему материала отраслевого мониторинга.

topic — одно значение:
- "regulatory" — регулирование, законодательство, требования органов власти
- "reputation" — упоминания компании, репутационные сюжеты
- "competitors" — действия и позиции конкурентов
- "trends" — отраслевые тренды, рыночные данные, технологии

Тип материала уже задан источником во входе и не подлежит переопределению.
act_identifier заполняй ТОЛЬКО для типа "act": номер и вид документа так, как он
назван в тексте, например "Законопроект № 1215252-8" или "ФЗ № 243-ФЗ". Если номера
в тексте нет — верни null.

Отвечай ТОЛЬКО валидным JSON вида:
{"topic": "regulatory", "act_identifier": "..."}""",
)

DEDUP_PAIR = Prompt(
    id="dedup_pair/v1",
    system="""Ты определяешь отношение между двумя материалами об одной теме.

relation:
- "same_fact" — оба сообщают ОДИН И ТОТ ЖЕ факт без собственной оценки, различаясь
  только формулировками. Такие материалы можно показать одной карточкой.
- "different_positions" — материалы содержат различающиеся позиции, оценки или мнения
  по одной теме. Объединять их нельзя: разница позиций и есть ценность.
- "unrelated" — материалы о разных событиях.

Отвечай ТОЛЬКО валидным JSON вида:
{"relation": "same_fact", "reason": "..."}""",
)


def _scale_block(config: ScoringConfig, scheme: AssessmentScheme) -> str:
    """Шкалы критериев подставляются из config/scoring.yaml, а не дублируются в промпте.

    Так шкала остаётся в одном месте: правка методики автоматически доезжает до модели.
    """
    scheme_cfg = config.for_scheme(scheme)
    lines: list[str] = []
    for criterion in scheme_cfg.criteria:
        options = " · ".join(f"{score} — {text}" for score, text in sorted(criterion.scale.items()))
        lines.append(f"{criterion.code}. {criterion.name}\n   {options}")
    return "\n".join(lines)


def _flags_block(config: ScoringConfig) -> str:
    return "\n".join(f"- {flag.text}" for flag in config.escalation_flags)


def build_score_prompt(
    scheme: AssessmentScheme,
    config: ScoringConfig,
    profile_context: str,
    today: date,
) -> Prompt:
    """Собирает системный промпт оценки: шкалы из конфига + профиль компании + дата.

    Дата передаётся явно: критерий актуальности Н1 зависит от «сейчас», и без явной
    даты оценка плывёт между прогонами, потому что модель опирается на своё
    представление о текущем моменте.
    """
    scheme_cfg = config.for_scheme(scheme)
    codes = ", ".join(scheme_cfg.codes)
    is_npa = scheme is AssessmentScheme.NPA_K1_K6
    prompt_id = f"score_{'npa' if is_npa else 'news'}/v1"

    flags_section = ""
    if is_npa:
        flags_section = f"""
Флаги эскалации. Если материал соответствует одному из условий ниже, добавь его
формулировку в escalation_candidates ДОСЛОВНО. Свои формулировки не придумывай —
они будут отброшены. Если ни одно условие не выполнено, верни пустой список.
{_flags_block(config)}
"""

    system = f"""Ты оцениваешь материал отраслевого мониторинга с точки зрения конкретной компании.

Выставь балл от 0 до 3 по каждому критерию: {codes}. Только целые числа.

Шкалы критериев — используй их буквально, не изобретай промежуточных значений:
{_scale_block(config, scheme)}

К каждому баллу дай обоснование в 1-2 предложениях. Обоснование обязано ссылаться
на конкретный факт из материала И на конкретный пункт профиля компании ниже.
Формулировки вида «в целом релевантно» недопустимы.

Профиль компании, с точки зрения которой оцениваешь:
{profile_context}

Сегодняшняя дата: {today.isoformat()}. Используй её для оценки сроков и актуальности.
{flags_section}
Не определяй итоговую категорию, приоритет и не считай индекс — это делает не ты.
Твоя задача только баллы и обоснования.

Отвечай ТОЛЬКО валидным JSON вида:
{{"scores": {{"{scheme_cfg.codes[0]}": 0}},
 "rationales": {{"{scheme_cfg.codes[0]}": "..."}},
 "escalation_candidates": []}}"""

    return Prompt(id=prompt_id, system=system)


def summarize_user_message(title: str, text: str, source_title: str) -> str:
    return f"Источник: {source_title}\nЗаголовок: {title}\n\nТекст материала:\n{text}"


def verify_claims_user_message(pairs: list[tuple[str, str]]) -> str:
    payload = [{"index": i, "statement": s, "quote": q} for i, (s, q) in enumerate(pairs)]
    return json.dumps(payload, ensure_ascii=False, indent=1)


def classify_user_message(title: str, text: str, url: str, item_type: str) -> str:
    return (
        f"Тип материала (задан источником): {item_type}\n"
        f"URL: {url}\nЗаголовок: {title}\n\nТекст:\n{text[:4000]}"
    )


def score_user_message(title: str, summary: str, text: str, published_at: str) -> str:
    return (
        f"Заголовок: {title}\n"
        f"Дата публикации: {published_at}\n\n"
        f"Краткое содержание:\n{summary}\n\n"
        f"Исходный текст:\n{text[:6000]}"
    )


def dedup_user_message(a_title: str, a_summary: str, b_title: str, b_summary: str) -> str:
    return (
        f"Материал A\nЗаголовок: {a_title}\nСодержание: {a_summary}\n\n"
        f"Материал B\nЗаголовок: {b_title}\nСодержание: {b_summary}"
    )
