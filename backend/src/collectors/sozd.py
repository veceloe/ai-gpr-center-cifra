"""Система обеспечения законодательной деятельности — задача T064, research R-04.

Первичный источник стадий и хронологии законопроектов. Строить досье НПА на
новостных упоминаниях бессмысленно: стадия и версия достоверно известны только
у первоисточника.

ПОЧЕМУ РАЗБОР ПО ТЕКСТУ, А НЕ ПО CSS-СЕЛЕКТОРАМ. Разметка СОЗД непроста и
меняется, а сайт недоступен из части сетей — проверить селекторы на живой
странице при написании не удалось. Поэтому извлечение опирается на устойчивые
признаки: номер законопроекта в URL (формат «1215252-8» стабилен годами) и
ключевые слова стадий в тексте страницы. Такой разбор переживает перевёрстку.

ОГРАНИЧЕНИЕ, КОТОРОЕ НАДО НАЗЫВАТЬ ВСЛУХ: парсер проверен на сохранённом снимке
страницы, а не на живом сайте. Перед демонстрацией прогнать `collect` по этому
источнику и убедиться, что стадии распознаются.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import UTC, date, datetime
from urllib.parse import urlparse

import httpx

from src.collectors.base import CollectedItem, register_adapter
from src.models import ActStage, Source, SourceType
from src.pipeline.normalize import clean_text, extract_from_html

logger = logging.getLogger(__name__)

BASE = "https://sozd.duma.gov.ru"
DUMA_SEARCH_RSS = "http://api.duma.gov.ru/api/search.rss"
REQUEST_TIMEOUT = 30.0
MAX_CONCURRENT = 3
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# Номер законопроекта: цифры, дефис, номер созыва. Формат неизменен много лет.
BILL_NUMBER = re.compile(r"\b(\d{6,8}-\d{1,2})\b")
BILL_HREF = re.compile(r"/bill/(\d{6,8}-\d{1,2})", re.I)
DATE_DMY = re.compile(r"\b(\d{2})\.(\d{2})\.(\d{4})\b")

# Стадии в порядке возрастания: если на странице нашлось несколько, берём самую
# позднюю — карточка законопроекта содержит всю историю, а нам нужно текущее.
STAGE_MARKERS: list[tuple[ActStage, tuple[str, ...]]] = [
    (ActStage.ANNOUNCEMENT, ("предварительное рассмотрение", "внесение в гд")),
    (ActStage.DRAFT_DISCUSSION, ("общественное обсуждение", "публичное обсуждение")),
    (ActStage.SUBMITTED, ("внесён в гд", "внесен в гд", "регистрация законопроекта")),
    (ActStage.READINGS, ("первое чтение", "второе чтение", "третье чтение", "рассмотрение советом")),
    (ActStage.ADOPTED, ("принят гд", "одобрен сф", "подписан президентом")),
    (ActStage.IN_FORCE, ("опубликован", "вступил в силу", "вступает в силу")),
]


def extract_bill_number(text: str) -> str | None:
    """Номер законопроекта из URL или текста."""
    href = BILL_HREF.search(text)
    if href:
        return href.group(1)
    plain = BILL_NUMBER.search(text)
    return plain.group(1) if plain else None


def detect_stage(text: str) -> ActStage | None:
    """Самая поздняя стадия, упомянутая на странице.

    Карточка СОЗД содержит всю хронологию, поэтому берём максимум по порядку
    жизненного цикла, а не первое совпадение.
    """
    lowered = text.lower()
    found: ActStage | None = None
    for stage, markers in STAGE_MARKERS:
        if any(m in lowered for m in markers):
            found = stage
    return found


def extract_last_event_date(text: str) -> date | None:
    """Самая поздняя дата на странице — приближение даты последнего события."""
    dates: list[date] = []
    for day, month, year in DATE_DMY.findall(text):
        try:
            parsed = date(int(year), int(month), int(day))
        except ValueError:
            continue
        # Отсекаем явную бессмыслицу: карточка не может ссылаться далеко в будущее.
        if 2000 <= parsed.year <= date.today().year + 2:
            dates.append(parsed)
    return max(dates) if dates else None


def extract_title(html_text: str, plain: str, number: str) -> str:
    """Наименование законопроекта.

    Заголовок страницы СОЗД содержит номер и наименование; если разметка
    изменилась, берём первую содержательную строку текста.
    """
    match = re.search(r"<title>(.*?)</title>", html_text, re.S | re.I)
    if match:
        title = clean_text(re.sub(r"\s+", " ", match.group(1)))
        title = title.replace("СОЗД ГАС «Законотворчество»", "").strip(" -—|")
        if len(title) > 15:
            return title[:900]

    for line in plain.split("\n"):
        candidate = line.strip()
        if len(candidate) > 30 and number not in candidate:
            return candidate[:900]
    return f"Законопроект № {number}"


class SozdAdapter:
    """Собирает карточки законопроектов со страницы списка СОЗД.

    В качестве URL источника задаётся страница со списком — например
    https://sozd.duma.gov.ru/oz — или страница поиска с фильтрами. Публичная
    /oz рендерится через JS, поэтому для стандартного списка используем
    официальный RSS API Государственной Думы.
    """

    source_type = SourceType.SOZD

    async def fetch(self, source: Source, limit: int) -> list[CollectedItem]:
        headers = {"User-Agent": USER_AGENT, "Accept-Language": "ru-RU,ru;q=0.9"}
        async with httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT, headers=headers, follow_redirects=True
        ) as client:
            if self._uses_official_rss(source.url):
                index = await client.get(
                    DUMA_SEARCH_RSS,
                    params={"law_type": 38, "status": 2},
                )
            else:
                index = await client.get(source.url)
            index.raise_for_status()

            numbers = self._bill_numbers(index.text, limit)
            if not numbers:
                raise ValueError(
                    "на странице не найдено ссылок вида /bill/<номер> — "
                    "проверьте URL источника или доступность СОЗД"
                )

            semaphore = asyncio.Semaphore(MAX_CONCURRENT)

            async def load(number: str) -> CollectedItem | None:
                async with semaphore:
                    return await self._load_bill(client, number)

            gathered = await asyncio.gather(*(load(n) for n in numbers))

        collected = [item for item in gathered if item is not None]
        logger.info("СОЗД: карточек получено %s из %s найденных", len(collected), len(numbers))
        return collected

    def _uses_official_rss(self, url: str) -> bool:
        parsed = urlparse(url)
        host = parsed.netloc.lower().removeprefix("www.")
        return host == "sozd.duma.gov.ru" and parsed.path.rstrip("/") in {"", "/oz"}

    def _bill_numbers(self, html_text: str, limit: int) -> list[str]:
        seen: list[str] = []
        for number in BILL_HREF.findall(html_text):
            if number not in seen:
                seen.append(number)
            if len(seen) >= limit:
                break
        return seen

    async def _load_bill(self, client: httpx.AsyncClient, number: str) -> CollectedItem | None:
        url = f"{BASE}/bill/{number}"
        try:
            page = await client.get(url)
            page.raise_for_status()
        except httpx.HTTPError as exc:
            logger.debug("Карточка %s недоступна: %s", number, str(exc)[:120])
            return None

        plain = extract_from_html(page.text)
        if not plain:
            return None

        stage = detect_stage(page.text)
        occurred = extract_last_event_date(plain)
        title = extract_title(page.text, plain, number)

        # Стадию и дату кладём в начало текста: конвейер оценивает материал по
        # тексту, а юридическая сила (критерий К2) выводится именно из стадии.
        header = [f"Законопроект № {number}."]
        if stage is not None:
            header.append(f"Текущая стадия: {STAGE_TEXT[stage]}.")
        if occurred is not None:
            header.append(f"Дата последнего события: {occurred.strftime('%d.%m.%Y')}.")

        published = (
            datetime.combine(occurred, datetime.min.time(), tzinfo=UTC) if occurred else None
        )

        return CollectedItem(
            url=url,
            title=title,
            raw_text=" ".join(header) + "\n\n" + plain,
            published_at=published,
            external_id=number,
        )


STAGE_TEXT = {
    ActStage.ANNOUNCEMENT: "анонс, предварительное рассмотрение",
    ActStage.DRAFT_DISCUSSION: "проект на публичном обсуждении",
    ActStage.SUBMITTED: "внесён в Государственную Думу",
    ActStage.READINGS: "рассмотрение в чтениях",
    ActStage.ADOPTED: "принят",
    ActStage.IN_FORCE: "опубликован, вступил в силу",
}


register_adapter(SozdAdapter())
