/**
 * Досье НПА — US3, FR-030…FR-037.
 *
 * Отдельная страница, а не панель: по правилу Cloudscape split view не заменяет
 * detail page, а здесь именно глубокий разбор одного объекта — стадии,
 * хронология, динамика влияния.
 *
 * Трекер стадий имеет ЧЕТЫРЕ состояния, включая «неприменима». Российские акты
 * стадии пропускают: акт отзывают, возвращают субъекту инициативы, принимают без
 * отдельного чтения, а указ Президента чтений не проходит вовсе. Линейная шкала
 * без этого состояния лжёт — ровно этот дефект остался в исходниках закрытого
 * трекера Open States комментарием «TODO: veto, failure, etc?».
 */

import { useCallback, useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { ApiError, api } from '../api/client'
import type { ActDetail, ActStage } from '../api/types'
import { FeedRow } from '../components/FeedRow'
import {
  ACT_STAGES,
  EVENT_LABELS,
  STAGE_LABELS,
  actTitle,
  formatFullDate,
  formatIndex,
  hasCanonicalNumber,
} from '../lib/format'

interface Props {
  onToast: (message: string, undo?: () => void) => void
}

type StageState = 'done' | 'current' | 'skipped' | 'pending'

/**
 * Состояние стадии. Правило отрисовки пропущенной сформулировано явно, как
 * в EU Law Tracker: шаг «не достигнут» и шаг «пропущен» выглядят по-разному,
 * иначе трекер вводит в заблуждение.
 */
function stageState(stage: ActStage, current: ActStage, timeline: ActDetail['timeline']): StageState {
  const index = ACT_STAGES.indexOf(stage)
  const currentIndex = ACT_STAGES.indexOf(current)
  if (index === currentIndex) return 'current'
  if (index > currentIndex) return 'pending'
  // Стадия позади текущей: если в хронологии нет ни одного упоминания — её пропустили.
  const mentioned = timeline.some((e) => e.description.toLowerCase().includes(STAGE_LABELS[stage].toLowerCase()))
  return mentioned ? 'done' : 'skipped'
}

const STATE_MARK: Record<StageState, string> = {
  done: 'пройдена',
  current: 'идёт',
  skipped: 'неприменима',
  pending: 'не достигнута',
}

export function ActPage({ onToast }: Props) {
  const { id } = useParams<{ id: string }>()
  const actId = Number(id)
  const [act, setAct] = useState<ActDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    try {
      setAct(await api.act(actId))
      setError(null)
    } catch (e) {
      setError((e as ApiError).message)
    }
  }, [actId])

  useEffect(() => {
    void load()
  }, [load])

  async function changeStage(stage: ActStage) {
    if (!act || stage === act.stage) return
    setBusy(true)
    try {
      const updated = await api.patchAct(act.id, { stage })
      setAct(updated)
      onToast(
        `Стадия: ${STAGE_LABELS[act.stage]} → ${STAGE_LABELS[stage]}. Связанные материалы отправлены на переоценку`,
      )
    } catch (e) {
      onToast((e as ApiError).message)
    } finally {
      setBusy(false)
    }
  }

  async function toggleArchive() {
    if (!act) return
    const updated = await api.patchAct(act.id, { is_archived: !act.is_archived })
    setAct(updated)
    onToast(updated.is_archived ? 'Досье в архиве, хронология сохранена' : 'Досье возвращено в работу')
  }

  if (error) {
    return (
      <div className="card" style={{ borderColor: 'var(--risk)' }}>
        <b>Не удалось открыть досье.</b> {error}
      </div>
    )
  }
  if (!act) {
    return (
      <div className="empty">
        <span className="spinner" /> <p>Загружаю досье…</p>
      </div>
    )
  }

  const history = act.assessment_history
  const currentIdx = history.find((a) => a.author !== undefined)
  const previous = history.length > 1 ? history[history.length - 2] : undefined

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap' }}>
          <div style={{ minWidth: 0 }}>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              <span className="badge badge-act">{act.doc_type}</span>
              {act.is_archived && <span className="badge">в архиве</span>}
              {act.is_tracked && !act.is_archived && (
                <span className="badge badge-brand">на отслеживании</span>
              )}
            </div>
            <h2 style={{ fontFamily: 'var(--font-head)', fontSize: 18, margin: '8px 0 4px' }}>
              {actTitle(act.act_identifier, act.essence)}
            </h2>
            {!hasCanonicalNumber(act.act_identifier) && (
              <p style={{ margin: '0 0 6px', fontSize: 12, color: 'var(--muted)' }}>
                Номер акта не распознан — материал не прошёл классификацию. Он появится
                после обработки моделью или его можно указать вручную.
              </p>
            )}
            <p style={{ margin: 0, fontSize: 13.5, color: 'var(--muted)', maxWidth: '68ch' }}>
              {act.essence}
            </p>
          </div>

          <div style={{ textAlign: 'right' }}>
            {act.index_value !== null && (
              <>
                <div className="index-num" style={{ fontSize: 26 }}>
                  {formatIndex(act.index_value)}
                </div>
                <div className="index-cat">{act.final_category}</div>
                {previous && currentIdx && previous.index_value !== currentIdx.index_value && (
                  <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 4 }}>
                    было {previous.index_value.toFixed(1)}
                  </div>
                )}
              </>
            )}
            <div style={{ display: 'flex', gap: 6, marginTop: 10, justifyContent: 'flex-end' }}>
              <a className="btn btn-sm" href={act.source_url} target="_blank" rel="noreferrer">
                первоисточник
              </a>
              <button type="button" className="btn btn-sm" onClick={toggleArchive}>
                {act.is_archived ? 'вернуть' : 'в архив'}
              </button>
            </div>
          </div>
        </div>

        <p className="block-label" style={{ marginTop: 18 }}>
          Стадия жизненного цикла {busy && <span className="spinner" />}
        </p>
        <div className="stages">
          {ACT_STAGES.map((stage) => {
            const state = stageState(stage, act.stage, act.timeline)
            return (
              <button
                key={stage}
                type="button"
                className="stage"
                data-state={state}
                disabled={busy || act.is_archived}
                onClick={() => changeStage(stage)}
                title={`Отметить стадию «${STAGE_LABELS[stage]}»`}
              >
                {STAGE_LABELS[stage]}
                <span className="stage-mark">{STATE_MARK[state]}</span>
              </button>
            )
          })}
        </div>
        <p className="grounding-line">
          Нажатие на стадию меняет её и записывает событие в хронологию. Связанные
          материалы отправляются на переоценку: юридическая сила входит в критерий К2.
        </p>
      </div>

      <div className="cards two">
        <div className="card">
          <p className="block-label">Хронология · {act.timeline.length}</p>
          {act.timeline.length === 0 ? (
            <p className="grounding-line">Событий пока нет.</p>
          ) : (
            <div className="timeline">
              {[...act.timeline].reverse().map((event, i) => (
                <div key={i} className="tl-item" data-kind={event.event_type}>
                  <div className="tl-date">
                    {formatFullDate(event.occurred_at)} · {EVENT_LABELS[event.event_type]}
                  </div>
                  <p className="tl-text">{event.description}</p>
                  {event.version_label && (
                    <span className="badge" style={{ marginTop: 4 }}>
                      {event.version_label}
                    </span>
                  )}
                  {event.document_url && (
                    <div style={{ marginTop: 4 }}>
                      <a
                        href={event.document_url}
                        target="_blank"
                        rel="noreferrer"
                        style={{ fontSize: 12 }}
                      >
                        документ
                      </a>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="card">
          <p className="block-label">Динамика влияния · {history.length}</p>
          {history.length === 0 ? (
            <p className="grounding-line">Оценок пока нет.</p>
          ) : (
            <>
              <ImpactChart history={history} />
              <table className="grid" style={{ marginTop: 12 }}>
                <thead>
                  <tr>
                    <th>Дата</th>
                    <th>Индекс</th>
                    <th>Категория</th>
                    <th>Автор</th>
                  </tr>
                </thead>
                <tbody>
                  {[...history].reverse().map((a, i) => (
                    <tr key={i}>
                      <td className="num">{formatFullDate(a.created_at)}</td>
                      <td className="num">{a.index_value.toFixed(1)}</td>
                      <td>{a.final_category}</td>
                      <td>{a.author === 'human' ? 'человек' : 'модель'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </div>
      </div>

      <div>
        <p className="block-label">Связанные материалы · {act.linked_items.length}</p>
        {act.linked_items.length === 0 ? (
          <div className="card">
            <p className="grounding-line">
              К досье пока не привязан ни один материал. Материалы связываются
              автоматически по идентификатору акта при обработке.
            </p>
          </div>
        ) : (
          <div className="feed">
            {act.linked_items.map((item) => (
              <FeedRow
                key={item.id}
                item={item}
                focused={false}
                expanded={false}
                selected={false}
                selectable={false}
                onFocus={() => {}}
                onToggle={() => window.open(item.url, '_blank')}
                onSelect={() => {}}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

/** Спарклайн истории оценок: видно, куда движется влияние, а не только текущее. */
function ImpactChart({ history }: { history: ActDetail['assessment_history'] }) {
  if (history.length < 2) {
    return (
      <p className="grounding-line">
        Для графика нужна хотя бы вторая оценка — она появится при смене стадии.
      </p>
    )
  }

  const w = 100
  const h = 40
  const values = history.map((a) => a.index_value)
  const max = Math.max(...values, 100)
  const points = values
    .map((v, i) => `${(i / (values.length - 1)) * w},${h - (v / max) * h}`)
    .join(' ')

  return (
    <svg viewBox={`0 0 ${w} ${h}`} width="100%" height="70" role="img"
         aria-label={`Динамика индекса: от ${values[0]!.toFixed(1)} до ${values.at(-1)!.toFixed(1)}`}>
      <polyline
        points={points}
        fill="none"
        stroke="var(--brand)"
        strokeWidth="1.6"
        vectorEffect="non-scaling-stroke"
      />
      {values.map((v, i) => (
        <circle
          key={i}
          cx={(i / (values.length - 1)) * w}
          cy={h - (v / max) * h}
          r="1.6"
          fill="var(--brand-hover)"
        />
      ))}
    </svg>
  )
}
