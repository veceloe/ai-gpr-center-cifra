/**
 * Раскрытие карточки прямо в ленте — FR-024, FR-025, FR-040, FR-041, FR-044, FR-045.
 *
 * Раскрывается вниз, по месту: пользователь не теряет позицию в ленте.
 * Слева — заземление саммари, справа — разбор оценки.
 */

import { useEffect, useState } from 'react'
import { ApiError, api } from '../api/client'
import type { ItemDetail as ItemDetailType } from '../api/types'
import { formatFullDate } from '../lib/format'
import { Claims } from './Claims'
import { ScoreBreakdown } from './ScoreBreakdown'

interface Props {
  itemId: number
  /**
   * Точечное обновление строки в ленте вместо перезагрузки списка.
   * Перезагрузка пересортировывает ленту по индексу, и карточка уезжает
   * из-под курсора — пользователь теряет место ровно в тот момент, когда
   * работает с материалом.
   */
  onPatch: (patch: Partial<ItemCardPatch>) => void
  onToast: (message: string, undo?: () => void) => void
}

/** Поля строки ленты, которые может изменить работа в карточке. */
export interface ItemCardPatch {
  summary: string
  index_value: number | null
  final_category: string | null
  is_edited: boolean
  is_hidden: boolean
  user_note: string | null
  act_id: number | null
}

export function ItemDetail({ itemId, onPatch, onToast }: Props) {
  const [item, setItem] = useState<ItemDetailType | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState('')
  const [editingSummary, setEditingSummary] = useState(false)
  const [summaryDraft, setSummaryDraft] = useState('')

  useEffect(() => {
    let alive = true
    setError(null)
    api
      .item(itemId)
      .then((data) => {
        if (!alive) return
        setItem(data)
        setNote(data.user_note ?? '')
        setSummaryDraft(data.summary)
      })
      .catch((e: ApiError) => alive && setError(e.message))
    return () => {
      alive = false
    }
  }, [itemId])

  if (error) {
    return (
      <div className="detail">
        <p className="grounding-line" style={{ color: 'var(--risk)' }}>
          {error}
        </p>
      </div>
    )
  }

  if (!item) {
    return (
      <div className="detail">
        <span className="spinner" /> <span className="grounding-line">Загружаю карточку…</span>
      </div>
    )
  }

  /** Оптимистичная правка балла: индекс пересчитан на клиенте, откат по кнопке. */
  async function changeScore(code: string, score: number) {
    if (!item?.assessment) return
    const before = item.assessment
    setBusy(true)
    try {
      const updated = await api.patchAssessment(item.id, { [code]: score })
      setItem({ ...item, assessment: updated, index_value: updated.index_value, is_edited: true })
      onPatch({
        index_value: updated.index_value,
        final_category: updated.final_category,
        is_edited: true,
      })
      onToast(
        `Индекс ${before.index_value.toFixed(1)} → ${updated.index_value.toFixed(1)}`,
        async () => {
          const reverted = await api.patchAssessment(item.id, { [code]: before.scores[code]! })
          setItem((prev) => (prev ? { ...prev, assessment: reverted } : prev))
          onPatch({ index_value: reverted.index_value, final_category: reverted.final_category })
        },
      )
    } catch (e) {
      onToast((e as ApiError).message)
    } finally {
      setBusy(false)
    }
  }

  async function saveNote() {
    if (!item) return
    const updated = await api.patchItem(item.id, { user_note: note || null })
    setItem(updated)
    onPatch({ user_note: updated.user_note, is_edited: true })
    onToast('Пометка сохранена')
  }

  async function saveSummary() {
    if (!item) return
    const updated = await api.patchItem(item.id, { summary: summaryDraft })
    setItem(updated)
    setEditingSummary(false)
    onPatch({ summary: updated.summary, is_edited: true })
    onToast('Саммари сохранено. Машинная версия осталась в истории')
  }

  async function hide() {
    if (!item) return
    await api.hideItem(item.id, !item.is_hidden, 'не относится к профилю компании')
    setItem({ ...item, is_hidden: !item.is_hidden })
    onPatch({ is_hidden: !item.is_hidden })
    onToast(item.is_hidden ? 'Материал возвращён в ленту' : 'Материал скрыт из ленты')
  }

  async function trackAsAct() {
    if (!item) return
    try {
      const act = await api.trackAsAct(item.id)
      setItem({ ...item, act_id: act.id })
      onPatch({ act_id: act.id })
      onToast(`Досье создано: ${act.act_identifier}`)
    } catch (e) {
      onToast((e as ApiError).message)
    }
  }

  return (
    <div className="detail">
      <div className="detail-grid">
        <div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 8 }}>
            <p className="block-label" style={{ margin: 0 }}>
              Саммари
            </p>
            {!editingSummary && (
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => setEditingSummary(true)}
              >
                исправить
              </button>
            )}
            {item.machine_summary && item.machine_summary !== item.summary && (
              <span className="badge badge-edited" title={item.machine_summary}>
                машинная версия сохранена
              </span>
            )}
          </div>

          {editingSummary ? (
            <div className="form-row">
              <textarea
                value={summaryDraft}
                onChange={(e) => setSummaryDraft(e.target.value)}
                aria-label="Текст саммари"
              />
              <div style={{ display: 'flex', gap: 6 }}>
                <button type="button" className="btn btn-primary btn-sm" onClick={saveSummary}>
                  Сохранить
                </button>
                <button
                  type="button"
                  className="btn btn-sm"
                  onClick={() => {
                    setEditingSummary(false)
                    setSummaryDraft(item.summary)
                  }}
                >
                  Отмена
                </button>
              </div>
            </div>
          ) : (
            <p style={{ margin: '0 0 12px', fontSize: 13.5, lineHeight: 1.5 }}>
              {item.summary || <span style={{ color: 'var(--faint)' }}>Саммари пока нет</span>}
            </p>
          )}

          <Claims claims={item.claims} grounding={item.grounding} rawText={item.raw_text} />

          {(item.entities.who.length > 0 || item.entities.consequences) && (
            <div style={{ marginTop: 14 }}>
              <p className="block-label">Ключевые сущности</p>
              <table className="grid">
                <tbody>
                  {item.entities.who.length > 0 && (
                    <tr>
                      <td style={{ width: 110, color: 'var(--muted)' }}>Кто</td>
                      <td>{item.entities.who.join(', ')}</td>
                    </tr>
                  )}
                  {item.entities.what && (
                    <tr>
                      <td style={{ color: 'var(--muted)' }}>Что</td>
                      <td>{item.entities.what}</td>
                    </tr>
                  )}
                  {item.entities.when && (
                    <tr>
                      <td style={{ color: 'var(--muted)' }}>Когда</td>
                      <td>{item.entities.when}</td>
                    </tr>
                  )}
                  {item.entities.consequences && (
                    <tr>
                      <td style={{ color: 'var(--muted)' }}>Последствия</td>
                      <td>{item.entities.consequences}</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div>
          {item.assessment ? (
            <ScoreBreakdown
              assessment={item.assessment}
              machine={item.machine_assessment}
              onScoreChange={changeScore}
              busy={busy}
            />
          ) : (
            <div>
              <p className="block-label">Оценка</p>
              <p className="grounding-line">
                {item.assessment_failed
                  ? 'Модель не вернула пригодную оценку. Материал сохранён и доступен — это осознанное поведение, а не потеря.'
                  : 'Материал ещё не обработан.'}
              </p>
            </div>
          )}

          <div style={{ marginTop: 16 }}>
            <p className="block-label">Рабочая пометка</p>
            <div className="form-row">
              <input
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="например: обсудить на совещании 15-го"
                aria-label="Рабочая пометка"
              />
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                <button type="button" className="btn btn-sm" onClick={saveNote}>
                  Сохранить пометку
                </button>
                <button type="button" className="btn btn-sm" onClick={hide}>
                  {item.is_hidden ? 'Вернуть в ленту' : 'Скрыть из ленты'}
                </button>
                {item.item_type === 'act' && !item.act_id && (
                  <button type="button" className="btn btn-sm" onClick={trackAsAct}>
                    Взять на отслеживание
                  </button>
                )}
                {item.act_id && (
                  <a className="btn btn-sm" href={`#/acts/${item.act_id}`}>
                    Открыть досье
                  </a>
                )}
              </div>
            </div>
          </div>

          {item.revisions.length > 0 && (
            <div style={{ marginTop: 16 }}>
              <p className="block-label">Журнал правок</p>
              <table className="grid">
                <tbody>
                  {item.revisions.slice(0, 6).map((rev, i) => (
                    <tr key={i}>
                      <td style={{ width: 96, color: 'var(--muted)' }}>{rev.field}</td>
                      <td>
                        {String(rev.old_value ?? '—').slice(0, 60)} →{' '}
                        <b>{String(rev.new_value ?? '—').slice(0, 60)}</b>
                        {rev.reason && (
                          <div style={{ color: 'var(--muted)', fontSize: 11.5 }}>{rev.reason}</div>
                        )}
                      </td>
                      <td className="num" style={{ width: 110, color: 'var(--faint)' }}>
                        {formatFullDate(rev.created_at)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
