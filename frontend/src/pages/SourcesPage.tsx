/** Источники — US2, FR-003, FR-004, FR-008, FR-009. */

import { useEffect, useRef, useState } from 'react'
import { ApiError, api } from '../api/client'
import type { Source, SourceType } from '../api/types'
import { SOURCE_TYPE_LABELS, formatRelative, plural } from '../lib/format'

interface Props {
  onToast: (message: string) => void
}

export function SourcesPage({ onToast }: Props) {
  const [sources, setSources] = useState<Source[]>([])
  const [error, setError] = useState<string | null>(null)
  const addDialog = useRef<HTMLDialogElement>(null)
  const manualDialog = useRef<HTMLDialogElement>(null)

  const [form, setForm] = useState<{ type: SourceType; url: string; title: string }>({
    type: 'rss',
    url: '',
    title: '',
  })
  const [manual, setManual] = useState({ title: '', raw_text: '', url: '' })

  async function load() {
    try {
      setSources(await api.sources())
      setError(null)
    } catch (e) {
      setError((e as ApiError).message)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  async function addSource() {
    try {
      await api.createSource({ type: form.type, url: form.url.trim(), title: form.title.trim() || undefined })
      addDialog.current?.close()
      setForm({ type: 'rss', url: '', title: '' })
      await load()
      onToast('Источник добавлен. Запустите сбор, чтобы получить материалы')
    } catch (e) {
      onToast((e as ApiError).message)
    }
  }

  async function addManual() {
    try {
      await api.createItem({
        title: manual.title.trim(),
        raw_text: manual.raw_text.trim(),
        url: manual.url.trim() || undefined,
      })
      manualDialog.current?.close()
      setManual({ title: '', raw_text: '', url: '' })
      onToast('Материал добавлен и пойдёт в обработку наравне с собранными')
    } catch (e) {
      onToast((e as ApiError).message)
    }
  }

  async function collect(source: Source) {
    try {
      await api.collectNow(source.id)
      onToast(`Сбор из «${source.title}» запущен`)
      setTimeout(load, 2500)
    } catch (e) {
      onToast((e as ApiError).message)
    }
  }

  async function toggle(source: Source) {
    await api.patchSource(source.id, { is_active: !source.is_active })
    await load()
  }

  async function remove(source: Source) {
    await api.deleteSource(source.id)
    await load()
    onToast(
      source.item_count > 0
        ? `Источник удалён. ${plural(source.item_count, 'Собранный материал остался', 'Собранные материалы остались', 'Собранные материалы остались')} в ленте — иначе она потеряет происхождение`
        : 'Источник удалён',
    )
  }

  return (
    <>
      <div className="filters">
        <button type="button" className="btn btn-primary" onClick={() => addDialog.current?.showModal()}>
          Добавить источник
        </button>
        <button type="button" className="btn" onClick={() => manualDialog.current?.showModal()}>
          Внести материал вручную
        </button>
      </div>

      {error && (
        <div className="card" style={{ borderColor: 'var(--risk)', marginBottom: 12 }}>
          <b>Не удалось загрузить источники.</b> {error}
        </div>
      )}

      <table className="grid">
        <thead>
          <tr>
            <th>Источник</th>
            <th style={{ width: 170 }}>Тип</th>
            <th style={{ width: 90 }}>Материалов</th>
            <th style={{ width: 150 }}>Последний сбор</th>
            <th style={{ width: 210 }}>Действия</th>
          </tr>
        </thead>
        <tbody>
          {sources.map((s) => (
            <tr key={s.id} style={{ opacity: s.is_active ? 1 : 0.6 }}>
              <td>
                <div style={{ fontWeight: 500 }}>{s.title}</div>
                <div style={{ fontSize: 11.5, color: 'var(--faint)', wordBreak: 'break-all' }}>{s.url}</div>
                {s.last_error && (
                  <div className="badge badge-risk" style={{ marginTop: 4 }} title={s.last_error}>
                    ошибка: {s.last_error.slice(0, 70)}
                  </div>
                )}
              </td>
              <td>
                {SOURCE_TYPE_LABELS[s.type]}
                <div style={{ fontSize: 11, color: 'var(--faint)' }}>
                  {s.item_type === 'act' ? 'НПА' : 'новости'} · раз в {s.poll_interval_min} мин
                </div>
              </td>
              <td className="num">{s.item_count}</td>
              <td style={{ fontSize: 12, color: 'var(--muted)' }}>
                {s.last_polled_at ? formatRelative(s.last_polled_at) : 'ещё не собирался'}
              </td>
              <td>
                <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap' }}>
                  <button type="button" className="btn btn-sm" onClick={() => collect(s)}>
                    собрать
                  </button>
                  <button type="button" className="btn btn-sm" onClick={() => toggle(s)}>
                    {s.is_active ? 'отключить' : 'включить'}
                  </button>
                  <button type="button" className="btn btn-sm" onClick={() => remove(s)}>
                    удалить
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <p style={{ marginTop: 10, fontSize: 12, color: 'var(--muted)' }}>
        {plural(sources.length, 'источник', 'источника', 'источников')} ·{' '}
        {sources.filter((s) => s.is_active).length} активных. Ошибка одного источника
        не останавливает сбор из остальных.
      </p>

      <dialog ref={addDialog}>
        <div className="dialog-head">
          <h2>Новый источник</h2>
        </div>
        <div className="dialog-body">
          <div className="form-row">
            <label htmlFor="s-type">Тип</label>
            <select
              id="s-type"
              value={form.type}
              onChange={(e) => setForm((f) => ({ ...f, type: e.target.value as SourceType }))}
            >
              <option value="rss">RSS-лента</option>
              <option value="web">Страница регулятора</option>
              <option value="sozd">СОЗД — законопроекты</option>
              <option value="telegram">Telegram-канал</option>
            </select>
          </div>
          <div className="form-row">
            <label htmlFor="s-url">URL</label>
            <input
              id="s-url"
              value={form.url}
              onChange={(e) => setForm((f) => ({ ...f, url: e.target.value }))}
              placeholder="https://example.ru/rss или https://t.me/channel"
            />
          </div>
          <div className="form-row">
            <label htmlFor="s-title">Название (необязательно)</label>
            <input
              id="s-title"
              value={form.title}
              onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
            />
          </div>
        </div>
        <div className="dialog-foot">
          <button type="button" className="btn" onClick={() => addDialog.current?.close()}>
            Отмена
          </button>
          <button type="button" className="btn btn-primary" disabled={!form.url.trim()} onClick={addSource}>
            Добавить
          </button>
        </div>
      </dialog>

      <dialog ref={manualDialog}>
        <div className="dialog-head">
          <h2>Материал вручную</h2>
        </div>
        <div className="dialog-body">
          <div className="form-row">
            <label htmlFor="m-title">Заголовок</label>
            <input
              id="m-title"
              value={manual.title}
              onChange={(e) => setManual((m) => ({ ...m, title: e.target.value }))}
            />
          </div>
          <div className="form-row">
            <label htmlFor="m-text">Текст</label>
            <textarea
              id="m-text"
              value={manual.raw_text}
              onChange={(e) => setManual((m) => ({ ...m, raw_text: e.target.value }))}
            />
          </div>
          <div className="form-row">
            <label htmlFor="m-url">Ссылка на оригинал (необязательно)</label>
            <input
              id="m-url"
              value={manual.url}
              onChange={(e) => setManual((m) => ({ ...m, url: e.target.value }))}
            />
          </div>
        </div>
        <div className="dialog-foot">
          <button type="button" className="btn" onClick={() => manualDialog.current?.close()}>
            Отмена
          </button>
          <button
            type="button"
            className="btn btn-primary"
            disabled={!manual.title.trim() || !manual.raw_text.trim()}
            onClick={addManual}
          >
            Добавить
          </button>
        </div>
      </dialog>
    </>
  )
}
