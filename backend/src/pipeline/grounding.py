"""Заземление саммари на оригинал — принцип III конституции, FR-012, FR-090…FR-092.

Две независимые ступени (ADR-0007):

  1. ВХОЖДЕНИЕ — детерминированная проверка кодом: цитата дословно содержится
     в исходном тексте. Ловит выдуманную цитату.
  2. ПОДТВЕРЖДЕНИЕ — отдельный вызов модели: следует ли утверждение из цитаты.
     Ловит misgrounded citation — настоящую цитату, которая утверждения не подтверждает.

Вторая ступень существует потому, что первой недостаточно. Stanford RegLab измерил
коммерческие юридические ИИ на RAG: Lexis+ AI — 17% галлюцинаций, Westlaw — 33%,
и главный класс ошибок там именно misgrounded citation, проходящий проверку наличия
ссылки. В замере BBC 13% цитат из их статей были изменены или отсутствовали
в оригинале.

Утверждение, не прошедшее любую ступень, в саммари не попадает, но СОХРАНЯЕТСЯ
в claims с причиной отбраковки: доля отбраковки должна быть измерима (FR-092),
а пользователь должен видеть счётчик неподтверждённого — молчаливое отбрасывание
рождает страх пропуска и возвращает специалиста в параллельный Excel.
"""

from __future__ import annotations

import logging
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

from src.llm.contracts import Claim, VerifyClaimsResult
from src.llm.prompts import VERIFY_CLAIMS, verify_claims_user_message
from src.llm.provider import LLMError, LLMProvider

logger = logging.getLogger(__name__)

# Минимальная доля цитаты, которая должна найтись непрерывным куском, если точное
# совпадение не получилось. Порог не «на глаз»: он измеряется долей отбраковки
# ступени 1 в evals и настраивается по ней.
FUZZY_MATCH_RATIO = 0.9
# Цитаты короче этого не проверяются нестрогим совпадением: на коротких строках
# частичное совпадение перестаёт что-либо гарантировать.
MIN_FUZZY_LENGTH = 40

# Типографика, которую модель меняет чаще всего, не меняя смысла.
_TRANSLATE = str.maketrans(
    {
        "«": '"',
        "»": '"',
        "“": '"',
        "”": '"',
        "„": '"',
        "‘": "'",
        "’": "'",
        "–": "-",
        "—": "-",
        "‑": "-",
        " ": " ",
        " ": " ",
        " ": " ",
    }
)


class RejectReason:
    QUOTE_NOT_FOUND = "quote_not_found"
    NOT_ENTAILED = "not_entailed"
    VERIFICATION_UNAVAILABLE = "verification_unavailable"


@dataclass
class NormalizedText:
    """Нормализованный текст с картой смещений в исходный.

    Карта нужна, чтобы подсветить фрагмент в ОРИГИНАЛЕ: пользователь должен видеть
    цитату в исходном тексте, а не в нашем внутреннем представлении.
    """

    text: str
    offsets: list[int]

    def original_span(self, start: int, end: int) -> tuple[int, int]:
        if not self.offsets:
            return 0, 0
        first = self.offsets[start]
        last = self.offsets[min(end, len(self.offsets)) - 1] + 1
        return first, last


def normalize_with_map(raw: str) -> NormalizedText:
    """Схлопывает пробелы и унифицирует типографику, сохраняя карту смещений."""
    chars: list[str] = []
    offsets: list[int] = []
    previous_was_space = False

    for index, raw_char in enumerate(raw):
        for char in unicodedata.normalize("NFKC", raw_char).translate(_TRANSLATE):
            if char.isspace():
                if previous_was_space or not chars:
                    continue
                chars.append(" ")
                offsets.append(index)
                previous_was_space = True
                continue
            chars.append(char.lower())
            offsets.append(index)
            previous_was_space = False

    while chars and chars[-1] == " ":
        chars.pop()
        offsets.pop()

    return NormalizedText("".join(chars), offsets)


def normalize_quote(raw: str) -> str:
    return normalize_with_map(raw).text


def locate_quote(source: NormalizedText, quote: str) -> tuple[int, int] | None:
    """Ищет цитату в тексте. Возвращает смещения в ОРИГИНАЛЕ или None.

    Сначала точное совпадение по нормализованному тексту. Если не вышло — ищем
    самый длинный общий непрерывный фрагмент: модель могла перефразировать край
    цитаты, и отбрасывать из-за этого содержательное утверждение расточительно.
    """
    needle = normalize_quote(quote)
    if not needle:
        return None

    position = source.text.find(needle)
    if position != -1:
        return source.original_span(position, position + len(needle))

    if len(needle) < MIN_FUZZY_LENGTH:
        return None

    matcher = SequenceMatcher(None, source.text, needle, autojunk=False)
    match = matcher.find_longest_match(0, len(source.text), 0, len(needle))
    if match.size / len(needle) < FUZZY_MATCH_RATIO:
        return None

    logger.debug("Цитата найдена нестрогим совпадением: %.0f%%", match.size / len(needle) * 100)
    return source.original_span(match.a, match.a + match.size)


def check_quotes(claims: list[Claim], raw_text: str) -> list[dict]:
    """Ступень 1 — FR-012. Возвращает claims с вердиктом вхождения."""
    source = normalize_with_map(raw_text)
    checked: list[dict] = []

    for claim in claims:
        span = locate_quote(source, claim.quote)
        record: dict = {
            "statement": claim.statement.strip(),
            "quote": claim.quote.strip(),
            "quote_found": span is not None,
            "char_start": span[0] if span else None,
            "char_end": span[1] if span else None,
            "entailed": None,
            "reject_reason": None if span else RejectReason.QUOTE_NOT_FOUND,
        }
        checked.append(record)

    return checked


async def check_entailment(claims: list[dict], provider: LLMProvider) -> list[dict]:
    """Ступень 2 — FR-090, FR-091.

    Проверяются только утверждения, прошедшие ступень 1. Все они уходят ОДНИМ
    вызовом: требование производительности из ADR-0007 (SC-003 — 10-15 секунд
    на публикацию), иначе на каждое утверждение приходился бы отдельный запрос.

    Исходный текст материала в промпт не передаётся намеренно: проверяется именно
    то, следует ли утверждение из приведённой цитаты, а не то, есть ли оно где-то
    в тексте вообще.
    """
    candidates = [c for c in claims if c["quote_found"]]
    if not candidates:
        return claims

    pairs = [(c["statement"], c["quote"]) for c in candidates]
    try:
        result = await provider.complete_json(
            VERIFY_CLAIMS.id,
            VERIFY_CLAIMS.system,
            verify_claims_user_message(pairs),
            VerifyClaimsResult,
        )
    except LLMError as exc:
        # Проверка недоступна — утверждения не проходят. Нарушить принцип III
        # молча опаснее, чем показать пустое саммари с явной причиной.
        logger.warning("Ступень 2 недоступна, утверждения отбракованы: %s", str(exc)[:200])
        for claim in candidates:
            claim["entailed"] = False
            claim["reject_reason"] = RejectReason.VERIFICATION_UNAVAILABLE
        return claims

    verdicts = {v.index: v for v in result.verdicts}
    for position, claim in enumerate(candidates):
        verdict = verdicts.get(position)
        if verdict is None:
            claim["entailed"] = False
            claim["reject_reason"] = RejectReason.VERIFICATION_UNAVAILABLE
            continue
        claim["entailed"] = verdict.entailed
        claim["reject_reason"] = None if verdict.entailed else RejectReason.NOT_ENTAILED
        if not verdict.entailed and verdict.reason:
            claim["reject_note"] = verdict.reason.strip()

    return claims


def build_summary_text(claims: list[dict]) -> str:
    """Собирает саммари из утверждений, прошедших обе ступени."""
    accepted = [c["statement"] for c in claims if c["quote_found"] and c["entailed"]]
    return " ".join(s if s.endswith((".", "!", "?")) else f"{s}." for s in accepted)


def grounding_stats(claims: list[dict]) -> dict[str, int]:
    """Доли отбраковки по причинам — FR-092, вход для evals."""
    stats = {
        "total": len(claims),
        "accepted": 0,
        RejectReason.QUOTE_NOT_FOUND: 0,
        RejectReason.NOT_ENTAILED: 0,
        RejectReason.VERIFICATION_UNAVAILABLE: 0,
    }
    for claim in claims:
        if claim["quote_found"] and claim["entailed"]:
            stats["accepted"] += 1
        elif claim.get("reject_reason"):
            stats[claim["reject_reason"]] = stats.get(claim["reject_reason"], 0) + 1
    return stats
