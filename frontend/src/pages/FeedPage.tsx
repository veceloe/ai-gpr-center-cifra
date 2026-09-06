/**
 * Лента — US1, FR-018, FR-020, FR-021, FR-022.
 *
 * Сортировка по убыванию влияния: специалист начинает с того, что сильнее
 * касается его компании, а не с самого свежего.
 *
 * Клавиатура: j/k или стрелки листают фокус, Space раскрывает, ? показывает
 * подсказку. Позиция в ленте при раскрытии не теряется.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ApiError, api } from '../api/client'
import type { FeedQuery, ItemCard, Source } from '../api/types'
import { FeedRow } from '../components/FeedRow'
import { ItemDetail, type ItemCardPatch } from '../components/ItemDetail'
import { IMPACT_CATEGORIES, RELEVANCE_CATEGORIES } from '../api/types'
import { TOPIC_LABELS, plural } from '../lib/format'

interface Props {
  onToast: (message: string, undo?: () => void) => void
  selection: number[]
  onSelectionChange: (ids: number[]) => void
}

const PAGE_SIZE = 60

export function FeedPage({ onToast, selection, onSelectionChange }: Props) {
  const [items, setItems] = useState<ItemCard[]>([])
  const [total, setTotal] = useState(0)
  const [sources, setSources] = useState<Source[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [focusIndex, setFocusIndex] = useState(0)
  const [showHelp, setShowHelp] = useState(false)

  const [query, setQuery] = useState('')
  const [filters, setFilters] = useState<FeedQuery>({})
  const [density, setDensity] = useState<'standard' | 'compact'>(
    () => (localStorage.getItem('density') as 'standard' | 'compact') ?? 'standard',
  )

  const listRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    document.documentElement.dataset.density = density
    localStorage.setItem('density', density)
  }, [density])

  useEffect(() => {
    api.sources().then(setSources).catch(() => setSources([]))
  }, [])

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await api.feed({ ...filters, q: query || undefined, limit: PAGE_SIZE })
      setItems(data.items)
      setTotal(data.total)
    } catch (e) {
      setError((e as ApiError).message)
    } finally {
      setLoading(false)
    }
  }, [filters, query])

  // Поиск с задержкой: набор текста не должен бомбить сервер на каждую букву.
  useEffect(() => {
    const timer = setTimeout(load, query ? 250 : 0)
    return () => clearTimeout(timer)
  }, [load, query])

  const categories = useMemo(
    () => [...IMPACT_CATEGORIES, ...RELEVANCE_CATEGORIES],
    [],
  )

  const focusRow = useCallback(
    (index: number) => {
      const clamped = Math.max(0, Math.min(index, items.length - 1))
      setFocusIndex(clamped)
      const rows = listRef.current?.querySelectorAll<HTMLElement>('.row')
      rows?.[clamped]?.scrollIntoView({ block: 'nearest' })
    },
    [items.length],
  )

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const target = e.target as HTMLElement
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)) return

      if (e.key === 'j' || e.key === 'ArrowDown') {
        e.preventDefault()
        focusRow(focusIndex + 1)
      } else if (e.key === 'k' || e.key === 'ArrowUp') {
        e.preventDefault()
        focusRow(focusIndex - 1)
      } else if (e.key === ' ') {
        e.preventDefault()
        const item = items[focusIndex]
        if (item) setExpandedId((id) => (id === item.id ? null : item.id))
      } else if (e.key === '?') {
        setShowHelp((v) => !v)
      } else if (e.key === 'Escape') {
        setExpandedId(null)
        setShowHelp(false)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [focusIndex, items, focusRow])

  /** Обновляем строку на месте: порядок ленты не меняется, место не теряется. */
  function patchRow(id: number, patch: Partial<ItemCardPatch>) {
    setItems((prev) => prev.map((it) => (it.id === id ? { ...it, ...patch } : it)))
  }

  function toggleSelect(id: number, checked: boolean) {
    onSelectionChange(checked ? [...selection, id] : selection.filter((x) => x !== id))
  }

  return (
    <>
      <div className="filters">
        <div className="field search">
          <label htmlFor="q">Поиск</label>
          <input
            id="q"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="по тексту, тегам и сущностям"
          />
        </div>

        <div className="field">
          <label htmlFor="f-type">Тип</label>
          <select
            id="f-type"
            value={filters.item_type ?? ''}
            onChange={(e) =>
              setFilters((f) => ({ ...f, item_type: (e.target.value || undefined) as never }))
            }
          >
            <option value="">все</option>
            <option value="news">новости</option>
            <option value="act">НПА</option>
          </select>
        </div>

        <div className="field">
          <label htmlFor="f-topic">Тематика</label>
          <select
            id="f-topic"
            value={filters.topic ?? ''}
            onChange={(e) =>
              setFilters((f) => ({ ...f, topic: (e.target.value || undefined) as never }))
            }
          >
            <option value="">любая</option>
            {Object.entries(TOPIC_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>

        <div className="field">
          <label htmlFor="f-cat">Влияние</label>
          <select
            id="f-cat"
            value={filters.category ?? ''}
            onChange={(e) => setFilters((f) => ({ ...f, category: e.target.value || undefined }))}
          >
            <option value="">любое</option>
            {categories.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </div>

        <div className="field">
          <label htmlFor="f-source">Источник</label>
          <select
            id="f-source"
            value={filters.source_id ?? ''}
            onChange={(e) =>
              setFilters((f) => ({
                ...f,
                source_id: e.target.value ? Number(e.target.value) : undefined,
              }))
            }
          >
            <option value="">все</option>
            {sources.map((s) => (
              <option key={s.id} value={s.id}>
                {s.title}
              </option>
            ))}
          </select>
        </div>

        <button
          type="button"
          className="btn"
          aria-pressed={filters.include_irrelevant ?? false}
          onClick={() =>
            setFilters((f) => ({ ...f, include_irrelevant: !f.include_irrelevant || undefined }))
          }
          title="Материалы без связи с профилем компании"
        >
          {filters.include_irrelevant ? '✓ ' : ''}показать шум
        </button>

        <button
          type="button"
          className="btn"
          aria-pressed={filters.include_hidden ?? false}
          onClick={() =>
            setFilters((f) => ({ ...f, include_hidden: !f.include_hidden || undefined }))
          }
        >
          {filters.include_hidden ? '✓ ' : ''}скрытое
        </button>

        <div style={{ marginLeft: 'auto', display: 'flex', gap: 7, alignItems: 'center' }}>
          <div className="seg">
            <button
              type="button"
              aria-pressed={density === 'standard'}
              onClick={() => setDensity('standard')}
            >
              обычно
            </button>
            <button
              type="button"
              aria-pressed={density === 'compact'}
              onClick={() => setDensity('compact')}
            >
              плотно
            </button>
          </div>
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => setShowHelp(true)}>
            <span className="kbd">?</span>
          </button>
        </div>
      </div>

      {error && (
        <div className="card" style={{ borderColor: 'var(--risk)', marginBottom: 12 }}>
          <b>Не удалось загрузить ленту.</b> {error}
        </div>
      )}

      <div className="feed" ref={listRef}>
        {loading && items.length === 0 && (
          <div className="empty">
            <span className="spinner" /> <p>Загружаю ленту…</p>
          </div>
        )}

        {!loading && items.length === 0 && (
          <div className="empty">
            <h3>Материалов нет</h3>
            <p>
              {query || Object.keys(filters).length > 0
                ? 'Под фильтры ничего не подошло. Сбросьте условия или включите показ шума.'
                : 'Добавьте источник и запустите сбор — материалы появятся здесь.'}
            </p>
          </div>
        )}

        {items.map((item, index) => (
          <div key={item.id}>
            <FeedRow
              item={item}
              focused={index === focusIndex}
              expanded={expandedId === item.id}
              selected={selection.includes(item.id)}
              selectable
              onFocus={() => setFocusIndex(index)}
              onToggle={() => {
                setFocusIndex(index)
                setExpandedId((id) => (id === item.id ? null : item.id))
              }}
              onSelect={(checked) => toggleSelect(item.id, checked)}
            />
            {expandedId === item.id && (
              <ItemDetail
                itemId={item.id}
                onPatch={(patch) => patchRow(item.id, patch)}
                onToast={onToast}
              />
            )}
          </div>
        ))}
      </div>

      {items.length > 0 && (
        <p style={{ marginTop: 10, fontSize: 12, color: 'var(--muted)' }}>
          Показано {items.length} из {plural(total, 'материала', 'материалов', 'материалов')}
          {selection.length > 0 && ` · отобрано в дайджест: ${selection.length}`}
        </p>
      )}

      {showHelp && (
        <div
          className="card"
          style={{ position: 'fixed', right: 24, bottom: 24, width: 300, zIndex: 90 }}
        >
          <p className="block-label">Клавиши</p>
          <table className="grid" style={{ border: 'none' }}>
            <tbody>
              <tr>
                <td>
                  <span className="kbd">j</span> <span className="kbd">↓</span>
                </td>
                <td>следующий материал</td>
              </tr>
              <tr>
                <td>
                  <span className="kbd">k</span> <span className="kbd">↑</span>
                </td>
                <td>предыдущий</td>
              </tr>
              <tr>
                <td>
                  <span className="kbd">Space</span>
                </td>
                <td>раскрыть разбор</td>
              </tr>
              <tr>
                <td>
                  <span className="kbd">Esc</span>
                </td>
                <td>свернуть</td>
              </tr>
            </tbody>
          </table>
          <button
            type="button"
            className="btn btn-sm"
            style={{ marginTop: 8 }}
            onClick={() => setShowHelp(false)}
          >
            Закрыть
          </button>
        </div>
      )}
    </>
  )
}
