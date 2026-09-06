/**
 * Клиент API — задача T016.
 *
 * В dev-режиме запросы идут на /api через прокси Vite (см. vite.config.ts),
 * в сборке — на тот же origin, который отдаёт статику. Поэтому базовый путь
 * один и тот же и не требует переменных окружения.
 */

import type {
  ActDetail,
  ActEventType,
  ActStage,
  Assessment,
  CompanyProfile,
  Digest,
  FeedQuery,
  FeedResponse,
  ItemDetail,
  ItemType,
  Source,
  SourceCategory,
  SourceType,
  Story,
} from './types'

const BASE = '/api'

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(BASE + path, {
      ...init,
      headers: init?.body ? { 'Content-Type': 'application/json', ...init?.headers } : init?.headers,
    })
  } catch {
    // Сеть недоступна — сообщение должно объяснять, что делать, а не извиняться.
    throw new ApiError(0, 'Сервер не отвечает. Проверьте, что backend запущен на :8000.')
  }

  if (!response.ok) {
    let detail = `Запрос не выполнен (${response.status})`
    try {
      const body = await response.json()
      if (typeof body?.detail === 'string') detail = body.detail
      else if (Array.isArray(body?.detail) && body.detail[0]?.msg) detail = body.detail[0].msg
    } catch {
      /* тело не JSON — оставляем сообщение по статусу */
    }
    throw new ApiError(response.status, detail)
  }

  if (response.status === 204) return undefined as T
  const type = response.headers.get('content-type') ?? ''
  return (type.includes('application/json') ? response.json() : response.text()) as Promise<T>
}

function query(params: object): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params as Record<string, unknown>)) {
    if (value === undefined || value === null || value === '') continue
    search.set(key, String(value))
  }
  const encoded = search.toString()
  return encoded ? `?${encoded}` : ''
}

export const api = {
  health: () => request<{ status: string }>('/health'),

  // --- лента и карточки -----------------------------------------------------
  feed: (params: FeedQuery = {}) => request<FeedResponse>(`/feed${query(params)}`),

  item: (id: number) => request<ItemDetail>(`/items/${id}`),

  createItem: (payload: {
    title: string
    raw_text: string
    url?: string
    published_at?: string
  }) => request<ItemDetail>('/items', { method: 'POST', body: JSON.stringify(payload) }),

  patchItem: (
    id: number,
    payload: {
      title?: string
      summary?: string
      topic?: string
      tags?: string[]
      user_note?: string | null
    },
  ) => request<ItemDetail>(`/items/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),

  /** Правка балла с немедленным пересчётом индекса — FR-041. */
  patchAssessment: (id: number, scores: Record<string, number>) =>
    request<Assessment>(`/items/${id}/assessment`, {
      method: 'PATCH',
      body: JSON.stringify({ scores }),
    }),

  hideItem: (id: number, hidden: boolean, reason?: string) =>
    request<void>(`/items/${id}/hide`, {
      method: 'POST',
      body: JSON.stringify({ hidden, reason }),
    }),

  // --- досье НПА ------------------------------------------------------------
  acts: (params: { stage?: ActStage; archived?: boolean } = {}) =>
    request<ActDetail[]>(`/acts${query(params)}`),

  act: (id: number) => request<ActDetail>(`/acts/${id}`),

  patchAct: (
    id: number,
    payload: { stage?: ActStage; is_archived?: boolean; is_tracked?: boolean; essence?: string },
  ) => request<ActDetail>(`/acts/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),

  addActEvent: (
    id: number,
    payload: {
      event_type: ActEventType
      occurred_at: string
      description: string
      version_label?: string
      document_url?: string
    },
  ) => request<ActDetail>(`/acts/${id}/events`, { method: 'POST', body: JSON.stringify(payload) }),

  linkItemToAct: (actId: number, itemId: number) =>
    request<ActDetail>(`/acts/${actId}/link-item`, {
      method: 'POST',
      body: JSON.stringify({ item_id: itemId }),
    }),

  trackAsAct: (itemId: number) =>
    request<ActDetail>(`/items/${itemId}/track-as-act`, { method: 'POST' }),

  // --- кластеры дублей ------------------------------------------------------
  story: (id: number) => request<Story>(`/stories/${id}`),

  splitStory: (id: number) => request<void>(`/stories/${id}/split`, { method: 'POST' }),

  // --- источники ------------------------------------------------------------
  sources: () => request<Source[]>('/sources'),

  createSource: (payload: {
    type: SourceType
    url: string
    title?: string
    category?: SourceCategory
    item_type?: ItemType
  }) => request<Source>('/sources', { method: 'POST', body: JSON.stringify(payload) }),

  patchSource: (
    id: number,
    payload: { title?: string; is_active?: boolean; poll_interval_min?: number },
  ) => request<Source>(`/sources/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),

  deleteSource: (id: number) => request<void>(`/sources/${id}`, { method: 'DELETE' }),

  collectNow: (id: number) =>
    request<{ status: string; source: string }>(`/sources/${id}/collect`, { method: 'POST' }),

  // --- профили компании -----------------------------------------------------
  profiles: () => request<CompanyProfile[]>('/profiles'),

  activateProfile: (id: number) =>
    request<{ status: string; profile: string }>(`/profiles/${id}/activate`, { method: 'POST' }),

  // --- дайджест -------------------------------------------------------------
  digests: () => request<Digest[]>('/digests'),

  digest: (id: number) => request<Digest>(`/digests/${id}`),

  createDigest: (payload: { recipient: string; title?: string; item_ids: number[] }) =>
    request<Digest>('/digests', { method: 'POST', body: JSON.stringify(payload) }),

  toggleDigestEntry: (digestId: number, itemId: number, isExcluded: boolean) =>
    request<Digest>(`/digests/${digestId}/items/${itemId}`, {
      method: 'PATCH',
      body: JSON.stringify({ is_excluded: isExcluded }),
    }),

  deleteDigest: (id: number) => request<void>(`/digests/${id}`, { method: 'DELETE' }),

  digestExportUrl: (id: number, format: 'html' | 'md') =>
    `${BASE}/digests/${id}/export?format=${format}`,
}
