/** Список досье НПА — US3. */

import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError, api } from '../api/client'
import type { ActCard } from '../api/types'
import { STAGE_LABELS, actTitle, formatIndex, isDimmed } from '../lib/format'

export function ActsPage() {
  const [acts, setActs] = useState<ActCard[]>([])
  const [archived, setArchived] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    api
      .acts({ archived })
      .then(setActs)
      .catch((e: ApiError) => setError(e.message))
      .finally(() => setLoading(false))
  }, [archived])

  return (
    <>
      <div className="filters">
        <div className="seg">
          <button type="button" aria-pressed={!archived} onClick={() => setArchived(false)}>
            на отслеживании
          </button>
          <button type="button" aria-pressed={archived} onClick={() => setArchived(true)}>
            архив
          </button>
        </div>
      </div>

      {error && (
        <div className="card" style={{ borderColor: 'var(--risk)' }}>
          <b>Не удалось загрузить досье.</b> {error}
        </div>
      )}

      {loading && <div className="empty"><span className="spinner" /> <p>Загружаю…</p></div>}

      {!loading && acts.length === 0 && (
        <div className="empty">
          <h3>{archived ? 'В архиве пусто' : 'Досье пока нет'}</h3>
          <p>
            Откройте материал типа НПА в ленте и нажмите «Взять на отслеживание» —
            он станет долгоживущим досье со стадиями и хронологией.
          </p>
        </div>
      )}

      {acts.length > 0 && (
        <table className="grid">
          <thead>
            <tr>
              <th style={{ width: 70 }}>Индекс</th>
              <th>Акт</th>
              <th style={{ width: 130 }}>Стадия</th>
              <th style={{ width: 110 }}>Категория</th>
              <th style={{ width: 90 }}>Событий</th>
              <th style={{ width: 100 }}>Материалов</th>
            </tr>
          </thead>
          <tbody>
            {acts.map((act) => (
              <tr key={act.id}>
                <td className="num" style={{ opacity: isDimmed(act.final_category) ? 0.55 : 1 }}>
                  {formatIndex(act.index_value)}
                </td>
                <td>
                  <Link to={`/acts/${act.id}`} style={{ fontWeight: 500 }}>
                    {actTitle(act.act_identifier, act.essence)}
                  </Link>
                  <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: 2 }}>
                    {act.essence.slice(0, 150)}
                  </div>
                </td>
                <td>
                  <span className="badge">{STAGE_LABELS[act.stage]}</span>
                </td>
                <td>{act.final_category ?? '—'}</td>
                <td className="num">{act.timeline_count}</td>
                <td className="num">{act.linked_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  )
}
