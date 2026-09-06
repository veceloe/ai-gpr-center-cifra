/**
 * Заземление саммари — FR-025, FR-092.
 *
 * Каждое утверждение показывается вместе с цитатой, которая его подтверждает.
 * Отбракованные утверждения не прячутся, а показываются со счётчиком и причиной:
 * молчаливое отбрасывание рождает страх пропуска и возвращает специалиста
 * в параллельный Excel.
 */

import { useState } from 'react'
import type { Claim, Grounding } from '../api/types'

const REJECT_REASONS: Record<string, string> = {
  quote_not_found: 'цитата не найдена в оригинале',
  not_entailed: 'цитата не подтверждает утверждение',
  verification_unavailable: 'проверка была недоступна',
}

interface Props {
  claims: Claim[]
  grounding: Grounding | null
  rawText: string
}

export function Claims({ claims, grounding, rawText }: Props) {
  const [showRejected, setShowRejected] = useState(false)

  const accepted = claims.filter((c) => c.quote_found && c.entailed)
  const rejected = claims.filter((c) => !(c.quote_found && c.entailed))

  if (claims.length === 0) {
    return (
      <div>
        <p className="block-label">Заземление</p>
        <p className="grounding-line">
          Материал ещё не обработан — утверждений с цитатами нет.
        </p>
      </div>
    )
  }

  return (
    <div>
      <p className="block-label">Утверждения и подтверждения из оригинала</p>

      <div className="claims">
        {accepted.map((claim, i) => (
          <ClaimCard key={`ok-${i}`} claim={claim} rawText={rawText} />
        ))}

        {showRejected &&
          rejected.map((claim, i) => (
            <ClaimCard key={`no-${i}`} claim={claim} rawText={rawText} rejected />
          ))}
      </div>

      {grounding && (
        <p className="grounding-line">
          Проверено утверждений: <b>{grounding.total}</b>, подтверждено{' '}
          <b>{grounding.accepted}</b>
          {rejected.length > 0 && (
            <>
              {', не подтверждено '}
              <b>{grounding.rejected}</b>{' '}
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => setShowRejected((v) => !v)}
              >
                {showRejected ? 'скрыть' : 'посмотреть'}
              </button>
            </>
          )}
        </p>
      )}
    </div>
  )
}

function ClaimCard({
  claim,
  rawText,
  rejected,
}: {
  claim: Claim
  rawText: string
  rejected?: boolean
}) {
  // Смещения указывают в оригинал: показываем фрагмент так, как он есть
  // в исходном тексте, а не пересказ модели.
  const quote =
    claim.char_start !== null && claim.char_end !== null
      ? rawText.slice(claim.char_start, claim.char_end)
      : claim.quote

  return (
    <div className="claim" data-rejected={rejected}>
      <p>{claim.statement}</p>
      {quote && <p className="quote">«{quote}»</p>}
      {rejected && claim.reject_reason && (
        <p className="reject-note">
          Отброшено: {REJECT_REASONS[claim.reject_reason] ?? claim.reject_reason}
        </p>
      )}
    </div>
  )
}
