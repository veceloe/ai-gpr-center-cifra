"""Двухступенчатое заземление — задача T022, ADR-0007, принцип III конституции.

Проверяем ровно то, ради чего вторая ступень появилась: выдуманная цитата должна
отбрасываться первой ступенью, а настоящая цитата, которая утверждения не
подтверждает (misgrounded citation), — второй. Именно второй класс ошибок
даёт 17-33% галлюцинаций у коммерческих юридических ИИ по данным Stanford RegLab.
"""

from __future__ import annotations

import pytest

from src.llm.contracts import Claim, ClaimVerdict, VerifyClaimsResult
from src.pipeline.grounding import (
    RejectReason,
    build_summary_text,
    check_entailment,
    check_quotes,
    grounding_stats,
    locate_quote,
    normalize_with_map,
)

SOURCE = (
    "Государственная Дума приняла закон о поддержке технологий искусственного интеллекта. "
    "Документ вводит режим для больших фундаментальных моделей с числом параметров "
    "не менее одного миллиарда. Маркировка контента становится обязательной "
    "с 1 марта 2027 года."
)


class FakeProvider:
    """Провайдер с заранее заданными вердиктами: тест проверяет наш код, а не модель."""

    name = "fake"
    model = "fake-model"

    def __init__(self, verdicts: list[ClaimVerdict] | None = None, fail: bool = False) -> None:
        self._verdicts = verdicts or []
        self._fail = fail
        self.calls: list[str] = []

    async def complete_json(self, prompt_id, system, user, schema):
        self.calls.append(prompt_id)
        if self._fail:
            from src.llm.provider import LLMError

            raise LLMError("провайдер недоступен")
        return VerifyClaimsResult(verdicts=self._verdicts)


class TestStageOneQuoteLookup:
    def test_exact_quote_is_found(self) -> None:
        claims = check_quotes([Claim(statement="Закон принят.", quote="Государственная Дума приняла закон")], SOURCE)
        assert claims[0]["quote_found"] is True
        assert SOURCE[claims[0]["char_start"] : claims[0]["char_end"]].startswith("Государственная Дума")

    def test_fabricated_quote_is_rejected(self) -> None:
        """Главная защита ступени 1: цитаты, которой нет в тексте, не существует."""
        claims = check_quotes(
            [Claim(statement="Штраф составит миллион.", quote="штраф в размере одного миллиона рублей")],
            SOURCE,
        )
        assert claims[0]["quote_found"] is False
        assert claims[0]["reject_reason"] == RejectReason.QUOTE_NOT_FOUND

    def test_typography_differences_tolerated(self) -> None:
        """Кавычки и тире модель меняет постоянно — это не повод терять утверждение."""
        source = 'Регулятор ввёл «доверенный» режим — с 1 января.'
        claims = check_quotes(
            [Claim(statement="Режим введён.", quote='ввёл "доверенный" режим - с 1 января')], source
        )
        assert claims[0]["quote_found"] is True

    def test_whitespace_and_case_normalized(self) -> None:
        claims = check_quotes(
            [Claim(statement="Маркировка обязательна.", quote="МАРКИРОВКА   контента\n становится обязательной")],
            SOURCE,
        )
        assert claims[0]["quote_found"] is True

    def test_offsets_point_into_original_text(self) -> None:
        """Смещения должны указывать в оригинал: подсветка идёт по исходному тексту."""
        source = normalize_with_map(SOURCE)
        span = locate_quote(source, "не менее одного миллиарда")
        assert span is not None
        assert "миллиард" in SOURCE[span[0] : span[1]]

    def test_short_quote_requires_exact_match(self) -> None:
        """На коротких строках нестрогое совпадение перестаёт что-либо гарантировать."""
        claims = check_quotes([Claim(statement="Что-то про ИИ.", quote="закон об ИИ")], SOURCE)
        assert claims[0]["quote_found"] is False


class TestStageTwoEntailment:
    @pytest.mark.asyncio
    async def test_misgrounded_citation_is_rejected(self) -> None:
        """Цитата настоящая, но утверждения не подтверждает.

        Ступень 1 такое пропускает — ради этого случая вторая ступень и существует.
        """
        claims = check_quotes(
            [
                Claim(
                    statement="Закон вводит уголовную ответственность за дипфейки.",
                    quote="Документ вводит режим для больших фундаментальных моделей",
                )
            ],
            SOURCE,
        )
        assert claims[0]["quote_found"] is True, "предусловие: ступень 1 пройдена"

        provider = FakeProvider(
            [ClaimVerdict(index=0, entailed=False, reason="в цитате нет уголовной ответственности")]
        )
        checked = await check_entailment(claims, provider)

        assert checked[0]["entailed"] is False
        assert checked[0]["reject_reason"] == RejectReason.NOT_ENTAILED
        assert checked[0]["reject_note"]

    @pytest.mark.asyncio
    async def test_supported_claim_passes(self) -> None:
        claims = check_quotes(
            [Claim(statement="Закон принят Госдумой.", quote="Государственная Дума приняла закон")],
            SOURCE,
        )
        provider = FakeProvider([ClaimVerdict(index=0, entailed=True)])
        checked = await check_entailment(claims, provider)
        assert checked[0]["entailed"] is True
        assert checked[0]["reject_reason"] is None

    @pytest.mark.asyncio
    async def test_all_claims_verified_in_single_call(self) -> None:
        """Одним вызовом на материал — требование производительности из ADR-0007."""
        claims = check_quotes(
            [
                Claim(statement="Закон принят.", quote="Государственная Дума приняла закон"),
                Claim(statement="Порог — миллиард параметров.", quote="не менее одного миллиарда"),
                Claim(statement="Маркировка с марта 2027.", quote="с 1 марта 2027 года"),
            ],
            SOURCE,
        )
        provider = FakeProvider([ClaimVerdict(index=i, entailed=True) for i in range(3)])
        await check_entailment(claims, provider)
        assert len(provider.calls) == 1

    @pytest.mark.asyncio
    async def test_failed_quotes_are_not_sent_to_verification(self) -> None:
        claims = check_quotes(
            [Claim(statement="Выдумка.", quote="этого в тексте нет совершенно точно")], SOURCE
        )
        provider = FakeProvider()
        await check_entailment(claims, provider)
        assert provider.calls == [], "не прошедшее ступень 1 не должно тратить вызов модели"

    @pytest.mark.asyncio
    async def test_unavailable_verification_rejects_claims(self) -> None:
        """Если проверить нельзя — утверждение не проходит.

        Нарушить принцип III молча опаснее, чем показать пустое саммари с причиной.
        """
        claims = check_quotes(
            [Claim(statement="Закон принят.", quote="Государственная Дума приняла закон")], SOURCE
        )
        checked = await check_entailment(claims, FakeProvider(fail=True))
        assert checked[0]["entailed"] is False
        assert checked[0]["reject_reason"] == RejectReason.VERIFICATION_UNAVAILABLE


class TestSummaryAssembly:
    @pytest.mark.asyncio
    async def test_only_passed_claims_reach_summary(self) -> None:
        claims = check_quotes(
            [
                Claim(statement="Закон принят Госдумой", quote="Государственная Дума приняла закон"),
                Claim(statement="Введены штрафы", quote="штрафы до пятисот тысяч рублей"),
                Claim(statement="Порог — миллиард", quote="не менее одного миллиарда"),
            ],
            SOURCE,
        )
        provider = FakeProvider(
            [ClaimVerdict(index=0, entailed=True), ClaimVerdict(index=1, entailed=False)]
        )
        checked = await check_entailment(claims, provider)
        text = build_summary_text(checked)

        assert "Закон принят Госдумой." in text
        assert "штраф" not in text.lower()

    @pytest.mark.asyncio
    async def test_rejected_claims_are_kept_for_counter(self) -> None:
        """Отбракованное сохраняется: пользователь должен видеть, сколько не подтвердилось."""
        claims = check_quotes(
            [
                Claim(statement="Закон принят.", quote="Государственная Дума приняла закон"),
                Claim(statement="Выдумка.", quote="ничего подобного в тексте нет и быть не может"),
            ],
            SOURCE,
        )
        checked = await check_entailment(claims, FakeProvider([ClaimVerdict(index=0, entailed=True)]))
        stats = grounding_stats(checked)

        assert stats["total"] == 2
        assert stats["accepted"] == 1
        assert stats[RejectReason.QUOTE_NOT_FOUND] == 1
        assert len(checked) == 2, "отбракованные утверждения не удаляются"
