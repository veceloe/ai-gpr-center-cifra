/** Форматирование и словари предметной области. */

import type { ActStage, ActEventType, ItemType, SourceType, Topic } from '../api/types'

export const TOPIC_LABELS: Record<Topic, string> = {
  regulatory: 'Регуляторика',
  reputation: 'Репутация',
  competitors: 'Конкуренты',
  trends: 'Тренды',
}

export const ITEM_TYPE_LABELS: Record<ItemType, string> = {
  news: 'Новость',
  act: 'НПА',
}

export const SOURCE_TYPE_LABELS: Record<SourceType, string> = {
  rss: 'RSS-лента',
  web: 'Страница регулятора',
  sozd: 'СОЗД — законопроекты',
  telegram: 'Telegram-канал',
  manual: 'Добавлено вручную',
}

/** Порядок совпадает с прохождением жизненного цикла — FR-032. */
export const ACT_STAGES: ActStage[] = [
  'announcement',
  'draft_discussion',
  'submitted',
  'readings',
  'adopted',
  'in_force',
]

export const STAGE_LABELS: Record<ActStage, string> = {
  announcement: 'Анонс',
  draft_discussion: 'Обсуждение',
  submitted: 'Внесён',
  readings: 'Чтения',
  adopted: 'Принят',
  in_force: 'В силе',
}

export const EVENT_LABELS: Record<ActEventType, string> = {
  stage_change: 'Смена стадии',
  new_version: 'Новая версия',
  feedback: 'Отзыв',
  hearing: 'Слушания',
  other: 'Событие',
}

/**
 * Цветом кодируются только два верхних уровня серьёзности.
 * Пять цветов превращают экран из сорока карточек в светофор, а сортировка
 * по индексу уже выполнила основную работу — интерфейс лишь не мешает.
 */
export function isDimmed(category: string | null): boolean {
  return category === null || category === 'Низкое' || category === 'Незначительное' ||
    category === 'Фон' || category === 'На заметку'
}

export function formatIndex(value: number | null): string {
  return value === null ? '—' : value.toFixed(1)
}

const DATE_FMT = new Intl.DateTimeFormat('ru-RU', { day: '2-digit', month: 'short' })
const DATE_FULL = new Intl.DateTimeFormat('ru-RU', { day: '2-digit', month: 'long', year: 'numeric' })

export function formatDate(iso: string): string {
  return DATE_FMT.format(new Date(iso))
}

export function formatFullDate(iso: string): string {
  return DATE_FULL.format(new Date(iso))
}

export function formatRelative(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const minutes = Math.round(diff / 60000)
  if (minutes < 1) return 'только что'
  if (minutes < 60) return `${minutes} мин назад`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours} ч назад`
  return formatDate(iso)
}

/** Склонение существительного по числу: 1 материал, 2 материала, 5 материалов. */
export function plural(n: number, one: string, few: string, many: string): string {
  const mod10 = n % 10
  const mod100 = n % 100
  if (mod10 === 1 && mod100 !== 11) return `${n} ${one}`
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return `${n} ${few}`
  return `${n} ${many}`
}

/** Вклад критерия в индекс, в баллах итоговой шкалы 0-100. */
export function contributionPoints(contribution: number, divisor = 3): number {
  return (contribution / divisor) * 100
}

/**
 * Человекочитаемое имя досье.
 *
 * Идентификатор акта — служебный ключ, по которому материалы связываются
 * в одно досье. Часть ключей человек читать не должен:
 *
 *   `ФЗ № 243-ФЗ`, `Законопроект № 1215252-8` — канонический номер, показываем как есть;
 *   `regulation.gov.ru:170862` — номер проекта на портале, разворачиваем в текст;
 *   `url:0fc4420b21f4613f` — номер не распознан вовсе, показываем суть документа.
 */
const PORTAL_LABELS: Record<string, string> = {
  'regulation.gov.ru': 'Проект НПА № {n} · regulation.gov.ru',
  'sozd.duma.gov.ru': 'Законопроект № {n} · СОЗД',
}

export function actTitle(identifier: string, essence: string): string {
  if (identifier.startsWith('url:')) {
    const firstSentence = essence.split(/[.:]\s/)[0]?.trim()
    return firstSentence && firstSentence.length > 12
      ? firstSentence.slice(0, 160)
      : 'Документ без распознанного номера'
  }
  const colon = identifier.indexOf(':')
  if (colon > 0) {
    const template = PORTAL_LABELS[identifier.slice(0, colon)]
    const number = identifier.slice(colon + 1)
    if (template && number) return template.replace('{n}', number)
  }
  return identifier
}

/** Номер акта не распознан — это стоит показать явно, а не прятать. */
export function hasCanonicalNumber(identifier: string): boolean {
  return !identifier.startsWith('url:')
}
