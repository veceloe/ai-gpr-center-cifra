/**
 * Строка ленты — FR-020, FR-023.
 *
 * Свёрнутая карточка держится в 64-72px, что даёт 12-14 материалов на экран
 * ноутбука: суточная лента в 20-60 материалов укладывается в 2-4 экрана.
 * Плотность переключается, выбор запоминается.
 *
 * Спарклайн из шести сегментов показывает вклад критериев без раскрытия —
 * читается периферийным зрением.
 */

import type { ItemCard } from '../api/types'
import {
  ITEM_TYPE_LABELS,
  TOPIC_LABELS,
  formatIndex,
  formatRelative,
  isDimmed,
  plural,
} from '../lib/format'

interface Props {
  item: ItemCard
  focused: boolean
  expanded: boolean
  selected: boolean
  selectable: boolean
  onToggle: () => void
  onFocus: () => void
  onSelect: (checked: boolean) => void
}

/** Шесть сегментов по вкладу критериев. Заливка — доля от максимума. */
function Sparkline({ item }: { item: ItemCard }) {
  if (item.index_value === null) return null
  // Индекс 0-100 раскладываем на 6 делений: не точные баллы, а форма оценки.
  const filled = Math.round((item.index_value / 100) * 6)
  return (
    <span className="spark" aria-hidden="true">
      {[0, 1, 2, 3, 4, 5].map((i) => (
        <i key={i} data-filled={i < filled} style={{ height: `${5 + i * 1.4}px` }} />
      ))}
    </span>
  )
}

export function FeedRow({
  item,
  focused,
  expanded,
  selected,
  selectable,
  onToggle,
  onFocus,
  onSelect,
}: Props) {
  const dim = isDimmed(item.final_category)

  return (
    <div
      className="row"
      data-sev={item.final_category ?? ''}
      data-dim={dim}
      data-focused={focused}
      role="button"
      tabIndex={0}
      aria-expanded={expanded}
      onClick={onToggle}
      onFocus={onFocus}
      onKeyDown={(e) => {
        if (e.key === 'Enter') {
          e.preventDefault()
          onToggle()
        }
      }}
    >
      <span className="sev-edge" />

      <div className="row-index">
        {item.index_value === null ? (
          <span className="index-none" title="Материал ещё не оценён">
            —
          </span>
        ) : (
          <>
            <div className="index-num">{formatIndex(item.index_value)}</div>
            <div className="index-cat">{item.final_category}</div>
          </>
        )}
      </div>

      <div className="row-body">
        <p className="row-title">{item.title}</p>
        {item.summary && <p className="row-summary">{item.summary}</p>}

        <div className="row-meta">
          <Sparkline item={item} />
          <span>{item.source.title}</span>
          <span className="dot">{formatRelative(item.published_at)}</span>
          {item.published_at_is_approx && (
            <span className="badge" title="Источник не сообщил дату публикации">
              дата приблизительна
            </span>
          )}
          {item.item_type === 'act' && <span className="badge badge-act">НПА</span>}
          {item.topic && <span>{TOPIC_LABELS[item.topic]}</span>}
          {item.story && item.story.item_count > 1 && (
            <span className="badge" title="Публикации об одном факте схлопнуты">
              +{plural(item.story.item_count - 1, 'перепечатка', 'перепечатки', 'перепечаток')}
            </span>
          )}
          {item.is_edited && <span className="badge badge-edited">скорректировано</span>}
          {item.assessment_failed && (
            <span className="badge badge-risk" title="Оценка не получена, материал сохранён">
              без оценки
            </span>
          )}
          {item.is_partial_text && (
            <span className="badge" title="Полный текст закрыт подпиской">
              частичный текст
            </span>
          )}
          {item.escalation_flags.length > 0 && (
            <span className="badge badge-risk" title={item.escalation_flags.join('\n')}>
              эскалация
            </span>
          )}
          {item.is_hidden && <span className="badge">скрыто</span>}
        </div>
      </div>

      <div className="row-actions" onClick={(e) => e.stopPropagation()}>
        {selectable && (
          <label className="btn btn-ghost btn-sm" title="В дайджест">
            <input
              type="checkbox"
              checked={selected}
              onChange={(e) => onSelect(e.target.checked)}
              aria-label={`Добавить «${item.title}» в дайджест`}
            />
          </label>
        )}
        <a
          className="btn btn-ghost btn-sm"
          href={item.url}
          target="_blank"
          rel="noreferrer"
          title="Открыть оригинал"
        >
          оригинал
        </a>
        <span className="badge" style={{ borderColor: 'transparent' }}>
          {ITEM_TYPE_LABELS[item.item_type]}
        </span>
      </div>
    </div>
  )
}
