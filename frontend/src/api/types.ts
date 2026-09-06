/**
 * Типы ответов API — задача T016.
 *
 * Соответствуют схемам из `specs/001-ai-monitoring-center/contracts/api.openapi.yaml`
 * и реализации в `backend/src/api/schemas.py`. Контракт зафиксирован до кода и
 * служит границей между дорожками: менять форму ответа можно только правкой
 * контракта, а не здесь в одностороннем порядке.
 */

export type ItemType = 'news' | 'act'
export type Topic = 'regulatory' | 'reputation' | 'competitors' | 'trends'
export type Author = 'ai' | 'human'
export type SourceType = 'rss' | 'web' | 'sozd' | 'telegram' | 'manual'
export type SourceCategory = 'media' | 'regulator' | 'telegram'

/** Стадии жизненного цикла НПА — FR-032. */
export type ActStage =
  | 'announcement'
  | 'draft_discussion'
  | 'submitted'
  | 'readings'
  | 'adopted'
  | 'in_force'

export type ActEventType = 'stage_change' | 'new_version' | 'feedback' | 'hearing' | 'other'

/** Категории влияния и актуальности — шкалы из методики заказчика. */
export const IMPACT_CATEGORIES = [
  'Незначительное',
  'Низкое',
  'Среднее',
  'Высокое',
  'Критическое',
] as const

export const RELEVANCE_CATEGORIES = ['Фон', 'На заметку', 'Актуально', 'Горячая тема'] as const

export interface Entities {
  who: string[]
  what: string
  when: string
  consequences: string
}

/** Утверждение саммари с заземлением на оригинал — FR-012, FR-090. */
export interface Claim {
  statement: string
  quote: string
  char_start: number | null
  char_end: number | null
  /** Ступень 1: дословная цитата найдена в исходном тексте. */
  quote_found: boolean
  /** Ступень 2: цитата подтверждает утверждение. null — проверка не выполнялась. */
  entailed: boolean | null
  reject_reason: string | null
}

/** Один критерий в разложении оценки — FR-024. */
export interface CriterionScore {
  code: string
  name: string
  score: number
  max_score: number
  weight: number
  contribution: number
  scale_label: string
  rationale: string
}

export interface Assessment {
  scheme: 'npa_k1_k6' | 'news_h1_h4'
  scores: Record<string, number>
  rationales: Record<string, string>
  breakdown: CriterionScore[]
  index_value: number
  category: string
  escalation_flags: string[]
  final_category: string
  escalated: boolean
  author: Author
  model: string | null
  prompt_version: string | null
  created_at: string
}

export interface SourceRef {
  id: number
  title: string
  type: SourceType
  category: SourceCategory
}

/** Счётчик неподтверждённого: молчаливое отбрасывание рождает недоверие. */
export interface Grounding {
  total: number
  accepted: number
  rejected: number
}

export interface StoryRef {
  id: number
  item_count: number
}

export interface ItemCard {
  id: number
  title: string
  summary: string
  entities: Entities
  item_type: ItemType
  topic: Topic | null
  index_value: number | null
  final_category: string | null
  escalation_flags: string[]
  url: string
  source: SourceRef
  published_at: string
  published_at_is_approx: boolean
  is_partial_text: boolean
  is_relevant: boolean | null
  is_hidden: boolean
  is_edited: boolean
  assessment_failed: boolean
  grounding: Grounding | null
  story_id: number | null
  story: StoryRef | null
  act_id: number | null
  tags: string[]
}

export interface Revision {
  field: string
  old_value: unknown
  new_value: unknown
  author: Author
  reason: string | null
  created_at: string
}

export interface ItemDetail extends ItemCard {
  raw_text: string
  claims: Claim[]
  assessment: Assessment | null
  user_note: string | null
  revisions: Revision[]
  /** Машинная версия сохраняется при правке человеком — FR-042. */
  machine_summary: string | null
  machine_assessment: Assessment | null
}

export interface FeedResponse {
  items: ItemCard[]
  total: number
}

export interface FeedQuery {
  date_from?: string
  date_to?: string
  source_id?: number
  item_type?: ItemType
  topic?: Topic
  category?: string
  q?: string
  include_irrelevant?: boolean
  include_hidden?: boolean
  limit?: number
  offset?: number
}

export interface Source {
  id: number
  type: SourceType
  category: SourceCategory
  item_type: ItemType
  url: string
  title: string
  is_active: boolean
  poll_interval_min: number
  last_polled_at: string | null
  last_error: string | null
  item_count: number
}

export interface CompanyProfile {
  id: number
  slug: string
  name: string
  industry: string
  products: string[]
  regimes: string[]
  risk_areas: string[]
  growth_areas: string[]
  competitors: string[]
  noise_markers: string[]
  is_active: boolean
}

export interface ActEvent {
  event_type: ActEventType
  occurred_at: string
  description: string
  version_label: string | null
  document_url: string | null
  source_item_id: number | null
}

export interface ActCard {
  id: number
  act_identifier: string
  doc_type: string
  stage: ActStage
  index_value: number | null
  final_category: string | null
  is_tracked: boolean
  is_archived: boolean
  effective_from: string | null
}

export interface ActDetail extends ActCard {
  essence: string
  source_url: string
  timeline: ActEvent[]
  /** История оценок — динамика влияния во времени, FR-035. */
  assessment_history: Assessment[]
  linked_items: ItemCard[]
}

export interface StoryMember {
  id: number
  title: string
  url: string
  source: SourceRef
  published_at: string
}

export interface Story {
  id: number
  canonical_title: string
  fact_summary: string
  first_seen_at: string
  item_count: number
  was_split_by_user: boolean
  items: StoryMember[]
}

export interface DigestEntry {
  position: number
  is_excluded: boolean
  item: ItemCard
}

export interface Digest {
  id: number
  recipient: string
  title: string
  created_at: string
  entries: DigestEntry[]
}
