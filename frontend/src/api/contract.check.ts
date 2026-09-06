/**
 * Сверка ручных типов с фактическим контрактом API — защита от расхождения.
 *
 * ПОЧЕМУ ЭТОТ ФАЙЛ СУЩЕСТВУЕТ. Типы в `types.ts` писались руками и однажды
 * разошлись с backend: список досье был объявлен как `ActDetail[]`, хотя
 * `GET /api/acts` отдаёт `ActCard` без поля `essence`. TypeScript промолчал —
 * он проверял код против вымысла, — и страница упала в браузере на
 * `essence.split(...)`.
 *
 * Здесь ручные типы сверяются с типами, сгенерированными из фактической
 * спецификации FastAPI. Расхождение становится ошибкой компиляции, а не
 * сюрпризом у пользователя.
 *
 * Как обновить после изменения API:
 *   cd backend && PYTHONPATH=. python -m src.cli export-openapi
 *   cd frontend && npm run types:api && npm run typecheck
 *
 * Файл ничего не экспортирует в рантайме: он существует только ради проверок.
 */

import type { components } from './schema'
import type {
  ActCard,
  ActDetail,
  ActEvent,
  Assessment,
  Claim,
  CompanyProfile,
  CriterionScore,
  Digest,
  FeedResponse,
  ItemCard,
  ItemDetail,
  Source,
  Story,
} from './types'

type Schemas = components['schemas']

/**
 * Наборы полей должны совпадать ровно. Именно это ловит ошибку, на которой
 * упало досье: в ручном типе было поле, которого сервер не отдаёт.
 */
type MissingInManual<M, S> = Exclude<keyof S, keyof M>
type ExtraInManual<M, S> = Exclude<keyof M, keyof S>

/**
 * Сужение допускается: `item_type: 'news' | 'act'` строже, чем `string`
 * из спецификации, и это осознанно. Расширение — нет.
 */
type Compatible<M, S> = M extends S ? true : never

function assertSameShape<M, S>(
  _keysNotInManual: MissingInManual<M, S> extends never ? true : MissingInManual<M, S>,
  _keysNotInSchema: ExtraInManual<M, S> extends never ? true : ExtraInManual<M, S>,
): void {
  /* проверка выполняется компилятором; тела не требуется */
}

function assertCompatible<M, S>(_witness: Compatible<M, S>): void {
  /* проверка выполняется компилятором */
}

// --- Ответы, на которых держатся экраны --------------------------------------
assertSameShape<ItemCard, Schemas['ItemCardOut']>(true, true)
assertSameShape<ItemDetail, Schemas['ItemDetailOut']>(true, true)
assertSameShape<FeedResponse, Schemas['FeedResponse']>(true, true)
assertSameShape<Assessment, Schemas['AssessmentOut']>(true, true)
assertSameShape<CriterionScore, Schemas['CriterionScoreOut']>(true, true)
assertSameShape<Claim, Schemas['ClaimOut']>(true, true)

// --- Досье: именно здесь ручные типы разошлись с контрактом -------------------
assertSameShape<ActCard, Schemas['ActCardOut']>(true, true)
assertSameShape<ActDetail, Schemas['ActDetailOut']>(true, true)
assertSameShape<ActEvent, Schemas['ActEventOut']>(true, true)

assertSameShape<Source, Schemas['SourceOut']>(true, true)
assertSameShape<CompanyProfile, Schemas['ProfileOut']>(true, true)
assertSameShape<Story, Schemas['StoryOut']>(true, true)
assertSameShape<Digest, Schemas['DigestOut']>(true, true)

// Совместимость значений там, где мы не сужали типы намеренно.
assertCompatible<CriterionScore, Schemas['CriterionScoreOut']>(true)
assertCompatible<Claim, Schemas['ClaimOut']>(true)
assertCompatible<ActEvent, Schemas['ActEventOut']>(true)

export {}
