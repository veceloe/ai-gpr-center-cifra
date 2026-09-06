import { useCallback, useEffect, useState } from 'react'
import { NavLink, Route, Routes, useLocation } from 'react-router-dom'
import { api } from './api/client'
import type { CompanyProfile } from './api/types'
import { ActPage } from './pages/ActPage'
import { ActsPage } from './pages/ActsPage'
import { DigestsPage } from './pages/DigestsPage'
import { FeedPage } from './pages/FeedPage'
import { ProfilePage } from './pages/ProfilePage'
import { SourcesPage } from './pages/SourcesPage'

interface Toast {
  id: number
  message: string
  undo?: () => void | Promise<void>
}

const PAGE_TITLES: Record<string, { title: string; sub: string }> = {
  '/': {
    title: 'Лента',
    sub: 'Отсортирована по влиянию на компанию, а не по дате публикации',
  },
  '/acts': {
    title: 'Досье НПА',
    sub: 'Долгоживущие карточки: стадии, хронология, динамика влияния',
  },
  '/sources': {
    title: 'Источники',
    sub: 'Добавление, отключение и разовый сбор. Ошибка одного не останавливает остальные',
  },
  '/digests': {
    title: 'Дайджесты',
    sub: 'Подборка под конкретного получателя с выгрузкой для почты',
  },
  '/profile': {
    title: 'Профиль компании',
    sub: 'Конфигурация релевантности: от неё зависит вся оценка',
  },
}

export function App() {
  const location = useLocation()
  const [toasts, setToasts] = useState<Toast[]>([])
  const [selection, setSelection] = useState<number[]>([])
  const [profiles, setProfiles] = useState<CompanyProfile[]>([])
  const [online, setOnline] = useState<boolean | null>(null)

  const loadProfiles = useCallback(() => {
    api.profiles().then(setProfiles).catch(() => setProfiles([]))
  }, [])

  useEffect(() => {
    loadProfiles()
    api
      .health()
      .then(() => setOnline(true))
      .catch(() => setOnline(false))
  }, [loadProfiles])

  const pushToast = useCallback((message: string, undo?: () => void | Promise<void>) => {
    const id = Date.now() + Math.random()
    setToasts((prev) => [...prev, { id, message, undo }])
    // Отмена должна быть заметной и доступной несколько секунд, а не спрятанной в меню.
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), undo ? 8000 : 4000)
  }, [])

  const active = profiles.find((p) => p.is_active)
  const head = PAGE_TITLES[location.pathname] ?? {
    title: 'Досье НПА',
    sub: 'Стадии, хронология и динамика влияния',
  }

  async function switchProfile(id: number) {
    const profile = profiles.find((p) => p.id === id)
    if (!profile || profile.is_active) return
    await api.activateProfile(id)
    setProfiles((prev) => prev.map((p) => ({ ...p, is_active: p.id === id })))
    pushToast(`Профиль «${profile.name}» активен. Лента переоценивается в фоне`)
  }

  return (
    <div className="shell">
      <aside className="rail">
        <div className="brand">
          <span className="brand-mark" />
          <span style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
            <span className="brand-text">
              Центр
              <br />
              PR/GR-мониторинга
            </span>
            <span className="brand-sub">GS Labs</span>
          </span>
        </div>

        <nav className="nav">
          <NavLink to="/" end>
            Лента
          </NavLink>
          <NavLink to="/acts">Досье НПА</NavLink>
          <NavLink to="/digests">
            Дайджесты
            {selection.length > 0 && <span className="count">{selection.length}</span>}
          </NavLink>
          <NavLink to="/sources">Источники</NavLink>
          <NavLink to="/profile">Профиль компании</NavLink>
        </nav>

        <div className="rail-foot">
          <div className="profile-switch">
            <label htmlFor="profile-select">Оценка с точки зрения</label>
            <select
              id="profile-select"
              value={active?.id ?? ''}
              onChange={(e) => switchProfile(Number(e.target.value))}
            >
              {profiles.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            {online === false && <span style={{ color: '#ff9d9d' }}>backend недоступен</span>}
            {online === true && <span>соединение в порядке</span>}
          </div>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div className="page-head">
            <div>
              <h1>{head.title}</h1>
              <p className="page-sub">{head.sub}</p>
            </div>
          </div>
        </header>

        <div className="content">
          <Routes>
            <Route
              path="/"
              element={
                <FeedPage
                  onToast={pushToast}
                  selection={selection}
                  onSelectionChange={setSelection}
                />
              }
            />
            <Route path="/acts" element={<ActsPage />} />
            <Route path="/acts/:id" element={<ActPage onToast={pushToast} />} />
            <Route path="/sources" element={<SourcesPage onToast={pushToast} />} />
            <Route
              path="/digests"
              element={
                <DigestsPage
                  selection={selection}
                  onSelectionChange={setSelection}
                  onToast={pushToast}
                />
              }
            />
            <Route
              path="/profile"
              element={<ProfilePage onToast={pushToast} onProfilesChanged={loadProfiles} />}
            />
          </Routes>
        </div>
      </main>

      <div className="toast-host">
        {toasts.map((toast) => (
          <div className="toast" key={toast.id} role="status">
            <span>{toast.message}</span>
            {toast.undo && (
              <button
                type="button"
                onClick={async () => {
                  setToasts((prev) => prev.filter((t) => t.id !== toast.id))
                  await toast.undo?.()
                }}
              >
                Отменить
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
