/**
 * Разложение оценки по критериям — FR-024, FR-041.
 *
 * Раскрытие идёт ВНИЗ по месту, а не в боковой панели: шесть баллов
 * математически складываются в индекс, а по юзабилити-тесту IBM (23 участника,
 * 21 из 23 понимали связь) именно этот случай требует вертикального
 * инлайн-раскрытия. Боковая панель годится, когда деталь — дополнительный
 * контекст, а не слагаемые итога.
 *
 * Балл правится сегментированным контролом 0-3, а не полем ввода: один клик,
 * нет валидации, нет ошибок ввода. Пересчёт индекса — оптимистичный, на клиенте,
 * с возможностью отмены; диалога подтверждения нет.
 */

import { useMemo, useState } from 'react'
import type { Assessment, CriterionScore } from '../api/types'

interface Props {
  assessment: Assessment
  /** Машинная версия — чтобы показать, где человек разошёлся с моделью. */
  machine?: Assessment | null
  onScoreChange?: (code: string, score: number) => void
  busy?: boolean
}

/** Индекс по методике заказчика: сумма (балл × вес), делённая на 3, умноженная на 100. */
function computeIndex(breakdown: CriterionScore[], scores: Record<string, number>): number {
  const weighted = breakdown.reduce((sum, c) => sum + (scores[c.code] ?? c.score) * c.weight, 0)
  return Math.round((weighted / 3) * 1000) / 10
}

export function ScoreBreakdown({ assessment, machine, onScoreChange, busy }: Props) {
  const [draft, setDraft] = useState<Record<string, number>>({})

  const scores = useMemo(
    () => ({ ...assessment.scores, ...draft }),
    [assessment.scores, draft],
  )
  const liveIndex = useMemo(
    () => computeIndex(assessment.breakdown, scores),
    [assessment.breakdown, scores],
  )
  const changed = liveIndex !== assessment.index_value

  function setScore(code: string, value: number) {
    if (!onScoreChange || busy) return
    setDraft((prev) => ({ ...prev, [code]: value }))
    onScoreChange(code, value)
  }

  return (
    <div>
      <p className="block-label">
        Разбор оценки: {assessment.breakdown.length}{' '}
        {assessment.scheme === 'npa_k1_k6' ? 'критериев влияния' : 'критерия актуальности'}
      </p>

      <div className="criteria">
        {assessment.breakdown.map((criterion) => {
          const current = scores[criterion.code] ?? criterion.score
          const machineScore = machine?.scores[criterion.code]
          const divergent = machineScore !== undefined && machineScore !== current
          return (
            <div
              key={criterion.code}
              className="criterion"
              data-edited={divergent || draft[criterion.code] !== undefined}
            >
              <span className="criterion-code">{criterion.code}</span>

              <div className="criterion-name">
                {criterion.name}
                <div className="criterion-scale">{criterion.scale_label}</div>
              </div>

              <div
                className="score-seg"
                role="group"
                aria-label={`Балл по критерию ${criterion.code}`}
              >
                {[0, 1, 2, 3].map((value) => (
                  <button
                    key={value}
                    type="button"
                    aria-pressed={current === value}
                    aria-label={`${criterion.code}: ${value}`}
                    disabled={!onScoreChange || busy}
                    onClick={() => setScore(criterion.code, value)}
                  >
                    {value}
                  </button>
                ))}
              </div>

              <span className="criterion-contrib" title="Вклад в индекс">
                +{((current * criterion.weight) / 3 * 100).toFixed(1)}
              </span>

              {criterion.rationale && <p className="rationale">{criterion.rationale}</p>}
              {divergent && (
                <p className="rationale" style={{ color: 'var(--brand-hover)' }}>
                  Модель давала {machineScore}, у вас {current}
                </p>
              )}
            </div>
          )
        })}
      </div>

      <div className="index-summary">
        {changed && <span className="was">{assessment.index_value.toFixed(1)}</span>}
        <span className="big">{liveIndex.toFixed(1)}</span>
        <span style={{ fontSize: 13 }}>{assessment.final_category}</span>
        {assessment.escalated && (
          <span className="badge badge-risk" title={assessment.escalation_flags.join('\n')}>
            эскалация: {assessment.category} → {assessment.final_category}
          </span>
        )}
        {busy && <span className="spinner" aria-label="Сохранение" />}
      </div>

      {assessment.prompt_version && (
        <p className="grounding-line" style={{ marginTop: 6 }}>
          Оценка: {assessment.author === 'human' ? 'скорректирована человеком' : 'модель'}
          {assessment.model ? ` · ${assessment.model}` : ''} · промпт{' '}
          {assessment.prompt_version}
        </p>
      )}
    </div>
  )
}
