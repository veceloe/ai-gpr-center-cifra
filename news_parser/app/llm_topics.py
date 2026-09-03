import json
import logging
import re
from datetime import datetime, timezone

from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Period
from app.llm_client import LlmClient
from app.models import Post, Topic, TopicPost
from app.parser_service import get_posts_for_period
from app.periods import period_bounds

logger = logging.getLogger(__name__)


class TopicItem(BaseModel):
    slug: str = Field(description="Идентификатор топика в kebab-case, латиница, уникальный в рамках ответа")
    title: str = Field(description="Краткий заголовок конкретного события на русском")
    summary: str = Field(description="2-3 предложения о сути события")
    post_ids: list[int] = Field(description="id постов из входного списка, относящихся к этому событию")


class TopicsResult(BaseModel):
    topics: list[TopicItem] = Field(default_factory=list)


class FilterResult(BaseModel):
    keep_ids: list[int] = Field(
        default_factory=list,
        description="id новостей, которые подходят как инфоповод для рекламы",
    )


SYSTEM_PROMPT = """Ты аналитик новостей. По списку постов из Telegram-каналов сгруппируй их по КОНКРЕТНЫМ событиям (инфоповодам).
Главное правило группировки — ОДИН ТОПИК = ОДНО КОНКРЕТНОЕ СОБЫТИЕ:
- Объединяй посты только если они про ОДНО И ТО ЖЕ событие. Про одно событие может быть несколько постов из разных каналов — их и объединяй.
- НЕ объединяй разные события только потому, что они из одной сферы или темы.
- ПЛОХО (слишком широко, это темы, а не события): "События на дорогах", "Тренды в образовании", "Новости спорта", "Изменения в законах".
- ХОРОШО (конкретное событие): "Открытие станции метро «Потапово»", "Запуск нового тарифа у оператора X", "Победа сборной в матче с Y".
- Если про событие всего один пост — это нормально, создай топик на один пост. Не выбрасывай уникальные события.
Остальные правила:
- slug: латиница, kebab-case, уникальный в рамках ответа
- post_ids: только id из входного списка, каждый пост максимум в одном топике
- title: называй конкретное событие, а не общую сферу
- summary: кратко опиши суть именно этого события
"""

FILTER_SYSTEM_PROMPT = """Ты — фильтр новостей для маркетинга. На основе новостей строятся рекламные кампании (инфоповоды для рекламы на определённую аудиторию).
Твоя задача — отобрать только те новости, которые ПОДХОДЯТ как инфоповод для рекламы.

Реклама строится для сервиса доставки продуктов и товаров экосистемы Сбера (Самокат и др.).

НЕ подходят (отсеивай) — негатив, на котором нельзя строить рекламу:
- происшествия, ДТП, аварии, катастрофы, пожары, ЧП
- криминал, преступления, насилие, теракты, мошенничество
- смерти, болезни, эпидемии, трагедии, стихийные бедствия
- скандалы, конфликты, военные сводки и прочий негатив

КОНКУРЕНТЫ (чужие бренды) — новости ПРО них ОТСЕИВАЙ
Отсеивай новость, если её центральный сюжет — конкурент: его акция, распродажа, запуск, скидки или новость о самом бренде. Основные конкуренты по категориям (список примерный, ориентируйся по смыслу):
- Маркетплейсы: Wildberries (Вайлдберриз, WB), Ozon (Озон), AliExpress.
- Доставка еды/продуктов и продуктовый ритейл: Яндекс.Лавка, Яндекс.Еда, Яндекс.Маркет, Delivery Club, ВкусВилл, Магнит, Пятёрочка, Перекрёсток, X5, Лента, Ашан.
Пример: «Вайлдберриз запустил фестиваль скидок» → ОТСЕИВАЙ (реклама конкурента, на ней нельзя строить наш инфоповод).

ПРОДУКТЫ ЭКОСИСТЕМЫ СБЕРА (свои бренды) — новости ПРО них ОСТАВЛЯЙ
Это НЕ конкуренты, а наши собственные продукты. Новости про них — хороший инфоповод, ОСТАВЛЯЙ:
- Доставка и ритейл: Самокат, Купер (бывш. СберМаркет), СберМаркет, Мегамаркет (СберМегаМаркет).
- Финансы и подписки: Сбер (СберБанк), СберПрайм, СберСпасибо, ЮMoney, СберСтрахование.
- Сервисы и медиа: Okko, Звук (СберЗвук), 2ГИС, Домклик, СберЗдоровье, СберЛогистика, СберМобайл, СберАвто, СберМаркетинг.
- Технологии и устройства: GigaChat, Салют (СалютДжаз), СберДевайсы, СберДиск.
ВНИМАНИЕ: Мегамаркет и Купер — это Сбер, а НЕ конкуренты. Их и другие бренды из этого блока НЕ путай с конкурентами и НЕ отсеивай.

Общее правило разделения: отсеивай, только если новость именно ПРО конкурента (его бренд/акция в центре сюжета). Нейтральную новость (погода, праздник, культурное или городское событие), где конкурент не упомянут вовсе, — ОСТАВЛЯЙ.

Подходят (оставляй) — нейтральные и позитивные инфоповоды:
- запуски продуктов, технологии, новинки, обновления сервисов (кроме брендов-конкурентов выше)
- культура, спорт, развлечения, праздники, события
- бизнес, экономика, наука (нейтральные/позитивные)
- погода, городские события, сезонные поводы
- всё, на чём уместно построить позитивную рекламную кампанию для доставки продуктов/товаров

В keep_ids верни id новостей, которые ПОДХОДЯТ для рекламы. Если ни одна не подходит — верни пустой список.
"""


def _slugify(text: str) -> str:
    value = text.lower().strip()
    value = re.sub(r"[^a-z0-9а-яё]+", "-", value, flags=re.IGNORECASE)
    value = re.sub(r"-+", "-", value).strip("-")
    return value[:120] or "topic"


async def filter_advertisable_posts(posts: list[Post]) -> list[Post]:
    """Отсеивает негатив и новости про конкурентов, непригодные как инфоповод для рекламы."""
    if not posts:
        return []

    payload_posts = [{"id": p.id, "text": p.text[:1000]} for p in posts]
    user_content = json.dumps(payload_posts, ensure_ascii=False)

    try:
        result = await LlmClient().chat_structured(FILTER_SYSTEM_PROMPT, user_content, FilterResult)
    except Exception as exc:  # noqa: BLE001 - the filtering stage is explicitly fail-open
        # Fail-open: при сбое фильтра не выбрасываем все новости, а пропускаем дальше как есть.
        logger.warning("News filter failed, keeping all posts: %s", exc)
        return posts

    keep_set = set(result.keep_ids)
    filtered = [p for p in posts if p.id in keep_set]
    logger.info("News filter kept %d of %d posts", len(filtered), len(posts))
    return filtered


async def extract_topics_with_llm(posts: list[Post]) -> list[TopicItem]:
    if not posts:
        return []

    payload_posts = [{"id": p.id, "channel": p.channel_username, "text": p.text[:1500]} for p in posts]
    user_content = json.dumps(payload_posts, ensure_ascii=False)
    result = await LlmClient().chat_structured(SYSTEM_PROMPT, user_content, TopicsResult)
    return result.topics


async def refresh_topics_for_period(session: AsyncSession, period: Period) -> int:
    period_start, period_end = period_bounds(period)
    posts = await get_posts_for_period(session, period_start, period_end)
    if not posts:
        await _clear_topics(session, period)
        await session.commit()
        return 0

    posts = await filter_advertisable_posts(posts)
    if not posts:
        await _clear_topics(session, period)
        await session.commit()
        logger.info("No advertisable posts left after filtering for period=%s", period)
        return 0

    valid_ids = {p.id for p in posts}
    raw_topics = await extract_topics_with_llm(posts)
    await _clear_topics(session, period)

    used_slugs: set[str] = set()
    created = 0
    for item in raw_topics:
        title = item.title.strip()
        if not title:
            continue
        slug = (item.slug or _slugify(title)).strip() or _slugify(title)
        base_slug = slug
        n = 2
        while slug in used_slugs:
            slug = f"{base_slug}-{n}"
            n += 1
        used_slugs.add(slug)
        summary = item.summary.strip() or title
        post_ids = [pid for pid in item.post_ids if pid in valid_ids]
        if not post_ids:
            continue

        topic = Topic(
            period=period,
            slug=slug,
            title=title,
            summary=summary,
            period_start=period_start,
            period_end=period_end,
            created_at=datetime.now(timezone.utc),
        )
        session.add(topic)
        await session.flush()

        for post_id in post_ids:
            session.add(TopicPost(topic_id=topic.id, post_id=post_id))
        created += 1

    await session.commit()
    logger.info("Created %d topics for period=%s", created, period)
    return created


async def refresh_all_periods(session: AsyncSession) -> dict[str, int]:
    result = {}
    for period in ("day", "week", "month"):
        result[period] = await refresh_topics_for_period(session, period)
    return result


async def _clear_topics(session: AsyncSession, period: Period) -> None:
    existing = await session.execute(select(Topic.id).where(Topic.period == period))
    topic_ids = [row[0] for row in existing.all()]
    if topic_ids:
        await session.execute(delete(TopicPost).where(TopicPost.topic_id.in_(topic_ids)))
        await session.execute(delete(Topic).where(Topic.id.in_(topic_ids)))
