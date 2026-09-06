/** Профиль компании — US5, FR-050, FR-052, ADR-0005. */

import { useEffect, useState } from 'react'
import { ApiError, api } from '../api/client'
import type { CompanyProfile } from '../api/types'

interface Props {
  onToast: (message: string) => void
  onProfilesChanged: () => void
}

const SECTIONS: Array<{ key: keyof CompanyProfile; label: string; hint: string }> = [
  { key: 'products', label: 'Ключевые продукты', hint: 'от них зависит критерий применимости К1' },
  { key: 'regimes', label: 'Режимы и статусы', hint: 'налоговые льготы, аккредитации, реестры' },
  { key: 'risk_areas', label: 'Зоны риска', hint: 'повышают К4, К5 и вероятность эскалации' },
  { key: 'growth_areas', label: 'Зоны роста', hint: 'льготы и меры поддержки — влияют на К3' },
  { key: 'competitors', label: 'Конкуренты', hint: 'и смежные игроки рынка' },
  { key: 'noise_markers', label: 'Признаки шума', hint: 'что заведомо нерелевантно' },
]

export function ProfilePage({ onToast, onProfilesChanged }: Props) {
  const [profiles, setProfiles] = useState<CompanyProfile[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .profiles()
      .then(setProfiles)
      .catch((e: ApiError) => setError(e.message))
  }, [])

  async function activate(profile: CompanyProfile) {
    try {
      await api.activateProfile(profile.id)
      setProfiles((prev) => prev.map((p) => ({ ...p, is_active: p.id === profile.id })))
      onProfilesChanged()
      onToast(`Профиль «${profile.name}» активен. Лента переоценивается в фоне`)
    } catch (e) {
      onToast((e as ApiError).message)
    }
  }

  if (error) {
    return (
      <div className="card" style={{ borderColor: 'var(--risk)' }}>
        <b>Не удалось загрузить профили.</b> {error}
      </div>
    )
  }

  return (
    <>
      <div className="card" style={{ marginBottom: 14 }}>
        <p style={{ margin: 0, fontSize: 13.5, lineHeight: 1.5 }}>
          Профиль компании — это <b>конфигурация релевантности</b>, а не справочная
          карточка. Он подставляется в промпт оценки: смена профиля переоценивает
          всю ленту, не меняя ни строчки кода. Так одно решение работает для разных
          компаний группы.
        </p>
      </div>

      <div className="cards two">
        {profiles.map((profile) => (
          <div
            className="card"
            key={profile.id}
            style={{
              borderColor: profile.is_active ? 'var(--brand)' : undefined,
              boxShadow: profile.is_active ? '0 0 0 1px var(--brand)' : undefined,
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'flex-start' }}>
              <div>
                <h2 style={{ fontFamily: 'var(--font-head)', fontSize: 16, margin: 0 }}>
                  {profile.name}
                </h2>
                <p style={{ margin: '4px 0 0', fontSize: 12.5, color: 'var(--muted)' }}>
                  {profile.industry}
                </p>
              </div>
              {profile.is_active ? (
                <span className="badge badge-brand">активен</span>
              ) : (
                <button type="button" className="btn btn-sm" onClick={() => activate(profile)}>
                  переключить
                </button>
              )}
            </div>

            <div style={{ marginTop: 14, display: 'flex', flexDirection: 'column', gap: 12 }}>
              {SECTIONS.map(({ key, label, hint }) => {
                const values = profile[key] as string[]
                if (!values?.length) return null
                return (
                  <div key={String(key)}>
                    <p className="block-label" style={{ marginBottom: 5 }}>
                      {label} <span style={{ textTransform: 'none', letterSpacing: 0, fontWeight: 400 }}>— {hint}</span>
                    </p>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
                      {values.map((v) => (
                        <span className="badge" key={v} title={v}>
                          {v.length > 64 ? `${v.slice(0, 64)}…` : v}
                        </span>
                      ))}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        ))}
      </div>
    </>
  )
}
